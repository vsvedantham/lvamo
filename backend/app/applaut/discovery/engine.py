import asyncio
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.discovery.companies import COMPANY_BOARDS
from app.applaut.models.opportunity import Opportunity
from app.applaut.models.profile import Profile

logger = logging.getLogger(__name__)

# Caps how many company-board fetches run concurrently. Several adapters
# share one host across every company on that platform (e.g. all Greenhouse
# boards hit boards-api.greenhouse.io), so an unbounded gather over a large
# COMPANY_BOARDS list risks looking like a burst/abuse pattern to that host.
DISCOVERY_CONCURRENCY = int(os.environ.get("DISCOVERY_CONCURRENCY", "20"))


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

    # Fetch from all boards concurrently, capped so we don't hammer any
    # single ATS host when COMPANY_BOARDS is large.
    semaphore = asyncio.Semaphore(DISCOVERY_CONCURRENCY)

    async def _fetch(adapter, slug):
        async with semaphore:
            return await adapter.fetch_jobs(slug, target_countries, target_roles)

    tasks = [_fetch(adapter, slug) for adapter, slug in COMPANY_BOARDS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    listings = []
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Discovery adapter error: %s", result)
            continue
        listings.extend(result)

    if not listings:
        return 0

    # Load existing external_ids to deduplicate
    existing = set(
        await db.scalars(
            select(Opportunity.external_id).where(
                Opportunity.owner_user_id.is_(None),  # Basic's shared pool only
                Opportunity.source.in_([l.source for l in listings]),
                Opportunity.external_id.in_([l.external_id for l in listings]),
            )
        )
    )

    new_count = 0
    for listing in listings:
        if listing.external_id in existing:
            continue
        opp = Opportunity(
            source=listing.source,
            external_id=listing.external_id,
            title=listing.title,
            company_name=listing.company_name,
            application_url=listing.application_url,
            location_raw=listing.location_raw,
            country_code=listing.country_code,
            description=listing.description,
            remote_option=listing.remote_option,
            posted_at=listing.posted_at or datetime.now(timezone.utc),
            raw_data=listing.raw_data,
            is_active=True,
        )
        db.add(opp)
        existing.add(listing.external_id)
        new_count += 1

    if new_count:
        await db.commit()

    return new_count
