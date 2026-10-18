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
    RoutineJobInfo,
    SetTrackingRequest,
    TrackingInfo,
)
from app.applaut.services.auth import get_current_user
from app.applaut.services.application import set_tracking
from app.applaut.services.opportunity import (
    get_opportunity_for_user, list_opportunities_with_scores, tracking_state, trigger_discovery,
)

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
    state: Literal["all", "open", "applied", "unavailable"] = Query("all"),
    include_shared: Optional[bool] = Query(None, description="Applaut Basic's shared jobs; default: yes, except on your own routine"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows, total, good_threshold, near_miss_threshold, counts, shared_included = await list_opportunities_with_scores(
        current_user, db, page, page_size, country_code, source, match, engine, state, include_shared
    )
    items = []
    for opp, score, assessment, application, routine_job in rows:
        item = OpportunityWithScoreResponse.model_validate(opp)
        if score:
            item.score = OpportunityScoreInfo.model_validate(score)
        if assessment:
            item.assessment = AssessmentInfo.model_validate(assessment)
        item.tracking = _tracking(application)
        if routine_job:
            item.routine = RoutineJobInfo(uid=routine_job.uid, docs_ready=routine_job.docs_status == "done",
                                          removed=routine_job.removed_at is not None)
        items.append(item)
    return OpportunityListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        good_threshold=good_threshold,
        near_miss_threshold=near_miss_threshold,
        counts=counts,
        include_shared=shared_included,
    )


def _tracking(application) -> TrackingInfo:
    if application is None:
        return TrackingInfo(state="open")
    return TrackingInfo(
        state=tracking_state(application.status), application_id=application.id,
        status=getattr(application.status, "value", application.status), applied_at=application.applied_at, updated_at=application.updated_at,
    )


@router.put("/opportunities/{opportunity_id}/tracking", response_model=TrackingInfo)
async def set_opp_tracking(
    opportunity_id: str,
    payload: SetTrackingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark as applied, not available (posting closed / can't apply), or back to review."""
    app = await set_tracking(opportunity_id, payload.state, payload.reason, current_user, db)
    return _tracking(app)


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
