from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.prosho_project import ProshoProject
from app.prosho.models.prosho_project_mentor import ProshoProjectMentor
from app.prosho.schemas.project import ProjectResponse
from app.prosho.services import feedback
from app.prosho.services.project import Access


async def respond_many(rows: list[tuple[ProshoProject, Access]], db: AsyncSession) -> list[ProjectResponse]:
    ids = [p.id for p, _ in rows]
    open_feedback = await feedback.open_counts(ids, db)
    mentored = set(await db.scalars(select(ProshoProjectMentor.project_id)
                                    .where(ProshoProjectMentor.project_id.in_(ids)))) if ids else set()
    return [ProjectResponse.from_project(p, access=access, has_mentor=p.id in mentored,
                                         open_feedback=open_feedback.get(p.id, 0)) for p, access in rows]


async def respond(project: ProshoProject, db: AsyncSession, access: Access = "owner") -> ProjectResponse:
    return (await respond_many([(project, access)], db))[0]
