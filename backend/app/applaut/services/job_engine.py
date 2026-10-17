"""Settings → Job engine: which engine a user has, and engine 3's connection
to the user's own Claude routine (docs/applaut/JOB_ENGINES_DESIGN.md §6.6–6.8)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.core import credentials
from app.applaut.models.profile import Profile
from app.applaut.models.routine import RoutineConnection, RoutineRun, RoutineSync
from app.applaut.models.user import User
from app.applaut.routine import checks, schedule
from app.applaut.routine.source import (
    NeonReader, NotReadOnly, R2Credentials, SourceError, check_r2, neon_host,
)
from app.applaut.schemas.job_engine import (
    CheckResult, ConnectionTestResponse, EngineCard, JobEngineResponse, RoutineConnectionInfo,
    RoutineConnectionInput, RoutineRunInfo, RoutineSyncInfo,
)
from app.applaut.services.audit import log_action
from app.applaut.services.profile import get_active_profile

logger = logging.getLogger(__name__)

SYNC_NOW_EVERY = timedelta(minutes=10)
DEFAULT_CRON = "7 6,18 * * *"
DEFAULT_TZ = "UTC"
DEFAULT_PREFIX = "jobautomationdocs"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_credentials_storage() -> None:
    if not credentials.is_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Applaut can't store credentials yet (APPLAUT_CREDENTIALS_KEY is not set)")


async def get_connection(user: User, db: AsyncSession) -> RoutineConnection | None:
    return await db.scalar(select(RoutineConnection).where(RoutineConnection.user_id == user.id))


async def _reschedule(profile: Profile, db: AsyncSession, reschedule: bool = False) -> None:
    from app.applaut.discovery.scheduler import sync_discovery_task
    try:
        await sync_discovery_task(profile.id, db)
        await schedule.ensure_routine_tasks(profile.id, db, reschedule=reschedule)
    except Exception:  # noqa: BLE001  (the bootstrap re-syncs at the next start)
        await db.rollback()
        logger.warning("Could not update the engine schedule for profile %s", profile.id, exc_info=True)


# ----------------------------------------------------------------------------- engine choice

async def set_engine(user: User, engine: str, confirm_delete_credentials: bool, db: AsyncSession) -> Profile:
    profile = await get_active_profile(user, db)
    if engine == "applaut_ai":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Applaut AI isn't available yet")
    before = profile.job_engine
    if engine == before:
        return profile
    conn = await get_connection(user, db)
    if before == "own_routine" and conn is not None:
        if not confirm_delete_credentials:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Switching away from your Claude routine deletes its stored connection. Confirm to continue.")
        await _delete_connection(user, conn, db, reason="engine_switch")
    profile.job_engine = engine
    profile.job_engine_changed_at = _now()
    await log_action(action="job_engine.switch", db=db, user_id=str(user.id), entity_type="profile",
                     entity_id=str(profile.id), before_state={"job_engine": before}, after_state={"job_engine": engine})
    await db.commit()
    await db.refresh(profile)
    await _reschedule(profile, db)
    return profile


# ----------------------------------------------------------------------------- connection

def _merged(conn: RoutineConnection | None, data: RoutineConnectionInput) -> dict:
    """The connection as it would be after this save, secrets decrypted."""
    def pick(new, old_attr, default=None):
        if new is not None:
            return new
        return getattr(conn, old_attr) if conn is not None else default

    merged = {
        "r2_account_id": pick(data.r2_account_id, "r2_account_id"),
        "r2_bucket": pick(data.r2_bucket, "r2_bucket"),
        "r2_prefix": pick(data.r2_prefix, "r2_prefix", DEFAULT_PREFIX),
        "routine_url": data.routine_url if "routine_url" in data.model_fields_set else (conn.routine_url if conn else None),
        "schedule_cron": pick(data.schedule_cron, "schedule_cron", DEFAULT_CRON),
        "timezone": pick(data.timezone, "timezone", DEFAULT_TZ),
        "neon_url": data.neon_url or (credentials.decrypt(conn.neon_url_enc) if conn else None),
        "r2_access_key_id": data.r2_access_key_id or (credentials.decrypt(conn.r2_access_key_id_enc) if conn else None),
        "r2_secret": data.r2_secret or (credentials.decrypt(conn.r2_secret_enc) if conn else None),
    }
    missing = [k for k in ("neon_url", "r2_account_id", "r2_bucket", "r2_access_key_id", "r2_secret") if not merged[k]]
    if missing:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Missing: {', '.join(missing)}")
    try:
        schedule.cron_trigger(merged["schedule_cron"], merged["timezone"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    return merged


async def run_checks(merged: dict) -> ConnectionTestResponse:
    """§6.6 Test connection: Neon reachable, read-only, jobs table readable,
    contract version; R2 listable and read-only."""
    results: list[CheckResult] = []
    version = None

    def add(key, label, ok, message):
        results.append(CheckResult(key=key, label=label, ok=ok, message=message))

    try:
        async with NeonReader(merged["neon_url"]) as src:
            add("neon_connect", "Neon reachable", True, "Connected")
            try:
                role = await src.check_read_only()
                add("neon_read_only", "Neon role is read-only", True, f"Role {role} can only read")
                version = await src.contract_version()
                jobs = await src.count_jobs()
                add("neon_jobs", "Jobs table readable", True, f"{jobs} job{'s' if jobs != 1 else ''} found")
                add("contract", "Run log", True,
                    f"run_tracker found (contract v{version})" if version else
                    "No run_tracker table: jobs and documents sync, but run status and failure reasons aren't "
                    "available. Update to the latest skeleton to see them.")
            except NotReadOnly as exc:
                add("neon_read_only", "Neon role is read-only", False, str(exc))
            except SourceError as exc:
                add("neon_jobs", "Jobs table readable", False, str(exc))
    except SourceError as exc:
        add("neon_connect", "Neon reachable", False, str(exc))

    try:
        report = await check_r2(R2Credentials(
            account_id=merged["r2_account_id"], bucket=merged["r2_bucket"], prefix=merged["r2_prefix"].strip("/"),
            access_key_id=merged["r2_access_key_id"], secret=merged["r2_secret"],
        ))
        add("r2_list", "R2 bucket readable", True,
            f"{merged['r2_bucket']}/{merged['r2_prefix']}/ " + ("is readable" + (f" ({'; '.join(report.notes)})" if report.notes else "")))
        add("r2_read_only", "R2 key is read-only", True, "The key can't write to the bucket")
    except NotReadOnly as exc:
        add("r2_list", "R2 bucket readable", True, f"{merged['r2_bucket']} is readable")
        add("r2_read_only", "R2 key is read-only", False, str(exc))
    except SourceError as exc:
        add("r2_list", "R2 bucket readable", False, str(exc))

    return ConnectionTestResponse(ok=all(r.ok for r in results) and len(results) >= 6,
                                  checks=results, contract_version=version)


async def test_connection(user: User, data: RoutineConnectionInput, db: AsyncSession) -> ConnectionTestResponse:
    _require_credentials_storage()
    conn = await get_connection(user, db)
    result = await run_checks(_merged(conn, data))
    await log_action(action="routine.connection_tested", db=db, user_id=str(user.id), entity_type="routine_connection",
                     entity_id=str(conn.id) if conn else None,
                     after_state={"ok": result.ok, "failed": [c.key for c in result.checks if not c.ok]})
    await db.commit()
    return result


async def save_connection(user: User, data: RoutineConnectionInput, db: AsyncSession) -> tuple[RoutineConnection | None, ConnectionTestResponse]:
    """Check, then store. Nothing is saved unless every check passes. A save
    also clears a paused or failing state ("Try again")."""
    _require_credentials_storage()
    profile = await get_active_profile(user, db)
    if profile.job_engine != "own_routine":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Choose 'Your own Claude routine' as your job engine first")
    conn = await get_connection(user, db)
    merged = _merged(conn, data)
    result = await run_checks(merged)
    if not result.ok:
        await log_action(action="routine.connection_refused", db=db, user_id=str(user.id),
                         entity_type="routine_connection", entity_id=str(conn.id) if conn else None,
                         after_state={"failed": [c.key for c in result.checks if not c.ok]})
        await db.commit()
        return None, result

    first = conn is None
    if first:
        conn = RoutineConnection(user_id=user.id)
        db.add(conn)
    replaced = [k for k in ("neon_url", "r2_access_key_id", "r2_secret") if getattr(data, k)]
    schedule_changed = not first and (conn.schedule_cron, conn.timezone) != (merged["schedule_cron"], merged["timezone"])
    conn.neon_url_enc = credentials.encrypt(merged["neon_url"])
    conn.neon_host = neon_host(merged["neon_url"])
    conn.r2_access_key_id_enc = credentials.encrypt(merged["r2_access_key_id"])
    conn.r2_access_key_hint = merged["r2_access_key_id"][-4:]
    conn.r2_secret_enc = credentials.encrypt(merged["r2_secret"])
    for k in ("r2_account_id", "r2_bucket", "r2_prefix", "routine_url", "schedule_cron", "timezone"):
        setattr(conn, k, merged[k])
    conn.contract_version = result.contract_version
    conn.status, conn.verified_at, conn.last_check_at = "active", _now(), _now()
    conn.last_error, conn.consecutive_failures = None, 0
    await db.flush()
    await log_action(
        action="routine.connection_saved", db=db, user_id=str(user.id), entity_type="routine_connection",
        entity_id=str(conn.id),
        after_state={"neon_host": conn.neon_host, "r2_bucket": conn.r2_bucket, "r2_prefix": conn.r2_prefix,
                     "schedule_cron": conn.schedule_cron, "timezone": conn.timezone,
                     "contract_version": conn.contract_version, "secrets_replaced": replaced, "first": first},
    )
    await db.commit()
    await db.refresh(conn)

    await _reschedule(profile, db, reschedule=schedule_changed or first)
    if first or replaced:
        # §6.7 step 9: the first sync runs now rather than after the next run.
        await schedule.queue_sync(db, profile, _now(), "initial" if first else "manual")
        _kick()
    return conn, result


async def _delete_connection(user: User, conn: RoutineConnection, db: AsyncSession, reason: str) -> None:
    await log_action(action="routine.connection_removed", db=db, user_id=str(user.id), entity_type="routine_connection",
                     entity_id=str(conn.id), before_state={"neon_host": conn.neon_host, "r2_bucket": conn.r2_bucket},
                     after_state={"reason": reason})
    await db.delete(conn)
    await db.flush()


async def remove_connection(user: User, db: AsyncSession) -> None:
    """Deletes the stored secrets now; synced jobs and documents stay."""
    conn = await get_connection(user, db)
    if conn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No routine connection")
    await _delete_connection(user, conn, db, reason="removed")
    await db.commit()
    profile = await get_active_profile(user, db)
    await _reschedule(profile, db)


def _kick() -> None:
    from app.applaut.discovery.scheduler import kick_dispatcher
    kick_dispatcher()


async def sync_now(user: User, db: AsyncSession) -> tuple[bool, str]:
    """§6.3 Sync now: refresh the run status, then sync at once. At most
    once every 10 minutes."""
    profile = await get_active_profile(user, db)
    conn = await get_connection(user, db)
    if conn is None or profile.job_engine != "own_routine":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No routine connection")
    if conn.status == "paused":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Checking is paused after repeated connection failures. Update your connection or press Try again.")
    now = _now()
    if conn.last_manual_sync_at and now - conn.last_manual_sync_at < SYNC_NOW_EVERY:
        wait = SYNC_NOW_EVERY - (now - conn.last_manual_sync_at)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"You can sync again in {max(1, int(wait.total_seconds() // 60) + 1)} minutes",
                            headers={"Retry-After": str(int(wait.total_seconds()) + 1)})
    conn.last_manual_sync_at = now
    await db.commit()
    try:
        await checks.refresh_runs(db, conn)
    except (SourceError, credentials.CredentialsUnavailable) as exc:
        await checks.record_failure(db, conn, str(exc))
        return False, f"Applaut can't connect to your routine's data: {exc}"
    if not await schedule.queue_sync(db, profile, now, "manual"):
        return False, "A sync is already running"
    await log_action(action="routine.sync_requested", db=db, user_id=str(user.id), entity_type="routine_connection",
                     entity_id=str(conn.id))
    await db.commit()
    _kick()
    return True, "Sync started"


# ----------------------------------------------------------------------------- reading

def run_info(run: RoutineRun, conn: RoutineConnection | None) -> RoutineRunInfo:
    info = RoutineRunInfo.model_validate(run)
    if conn is not None:
        info.message = checks.describe(run, conn)
    return info


async def list_runs(user: User, db: AsyncSession, limit: int = 50) -> list[RoutineRunInfo]:
    conn = await get_connection(user, db)
    runs = await db.scalars(
        select(RoutineRun).where(RoutineRun.user_id == user.id)
        .order_by(func.coalesce(RoutineRun.started_at, RoutineRun.expected_at).desc()).limit(limit)
    )
    return [run_info(r, conn) for r in runs]


async def list_syncs(user: User, db: AsyncSession, limit: int = 20) -> list[RoutineSyncInfo]:
    syncs = await db.scalars(
        select(RoutineSync).where(RoutineSync.user_id == user.id).order_by(RoutineSync.started_at.desc()).limit(limit)
    )
    return [RoutineSyncInfo.model_validate(s) for s in syncs]


CARD_LABELS = {
    "setup_incomplete": "Setup incomplete", "waiting": "Waiting for the first run", "running": "Running",
    "healthy": "Healthy", "problems": "Finished with problems", "failed": "Failed", "stopped": "Stopped part-way",
    "didnt_run": "Didn't run", "cant_connect": "Can't connect", "no_run_details": "Run details not available",
}
OUTCOME_STATE = {"running": "running", "succeeded": "healthy", "problems": "problems", "failed": "failed",
                 "stopped": "stopped", "missed": "didnt_run"}


async def build_card(user: User, profile: Profile, db: AsyncSession) -> EngineCard:
    conn = await get_connection(user, db)
    if conn is None:
        return EngineCard(state="setup_incomplete", label=CARD_LABELS["setup_incomplete"],
                          message="Connect your routine's Neon database and R2 bucket in Settings → Job engine.")
    latest = await db.scalar(
        select(RoutineRun).where(RoutineRun.user_id == user.id)
        .order_by(func.coalesce(RoutineRun.started_at, RoutineRun.expected_at).desc()).limit(1)
    )
    last_sync = await db.scalar(select(RoutineSync).where(RoutineSync.user_id == user.id)
                                .order_by(RoutineSync.started_at.desc()).limit(1))
    tasks = await schedule.open_tasks(profile.id, db)
    now = _now()
    try:
        next_run = schedule.next_run_after(conn, now)
    except ValueError:
        next_run = None
    sync_task = tasks.get(schedule.KIND_ROUTINE_SYNC)
    next_sync, estimated = (sync_task.due_at, False) if sync_task and sync_task.status == "pending" else (None, False)
    if next_sync is None and next_run is not None and conn.status in schedule.CHECKED_STATUSES:
        # A typical run takes ~15 minutes; the sync follows an hour after it ends.
        next_sync, estimated = next_run + timedelta(minutes=15) + schedule.SYNC_DELAY, True

    if conn.status in ("error", "paused"):
        state = "cant_connect"
        message = f"Applaut can't connect to your routine's data ({conn.last_error or 'unknown error'}). " \
                  "Did the password or key change? Update your connection."
        if conn.status == "paused":
            message += f" Checking stopped after {checks.MAX_CONSECUTIVE_FAILURES} failed attempts."
    elif conn.contract_version == 0:
        state = "no_run_details"
        message = "Run details aren't available for your routine version. Update to the latest skeleton to see why runs fail."
    elif latest is None:
        state = "waiting"
        message = "No runs recorded yet. Applaut checks after each scheduled run."
    else:
        state = OUTCOME_STATE.get(latest.outcome, "problems")
        message = checks.describe(latest, conn)

    available = conn.last_manual_sync_at + SYNC_NOW_EVERY if conn.last_manual_sync_at else None
    return EngineCard(
        state=state, label=CARD_LABELS[state], message=message, paused=conn.status == "paused",
        last_run=run_info(latest, conn) if latest else None,
        last_sync=RoutineSyncInfo.model_validate(last_sync) if last_sync else None,
        next_run_at=next_run, next_sync_at=next_sync, next_sync_estimated=estimated,
        sync_running=bool(sync_task and sync_task.status == "running"),
        sync_now_available_at=available if available and available > now else None,
        routine_url=conn.routine_url,
    )


async def get_job_engine(user: User, db: AsyncSession) -> JobEngineResponse:
    profile = await get_active_profile(user, db)
    conn = await get_connection(user, db)
    card = await build_card(user, profile, db) if profile.job_engine == "own_routine" else None
    return JobEngineResponse(
        engine=profile.job_engine, engine_changed_at=profile.job_engine_changed_at,
        credentials_storage_ready=credentials.is_configured(),
        connection=RoutineConnectionInfo.model_validate(conn) if conn else None, card=card,
    )
