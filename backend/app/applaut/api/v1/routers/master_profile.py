from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.models.user import User
from app.applaut.schemas.master_profile import MasterProfileResponse, MasterProfileSave, PreviewKind
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
