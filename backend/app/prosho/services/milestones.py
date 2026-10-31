"""Milestones: the student plans and completes them; a mentor reviews
completed ones. Shown on the public page (title, due date, done, reviewed)."""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.prosho_milestone import ProshoMilestone
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.schemas.team import MilestoneCreate, MilestoneResponse, MilestoneUpdate, Person
from app.prosho.services import audit
from app.prosho.services.project import Access

MAX_PER_PROJECT = 50


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


async def list_milestones(project_id: uuid.UUID, db: AsyncSession) -> list[ProshoMilestone]:
    """Dated ones first, by due date; undated ones after, in the order added."""
    rows = await db.scalars(select(ProshoMilestone).where(ProshoMilestone.project_id == project_id)
                            .order_by(ProshoMilestone.due_on.asc().nulls_last(), ProshoMilestone.position))
    return list(rows)


async def responses(milestones: list[ProshoMilestone], db: AsyncSession) -> list[MilestoneResponse]:
    reviewer_ids = {m.reviewed_by for m in milestones if m.reviewed_by}
    reviewers = ({u.id: u for u in await db.scalars(select(ProshoUser).where(ProshoUser.id.in_(reviewer_ids)))}
                 if reviewer_ids else {})
    return [MilestoneResponse(
        id=m.id, title=m.title, due_on=m.due_on, completed_at=m.completed_at, reviewed_at=m.reviewed_at,
        reviewed_by=Person.model_validate(reviewers[m.reviewed_by]) if m.reviewed_by in reviewers else None,
        position=m.position, created_at=m.created_at,
    ) for m in milestones]


async def _get(project: ProshoProject, milestone_id: uuid.UUID, db: AsyncSession) -> ProshoMilestone:
    m = await db.get(ProshoMilestone, milestone_id)
    if not m or m.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")
    return m


async def create(project: ProshoProject, body: MilestoneCreate, user: ProshoUser, db: AsyncSession) -> ProshoMilestone:
    count = await db.scalar(select(func.count()).where(ProshoMilestone.project_id == project.id))
    if count >= MAX_PER_PROJECT:
        raise _conflict(f"A project can have at most {MAX_PER_PROJECT} milestones")
    last = await db.scalar(select(func.max(ProshoMilestone.position)).where(ProshoMilestone.project_id == project.id))
    m = ProshoMilestone(project_id=project.id, title=body.title, due_on=body.due_on,
                        position=(last + 1) if last is not None else 0)
    db.add(m)
    await db.flush()
    audit.record(db, actor_id=user.id, action="milestone.create", entity="milestone", entity_id=m.id,
                 after={"project_id": project.id, "title": m.title, "due_on": m.due_on})
    await db.commit()
    await db.refresh(m)
    return m


async def update(project: ProshoProject, access: Access, milestone_id: uuid.UUID, body: MilestoneUpdate,
                 user: ProshoUser, db: AsyncSession) -> ProshoMilestone:
    m = await _get(project, milestone_id, db)
    sent = body.model_dump(exclude_unset=True)
    owner_fields = {"title", "due_on", "completed"} & sent.keys()
    if access == "mentor" and owner_fields:
        raise _conflict("Only the student can edit or complete milestones")
    if access == "owner" and "reviewed" in sent:
        raise _conflict("Only a mentor can review milestones")

    now = datetime.now(timezone.utc)
    changes: dict = {}
    if "title" in sent and sent["title"] is not None and sent["title"] != m.title:
        changes["title"] = sent["title"]
    if "due_on" in sent and sent["due_on"] != m.due_on:
        changes["due_on"] = sent["due_on"]
    if "completed" in sent and sent["completed"] is not None:
        if sent["completed"] and m.completed_at is None:
            changes["completed_at"] = now
        elif not sent["completed"] and m.completed_at is not None:
            changes["completed_at"] = None
    # A review covers the milestone as it was: reopening it or renaming it
    # (it's now about something else) takes the review away.
    if m.reviewed_at is not None and ("title" in changes or changes.get("completed_at", m.completed_at) is None):
        changes["reviewed_at"] = changes["reviewed_by"] = None
    if "reviewed" in sent and sent["reviewed"] is not None:
        if sent["reviewed"] and m.reviewed_at is None:
            if m.completed_at is None:
                raise _conflict("A milestone can be reviewed once the student has completed it")
            changes["reviewed_at"], changes["reviewed_by"] = now, user.id
        elif not sent["reviewed"] and m.reviewed_at is not None:
            changes["reviewed_at"] = changes["reviewed_by"] = None

    if not changes:
        return m
    before = {k: getattr(m, k) for k in changes}
    for k, v in changes.items():
        setattr(m, k, v)
    audit.record(db, actor_id=user.id, action="milestone.update", entity="milestone", entity_id=m.id,
                 before=before, after=changes)
    await db.commit()
    await db.refresh(m)
    return m


async def delete(project: ProshoProject, milestone_id: uuid.UUID, user: ProshoUser, db: AsyncSession) -> None:
    m = await _get(project, milestone_id, db)
    audit.record(db, actor_id=user.id, action="milestone.delete", entity="milestone", entity_id=m.id,
                 before={"project_id": project.id, "title": m.title, "due_on": m.due_on,
                         "completed_at": m.completed_at, "reviewed_at": m.reviewed_at})
    await db.delete(m)
    await db.commit()
