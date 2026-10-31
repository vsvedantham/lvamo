"""Deleting a project or a whole account (privacy notice: "your rights").

Everything a project owns goes with it through ON DELETE CASCADE. The audit
log has no foreign keys, so the rows that describe the deleted things are
removed here and one tombstone row is kept to say a deletion happened.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.enums import ProshoUserRole
from app.prosho.models.prosho_audit_log import ProshoAuditLog
from app.prosho.models.prosho_claim import ProshoClaim
from app.prosho.models.prosho_ingest_token import ProshoIngestToken
from app.prosho.models.prosho_milestone import ProshoMilestone
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.models.prosho_retired_slug import ProshoRetiredSlug
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.services import audit


async def _purge_project(project: ProshoProject, db: AsyncSession) -> None:
    """Drops the project, its children and their audit history. Doesn't
    commit and doesn't write the tombstone."""
    ids = [project.id]
    for model in (ProshoClaim, ProshoMilestone, ProshoIngestToken):
        ids += list(await db.scalars(select(model.id).where(model.project_id == project.id)))
    pid = str(project.id)
    await db.execute(delete(ProshoAuditLog).where(or_(
        ProshoAuditLog.entity_id.in_(ids),
        ProshoAuditLog.after["project_id"].astext == pid,
        ProshoAuditLog.before["project_id"].astext == pid,
    )))
    # A link that was ever shared stays dead rather than passing to a stranger.
    if project.published_at is not None:
        await db.merge(ProshoRetiredSlug(slug=project.slug))
    await db.delete(project)


async def delete_project(project: ProshoProject, user: ProshoUser, db: AsyncSession) -> None:
    retired = project.published_at is not None
    pid = project.id
    await _purge_project(project, db)
    audit.record(db, actor_id=user.id, action="project.delete", entity="project", entity_id=pid,
                 after={"slug_retired": retired})
    await db.commit()


async def delete_account(user: ProshoUser, confirm: str, db: AsyncSession) -> None:
    if confirm.strip().lower() != user.github_login.lower():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Type your GitHub username to confirm")
    if user.role == ProshoUserRole.admin:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Admins can't delete their own account — ask another admin to change your role first")

    # Including deactivated ones: deletion means all of it.
    projects = list(await db.scalars(select(ProshoProject).where(ProshoProject.owner_id == user.id)))
    for project in projects:
        await _purge_project(project, db)

    uid = str(user.id)
    await db.execute(delete(ProshoAuditLog).where(
        ProshoAuditLog.entity == "user", ProshoAuditLog.entity_id == user.id))
    # Mentor assignments on other students' projects name the mentor.
    await db.execute(text("""
        UPDATE prosho.audit_logs
        SET after = CASE WHEN after->>'mentor_id' = :uid THEN after - 'mentor_login' ELSE after END,
            before = CASE WHEN before->>'mentor_id' = :uid THEN before - 'mentor_login' ELSE before END
        WHERE after->>'mentor_id' = :uid OR before->>'mentor_id' = :uid
    """), {"uid": uid})

    # Feedback they wrote on someone else's project stays, signed "Former
    # member" (author_id SET NULL); the student's side of the thread is theirs.
    audit.record(db, actor_id=None, action="user.delete", entity="user", entity_id=user.id,
                 after={"projects_deleted": len(projects)})
    await db.delete(user)
    await db.commit()
