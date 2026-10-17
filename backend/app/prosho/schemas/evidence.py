import json
import math
import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.prosho.models.enums import EvidenceKind, EvidenceSource

KEY_PATTERN = r"^[a-z0-9][a-z0-9_.-]{0,99}$"
MAX_ITEMS = 50
MAX_BODY_BYTES = 64 * 1024
MAX_PAYLOAD_BYTES = 4 * 1024

CHECK_VALUES = {"pass", "fail", "warn"}
RUN_VALUES = {"success", "failure", "cancelled"}


class IngestItem(BaseModel):
    """One item of POST /ingest/evidence. Validated on its own, so a bad item
    is rejected without failing the rest of the batch."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=KEY_PATTERN)
    kind: Literal["metric", "check", "run"]
    value_num: Optional[float] = None
    value_text: Optional[str] = Field(default=None, max_length=500)
    unit: Optional[str] = Field(default=None, max_length=30)
    claim: Optional[str] = Field(default=None, max_length=60)
    payload: Optional[dict[str, Any]] = None

    @field_validator("value_num")
    @classmethod
    def _finite(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not math.isfinite(v):
            raise ValueError("value_num must be a finite number")
        return v

    @model_validator(mode="after")
    def _by_kind(self) -> "IngestItem":
        if self.kind == "metric":
            if self.value_num is None:
                raise ValueError("a metric needs value_num")
        elif self.kind == "check":
            if self.value_text not in CHECK_VALUES:
                raise ValueError("a check needs value_text: pass, fail or warn")
        elif self.kind == "run":
            if self.value_text not in RUN_VALUES:
                raise ValueError("a run needs value_text: success, failure or cancelled")
        if self.payload is not None:
            if len(json.dumps(self.payload)) > MAX_PAYLOAD_BYTES:
                raise ValueError(f"payload is larger than {MAX_PAYLOAD_BYTES // 1024} KB")
        return self


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commit_sha: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    items: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_ITEMS)


class IngestItemResult(BaseModel):
    index: int
    key: Optional[str]
    result: Literal["accepted", "duplicate", "rejected"]
    reason: Optional[str] = None


class IngestResponse(BaseModel):
    accepted: int
    duplicate: int
    rejected: int
    items: list[IngestItemResult]


class EvidenceResponse(BaseModel):
    id: uuid.UUID
    module: str
    kind: EvidenceKind
    key: str
    value_num: Optional[float]
    value_text: Optional[str]
    unit: Optional[str]
    payload: Optional[dict[str, Any]]
    commit_sha: Optional[str]
    source: EvidenceSource
    recorded_at: datetime

    model_config = {"from_attributes": True}


class TokenCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)


class TokenResponse(BaseModel):
    id: uuid.UUID
    label: str
    token_prefix: str
    last_used_at: Optional[datetime]
    revoked_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenCreated(TokenResponse):
    # Shown exactly once; only its SHA-256 is stored.
    token: str
