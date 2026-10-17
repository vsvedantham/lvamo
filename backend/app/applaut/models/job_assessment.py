from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.applaut.models.enums import JobEngineEnum


class JobAssessment(Base, UUIDPrimaryKey, TimestampMixin):
    """An AI engine's verdict on a job for one profile: match %, which
    must-have skills matched and which are missing, and anything to check.
    Separate from `scores`, which rule-based scoring rewrites on every run."""

    __tablename__ = "job_assessments"
    __table_args__ = (
        sa.UniqueConstraint(
            "profile_id", "opportunity_id", "engine",
            name="uq_applaut_job_assessments_profile_opportunity_engine",
        ),
        sa.Index("ix_applaut_job_assessments_opportunity_id", "opportunity_id"),
        {"schema": "applaut"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.users.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.profiles.id", ondelete="CASCADE"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.opportunities.id", ondelete="CASCADE"), nullable=False
    )
    engine: Mapped[str] = mapped_column(
        sa.Enum(JobEngineEnum, name="job_engine_enum", schema="applaut", create_type=False),
        nullable=False,
    )
    match_score: Mapped[Optional[int]] = mapped_column(SmallInteger)
    matched_skills: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, default=list)
    missing_skills: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, default=list)
    german_required: Mapped[Optional[str]] = mapped_column(String(50))
    seniority: Mapped[Optional[str]] = mapped_column(String(50))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    flags: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, default=list)
    model: Mapped[Optional[str]] = mapped_column(String(100))
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    times_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
