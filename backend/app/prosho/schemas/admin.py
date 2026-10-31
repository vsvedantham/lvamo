import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from app.prosho.models.enums import ProshoUserRole, Visibility
from app.prosho.schemas.team import Person


class AdminUser(BaseModel):
    id: uuid.UUID
    github_login: str
    name: Optional[str]
    avatar_url: Optional[str]
    role: ProshoUserRole
    is_active: bool
    created_at: datetime
    projects_owned: int


class AdminUserUpdate(BaseModel):
    role: Optional[ProshoUserRole] = None
    is_active: Optional[bool] = None


class AdminProject(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    visibility: Visibility
    is_active: bool
    repo_full_name: Optional[str]
    owner: Person
    mentors: list[Person]
    created_at: datetime


class AdminProjectUpdate(BaseModel):
    is_active: bool


class MentorAssign(BaseModel):
    mentor_id: uuid.UUID


class AuditEntry(BaseModel):
    id: uuid.UUID
    actor_login: Optional[str]
    action: str
    entity: str
    entity_id: Optional[uuid.UUID]
    before: Optional[dict[str, Any]]
    after: Optional[dict[str, Any]]
    created_at: datetime
