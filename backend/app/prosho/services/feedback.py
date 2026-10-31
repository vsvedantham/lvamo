"""Mentor <-> student feedback. Threads with one level of replies, optionally
about a milestone or a claim. Either side can start a thread, reply, or
mark a thread resolved. Never shown on the public page (BETA_PLAN §8)."""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.prosho_claim import ProshoClaim
from app.prosho.models.prosho_feedback import ProshoFeedback
from app.prosho.models.prosho_milestone import ProshoMilestone
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.models.prosho_project_mentor import ProshoProjectMentor
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.schemas.team import FeedbackCreate, FeedbackMessage, FeedbackThread, Person

MAX_THREADS_PER_PROJECT = 500
MAX_REPLIES_PER_THREAD = 100


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


async def open_counts(project_ids: list[uuid.UUID], db: AsyncSession) -> dict[uuid.UUID, int]:
    if not project_ids:
        return {}
    rows = await db.execute(
        select(ProshoFeedback.project_id, func.count())
        .where(ProshoFeedback.project_id.in_(project_ids), ProshoFeedback.parent_id.is_(None),
               ProshoFeedback.resolved_at.is_(None))
        .group_by(ProshoFeedback.project_id))
    return dict(rows.all())


async def list_threads(project: ProshoProject, db: AsyncSession) -> list[FeedbackThread]:
    """Open threads first, newest first within each group; replies oldest first."""
    rows = list(await db.scalars(select(ProshoFeedback).where(ProshoFeedback.project_id == project.id)
                                 .order_by(ProshoFeedback.created_at)))
    author_ids = {r.author_id for r in rows if r.author_id}
    authors = ({u.id: u for u in await db.scalars(select(ProshoUser).where(ProshoUser.id.in_(author_ids)))}
               if author_ids else {})
    mentor_ids = set(await db.scalars(select(ProshoProjectMentor.mentor_id)
                                      .where(ProshoProjectMentor.project_id == project.id)))
    milestone_ids = {r.milestone_id for r in rows if r.milestone_id}
    milestones = ({m.id: m.title for m in await db.scalars(select(ProshoMilestone).where(ProshoMilestone.id.in_(milestone_ids)))}
                  if milestone_ids else {})
    claim_ids = {r.claim_id for r in rows if r.claim_id}
    claims = ({c.id: c.text for c in await db.scalars(select(ProshoClaim).where(ProshoClaim.id.in_(claim_ids)))}
              if claim_ids else {})

    def message(r: ProshoFeedback) -> dict:
        author = authors.get(r.author_id)
        role = ("owner" if r.author_id == project.owner_id
                else "mentor" if r.author_id in mentor_ids else None)
        return {"id": r.id, "author": Person.model_validate(author) if author else None,
                "author_role": role, "body": r.body, "created_at": r.created_at}

    replies: dict[uuid.UUID, list[FeedbackMessage]] = {}
    for r in rows:
        if r.parent_id:
            replies.setdefault(r.parent_id, []).append(FeedbackMessage(**message(r)))
    threads = [FeedbackThread(
        **message(r), milestone_id=r.milestone_id, milestone_title=milestones.get(r.milestone_id),
        claim_id=r.claim_id, claim_text=claims.get(r.claim_id), resolved_at=r.resolved_at,
        replies=replies.get(r.id, []),
    ) for r in rows if r.parent_id is None]
    threads.sort(key=lambda t: t.created_at, reverse=True)
    threads.sort(key=lambda t: t.resolved_at is not None)
    return threads


async def create(project: ProshoProject, body: FeedbackCreate, user: ProshoUser, db: AsyncSession) -> None:
    if body.parent_id:
        if body.milestone_id or body.claim_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="A reply belongs to its thread — it can't point at a milestone or claim")
        parent = await db.get(ProshoFeedback, body.parent_id)
        if not parent or parent.project_id != project.id or parent.parent_id is not None:
            raise _not_found("Thread")
        count = await db.scalar(select(func.count()).where(ProshoFeedback.parent_id == parent.id))
        if count >= MAX_REPLIES_PER_THREAD:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This thread is full — start a new one")
        # Replying to a resolved thread reopens it.
        parent.resolved_at = parent.resolved_by = None
    else:
        count = await db.scalar(select(func.count()).where(ProshoFeedback.project_id == project.id,
                                                           ProshoFeedback.parent_id.is_(None)))
        if count >= MAX_THREADS_PER_PROJECT:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This project has too many feedback threads")
    if body.milestone_id:
        m = await db.get(ProshoMilestone, body.milestone_id)
        if not m or m.project_id != project.id:
            raise _not_found("Milestone")
    if body.claim_id:
        c = await db.get(ProshoClaim, body.claim_id)
        if not c or c.project_id != project.id or c.archived_at is not None:
            raise _not_found("Claim")
    db.add(ProshoFeedback(project_id=project.id, author_id=user.id, parent_id=body.parent_id,
                          milestone_id=body.milestone_id, claim_id=body.claim_id, body=body.body))
    await db.commit()


async def set_resolved(project: ProshoProject, feedback_id: uuid.UUID, resolved: bool, user: ProshoUser,
                       db: AsyncSession) -> None:
    f = await db.get(ProshoFeedback, feedback_id)
    if not f or f.project_id != project.id or f.parent_id is not None:
        raise _not_found("Thread")
    if resolved and f.resolved_at is None:
        f.resolved_at, f.resolved_by = datetime.now(timezone.utc), user.id
    elif not resolved and f.resolved_at is not None:
        f.resolved_at = f.resolved_by = None
    await db.commit()
