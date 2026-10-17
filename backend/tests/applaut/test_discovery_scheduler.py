"""Scheduled discovery runs once per profile per interval, however many
uvicorn workers (each with its own scheduler) fire the job."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, text

from app.applaut.discovery import scheduler
from app.applaut.models.profile import Profile
from app.applaut.models.user import User
from app.db.session import AsyncSessionLocal


@pytest.fixture
async def profile_id():
    async with AsyncSessionLocal() as db:
        user = User(email=f"scheduler-test-{uuid.uuid4().hex}@test.invalid", name="Scheduler Test")
        db.add(user)
        await db.flush()
        profile = Profile(
            user_id=user.id,
            display_name="Scheduler Test",
            target_roles=["Engineer"],
            target_countries=["US"],
            discovery_enabled=True,
            discovery_frequency_hours=6,
        )
        db.add(profile)
        await db.commit()
        user_id, pid = user.id, str(profile.id)
    yield pid
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.id == user_id))  # profile cascades
        await db.commit()


@pytest.fixture
def discovery_calls(monkeypatch):
    """Replaces the real discovery (network) and scoring with stubs; returns
    the list of profile ids discovery was run for."""
    calls = []

    async def fake_discovery(profile, db):
        calls.append(str(profile.id))
        await asyncio.sleep(0.3)  # long enough for a second worker to collide
        return 0

    async def fake_scoring(user, db, mode="rule_based"):
        return {"scored": 0, "good_matches": 0, "near_misses": 0}

    monkeypatch.setattr(scheduler, "run_discovery_for_profile", fake_discovery)
    monkeypatch.setattr("app.applaut.services.scoring.run_scoring", fake_scoring)
    return calls


async def _set_last_discovery(profile_id, when):
    async with AsyncSessionLocal() as db:
        profile = await db.get(Profile, profile_id)
        profile.last_discovery_at = when
        await db.commit()


async def _last_discovery(profile_id):
    async with AsyncSessionLocal() as db:
        return (await db.get(Profile, profile_id)).last_discovery_at


async def test_two_workers_firing_together_run_once(profile_id, discovery_calls):
    await asyncio.gather(scheduler._run_profile(profile_id), scheduler._run_profile(profile_id))
    assert discovery_calls == [profile_id]
    assert await _last_discovery(profile_id) is not None


async def test_second_worker_firing_after_first_finished_skips(profile_id, discovery_calls):
    await scheduler._run_profile(profile_id)
    await scheduler._run_profile(profile_id)
    assert discovery_calls == [profile_id]


async def test_skips_while_lock_held_elsewhere(profile_id, discovery_calls):
    async with AsyncSessionLocal() as other_worker:
        await other_worker.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"applaut.discovery:{profile_id}"},
        )
        await scheduler._run_profile(profile_id)
    assert discovery_calls == []


async def test_runs_again_once_interval_has_mostly_passed(profile_id, discovery_calls):
    # 6h interval: 5h ago is within 90% (5.4h) -> skip; 5.5h ago -> due.
    now = datetime.now(timezone.utc)
    await _set_last_discovery(profile_id, now - timedelta(hours=5))
    await scheduler._run_profile(profile_id)
    assert discovery_calls == []

    await _set_last_discovery(profile_id, now - timedelta(hours=5, minutes=30))
    await scheduler._run_profile(profile_id)
    assert discovery_calls == [profile_id]
    assert await _last_discovery(profile_id) > now
