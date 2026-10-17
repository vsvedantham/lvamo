"""Owner-side evidence management: CI tokens, evidence history, and the
data module's sources (with an on-demand check)."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.prosho.models.enums import ProjectType
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.modules import data_science_page, source_checks
from app.prosho.schemas.evidence import EvidenceResponse, TokenCreate, TokenCreated, TokenResponse
from app.prosho.schemas.public import DataModule
from app.prosho.services import claims_view, ingest_tokens
from app.prosho.services import evidence as evidence_service
from app.prosho.services.auth import get_current_user
from app.prosho.services.project import get_owned

router = APIRouter(prefix="/projects/{project_id}")


@router.get("/tokens", response_model=list[TokenResponse])
async def list_tokens(project_id: uuid.UUID, user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await ingest_tokens.list_tokens(await get_owned(project_id, user, db), db)


@router.post("/tokens", response_model=TokenCreated, status_code=status.HTTP_201_CREATED)
async def create_token(project_id: uuid.UUID, body: TokenCreate, user: ProshoUser = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    row, token = await ingest_tokens.create_token(await get_owned(project_id, user, db), body.label.strip(), user, db)
    return TokenCreated(**TokenResponse.model_validate(row).model_dump(), token=token)


@router.delete("/tokens/{token_id}", response_model=TokenResponse)
async def revoke_token(project_id: uuid.UUID, token_id: uuid.UUID, user: ProshoUser = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    return await ingest_tokens.revoke_token(await get_owned(project_id, user, db), token_id, user, db)


@router.get("/evidence", response_model=list[EvidenceResponse])
async def evidence_history(project_id: uuid.UUID, key: str | None = None, limit: int = Query(default=50, ge=1, le=200),
                           user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await evidence_service.history(await get_owned(project_id, user, db), db, key=key, limit=limit)


@router.get("/data-module", response_model=DataModule)
async def data_module(project_id: uuid.UUID, user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project = await get_owned(project_id, user, db)
    return await data_science_page.build(project, await claims_view.active_claims(project, db), db)


@router.post("/sources/check", response_model=DataModule)
async def check_sources_now(project_id: uuid.UUID, user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project = await get_owned(project_id, user, db)
    if project.project_type != ProjectType.data_science or not source_checks.configured_sources(project):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="No data sources to check — list them under data.sources in prosho.yaml")
    last = await source_checks.last_checked_at(project.id, db)
    if last and datetime.now(timezone.utc) - last < source_checks.ON_DEMAND_MIN_GAP:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Sources were checked in the last 10 minutes — try again a little later")
    await source_checks.check_project_sources(project, db, trigger="on_demand")
    return await data_science_page.build(project, await claims_view.active_claims(project, db), db)
