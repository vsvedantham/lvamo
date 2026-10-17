from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.models.user import User
from app.applaut.schemas.job_engine import (
    ConnectionTestRequest, ConnectionTestResponse, JobEngineResponse, RoutineConnectionInput,
    RoutineRunInfo, RoutineSyncInfo, SetEngineRequest, SyncNowResponse,
)
from app.applaut.services import job_engine as svc
from app.applaut.services.auth import get_current_user
from app.applaut.services.profile import get_active_profile
from app.db.session import get_db

router = APIRouter(prefix="/job-engine")


@router.get("", response_model=JobEngineResponse)
async def get_engine(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.get_job_engine(user, db)


@router.put("", response_model=JobEngineResponse)
async def set_engine(payload: SetEngineRequest, user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    await svc.set_engine(user, payload.engine.value, payload.confirm_delete_credentials, db)
    return await svc.get_job_engine(user, db)


@router.post("/routine/test", response_model=ConnectionTestResponse)
async def test_routine(payload: ConnectionTestRequest, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """Run every check against the given values (missing ones: the saved ones). Saves nothing."""
    return await svc.test_connection(user, payload, db)


@router.put("/routine", response_model=JobEngineResponse,
            responses={422: {"model": ConnectionTestResponse, "description": "A check failed; nothing saved"}})
async def save_routine(payload: RoutineConnectionInput, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    conn, result = await svc.save_connection(user, payload, db)
    if conn is None:
        return JSONResponse(status_code=422, content={"detail": "A check failed; nothing was saved",
                                                      **result.model_dump(mode="json")})
    return await svc.get_job_engine(user, db)


@router.delete("/routine", status_code=204)
async def remove_routine(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.remove_connection(user, db)


@router.post("/routine/sync-now", response_model=SyncNowResponse)
async def sync_now(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    queued, message = await svc.sync_now(user, db)
    profile = await get_active_profile(user, db)
    return SyncNowResponse(queued=queued, message=message, card=await svc.build_card(user, profile, db))


@router.get("/routine/runs", response_model=list[RoutineRunInfo])
async def list_runs(limit: int = Query(50, ge=1, le=200), user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    return await svc.list_runs(user, db, limit)


@router.get("/routine/syncs", response_model=list[RoutineSyncInfo])
async def list_syncs(limit: int = Query(20, ge=1, le=100), user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    return await svc.list_syncs(user, db, limit)
