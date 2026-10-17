"""When Applaut looks at a user's routine (docs/applaut/JOB_ENGINES_DESIGN.md §6.3).

For each run time T in the routine's schedule: status checks at T + 30 min,
+ 60 min, + 2 h and + 3 h (stopping at the first that sees the run
finished), then a sync 60 minutes after the run finished. Both are
engine_tasks rows, run by the dispatcher in discovery/scheduler.py; there is
at most one open check and one open sync per profile."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.models.engine_task import EngineTask
from app.applaut.models.profile import Profile
from app.applaut.models.routine import RoutineConnection

KIND_ROUTINE_CHECK = "routine_check"
KIND_ROUTINE_SYNC = "routine_sync"
OPEN_STATUSES = ("pending", "running")

CHECK_OFFSETS = (timedelta(minutes=30), timedelta(minutes=60), timedelta(hours=2), timedelta(hours=3))
SYNC_DELAY = timedelta(minutes=60)
# A run belongs to T if it started between T - this and T + 3 h (routines can
# start a little early or late).
RUN_EARLY_TOLERANCE = timedelta(minutes=20)
CHECKED_STATUSES = ("active", "error")  # connection states that still get checks

_DOW_NAMES = ["sun", "mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cron_dow_to_names(field: str) -> str:
    # Cron counts weekdays from Sunday = 0; APScheduler from Monday = 0. Names
    # mean the same in both, so translate numbers to names.
    return re.sub(r"\d+", lambda m: _DOW_NAMES[int(m.group())] if int(m.group()) <= 7 else m.group(), field)


def cron_trigger(expr: str, tz: str) -> CronTrigger:
    """Raise ValueError for an expression or timezone Applaut can't use."""
    fields = (expr or "").split()
    if len(fields) != 5:
        raise ValueError("A schedule needs 5 cron fields: minute hour day month weekday")
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"Unknown timezone {tz!r}") from None
    minute, hour, day, month, dow = fields
    try:
        trigger = CronTrigger(minute=minute, hour=hour, day=day, month=month,
                              day_of_week=_cron_dow_to_names(dow), timezone=zone)
    except ValueError as exc:
        raise ValueError(f"Invalid schedule: {exc}") from None
    # A routine that runs more than every 4 hours would mean checks overlap.
    first = trigger.get_next_fire_time(None, _now())
    second = trigger.get_next_fire_time(first, first + timedelta(seconds=1)) if first else None
    if first is None:
        raise ValueError("This schedule never runs")
    if second is not None and second - first < timedelta(hours=4):
        raise ValueError("Runs must be at least 4 hours apart")
    return trigger


def next_run_after(conn: RoutineConnection, after: datetime) -> datetime | None:
    """The first scheduled run time strictly after `after` (UTC)."""
    trigger = cron_trigger(conn.schedule_cron, conn.timezone)
    t = trigger.get_next_fire_time(None, after + timedelta(seconds=1))
    return t.astimezone(timezone.utc) if t else None


def plan_check(conn: RoutineConnection, now: datetime, after_run: datetime | None = None) -> dict | None:
    """The next status check to queue: {expected_at, step, due_at}. `after_run`
    = the run time just dealt with, so the plan moves on to a later one."""
    floor = now - CHECK_OFFSETS[-1]
    if after_run is not None:
        floor = max(floor, after_run)
    t = next_run_after(conn, floor)
    if t is None:
        return None
    for step, offset in enumerate(CHECK_OFFSETS):
        if t + offset > now:
            return {"expected_at": t.isoformat(), "step": step, "due_at": (t + offset).isoformat()}
    return None  # unreachable: t > now - 3 h


def next_step(payload: dict) -> dict | None:
    step = int(payload["step"]) + 1
    if step >= len(CHECK_OFFSETS):
        return None
    t = datetime.fromisoformat(payload["expected_at"])
    return {"expected_at": payload["expected_at"], "step": step, "due_at": (t + CHECK_OFFSETS[step]).isoformat()}


async def _open_task(db: AsyncSession, kind: str, profile_id: uuid.UUID) -> EngineTask | None:
    return await db.scalar(select(EngineTask).where(
        EngineTask.kind == kind, EngineTask.profile_id == profile_id, EngineTask.status.in_(OPEN_STATUSES),
    ))


async def queue_check(db: AsyncSession, profile: Profile, plan: dict) -> None:
    """Queue (or move) the profile's one open status check. Commits."""
    open_task = await _open_task(db, KIND_ROUTINE_CHECK, profile.id)
    due = datetime.fromisoformat(plan["due_at"])
    if open_task is None:
        await db.execute(insert(EngineTask).values(
            id=uuid.uuid4(), kind=KIND_ROUTINE_CHECK, user_id=profile.user_id, profile_id=profile.id,
            due_at=due, status="pending", attempts=0,
            payload={"expected_at": plan["expected_at"], "step": plan["step"]},
        ).on_conflict_do_nothing())
    elif open_task.status == "pending":
        open_task.due_at = due
        open_task.payload = {"expected_at": plan["expected_at"], "step": plan["step"]}
    await db.commit()


async def queue_sync(db: AsyncSession, profile: Profile, due: datetime, trigger: str,
                     run_id: str | None = None) -> bool:
    """Queue a sync at `due`, or bring an already queued one forward. Returns
    False when a sync is running right now (it can't be queued twice). Commits."""
    open_task = await _open_task(db, KIND_ROUTINE_SYNC, profile.id)
    if open_task is not None and open_task.status == "running":
        return False
    payload = {"trigger": trigger, "run_id": run_id}
    if open_task is None:
        await db.execute(insert(EngineTask).values(
            id=uuid.uuid4(), kind=KIND_ROUTINE_SYNC, user_id=profile.user_id, profile_id=profile.id,
            due_at=due, status="pending", attempts=0, payload=payload,
        ).on_conflict_do_nothing())
    elif due < open_task.due_at:
        open_task.due_at = due
        open_task.payload = payload
    await db.commit()
    return True


async def _cancel_open(db: AsyncSession, profile_id: uuid.UUID) -> None:
    tasks = await db.scalars(select(EngineTask).where(
        EngineTask.kind.in_((KIND_ROUTINE_CHECK, KIND_ROUTINE_SYNC)),
        EngineTask.profile_id == profile_id, EngineTask.status == "pending",
    ))
    for task in tasks:
        task.status, task.finished_at = "cancelled", _now()
    await db.commit()


async def ensure_routine_tasks(profile_id: uuid.UUID | str, db: AsyncSession, reschedule: bool = False) -> None:
    """Make the queue match the profile: a status check is queued while the
    profile uses its own routine and the connection is active (or failing but
    not yet paused); nothing otherwise. `reschedule` re-plans a queued check
    (after the schedule changed). Commits."""
    profile = await db.get(Profile, uuid.UUID(str(profile_id)))
    if profile is None:
        return
    conn = await db.scalar(select(RoutineConnection).where(RoutineConnection.user_id == profile.user_id))
    wanted = (profile.is_active and profile.job_engine == "own_routine"
              and conn is not None and conn.status in CHECKED_STATUSES)
    if not wanted:
        await _cancel_open(db, profile.id)
        return
    open_task = await _open_task(db, KIND_ROUTINE_CHECK, profile.id)
    if open_task is None or (reschedule and open_task.status == "pending"):
        plan = plan_check(conn, _now())
        if plan is not None:
            await queue_check(db, profile, plan)


async def open_tasks(profile_id: uuid.UUID, db: AsyncSession) -> dict[str, EngineTask]:
    tasks = await db.scalars(select(EngineTask).where(
        EngineTask.kind.in_((KIND_ROUTINE_CHECK, KIND_ROUTINE_SYNC)),
        EngineTask.profile_id == profile_id, EngineTask.status.in_(OPEN_STATUSES),
    ))
    return {t.kind: t for t in tasks}
