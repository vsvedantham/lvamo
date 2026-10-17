"""Which opportunities a user may see.

Opportunities found by Applaut Basic are shared (owner_user_id IS NULL).
Those brought in by an AI engine belong to one user (owner_user_id set) and
must never reach anyone else. Every read of `opportunities` goes through
these helpers; a job the caller can't see is reported as not found (404),
so its existence isn't leaked."""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.models.opportunity import Opportunity


def visible_to(user_id: uuid.UUID) -> ColumnElement[bool]:
    return or_(Opportunity.owner_user_id.is_(None), Opportunity.owner_user_id == user_id)


def is_visible(opp: Opportunity, user_id: uuid.UUID) -> bool:
    return opp.owner_user_id is None or opp.owner_user_id == user_id


async def get_visible_opportunity(
    opportunity_id: str | uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> Opportunity | None:
    try:
        opp = await db.get(Opportunity, uuid.UUID(str(opportunity_id)))
    except ValueError:
        return None
    return opp if opp is not None and is_visible(opp, user_id) else None


async def require_visible_opportunity(
    opportunity_id: str | uuid.UUID, user_id: uuid.UUID, db: AsyncSession, active_only: bool = True
) -> Opportunity:
    opp = await get_visible_opportunity(opportunity_id, user_id, db)
    if opp is None or (active_only and not opp.is_active):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    return opp
