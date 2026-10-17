from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class EngineTask(Base, UUIDPrimaryKey, TimestampMixin):
    """One scheduled unit of engine work (e.g. a Basic discovery run for a
    profile). The schedule lives here, not in each worker's memory: the
    dispatcher in discovery/scheduler.py claims due rows with
    FOR UPDATE SKIP LOCKED, so every worker sees the same schedule and no
    task runs twice."""

    __tablename__ = "engine_tasks"
    __table_args__ = (
        sa.Index("ix_applaut_engine_tasks_due", "due_at", postgresql_where=sa.text("status = 'pending'")),
        sa.Index("ix_applaut_engine_tasks_profile_id", "profile_id"),
        sa.Index(
            "uq_applaut_engine_tasks_open_kind_profile", "kind", "profile_id",
            unique=True, postgresql_where=sa.text("status IN ('pending', 'running')"),
        ),
        {"schema": "applaut"},
    )

    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.users.id", ondelete="CASCADE")
    )
    profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.profiles.id", ondelete="CASCADE")
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
