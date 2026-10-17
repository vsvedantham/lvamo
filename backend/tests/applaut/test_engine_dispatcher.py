"""The database-driven schedule: one open discovery task per eligible
profile, each due task runs in exactly one worker, failures retry with
backoff, and a task orphaned by a dead worker is picked up again."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.applaut.discovery import scheduler
from app.applaut.models.engine_task import EngineTask
from app.applaut.models.profile import Profile
from app.db.session import AsyncSessionLocal


async def _tasks(profile_id) -> list[EngineTask]:
    async with AsyncSessionLocal() as db:
        return list(await db.scalars(
            select(EngineTask).where(EngineTask.profile_id == profile_id).order_by(EngineTask.created_at)
        ))


async def _set_profile(profile_id, **fields) -> None:
    async with AsyncSessionLocal() as db:
        profile = await db.get(Profile, profile_id)
        for k, v in fields.items():
            setattr(profile, k, v)
        await db.commit()
        await scheduler.sync_discovery_task(profile_id, db)


@pytest.fixture
def discovery_runs(monkeypatch):
    """Stub out the network discovery and scoring; returns the profile ids run."""
    runs = []

    async def fake_discovery(profile, db):
        runs.append(profile.id)
        await asyncio.sleep(0.2)
        return 0

    async def fake_scoring(user, db, mode="rule_based"):
        return {"scored": 0, "good_matches": 0, "near_misses": 0}

    monkeypatch.setattr(scheduler, "run_discovery_for_profile", fake_discovery)
    monkeypatch.setattr("app.applaut.services.scoring.run_scoring", fake_scoring)
    return runs


async def test_one_open_task_while_enabled_none_when_disabled(make_user):
    _, profile, _ = await make_user(discovery_frequency_hours=12)

    await _set_profile(profile.id, discovery_enabled=True)
    await _set_profile(profile.id, discovery_enabled=True)  # idempotent
    tasks = await _tasks(profile.id)
    assert [(t.kind, t.status) for t in tasks] == [("basic_discovery", "pending")]
    assert tasks[0].payload == {"interval_hours": 12}

    await _set_profile(profile.id, discovery_enabled=False)
    assert [t.status for t in await _tasks(profile.id)] == ["cancelled"]


async def test_switching_engine_away_from_basic_cancels_discovery(make_user):
    _, profile, _ = await make_user()
    await _set_profile(profile.id, discovery_enabled=True)
    await _set_profile(profile.id, job_engine="own_routine")
    assert [t.status for t in await _tasks(profile.id)] == ["cancelled"]


async def test_changing_frequency_moves_the_next_run(make_user):
    _, profile, _ = await make_user(discovery_frequency_hours=24)
    last = datetime.now(timezone.utc) - timedelta(hours=1)
    await _set_profile(profile.id, discovery_enabled=True, last_discovery_at=last)
    assert abs((await _tasks(profile.id))[0].due_at - (last + timedelta(hours=24))) < timedelta(seconds=1)

    await _set_profile(profile.id, discovery_frequency_hours=6)
    task = (await _tasks(profile.id))[0]
    assert abs(task.due_at - (last + timedelta(hours=6))) < timedelta(seconds=1)
    assert task.payload == {"interval_hours": 6}


async def test_two_workers_dispatching_together_run_a_due_task_once(make_user, discovery_runs):
    _, profile, _ = await make_user(discovery_frequency_hours=6)
    await _set_profile(profile.id, discovery_enabled=True)  # never run -> due now

    await asyncio.gather(scheduler.dispatch_due_tasks(), scheduler.dispatch_due_tasks())

    assert discovery_runs == [profile.id]
    done, nxt = await _tasks(profile.id)
    assert (done.status, done.attempts) == ("done", 1)
    assert nxt.status == "pending"
    assert nxt.due_at > datetime.now(timezone.utc) + timedelta(hours=5, minutes=59)


async def test_a_failing_task_retries_with_backoff_then_fails(make_user, monkeypatch):
    _, profile, _ = await make_user()
    await _set_profile(profile.id, discovery_enabled=True)

    async def boom(task):
        raise RuntimeError("ATS host down")

    monkeypatch.setitem(scheduler._HANDLERS, scheduler.KIND_BASIC_DISCOVERY, boom)

    for attempt, delay in enumerate(scheduler.RETRY_DELAYS, start=1):
        assert await scheduler.dispatch_due_tasks() == 1
        (task,) = await _tasks(profile.id)
        assert (task.status, task.attempts) == ("pending", attempt)
        assert task.last_error == "RuntimeError: ATS host down"
        assert task.due_at > datetime.now(timezone.utc) + delay - timedelta(seconds=5)
        async with AsyncSessionLocal() as db:  # fast-forward to the retry
            (await db.get(EngineTask, task.id)).due_at = datetime.now(timezone.utc)
            await db.commit()

    assert await scheduler.dispatch_due_tasks() == 1
    failed, nxt = await _tasks(profile.id)
    assert failed.status == "failed"
    # The next regular run is still queued, one interval out.
    assert nxt.status == "pending"
    assert nxt.due_at > datetime.now(timezone.utc) + timedelta(hours=23)


async def test_a_task_left_running_by_a_dead_worker_runs_again(make_user, discovery_runs):
    _, profile, _ = await make_user()
    await _set_profile(profile.id, discovery_enabled=True)
    async with AsyncSessionLocal() as db:
        task = (await db.scalars(select(EngineTask).where(EngineTask.profile_id == profile.id))).one()
        task.status, task.attempts = "running", 1
        task.started_at = datetime.now(timezone.utc) - scheduler.STALE_RUNNING_AFTER - timedelta(minutes=1)
        await db.commit()

    assert await scheduler.dispatch_due_tasks() == 1
    assert discovery_runs == [profile.id]
    assert [t.status for t in await _tasks(profile.id)] == ["done", "pending"]
