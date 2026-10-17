"""Engine 3: the user's own Claude routine (docs/applaut/JOB_ENGINES_DESIGN.md §6).

Applaut reads the routine's output from the user's Neon database and R2
bucket with read-only credentials and copies it into its own tables."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class RoutineConnection(Base, UUIDPrimaryKey, TimestampMixin):
    """Where a user's routine writes, and when it runs. The *_enc columns are
    Fernet tokens (core/credentials.py) and are decrypted only to connect;
    never return them, or their plaintext, from the API."""

    __tablename__ = "routine_connections"
    __table_args__ = {"schema": "applaut"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    neon_url_enc: Mapped[str] = mapped_column(Text, nullable=False)
    neon_host: Mapped[str] = mapped_column(String(255), nullable=False)
    r2_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    r2_bucket: Mapped[str] = mapped_column(String(63), nullable=False)
    r2_prefix: Mapped[str] = mapped_column(String(200), nullable=False, default="jobautomationdocs")
    r2_access_key_id_enc: Mapped[str] = mapped_column(Text, nullable=False)
    r2_access_key_hint: Mapped[str] = mapped_column(String(8), nullable=False)
    r2_secret_enc: Mapped[str] = mapped_column(Text, nullable=False)
    routine_url: Mapped[Optional[str]] = mapped_column(String(2000))
    schedule_cron: Mapped[str] = mapped_column(String(100), nullable=False, default="7 6,18 * * *")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    contract_version: Mapped[Optional[int]] = mapped_column(SmallInteger)
    # setup | active | error (last check failed, still checking) | paused (stopped after repeated failures)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="setup")
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_check_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_manual_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class RoutineRun(Base, UUIDPrimaryKey, TimestampMixin):
    """A routine run as Applaut knows it: a copy of its run_tracker row, or a
    scheduled run that never started (run_id NULL, outcome `missed`)."""

    __tablename__ = "routine_runs"
    __table_args__ = (
        sa.Index("uq_applaut_routine_runs_user_run_id", "user_id", "run_id",
                 unique=True, postgresql_where=sa.text("run_id IS NOT NULL")),
        sa.Index("uq_applaut_routine_runs_user_missed", "user_id", "expected_at",
                 unique=True, postgresql_where=sa.text("run_id IS NULL")),
        sa.Index("ix_applaut_routine_runs_user_started", "user_id", sa.text("started_at DESC")),
        {"schema": "applaut"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.users.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[Optional[str]] = mapped_column(String(100))
    # The scheduled time this run belongs to, when Applaut matched one.
    expected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Applaut's reading of the run: running | succeeded | problems | failed | stopped | missed
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    contract_version: Mapped[Optional[int]] = mapped_column(SmallInteger)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # The routine's own fields, copied as written (untrusted text: show as plain text).
    status: Mapped[Optional[str]] = mapped_column(String(20))
    current_step: Mapped[Optional[str]] = mapped_column(String(50))
    error: Mapped[Optional[str]] = mapped_column(Text)
    searches_run: Mapped[Optional[int]] = mapped_column(Integer)
    search_budget: Mapped[Optional[int]] = mapped_column(Integer)
    postings_found: Mapped[Optional[int]] = mapped_column(Integer)
    postings_assessed: Mapped[Optional[int]] = mapped_column(Integer)
    jobs_eligible: Mapped[Optional[int]] = mapped_column(Integer)
    jobs_new: Mapped[Optional[int]] = mapped_column(Integer)
    jobs_updated: Mapped[Optional[int]] = mapped_column(Integer)
    jobs_rejected: Mapped[Optional[int]] = mapped_column(Integer)
    docs_done: Mapped[Optional[int]] = mapped_column(Integer)
    docs_failed: Mapped[Optional[int]] = mapped_column(Integer)
    sources_failed: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Set once the user has been told about a bad outcome, so it is told once.
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class RoutineSync(Base, UUIDPrimaryKey):
    __tablename__ = "routine_syncs"
    __table_args__ = (
        sa.Index("ix_applaut_routine_syncs_user_started", "user_id", sa.text("started_at DESC")),
        {"schema": "applaut"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.users.id", ondelete="CASCADE"), nullable=False
    )
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)  # scheduled | manual | initial
    run_id: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rows_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    docs_copied: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    docs_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Newest last_seen_at read from the routine's jobs table in this sync.
    watermark: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    problems: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, default=list)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


class RoutineJob(Base, UUIDPrimaryKey):
    """One job uid from the routine's database and the opportunity it became."""

    __tablename__ = "routine_jobs"
    __table_args__ = (
        sa.UniqueConstraint("user_id", "uid", name="uq_applaut_routine_jobs_user_uid"),
        sa.Index("ix_applaut_routine_jobs_opportunity_id", "opportunity_id"),
        {"schema": "applaut"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.users.id", ondelete="CASCADE"), nullable=False
    )
    uid: Mapped[str] = mapped_column(String(200), nullable=False)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.opportunities.id", ondelete="CASCADE"), nullable=False
    )
    # True when the job is a posting Applaut Basic already had (same apply URL).
    linked_to_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    docs_status: Mapped[Optional[str]] = mapped_column(String(20))
    docs_error: Mapped[Optional[str]] = mapped_column(Text)
    cv_etag: Mapped[Optional[str]] = mapped_column(String(200))
    cover_letter_etag: Mapped[Optional[str]] = mapped_column(String(200))
    # Set when the uid is no longer in the routine's database (the job is kept).
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    first_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
