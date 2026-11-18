"""Arbeitnow job board API: jobs in Germany, many in English, newest first,
300 a page with their descriptions. Free and public ("please do not abuse"):
read once a night, page by page, a pause between pages."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from app.applaut.discovery.base import JobListing
from app.applaut.discovery.location import matches_roles, resolve_country
from app.applaut.discovery.search.http import get_json

SOURCE = "arbeitnow"
API = "https://www.arbeitnow.com/api/job-board-api"
MAX_PAGES = 40
PAUSE = 1.0  # seconds between pages


def _listing(job: dict) -> JobListing | None:
    try:
        posted_at = datetime.fromtimestamp(int(job.get("created_at")), tz=timezone.utc)
    except (TypeError, ValueError):
        posted_at = None
    remote = job.get("remote") in (True, "true", "True", 1)
    location = (job.get("location") or "").strip() or None
    if not job.get("slug") or not job.get("title"):
        return None
    return JobListing(
        source=SOURCE, external_id=job["slug"], title=job["title"].strip(),
        company_name=(job.get("company_name") or "").strip() or "Unknown employer",
        application_url=job.get("url") or f"https://www.arbeitnow.com/view/{job['slug']}", location_raw=location,
        # A German job board: a city no country list knows is in Germany.
        country_code=resolve_country(location) or ("DE" if location and not remote else None),
        description=job.get("description"), remote_option="remote" if remote else "onsite", posted_at=posted_at,
        raw_data={k: job.get(k) for k in ("tags", "job_types", "remote") if k in job},
    )


async def search(target_countries: list[str], target_roles: list[str], skills: list[str] | tuple = (),
                 max_age_days: int = 60) -> list[JobListing]:
    if "DE" not in target_countries or not target_roles:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    out = []
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "Applaut job search"}) as client:
        for page in range(1, MAX_PAGES + 1):
            data = await get_json(client, API, params={"page": page})
            jobs = (data or {}).get("data") or [] if isinstance(data, dict) else []
            listings = [x for x in map(_listing, jobs) if x]
            out += [x for x in listings if matches_roles(x.title, target_roles, skills)
                    and (x.posted_at is None or x.posted_at >= cutoff)
                    and (x.country_code in target_countries or x.country_code is None)]
            if not jobs or all(x.posted_at and x.posted_at < cutoff for x in listings):
                break
            await asyncio.sleep(PAUSE)
    return out
