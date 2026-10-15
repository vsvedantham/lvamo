import re
import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.prosho.models.enums import DemoKind, ProjectType, Visibility

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,58}[a-z0-9])$")
# Path segments under /prosho/ that pages or the app itself use (BETA_PLAN §6).
RESERVED_SLUGS = frozenset({
    "login", "dashboard", "projects", "admin", "gallery", "auth", "new",
    "api", "github", "settings", "help", "about",
})


def validate_slug(v: str) -> str:
    v = v.strip().lower()
    if not SLUG_RE.match(v):
        raise ValueError("3–60 characters: lowercase letters, numbers and hyphens, not starting or ending with a hyphen")
    if v in RESERVED_SLUGS:
        raise ValueError("this address is reserved — pick another")
    return v


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    slug: str
    project_type: ProjectType

    _slug = field_validator("slug")(validate_slug)


class ProjectUpdate(BaseModel):
    """Every field optional; only fields actually sent are applied."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    slug: Optional[str] = None
    university: Optional[str] = Field(default=None, max_length=200)
    programme: Optional[str] = Field(default=None, max_length=200)
    visibility: Optional[Visibility] = None
    # "My supervisor has agreed this can be public" (BETA_PLAN §11).
    supervisor_confirmed: Optional[bool] = None
    demo_kind: Optional[DemoKind] = None
    demo_url: Optional[HttpUrl] = None

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else validate_slug(v)

    @field_validator("university", "programme")
    @classmethod
    def _blank_to_none(cls, v: Optional[str]) -> Optional[str]:
        return (v.strip() or None) if isinstance(v, str) else v

    @field_validator("demo_url")
    @classmethod
    def _demo_url_length(cls, v: Optional[HttpUrl]) -> Optional[HttpUrl]:
        if v is not None and len(str(v)) > 500:
            raise ValueError("URL is too long (max 500 characters)")
        return v

    @model_validator(mode="after")
    def _demo_pair(self) -> "ProjectUpdate":
        sent = self.model_fields_set
        if ("demo_kind" in sent) != ("demo_url" in sent) or (
            "demo_kind" in sent and (self.demo_kind is None) != (self.demo_url is None)
        ):
            raise ValueError("demo_kind and demo_url are set (or cleared) together")
        return self


class ProjectResponse(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    summary: Optional[str]
    problem: Optional[str]
    project_type: ProjectType
    university: Optional[str]
    programme: Optional[str]
    visibility: Visibility
    supervisor_ok_at: Optional[datetime]
    repo_full_name: Optional[str]
    demo_kind: Optional[DemoKind]
    demo_url: Optional[str]
    manifest_sha: Optional[str]
    manifest_synced_at: Optional[datetime]
    manifest_checked_at: Optional[datetime]
    manifest_errors: Optional[list[dict[str, Any]]]
    published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    # True once prosho.yaml has synced: title/summary/problem/type/demo are
    # then read-only on ProSho (edit them in the repo instead).
    manifest_managed: bool
    # Connected, but the App lost access (uninstalled / repo removed from it).
    repo_access_lost: bool

    model_config = {"from_attributes": True}

    @classmethod
    def from_project(cls, p: Any) -> "ProjectResponse":
        computed = {
            "manifest_managed": p.manifest_synced_at is not None,
            "repo_access_lost": p.repo_id is not None and p.github_installation_id is None,
        }
        return cls.model_validate({**{k: getattr(p, k) for k in cls.model_fields if k not in computed}, **computed})
