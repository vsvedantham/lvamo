"""The model's work queue: first in, first out.

The ai-worker's lanes (one per model host) claim items; each host does one
at a time. `seq` is the order: a new item takes the next number, and so does
a retry, which therefore goes to the back. An item whose host was unreachable
is released back to its old place without using a try.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.models.ai_queue import AIQueueItem
from app.applaut.models.bullet_draft import BulletDraft
from app.applaut.models.job_assessment import JobAssessment

MAX_ATTEMPTS = 3          # first try + 2 retries (design §4)
STALE_RUNNING_AFTER = timedelta(minutes=30)
# A lane prefers its last user's next item (that user's prompt is still cached
# on its host), but only among the oldest PREFER_WINDOW pending items.
PREFER_WINDOW = 20


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


async def enqueue_draft(db: AsyncSession, draft: BulletDraft, profile_id: uuid.UUID) -> AIQueueItem:
    """Queue drafting bullets from the user's notes; it takes its place in the same FIFO."""
    item = AIQueueItem(kind="draft_bullets", user_id=draft.user_id, profile_id=profile_id,
                       bullet_draft_id=draft.id, status="pending")
    db.add(item)
    await db.flush()
    return item


async def enqueue_template(db: AsyncSession, template, profile_id: uuid.UUID) -> AIQueueItem:
    """Queue reading the user's own .docx CV (one-time); it takes its place in the same FIFO."""
    item = AIQueueItem(kind="build_template", user_id=template.user_id, profile_id=profile_id,
                       cv_template_id=template.id, status="pending")
    db.add(item)
    await db.flush()
    return item


async def enqueue_import(db: AsyncSession, imp, profile_id: uuid.UUID) -> AIQueueItem:
    """Queue drafting a master profile from the user's CV (one-time), in the same FIFO."""
    item = AIQueueItem(kind="import_profile", user_id=imp.user_id, profile_id=profile_id,
                       profile_import_id=imp.id, status="pending")
    db.add(item)
    await db.flush()
    return item


async def ahead_of(db: AsyncSession, item: AIQueueItem) -> int:
    """Items to be served before this pending one (running ones included)."""
    return await db.scalar(select(func.count()).select_from(AIQueueItem).where(
        AIQueueItem.status.in_(("pending", "running")), AIQueueItem.seq < item.seq))


async def claim_next(db: AsyncSession, host: str | None = None,
                     prefer_user: uuid.UUID | None = None) -> AIQueueItem | None:
    """The oldest pending item, or, among the oldest PREFER_WINDOW, the first of `prefer_user`'s."""
    window = list(await db.scalars(
        select(AIQueueItem).where(AIQueueItem.status == "pending")
        .order_by(AIQueueItem.seq).limit(PREFER_WINDOW if prefer_user else 1)
        .with_for_update(skip_locked=True)
    ))
    if not window:
        return None
    item = next((i for i in window if i.user_id == prefer_user), window[0])
    item.status, item.started_at, item.attempts, item.host = "running", _now(), item.attempts + 1, host
    await db.commit()
    return item


async def release(db: AsyncSession, item_id: int, error: str) -> None:
    """Its host was unreachable: back to pending, same place, the try not counted."""
    await db.execute(update(AIQueueItem).where(AIQueueItem.id == item_id).values(
        status="pending", started_at=None, attempts=AIQueueItem.attempts - 1, host=None, last_error=error[:4000]))
    await db.commit()


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
