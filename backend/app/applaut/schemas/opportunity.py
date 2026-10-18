import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, computed_field


class OpportunityResponse(BaseModel):
    id: uuid.UUID
    source: str
    title: str
    company_name: str
    location_raw: Optional[str]
    country_code: Optional[str]
    remote_option: Optional[str]
    employment_type: Optional[str]
    application_url: Optional[str]
    posted_at: Optional[datetime]
    is_active: bool
    created_at: datetime
    owner_user_id: Optional[uuid.UUID] = Field(default=None, exclude=True)

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def is_private(self) -> bool:
        """True for a job an AI engine brought in for this user only."""
        return self.owner_user_id is not None


class AssessmentInfo(BaseModel):
    """An AI engine's verdict on a job (JobAssessment)."""
    engine: str
    match_score: Optional[int]
    matched_skills: list[str]
    missing_skills: list[str]
    german_required: Optional[str]
    seniority: Optional[str]
    notes: Optional[str]
    flags: list[str]
    first_seen_at: datetime
    last_seen_at: datetime
    times_seen: int

    model_config = {"from_attributes": True}


class OpportunityDetailResponse(OpportunityResponse):
    description: Optional[str]
    requirements: Optional[str]
    salary_min: Optional[int]
    salary_max: Optional[int]
    salary_currency: Optional[str]
    assessment: Optional[AssessmentInfo] = None


class OpportunityScoreInfo(BaseModel):
    id: uuid.UUID
    total_score: int
    explanation: Any
    scoring_mode: str
    near_miss_keywords: Optional[Any]
    user_decision: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


TrackingState = Literal["open", "applied", "unavailable"]


class TrackingInfo(BaseModel):
    """Where the user is with a job: to review, applied, or unavailable
    (posting closed / can't apply). Backed by their Application row."""
    state: TrackingState
    application_id: Optional[uuid.UUID] = None
    status: Optional[str] = None
    applied_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RoutineJobInfo(BaseModel):
    """The job's place in the user's own routine output."""
    uid: str
    docs_ready: bool
    removed: bool


class OpportunityWithScoreResponse(OpportunityResponse):
    score: Optional[OpportunityScoreInfo] = None
    assessment: Optional[AssessmentInfo] = None
    tracking: TrackingInfo = TrackingInfo(state="open")
    routine: Optional[RoutineJobInfo] = None


class SetTrackingRequest(BaseModel):
    state: TrackingState
    # For state "unavailable": the posting closed, or the user can't apply.
    reason: Optional[Literal["closed", "cannot_apply"]] = None


class DiscoveryRunResponse(BaseModel):
    new_jobs_found: int
    scored: int
    good_matches: int
    near_misses: int
    message: str


class OpportunityListResponse(BaseModel):
    items: list[OpportunityWithScoreResponse]
    total: int
    page: int
    page_size: int
    good_threshold: int
    near_miss_threshold: int
    # Jobs per tracking state, for the tabs (same filters except the state).
    counts: dict[str, int] = {}
