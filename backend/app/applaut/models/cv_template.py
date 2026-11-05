from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class CvTemplate(Base, UUIDPrimaryKey):
    """A user's own .docx CV made into a template (APPLAUT_AI_V2_PLAN.md §5):
    only the headline, skills items, bullets and technologies lines change per
    job; everything else stays as the user's file has it.

    status: reading (queued for the model to label its lines) → ready (built;
    the user compares the round trip) or failed → active (the user switched it
    on; at most one per user) → retired (replaced or switched off). discarded:
    the user dropped it before switching it on."""

    __tablename__ = "cv_templates"
    __table_args__ = {"schema": "applaut"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="cv")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reading")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_key: Mapped[str] = mapped_column(String(500), nullable=False)        # the upload (R2)
    template_key: Mapped[Optional[str]] = mapped_column(String(500))           # the built template (R2)
    original_pdf_key: Mapped[Optional[str]] = mapped_column(String(500))       # the upload as PDF
    rebuilt_pdf_key: Mapped[Optional[str]] = mapped_column(String(500))        # the template, upload's text
    pages: Mapped[Optional[int]] = mapped_column(Integer)                      # the upload's page count
    labels: Mapped[Optional[list]] = mapped_column(JSONB)                      # one per line, after code's fixes
    slots: Mapped[Optional[dict]] = mapped_column(JSONB)                       # own_template.Slots.to_json()
    # {"differences": [...], "fonts": [{font, shown_as}], "roles": [{heading, entry}], "rows": [{label, row}],
    #  "headline": bool, "notes": [...]}
    report: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # switched on, off or dropped
