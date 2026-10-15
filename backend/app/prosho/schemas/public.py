from datetime import datetime
from typing import Literal, Optional

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
    updated_at: datetime
    # True when the owner is looking at their own not-yet-shared page.
    preview: bool
