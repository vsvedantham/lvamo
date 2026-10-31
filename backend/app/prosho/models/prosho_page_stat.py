import uuid
from datetime import date

import sqlalchemy as sa
from sqlalchemy import Date, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.prosho.models.enums import PageEvent


class ProshoPageStatDaily(Base):
    """Aggregate page counts per project, day, event and referring domain
    (BETA_PLAN §11: no IPs, no cookies, nothing per visitor)."""

    __tablename__ = "page_stats_daily"
    __table_args__ = {"schema": "prosho"}

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("prosho.projects.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    event: Mapped[PageEvent] = mapped_column(
        sa.Enum(PageEvent, name="page_event_enum", schema="prosho", create_type=False), primary_key=True
    )
    # "" for direct visits / no referrer.
    referrer_domain: Mapped[str] = mapped_column(String(100), primary_key=True, default="", server_default="")
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
