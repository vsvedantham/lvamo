from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.applaut.models.application import Application
from app.applaut.models.generated_document import GeneratedDocument
from app.applaut.models.job_assessment import JobAssessment
from app.applaut.models.opportunity import Opportunity
from app.applaut.models.routine import RoutineJob
from app.applaut.models.score import Score
from app.applaut.models.user import User
from app.applaut.services.auth import get_current_user
from app.applaut.services.profile import get_active_profile
from app.applaut.services.visibility import visible_to

router = APIRouter(prefix="/stats")


class ApplicationStats(BaseModel):
    total: int
    pending_review: int
    submitted: int
    interviewing: int
    offered: int


class DashboardStats(BaseModel):
    opportunities_found: int
    good_matches: int
    near_misses: int
    documents_generated: int
    applications: ApplicationStats


@router.get("", response_model=DashboardStats)
async def get_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = user.id
    profile = await get_active_profile(user, db)
    good_threshold = profile.good_threshold
    near_miss_threshold = good_threshold - 15

    if profile.job_engine == "own_routine":
        # Your routine's jobs only (Applaut Basic's shared pool is hidden for
        # you, as on Opportunities), ranked by the routine's match %.
        routine_opps = (
            select(RoutineJob.opportunity_id).where(RoutineJob.user_id == uid)
            .union(select(Opportunity.id).where(Opportunity.owner_user_id == uid))
        )
        opportunities_found = await db.scalar(
            select(func.count(Opportunity.id)).where(Opportunity.is_active == True, Opportunity.id.in_(routine_opps))
        ) or 0
        match = select(func.count(JobAssessment.id)).where(
            JobAssessment.profile_id == profile.id, JobAssessment.engine == "own_routine",
            JobAssessment.opportunity_id.in_(routine_opps),
        )
        good_matches = await db.scalar(match.where(JobAssessment.match_score >= good_threshold)) or 0
        near_misses = await db.scalar(match.where(
            JobAssessment.match_score >= near_miss_threshold, JobAssessment.match_score < good_threshold,
        )) or 0
        return await _with_documents_and_applications(uid, db, opportunities_found, good_matches, near_misses)

    opportunities_found = await db.scalar(
        select(func.count(Opportunity.id)).where(Opportunity.is_active == True, visible_to(uid))
    ) or 0

    good_matches = await db.scalar(
        select(func.count(Score.id)).where(
            Score.user_id == uid,
            Score.total_score >= good_threshold,
        )
    ) or 0

    near_misses = await db.scalar(
        select(func.count(Score.id)).where(
            Score.user_id == uid,
            Score.total_score >= near_miss_threshold,
            Score.total_score < good_threshold,
        )
    ) or 0

    return await _with_documents_and_applications(uid, db, opportunities_found, good_matches, near_misses)


async def _with_documents_and_applications(
    uid, db: AsyncSession, opportunities_found: int, good_matches: int, near_misses: int,
) -> DashboardStats:
    documents_generated = await db.scalar(
        select(func.count(GeneratedDocument.id)).where(
            GeneratedDocument.user_id == uid,
            GeneratedDocument.is_current == True,
        )
    ) or 0

    app_total = await db.scalar(
        select(func.count(Application.id)).where(Application.user_id == uid)
    ) or 0

    def _count_status(status: str):
        return select(func.count(Application.id)).where(
            Application.user_id == uid,
            Application.status == status,
        )

    app_pending = await db.scalar(_count_status("pending_review")) or 0
    app_submitted = await db.scalar(_count_status("submitted")) or 0
    app_interviewing = await db.scalar(_count_status("interviewing")) or 0
    app_offered = await db.scalar(_count_status("offered")) or 0

    return DashboardStats(
        opportunities_found=opportunities_found,
        good_matches=good_matches,
        near_misses=near_misses,
        documents_generated=documents_generated,
        applications=ApplicationStats(
            total=app_total,
            pending_review=app_pending,
            submitted=app_submitted,
            interviewing=app_interviewing,
            offered=app_offered,
        ),
    )
