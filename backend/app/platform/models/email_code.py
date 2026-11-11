from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class EmailCode(Base, UUIDPrimaryKey):
    """One-time codes emailed to prove someone owns an address, for any
    vertical (sign-up and password reset). Only a hash of the code is kept.

    A code is dead once it is consumed, expires, runs out of attempts, or a
    newer code is sent for the same (vertical, email, purpose)."""

    __tablename__ = "email_codes"
    __table_args__ = (
        CheckConstraint("purpose IN ('register', 'reset_password')", name="email_codes_purpose_check"),
        Index("ix_platform_email_codes_lookup", "vertical", "email", "purpose", "created_at"),
        {"schema": "platform"},
    )

    vertical: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)  # lowercased
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requester_ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
