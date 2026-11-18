from datetime import datetime, timezone

import httpx

from app.applaut.discovery.base import JobListing, JobSourceAdapter
from app.applaut.discovery.location import matches_countries, matches_roles, resolve_remote_option

BASE_URL = "https://apply.workable.com/api/v3/accounts"
MAX_PAGES = 3  # bounds worst-case latency for any single large company

WORKPLACE_TO_REMOTE_OPTION = {
    "remote": "remote",
    "hybrid": "hybrid",
    "on_site": "onsite",
}

TYPE_TO_EMPLOYMENT_TYPE = {
    "full": "full_time",
    "part": "part_time",
    "contract": "contract",
    "temporary": "contract",
    "internship": "internship",
}


class WorkableAdapter(JobSourceAdapter):
    source_name = "workable"

    async def fetch_jobs(
        self,
        company_slug: str,
        target_countries: list[str],
        target_roles: list[str],
        skills: list[str] | tuple = (),
    ) -> list[JobListing]:
        url = f"{BASE_URL}/{company_slug}/jobs"
        all_jobs: list[dict] = []
        body: dict = {}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                for _ in range(MAX_PAGES):
                    resp = await client.post(url, json=body)
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    all_jobs.extend(data.get("results", []))
                    next_page = data.get("nextPage")
                    if not next_page:
                        break
                    body = {"token": next_page}
        except Exception:
            return []

        results = []
        for job in all_jobs:
            title = job.get("title", "")
            if not matches_roles(title, target_roles, skills):
                continue

            location = job.get("location") or {}
            location_parts = [location.get("city"), location.get("region"), location.get("country")]
            location_raw = ", ".join(p for p in location_parts if p) or None

            workplace = job.get("workplace")
            remote_option = WORKPLACE_TO_REMOTE_OPTION.get(workplace)
            if not remote_option:
                remote_option = "remote" if job.get("remote") else resolve_remote_option(location_raw)

            country_code = location.get("countryCode")
            country_code = country_code.upper() if country_code else None

            if not matches_countries(country_code, target_countries):
                if remote_option != "remote":
                    continue
                if country_code and not matches_countries(country_code, target_countries):
                    continue

            posted_at = None
            published = job.get("published")
            if published:
                try:
                    posted_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
                except ValueError:
                    posted_at = None

            shortcode = job.get("shortcode", "")
            results.append(
                JobListing(
                    source=self.source_name,
                    external_id=str(job.get("id", shortcode)),
                    title=title,
                    company_name=company_slug,
                    application_url=f"https://apply.workable.com/{company_slug}/j/{shortcode}/",
                    location_raw=location_raw,
                    country_code=country_code,
                    description=None,
                    employment_type=TYPE_TO_EMPLOYMENT_TYPE.get(job.get("type", "")),
                    remote_option=remote_option,
                    posted_at=posted_at or datetime.now(timezone.utc),
                    raw_data=job,
                )
            )
        return results
