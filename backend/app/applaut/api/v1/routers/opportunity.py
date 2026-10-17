from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.applaut.models.user import User
from app.applaut.schemas.opportunity import (
    AssessmentInfo,
    DiscoveryRunResponse,
    OpportunityDetailResponse,
    OpportunityListResponse,
    OpportunityScoreInfo,
    OpportunityWithScoreResponse,
)
from app.applaut.services.auth import get_current_user
from app.applaut.services.opportunity import get_opportunity_for_user, list_opportunities_with_scores, trigger_discovery

router = APIRouter()


@router.post("/discovery/run", response_model=DiscoveryRunResponse)
async def run_discovery(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await trigger_discovery(current_user, db)
    message = (
        f"Discovery complete. {result['new_jobs_found']} new job(s) found. "
        f"Scored {result['scored']} — {result['good_matches']} good match(es), "
        f"{result['near_misses']} near miss(es)."
    )
    return DiscoveryRunResponse(**result, message=message)


@router.get("/opportunities", response_model=OpportunityListResponse)
async def list_opps(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    country_code: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    match: Literal["all", "good", "near_miss", "below", "unscored"] = Query("all"),
    engine: Optional[Literal["basic", "applaut_ai", "own_routine"]] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows, total, good_threshold, near_miss_threshold = await list_opportunities_with_scores(
        current_user, db, page, page_size, country_code, source, match, engine
    )
    items = []
    for opp, score, assessment in rows:
        item = OpportunityWithScoreResponse.model_validate(opp)
        if score:
            item.score = OpportunityScoreInfo.model_validate(score)
        if assessment:
            item.assessment = AssessmentInfo.model_validate(assessment)
        items.append(item)
    return OpportunityListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        good_threshold=good_threshold,
        near_miss_threshold=near_miss_threshold,
    )


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityDetailResponse)
async def get_opp(
    opportunity_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    found = await get_opportunity_for_user(opportunity_id, current_user, db)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    opp, assessment = found
    detail = OpportunityDetailResponse.model_validate(opp)
    if assessment:
        detail.assessment = AssessmentInfo.model_validate(assessment)
    return detail
