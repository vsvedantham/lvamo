import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.prosho.models.enums import ClaimManualStatus, ClaimTargetOp


class ProshoClaim(Base, UUIDPrimaryKey, TimestampMixin):
    """A promise the project makes ("X, to standard Y"), from prosho.yaml.
    Upserted by (project_id, key) on each sync; archived when dropped."""

    __tablename__ = "claims"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "key", name="uq_prosho_claims_project_key"),
        sa.CheckConstraint(
            "(metric_key IS NULL) = (target_op IS NULL) AND (target_op IS NULL) = (target_value IS NULL)",
            name="prosho_claims_metric_target",
        ),
        sa.CheckConstraint(
            "COALESCE(target_op = 'between', FALSE) = (target_value_hi IS NOT NULL)",
            name="prosho_claims_between_hi",
        ),
        {"schema": "prosho"},
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("prosho.projects.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    text: Mapped[str] = mapped_column(String(300), nullable=False)
    metric_key: Mapped[Optional[str]] = mapped_column(String(100))
    target_op: Mapped[Optional[ClaimTargetOp]] = mapped_column(
        sa.Enum(ClaimTargetOp, name="claim_target_op_enum", schema="prosho", create_type=False)
    )
    target_value: Mapped[Optional[float]] = mapped_column(Float)
    target_value_hi: Mapped[Optional[float]] = mapped_column(Float)
    manual_status: Mapped[ClaimManualStatus] = mapped_column(
        sa.Enum(ClaimManualStatus, name="claim_manual_status_enum", schema="prosho", create_type=False),
        nullable=False, default=ClaimManualStatus.not_started,
        server_default=ClaimManualStatus.not_started.value,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
