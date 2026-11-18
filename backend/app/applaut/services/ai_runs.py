"""Applaut AI's nightly runs as one user sees them: what each night searched,
what fit them, and what the model did with it (scored, 80+, documents)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.ai.nightly import next_run_at
from app.applaut.models.ai_queue import AIQueueItem, NightRun
from app.applaut.models.job_assessment import JobAssessment
from app.applaut.schemas.job_engine import AiNight, AiRunsResponse, AiRunTotals
from app.config import settings

LEFT = ("pending", "running")


async def _work(db: AsyncSession, user_id: uuid.UUID, night_ids: list[uuid.UUID]) -> dict:
    """{night id: {"score_job": {status: n}, "write_docs": {...}, "good": n}} from the queue."""
    out: dict = {}
    if not night_ids:
        return out
    good = case((JobAssessment.match_score >= settings.applaut_ai_doc_threshold, 1), else_=0)
    rows = await db.execute(
        select(AIQueueItem.night_run_id, AIQueueItem.kind, AIQueueItem.status, func.count(), func.sum(good))
        .join(JobAssessment, JobAssessment.id == AIQueueItem.assessment_id, isouter=True)
        .where(AIQueueItem.user_id == user_id, AIQueueItem.night_run_id.in_(night_ids),
               AIQueueItem.kind.in_(("score_job", "write_docs")))
        .group_by(AIQueueItem.night_run_id, AIQueueItem.kind, AIQueueItem.status)
    )
    for night_id, kind, status, n, n_good in rows:
        night = out.setdefault(night_id, {"score_job": {}, "write_docs": {}, "good": 0})
        night[kind][status] = n
        if kind == "score_job" and status == "done":
            night["good"] += int(n_good or 0)
    return out


def _night(run: NightRun, mine: dict, work: dict) -> AiNight:
    score, docs = work.get("score_job", {}), work.get("write_docs", {})
    pool = (run.stats or {}).get("_pool") or {}
    return AiNight(
        run_date=run.run_date, started_at=run.started_at, discovery_done_at=run.discovery_done_at,
        postings_checked=run.jobs_found, by_source=pool.get("by_source") or {}, closed=pool.get("closed"),
        matched=int(mine.get("matched") or 0), new=int(mine.get("new") or 0),
        no_description=int(mine.get("no_description") or 0), queued=int(mine.get("queued") or 0),
        waiting=int(mine.get("waiting") or 0),
        scored=score.get("done", 0), scoring_left=sum(score.get(s, 0) for s in LEFT),
        scoring_failed=score.get("failed", 0), good=work.get("good", 0),
        docs_done=docs.get("done", 0), docs_left=sum(docs.get(s, 0) for s in LEFT), docs_failed=docs.get("failed", 0),
    )


async def list_nights(user_id: uuid.UUID, db: AsyncSession, limit: int = 30) -> AiRunsResponse:
    """The nights this user was part of, newest first, and totals over all of them."""
    key = str(user_id)
    runs = list(await db.scalars(
        select(NightRun).where(NightRun.stats.has_key(key)).order_by(NightRun.run_date.desc())))
    work = await _work(db, user_id, [r.id for r in runs])
    nights = [_night(r, r.stats[key], work.get(r.id, {})) for r in runs]
    totals = AiRunTotals(nights=len(nights), new=sum(n.new for n in nights), scored=sum(n.scored for n in nights),
                         good=sum(n.good for n in nights), docs_done=sum(n.docs_done for n in nights))
    return AiRunsResponse(nights=nights[:limit], totals=totals, doc_threshold=settings.applaut_ai_doc_threshold,
                          next_run_at=next_run_at(datetime.now(timezone.utc)))
