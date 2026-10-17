"""Applaut's engine scheduler.

The schedule lives in Postgres (`applaut.engine_tasks`), not in each
worker's memory. Every uvicorn worker runs the same small dispatcher every
two minutes; it claims due tasks with FOR UPDATE SKIP LOCKED, so a task runs
in exactly one worker, every worker sees the same schedule, and the schedule
survives restarts (docs/applaut/JOB_ENGINES_DESIGN.md §3.3).

Task kinds: Applaut Basic's discovery run for a profile, and engine 3's
status checks and syncs (routine/schedule.py); engine 2 runs come later.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.applaut.discovery.engine import run_discovery_for_profile
from app.applaut.models.engine_task import EngineTask
from app.applaut.models.profile import Profile

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")

KIND_BASIC_DISCOVERY = "basic_discovery"
OPEN_STATUSES = ("pending", "running")

DISPATCH_EVERY_SECONDS = 120
CLAIM_BATCH = 5
# A task still `running` after this long belongs to a worker that died.
STALE_RUNNING_AFTER = timedelta(hours=1)
# Waits before retrying a task that raised; after the last one it is `failed`.
RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30))

# Belt and braces inside a discovery run: the dispatcher already runs each
# task once, but the run itself also takes a Postgres advisory lock and skips
# if the last run finished within this fraction of the interval.
_RECENT_RUN_FRACTION = 0.9


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ran_recently(profile: Profile) -> bool:
    if profile.last_discovery_at is None:
        return False
    hours = max(1, profile.discovery_frequency_hours or 24)
    age = datetime.now(timezone.utc) - profile.last_discovery_at
    return age < timedelta(hours=hours * _RECENT_RUN_FRACTION)


async def _run_profile(profile_id: str) -> None:
    # The lock lives on its own session: discovery and scoring commit several
    # times, and each commit would release a transaction-level lock held on
    # the working session. It is released when lock_db closes, after the
    # working session has committed last_discovery_at.
    async with AsyncSessionLocal() as lock_db:
        acquired = await lock_db.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"applaut.discovery:{profile_id}"},
        )
        if not acquired:
            logger.info("Discovery for profile %s already running in another worker; skipping", profile_id)
            return
        await _run_profile_locked(profile_id)


async def _run_profile_locked(profile_id: str) -> None:
    async with AsyncSessionLocal() as db:
        profile = await db.get(Profile, profile_id)
        if not profile or not profile.is_active or not profile.discovery_enabled:
            return
        if _ran_recently(profile):
            logger.info(
                "Discovery for profile %s already ran at %s; skipping",
                profile_id, profile.last_discovery_at.isoformat(),
            )
            return

        new_count = 0
        try:
            new_count = await run_discovery_for_profile(profile, db)
            profile.last_discovery_at = datetime.now(timezone.utc)
            logger.info("Discovery: %d new jobs for profile %s", new_count, profile_id)
        except Exception as exc:
            logger.error("Discovery failed for profile %s: %s", profile_id, exc)
            return

        # Auto-score after discovery
        good_matches = 0
        near_misses = 0
        try:
            from app.applaut.services.scoring import run_scoring
            from app.applaut.models.user import User
            user = await db.get(User, profile.user_id)
            if user:
                result = await run_scoring(user, db, mode="rule_based")
                good_matches = result["good_matches"]
                near_misses = result["near_misses"]
                profile.last_scored_at = datetime.now(timezone.utc)
                logger.info(
                    "Auto-scoring: %d scored, %d good, %d near-miss for profile %s",
                    result["scored"], good_matches, near_misses, profile_id,
                )
        except Exception as exc:
            logger.error("Auto-scoring failed for profile %s: %s", profile_id, exc)

        # Notify user of new matches
        try:
            from app.applaut.services.notification import create_notification
            if new_count > 0 or good_matches > 0:
                parts = []
                if new_count > 0:
                    parts.append(f"{new_count} new job{'s' if new_count != 1 else ''} found")
                if good_matches > 0:
                    parts.append(f"{good_matches} good match{'es' if good_matches != 1 else ''}")
                if near_misses > 0:
                    parts.append(f"{near_misses} near miss{'es' if near_misses != 1 else ''}")
                await create_notification(
                    user_id=str(profile.user_id),
                    type="discovery_complete",
                    title="Discovery complete — " + ", ".join(parts),
                    body=f"Review your matches on the Scores page.",
                    metadata={"new_jobs": new_count, "good_matches": good_matches, "near_misses": near_misses},
                    db=db,
                )
        except Exception as exc:
            logger.error("Notification failed for profile %s: %s", profile_id, exc)

        await db.commit()


# ----------------------------------------------------------------------------- schedule

def _wants_discovery(profile: Profile | None) -> bool:
    return bool(
        profile and profile.is_active and profile.discovery_enabled and profile.job_engine == "basic"
    )


async def sync_discovery_task(
    profile_id: str | uuid.UUID, db: AsyncSession, not_before: datetime | None = None
) -> None:
    """Make the queue match the profile: exactly one open discovery task if
    the profile is active, on Applaut Basic and has discovery on; none
    otherwise. Call after any change to those settings (commits).
    `not_before` keeps the next run at least that far out (used after a run,
    so a run that failed before recording itself doesn't repeat at once)."""
    profile = await db.get(Profile, uuid.UUID(str(profile_id)))
    open_task = await db.scalar(select(EngineTask).where(
        EngineTask.kind == KIND_BASIC_DISCOVERY,
        EngineTask.profile_id == uuid.UUID(str(profile_id)),
        EngineTask.status.in_(OPEN_STATUSES),
    ))

    if not _wants_discovery(profile):
        if open_task is not None and open_task.status == "pending":
            open_task.status = "cancelled"
            open_task.finished_at = _now()
            await db.commit()
            logger.info("Cancelled discovery for profile %s", profile_id)
        return

    hours = max(1, profile.discovery_frequency_hours or 24)
    due = max(_now(), profile.last_discovery_at + timedelta(hours=hours)) if profile.last_discovery_at else _now()
    if not_before is not None:
        due = max(due, not_before)

    if open_task is None:
        # ON CONFLICT DO NOTHING: two workers bootstrapping at once race here,
        # and the partial unique index keeps only one open task.
        await db.execute(insert(EngineTask).values(
            id=uuid.uuid4(), kind=KIND_BASIC_DISCOVERY, user_id=profile.user_id, profile_id=profile.id,
            due_at=due, status="pending", attempts=0, payload={"interval_hours": hours},
        ).on_conflict_do_nothing())
        await db.commit()
        logger.info("Scheduled discovery for profile %s every %dh, next %s", profile_id, hours, due.isoformat())
    elif open_task.status == "pending" and (open_task.payload or {}).get("interval_hours") != hours:
        open_task.due_at = due
        open_task.payload = {**(open_task.payload or {}), "interval_hours": hours}
        await db.commit()
        logger.info("Rescheduled discovery for profile %s every %dh, next %s", profile_id, hours, due.isoformat())


async def get_discovery_schedule(profile_id: str | uuid.UUID, db: AsyncSession) -> dict | None:
    task = await db.scalar(select(EngineTask).where(
        EngineTask.kind == KIND_BASIC_DISCOVERY,
        EngineTask.profile_id == uuid.UUID(str(profile_id)),
        EngineTask.status.in_(OPEN_STATUSES),
    ))
    if task is None:
        return None
    return {
        "profile_id": str(profile_id),
        "next_run_at": task.due_at.isoformat(),
        "interval_hours": int((task.payload or {}).get("interval_hours") or 24),
    }


# ----------------------------------------------------------------------------- dispatcher

async def _run_basic_discovery(task: EngineTask) -> None:
    await _run_profile(str(task.profile_id))


async def _after_basic_discovery(task: EngineTask, db: AsyncSession) -> None:
    hours = int((task.payload or {}).get("interval_hours") or 24)
    await sync_discovery_task(task.profile_id, db, not_before=_now() + timedelta(hours=hours))


async def _run_routine_check(task: EngineTask) -> None:
    from app.applaut.routine.checks import run_check
    await run_check(task)


async def _after_routine_check(task: EngineTask, db: AsyncSession) -> None:
    """Queue the check the handler decided on (in payload `next`); if the
    handler never got that far (it kept failing), plan from the schedule."""
    from app.applaut.models.routine import RoutineConnection
    from app.applaut.routine import schedule as routine_schedule
    payload = task.payload or {}
    profile = await db.get(Profile, task.profile_id)
    if profile is None:
        return
    plan = payload.get("next")
    if not payload.get("decided"):
        conn = await db.scalar(select(RoutineConnection).where(RoutineConnection.user_id == task.user_id))
        if conn is not None:
            expected = datetime.fromisoformat(payload["expected_at"])
            plan = routine_schedule.plan_check(conn, _now(), after_run=expected)
    if plan is not None:
        await routine_schedule.queue_check(db, profile, plan)
    await routine_schedule.ensure_routine_tasks(profile.id, db)


async def _run_routine_sync(task: EngineTask) -> None:
    from app.applaut.routine.sync import SyncBusy, sync_user
    payload = task.payload or {}
    try:
        await sync_user(task.user_id, payload.get("trigger") or "scheduled", payload.get("run_id"))
    except SyncBusy:
        logger.info("Routine sync for user %s already running elsewhere; skipping", task.user_id)


_HANDLERS: dict[str, Callable[[EngineTask], Awaitable[None]]] = {
    KIND_BASIC_DISCOVERY: _run_basic_discovery,
    "routine_check": _run_routine_check,
    "routine_sync": _run_routine_sync,
}
# Runs after a task is closed (done or finally failed), e.g. to queue the next run.
_FOLLOW_UPS: dict[str, Callable[[EngineTask, AsyncSession], Awaitable[None]]] = {
    KIND_BASIC_DISCOVERY: _after_basic_discovery,
    "routine_check": _after_routine_check,
}


async def _recover_stale_tasks(db: AsyncSession) -> None:
    await db.execute(
        update(EngineTask)
        .where(EngineTask.status == "running", EngineTask.started_at < _now() - STALE_RUNNING_AFTER)
        .values(status="pending", due_at=_now(), last_error="worker stopped while running; retrying",
                updated_at=_now())
    )
    await db.commit()


async def _claim_due_tasks(db: AsyncSession) -> list[EngineTask]:
    tasks = list(await db.scalars(
        select(EngineTask)
        .where(EngineTask.status == "pending", EngineTask.due_at <= _now())
        .order_by(EngineTask.due_at)
        .limit(CLAIM_BATCH)
        .with_for_update(skip_locked=True)
    ))
    for task in tasks:
        task.status = "running"
        task.started_at = _now()
        task.attempts += 1
    await db.commit()
    return tasks


async def _close_task(task_id: uuid.UUID, error: str | None) -> None:
    async with AsyncSessionLocal() as db:
        task = await db.get(EngineTask, task_id)
        if task is None:
            return
        if error is None:
            task.status, task.last_error = "done", None
        elif task.attempts <= len(RETRY_DELAYS):
            task.status, task.last_error = "pending", error[:4000]
            task.due_at = _now() + RETRY_DELAYS[task.attempts - 1]
        else:
            task.status, task.last_error = "failed", error[:4000]
        task.finished_at = _now()
        await db.commit()
        if task.status in ("done", "failed") and task.kind in _FOLLOW_UPS:
            await _FOLLOW_UPS[task.kind](task, db)


async def dispatch_due_tasks() -> int:
    """Run every due task this worker can claim. Returns how many ran."""
    async with AsyncSessionLocal() as db:
        await _recover_stale_tasks(db)
        tasks = await _claim_due_tasks(db)
    for task in tasks:
        handler = _HANDLERS.get(task.kind)
        error = None
        try:
            if handler is None:
                raise RuntimeError(f"no handler for task kind {task.kind!r}")
            await handler(task)
        except Exception as exc:  # noqa: BLE001  (a failed task must not stop the others)
            logger.exception("Engine task %s (%s) failed", task.id, task.kind)
            error = f"{type(exc).__name__}: {exc}"
        await _close_task(task.id, error)
    return len(tasks)


_kicked: set[asyncio.Task] = set()


def kick_dispatcher() -> None:
    """Run the dispatcher now in the background (e.g. after Sync now), instead
    of waiting up to two minutes for its next tick."""
    try:
        task = asyncio.get_running_loop().create_task(dispatch_due_tasks())
    except RuntimeError:
        return
    _kicked.add(task)
    task.add_done_callback(_kicked.discard)


async def _bootstrap() -> None:
    """Bring the queue in line with every active profile (idempotent, so every
    worker can run it at startup)."""
    from app.applaut.routine.schedule import ensure_routine_tasks
    async with AsyncSessionLocal() as db:
        profile_ids = list(await db.scalars(select(Profile.id).where(Profile.is_active == True)))
        for profile_id in profile_ids:
            await sync_discovery_task(profile_id, db)
            await ensure_routine_tasks(profile_id, db)


def start_scheduler() -> None:
    scheduler.start()
    scheduler.add_job(_bootstrap, trigger="date", id="engine_bootstrap", replace_existing=True)
    scheduler.add_job(
        dispatch_due_tasks,
        trigger="interval",
        seconds=DISPATCH_EVERY_SECONDS,
        id="engine_dispatcher",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        next_run_time=_now() + timedelta(seconds=30),
    )
    logger.info("Engine scheduler started")


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
