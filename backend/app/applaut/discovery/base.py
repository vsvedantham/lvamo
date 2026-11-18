from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class JobListing:
    source: str
    external_id: str
    title: str
    company_name: str
    application_url: str
    location_raw: Optional[str] = None
    country_code: Optional[str] = None
    description: Optional[str] = None
    employment_type: Optional[str] = None
    remote_option: Optional[str] = None
    posted_at: Optional[datetime] = None
    raw_data: dict = field(default_factory=dict)


class JobSourceAdapter(ABC):
    source_name: str

    @abstractmethod
    async def fetch_jobs(
        self,
        company_slug: str,
        target_countries: list[str],
        target_roles: list[str],
        skills: list[str] | tuple = (),
    ) -> list[JobListing]:
        """Fetch and filter jobs for a single company board."""
