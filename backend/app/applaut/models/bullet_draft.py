from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class BulletDraft(Base, UUIDPrimaryKey):
    """The bullet bank builder (APPLAUT_AI_V2_PLAN.md §4): the user's notes about
    one role or project of their master profile, and the CV bullets the writer
    drafted from them. Nothing here is in the profile until the user keeps it."""

    __tablename__ = "bullet_drafts"
    __table_args__ = {"schema": "applaut"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.users.id", ondelete="CASCADE"), nullable=False
    )
    entry_id: Mapped[str] = mapped_column(String(100), nullable=False)  # a master-profile experience/project id
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending | done | failed
    # [{"text", "confirm": [numbers not in the notes or role]}]: shown for Keep / Edit / Discard
    drafts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # [{"text", "reason"}]: drafts the checks left out, shown with why
    left_out: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    error: Mapped[Optional[str]] = mapped_column(Text)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # kept or discarded by the user
