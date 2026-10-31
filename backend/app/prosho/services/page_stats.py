"""Page views and clicks to the LVAMO hub, as daily aggregates only
(BETA_PLAN §11: no IPs, no cookies, nothing per visitor).

The public page reports its own view once per browser tab session; views by
the owner or a mentor, and owner previews of private pages, aren't counted.
Only the referring *domain* is kept — never the path or query, which can
carry personal data."""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.enums import PageEvent, Visibility
from app.prosho.models.prosho_page_stat import ProshoPageStatDaily
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.schemas.activity import PageStats, StatsDay, StatsReferrer

_HOSTNAME = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,98}[a-z0-9])?$")
MAX_DAYS = 90
# How often one address can add to a page's count in an hour (routers/public.py).
COUNTS_PER_IP_HOUR = 3


def referrer_domain(referrer: str | None) -> str:
    if not referrer:
        return ""
    try:
        host = (urlsplit(referrer.strip()).hostname or "").lower()
    except ValueError:
        return ""
    host = host.removeprefix("www.")
    return host if _HOSTNAME.match(host) and "." in host else ""


async def record(slug: str, event: PageEvent, referrer: str | None, db: AsyncSession) -> None:
    """Silently ignores unknown, private and inactive pages: the caller
    always gets the same answer, and nothing is counted for them."""
    project = await db.scalar(
        select(ProshoProject).join(ProshoUser, ProshoUser.id == ProshoProject.owner_id)
        .where(ProshoProject.slug == slug.lower(), ProshoProject.is_active.is_(True), ProshoUser.is_active.is_(True),
               ProshoProject.visibility != Visibility.private))
    if project is None:
        return
    domain = referrer_domain(referrer) if event == PageEvent.view else ""
    stmt = insert(ProshoPageStatDaily).values(
        project_id=project.id, day=datetime.now(timezone.utc).date(), event=event, referrer_domain=domain, count=1)
    await db.execute(stmt.on_conflict_do_update(
        index_elements=["project_id", "day", "event", "referrer_domain"],
        set_={"count": ProshoPageStatDaily.count + 1}))
    await db.commit()


async def summary(project_id: uuid.UUID, days: int, db: AsyncSession) -> PageStats:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    rows = (await db.execute(
        select(ProshoPageStatDaily.day, ProshoPageStatDaily.event, ProshoPageStatDaily.referrer_domain,
               ProshoPageStatDaily.count)
        .where(ProshoPageStatDaily.project_id == project_id, ProshoPageStatDaily.day >= start))).all()
    per_day: dict[date, int] = {}
    per_ref: dict[str, int] = {}
    hub_clicks = 0
    for day, event, domain, count in rows:
        if event == PageEvent.hub_click:
            hub_clicks += count
            continue
        per_day[day] = per_day.get(day, 0) + count
        per_ref[domain] = per_ref.get(domain, 0) + count
    return PageStats(
        days=[StatsDay(day=start + timedelta(days=i), views=per_day.get(start + timedelta(days=i), 0))
              for i in range(days)],
        total_views=sum(per_day.values()),
        hub_clicks=hub_clicks,
        referrers=[StatsReferrer(domain=d, views=v)
                   for d, v in sorted(per_ref.items(), key=lambda kv: (-kv[1], kv[0]))][:10],
    )

