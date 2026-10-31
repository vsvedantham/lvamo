"""The work timeline: commits on the connected repo's default branch.

Refreshed on every manifest sync (connect, "Sync now", push webhook) from
GitHub's commit list — so pushes of more than 20 commits and the history from
before the repo was connected are covered too. Activity per week is always
public; commit messages only when the repo itself is public (or for the
owner and mentors)."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.prosho_project import ProshoProject
from app.prosho.models.prosho_repo_event import ProshoRepoEvent
from app.prosho.schemas.activity import Timeline, TimelineCommit, TimelineWeek
from app.prosho.services import github

log = logging.getLogger(__name__)

FIRST_SYNC_PAGES = 3  # up to 300 commits of history on the first sync
WEEKS_SHOWN = 26
MIN_WEEKS_SHOWN = 8
COMMITS_SHOWN = 20


def _parse(item: dict) -> dict | None:
    commit = item.get("commit") or {}
    when = (commit.get("author") or {}).get("date") or (commit.get("committer") or {}).get("date")
    if not item.get("sha") or not when:
        return None
    message = (commit.get("message") or "").strip().splitlines()
    return {
        "commit_sha": item["sha"][:40],
        "message": (message[0] if message else "")[:300],
        "author_login": ((item.get("author") or {}).get("login") or None),
        "committed_at": datetime.fromisoformat(when.replace("Z", "+00:00")),
    }


async def refresh(project: ProshoProject, token: str, full_name: str, ref: str, db: AsyncSession) -> None:
    """Best effort: a GitHub hiccup here never fails the manifest sync. Adds
    rows to the caller's transaction; the caller commits."""
    have_any = await db.scalar(select(ProshoRepoEvent.id).where(ProshoRepoEvent.project_id == project.id).limit(1))
    try:
        items = await github.list_commits(token, full_name, ref, pages=1 if have_any else FIRST_SYNC_PAGES)
    except github.GitHubError:
        log.warning("prosho: couldn't read commits for project %s", project.id)
        return
    rows = [{**r, "project_id": project.id} for r in map(_parse, items) if r]
    for r in rows:
        if r["author_login"]:
            r["author_login"] = r["author_login"][:100]
    if rows:
        await db.execute(insert(ProshoRepoEvent).values(rows)
                         .on_conflict_do_nothing(constraint="uq_prosho_repo_events_project_commit"))


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


async def build(project: ProshoProject, db: AsyncSession, *, include_messages: bool) -> Timeline | None:
    total, first_at, last_at = (await db.execute(
        select(func.count(), func.min(ProshoRepoEvent.committed_at), func.max(ProshoRepoEvent.committed_at))
        .where(ProshoRepoEvent.project_id == project.id))).one()
    if not total:
        return None

    this_week = _monday(datetime.now(timezone.utc).date())
    start = max(_monday(first_at.astimezone(timezone.utc).date()), this_week - timedelta(weeks=WEEKS_SHOWN - 1))
    start = min(start, this_week - timedelta(weeks=MIN_WEEKS_SHOWN - 1))
    week = func.date_trunc("week", func.timezone("UTC", ProshoRepoEvent.committed_at))
    counts = {w.date(): n for w, n in (await db.execute(
        select(week, func.count())
        .where(ProshoRepoEvent.project_id == project.id,
               ProshoRepoEvent.committed_at >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc))
        .group_by(week))).all()}
    weeks = []
    w = start
    while w <= this_week:
        weeks.append(TimelineWeek(week_start=w, commits=counts.get(w, 0)))
        w += timedelta(weeks=1)

    commits = None
    if include_messages:
        recent = await db.scalars(select(ProshoRepoEvent).where(ProshoRepoEvent.project_id == project.id)
                                  .order_by(ProshoRepoEvent.committed_at.desc()).limit(COMMITS_SHOWN))
        commits = [TimelineCommit(sha=e.commit_sha, message=e.message, author_login=e.author_login,
                                  committed_at=e.committed_at,
                                  url=f"https://github.com/{project.repo_full_name}/commit/{e.commit_sha}")
                   for e in recent]
    return Timeline(weeks=weeks, total_commits=total, last_commit_at=last_at, commits=commits)
