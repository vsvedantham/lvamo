from datetime import datetime, timezone

import httpx

from app.applaut.discovery.base import JobListing, JobSourceAdapter
from app.applaut.discovery.location import matches_countries, matches_roles, resolve_country, resolve_remote_option

BASE_URL = "https://api.lever.co/v0/postings"


class LeverAdapter(JobSourceAdapter):
    source_name = "lever"

    async def fetch_jobs(
        self,
        company_slug: str,
        target_countries: list[str],
        target_roles: list[str],
        skills: list[str] | tuple = (),
    ) -> list[JobListing]:
        url = f"{BASE_URL}/{company_slug}?mode=json&limit=100"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return []
                jobs = resp.json()
        except Exception:
            return []

        results = []
        for job in jobs:
            title = job.get("text", "")
            if not matches_roles(title, target_roles, skills):
                continue

            categories = job.get("categories", {})
            location_raw = categories.get("location") or categories.get("allLocations", [""])[0]
            country_code = resolve_country(location_raw)
            location_remote = resolve_remote_option(location_raw)
            remote_option = resolve_remote_option(location_raw, job.get("descriptionPlain"))

            if not matches_countries(country_code, target_countries):
                if location_remote != "remote":
                    continue
                if country_code and not matches_countries(country_code, target_countries):
                    continue

            results.append(
                JobListing(
                    source=self.source_name,
                    external_id=job["id"],
                    title=title,
                    company_name=company_slug,
                    application_url=job.get("hostedUrl", ""),
                    location_raw=location_raw,
                    country_code=country_code,
                    description=job.get("descriptionPlain") or job.get("description"),
                    remote_option=remote_option,
                    posted_at=(datetime.fromtimestamp(job["createdAt"] / 1000, tz=timezone.utc)
                               if isinstance(job.get("createdAt"), (int, float)) else None),
                    raw_data=job,
                )
            )
        return results
