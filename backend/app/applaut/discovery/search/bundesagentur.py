"""Bundesagentur für Arbeit Jobsuche API: Germany's largest job database
(every employer and agency posting, all of Germany), searched by keyword.

Search: GET /pc/v6/jobs (the app's public key; v4 now answers 403). The
results carry no description: `describe` reads it from /pc/v4/jobdetails
(v6 jobdetails answers 403), only for postings Applaut stores new.
"""
from __future__ import annotations

import asyncio
import base64
from datetime import date, datetime, timezone

import httpx

from app.applaut.core.role_synonyms import expand_role
from app.applaut.discovery.base import JobListing
from app.applaut.discovery.location import GENERIC_SKILLS, matches_roles, resolve_country
from app.applaut.discovery.search.http import get_json

SOURCE = "bundesagentur"
API = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
HEADERS = {"X-API-Key": "jobboerse-jobsuche", "User-Agent": "Applaut job search"}  # the API's public app key
PAGE_SIZE = 100
MAX_PAGES = 5               # per search term: 500 postings
MAX_SKILL_TERMS = 8         # skill-led searches ("Databricks") on top of the role titles
CONCURRENCY = 3


def search_terms(roles: list[str], skills: list[str] | tuple) -> list[str]:
    terms = []
    for role in roles:
        terms += [role.lower(), *expand_role(role)]
    terms += [s for s in skills if len(s) >= 4 and s.lower() not in GENERIC_SKILLS][:MAX_SKILL_TERMS]
    return list(dict.fromkeys(t.lower() for t in terms))


def job_page(ref: str) -> str:
    return f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}"


def _listing(job: dict) -> JobListing | None:
    ref = job.get("referenznummer")
    if not ref:
        return None
    places = [p.get("adresse") or {} for p in job.get("stellenlokationen") or []]
    location = ", ".join(dict.fromkeys(p.get("ort") for p in places if p.get("ort"))) or None
    lands = {(p.get("land") or "").upper() for p in places}
    country = "DE" if not lands or lands <= {"DEUTSCHLAND", ""} else resolve_country(" ".join(lands).lower())
    posted = job.get("datumErsteVeroeffentlichung")
    try:
        posted_at = datetime.combine(date.fromisoformat(posted), datetime.min.time(), timezone.utc) if posted else None
    except ValueError:
        posted_at = None
    return JobListing(
        source=SOURCE, external_id=ref, title=(job.get("stellenangebotsTitel") or job.get("titel") or "").strip(),
        company_name=(job.get("firma") or "").strip() or "Unknown employer", application_url=job_page(ref),
        location_raw=location, country_code=country, description=None, employment_type="full_time",
        remote_option="hybrid" if job.get("homeofficemoeglich") else "onsite", posted_at=posted_at,
        raw_data={k: job.get(k) for k in ("externeURL", "hauptberuf", "arbeitszeitVollzeit", "homeofficemoeglich",
                                          "istArbeitnehmerUeberlassung", "istPrivateArbeitsvermittlung")
                  if k in job},
    )


async def search(target_countries: list[str], target_roles: list[str], skills: list[str] | tuple = (),
                 max_age_days: int = 60) -> list[JobListing]:
    """Full-time postings in Germany from the last `max_age_days` whose title
    matches. Nothing when Germany isn't a target country."""
    if "DE" not in target_countries or not target_roles:
        return []
    found: dict[str, JobListing] = {}
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def one(client: httpx.AsyncClient, term: str) -> None:
        for page in range(1, MAX_PAGES + 1):
            async with semaphore:
                data = await get_json(client, f"{API}/pc/v6/jobs", params={
                    "was": term, "veroeffentlichtseit": max_age_days, "size": PAGE_SIZE, "page": page,
                    "arbeitszeit": "vz", "angebotsart": 1})
            jobs = (data or {}).get("ergebnisliste") or [] if isinstance(data, dict) else []
            for job in jobs:
                listing = _listing(job)
                if (listing and listing.external_id not in found and listing.country_code in target_countries
                        and matches_roles(listing.title, target_roles, skills)):
                    found[listing.external_id] = listing
            if len(jobs) < PAGE_SIZE:
                return

    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        await asyncio.gather(*(one(client, t) for t in search_terms(target_roles, skills)))
    return list(found.values())


async def describe(client: httpx.AsyncClient, listing: JobListing) -> str | None:
    ref = base64.b64encode(listing.external_id.encode()).decode()
    data = await get_json(client, f"{API}/pc/v4/jobdetails/{ref}", headers=HEADERS)
    text = (data or {}).get("stellenangebotsBeschreibung") if isinstance(data, dict) else None
    return text.strip() if text else None
