from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import BigInteger, Date, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIQueueItem(Base):
    """One unit of model work for Applaut AI. Served first in, first out
    (`ORDER BY seq`) by the ai-worker's lanes, one per model host; a retry is
    given a new `seq`, so it goes to the back of the queue."""

    __tablename__ = "ai_queue"
    __table_args__ = (
        sa.Index("ix_applaut_ai_queue_pending", "seq", postgresql_where=sa.text("status = 'pending'")),
        {"schema": "applaut"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False,
                                     server_default=sa.text("nextval('applaut.ai_queue_seq')"))
    kind: Mapped[str] = mapped_column(String(30), nullable=False)  # score_job | write_docs | draft_bullets | build_template
    night_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.night_runs.id", ondelete="SET NULL")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.users.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.profiles.id", ondelete="CASCADE"), nullable=False
    )
    # The job (score_job, write_docs), the notes (draft_bullets) or the upload (build_template) the item is for.
    assessment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.job_assessments.id", ondelete="CASCADE")
    )
    bullet_draft_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.bullet_drafts.id", ondelete="CASCADE")
    )
    cv_template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.cv_templates.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    host: Mapped[Optional[str]] = mapped_column(String(100))  # the model host that served it
    model: Mapped[Optional[str]] = mapped_column(String(100))
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)


class NightRun(Base):
    """One night's Applaut AI run: what each stage did, for the morning card."""

    __tablename__ = "night_runs"
    __table_args__ = {"schema": "applaut"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    discovery_done_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_queued: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # per-user counts
