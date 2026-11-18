from datetime import datetime, timezone

import httpx

from app.applaut.discovery.base import JobListing, JobSourceAdapter
from app.applaut.discovery.location import matches_roles

BASE_URL = "https://{slug}.recruitee.com/api/offers/"

EMPLOYMENT_TYPE_MAP = {
    "fulltime_permanent": "full_time",
    "fulltime_temporary": "contract",
    "parttime_permanent": "part_time",
    "parttime_temporary": "contract",
    "internship": "internship",
    "apprenticeship": "internship",
    "freelance": "freelance",
}


def _offer_country_codes(offer: dict) -> set[str]:
    codes = set()
    top_level = offer.get("country_code")
    if top_level:
        codes.add(top_level.upper())
    for loc in offer.get("locations") or []:
        cc = loc.get("country_code")
        if cc:
            codes.add(cc.upper())
    return codes


class RecruiteeAdapter(JobSourceAdapter):
    source_name = "recruitee"

    async def fetch_jobs(
        self,
        company_slug: str,
        target_countries: list[str],
        target_roles: list[str],
        skills: list[str] | tuple = (),
    ) -> list[JobListing]:
        url = BASE_URL.format(slug=company_slug)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers={"Accept": "application/json"})
                if resp.status_code != 200:
                    return []
                data = resp.json()
        except Exception:
            return []

        offers = data.get("offers", [])
        target_set = set(target_countries)

        results = []
        for offer in offers:
            title = offer.get("title", "")
            if not matches_roles(title, target_roles, skills):
                continue

            is_remote = bool(offer.get("remote"))
            country_codes = _offer_country_codes(offer)

            if is_remote:
                # Eligible-country list unknown or overlaps our targets → accept
                if country_codes and not (country_codes & target_set):
                    continue
                remote_option = "remote"
                country_code = next(iter(country_codes & target_set), next(iter(country_codes), None))
            else:
                if not (country_codes & target_set):
                    continue
                remote_option = "hybrid" if offer.get("hybrid") else "onsite"
                country_code = next(iter(country_codes & target_set))

            posted_at = None
            published = offer.get("published_at")
            if published:
                try:
                    posted_at = datetime.strptime(published, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
                except ValueError:
                    posted_at = None

            results.append(
                JobListing(
                    source=self.source_name,
                    external_id=str(offer.get("id", "")),
                    title=title,
                    company_name=company_slug,
                    application_url=offer.get("careers_url", ""),
                    location_raw=offer.get("location"),
                    country_code=country_code,
                    description=offer.get("description"),
                    employment_type=EMPLOYMENT_TYPE_MAP.get(offer.get("employment_type_code", "")),
                    remote_option=remote_option,
                    posted_at=posted_at or datetime.now(timezone.utc),
                    raw_data=offer,
                )
            )
        return results
