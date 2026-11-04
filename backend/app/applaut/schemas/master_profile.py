import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class MasterProfileResponse(BaseModel):
    data: dict
    yaml: str
    version: int
    source: str
    updated_at: datetime


class MasterProfileSave(BaseModel):
    """Either the routine's master_profile.yaml as text, or the same data as JSON."""
    yaml: str | None = None
    data: dict | None = None

    @model_validator(mode="after")
    def _one(self):
        if (self.yaml is None) == (self.data is None):
            raise ValueError("send either yaml or data")
        return self


PreviewKind = Literal["cv", "cover_letter"]


class DraftRequest(BaseModel):
    notes: str = Field(min_length=20, max_length=4000)


class DraftedBullet(BaseModel):
    text: str
    confirm: list[str]  # numbers in neither the notes nor the role: check before keeping


class LeftOutBullet(BaseModel):
    text: str
    reason: str


class BulletDraftResponse(BaseModel):
    id: uuid.UUID
    entry_id: str
    notes: str
    status: Literal["pending", "done", "failed"]
    ahead: Optional[int] = None  # queue items before this one, while pending
    drafts: list[DraftedBullet]
    left_out: list[LeftOutBullet]
    error: Optional[str]
    created_at: datetime
    finished_at: Optional[datetime]


class AddFactsRequest(BaseModel):
    facts: list[str] = Field(min_length=1, max_length=10)
    draft_id: Optional[uuid.UUID] = None  # the drafts these came from; closed once saved
