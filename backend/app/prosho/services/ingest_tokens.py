"""Per-project CI tokens (BETA_PLAN §11): random 32 bytes, shown once,
stored as SHA-256, scoped to one project, revocable, last use tracked."""
import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.prosho_ingest_token import ProshoIngestToken
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.services import audit

TOKEN_PREFIX = "psho_"
MAX_ACTIVE_TOKENS = 10


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def list_tokens(project: ProshoProject, db: AsyncSession) -> list[ProshoIngestToken]:
    rows = await db.scalars(select(ProshoIngestToken)
                            .where(ProshoIngestToken.project_id == project.id)
                            .order_by(ProshoIngestToken.revoked_at.is_not(None), ProshoIngestToken.created_at.desc()))
    return list(rows)


async def create_token(project: ProshoProject, label: str, user: ProshoUser, db: AsyncSession) -> tuple[ProshoIngestToken, str]:
    active = await db.scalar(select(func.count()).select_from(ProshoIngestToken).where(
        ProshoIngestToken.project_id == project.id, ProshoIngestToken.revoked_at.is_(None)))
    if active >= MAX_ACTIVE_TOKENS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"A project can have at most {MAX_ACTIVE_TOKENS} active tokens — revoke one first")
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    row = ProshoIngestToken(project_id=project.id, token_hash=hash_token(token), token_prefix=token[:9],
                            label=label, created_by=user.id)
    db.add(row)
    await db.flush()
    audit.record(db, actor_id=user.id, action="token.create", entity="ingest_token", entity_id=row.id,
                 after={"project_id": project.id, "label": label, "token_prefix": row.token_prefix})
    await db.commit()
    await db.refresh(row)
    return row, token


async def revoke_token(project: ProshoProject, token_id: uuid.UUID, user: ProshoUser, db: AsyncSession) -> ProshoIngestToken:
    row = await db.get(ProshoIngestToken, token_id)
    if not row or row.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        audit.record(db, actor_id=user.id, action="token.revoke", entity="ingest_token", entity_id=row.id,
                     before={"revoked_at": None}, after={"revoked_at": row.revoked_at})
        await db.commit()
        await db.refresh(row)
    return row


async def project_for_token(token: str, db: AsyncSession) -> ProshoProject | None:
    """The active project a live token belongs to, or None. Marks it used."""
    if not token.startswith(TOKEN_PREFIX):
        return None
    row = await db.scalar(select(ProshoIngestToken).where(ProshoIngestToken.token_hash == hash_token(token)))
    if row is None or row.revoked_at is not None:
        return None
    project = await db.get(ProshoProject, row.project_id)
    if project is None or not project.is_active:
        return None
    row.last_used_at = datetime.now(timezone.utc)
    return project
