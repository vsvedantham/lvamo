from typing import Optional

import sqlalchemy as sa
from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.prosho.models.enums import ProshoUserRole


class ProshoUser(Base, UUIDPrimaryKey, TimestampMixin):
    """A ProSho account. Identity comes from GitHub OAuth (beta plan §8), so
    `github_id` — GitHub's stable numeric user id, not the renameable login —
    is the dedup key. No password column: ProSho has no password sign-in."""

    __tablename__ = "users"
    __table_args__ = {"schema": "prosho"}

    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    github_login: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    # GitHub only returns an email if the user has a verified one we can read.
    email: Mapped[Optional[str]] = mapped_column(String(255))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    role: Mapped[ProshoUserRole] = mapped_column(
        sa.Enum(
            ProshoUserRole,
            name="user_role_enum",
            schema="prosho",
            create_type=False,
        ),
        nullable=False,
        default=ProshoUserRole.student,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa.true()
    )
