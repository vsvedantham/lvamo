"""Rate limits on the endpoints anyone can call."""
import uuid

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.prosho.models import ProshoPageStatDaily
from app.prosho.services import page_stats
from app.prosho.services.rate_limit import hit
from tests.prosho.test_evidence import _ingest, project  # noqa: F401  (fixture)

API = "/api/v1/prosho"


def test_window_counts_per_key():
    assert all(hit("unit:a", 3) for _ in range(3))
    assert not hit("unit:a", 3)
    assert hit("unit:b", 3)  # another key is untouched


async def test_ingest_is_limited_per_token(client, project):  # noqa: F811
    token = project["token"]["token"]
    statuses = [(await _ingest(client, token, {"items": []})).status_code for _ in range(31)]
    assert 429 not in statuses[:30] and statuses[30] == 429
    resp = await _ingest(client, "pst_guessed", {"items": []})
    assert resp.status_code == 401  # another token still gets through to auth


async def test_public_page_limit_by_forwarded_address(client):
    url = f"{API}/public/projects/no-such-page"
    for _ in range(120):
        assert (await client.get(url, headers={"X-Real-IP": "203.0.113.7"})).status_code == 404
    resp = await client.get(url, headers={"X-Real-IP": "203.0.113.7"})
    assert resp.status_code == 429 and resp.headers["Retry-After"] == "60"
    assert (await client.get(url, headers={"X-Real-IP": "203.0.113.8"})).status_code == 404


async def test_reloads_dont_pump_the_count(client, make_user):
    _, h = await make_user("student")
    slug = f"rl-{uuid.uuid4().hex[:8]}"
    pid = (await client.post(f"{API}/projects", json={"title": "RL", "slug": slug, "project_type": "frontend"},
                             headers=h)).json()["id"]
    await client.patch(f"{API}/projects/{pid}", json={"visibility": "unlisted"}, headers=h)
    events = f"{API}/public/projects/{slug}/events"
    for _ in range(10):
        assert (await client.post(events, json={}, headers={"X-Real-IP": "198.51.100.1"})).status_code == 204
    await client.post(events, json={}, headers={"X-Real-IP": "198.51.100.2"})
    async with AsyncSessionLocal() as db:
        counts = list(await db.scalars(select(ProshoPageStatDaily.count)
                                       .where(ProshoPageStatDaily.project_id == uuid.UUID(pid))))
    assert sum(counts) == page_stats.COUNTS_PER_IP_HOUR + 1
