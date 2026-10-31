"""Milestones and mentor feedback (BETA_PLAN §5, Phase 3)."""
import uuid
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Person(BaseModel):
    id: uuid.UUID
    github_login: str
    name: Optional[str]
    avatar_url: Optional[str]

    model_config = {"from_attributes": True}


def _strip(v: Optional[str]) -> Optional[str]:
    return v.strip() if isinstance(v, str) else v


class MilestoneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_on: Optional[date] = None

    _title = field_validator("title")(_strip)


class MilestoneUpdate(BaseModel):
    """Owner: title, due_on, completed. Mentor: reviewed. Only fields
    actually sent are applied."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    due_on: Optional[date] = None
    completed: Optional[bool] = None
    reviewed: Optional[bool] = None

    _title = field_validator("title")(_strip)


class MilestoneResponse(BaseModel):
    id: uuid.UUID
    title: str
    due_on: Optional[date]
    completed_at: Optional[datetime]
    reviewed_at: Optional[datetime]
    reviewed_by: Optional[Person] = None
    position: int
    created_at: datetime


class FeedbackCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    # A reply to a thread; replies can't point at a milestone or claim.
    parent_id: Optional[uuid.UUID] = None
    milestone_id: Optional[uuid.UUID] = None
    claim_id: Optional[uuid.UUID] = None

    @field_validator("body")
    @classmethod
    def _body(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("write something first")
        return v


class FeedbackUpdate(BaseModel):
    resolved: bool


class FeedbackMessage(BaseModel):
    id: uuid.UUID
    author: Optional[Person]
    # Relative to this project — so the UI can say "Mentor" or "Student".
    author_role: Optional[Literal["owner", "mentor"]]
    body: str
    created_at: datetime


class FeedbackThread(FeedbackMessage):
    milestone_id: Optional[uuid.UUID]
    milestone_title: Optional[str]
    claim_id: Optional[uuid.UUID]
    claim_text: Optional[str]
    resolved_at: Optional[datetime]
    replies: list[FeedbackMessage]
