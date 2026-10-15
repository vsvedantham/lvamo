import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.prosho.services import project as project_service
from app.prosho.services.auth import get_current_user

router = APIRouter(prefix="/projects")


@router.get("", response_model=list[ProjectResponse])
async def list_projects(user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return [ProjectResponse.from_project(p) for p in await project_service.list_projects(user, db)]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ProjectResponse.from_project(await project_service.create_project(body, user, db))


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: uuid.UUID, user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ProjectResponse.from_project(await project_service.get_owned(project_id, user, db))


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: uuid.UUID, body: ProjectUpdate, user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project = await project_service.get_owned(project_id, user, db)
    return ProjectResponse.from_project(await project_service.update_project(project, body, user, db))
