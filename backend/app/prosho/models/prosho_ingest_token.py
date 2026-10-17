import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import CHAR, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class ProshoIngestToken(Base, UUIDPrimaryKey, TimestampMixin):
    """A per-project secret the student's CI uses to POST evidence. Only the
    SHA-256 is stored; `token_prefix` (e.g. "psho_Ab3x") lets the dashboard
    tell tokens apart without revealing them."""

    __tablename__ = "ingest_tokens"
    __table_args__ = (sa.Index("ix_prosho_ingest_tokens_project_id", "project_id"), {"schema": "prosho"})

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("prosho.projects.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("prosho.users.id", ondelete="SET NULL")
    )
