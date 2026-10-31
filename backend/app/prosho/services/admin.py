"""Admin tools (BETA_PLAN §5): assign mentors, deactivate users and
projects, read the audit log. Every change is audited."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.enums import ProshoUserRole
from app.prosho.models.prosho_audit_log import ProshoAuditLog
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.models.prosho_project_mentor import ProshoProjectMentor
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.schemas.admin import AdminProject, AdminUser, AdminUserUpdate, AuditEntry
from app.prosho.schemas.team import Person
from app.prosho.services import audit
from app.prosho.services.auth import get_current_user

MENTOR_ROLES = (ProshoUserRole.mentor, ProshoUserRole.admin)


async def get_admin(user: ProshoUser = Depends(get_current_user)) -> ProshoUser:
    if user.role != ProshoUserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return user


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


async def list_users(db: AsyncSession) -> list[AdminUser]:
    owned = (select(ProshoProject.owner_id, func.count().label("n"))
             .group_by(ProshoProject.owner_id).subquery())
    rows = (await db.execute(select(ProshoUser, func.coalesce(owned.c.n, 0))
                             .outerjoin(owned, owned.c.owner_id == ProshoUser.id)
                             .order_by(ProshoUser.created_at))).all()
    return [AdminUser(id=u.id, github_login=u.github_login, name=u.name, avatar_url=u.avatar_url, role=u.role,
                      is_active=u.is_active, created_at=u.created_at, projects_owned=n) for u, n in rows]


async def update_user(user_id: uuid.UUID, body: AdminUserUpdate, admin: ProshoUser, db: AsyncSession) -> None:
    user = await db.get(ProshoUser, user_id)
    if user is None:
        raise _not_found("User")
    sent = body.model_dump(exclude_unset=True, exclude_none=True)
    if user.id == admin.id and sent:
        # The only admin in beta — this would lock everyone out of these tools.
        raise _conflict("You can't change your own role or deactivate yourself")
    changes = {k: v for k, v in sent.items() if getattr(user, k) != v}
    if not changes:
        return
    if "role" in changes and changes["role"] not in MENTOR_ROLES:
        mentoring = await db.scalar(select(func.count()).where(ProshoProjectMentor.mentor_id == user.id))
        if mentoring:
            raise _conflict("Remove them as mentor from their projects first")
    before = {k: getattr(user, k) for k in changes}
    for k, v in changes.items():
        setattr(user, k, v)
    audit.record(db, actor_id=admin.id, action="user.update", entity="user", entity_id=user.id,
                 before=before, after=changes)
    await db.commit()


async def list_projects(db: AsyncSession) -> list[AdminProject]:
    rows = (await db.execute(select(ProshoProject, ProshoUser)
                             .join(ProshoUser, ProshoUser.id == ProshoProject.owner_id)
                             .order_by(ProshoProject.created_at.desc()))).all()
    mentors: dict[uuid.UUID, list[Person]] = {}
    for pm, u in (await db.execute(select(ProshoProjectMentor, ProshoUser)
                                   .join(ProshoUser, ProshoUser.id == ProshoProjectMentor.mentor_id)
                                   .order_by(ProshoProjectMentor.created_at))).all():
        mentors.setdefault(pm.project_id, []).append(Person.model_validate(u))
    return [AdminProject(id=p.id, slug=p.slug, title=p.title, visibility=p.visibility, is_active=p.is_active,
                         repo_full_name=p.repo_full_name, owner=Person.model_validate(owner),
                         mentors=mentors.get(p.id, []), created_at=p.created_at) for p, owner in rows]


async def _project(project_id: uuid.UUID, db: AsyncSession) -> ProshoProject:
    project = await db.get(ProshoProject, project_id)
    if project is None:
        raise _not_found("Project")
    return project


async def set_project_active(project_id: uuid.UUID, is_active: bool, admin: ProshoUser, db: AsyncSession) -> None:
    project = await _project(project_id, db)
    if project.is_active == is_active:
        return
    audit.record(db, actor_id=admin.id, action="project.update", entity="project", entity_id=project.id,
                 before={"is_active": project.is_active}, after={"is_active": is_active})
    project.is_active = is_active
    await db.commit()


async def assign_mentor(project_id: uuid.UUID, mentor_id: uuid.UUID, admin: ProshoUser, db: AsyncSession) -> None:
    project = await _project(project_id, db)
    mentor = await db.get(ProshoUser, mentor_id)
    if mentor is None:
        raise _not_found("User")
    if not mentor.is_active or mentor.role not in MENTOR_ROLES:
        raise _conflict("Only active mentors or admins can be assigned — change their role first")
    if mentor.id == project.owner_id:
        raise _conflict("A student can't mentor their own project")
    db.add(ProshoProjectMentor(project_id=project.id, mentor_id=mentor.id, assigned_by=admin.id))
    audit.record(db, actor_id=admin.id, action="mentor.assign", entity="project", entity_id=project.id,
                 after={"mentor_id": mentor.id, "mentor_login": mentor.github_login})
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _conflict("Already a mentor on this project")


async def remove_mentor(project_id: uuid.UUID, mentor_id: uuid.UUID, admin: ProshoUser, db: AsyncSession) -> None:
    project = await _project(project_id, db)
    link = await db.scalar(select(ProshoProjectMentor).where(
        ProshoProjectMentor.project_id == project.id, ProshoProjectMentor.mentor_id == mentor_id))
    if link is None:
        raise _not_found("Mentor assignment")
    login = await db.scalar(select(ProshoUser.github_login).where(ProshoUser.id == mentor_id))
    audit.record(db, actor_id=admin.id, action="mentor.remove", entity="project", entity_id=project.id,
                 before={"mentor_id": mentor_id, "mentor_login": login})
    await db.delete(link)
    await db.commit()


async def audit_log(db: AsyncSession, limit: int, before: Optional[datetime]) -> list[AuditEntry]:
    q = (select(ProshoAuditLog, ProshoUser.github_login)
         .outerjoin(ProshoUser, ProshoUser.id == ProshoAuditLog.actor_id)
         .order_by(ProshoAuditLog.created_at.desc()).limit(limit))
    if before is not None:
        q = q.where(ProshoAuditLog.created_at < before)
    return [AuditEntry(id=a.id, actor_login=login, action=a.action, entity=a.entity, entity_id=a.entity_id,
                       before=a.before, after=a.after, created_at=a.created_at)
            for a, login in (await db.execute(q)).all()]
