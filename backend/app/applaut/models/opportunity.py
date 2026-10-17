from __future__ import annotations

from datetime import datetime
from typing import Optional

import uuid

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.applaut.models.enums import EmploymentTypeEnum, RemotePreferenceEnum


class Opportunity(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "opportunities"
    __table_args__ = (
        # Shared (Applaut Basic) and private (AI engine) jobs are unique
        # separately, so the same posting can exist once shared and once per user.
        sa.Index(
            "uq_applaut_opportunities_shared_source_external_id", "source", "external_id",
            unique=True, postgresql_where=sa.text("owner_user_id IS NULL"),
        ),
        sa.Index(
            "uq_applaut_opportunities_owned_source_external_id", "owner_user_id", "source", "external_id",
            unique=True, postgresql_where=sa.text("owner_user_id IS NOT NULL"),
        ),
        {"schema": "applaut"},
    )

    # NULL = found by Applaut Basic, visible to everyone; set = brought in by an
    # AI engine for this user only. Read through services/visibility.py.
    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.users.id", ondelete="CASCADE")
    )

    source: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company_name: Mapped[str] = mapped_column(String(500), nullable=False)
    location_raw: Mapped[Optional[str]] = mapped_column(String(500))
    country_code: Mapped[Optional[str]] = mapped_column(String(10))

    remote_option: Mapped[Optional[str]] = mapped_column(
        sa.Enum(
            RemotePreferenceEnum,
            name="remote_preference_enum",
            schema="applaut",
            create_type=False,
        )
    )
    employment_type: Mapped[Optional[str]] = mapped_column(
        sa.Enum(
            EmploymentTypeEnum,
            name="employment_type_enum",
            schema="applaut",
            create_type=False,
        )
    )

    description: Mapped[Optional[str]] = mapped_column(Text)
    requirements: Mapped[Optional[str]] = mapped_column(Text)
    salary_min: Mapped[Optional[int]] = mapped_column(Integer)
    salary_max: Mapped[Optional[int]] = mapped_column(Integer)
    salary_currency: Mapped[Optional[str]] = mapped_column(String(10))
    application_url: Mapped[Optional[str]] = mapped_column(String(2000))
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    scores: Mapped[list[Score]] = relationship(back_populates="opportunity")
    applications: Mapped[list[Application]] = relationship(back_populates="opportunity")
    generated_documents: Mapped[list[GeneratedDocument]] = relationship(
        back_populates="opportunity"
    )


from app.applaut.models.score import Score  # noqa: E402
from app.applaut.models.application import Application  # noqa: E402
from app.applaut.models.generated_document import GeneratedDocument  # noqa: E402
