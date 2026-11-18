import httpx

from app.applaut.discovery.adapters.ashby import parse_time
from app.applaut.discovery.base import JobListing, JobSourceAdapter
from app.applaut.discovery.location import matches_countries, matches_roles, resolve_country, resolve_remote_option

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseAdapter(JobSourceAdapter):
    source_name = "greenhouse"

    async def fetch_jobs(
        self,
        company_slug: str,
        target_countries: list[str],
        target_roles: list[str],
        skills: list[str] | tuple = (),
    ) -> list[JobListing]:
        url = f"{BASE_URL}/{company_slug}/jobs?content=true"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return []
                data = resp.json()
        except Exception:
            return []

        results = []
        for job in data.get("jobs", []):
            title = job.get("title", "")
            if not matches_roles(title, target_roles, skills):
                continue

            location_raw = job.get("location", {}).get("name")
            country_code = resolve_country(location_raw)
            # Use location-only for filtering (description is too noisy)
            location_remote = resolve_remote_option(location_raw)
            remote_option = resolve_remote_option(location_raw, job.get("content"))

            # Accept if country matches OR job is remote in location with no explicit non-target country
            if not matches_countries(country_code, target_countries):
                if location_remote != "remote":
                    continue
                # Remote with explicit non-target country (e.g. "Remote - US") → skip
                if country_code and not matches_countries(country_code, target_countries):
                    continue

            results.append(
                JobListing(
                    source=self.source_name,
                    external_id=str(job["id"]),
                    title=title,
                    company_name=company_slug,
                    application_url=job.get("absolute_url", ""),
                    location_raw=location_raw,
                    country_code=country_code,
                    description=job.get("content"),
                    remote_option=remote_option,
                    posted_at=parse_time(job.get("first_published") or job.get("updated_at")),
                    raw_data=job,
                )
            )
        return results
