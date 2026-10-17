from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.applaut.discovery.scheduler import get_discovery_schedule, sync_discovery_task
from app.applaut.models.user import User
from app.applaut.services.auth import get_current_user
from app.applaut.services.profile import get_active_profile

router = APIRouter(prefix="/scheduler")


class ProfileJobStatus(BaseModel):
    profile_id: str
    next_run_at: str | None
    interval_hours: int


class SchedulerStatusResponse(BaseModel):
    jobs: list[ProfileJobStatus]
    discovery_enabled: bool
    discovery_frequency_hours: int
    last_discovery_at: str | None
    last_scored_at: str | None


@router.get("/status", response_model=SchedulerStatusResponse)
async def get_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await get_active_profile(user, db)
    job = await get_discovery_schedule(profile.id, db)
    profile_jobs = [job] if job else []

    return SchedulerStatusResponse(
        jobs=[ProfileJobStatus(**j) for j in profile_jobs],
        discovery_enabled=profile.discovery_enabled,
        discovery_frequency_hours=profile.discovery_frequency_hours,
        last_discovery_at=profile.last_discovery_at.isoformat() if profile.last_discovery_at else None,
        last_scored_at=profile.last_scored_at.isoformat() if profile.last_scored_at else None,
    )


@router.post("/enable", response_model=SchedulerStatusResponse)
async def enable_discovery(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await get_active_profile(user, db)
    profile.discovery_enabled = True
    await db.commit()
    await db.refresh(profile)
    await sync_discovery_task(profile.id, db)
    return await get_status(user, db)


@router.post("/disable", response_model=SchedulerStatusResponse)
async def disable_discovery(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await get_active_profile(user, db)
    profile.discovery_enabled = False
    await db.commit()
    await db.refresh(profile)
    await sync_discovery_task(profile.id, db)
    return await get_status(user, db)
