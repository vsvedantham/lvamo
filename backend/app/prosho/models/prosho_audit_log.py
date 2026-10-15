import uuid
from datetime import datetime
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class ProshoAuditLog(Base, UUIDPrimaryKey):
    """Append-only record of every write to projects, visibility, claims and
    (later) tokens and mentors. `actor_id` is NULL for system writes such as
    a webhook-driven manifest sync."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        sa.Index("ix_prosho_audit_logs_entity", "entity", "entity_id", sa.text("created_at DESC")),
        {"schema": "prosho"},
    )

    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("prosho.users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    before: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    after: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
