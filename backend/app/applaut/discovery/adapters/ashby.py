from datetime import datetime

import httpx

from app.applaut.discovery.base import JobListing, JobSourceAdapter
from app.applaut.discovery.location import matches_countries, matches_roles, resolve_country, resolve_remote_option

# Ashby's public posting API (the one its docs name for job boards).
BASE_URL = "https://api.ashbyhq.com/posting-api/job-board"


def parse_time(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def _country(address: dict | None) -> str | None:
    name = (((address or {}).get("postalAddress") or {}).get("addressCountry") or "").strip()
    return resolve_country(name) if name else None


class AshbyAdapter(JobSourceAdapter):
    source_name = "ashby"

    async def fetch_jobs(
        self,
        company_slug: str,
        target_countries: list[str],
        target_roles: list[str],
        skills: list[str] | tuple = (),
    ) -> list[JobListing]:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{BASE_URL}/{company_slug}")
                if resp.status_code != 200:
                    return []
                data = resp.json()
        except Exception:
            return []

        results = []
        for job in data.get("jobs") or []:
            title = job.get("title", "")
            if job.get("isListed") is False or not matches_roles(title, target_roles, skills):
                continue
            places = [(job.get("location"), job.get("address"))] + [
                (x.get("location"), x.get("address")) for x in job.get("secondaryLocations") or []]
            countries = [c for loc, addr in places if (c := _country(addr) or resolve_country(loc))]
            location_raw = " / ".join(loc for loc, _ in places if loc) or None
            country_code = next((c for c in countries if c in target_countries), countries[0] if countries else None)
            remote = bool(job.get("isRemote")) or job.get("workplaceType") == "Remote"
            if not matches_countries(country_code, target_countries):
                if not remote or country_code:  # remote somewhere else ("Remote - US") isn't a match
                    continue
            results.append(
                JobListing(
                    source=self.source_name,
                    external_id=job["id"],
                    title=title,
                    company_name=company_slug,
                    application_url=job.get("jobUrl") or f"https://jobs.ashbyhq.com/{company_slug}/{job['id']}",
                    location_raw=location_raw,
                    country_code=country_code,
                    description=job.get("descriptionPlain") or job.get("descriptionHtml"),
                    remote_option="remote" if remote else resolve_remote_option(location_raw),
                    posted_at=parse_time(job.get("publishedAt")),
                    raw_data={k: v for k, v in job.items() if k not in ("descriptionHtml", "descriptionPlain")},
                )
            )
        return results
