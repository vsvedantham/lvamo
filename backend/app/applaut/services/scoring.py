import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.models.opportunity import Opportunity
from app.applaut.models.profile import Profile
from app.applaut.models.resume import Resume
from app.applaut.models.score import Score
from app.applaut.models.user import User
from app.applaut.scoring.rule_based import score_opportunity
from app.applaut.services.profile import get_active_profile
from app.applaut.services.visibility import get_visible_opportunity, visible_to

logger = logging.getLogger(__name__)

USER_DECISIONS = {"keep", "dismiss", "keep_with_keywords"}


async def _get_resume(user: User, db: AsyncSession) -> Resume | None:
    return await db.scalar(
        select(Resume).where(Resume.user_id == user.id, Resume.is_master == True)
    )


async def _get_all_active_opportunities(user: User, db: AsyncSession) -> list[Opportunity]:
    result = await db.scalars(select(Opportunity).where(Opportunity.is_active == True, visible_to(user.id)))
    return list(result)


async def _get_unscored_opportunities(user: User, profile: Profile, db: AsyncSession) -> list[Opportunity]:
    scored_ids = set(await db.scalars(
        select(Score.opportunity_id).where(Score.profile_id == profile.id)
    ))
    opps = await db.scalars(select(Opportunity).where(Opportunity.is_active == True, visible_to(user.id)))
    return [o for o in opps if o.id not in scored_ids]


async def _get_existing_scores(profile: Profile, db: AsyncSession) -> dict:
    rows = await db.scalars(select(Score).where(Score.profile_id == profile.id))
    return {s.opportunity_id: s for s in rows}


async def run_scoring(
    user: User,
    db: AsyncSession,
    mode: str = "rule_based",
) -> dict:
    if mode not in ("rule_based", "ai"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mode must be rule_based or ai")

    profile = await get_active_profile(user, db)
    resume = await _get_resume(user, db)
    good_threshold = profile.good_threshold
    near_miss_threshold = good_threshold - 15

    if mode == "rule_based":
        # Re-score every active opportunity (upsert) — fast and free
        opportunities = await _get_all_active_opportunities(user, db)
        existing_scores = await _get_existing_scores(profile, db)
    else:
        # AI mode: only score new opportunities to control API cost
        opportunities = await _get_unscored_opportunities(user, profile, db)
        existing_scores = {}

    if not opportunities:
        return {"scored": 0, "good_matches": 0, "near_misses": 0, "below_threshold": 0, "mode": mode}

    good = near_miss = below = 0

    for opp in opportunities:
        try:
            if mode == "ai":
                from app.applaut.scoring.ai_scorer import score_opportunity_ai
                result = await score_opportunity_ai(opp, profile, resume)
                ai_model = "gpt-4o-mini"
            else:
                result = score_opportunity(opp, profile, resume)
                ai_model = None

            is_good = result.total >= good_threshold
            is_near = near_miss_threshold <= result.total < good_threshold
            near_miss_kw = result.near_miss_keywords if result.near_miss_keywords else None

            existing = existing_scores.get(opp.id)
            if existing:
                # Update in-place — preserve user_decision unless category changed
                existing.total_score = result.total
                existing.skills_score = result.dimensions["skills"].score
                existing.experience_score = result.dimensions["experience"].score
                existing.location_score = result.dimensions["location"].score
                existing.employment_type_score = result.dimensions["employment_type"].score
                existing.explanation = result.to_explanation_dict()
                existing.near_miss_keywords = near_miss_kw
                existing.scoring_mode = mode
                if ai_model:
                    existing.ai_model = ai_model
                # Reset decision only when category changes
                if is_near and existing.user_decision is None:
                    existing.user_decision = "pending_review"
                elif not is_near and existing.user_decision == "pending_review":
                    existing.user_decision = None
            else:
                score = Score(
                    opportunity_id=opp.id,
                    profile_id=profile.id,
                    user_id=user.id,
                    total_score=result.total,
                    skills_score=result.dimensions["skills"].score,
                    experience_score=result.dimensions["experience"].score,
                    location_score=result.dimensions["location"].score,
                    employment_type_score=result.dimensions["employment_type"].score,
                    explanation=result.to_explanation_dict(),
                    ai_model=ai_model,
                    scoring_mode=mode,
                    near_miss_keywords=near_miss_kw,
                    user_decision="pending_review" if is_near else None,
                )
                db.add(score)

            if is_good:
                good += 1
            elif is_near:
                near_miss += 1
            else:
                below += 1

        except Exception as exc:
            logger.warning("Scoring failed for opportunity %s: %s", opp.id, exc)

    from app.applaut.services.audit import log_action
    await log_action(
        action="scoring.run",
        db=db,
        user_id=str(user.id),
        entity_type="profile",
        entity_id=str(profile.id),
        after_state={"scored": good + near_miss + below, "good_matches": good, "near_misses": near_miss, "mode": mode},
    )
    await db.commit()
    return {"scored": good + near_miss + below, "good_matches": good, "near_misses": near_miss, "below_threshold": below, "mode": mode}


async def list_scores(
    user: User,
    db: AsyncSession,
    filter_type: str = "good",
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Score], int]:
    profile = await get_active_profile(user, db)
    good_threshold = profile.good_threshold
    near_miss_threshold = good_threshold - 15

    query = select(Score).where(Score.user_id == user.id)

    if filter_type == "good":
        query = query.where(Score.total_score >= good_threshold)
    elif filter_type == "near_miss":
        query = query.where(
            Score.total_score >= near_miss_threshold,
            Score.total_score < good_threshold,
        )

    from sqlalchemy import func
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    items = await db.scalars(
        query.order_by(Score.total_score.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(items), total or 0


async def decide_near_miss(
    score_id: str,
    action: str,
    keywords_to_add: list[str],
    user: User,
    db: AsyncSession,
) -> Score:
    if action not in USER_DECISIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"action must be one of {USER_DECISIONS}")

    profile = await get_active_profile(user, db)
    score = await db.get(Score, score_id)
    if not score or score.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Score not found")
    if score.total_score >= profile.good_threshold:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only near-miss scores require a decision")

    score.user_decision = action

    if action == "keep_with_keywords" and keywords_to_add:
        existing_set = {s.lower() for s in (profile.skills or [])}
        new_skills = [kw for kw in keywords_to_add if kw.lower() not in existing_set]
        if new_skills:
            profile.skills = list(profile.skills or []) + new_skills

        resume = await _get_resume(user, db)
        opp = await get_visible_opportunity(score.opportunity_id, user.id, db)
        if opp:
            try:
                result = score_opportunity(opp, profile, resume)
                score.total_score = result.total
                score.skills_score = result.dimensions["skills"].score
                score.experience_score = result.dimensions["experience"].score
                score.location_score = result.dimensions["location"].score
                score.employment_type_score = result.dimensions["employment_type"].score
                score.explanation = result.to_explanation_dict()
                score.near_miss_keywords = result.near_miss_keywords if result.near_miss_keywords else None
                if result.total >= profile.good_threshold:
                    score.user_decision = None
            except Exception as exc:
                logger.warning("Re-scoring failed for score %s: %s", score_id, exc)

    # A dismissal is this user's decision: it hides the job from their list
    # (services/opportunity.py filters user_decision = "dismiss"). Deactivating
    # the row is only safe for a job this user owns; a shared job stays
    # active for everyone else.
    if action == "dismiss":
        opp = await get_visible_opportunity(score.opportunity_id, user.id, db)
        if opp and opp.owner_user_id == user.id:
            opp.is_active = False

    await db.commit()
    await db.refresh(score)
    return score
