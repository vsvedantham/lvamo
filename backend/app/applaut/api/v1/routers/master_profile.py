from typing import Optional

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.models.user import User
from app.applaut.schemas.master_profile import (
    AddFactsRequest, BulletDraftResponse, DraftRequest, MasterProfileResponse, MasterProfileSave, PreviewKind,
)
from app.applaut.services import master_profile as svc
from app.applaut.services.auth import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/master-profile")


@router.get("", response_model=MasterProfileResponse)
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return svc.to_response(await svc.require_master_profile(user, db))


@router.put("", response_model=MasterProfileResponse,
            responses={422: {"description": "Validation failed; `errors` lists each problem; nothing saved"}})
async def save_profile(payload: MasterProfileSave, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    try:
        mp = await svc.save_master_profile(user, payload, db)
    except svc.ProfileError as exc:
        return svc.invalid(exc.errors)
    return svc.to_response(mp)


@router.get("/preview/{kind}", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}})
async def preview(kind: PreviewKind, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    pdf = await svc.preview_pdf(user, kind, db)
    name = "CV_preview.pdf" if kind == "cv" else "Cover_Letter_preview.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})


@router.post("/entries/{entry_id}/draft-bullets", response_model=BulletDraftResponse,
             status_code=status.HTTP_202_ACCEPTED)
async def draft_bullets(entry_id: str, payload: DraftRequest, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """Queue Applaut AI to draft CV bullets for one role from the user's notes."""
    draft = await svc.start_draft(user, entry_id, payload.notes, db)
    return await svc.draft_response(draft, db)


@router.get("/entries/{entry_id}/drafts", response_model=Optional[BulletDraftResponse])
async def get_drafts(entry_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The role's open drafts (pending, done or failed), or null."""
    draft = await svc.latest_draft(user, entry_id, db)
    return await svc.draft_response(draft, db) if draft else None


@router.delete("/entries/{entry_id}/drafts", status_code=status.HTTP_204_NO_CONTENT)
async def discard_drafts(entry_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.close_draft(user, entry_id, db)


@router.post("/entries/{entry_id}/facts", response_model=MasterProfileResponse,
             responses={422: {"description": "The profile would be invalid; `errors` lists each problem"}})
async def add_facts(entry_id: str, payload: AddFactsRequest, user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    """Append bullets the user kept (as edited) to one role's facts."""
    try:
        mp = await svc.add_facts(user, entry_id, payload, db)
    except svc.ProfileError as exc:
        return svc.invalid(exc.errors)
    return svc.to_response(mp)
