"""Status checks after each scheduled run (docs/applaut/JOB_ENGINES_DESIGN.md
§6.3, §6.5), run through the real dispatcher."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.applaut.discovery import scheduler
from app.applaut.models.engine_task import EngineTask
from app.applaut.models.notification import Notification
from app.applaut.models.routine import RoutineConnection, RoutineRun
from app.applaut.routine import schedule
from app.db.session import AsyncSessionLocal
from tests.applaut.routine_fake import *  # noqa: F401,F403

API = "/api/v1/applaut/job-engine"


async def _tasks(profile_id, kind=None) -> list[EngineTask]:
    async with AsyncSessionLocal() as db:
        q = select(EngineTask).where(EngineTask.profile_id == profile_id).order_by(EngineTask.created_at)
        if kind:
            q = q.where(EngineTask.kind == kind)
        return list(await db.scalars(q))


async def _open(profile_id, kind) -> EngineTask | None:
    return next((t for t in await _tasks(profile_id, kind) if t.status in ("pending", "running")), None)


async def _runs(user_id) -> list[RoutineRun]:
    async with AsyncSessionLocal() as db:
        return list(await db.scalars(select(RoutineRun).where(RoutineRun.user_id == user_id)))


async def _make_check_due(profile_id, expected_at: datetime, step: int) -> None:
    """Point the open check at `expected_at` / `step` and make it due now."""
    async with AsyncSessionLocal() as db:
        await db.execute(update(EngineTask).where(
            EngineTask.profile_id == profile_id, EngineTask.kind == "routine_check", EngineTask.status == "pending",
        ).values(due_at=datetime.now(timezone.utc) - timedelta(seconds=1),
                 payload={"expected_at": expected_at.isoformat(), "step": step}))
        # Keep the first sync out of the way.
        await db.execute(update(EngineTask).where(
            EngineTask.profile_id == profile_id, EngineTask.kind == "routine_sync", EngineTask.status == "pending",
        ).values(status="cancelled"))
        await db.commit()


async def _dispatch(user_id) -> None:
    """Run due tasks, keeping other users' tasks out of it."""
    async with AsyncSessionLocal() as db:
        await db.execute(update(EngineTask).where(EngineTask.user_id != user_id, EngineTask.status == "pending")
                         .values(due_at=EngineTask.due_at + timedelta(days=3650)))
        await db.commit()
    try:
        await scheduler.dispatch_due_tasks()
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(update(EngineTask).where(EngineTask.user_id != user_id, EngineTask.status == "pending",
                                                      EngineTask.due_at > datetime.now(timezone.utc) + timedelta(days=3000))
                             .values(due_at=EngineTask.due_at - timedelta(days=3650)))
            await db.commit()


@pytest.fixture
async def connected(client, make_user, fake_source, fake_r2, routine_env):
    user, profile, headers = await make_user()
    r = await connect_routine(client, headers, fake_source)
    assert r.status_code == 200, r.text
    return user, profile, headers


def _t(hours_ago: float) -> datetime:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).replace(microsecond=0)


def test_cron_weekdays_follow_cron_numbering():
    trig = schedule.cron_trigger("7 6 * * 1", "UTC")  # cron 1 = Monday
    start = datetime(2026, 10, 17, tzinfo=timezone.utc)  # a Saturday
    assert trig.get_next_fire_time(None, start).strftime("%a %H:%M") == "Mon 06:07"


def test_plan_check_offsets():
    conn = RoutineConnection(schedule_cron="7 6,18 * * *", timezone="UTC")
    run = datetime(2026, 10, 17, 6, 7, tzinfo=timezone.utc)
    plan = schedule.plan_check(conn, run + timedelta(minutes=45))
    assert plan == {"expected_at": run.isoformat(), "step": 1, "due_at": (run + timedelta(hours=1)).isoformat()}
    plan = schedule.plan_check(conn, run + timedelta(minutes=45), after_run=run)
    assert plan["expected_at"] == (run + timedelta(hours=12)).isoformat() and plan["step"] == 0
    assert schedule.next_step({"expected_at": run.isoformat(), "step": 3}) is None


async def test_finished_run_queues_sync_an_hour_after_it_finished(connected, fake_source):
    user, profile, _ = connected
    t = _t(1)
    finished = t + timedelta(minutes=15)
    await fake_source.add_run("20261017_0808", t + timedelta(minutes=1), status="succeeded", finished_at=finished,
                              current_step="summary", jobs_new=3, docs_done=3)
    await _make_check_due(profile.id, t, step=1)
    await _dispatch(user.id)

    [run] = await _runs(user.id)
    assert (run.outcome, run.jobs_new, run.expected_at) == ("succeeded", 3, t)
    sync = await _open(profile.id, "routine_sync")
    assert sync is not None and sync.due_at == finished + timedelta(minutes=60)
    assert sync.payload["run_id"] == "20261017_0808"
    nxt = await _open(profile.id, "routine_check")  # moved on to the next run time
    assert datetime.fromisoformat(nxt.payload["expected_at"]) > t and nxt.payload["step"] == 0


async def test_failed_run_shows_reason_and_notifies_once(connected, client, fake_source):
    user, profile, headers = connected
    t = _t(0.6)
    await fake_source.add_run("r1", t, status="failed", finished_at=t + timedelta(minutes=5), current_step="documents",
                              error="selftest: r2: FAIL AccessDenied")
    await _make_check_due(profile.id, t, step=0)
    await _dispatch(user.id)

    card = (await client.get(API, headers=headers)).json()["card"]
    assert card["state"] == "failed"
    assert "failed at step Documents: selftest: r2: FAIL AccessDenied" in card["message"]
    runs = (await client.get(f"{API}/routine/runs", headers=headers)).json()
    assert runs[0]["error"] == "selftest: r2: FAIL AccessDenied"
    async with AsyncSessionLocal() as db:
        notes = list(await db.scalars(select(Notification).where(Notification.user_id == user.id,
                                                                 Notification.type == "routine_run")))
    assert len(notes) == 1
    # A failed run's saved jobs still sync.
    assert await _open(profile.id, "routine_sync") is not None


async def test_still_running_checks_again_then_stopped_at_three_hours(connected, client, fake_source):
    user, profile, headers = connected
    t = _t(1.2)
    await fake_source.add_run("r2", t, status="running", current_step="search")
    await _make_check_due(profile.id, t, step=1)
    await _dispatch(user.id)
    nxt = await _open(profile.id, "routine_check")
    assert (nxt.payload["expected_at"], nxt.payload["step"]) == (t.isoformat(), 2)
    assert (await _runs(user.id))[0].outcome == "running"

    await _make_check_due(profile.id, t, step=3)
    await _dispatch(user.id)
    run = (await _runs(user.id))[0]
    assert run.outcome == "stopped"
    card = (await client.get(API, headers=headers)).json()["card"]
    assert card["state"] == "stopped" and "stopped during Search" in card["message"]


async def test_routine_stale_marker_counts_as_stopped(connected, fake_source):
    user, profile, _ = connected
    t = _t(0.7)
    await fake_source.add_run("r3", t, status="failed", current_step="assess",
                              error="no completion recorded within 6 h (session ended or crashed)")
    await _make_check_due(profile.id, t, step=0)
    await _dispatch(user.id)
    assert (await _runs(user.id))[0].outcome == "stopped"


async def test_sources_failed_means_problems(connected, fake_source):
    user, profile, _ = connected
    t = _t(0.7)
    await fake_source.add_run("r4", t, status="succeeded", finished_at=t + timedelta(minutes=14),
                              sources_failed="Arbeitsagentur: connection timeout")
    await _make_check_due(profile.id, t, step=0)
    await _dispatch(user.id)
    assert (await _runs(user.id))[0].outcome == "problems"


async def test_no_run_by_three_hours_is_missed(connected, client, fake_source):
    user, profile, headers = connected
    t = _t(3.1)
    await _make_check_due(profile.id, t, step=3)
    await _dispatch(user.id)
    [run] = await _runs(user.id)
    assert (run.outcome, run.run_id, run.expected_at) == ("missed", None, t)
    card = (await client.get(API, headers=headers)).json()["card"]
    assert card["state"] == "didnt_run" and "didn't run at" in card["message"]


async def test_contract_v0_uses_jobs_table(connected, client, fake_source):
    user, profile, headers = connected
    await fake_source.drop_run_tracker()
    t = _t(0.7)
    await fake_source.add_job("a__b__c", last_seen_at=t + timedelta(minutes=10), docs_status="pending")
    await _make_check_due(profile.id, t, step=0)
    await _dispatch(user.id)
    sync = await _open(profile.id, "routine_sync")
    assert sync.due_at == t + timedelta(minutes=70)
    card = (await client.get(API, headers=headers)).json()["card"]
    assert card["state"] == "no_run_details"


async def test_connection_failures_pause_after_five(connected, client, fake_source):
    user, profile, headers = connected
    await fake_source.drop()
    for attempt in range(5):
        await _make_check_due(profile.id, _t(0.7), step=0)
        await _dispatch(user.id)
    async with AsyncSessionLocal() as db:
        conn = await db.scalar(select(RoutineConnection).where(RoutineConnection.user_id == user.id))
        notes = list(await db.scalars(select(Notification).where(Notification.user_id == user.id,
                                                                 Notification.type == "routine_connection")))
    assert (conn.status, conn.consecutive_failures) == ("paused", 5)
    assert len(notes) == 2  # "can't connect", then "paused"
    assert await _open(profile.id, "routine_check") is None
    card = (await client.get(API, headers=headers)).json()["card"]
    assert card["state"] == "cant_connect" and card["paused"] is True

    # Try again (re-save with the stored values) once it's fixed.
    await fake_source.create()
    r = await client.put(f"{API}/routine", json={"neon_url": fake_source.url}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["connection"]["status"] == "active"
    assert await _open(profile.id, "routine_check") is not None


async def test_bootstrap_queues_checks_for_connected_profiles(connected):
    user, profile, _ = connected
    async with AsyncSessionLocal() as db:
        await db.execute(update(EngineTask).where(EngineTask.profile_id == profile.id).values(status="cancelled"))
        await db.commit()
        await schedule.ensure_routine_tasks(profile.id, db)
    assert await _open(profile.id, "routine_check") is not None
