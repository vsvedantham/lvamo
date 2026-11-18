import xml.etree.ElementTree as ET

import httpx

from app.applaut.discovery.adapters.ashby import parse_time
from app.applaut.discovery.base import JobListing, JobSourceAdapter
from app.applaut.discovery.location import matches_countries, matches_roles, resolve_country, resolve_remote_option

EMPLOYMENT_TYPE_MAP = {
    "permanent": "full_time",
    "temporary": "contract",
    "intern": "internship",
    "trainee": "internship",
    "freelance": "freelance",
}


class PersonioAdapter(JobSourceAdapter):
    source_name = "personio"

    async def fetch_jobs(
        self,
        company_slug: str,
        target_countries: list[str],
        target_roles: list[str],
        skills: list[str] | tuple = (),
    ) -> list[JobListing]:
        # Personio retired its /api/v1/jobs JSON endpoint (now 404s, replaced by
        # a client-rendered SPA); the legacy /xml feed (their "workzag-jobs"
        # format, from the Workzag product the recruiting board was built on)
        # is still live and is the only public no-auth source left.
        url = f"https://{company_slug}.jobs.personio.de/xml"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return []
                root = ET.fromstring(resp.text)
        except Exception:
            return []

        results = []
        for position in root.findall("position"):
            title = (position.findtext("name") or "").strip()
            if not matches_roles(title, target_roles, skills):
                continue

            location_raw = (position.findtext("office") or "").strip() or None
            country_code = resolve_country(location_raw)
            remote_option = resolve_remote_option(location_raw)

            if not matches_countries(country_code, target_countries):
                if remote_option != "remote":
                    continue
                if country_code and not matches_countries(country_code, target_countries):
                    continue

            description = "\n\n".join(
                f"{(jd.findtext('name') or '').strip()}\n{(jd.findtext('value') or '').strip()}"
                for jd in position.findall("jobDescriptions/jobDescription")
            ).strip() or None

            employment_type = EMPLOYMENT_TYPE_MAP.get((position.findtext("employmentType") or "").strip())
            if employment_type == "full_time" and (position.findtext("schedule") or "").strip() == "part-time":
                employment_type = "part_time"

            job_id = (position.findtext("id") or "").strip()
            posted_at = parse_time((position.findtext("createdAt") or "").strip())
            results.append(
                JobListing(
                    source=self.source_name,
                    external_id=job_id,
                    title=title,
                    company_name=company_slug,
                    application_url=f"https://{company_slug}.jobs.personio.de/job/{job_id}",
                    location_raw=location_raw,
                    country_code=country_code,
                    description=description,
                    employment_type=employment_type,
                    remote_option=remote_option,
                    posted_at=posted_at,
                    raw_data={child.tag: child.text for child in position if child.tag != "jobDescriptions"},
                )
            )
        return results
