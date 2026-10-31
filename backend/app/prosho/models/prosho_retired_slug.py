from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProshoRetiredSlug(Base):
    """The address of a deleted page that had been shared. Never reused, so a
    link on someone's CV can't start pointing at a stranger's project."""

    __tablename__ = "retired_slugs"
    __table_args__ = {"schema": "prosho"}

    slug: Mapped[str] = mapped_column(String(60), primary_key=True)
    retired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
