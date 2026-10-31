import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class ProshoRepoEvent(Base, UUIDPrimaryKey):
    """A commit on the connected repo's default branch — the work timeline.
    Read from GitHub on every manifest sync; one row per (project, commit).
    `message` is the first line only."""

    __tablename__ = "repo_events"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "commit_sha", name="uq_prosho_repo_events_project_commit"),
        sa.Index("ix_prosho_repo_events_project_time", "project_id", sa.text("committed_at DESC")),
        {"schema": "prosho"},
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("prosho.projects.id", ondelete="CASCADE"), nullable=False
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(String(300), nullable=False)
    author_login: Mapped[Optional[str]] = mapped_column(String(100))
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
