import asyncio
from datetime import datetime, timezone

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.documents.profile_schema import ProfileError, parse_yaml, to_yaml, validate_profile
from app.applaut.documents.render import DocumentError, sample_documents
from app.applaut.ai import queue
from app.applaut.ai.hosts import host_addresses
from app.applaut.models.ai_queue import AIQueueItem
from app.applaut.models.bullet_draft import BulletDraft
from app.applaut.models.master_profile import MasterProfile
from app.applaut.models.user import User
from app.applaut.schemas.master_profile import AddFactsRequest, MasterProfileResponse, MasterProfileSave
from app.applaut.services.audit import log_action
from app.applaut.services.profile import get_active_profile


def to_response(mp: MasterProfile) -> MasterProfileResponse:
    return MasterProfileResponse(data=mp.data, yaml=to_yaml(mp.data), version=mp.version,
                                 source=mp.source, updated_at=mp.updated_at)


def invalid(errors: list[str]) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "The master profile has problems; nothing was saved",
                                                  "errors": errors})


async def get_master_profile(user: User, db: AsyncSession) -> MasterProfile | None:
    return await db.scalar(select(MasterProfile).where(MasterProfile.user_id == user.id))


async def require_master_profile(user: User, db: AsyncSession) -> MasterProfile:
    mp = await get_master_profile(user, db)
    if not mp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No master profile yet")
    return mp


async def save_master_profile(user: User, payload: MasterProfileSave, db: AsyncSession) -> MasterProfile:
    """Validate, then create or replace. Raises ProfileError with one line per problem."""
    if payload.yaml is not None:
        data, source = parse_yaml(payload.yaml), "yaml"
    else:
        data, source = validate_profile(payload.data), "manual"
    mp = await get_master_profile(user, db)
    before = mp.version if mp else None
    if mp:
        mp.data, mp.source, mp.version = data, source, mp.version + 1
    else:
        mp = MasterProfile(user_id=user.id, data=data, source=source, version=1)
        db.add(mp)
    await log_action(
        action="master_profile.save", db=db, user_id=str(user.id), entity_type="master_profile",
        entity_id=str(user.id), after_state={"source": source, "from_version": before,
                                             "roles": len(data["experience"]), "projects": len(data["projects"])},
    )
    await db.commit()
    await db.refresh(mp)
    return mp


async def preview_pdf(user: User, kind: str, db: AsyncSession) -> bytes:
    """The saved profile in the standard template, with placeholder letter text."""
    mp = await require_master_profile(user, db)
    try:
        docs = await asyncio.to_thread(sample_documents, mp.data)  # WeasyPrint is blocking
    except DocumentError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="; ".join(exc.errors))
    return docs.cv.pdf if kind == "cv" else docs.cover_letter.pdf



# ---------------------------------------------------------------- bullet bank builder (v2 plan §4)

def _entry(mp: MasterProfile, entry_id: str) -> dict:
    entry = next((e for e in mp.data.get("experience", []) + mp.data.get("projects", []) if e.get("id") == entry_id), None)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No role or project with that id")
    return entry


async def draft_response(draft: BulletDraft, db: AsyncSession) -> dict:
    out = {k: getattr(draft, k) for k in ("id", "entry_id", "notes", "status", "drafts", "left_out", "error",
                                          "created_at", "finished_at")}
    if draft.status == "pending":
        item = await db.scalar(select(AIQueueItem).where(AIQueueItem.bullet_draft_id == draft.id,
                                                          AIQueueItem.status.in_(("pending", "running"))))
        out["ahead"] = await queue.ahead_of(db, item) if item is not None and item.status == "pending" else 0
    return out


async def _open_draft(user: User, entry_id: str, db: AsyncSession) -> BulletDraft | None:
    return await db.scalar(select(BulletDraft).where(
        BulletDraft.user_id == user.id, BulletDraft.entry_id == entry_id, BulletDraft.closed_at.is_(None))
        .order_by(BulletDraft.created_at.desc()).limit(1))


async def start_draft(user: User, entry_id: str, notes: str, db: AsyncSession) -> BulletDraft:
    """Queue the writer to draft bullets for one role from the user's notes."""
    mp = await require_master_profile(user, db)
    _entry(mp, entry_id)
    profile = await get_active_profile(user, db)
    if profile.job_engine != "applaut_ai":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Drafting bullets needs Applaut AI as your job engine")
    if not host_addresses():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Applaut AI can't draft bullets right now; please try again later")
    if await _open_draft(user, entry_id, db):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="This role already has drafts; keep or discard them first")
    draft = BulletDraft(user_id=user.id, entry_id=entry_id, notes=notes.strip(), status="pending",
                        drafts=[], left_out=[], profile_version=mp.version)
    db.add(draft)
    await db.flush()
    await queue.enqueue_draft(db, draft, profile.id)
    await db.commit()
    await db.refresh(draft)
    return draft


async def latest_draft(user: User, entry_id: str, db: AsyncSession) -> BulletDraft | None:
    """The role's open drafts (not yet kept or discarded), if any."""
    _entry(await require_master_profile(user, db), entry_id)
    return await _open_draft(user, entry_id, db)


async def close_draft(user: User, entry_id: str, db: AsyncSession) -> None:
    """Discard the role's open drafts. If the writer hasn't started on them, they
    leave the queue too; if it has, its answer is ignored."""
    draft = await _open_draft(user, entry_id, db)
    if draft is not None:
        draft.closed_at = datetime.now(timezone.utc)
        await db.execute(delete(AIQueueItem).where(AIQueueItem.bullet_draft_id == draft.id,
                                                   AIQueueItem.status == "pending"))
        await db.commit()


async def add_facts(user: User, entry_id: str, payload: AddFactsRequest, db: AsyncSession) -> MasterProfile:
    """Append bullets the user approved (as they edited them) to one role's facts."""
    mp = await require_master_profile(user, db)
    _entry(mp, entry_id)
    facts = [" ".join(f.split()) for f in payload.facts if f and f.strip()]
    if not facts:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No bullets to add")
    data = {**mp.data}
    for key in ("experience", "projects"):
        data[key] = [{**e, "facts": [*e["facts"], *facts]} if e.get("id") == entry_id else e
                     for e in data.get(key, [])]
    data = validate_profile(data)  # raises ProfileError
    before = mp.version
    mp.data, mp.version = data, mp.version + 1
    if payload.draft_id is not None:
        draft = await db.get(BulletDraft, payload.draft_id)
        if draft is not None and draft.user_id == user.id and draft.entry_id == entry_id:
            draft.closed_at = datetime.now(timezone.utc)
    await log_action(
        action="master_profile.add_facts", db=db, user_id=str(user.id), entity_type="master_profile",
        entity_id=str(user.id), after_state={"entry_id": entry_id, "added": len(facts), "from_version": before,
                                             "draft_id": str(payload.draft_id) if payload.draft_id else None},
    )
    await db.commit()
    await db.refresh(mp)
    return mp
