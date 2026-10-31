"""Work over time (BETA_PLAN Phase 3): milestones, mentor feedback, the
commit timeline and page stats. The owner and assigned mentors can use all
of it; who may change what is decided in the services."""
import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.schemas.activity import PageStats, Timeline
from app.prosho.schemas.team import (
    FeedbackCreate, FeedbackThread, FeedbackUpdate, MilestoneCreate, MilestoneResponse, MilestoneUpdate,
)
from app.prosho.services import feedback, milestones, page_stats, timeline
from app.prosho.services.auth import get_current_user
from app.prosho.services.project import get_for_team, get_owned

router = APIRouter(prefix="/projects/{project_id}")


@router.get("/milestones", response_model=list[MilestoneResponse])
async def list_milestones(project_id: uuid.UUID, user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project, _ = await get_for_team(project_id, user, db)
    return await milestones.responses(await milestones.list_milestones(project.id, db), db)


@router.post("/milestones", response_model=MilestoneResponse, status_code=status.HTTP_201_CREATED)
async def create_milestone(project_id: uuid.UUID, body: MilestoneCreate, user: ProshoUser = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    project = await get_owned(project_id, user, db)
    return (await milestones.responses([await milestones.create(project, body, user, db)], db))[0]


@router.patch("/milestones/{milestone_id}", response_model=MilestoneResponse)
async def update_milestone(project_id: uuid.UUID, milestone_id: uuid.UUID, body: MilestoneUpdate,
                           user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project, access = await get_for_team(project_id, user, db)
    m = await milestones.update(project, access, milestone_id, body, user, db)
    return (await milestones.responses([m], db))[0]


@router.delete("/milestones/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_milestone(project_id: uuid.UUID, milestone_id: uuid.UUID, user: ProshoUser = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    await milestones.delete(await get_owned(project_id, user, db), milestone_id, user, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/feedback", response_model=list[FeedbackThread])
async def list_feedback(project_id: uuid.UUID, user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project, _ = await get_for_team(project_id, user, db)
    return await feedback.list_threads(project, db)


@router.post("/feedback", response_model=list[FeedbackThread], status_code=status.HTTP_201_CREATED)
async def post_feedback(project_id: uuid.UUID, body: FeedbackCreate, user: ProshoUser = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    project, _ = await get_for_team(project_id, user, db)
    await feedback.create(project, body, user, db)
    return await feedback.list_threads(project, db)


@router.patch("/feedback/{feedback_id}", response_model=list[FeedbackThread])
async def update_feedback(project_id: uuid.UUID, feedback_id: uuid.UUID, body: FeedbackUpdate,
                          user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project, _ = await get_for_team(project_id, user, db)
    await feedback.set_resolved(project, feedback_id, body.resolved, user, db)
    return await feedback.list_threads(project, db)


@router.get("/timeline", response_model=Timeline | None)
async def get_timeline(project_id: uuid.UUID, user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project, _ = await get_for_team(project_id, user, db)
    return await timeline.build(project, db, include_messages=True)


@router.get("/stats", response_model=PageStats)
async def get_stats(project_id: uuid.UUID, days: int = Query(default=30, ge=1, le=page_stats.MAX_DAYS),
                    user: ProshoUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project, _ = await get_for_team(project_id, user, db)
    return await page_stats.summary(project.id, days, db)
