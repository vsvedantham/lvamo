"""Ingest tokens, /ingest/evidence, computed claim status, data module."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.db.session import AsyncSessionLocal
from app.prosho.models import ProshoAuditLog, ProshoClaim, ProshoEvidence, ProshoIngestToken, ProshoProject
from app.prosho.models.enums import ClaimTargetOp, EvidenceKind, EvidenceSource
from app.prosho.modules import source_checks
from app.prosho.services import safe_fetch

API = "/api/v1/prosho"
SHA = "c" * 40
SOURCES = {"data": {"sources": [
    {"name": "Eurostat", "url": "https://ec.europa.eu/eurostat/", "licence": "CC BY 4.0"},
    {"name": "Down portal", "url": "https://down.example/data", "licence": None},
]}}


@pytest.fixture
async def project(client, make_user):
    user, h = await make_user("student")
    slug = f"ev-{uuid.uuid4().hex[:8]}"
    pid = (await client.post(f"{API}/projects", json={"title": "Ev", "slug": slug, "project_type": "data_science"},
                             headers=h)).json()["id"]
    await client.patch(f"{API}/projects/{pid}", json={"visibility": "unlisted"}, headers=h)
    async with AsyncSessionLocal() as db:
        await db.execute(update(ProshoProject).where(ProshoProject.id == uuid.UUID(pid)).values(module_config=SOURCES))
        db.add_all([
            ProshoClaim(project_id=uuid.UUID(pid), key="predict", text="Within 25%", metric_key="prediction_error_pct",
                        target_op=ClaimTargetOp.abs_lte, target_value=25, position=0),
            ProshoClaim(project_id=uuid.UUID(pid), key="maps", text="Five maps", position=1),
        ])
        await db.commit()
    token = (await client.post(f"{API}/projects/{pid}/tokens", json={"label": "GitHub Actions"}, headers=h)).json()
    return {"user": user, "h": h, "id": pid, "slug": slug, "token": token}


async def _ingest(client, token, body):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return await client.post(f"{API}/ingest/evidence", content=raw,
                             headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})


async def test_token_lifecycle(client, project, make_user):
    tok = project["token"]
    assert tok["token"].startswith("psho_") and tok["token_prefix"] == tok["token"][:9]
    listed = (await client.get(f"{API}/projects/{project['id']}/tokens", headers=project["h"])).json()
    assert [t["id"] for t in listed] == [tok["id"]] and "token" not in listed[0]
    async with AsyncSessionLocal() as db:
        row = await db.get(ProshoIngestToken, uuid.UUID(tok["id"]))
        assert row.token_hash != tok["token"] and len(row.token_hash) == 64

    _, other = await make_user("other")
    assert (await client.get(f"{API}/projects/{project['id']}/tokens", headers=other)).status_code == 404
    assert (await client.delete(f"{API}/projects/{project['id']}/tokens/{tok['id']}", headers=other)).status_code == 404

    resp = await client.delete(f"{API}/projects/{project['id']}/tokens/{tok['id']}", headers=project["h"])
    assert resp.json()["revoked_at"]
    r = await _ingest(client, tok["token"], {"items": [{"key": "a", "kind": "metric", "value_num": 1}]})
    assert r.status_code == 401
    async with AsyncSessionLocal() as db:
        actions = [a.action for a in await db.scalars(select(ProshoAuditLog).where(
            ProshoAuditLog.entity_id == uuid.UUID(tok["id"])).order_by(ProshoAuditLog.created_at))]
    assert actions == ["token.create", "token.revoke"]


async def test_ingest_auth_and_envelope(client, project):
    ok_body = {"items": [{"key": "a", "kind": "metric", "value_num": 1}]}
    assert (await client.post(f"{API}/ingest/evidence", json=ok_body)).status_code == 401
    assert (await _ingest(client, "psho_" + "x" * 43, ok_body)).status_code == 401
    t = project["token"]["token"]
    assert (await _ingest(client, t, b"not json")).status_code == 422
    assert (await _ingest(client, t, {"items": []})).status_code == 422
    assert (await _ingest(client, t, {"items": [{}] * 51})).status_code == 422
    assert (await _ingest(client, t, {"commit_sha": "abc", "items": ok_body["items"]})).status_code == 422
    big = {"items": [{"key": "a", "kind": "metric", "value_num": 1, "payload": {"x": "y" * 70_000}}]}
    assert (await _ingest(client, t, big)).status_code == 413

    async with AsyncSessionLocal() as db:
        await db.execute(update(ProshoProject).where(ProshoProject.id == uuid.UUID(project["id"])).values(is_active=False))
        await db.commit()
    assert (await _ingest(client, t, ok_body)).status_code == 401


async def test_per_item_results_and_idempotency(client, project):
    t = project["token"]["token"]
    body = {"commit_sha": SHA, "items": [
        {"key": "prediction_error_pct", "kind": "metric", "value_num": -12.4, "unit": "%", "claim": "predict"},
        {"key": "pipeline", "kind": "run", "value_text": "success", "payload": {"tests_passed": 48, "tests_total": 48}},
        {"key": "bad", "kind": "metric"},
        {"key": "source.fake", "kind": "check", "value_text": "pass"},
        {"key": "x", "kind": "metric", "value_num": 1, "claim": "nope"},
        {"key": "Bad Key", "kind": "metric", "value_num": 1},
        {"key": "chk", "kind": "check", "value_text": "maybe"},
    ]}
    r = (await _ingest(client, t, body)).json()
    assert (r["accepted"], r["duplicate"], r["rejected"]) == (2, 0, 5)
    reasons = {i["index"]: i.get("reason") for i in r["items"] if i["result"] == "rejected"}
    assert "value_num" in reasons[2] and "reserved" in reasons[3] and "nope" in reasons[4]
    assert "key" in reasons[5] and "pass, fail or warn" in reasons[6]

    again = (await _ingest(client, t, body)).json()
    assert (again["accepted"], again["duplicate"]) == (0, 2)  # CI retry of the same commit

    nosha = {"items": [{"key": "prediction_error_pct", "kind": "metric", "value_num": 30}]}
    assert (await _ingest(client, t, nosha)).json()["accepted"] == 1
    assert (await _ingest(client, t, nosha)).json()["accepted"] == 1  # no commit → accumulates

    async with AsyncSessionLocal() as db:
        rows = list(await db.scalars(select(ProshoEvidence).where(ProshoEvidence.project_id == uuid.UUID(project["id"]))))
        tok = await db.get(ProshoIngestToken, uuid.UUID(project["token"]["id"]))
    assert len(rows) == 4 and all(e.source == EvidenceSource.ci for e in rows)
    linked = next(e for e in rows if e.commit_sha == SHA and e.kind == EvidenceKind.metric)
    assert linked.claim_id is not None and tok.last_used_at is not None


async def test_claim_status_follows_latest_evidence(client, project):
    t, pid, h = project["token"]["token"], project["id"], project["h"]
    page = lambda: client.get(f"{API}/public/projects/{project['slug']}")  # noqa: E731

    claims = {c["key"]: c for c in (await page()).json()["claims"]}
    assert claims["predict"]["status"] == "awaiting_evidence" and claims["maps"]["status"] == "not_started"

    await _ingest(client, t, {"commit_sha": SHA, "items": [{"key": "prediction_error_pct", "kind": "metric", "value_num": -12, "unit": "%"}]})
    c = {c["key"]: c for c in (await page()).json()["claims"]}["predict"]
    assert (c["status"], c["latest_value"], c["latest_unit"], c["latest_commit"]) == ("met", -12, "%", SHA)

    await _ingest(client, t, {"commit_sha": "d" * 40, "items": [{"key": "prediction_error_pct", "kind": "metric", "value_num": 31}]})
    assert {c["key"]: c for c in (await page()).json()["claims"]}["predict"]["status"] == "not_met"

    owner_view = {c["key"]: c for c in (await client.get(f"{API}/projects/{pid}/claims", headers=h)).json()}
    assert owner_view["predict"]["status"] == "not_met" and owner_view["predict"]["latest_value"] == 31

    hist = (await client.get(f"{API}/projects/{pid}/evidence?key=prediction_error_pct", headers=h)).json()
    assert [e["value_num"] for e in hist] == [31, -12]


@pytest.fixture
def fake_checks(monkeypatch):
    calls = []

    async def check_url(url, **kw):
        calls.append(url)
        if "down" in url:
            return safe_fetch.FetchResult(ok=False, status_code=503, final_url=url, elapsed_ms=40, error="HTTP 503")
        return safe_fetch.FetchResult(ok=True, status_code=200, final_url=url, elapsed_ms=120)

    monkeypatch.setattr(safe_fetch, "check_url", check_url)
    return calls


async def test_data_module_panels_and_check_now(client, project, fake_checks):
    pid, h = project["id"], project["h"]
    dm = (await client.get(f"{API}/public/projects/{project['slug']}")).json()["data_module"]
    assert [s["status"] for s in dm["sources"]] == ["unchecked", "unchecked"] and dm["metrics"] == [] and dm["runs"] == []

    dm = (await client.post(f"{API}/projects/{pid}/sources/check", headers=h)).json()
    assert [(s["name"], s["status"], s["status_code"]) for s in dm["sources"]] == [
        ("Eurostat", "pass", 200), ("Down portal", "fail", 503)]
    assert dm["sources"][1]["detail"] == "HTTP 503"
    assert (await client.post(f"{API}/projects/{pid}/sources/check", headers=h)).status_code == 429

    await _ingest(client, project["token"]["token"], {"commit_sha": SHA, "items": [
        {"key": "prediction_error_pct", "kind": "metric", "value_num": 8, "unit": "%"},
        {"key": "rmse", "kind": "metric", "value_num": 0.42},
        {"key": "pipeline", "kind": "run", "value_text": "success", "payload": {"tests_passed": 48, "tests_total": 48, "secret": "x"}},
    ]})
    dm = (await client.get(f"{API}/public/projects/{project['slug']}")).json()["data_module"]
    metrics = {m["key"]: m for m in dm["metrics"]}
    assert metrics["prediction_error_pct"]["status"] == "met" and metrics["prediction_error_pct"]["claim_text"] == "Within 25%"
    assert metrics["rmse"]["status"] is None  # not tied to a claim
    assert dm["runs"][0]["status"] == "success" and dm["runs"][0]["details"] == {"tests_passed": 48, "tests_total": 48}


async def test_daily_job_skips_recent_and_checks_due(client, project, fake_checks):
    pid = uuid.UUID(project["id"])
    await source_checks.run_daily_checks()
    assert len(fake_checks) == 2  # both sources of the one due project…
    await source_checks.run_daily_checks()
    assert len(fake_checks) == 2  # …and not again within 20 hours (second worker)

    async with AsyncSessionLocal() as db:
        await db.execute(update(ProshoEvidence).where(ProshoEvidence.project_id == pid)
                         .values(recorded_at=datetime.now(timezone.utc) - timedelta(hours=21)))
        await db.commit()
    await source_checks.run_daily_checks()
    assert len(fake_checks) == 4
    async with AsyncSessionLocal() as db:
        rows = list(await db.scalars(select(ProshoEvidence).where(ProshoEvidence.project_id == pid)))
    assert all(e.source == EvidenceSource.scheduler and e.key.startswith("source.") for e in rows)


async def test_check_now_needs_sources(client, make_user):
    _, h = await make_user("fe")
    pid = (await client.post(f"{API}/projects", json={"title": "FE", "slug": f"fe-{uuid.uuid4().hex[:6]}",
                                                      "project_type": "frontend"}, headers=h)).json()["id"]
    assert (await client.post(f"{API}/projects/{pid}/sources/check", headers=h)).status_code == 409
    assert (await client.get(f"{API}/public/projects/x")).status_code == 404
