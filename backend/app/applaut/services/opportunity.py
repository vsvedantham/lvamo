from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.applaut.models.job_assessment import JobAssessment
from app.applaut.models.opportunity import Opportunity
from app.applaut.models.score import Score
from app.applaut.models.user import User
from app.applaut.services.profile import get_active_profile
from app.applaut.services.visibility import get_visible_opportunity, visible_to
from app.applaut.discovery.engine import run_discovery_for_profile


async def trigger_discovery(user: User, db: AsyncSession) -> dict:
    profile = await get_active_profile(user, db)
    count = await run_discovery_for_profile(profile, db)
    from app.applaut.services.audit import log_action
    await log_action(
        action="discovery.run",
        db=db,
        user_id=str(user.id),
        entity_type="profile",
        entity_id=str(profile.id),
        after_state={"new_jobs_found": count},
    )
    await db.commit()

    from app.applaut.services.scoring import run_scoring
    scoring_result = await run_scoring(user, db, "rule_based")

    return {
        "new_jobs_found": count,
        "scored": scoring_result["scored"],
        "good_matches": scoring_result["good_matches"],
        "near_misses": scoring_result["near_misses"],
    }


async def list_opportunities_with_scores(
    user: User,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    country_code: str | None = None,
    source: str | None = None,
    match: str = "all",
    engine: str | None = None,
) -> tuple[list[tuple[Opportunity, Score | None, JobAssessment | None]], int, int, int]:
    profile = await get_active_profile(user, db)
    good_threshold = profile.good_threshold
    near_miss_threshold = good_threshold - 15

    # This profile's latest assessment per job (a job can have one per engine
    # if the user switched engines), so the join never duplicates a row.
    latest = (
        select(JobAssessment)
        .where(JobAssessment.profile_id == profile.id)
        .distinct(JobAssessment.opportunity_id)
        .order_by(JobAssessment.opportunity_id, JobAssessment.last_seen_at.desc())
        .subquery()
    )
    assessment = aliased(JobAssessment, latest)

    # An AI engine's match % when there is one, else Applaut's rule-based score.
    effective_score = func.coalesce(assessment.match_score, Score.total_score)

    query = (
        select(Opportunity, Score, assessment)
        .outerjoin(
            Score,
            (Score.opportunity_id == Opportunity.id) & (Score.profile_id == profile.id),
        )
        .outerjoin(assessment, assessment.opportunity_id == Opportunity.id)
        .where(
            Opportunity.is_active == True,
            visible_to(user.id),
            or_(Score.user_decision.is_(None), Score.user_decision != "dismiss"),
        )
    )

    if country_code:
        query = query.where(Opportunity.country_code == country_code)
    if source:
        query = query.where(Opportunity.source == source)
    if engine == "basic":
        query = query.where(Opportunity.owner_user_id.is_(None))
    elif engine in ("applaut_ai", "own_routine"):
        query = query.where(assessment.engine == engine)
    if match == "good":
        query = query.where(effective_score >= good_threshold)
    elif match == "near_miss":
        query = query.where(effective_score >= near_miss_threshold, effective_score < good_threshold)
    elif match == "below":
        query = query.where(effective_score < near_miss_threshold)
    elif match == "unscored":
        query = query.where(effective_score.is_(None))

    total = await db.scalar(select(func.count()).select_from(query.subquery()))

    query = query.order_by(effective_score.desc().nulls_last(), Opportunity.posted_at.desc().nulls_last())
    rows = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    return list(rows.all()), total or 0, good_threshold, near_miss_threshold


async def get_opportunity_for_user(
    opportunity_id: str, user: User, db: AsyncSession
) -> tuple[Opportunity, JobAssessment | None] | None:
    opp = await get_visible_opportunity(opportunity_id, user.id, db)
    if opp is None:
        return None
    profile = await get_active_profile(user, db)
    assessment = await db.scalar(
        select(JobAssessment)
        .where(JobAssessment.opportunity_id == opp.id, JobAssessment.profile_id == profile.id)
        .order_by(JobAssessment.last_seen_at.desc())
        .limit(1)
    )
    return opp, assessment
