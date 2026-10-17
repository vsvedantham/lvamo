from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKey
from app.applaut.models.enums import DocumentTypeEnum, JobEngineEnum


class GeneratedDocument(Base, UUIDPrimaryKey):
    __tablename__ = "generated_documents"
    __table_args__ = {"schema": "applaut"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.users.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.profiles.id", ondelete="CASCADE")
    )
    application_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.applications.id", ondelete="SET NULL")
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("applaut.opportunities.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_resume_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.resumes.id", ondelete="SET NULL")
    )

    document_type: Mapped[str] = mapped_column(
        sa.Enum(
            DocumentTypeEnum,
            name="document_type_enum",
            schema="applaut",
            create_type=False,
        ),
        nullable=False,
    )
    generation_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="template")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    file_name: Mapped[Optional[str]] = mapped_column(String(500))
    r2_key: Mapped[Optional[str]] = mapped_column(String(1000))
    ai_model: Mapped[Optional[str]] = mapped_column(String(200))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    engine: Mapped[str] = mapped_column(
        sa.Enum(JobEngineEnum, name="job_engine_enum", schema="applaut", create_type=False),
        nullable=False,
        default=JobEngineEnum.basic,
    )
    # text/markdown for Applaut Basic's documents; application/pdf (stored in
    # R2 at r2_key) for AI engines', whose `content` holds a text version.
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, default="text/markdown")
    content_sha256: Mapped[Optional[str]] = mapped_column(sa.CHAR(64))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    application: Mapped[Optional[Application]] = relationship(
        back_populates="generated_documents"
    )
    opportunity: Mapped[Opportunity] = relationship(back_populates="generated_documents")
    source_resume: Mapped[Optional[Resume]] = relationship(
        back_populates="generated_documents"
    )


from app.applaut.models.application import Application  # noqa: E402
from app.applaut.models.opportunity import Opportunity  # noqa: E402
from app.applaut.models.resume import Resume  # noqa: E402
