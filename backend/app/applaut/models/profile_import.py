from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class ProfileImport(Base, UUIDPrimaryKey):
    """A master profile drafted from the user's own CV (documents/profile_import.py).
    Only the CV's text lines are kept, never the file, and only until the user
    closes the import (saved the profile or discarded the draft).

    status: reading (queued for the model) → ready (`draft` + `notes`) or failed.
    closed_at set: done with; lines and draft are cleared."""

    __tablename__ = "profile_imports"
    __table_args__ = {"schema": "applaut"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reading")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    lines: Mapped[Optional[list]] = mapped_column(JSONB)          # the CV's non-empty lines
    draft: Mapped[Optional[dict]] = mapped_column(JSONB)          # the drafted profile, gaps and all
    notes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # left out / still to fill
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
