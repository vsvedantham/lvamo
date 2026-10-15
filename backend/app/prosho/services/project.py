import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.enums import Visibility
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.schemas.project import ProjectCreate, ProjectUpdate
from app.prosho.services import audit

# Owned by prosho.yaml once a manifest has synced (BETA_PLAN §7).
MANIFEST_FIELDS = {"title", "demo_kind", "demo_url"}


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


async def list_projects(user: ProshoUser, db: AsyncSession) -> list[ProshoProject]:
    rows = await db.scalars(
        select(ProshoProject)
        .where(ProshoProject.owner_id == user.id, ProshoProject.is_active.is_(True))
        .order_by(ProshoProject.created_at.desc())
    )
    return list(rows)


async def get_owned(project_id: uuid.UUID, user: ProshoUser, db: AsyncSession) -> ProshoProject:
    """404 for missing, inactive or someone else's project — never 403, so
    existence isn't leaked (CLAUDE.md API rules)."""
    project = await db.get(ProshoProject, project_id)
    if not project or not project.is_active or project.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def _slug_taken(slug: str, db: AsyncSession, exclude: uuid.UUID | None = None) -> bool:
    q = select(ProshoProject.id).where(ProshoProject.slug == slug)
    if exclude:
        q = q.where(ProshoProject.id != exclude)
    return (await db.scalar(q)) is not None


async def create_project(payload: ProjectCreate, user: ProshoUser, db: AsyncSession) -> ProshoProject:
    if await _slug_taken(payload.slug, db):
        raise _conflict("That address is already taken — pick another")
    project = ProshoProject(owner_id=user.id, title=payload.title.strip(), slug=payload.slug,
                            project_type=payload.project_type)
    db.add(project)
    try:
        await db.flush()
    except IntegrityError:  # lost a race for the slug
        await db.rollback()
        raise _conflict("That address is already taken — pick another")
    audit.record(db, actor_id=user.id, action="project.create", entity="project", entity_id=project.id,
                 after={"title": project.title, "slug": project.slug, "project_type": project.project_type})
    await db.commit()
    await db.refresh(project)
    return project


async def update_project(project: ProshoProject, payload: ProjectUpdate, user: ProshoUser, db: AsyncSession) -> ProshoProject:
    sent = payload.model_dump(exclude_unset=True)
    changes: dict = {}

    if project.manifest_synced_at is not None and MANIFEST_FIELDS & sent.keys():
        raise _conflict("Title and demo come from prosho.yaml in your repo — edit them there")

    if "title" in sent:
        changes["title"] = sent["title"].strip()

    if "slug" in sent and sent["slug"] != project.slug:
        # A shared link must keep working: the address is fixed once the page
        # has ever been visible to anyone else.
        if project.published_at is not None:
            raise _conflict("The page address can't change after the page has been shared")
        if await _slug_taken(sent["slug"], db, exclude=project.id):
            raise _conflict("That address is already taken — pick another")
        changes["slug"] = sent["slug"]

    for field in ("university", "programme"):
        if field in sent:
            changes[field] = sent[field]

    if "demo_kind" in sent:
        changes["demo_kind"] = sent["demo_kind"]
        changes["demo_url"] = str(sent["demo_url"]) if sent["demo_url"] is not None else None

    target_visibility = sent.get("visibility") or project.visibility
    supervisor_ok_at = project.supervisor_ok_at
    if "supervisor_confirmed" in sent:
        if sent["supervisor_confirmed"]:
            supervisor_ok_at = supervisor_ok_at or datetime.now(timezone.utc)
        else:
            if target_visibility == Visibility.public:
                raise _conflict("Make the page unlisted or private before withdrawing supervisor approval")
            supervisor_ok_at = None
        if supervisor_ok_at != project.supervisor_ok_at:
            changes["supervisor_ok_at"] = supervisor_ok_at

    if "visibility" in sent and sent["visibility"] != project.visibility:
        if sent["visibility"] == Visibility.public and supervisor_ok_at is None:
            raise _conflict("Confirm your supervisor has agreed before making the page public")
        changes["visibility"] = sent["visibility"]
        if sent["visibility"] != Visibility.private and project.published_at is None:
            changes["published_at"] = datetime.now(timezone.utc)

    changes = {k: v for k, v in changes.items() if getattr(project, k) != v}
    if not changes:
        return project

    before = {k: getattr(project, k) for k in changes}
    for k, v in changes.items():
        setattr(project, k, v)
    audit.record(db, actor_id=user.id, action="project.update", entity="project", entity_id=project.id,
                 before=before, after=changes)
    try:
        await db.commit()
    except IntegrityError:  # slug race
        await db.rollback()
        raise _conflict("That address is already taken — pick another")
    await db.refresh(project)
    return project
