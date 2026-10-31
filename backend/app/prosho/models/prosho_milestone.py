import uuid
from datetime import date, datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Date, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class ProshoMilestone(Base, UUIDPrimaryKey, TimestampMixin):
    """A step the student plans ("Data pipeline for 5 countries", due 15 Nov).
    The student completes it; a mentor can then mark it reviewed. Shown on
    the public page without any feedback."""

    __tablename__ = "milestones"
    __table_args__ = (
        sa.CheckConstraint("reviewed_at IS NULL OR completed_at IS NOT NULL",
                           name="prosho_milestones_review_needs_completion"),
        sa.Index("ix_prosho_milestones_project_id", "project_id"),
        {"schema": "prosho"},
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("prosho.projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    due_on: Mapped[Optional[date]] = mapped_column(Date)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("prosho.users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
