import uuid
from datetime import datetime
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey
from app.prosho.models.enums import EvidenceKind, EvidenceSource


class ProshoEvidence(Base, UUIDPrimaryKey):
    """One piece of evidence (BETA_PLAN §2: "anything can attach a piece of
    evidence to a project, optionally against a claim"). Append-only — never
    updated or deleted except with its project."""

    __tablename__ = "evidence"
    __table_args__ = (
        sa.Index("ix_prosho_evidence_project_key_time", "project_id", "key", sa.text("recorded_at DESC")),
        sa.Index("uq_prosho_evidence_project_key_commit", "project_id", "key", "commit_sha", unique=True,
                 postgresql_where=sa.text("commit_sha IS NOT NULL")),
        {"schema": "prosho"},
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("prosho.projects.id", ondelete="CASCADE"), nullable=False
    )
    claim_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("prosho.claims.id", ondelete="SET NULL")
    )
    module: Mapped[str] = mapped_column(String(30), nullable=False)
    kind: Mapped[EvidenceKind] = mapped_column(
        sa.Enum(EvidenceKind, name="evidence_kind_enum", schema="prosho", create_type=False), nullable=False
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value_num: Mapped[Optional[float]] = mapped_column(Float)
    value_text: Mapped[Optional[str]] = mapped_column(String(500))
    unit: Mapped[Optional[str]] = mapped_column(String(30))
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    r2_key: Mapped[Optional[str]] = mapped_column(String(500))
    commit_sha: Mapped[Optional[str]] = mapped_column(String(40))
    source: Mapped[EvidenceSource] = mapped_column(
        sa.Enum(EvidenceSource, name="evidence_source_enum", schema="prosho", create_type=False), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
