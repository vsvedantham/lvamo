import sqlalchemy as sa
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class PlatformSetting(Base, UUIDPrimaryKey, TimestampMixin):
    """LVAMO-wide settings that belong to no single vertical (e.g. which
    verticals the hub lists). Vertical-specific settings stay in their own
    schema — e.g. Applaut's `allow_new_registrations` lives in
    `applaut.application_settings`."""

    __tablename__ = "settings"
    __table_args__ = {"schema": "platform"}

    setting_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Only public settings are readable through the unauthenticated API.
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )
