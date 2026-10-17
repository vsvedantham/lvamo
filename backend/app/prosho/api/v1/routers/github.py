import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.schemas.github import AvailableRepos, ClaimResponse, ClaimStatusUpdate, ConnectRepo
from app.prosho.schemas.project import ProjectResponse
from app.prosho.services import claims as claims_service
from app.prosho.services import claims_view
from app.prosho.services import github_connect
from app.prosho.services.auth import get_current_user
from app.prosho.services.manifest_sync import sync_project
from app.prosho.services.project import get_owned

router = APIRouter(prefix="/projects/{project_id}")


@router.get("/github/repos", response_model=AvailableRepos)
async def available_repos(project_id: uuid.UUID, user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project = await get_owned(project_id, user, db)
    return await github_connect.available_repos(project, user)


@router.post("/github/connect", response_model=ProjectResponse)
async def connect(project_id: uuid.UUID, body: ConnectRepo, user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project = await get_owned(project_id, user, db)
    return ProjectResponse.from_project(await github_connect.connect_repo(project, body.repo_id, user, db))


@router.delete("/github", response_model=ProjectResponse)
async def disconnect(project_id: uuid.UUID, user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project = await get_owned(project_id, user, db)
    return ProjectResponse.from_project(await github_connect.disconnect_repo(project, user, db))


@router.post("/sync", response_model=ProjectResponse)
async def sync_now(project_id: uuid.UUID, user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project = await get_owned(project_id, user, db)
    return ProjectResponse.from_project(await sync_project(project, db, actor_id=user.id))


@router.get("/claims", response_model=list[ClaimResponse])
async def list_claims(project_id: uuid.UUID, user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project = await get_owned(project_id, user, db)
    claims = await claims_service.list_claims(project, db)
    resolved = {c.key: c for c in await claims_view.resolve(project, claims, db)}
    return [ClaimResponse.model_validate(c).model_copy(update={
        "status": resolved[c.key].status, "latest_value": resolved[c.key].latest_value,
        "latest_unit": resolved[c.key].latest_unit, "latest_at": resolved[c.key].latest_at,
    }) for c in claims]


@router.patch("/claims/{claim_id}", response_model=ClaimResponse)
async def update_claim(project_id: uuid.UUID, claim_id: uuid.UUID, body: ClaimStatusUpdate,
                       user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project = await get_owned(project_id, user, db)
    return await claims_service.set_manual_status(project, claim_id, body.manual_status, user, db)
