from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class MasterProfile(Base, UUIDPrimaryKey, TimestampMixin):
    """Everything Applaut AI's documents may say about a user, in the Claude
    routine's master_profile.yaml shape (validated by
    documents/profile_schema.py). One per user; `version` goes up on each save."""

    __tablename__ = "master_profiles"
    __table_args__ = {"schema": "applaut"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")  # manual | yaml
