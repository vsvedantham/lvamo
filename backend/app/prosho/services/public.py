"""The public project page (lvamo.com/prosho/<slug>).

Unlisted and public pages are open to anyone. A private page is visible only
to its owner and mentors (as a preview); to everyone else it's a 404, the
same as a page that doesn't exist — so private projects can't be discovered
by guessing slugs.
"""
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.enums import ProjectType, Visibility
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.modules import data_science_page
from app.prosho.schemas.public import PublicMilestone, PublicOwner, PublicProject
from app.prosho.services import claims_view, milestones, timeline
from app.prosho.services.project import has_mentor, is_mentor


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


async def get_public_project(slug: str, viewer: ProshoUser | None, db: AsyncSession) -> PublicProject:
    row = (await db.execute(
        select(ProshoProject, ProshoUser)
        .join(ProshoUser, ProshoUser.id == ProshoProject.owner_id)
        .where(ProshoProject.slug == slug.lower())
    )).first()
    if row is None:
        raise _not_found()
    project, owner = row
    if not project.is_active or not owner.is_active:
        raise _not_found()
    is_team = viewer is not None and (viewer.id == owner.id or await is_mentor(project.id, viewer.id, db))
    if project.visibility == Visibility.private and not is_team:
        raise _not_found()

    claims = await claims_view.active_claims(project, db)
    data_module = (await data_science_page.build(project, claims, db)
                   if project.project_type == ProjectType.data_science else None)
    return PublicProject(
        slug=project.slug,
        title=project.title,
        summary=project.summary,
        problem=project.problem,
        project_type=project.project_type,
        university=project.university,
        programme=project.programme,
        visibility=project.visibility,
        demo_kind=project.demo_kind,
        demo_url=project.demo_url,
        owner=PublicOwner(name=owner.name, github_login=owner.github_login, avatar_url=owner.avatar_url),
        claims=await claims_view.resolve(project, claims, db),
        data_module=data_module,
        milestones=[PublicMilestone(title=m.title, due_on=m.due_on, completed_at=m.completed_at,
                                    reviewed=m.reviewed_at is not None)
                    for m in await milestones.list_milestones(project.id, db)],
        timeline=(await timeline.build(project, db, include_messages=project.repo_private is False)
                  if project.repo_id is not None else None),
        mentored=await has_mentor(project.id, db),
        updated_at=max(project.updated_at, project.manifest_synced_at or project.updated_at),
        preview=project.visibility == Visibility.private,
        viewer_is_team=is_team,
    )
