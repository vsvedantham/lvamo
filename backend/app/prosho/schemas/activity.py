"""Work timeline (commits) and page stats (BETA_PLAN Phase 3)."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class TimelineWeek(BaseModel):
    week_start: date  # Monday, UTC
    commits: int


class TimelineCommit(BaseModel):
    sha: str
    message: str
    author_login: Optional[str]
    committed_at: datetime
    url: str


class Timeline(BaseModel):
    weeks: list[TimelineWeek]
    total_commits: int
    last_commit_at: Optional[datetime]
    # None when the messages may not be shown (a private repo on the public
    # page). The owner and mentors always get them.
    commits: Optional[list[TimelineCommit]]


class StatsDay(BaseModel):
    day: date
    views: int


class StatsReferrer(BaseModel):
    domain: str  # "" = direct / unknown
    views: int


class PageStats(BaseModel):
    days: list[StatsDay]
    total_views: int
    hub_clicks: int
    referrers: list[StatsReferrer]
