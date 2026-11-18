"""Job discovery: company boards plus Germany-wide job-board searches, into
Applaut's shared job pool.

One fetch keeps postings that match the target countries and roles (or the
user's skills in a job title), drops ones older than MAX_AGE_DAYS, and
merges the same job posted per city or on several sites. Storing records
when each job was last seen; `expire_unseen` closes jobs gone from their
board for EXPIRE_AFTER, so closed postings leave the list.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.discovery.base import JobListing
from app.applaut.discovery.companies import BOARD_NAMES, COMPANY_BOARDS
from app.applaut.discovery.location import dedupe_key
from app.applaut.discovery.search import arbeitnow, bundesagentur, personio_page
from app.applaut.models.opportunity import Opportunity
from app.applaut.models.profile import Profile

logger = logging.getLogger(__name__)

# Caps how many company-board fetches run concurrently. Several adapters
# share one host across every company on that platform (e.g. all Greenhouse
# boards hit boards-api.greenhouse.io), so an unbounded gather over a large
# COMPANY_BOARDS list risks looking like a burst/abuse pattern to that host.
DISCOVERY_CONCURRENCY = int(os.environ.get("DISCOVERY_CONCURRENCY", "20"))
MAX_AGE_DAYS = 60                   # an older posting is stale (or "evergreen") and isn't fetched
EXPIRE_AFTER = timedelta(days=3)    # unseen this long (three nightly runs): closed
DESCRIBE_CONCURRENCY = 4
# Job-board searches: (source, search function). They cover all of Germany.
SEARCHES = ((bundesagentur.SOURCE, bundesagentur.search), (arbeitnow.SOURCE, arbeitnow.search))
# Where a posting's description comes from when the listing has none.
DESCRIBERS = {bundesagentur.SOURCE: bundesagentur.describe, "personio": personio_page.describe}
# The same job found twice: the employer's own board wins, then the job boards.
_RANK = {arbeitnow.SOURCE: 1, bundesagentur.SOURCE: 2}


async def fetch_listings(target_countries: list[str], target_roles: list[str],
                         skills: list[str] | tuple = ()) -> list[JobListing]:
    """Every company board and job-board search once, keeping postings that
    match the countries and roles (or a skill in the title, see
    location.matches_roles), newer than MAX_AGE_DAYS, one per job. Source
    errors are logged and skipped."""
    semaphore = asyncio.Semaphore(DISCOVERY_CONCURRENCY)

    async def _fetch(adapter, slug):
        async with semaphore:
            found = await adapter.fetch_jobs(slug, target_countries, target_roles, skills)
        name = BOARD_NAMES.get((adapter.source_name, slug.lower()))
        for listing in found:
            listing.company_name = name or listing.company_name
        return found

    tasks = [_fetch(adapter, slug) for adapter, slug in COMPANY_BOARDS]
    tasks += [search(target_countries, target_roles, skills, max_age_days=MAX_AGE_DAYS) for _, search in SEARCHES]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    listings = []
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Discovery source error: %r", result)
            continue
        listings.extend(result)
    return prepare(listings)


def prepare(listings: list[JobListing], now: datetime | None = None) -> list[JobListing]:
    """Drop postings older than MAX_AGE_DAYS and keep one listing per job:
    the same company and title (gender marks aside) is one job, wherever and
    however often it is posted. The kept one lists every place."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=MAX_AGE_DAYS)
    fresh = [x for x in listings if x.posted_at is None or x.posted_at >= cutoff]
    groups: dict[tuple[str, str], list[JobListing]] = {}
    for x in fresh:
        groups.setdefault(dedupe_key(x.company_name, x.title), []).append(x)
    out = []
    for group in groups.values():
        group.sort(key=lambda x: (_RANK.get(x.source, 0), x.source, x.external_id))  # stable: same pick every night
        keep = group[0]
        places = list(dict.fromkeys(p.strip() for x in group for p in (x.location_raw or "").split(" / ") if p.strip()))
        if len(group) > 1:
            keep.location_raw = " / ".join(places)[:500] or keep.location_raw
            keep.raw_data = {**(keep.raw_data or {}), "also_posted": [
                {"source": x.source, "external_id": x.external_id, "url": x.application_url} for x in group[1:]]}
        out.append(keep)
    return out


async def run_discovery_for_profile(profile: Profile, db: AsyncSession) -> int:
    """
    Runs discovery for all company boards, filters against the profile's
    target countries and roles, and upserts new opportunities.
    Returns the count of newly inserted opportunities.
    """
    target_countries = profile.target_countries or []
    target_roles = profile.target_roles or []

    if not target_countries or not target_roles:
        return 0

    listings = await fetch_listings(target_countries, target_roles)
    return await store_listings(listings, db)


async def describe_missing(listings: list[JobListing]) -> None:
    """Fill descriptions the listing lacks (job boards that list without one,
    Personio feeds that leave it empty), a few at a time."""
    todo = [x for x in listings if not (x.description or "").strip() and x.source in DESCRIBERS]
    if not todo:
        return
    semaphore = asyncio.Semaphore(DESCRIBE_CONCURRENCY)

    async def one(client: httpx.AsyncClient, listing: JobListing) -> None:
        async with semaphore:
            try:
                listing.description = await DESCRIBERS[listing.source](client, listing)
            except Exception as exc:  # one posting's page never stops the run
                logger.warning("Description for %s %s failed: %r", listing.source, listing.external_id, exc)

    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "Applaut job search"}) as client:
        await asyncio.gather(*(one(client, x) for x in todo))


async def store_listings(listings: list[JobListing], db: AsyncSession) -> int:
    """Insert postings not yet in the shared pool (with their descriptions) and
    mark every listed one as seen now (a closed one seen again reopens).
    Returns how many were new."""
    if not listings:
        return 0
    now = datetime.now(timezone.utc)
    stored = {(o.source, o.external_id): o for o in await db.scalars(
        select(Opportunity).where(
            Opportunity.owner_user_id.is_(None),  # the shared pool only
            Opportunity.source.in_({x.source for x in listings}),
            Opportunity.external_id.in_({x.external_id for x in listings}),
        )
    )}
    for opp in stored.values():
        opp.last_seen_at, opp.is_active = now, True

    new = list({(x.source, x.external_id): x for x in listings if (x.source, x.external_id) not in stored}.values())
    await describe_missing(new)
    for listing in new:
        db.add(Opportunity(
            source=listing.source,
            external_id=listing.external_id,
            title=listing.title[:500],
            company_name=listing.company_name[:500],
            application_url=listing.application_url,
            location_raw=(listing.location_raw or "")[:500] or None,
            country_code=listing.country_code,
            description=listing.description,
            remote_option=listing.remote_option,
            posted_at=listing.posted_at or now,
            raw_data=listing.raw_data,
            is_active=True,
            last_seen_at=now,
        ))
    await db.commit()
    return len(new)


async def expire_unseen(db: AsyncSession, now: datetime | None = None, sources: set[str] | None = None) -> int:
    """Close shared-pool jobs no source has listed for EXPIRE_AFTER: the
    posting is gone (or now older than MAX_AGE_DAYS). `sources`: only jobs
    from these. Returns how many."""
    cutoff = (now or datetime.now(timezone.utc)) - EXPIRE_AFTER
    query = (update(Opportunity)
             .where(Opportunity.owner_user_id.is_(None), Opportunity.is_active == True,  # noqa: E712
                    Opportunity.last_seen_at < cutoff)
             .values(is_active=False))
    if sources is not None:
        query = query.where(Opportunity.source.in_(sources))
    result = await db.execute(query)
    await db.commit()
    return result.rowcount or 0
