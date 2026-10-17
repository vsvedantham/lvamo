"""The public project page (lvamo.com/prosho/<slug>).

Unlisted and public pages are open to anyone. A private page is visible only
to its owner (as a preview); to everyone else it's a 404, the same as a page
that doesn't exist — so private projects can't be discovered by guessing
slugs.
"""
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.enums import ProjectType, Visibility
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.modules import data_science_page
from app.prosho.schemas.public import PublicOwner, PublicProject
from app.prosho.services import claims_view


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
    is_owner = viewer is not None and viewer.id == owner.id
    if project.visibility == Visibility.private and not is_owner:
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
        updated_at=max(project.updated_at, project.manifest_synced_at or project.updated_at),
        preview=project.visibility == Visibility.private,
    )
