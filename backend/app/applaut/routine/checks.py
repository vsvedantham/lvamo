"""Status checks: what happened to the routine run scheduled at T
(docs/applaut/JOB_ENGINES_DESIGN.md §6.3, §6.5).

A check opens one short read-only session on the user's Neon, copies the
recent run_tracker rows into routine_runs, and decides: the run finished
(queue its sync an hour after it finished), still running (check again
later), or, at the last check (T + 3 h), stopped part-way or never started.
Applaut never guesses: with no run_tracker (contract v0) it only knows
whether the jobs table changed."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.core import credentials
from app.applaut.models.engine_task import EngineTask
from app.applaut.models.profile import Profile
from app.applaut.models.routine import RoutineConnection, RoutineRun
from app.applaut.routine import schedule
from app.applaut.routine.source import NeonReader, SourceError
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 5  # §6.9: then the connection is paused
STALE_AFTER = schedule.CHECK_OFFSETS[-1]
STALE_ERROR_PREFIX = "no completion recorded"
RUN_FIELDS = (
    "contract_version", "started_at", "finished_at", "status", "current_step", "error",
    "searches_run", "search_budget", "postings_found", "postings_assessed", "jobs_eligible",
    "jobs_new", "jobs_updated", "jobs_rejected", "docs_done", "docs_failed", "sources_failed", "summary",
)
TEXT_LIMITS = {"error": 4000, "summary": 20000, "sources_failed": 4000, "current_step": 50, "status": 20}
BAD_OUTCOMES = ("problems", "failed", "stopped", "missed")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def outcome_of(row: dict, now: datetime) -> str:
    status = (row.get("status") or "").lower()
    if status == "running":
        started = row.get("started_at")
        return "stopped" if started and started < now - STALE_AFTER else "running"
    if status == "failed":
        return "stopped" if (row.get("error") or "").lower().startswith(STALE_ERROR_PREFIX) else "failed"
    if status == "partial" or (row.get("sources_failed") or "").strip():
        return "problems"
    if status == "succeeded":
        return "succeeded"
    return "problems"


def neon_url(conn: RoutineConnection) -> str:
    return credentials.decrypt(conn.neon_url_enc)


async def mirror_runs(db: AsyncSession, user_id: uuid.UUID, rows: list[dict], now: datetime) -> dict[str, RoutineRun]:
    """Upsert run_tracker rows into routine_runs (flushes). Returns them by run_id."""
    out: dict[str, RoutineRun] = {}
    for row in rows:
        run_id = str(row.get("run_id") or "")[:100]
        if not run_id:
            continue
        run = await db.scalar(select(RoutineRun).where(RoutineRun.user_id == user_id, RoutineRun.run_id == run_id))
        if run is None:
            run = RoutineRun(user_id=user_id, run_id=run_id)
            db.add(run)
        for f in RUN_FIELDS:
            value = row.get(f)
            if isinstance(value, str) and f in TEXT_LIMITS:
                value = value[:TEXT_LIMITS[f]]
            setattr(run, f, value)
        run.source_updated_at = row.get("updated_at")
        run.outcome = outcome_of(row, now)
        out[run_id] = run
    await db.flush()
    return out


def run_for(runs: list[RoutineRun], expected_at: datetime) -> RoutineRun | None:
    """The run that belongs to the scheduled time: the first one started in
    [T - 20 min, T + 3 h]."""
    lo, hi = expected_at - schedule.RUN_EARLY_TOLERANCE, expected_at + STALE_AFTER
    candidates = [r for r in runs if r.started_at and lo <= r.started_at <= hi]
    return min(candidates, key=lambda r: r.started_at) if candidates else None


def local_time(conn: RoutineConnection, at: datetime | None) -> str:
    if at is None:
        return "?"
    try:
        return at.astimezone(ZoneInfo(conn.timezone)).strftime("%H:%M %Z")
    except Exception:  # noqa: BLE001
        return at.strftime("%H:%M UTC")


def step_label(step: str | None) -> str:
    return (step or "an unknown step").replace("_", " ").capitalize()


def describe(run: RoutineRun, conn: RoutineConnection) -> str:
    """The §6.5 sentence for a run's outcome (plain text)."""
    when = local_time(conn, run.started_at or run.expected_at)
    if run.outcome == "missed":
        return (f"Your routine didn't run at {when}. Common causes: the routine is paused, your Claude plan's "
                "limit was reached, or its environment failed to start. Open the routine in Claude to check.")
    if run.outcome == "stopped":
        return (f"Your routine run at {when} stopped during {step_label(run.current_step)} and never finished. "
                "This usually means the run hit your Claude plan's usage limit or a time limit. "
                "Open the routine in Claude to see its transcript.")
    if run.outcome == "failed":
        reason = (run.error or "no reason recorded").strip().splitlines()[0][:300]
        return f"Your routine run at {when} failed at step {step_label(run.current_step)}: {reason}"
    if run.outcome == "problems":
        parts = []
        if (run.sources_failed or "").strip():
            parts.append(run.sources_failed.strip()[:300])
        if run.docs_failed:
            parts.append(f"{run.docs_failed} document{'s' if run.docs_failed != 1 else ''} failed")
        return "Finished with problems: " + ("; ".join(parts) if parts else "see the run's summary")
    if run.outcome == "running":
        return f"Your routine started at {when} and is still running (now at {step_label(run.current_step)})."
    found = f" · {run.jobs_new} new job{'s' if run.jobs_new != 1 else ''}" if run.jobs_new is not None else ""
    return f"Your routine ran at {when} and completed{found}."


async def _notify_run(db: AsyncSession, conn: RoutineConnection, run: RoutineRun) -> None:
    if run.outcome not in BAD_OUTCOMES or run.notified_at is not None:
        return
    from app.applaut.services.notification import create_notification
    titles = {"missed": "Your routine didn't run", "stopped": "Your routine stopped part-way",
              "failed": "Your routine run failed", "problems": "Your routine finished with problems"}
    run.notified_at = _now()
    await create_notification(
        user_id=str(conn.user_id), type="routine_run", title=titles[run.outcome], body=describe(run, conn),
        metadata={"run_id": run.run_id, "outcome": run.outcome}, db=db,
    )


async def record_success(db: AsyncSession, conn: RoutineConnection, contract_version: int | None = None) -> None:
    conn.last_check_at = _now()
    conn.consecutive_failures = 0
    conn.last_error = None
    if conn.status in schedule.CHECKED_STATUSES:
        conn.status = "active"
    if contract_version is not None:
        conn.contract_version = contract_version


async def record_failure(db: AsyncSession, conn: RoutineConnection, message: str) -> None:
    """Count a failed connection; tell the user when it starts failing and
    when Applaut stops trying (paused). Commits."""
    from app.applaut.services.notification import create_notification
    was = conn.status
    conn.last_check_at = _now()
    conn.consecutive_failures += 1
    conn.last_error = message[:2000]
    if conn.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        conn.status = "paused"
    elif conn.status == "active":
        conn.status = "error"
    await db.commit()
    if conn.status != was and conn.status in ("error", "paused"):
        body = f"Applaut can't connect to your routine's data ({message}). Did the password or key change? Update your connection."
        if conn.status == "paused":
            body += f" Applaut stopped checking after {MAX_CONSECUTIVE_FAILURES} failed attempts; press Try again once it's fixed."
        await create_notification(user_id=str(conn.user_id), type="routine_connection",
                                  title="Applaut can't read your routine's data", body=body,
                                  metadata={"status": conn.status}, db=db)


async def _set_next(task_id: uuid.UUID, next_plan: dict | None, db: AsyncSession) -> None:
    task = await db.get(EngineTask, task_id)
    task.payload = {**(task.payload or {}), "next": next_plan, "decided": True}
    await db.commit()


async def run_check(task: EngineTask) -> None:
    """The routine_check task handler. Stores the next check to queue in the
    task's payload (`next`); the dispatcher's follow-up queues it."""
    payload = task.payload or {}
    expected_at = datetime.fromisoformat(payload["expected_at"])
    final = int(payload.get("step", 0)) >= len(schedule.CHECK_OFFSETS) - 1
    now = _now()
    async with AsyncSessionLocal() as db:
        profile = await db.get(Profile, task.profile_id)
        conn = await db.scalar(select(RoutineConnection).where(RoutineConnection.user_id == task.user_id))
        if (profile is None or profile.job_engine != "own_routine" or conn is None
                or conn.status not in schedule.CHECKED_STATUSES):
            await _set_next(task.id, None, db)
            return

        try:
            resolved = await _observe(db, conn, profile, expected_at, final, now)
        except (SourceError, credentials.CredentialsUnavailable) as exc:
            # Raised while reading the user's Neon, before anything local changed.
            await record_failure(db, conn, str(exc))
            resolved = False
        if conn.status not in schedule.CHECKED_STATUSES:
            next_plan = None
        elif resolved or final:
            next_plan = schedule.plan_check(conn, now, after_run=expected_at)
        else:
            next_plan = schedule.next_step(payload)
        await _set_next(task.id, next_plan, db)


async def _observe(db: AsyncSession, conn: RoutineConnection, profile: Profile,
                   expected_at: datetime, final: bool, now: datetime) -> bool:
    """True when the run for expected_at is settled (finished, stopped or missed)."""
    async with NeonReader(neon_url(conn)) as src:
        version = await src.contract_version()
        if version >= 1:
            rows = await src.runs_since(expected_at - timedelta(days=1))
            latest_seen = None
        else:
            rows, latest_seen = [], await src.latest_job_seen_at()
    await record_success(db, conn, version)

    if version == 0:
        await db.commit()
        if latest_seen is not None and latest_seen >= expected_at - schedule.RUN_EARLY_TOLERANCE:
            await schedule.queue_sync(db, profile, latest_seen + schedule.SYNC_DELAY, "scheduled")
            return True
        if final:  # no run log: sync anyway, in case documents changed
            await schedule.queue_sync(db, profile, now, "scheduled")
        return False

    runs = await mirror_runs(db, conn.user_id, rows, now)
    run = run_for(list(runs.values()), expected_at)
    if run is not None:
        run.expected_at = expected_at
    settled = False
    if run is None and final:
        missed = await db.scalar(select(RoutineRun).where(
            RoutineRun.user_id == conn.user_id, RoutineRun.run_id.is_(None), RoutineRun.expected_at == expected_at,
        ))
        if missed is None:
            missed = RoutineRun(user_id=conn.user_id, expected_at=expected_at, outcome="missed")
            db.add(missed)
        run, settled = missed, True
    elif run is not None and run.outcome == "running" and final:
        run.outcome, settled = "stopped", True
    elif run is not None and run.outcome != "running":
        settled = True
    await db.commit()

    if run is not None and run.run_id and run.outcome != "running":
        # A failed or stopped run may still have saved jobs: sync them too.
        finished = run.finished_at or now
        await schedule.queue_sync(db, profile, max(now, finished + schedule.SYNC_DELAY), "scheduled", run.run_id)
    if run is not None:
        await _notify_run(db, conn, run)
        await db.commit()
    return settled


async def refresh_runs(db: AsyncSession, conn: RoutineConnection) -> RoutineRun | None:
    """Copy the latest run_tracker rows now (Sync now / Test). Returns the
    newest run, or None on contract v0. Raises SourceError."""
    now = _now()
    async with NeonReader(neon_url(conn)) as src:
        version = await src.contract_version()
        rows = await src.runs_since(now - timedelta(days=14)) if version >= 1 else []
    await record_success(db, conn, version)
    runs = await mirror_runs(db, conn.user_id, rows, now)
    await db.commit()
    newest = max((r for r in runs.values() if r.started_at), key=lambda r: r.started_at, default=None)
    return newest
