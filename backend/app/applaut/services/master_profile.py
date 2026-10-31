import asyncio

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.documents.profile_schema import ProfileError, parse_yaml, to_yaml, validate_profile
from app.applaut.documents.render import DocumentError, sample_documents
from app.applaut.models.master_profile import MasterProfile
from app.applaut.models.user import User
from app.applaut.schemas.master_profile import MasterProfileResponse, MasterProfileSave
from app.applaut.services.audit import log_action


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

