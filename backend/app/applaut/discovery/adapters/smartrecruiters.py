from datetime import datetime, timezone

import httpx

from app.applaut.discovery.base import JobListing, JobSourceAdapter
from app.applaut.discovery.location import matches_countries, matches_roles, resolve_remote_option

BASE_URL = "https://api.smartrecruiters.com/v1/companies"
PAGE_SIZE = 100
MAX_RESULTS = 200  # bounds worst-case latency/volume for very large accounts (e.g. Bosch)

TYPE_TO_EMPLOYMENT_TYPE = {
    "full-time": "full_time",
    "permanent": "full_time",
    "part-time": "part_time",
    "temporary": "contract",
    "contractor": "contract",
    "intern": "internship",
    "internship": "internship",
}


class SmartRecruitersAdapter(JobSourceAdapter):
    source_name = "smartrecruiters"

    async def fetch_jobs(
        self,
        company_slug: str,
        target_countries: list[str],
        target_roles: list[str],
        skills: list[str] | tuple = (),
    ) -> list[JobListing]:
        list_url = f"{BASE_URL}/{company_slug}/postings"
        postings: list[dict] = []

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                offset = 0
                while offset < MAX_RESULTS:
                    resp = await client.get(list_url, params={"limit": PAGE_SIZE, "offset": offset})
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    page = data.get("content", [])
                    postings.extend(page)
                    if len(page) < PAGE_SIZE:
                        break
                    offset += PAGE_SIZE

                # Filter to role+country matches first, then fetch full detail
                # (description, apply URL) only for the small surviving set —
                # avoids an expensive detail fetch per posting on accounts
                # with thousands of open roles.
                candidates = []
                for job in postings:
                    title = job.get("name", "")
                    if not matches_roles(title, target_roles, skills):
                        continue

                    location = job.get("location") or {}
                    country_code = (location.get("country") or "").upper() or None
                    is_remote = bool(location.get("remote"))
                    is_hybrid = bool(location.get("hybrid"))
                    remote_option = "remote" if is_remote else "hybrid" if is_hybrid else resolve_remote_option(
                        location.get("fullLocation")
                    )

                    if not matches_countries(country_code, target_countries):
                        if remote_option != "remote":
                            continue
                        if country_code and not matches_countries(country_code, target_countries):
                            continue

                    candidates.append((job, country_code, remote_option))

                results = []
                for job, country_code, remote_option in candidates:
                    job_id = job.get("id", "")
                    detail = {}
                    try:
                        detail_resp = await client.get(f"{list_url}/{job_id}")
                        if detail_resp.status_code == 200:
                            detail = detail_resp.json()
                    except Exception:
                        detail = {}

                    description = None
                    sections = (detail.get("jobAd") or {}).get("sections") or {}
                    desc_parts = [
                        s.get("text", "")
                        for key, s in sections.items()
                        if isinstance(s, dict) and s.get("text")
                    ]
                    if desc_parts:
                        description = "\n".join(desc_parts)

                    application_url = detail.get("applyUrl") or f"https://jobs.smartrecruiters.com/{company_slug}/{job_id}"

                    posted_at = None
                    released = job.get("releasedDate")
                    if released:
                        try:
                            posted_at = datetime.fromisoformat(released.replace("Z", "+00:00"))
                        except ValueError:
                            posted_at = None

                    employment_type = TYPE_TO_EMPLOYMENT_TYPE.get(
                        (job.get("typeOfEmployment") or {}).get("id", "")
                    )

                    results.append(
                        JobListing(
                            source=self.source_name,
                            external_id=str(job_id),
                            title=job.get("name", ""),
                            company_name=company_slug,
                            application_url=application_url,
                            location_raw=(job.get("location") or {}).get("fullLocation"),
                            country_code=country_code,
                            description=description,
                            employment_type=employment_type,
                            remote_option=remote_option,
                            posted_at=posted_at or datetime.now(timezone.utc),
                            raw_data=job,
                        )
                    )
                return results
        except Exception:
            return []
