import uuid
from datetime import datetime
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy import BigInteger, Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.prosho.models.enums import DemoKind, ProjectType, Visibility


def _enum(cls, name: str) -> sa.Enum:
    return sa.Enum(cls, name=name, schema="prosho", create_type=False)


class ProshoProject(Base, UUIDPrimaryKey, TimestampMixin):
    """One student project = one page at lvamo.com/prosho/<slug>.

    Once a repo is connected, title/summary/problem/type/demo come from its
    prosho.yaml on every sync (the manifest owns the story, BETA_PLAN §7);
    visibility, university, programme and supervisor confirmation are only
    ever set on ProSho itself."""

    __tablename__ = "projects"
    __table_args__ = (
        sa.CheckConstraint(
            "visibility <> 'public' OR supervisor_ok_at IS NOT NULL",
            name="prosho_projects_public_needs_supervisor",
        ),
        sa.CheckConstraint("(demo_kind IS NULL) = (demo_url IS NULL)", name="prosho_projects_demo_pair"),
        sa.Index("ix_prosho_projects_owner_id", "owner_id"),
        sa.Index(
            "uq_prosho_projects_repo_id", "repo_id", unique=True,
            postgresql_where=sa.text("repo_id IS NOT NULL"),
        ),
        {"schema": "prosho"},
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("prosho.users.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(String(300))
    problem: Mapped[Optional[str]] = mapped_column(Text)
    project_type: Mapped[ProjectType] = mapped_column(_enum(ProjectType, "project_type_enum"), nullable=False)
    university: Mapped[Optional[str]] = mapped_column(String(200))
    programme: Mapped[Optional[str]] = mapped_column(String(200))
    visibility: Mapped[Visibility] = mapped_column(
        _enum(Visibility, "visibility_enum"), nullable=False,
        default=Visibility.private, server_default=Visibility.private.value,
    )
    supervisor_ok_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    repo_full_name: Mapped[Optional[str]] = mapped_column(String(200))
    repo_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    github_installation_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    demo_kind: Mapped[Optional[DemoKind]] = mapped_column(_enum(DemoKind, "demo_kind_enum"))
    demo_url: Mapped[Optional[str]] = mapped_column(String(500))
    manifest_sha: Mapped[Optional[str]] = mapped_column(String(40))
    manifest_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # List of {"line": int | None, "path": str, "message": str} from the last sync.
    manifest_errors: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=sa.true())
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
