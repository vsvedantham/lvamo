"""22:00 (Europe/Berlin): Stage 1 of the nightly flow (design §2), all code.

Fetch every company board once for all Applaut AI users together, keep each
user's matches as `raw` assessments, then queue their scoring in FIFO order:
users in the order they turned Applaut AI on, each user's raw jobs best
pre-score first, at most `applaut_ai_score_cap` per user per night (the rest
wait for the next night). Scoring queues each ≥80 job's documents itself.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.ai.queue import enqueue
from app.applaut.discovery.engine import fetch_listings, store_listings
from app.applaut.discovery.location import matches_countries, matches_roles
from app.applaut.documents.tailor import job_skills
from app.applaut.models.engine_task import EngineTask
from app.applaut.models.job_assessment import JobAssessment
from app.applaut.models.master_profile import MasterProfile
from app.applaut.models.ai_queue import NightRun
from app.applaut.models.opportunity import Opportunity
from app.applaut.models.profile import Profile
from app.config import settings
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
BERLIN = ZoneInfo("Europe/Berlin")
KIND_NIGHTLY = "applaut_ai_nightly"
ENGINE = "applaut_ai"


def next_run_at(now: datetime) -> datetime:
    """The next 22:00 in Berlin after `now` (UTC), DST-aware."""
    local = now.astimezone(BERLIN)
    run = datetime.combine(local.date(), time(settings.applaut_nightly_hour), tzinfo=BERLIN)
    if run <= local:
        run = datetime.combine(local.date() + timedelta(days=1), time(settings.applaut_nightly_hour), tzinfo=BERLIN)
    return run.astimezone(timezone.utc)


async def ensure_nightly_task(db: AsyncSession) -> None:
    """Exactly one open nightly task (idempotent; every API worker calls it at startup)."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('applaut.ai.nightly', 0))"))
    open_task = await db.scalar(select(EngineTask.id).where(
        EngineTask.kind == KIND_NIGHTLY, EngineTask.status.in_(("pending", "running"))))
    if open_task is None:
        db.add(EngineTask(kind=KIND_NIGHTLY, due_at=next_run_at(datetime.now(timezone.utc)), status="pending"))
    await db.commit()


async def _profiles(db: AsyncSession) -> list[Profile]:
    return list(await db.scalars(
        select(Profile).where(Profile.is_active == True, Profile.job_engine == ENGINE)
        .order_by(Profile.job_engine_changed_at.asc().nulls_last(), Profile.created_at)
    ))


def _pre_score(opp: Opportunity, master: dict | None, skills: list[str]) -> int:
    """Cheap code ranking of raw jobs: how many of the user's skills the posting names."""
    text_ = f"{opp.title}\n{opp.description or ''}"
    if master:
        return len(job_skills(master, text_))
    low = text_.lower()
    return sum(1 for s in skills if s.lower() in low)


async def run_nightly(today: date | None = None) -> NightRun | None:
    today = today or datetime.now(BERLIN).date()
    async with AsyncSessionLocal() as db:
        profiles = await _profiles(db)
        if not profiles:
            logger.info("Nightly: no Applaut AI users")
            return None
        night = await db.scalar(select(NightRun).where(NightRun.run_date == today))
        if night is None:
            night = NightRun(run_date=today)
            db.add(night)
            await db.commit()

        countries = sorted({c for p in profiles for c in (p.target_countries or [])})
        roles = sorted({r for p in profiles for r in (p.target_roles or [])})
        listings = await fetch_listings(countries, roles) if countries and roles else []
        new = await store_listings(listings, db)
        keys = list({(l.source, l.external_id) for l in listings})
        opps = list(await db.scalars(select(Opportunity).where(
            Opportunity.owner_user_id.is_(None), Opportunity.is_active == True,
            tuple_(Opportunity.source, Opportunity.external_id).in_(keys),
        ))) if keys else []

        stats: dict[str, dict] = {}
        for p in profiles:
            mine = [o for o in opps if matches_countries(o.country_code, p.target_countries or [])
                    and matches_roles(o.title, p.target_roles or [])]
            seen = set(await db.scalars(select(JobAssessment.opportunity_id).where(
                JobAssessment.profile_id == p.id, JobAssessment.engine == ENGINE)))
            fresh = [o for o in mine if o.id not in seen]
            for o in fresh:
                db.add(JobAssessment(user_id=p.user_id, profile_id=p.id, opportunity_id=o.id, engine=ENGINE,
                                     status="raw", docs_status="not_needed", matched_skills=[], missing_skills=[],
                                     flags=[], raw={}))
            stats[str(p.user_id)] = {"matched": len(mine), "new": len(fresh)}
        await db.commit()
        night.discovery_done_at = datetime.now(timezone.utc)

        queued = 0
        for p in profiles:  # FIFO: users in opt-in order, all their scoring before the next user's
            master = await db.scalar(select(MasterProfile.data).where(MasterProfile.user_id == p.user_id))
            raws = list(await db.execute(
                select(JobAssessment, Opportunity).join(Opportunity, Opportunity.id == JobAssessment.opportunity_id)
                .where(JobAssessment.profile_id == p.id, JobAssessment.engine == ENGINE, JobAssessment.status == "raw")
            ))
            raws.sort(key=lambda r: -_pre_score(r[1], master, p.skills or []))
            n = 0
            for a, _ in raws[:settings.applaut_ai_score_cap]:
                n += await enqueue(db, "score_job", a, night.id)
            stats[str(p.user_id)].update(queued=n, waiting=max(0, len(raws) - settings.applaut_ai_score_cap))
            queued += n

        night.users, night.jobs_found, night.jobs_queued, night.stats = len(profiles), len(listings), queued, stats
        await db.commit()
        logger.info("Nightly %s: %d users, %d postings (%d new), %d jobs queued for scoring",
                    today, len(profiles), len(listings), new, queued)
        return night


async def run_nightly_task(task: EngineTask) -> None:
    await run_nightly()


async def after_nightly(task: EngineTask, db: AsyncSession) -> None:
    await ensure_nightly_task(db)
