import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, text

from app.db.session import AsyncSessionLocal
from app.applaut.discovery.engine import run_discovery_for_profile
from app.applaut.models.profile import Profile

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

_JOB_PREFIX = "discovery_"

# Production runs several uvicorn workers, and each one has its own scheduler
# holding its own job per profile. Two guards keep a profile's discovery to one
# run per interval: a Postgres advisory lock stops two workers running it at
# the same time, and a run is skipped if the last one finished within this
# fraction of the interval (a second worker whose timer fires later).
_RECENT_RUN_FRACTION = 0.9


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


def schedule_profile(profile: Profile) -> None:
    job_id = f"{_JOB_PREFIX}{profile.id}"
    if not profile.is_active or not profile.discovery_enabled:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info("Removed discovery job for profile %s", profile.id)
        return

    hours = max(1, profile.discovery_frequency_hours or 24)
    scheduler.add_job(
        _run_profile,
        trigger="interval",
        hours=hours,
        args=[str(profile.id)],
        id=job_id,
        replace_existing=True,
    )
    logger.info("Scheduled discovery for profile %s every %dh", profile.id, hours)


def unschedule_profile(profile_id: str) -> None:
    job_id = f"{_JOB_PREFIX}{profile_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


def get_scheduler_status() -> list[dict]:
    jobs = [j for j in scheduler.get_jobs() if j.id.startswith(_JOB_PREFIX)]
    return [
        {
            "profile_id": j.id.removeprefix(_JOB_PREFIX),
            "next_run_at": j.next_run_time.isoformat() if j.next_run_time else None,
            "interval_hours": int(j.trigger.interval.total_seconds() // 3600),
        }
        for j in jobs
    ]


async def _load_all_profiles() -> None:
    async with AsyncSessionLocal() as db:
        profiles = await db.scalars(
            select(Profile).where(Profile.is_active == True)
        )
        for profile in profiles:
            schedule_profile(profile)


def start_scheduler() -> None:
    scheduler.start()
    # Defer profile loading until the event loop is running
    scheduler.add_job(
        _load_all_profiles,
        trigger="date",
        id="bootstrap_profiles",
        replace_existing=True,
    )
    logger.info("Discovery scheduler started")


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
