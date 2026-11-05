import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.models.user import User
from app.applaut.schemas.cv_template import CvTemplateResponse, CvTemplateState, PreviewWhich, TemplatePreviewResponse
from app.applaut.services import cv_template as svc
from app.applaut.services.auth import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/cv-template")


@router.get("", response_model=CvTemplateState)
async def get_state(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The active template (if any) and an upload not switched on yet (if any)."""
    return await svc.state(user, db)


@router.post("", response_model=CvTemplateResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload(file: UploadFile = File(...), user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    """Upload a .docx CV; Applaut AI reads it in the queue and builds the template."""
    t = await svc.upload(file, user, db)
    return await svc.to_response(t, db)


@router.get("/{template_id}/preview/{which}", response_model=TemplatePreviewResponse)
async def preview(template_id: uuid.UUID, which: PreviewWhich, user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    """A short-lived link to the upload as PDF (`original`) or the template filled with its own text (`rebuilt`)."""
    url, file_name = await svc.preview_link(template_id, which, user, db)
    return TemplatePreviewResponse(url=url, expires_in=svc.PREVIEW_LINK_SECONDS, file_name=file_name)


@router.post("/{template_id}/use", response_model=CvTemplateResponse)
async def use(template_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Switch the template on for every new CV."""
    return await svc.to_response(await svc.use(template_id, user, db), db)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(template_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Switch it off (back to the standard template) or drop an upload not switched on."""
    await svc.remove(template_id, user, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
