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

from app.applaut.ai.prompts import posting_text
from app.applaut.ai.queue import enqueue
from app.applaut.discovery.engine import expire_unseen, fetch_listings, store_listings
from app.applaut.discovery.location import dedupe_key, matches_roles, wanted_place
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
MIN_DESCRIPTION_CHARS = 100   # real postings run to 500+ characters; under 100 is empty or one line
# Expire closed jobs only after a normal fetch: one that found under this share
# of last night's postings (a source down) would close jobs that are still open.
EXPIRE_MIN_SHARE = 0.5


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


def skill_terms(master: dict | None) -> list[str]:
    """The user's skills as their master profile names them (rows first, then
    additional skills): searched for in job titles ("Databricks Developer")."""
    if not master:
        return []
    rows = [s for items in (master.get("skills") or {}).values() for s in items or []]
    return list(dict.fromkeys(s for s in rows + list(master.get("additional_skills") or [])
                              if isinstance(s, str) and len(s.strip()) >= 3))


def _has_description(opp: Opportunity) -> bool:
    return len(posting_text(opp.description or "")) >= MIN_DESCRIPTION_CHARS


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

        masters = {p.user_id: await db.scalar(select(MasterProfile.data).where(MasterProfile.user_id == p.user_id))
                   for p in profiles}
        skills = {p.user_id: skill_terms(masters[p.user_id]) for p in profiles}
        countries = sorted({c for p in profiles for c in (p.target_countries or [])})
        roles = sorted({r for p in profiles for r in (p.target_roles or [])})
        all_skills = list(dict.fromkeys(s for p in profiles for s in skills[p.user_id]))
        listings = await fetch_listings(countries, roles, all_skills) if countries and roles else []
        new = await store_listings(listings, db)
        last = await db.scalar(select(NightRun.jobs_found).where(NightRun.run_date < today)
                               .order_by(NightRun.run_date.desc()).limit(1))
        if listings and len(listings) >= EXPIRE_MIN_SHARE * (last or 0):
            closed = await expire_unseen(db)
        else:
            closed = 0
            logger.warning("Nightly %s: %d postings against %s last night; closed jobs not expired tonight",
                           today, len(listings), last)
        keys = list({(l.source, l.external_id) for l in listings})
        opps = list(await db.scalars(select(Opportunity).where(
            Opportunity.owner_user_id.is_(None), Opportunity.is_active == True,
            tuple_(Opportunity.source, Opportunity.external_id).in_(keys),
        ))) if keys else []

        stats: dict[str, dict] = {}
        for p in profiles:
            matched = [o for o in opps if wanted_place(o.country_code, o.remote_option, p.target_countries or [])
                       and matches_roles(o.title, p.target_roles or [], skills[p.user_id])]
            mine = [o for o in matched if _has_description(o)]  # the rest wait for a description
            assessed = list(await db.execute(
                select(Opportunity.id, Opportunity.company_name, Opportunity.title)
                .join(JobAssessment, JobAssessment.opportunity_id == Opportunity.id)
                .where(JobAssessment.profile_id == p.id, JobAssessment.engine == ENGINE)))
            seen = {row.id for row in assessed}
            same_job = {dedupe_key(row.company_name, row.title) for row in assessed}  # e.g. on two sites
            fresh = []
            for o in mine:
                key = dedupe_key(o.company_name, o.title)
                if o.id not in seen and key not in same_job:
                    fresh.append(o)
                    same_job.add(key)
            for o in fresh:
                db.add(JobAssessment(user_id=p.user_id, profile_id=p.id, opportunity_id=o.id, engine=ENGINE,
                                     status="raw", docs_status="not_needed", matched_skills=[], missing_skills=[],
                                     flags=[], raw={}))
            stats[str(p.user_id)] = {"matched": len(mine), "new": len(fresh),
                                     "no_description": len(matched) - len(mine)}
        await db.commit()
        night.discovery_done_at = datetime.now(timezone.utc)

        queued = 0
        for p in profiles:  # FIFO: users in opt-in order, all their scoring before the next user's
            master = masters[p.user_id]
            raws = list(await db.execute(
                select(JobAssessment, Opportunity).join(Opportunity, Opportunity.id == JobAssessment.opportunity_id)
                .where(JobAssessment.profile_id == p.id, JobAssessment.engine == ENGINE, JobAssessment.status == "raw",
                       Opportunity.is_active == True)  # noqa: E712  (a closed job isn't worth scoring)
            ))
            raws.sort(key=lambda r: -_pre_score(r[1], master, p.skills or []))
            n = 0
            for a, _ in (raws[:settings.applaut_ai_score_cap] if master else []):  # no master profile: they wait
                n += await enqueue(db, "score_job", a, night.id)
            stats[str(p.user_id)].update(queued=n, waiting=len(raws) - n)
            queued += n

        night.users, night.jobs_found, night.jobs_queued = len(profiles), len(listings), queued
        night.stats = {**stats, "_pool": {"postings": len(listings), "new": new, "closed": closed,
                                          "by_source": _by_source(listings)}}
        await db.commit()
        logger.info("Nightly %s: %d users, %d postings (%d new, %d closed), %d jobs queued for scoring",
                    today, len(profiles), len(listings), new, closed, queued)
        return night


def _by_source(listings) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in listings:
        out[x.source] = out.get(x.source, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


async def run_nightly_task(task: EngineTask) -> None:
    await run_nightly()


async def after_nightly(task: EngineTask, db: AsyncSession) -> None:
    await ensure_nightly_task(db)
