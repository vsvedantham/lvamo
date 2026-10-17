from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, SmallInteger, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.applaut.models.enums import EmploymentTypeEnum, JobEngineEnum, RemotePreferenceEnum


class Profile(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "profiles"
    __table_args__ = {"schema": "applaut"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("applaut.users.id", ondelete="CASCADE"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    total_experience_years: Mapped[Optional[int]] = mapped_column(SmallInteger)

    target_roles: Mapped[list] = mapped_column(ARRAY(String), nullable=False, default=list)
    target_countries: Mapped[list] = mapped_column(ARRAY(String), nullable=False, default=list)
    skills: Mapped[list] = mapped_column(ARRAY(String), nullable=False, default=list)
    languages: Mapped[list] = mapped_column(ARRAY(String), nullable=False, default=list)

    remote_preference: Mapped[str] = mapped_column(
        sa.Enum(
            RemotePreferenceEnum,
            name="remote_preference_enum",
            schema="applaut",
            create_type=False,
        ),
        nullable=False,
        default=RemotePreferenceEnum.any,
    )
    employment_types: Mapped[list] = mapped_column(ARRAY(String), nullable=False, default=list)

    education: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    certifications: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)

    # Automation schedule
    discovery_frequency_hours: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=24,
        # CHECK (discovery_frequency_hours IN (6, 12, 24)) enforced in migration
    )
    discovery_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    good_threshold: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=85)
    last_discovery_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_scored_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    job_engine: Mapped[str] = mapped_column(
        sa.Enum(JobEngineEnum, name="job_engine_enum", schema="applaut", create_type=False),
        nullable=False,
        default=JobEngineEnum.basic,
    )
    job_engine_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped[User] = relationship(back_populates="profiles")
    resumes: Mapped[list[Resume]] = relationship(back_populates="profile")
    scores: Mapped[list[Score]] = relationship(back_populates="profile")
    applications: Mapped[list[Application]] = relationship(back_populates="profile")


from app.applaut.models.user import User  # noqa: E402
from app.applaut.models.resume import Resume  # noqa: E402
from app.applaut.models.score import Score  # noqa: E402
from app.applaut.models.application import Application  # noqa: E402
