"""Phase 3: the commit timeline and page stats."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.prosho.models import ProshoPageStatDaily
from app.core import rate_limit
from app.prosho.services.page_stats import referrer_domain
from tests.prosho.test_github_sync import REPO, FakeGitHub

API = "/api/v1/prosho"


def _commit(sha: str, message: str, days_ago: int, login: str | None = "student") -> dict:
    when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"sha": sha * 40, "commit": {"message": message, "author": {"date": when}},
            "author": {"login": login} if login else None}


@pytest.fixture
def gh(monkeypatch):
    fake = FakeGitHub()
    fake.repos = [dict(REPO)]
    fake.install(monkeypatch)
    monkeypatch.setattr(settings, "prosho_github_webhook_secret", "test-secret")
    return fake


@pytest.fixture
async def connected(client, make_user, gh):
    user, h = await make_user("student")
    slug = f"tl-{uuid.uuid4().hex[:8]}"
    pid = (await client.post(f"{API}/projects", json={"title": "TL", "slug": slug, "project_type": "data_science"},
                             headers=h)).json()["id"]
    gh.account_id = user.github_id
    gh.commits = [_commit("c", "Add maps\n\nLong body", 1), _commit("b", "Fix pipeline", 8, login=None),
                  _commit("a", "Initial commit", 9)]
    assert (await client.post(f"{API}/projects/{pid}/github/connect", json={"repo_id": REPO["id"]},
                              headers=h)).status_code == 200
    await client.patch(f"{API}/projects/{pid}", json={"visibility": "unlisted"}, headers=h)
    return {"pid": pid, "slug": slug, "h": h}


async def test_timeline_for_the_owner(client, connected):
    tl = (await client.get(f"{API}/projects/{connected['pid']}/timeline", headers=connected["h"])).json()
    assert tl["total_commits"] == 3 and len(tl["weeks"]) >= 8
    assert sum(w["commits"] for w in tl["weeks"]) == 3
    assert [(c["message"], c["author_login"]) for c in tl["commits"]] == [
        ("Add maps", "student"), ("Fix pipeline", None), ("Initial commit", "student")]
    assert tl["commits"][0]["url"] == f"https://github.com/{REPO['full_name']}/commit/{'c' * 40}"
    weeks = [w["week_start"] for w in tl["weeks"]]
    assert weeks == sorted(weeks) and all(datetime.fromisoformat(w).weekday() == 0 for w in weeks)


async def test_public_page_hides_messages_of_private_repos(client, connected, gh):
    page = (await client.get(f"{API}/public/projects/{connected['slug']}")).json()
    assert page["timeline"]["total_commits"] == 3 and len(page["timeline"]["commits"]) == 3  # public repo

    gh.repos[0]["private"] = True
    gh.commits.insert(0, _commit("d", "Secret tweak", 0))
    await client.post(f"{API}/projects/{connected['pid']}/sync", headers=connected["h"])
    page = (await client.get(f"{API}/public/projects/{connected['slug']}")).json()
    assert page["timeline"]["commits"] is None and page["timeline"]["total_commits"] == 4
    assert "Secret tweak" not in str(page)
    tl = (await client.get(f"{API}/projects/{connected['pid']}/timeline", headers=connected["h"])).json()
    assert tl["commits"][0]["message"] == "Secret tweak"  # the owner still sees it


async def test_resync_is_idempotent_and_disconnect_clears(client, connected):
    pid, h = connected["pid"], connected["h"]
    await client.post(f"{API}/projects/{pid}/sync", headers=h)
    assert (await client.get(f"{API}/projects/{pid}/timeline", headers=h)).json()["total_commits"] == 3
    await client.delete(f"{API}/projects/{pid}/github", headers=h)
    assert (await client.get(f"{API}/projects/{pid}/timeline", headers=h)).json() is None
    assert (await client.get(f"{API}/public/projects/{connected['slug']}")).json()["timeline"] is None


def test_referrer_domain():
    assert referrer_domain("https://www.linkedin.com/feed/?trk=abc") == "linkedin.com"
    assert referrer_domain("https://user:pw@Mail.Google.com/x") == "mail.google.com"
    assert referrer_domain("http://localhost:5173/") == ""
    assert referrer_domain("not a url") == ""
    assert referrer_domain(None) == ""


async def test_page_events_and_stats(client, make_user):
    user, h = await make_user("student")
    slug = f"ps-{uuid.uuid4().hex[:8]}"
    pid = (await client.post(f"{API}/projects", json={"title": "PS", "slug": slug, "project_type": "frontend"},
                             headers=h)).json()["id"]
    events = f"{API}/public/projects/{slug}/events"

    # Private: accepted, not counted.
    assert (await client.post(events, json={"event": "view"})).status_code == 204
    assert (await client.post(f"{API}/public/projects/no-such-page/events", json={})).status_code == 204
    async with AsyncSessionLocal() as db:
        assert list(await db.scalars(select(ProshoPageStatDaily).where(ProshoPageStatDaily.project_id == uuid.UUID(pid)))) == []

    await client.patch(f"{API}/projects/{pid}", json={"visibility": "unlisted"}, headers=h)
    rate_limit.reset()  # the private-page hit above used up some of this address's hourly budget
    for body in ({"referrer": "https://www.linkedin.com/feed/?trk=x"}, {}, {"event": "view", "referrer": "junk"},
                 {"event": "hub_click", "referrer": "https://linkedin.com/"}):
        assert (await client.post(events, json=body)).status_code == 204
    assert (await client.post(events, json={"event": "bogus"})).status_code == 422

    stats = (await client.get(f"{API}/projects/{pid}/stats?days=7", headers=h)).json()
    assert (stats["total_views"], stats["hub_clicks"]) == (3, 1)
    assert stats["referrers"] == [{"domain": "", "views": 2}, {"domain": "linkedin.com", "views": 1}]
    assert len(stats["days"]) == 7 and stats["days"][-1]["views"] == 3

    _, other = await make_user("other")
    assert (await client.get(f"{API}/projects/{pid}/stats", headers=other)).status_code == 404
    assert (await client.get(f"{API}/projects/{pid}/stats?days=500", headers=h)).status_code == 422
