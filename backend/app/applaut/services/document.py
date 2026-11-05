import asyncio
import copy
import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.storage import generate_presigned_url, upload_file
from app.applaut.generation.template import generate_cover_letter, generate_resume
from app.applaut.models.generated_document import GeneratedDocument
from app.applaut.models.opportunity import Opportunity
from app.applaut.models.resume import Resume
from app.applaut.models.user import User
from app.applaut.services.audit import log_action
from app.applaut.services.profile import get_active_profile
from app.applaut.services.visibility import require_visible_opportunity

logger = logging.getLogger(__name__)

ALLOWED_MODES = {"template", "ai"}


async def _get_opportunity(opportunity_id: str, user: User, db: AsyncSession) -> Opportunity:
    return await require_visible_opportunity(opportunity_id, user.id, db)


async def _get_master_resume(user: User, db: AsyncSession) -> Resume:
    resume = await db.scalar(
        select(Resume).where(Resume.user_id == user.id, Resume.is_master == True)
    )
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Upload a master resume before generating documents",
        )
    return resume


def _store_in_r2(content: str, key: str) -> str | None:
    if not settings.r2_bucket_name:
        return None
    try:
        upload_file(key, content.encode("utf-8"), "text/markdown")
        return key
    except Exception as exc:
        logger.warning("R2 upload failed for %s: %s", key, exc)
        return None


async def generate_documents(
    opportunity_id: str,
    mode: str,
    user: User,
    db: AsyncSession,
) -> tuple[GeneratedDocument, GeneratedDocument]:
    if mode not in ALLOWED_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"mode must be one of {ALLOWED_MODES}",
        )

    profile = await get_active_profile(user, db)
    opp = await _get_opportunity(opportunity_id, user, db)
    if profile.job_engine != "basic" or opp.owner_user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Documents for this job come from your job engine, not Applaut's templates",
        )
    resume = await _get_master_resume(user, db)

    if mode == "ai":
        from app.applaut.generation.ai_generator import generate_cover_letter_ai, generate_resume_ai
        resume_content = await generate_resume_ai(opp, profile, resume)
        cover_content = await generate_cover_letter_ai(opp, profile, resume)
        ai_model = "gpt-4o-mini"
    else:
        resume_content = generate_resume(opp, profile, resume)
        cover_content = generate_cover_letter(opp, profile, resume)
        ai_model = None

    # Mark previous docs for this opportunity as no longer current
    prev_docs = await db.scalars(
        select(GeneratedDocument).where(
            GeneratedDocument.opportunity_id == opp.id,
            GeneratedDocument.user_id == user.id,
            GeneratedDocument.is_current == True,
        )
    )
    for doc in prev_docs:
        doc.is_current = False

    run_id = uuid.uuid4()
    resume_key = f"documents/{user.id}/{opp.id}/{run_id}/tailored_resume.md"
    cover_key = f"documents/{user.id}/{opp.id}/{run_id}/cover_letter.md"

    resume_doc = GeneratedDocument(
        user_id=user.id,
        profile_id=profile.id,
        opportunity_id=opp.id,
        source_resume_id=resume.id,
        document_type="tailored_resume",
        generation_mode=mode,
        content=resume_content,
        r2_key=_store_in_r2(resume_content, resume_key),
        ai_model=ai_model,
        is_current=True,
    )
    cover_doc = GeneratedDocument(
        user_id=user.id,
        profile_id=profile.id,
        opportunity_id=opp.id,
        source_resume_id=resume.id,
        document_type="cover_letter",
        generation_mode=mode,
        content=cover_content,
        r2_key=_store_in_r2(cover_content, cover_key),
        ai_model=ai_model,
        is_current=True,
    )

    db.add(resume_doc)
    db.add(cover_doc)

    from app.applaut.services.audit import log_action
    await log_action(
        action="document.generate",
        db=db,
        user_id=str(user.id),
        entity_type="opportunity",
        entity_id=str(opp.id),
        after_state={"mode": mode, "company": opp.company_name, "title": opp.title},
    )

    await db.commit()
    await db.refresh(resume_doc)
    await db.refresh(cover_doc)
    return resume_doc, cover_doc


async def get_opportunity_documents(
    opportunity_id: str,
    user: User,
    db: AsyncSession,
) -> tuple[GeneratedDocument | None, GeneratedDocument | None]:
    docs = await db.scalars(
        select(GeneratedDocument).where(
            GeneratedDocument.opportunity_id == opportunity_id,
            GeneratedDocument.user_id == user.id,
            GeneratedDocument.is_current == True,
        )
    )
    tailored_resume = None
    cover_letter = None
    for doc in docs:
        if doc.document_type == "tailored_resume":
            tailored_resume = doc
        elif doc.document_type == "cover_letter":
            cover_letter = doc
    return tailored_resume, cover_letter


async def get_document(
    document_id: str,
    user: User,
    db: AsyncSession,
) -> GeneratedDocument:
    try:
        doc = await db.get(GeneratedDocument, uuid.UUID(str(document_id)))
    except ValueError:
        doc = None
    if not doc or doc.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


FILE_LINK_SECONDS = 300


def _details_response(doc: GeneratedDocument, details: dict) -> dict:
    entries = {e["id"]: e for e in details["profile"]["experience"] + details["profile"].get("projects", [])}

    def label(eid: str) -> str:
        e = entries.get(eid, {})
        return " at ".join(x for x in (e.get("title"), e.get("company")) if x) or e.get("name") or eid
    return {"document_id": doc.id, "is_current": doc.is_current, "bullets": [
        {"fact_id": b["id"], "entry": label(e["id"]), "original": b["original"], "tailored": b["tailored"],
         "use": b["use"], "note": b["note"]}
        for e in details["entries"] for b in e["bullets"]]}


async def _cv_with_details(document_id: str, user: User, db: AsyncSession) -> GeneratedDocument:
    doc = await get_document(document_id, user, db)
    if doc.document_type != "tailored_resume" or not doc.details:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This document has no tailored bullets")
    return doc


async def get_cv_details(document_id: str, user: User, db: AsyncSession) -> dict:
    doc = await _cv_with_details(document_id, user, db)
    return _details_response(doc, doc.details)


async def choose_bullet_version(document_id: str, fact_id: str, version: str, user: User,
                                db: AsyncSession) -> tuple[GeneratedDocument, dict]:
    """Show one CV bullet in its tailored or original wording. The CV is built
    again in code from its stored details (no model) and saved as a new current
    version; the previous one stays, so the choice can be traced."""
    from app.applaut.ai import handlers
    from app.applaut.documents.render import DocumentError, rerender_cv

    doc = await _cv_with_details(document_id, user, db)
    doc = await db.get(GeneratedDocument, doc.id, with_for_update=True, populate_existing=True)  # one switch at a time
    if not doc.is_current:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A newer version of this CV exists; reload it")
    details = copy.deepcopy(doc.details)
    bullet = next((b for e in details["entries"] for b in e["bullets"] if b["id"] == fact_id), None)
    if bullet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That bullet isn't on this CV")
    if version == "tailored" and not bullet["tailored"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="This bullet has no tailored wording")
    if bullet["use"] == version:
        return doc, _details_response(doc, details)

    bullet["use"] = version
    details["choices"].append({"fact_id": fact_id, "use": version, "from_document": str(doc.id),
                               "at": datetime.now(timezone.utc).isoformat()})
    try:
        own = None
        if (details.get("template") or {}).get("id"):
            own = await handlers.own_cv(db, user.id, details["template"]["id"])
        rendered, details = await asyncio.to_thread(rerender_cv, details, own)
    except handlers.PermanentError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="File storage isn't configured")
    except DocumentError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    key = f"applaut/documents/{user.id}/{doc.opportunity_id}/{rendered.sha256[:8]}/cv.pdf"
    try:
        await handlers.store_file(key, rendered.pdf, "application/pdf")
    except handlers.PermanentError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="File storage isn't configured")

    doc.is_current = False
    new = GeneratedDocument(
        user_id=doc.user_id, profile_id=doc.profile_id, application_id=doc.application_id,
        opportunity_id=doc.opportunity_id, document_type=doc.document_type, generation_mode=doc.generation_mode,
        content=rendered.text, file_name=doc.file_name, r2_key=key, ai_model=doc.ai_model, is_current=True,
        engine=doc.engine, content_type=doc.content_type, content_sha256=rendered.sha256, details=details,
    )
    db.add(new)
    await db.flush()
    await log_action(action="document.bullet_choice", db=db, user_id=str(user.id), entity_type="generated_document",
                     entity_id=str(new.id), before_state={"document_id": str(doc.id), "fact_id": fact_id},
                     after_state={"document_id": str(new.id), "fact_id": fact_id, "use": version})
    await db.commit()
    await db.refresh(new)
    return new, _details_response(new, details)


async def get_document_file_link(document_id: str, user: User, db: AsyncSession) -> tuple[str, str]:
    """A short-lived signed link to a document's PDF, for its owner only."""
    doc = await get_document(document_id, user, db)
    if doc.content_type != "application/pdf" or not doc.r2_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This document has no file")
    if not settings.r2_bucket_name:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="File storage isn't configured")
    stem = "CV" if doc.document_type == "tailored_resume" else "Cover_Letter"
    file_name = doc.file_name or f"{stem}.pdf"
    return generate_presigned_url(doc.r2_key, expires_in=FILE_LINK_SECONDS, download_name=file_name), file_name
