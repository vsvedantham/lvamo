"""The model's work queue: strictly first in, first out, one item at a time.

Only the ai-worker process claims items. `seq` is the order: a new item takes
the next number, and so does a retry, which therefore goes to the back.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.models.ai_queue import AIQueueItem
from app.applaut.models.job_assessment import JobAssessment

MAX_ATTEMPTS = 3          # first try + 2 retries (design §4)
STALE_RUNNING_AFTER = timedelta(minutes=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def enqueue(db: AsyncSession, kind: str, assessment: JobAssessment, night_run_id: uuid.UUID | None = None) -> bool:
    """Queue one item for this job; False if it is already queued (pending or running)."""
    result = await db.execute(
        insert(AIQueueItem)
        .values(kind=kind, night_run_id=night_run_id, user_id=assessment.user_id, profile_id=assessment.profile_id,
                assessment_id=assessment.id, status="pending")
        .on_conflict_do_nothing(index_elements=["assessment_id", "kind"],
                                index_where=text("status IN ('pending', 'running')"))
    )
    return result.rowcount == 1


async def claim_next(db: AsyncSession) -> AIQueueItem | None:
    item = await db.scalar(
        select(AIQueueItem).where(AIQueueItem.status == "pending")
        .order_by(AIQueueItem.seq).limit(1).with_for_update(skip_locked=True)
    )
    if item is None:
        return None
    item.status, item.started_at, item.attempts = "running", _now(), item.attempts + 1
    await db.commit()
    return item


async def finish(db: AsyncSession, item_id: int, *, model: str | None = None, prompt_tokens: int | None = None,
                 output_tokens: int | None = None, duration_ms: int | None = None) -> None:
    await db.execute(update(AIQueueItem).where(AIQueueItem.id == item_id).values(
        status="done", finished_at=_now(), last_error=None, model=model,
        prompt_tokens=prompt_tokens, output_tokens=output_tokens, duration_ms=duration_ms))
    await db.commit()


async def fail(db: AsyncSession, item_id: int, error: str, retry: bool) -> bool:
    """Record a failure. Retryable failures go to the back of the queue until
    MAX_ATTEMPTS; returns True when the item is finally failed."""
    item = await db.get(AIQueueItem, item_id)
    if item is None:
        return True
    final = not retry or item.attempts >= MAX_ATTEMPTS
    item.last_error, item.finished_at = error[:4000], _now()
    if final:
        item.status = "failed"
    else:
        item.status = "pending"
        item.seq = await db.scalar(text("SELECT nextval('applaut.ai_queue_seq')"))
    await db.commit()
    return final


async def recover_stale(db: AsyncSession) -> int:
    """A worker that died mid-item leaves it running; put it back where it was."""
    result = await db.execute(update(AIQueueItem).where(
        AIQueueItem.status == "running", AIQueueItem.started_at < _now() - STALE_RUNNING_AFTER,
    ).values(status="pending", last_error="worker stopped while running; retrying"))
    await db.commit()
    return result.rowcount


async def position(db: AsyncSession, user_id: uuid.UUID) -> int | None:
    """How many items are ahead of this user's first pending item (for "N jobs ahead of you")."""
    first = await db.scalar(select(AIQueueItem.seq).where(
        AIQueueItem.user_id == user_id, AIQueueItem.status == "pending").order_by(AIQueueItem.seq).limit(1))
    if first is None:
        return None
    return await db.scalar(select(func.count()).select_from(AIQueueItem).where(
        AIQueueItem.status.in_(("pending", "running")), AIQueueItem.seq < first))
