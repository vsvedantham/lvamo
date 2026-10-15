import uuid
from typing import Optional

from pydantic import BaseModel

from app.prosho.models.enums import ClaimManualStatus, ClaimTargetOp


class RepoOption(BaseModel):
    id: int
    full_name: str
    private: bool


class AvailableRepos(BaseModel):
    installed: bool
    install_url: str
    manage_url: Optional[str]
    repos: list[RepoOption]


class ConnectRepo(BaseModel):
    repo_id: int


class ClaimResponse(BaseModel):
    id: uuid.UUID
    key: str
    text: str
    metric_key: Optional[str]
    target_op: Optional[ClaimTargetOp]
    target_value: Optional[float]
    target_value_hi: Optional[float]
    manual_status: ClaimManualStatus
    position: int

    model_config = {"from_attributes": True}


class ClaimStatusUpdate(BaseModel):
    manual_status: ClaimManualStatus
