"""The user's own CV template (APPLAUT_AI_V2_PLAN.md §5): upload a .docx, the
writer labels its lines (queue kind build_template), the user compares the
round trip and switches it on; every new CV then uses it."""
import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.ai import handlers, prompts, queue
from app.applaut.ai.hosts import host_addresses
from app.applaut.documents import own_template
from app.applaut.models.ai_queue import AIQueueItem
from app.applaut.models.cv_template import CvTemplate
from app.applaut.models.user import User
from app.applaut.schemas.cv_template import CvTemplateResponse, CvTemplateState
from app.applaut.services.audit import log_action
from app.applaut.services.profile import get_active_profile
from app.config import settings
from app.core.storage import generate_presigned_url

MAX_FILE_SIZE = 5 * 1024 * 1024
PREVIEW_LINK_SECONDS = 300
OPEN = ("reading", "ready", "failed")


async def to_response(t: CvTemplate, db: AsyncSession) -> CvTemplateResponse:
    ahead = None
    if t.status == "reading":
        item = await db.scalar(select(AIQueueItem).where(AIQueueItem.cv_template_id == t.id,
                                                         AIQueueItem.status.in_(("pending", "running"))))
        ahead = await queue.ahead_of(db, item) if item is not None else None
    return CvTemplateResponse(
        id=t.id, file_name=t.file_name, status=t.status, ahead=ahead, pages=t.pages, report=t.report or {},
        error=t.error, can_use=t.status == "ready" and not (t.report or {}).get("differences"),
        created_at=t.created_at, finished_at=t.finished_at, decided_at=t.decided_at)


async def _mine(template_id: uuid.UUID, user: User, db: AsyncSession, lock: bool = False) -> CvTemplate:
    t = await db.get(CvTemplate, template_id, with_for_update=lock, populate_existing=lock)
    if t is None or t.user_id != user.id or t.status == "discarded":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return t


async def _close_open(user: User, db: AsyncSession) -> None:
    """Drop an upload that wasn't switched on (a new upload replaces it)."""
    for t in await db.scalars(select(CvTemplate).where(CvTemplate.user_id == user.id, CvTemplate.status.in_(OPEN))):
        t.status, t.decided_at = "discarded", datetime.now(timezone.utc)
        await db.execute(delete(AIQueueItem).where(AIQueueItem.cv_template_id == t.id, AIQueueItem.status == "pending"))


async def upload(file: UploadFile, user: User, db: AsyncSession) -> CvTemplate:
    name = file.filename or "cv.docx"
    if name.lower().endswith(".pdf") or file.content_type == "application/pdf":
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail="A PDF can't be made into a template exactly. Upload the .docx (in Google Docs: "
                                   "File → Download → Microsoft Word), or keep the standard template.")
    if not name.lower().endswith(".docx"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload a .docx file")
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="The file must be 5 MB or less")
    try:
        lines = await asyncio.to_thread(own_template.read_lines, data)
    except own_template.TemplateError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.problems[0])
    shown = sum(1 for ln in lines if ln.text.strip())
    if shown == 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The file has no text")
    if shown > prompts.TEMPLATE_MAX_LINES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"The file has {shown} lines; Applaut reads CVs of up to {prompts.TEMPLATE_MAX_LINES}")
    profile = await get_active_profile(user, db)
    if profile.job_engine != "applaut_ai":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Your own template needs Applaut AI as your job engine")
    if not host_addresses():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Applaut AI can't read templates right now; please try again later")

    t = CvTemplate(id=uuid.uuid4(), user_id=user.id, kind="cv", status="reading", file_name=name[:255], report={})
    t.source_key = f"applaut/templates/{user.id}/{t.id}/upload.docx"
    try:
        await handlers.store_file(t.source_key, data, handlers.DOCX)
    except handlers.PermanentError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="File storage isn't configured")
    await _close_open(user, db)
    db.add(t)
    await db.flush()
    await queue.enqueue_template(db, t, profile.id)
    await db.commit()
    await db.refresh(t)
    return t


async def state(user: User, db: AsyncSession) -> CvTemplateState:
    active = await db.scalar(select(CvTemplate).where(CvTemplate.user_id == user.id, CvTemplate.status == "active"))
    latest = await db.scalar(select(CvTemplate).where(CvTemplate.user_id == user.id, CvTemplate.status.in_(OPEN))
                             .order_by(CvTemplate.created_at.desc()).limit(1))
    return CvTemplateState(active=await to_response(active, db) if active else None,
                           latest=await to_response(latest, db) if latest else None)


async def preview_link(template_id: uuid.UUID, which: str, user: User, db: AsyncSession) -> tuple[str, str]:
    t = await _mine(template_id, user, db)
    key = t.original_pdf_key if which == "original" else t.rebuilt_pdf_key
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No preview yet")
    if not settings.r2_bucket_name:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="File storage isn't configured")
    file_name = f"{'Your_upload' if which == 'original' else 'Applaut_template'}.pdf"
    return generate_presigned_url(key, expires_in=PREVIEW_LINK_SECONDS, download_name=file_name), file_name


async def use(template_id: uuid.UUID, user: User, db: AsyncSession) -> CvTemplate:
    """Switch the template on: every new CV uses it (the one before is retired)."""
    t = await _mine(template_id, user, db, lock=True)
    if t.status == "active":
        return t
    if t.status != "ready":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This template isn't ready to use")
    if (t.report or {}).get("differences"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="The template doesn't give your CV back exactly, so it can't be used")
    before = await db.scalar(select(CvTemplate).where(CvTemplate.user_id == user.id, CvTemplate.status == "active")
                             .with_for_update())
    now = datetime.now(timezone.utc)
    if before is not None:
        before.status, before.decided_at = "retired", now
        await db.flush()
    t.status, t.decided_at = "active", now
    await log_action(action="cv_template.use", db=db, user_id=str(user.id), entity_type="cv_template",
                     entity_id=str(t.id), before_state={"template_id": str(before.id) if before else None},
                     after_state={"template_id": str(t.id), "file_name": t.file_name})
    await db.commit()
    await db.refresh(t)
    return t


async def remove(template_id: uuid.UUID, user: User, db: AsyncSession) -> None:
    """Switch an active template off (new CVs use the standard template again),
    or drop an upload that isn't on. CVs already built keep their template."""
    t = await _mine(template_id, user, db, lock=True)
    now = datetime.now(timezone.utc)
    if t.status == "active":
        t.status, t.decided_at = "retired", now
        await log_action(action="cv_template.stop", db=db, user_id=str(user.id), entity_type="cv_template",
                         entity_id=str(t.id), before_state={"template_id": str(t.id)}, after_state={"template_id": None})
    elif t.status in OPEN:
        t.status, t.decided_at = "discarded", now
        await db.execute(delete(AIQueueItem).where(AIQueueItem.cv_template_id == t.id, AIQueueItem.status == "pending"))
    await db.commit()
