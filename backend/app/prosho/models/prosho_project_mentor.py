import uuid
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class ProshoProjectMentor(Base, UUIDPrimaryKey, TimestampMixin):
    """An LVAMO mentor assigned to a project by an admin (BETA_PLAN §5). The
    mentor can see the project even while it's private, leave feedback and
    review milestones. The public page never names them."""

    __tablename__ = "project_mentors"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "mentor_id", name="uq_prosho_project_mentors_pair"),
        sa.Index("ix_prosho_project_mentors_mentor_id", "mentor_id"),
        {"schema": "prosho"},
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("prosho.projects.id", ondelete="CASCADE"), nullable=False
    )
    mentor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("prosho.users.id", ondelete="CASCADE"), nullable=False
    )
    assigned_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("prosho.users.id", ondelete="SET NULL")
    )
