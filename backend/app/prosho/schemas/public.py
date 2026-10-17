from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel

from app.prosho.models.enums import DemoKind, ProjectType, Visibility

# A measured claim's status comes from evidence (Phase 2); until then it's
# "awaiting_evidence". A self-reported claim shows the student's own status.
ClaimStatus = Literal["not_started", "in_progress", "met", "not_met", "awaiting_evidence"]


class PublicOwner(BaseModel):
    name: Optional[str]
    github_login: str
    avatar_url: Optional[str]


class PublicClaim(BaseModel):
    key: str
    text: str
    status: ClaimStatus
    self_reported: bool
    metric_key: Optional[str]
    target_op: Optional[str]
    target_value: Optional[float]
    target_value_hi: Optional[float]
    # The evidence that decided a measured claim's status.
    latest_value: Optional[float] = None
    latest_unit: Optional[str] = None
    latest_at: Optional[datetime] = None
    latest_commit: Optional[str] = None


class SourcePanelItem(BaseModel):
    name: str
    url: str
    licence: Optional[str]
    status: Literal["pass", "fail", "warn", "unchecked"]
    checked_at: Optional[datetime]
    detail: Optional[str]
    status_code: Optional[int]


class MetricPanelItem(BaseModel):
    key: str
    value: Optional[float]
    unit: Optional[str]
    recorded_at: datetime
    commit_sha: Optional[str]
    claim_text: Optional[str]
    target_op: Optional[str]
    target_value: Optional[float]
    target_value_hi: Optional[float]
    status: Optional[Literal["met", "not_met", "awaiting_evidence"]]


class RunPanelItem(BaseModel):
    key: str
    status: Optional[str]
    recorded_at: datetime
    commit_sha: Optional[str]
    details: dict[str, Any]


class DataModule(BaseModel):
    sources: list[SourcePanelItem]
    metrics: list[MetricPanelItem]
    runs: list[RunPanelItem]


class PublicProject(BaseModel):
    slug: str
    title: str
    summary: Optional[str]
    problem: Optional[str]
    project_type: ProjectType
    university: Optional[str]
    programme: Optional[str]
    visibility: Visibility
    demo_kind: Optional[DemoKind]
    demo_url: Optional[str]
    owner: PublicOwner
    claims: list[PublicClaim]
    # Present for data-science projects (BETA_PLAN §2 data module).
    data_module: Optional[DataModule] = None
    updated_at: datetime
    # True when the owner is looking at their own not-yet-shared page.
    preview: bool
