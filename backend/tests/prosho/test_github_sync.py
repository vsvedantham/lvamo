"""Repo connection, prosho.yaml sync, claims, webhook — GitHub faked."""
import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import select

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.prosho.models import ProshoAuditLog, ProshoProject
from app.prosho.services import github

API = "/api/v1/prosho"
INSTALLATION = 77_000_001
REPO = {"id": 66_000_001, "full_name": "student/heatrisk", "private": False, "default_branch": "main"}
OTHER_REPO = {"id": 66_000_002, "full_name": "student/other", "private": True, "default_branch": "main"}

MANIFEST = b"""version: 1
title: HeatRisk EU
type: data-science
summary: Heat risk across Europe
demo: { kind: streamlit, url: https://heatrisk.streamlit.app }
claims:
  - id: predict-2026
    text: Predict 2026 heat deaths within 25%
    metric: prediction_error_pct
    target: { op: abs_lte, value: 25 }
  - id: city-maps
    text: Heat maps for five capitals
"""


class FakeGitHub:
    def __init__(self):
        self.account_id = None  # set to the student's github_id once "installed"
        self.repos = [REPO, OTHER_REPO]
        self.files = {"prosho.yaml": MANIFEST}
        self.fail = None
        self.synced_refs = []

    def install(self, monkeypatch):
        async def get_user_installation(login):
            return None if self.account_id is None else {"id": INSTALLATION, "account": {"id": self.account_id}}

        async def installation_token(installation_id):
            if self.fail:
                raise github.GitHubError(self.fail)
            assert installation_id == INSTALLATION
            return "inst-token"

        async def list_installation_repos(token):
            return list(self.repos)

        async def get_repo(token, repo_id):
            return next(r for r in self.repos if r["id"] == repo_id)

        async def get_branch_head_sha(token, full_name, branch):
            return "a" * 40

        async def get_file(token, full_name, path, ref, max_bytes):
            self.synced_refs.append(ref)
            return self.files.get(path)

        for name, fn in locals().items():
            if callable(fn) and name != "self":
                monkeypatch.setattr(github, name, fn)


@pytest.fixture
def gh(monkeypatch):
    fake = FakeGitHub()
    fake.install(monkeypatch)
    monkeypatch.setattr(settings, "prosho_github_webhook_secret", "test-secret")
    return fake


@pytest.fixture
async def student(make_user, client, gh):
    user, h = await make_user("student")
    resp = await client.post(f"{API}/projects", json={"title": "Draft", "slug": f"hr-{uuid.uuid4().hex[:8]}",
                                                       "project_type": "frontend"}, headers=h)
    return user, h, resp.json()["id"]


async def _connect(client, gh, user, h, pid, repo_id=REPO["id"]):
    gh.account_id = user.github_id
    return await client.post(f"{API}/projects/{pid}/github/connect", json={"repo_id": repo_id}, headers=h)


async def _claims(client, h, pid):
    return {c["key"]: c for c in (await client.get(f"{API}/projects/{pid}/claims", headers=h)).json()}


async def test_repos_before_and_after_install(client, gh, student):
    user, h, pid = student
    resp = (await client.get(f"{API}/projects/{pid}/github/repos", headers=h)).json()
    assert resp["installed"] is False and resp["install_url"].endswith(f"state={pid}")

    gh.account_id = 123  # installed on somebody else's account
    assert (await client.get(f"{API}/projects/{pid}/github/repos", headers=h)).json()["installed"] is False

    gh.account_id = user.github_id
    resp = (await client.get(f"{API}/projects/{pid}/github/repos", headers=h)).json()
    assert resp["installed"] and [r["full_name"] for r in resp["repos"]] == ["student/heatrisk", "student/other"]


async def test_connect_syncs_manifest_and_claims(client, gh, student):
    user, h, pid = student
    resp = await _connect(client, gh, user, h, pid)
    assert resp.status_code == 200
    p = resp.json()
    assert (p["title"], p["project_type"], p["demo_kind"], p["repo_full_name"]) == (
        "HeatRisk EU", "data_science", "streamlit", "student/heatrisk")
    assert p["manifest_managed"] and p["manifest_errors"] is None and p["manifest_sha"] == "a" * 40

    claims = await _claims(client, h, pid)
    assert list(claims) == ["predict-2026", "city-maps"]
    assert claims["predict-2026"]["target_op"] == "abs_lte" and claims["city-maps"]["metric_key"] is None

    async with AsyncSessionLocal() as db:
        actions = [a.action for a in await db.scalars(
            select(ProshoAuditLog).where(ProshoAuditLog.entity_id == uuid.UUID(pid)).order_by(ProshoAuditLog.created_at))]
    assert actions == ["project.create", "project.repo_connect", "manifest.sync"]


async def test_connect_refusals(client, gh, student, make_user):
    user, h, pid = student
    gh.account_id = None
    assert (await client.post(f"{API}/projects/{pid}/github/connect", json={"repo_id": REPO["id"]}, headers=h)).status_code == 409
    assert (await _connect(client, gh, user, h, pid, repo_id=999)).status_code == 404

    await _connect(client, gh, user, h, pid)
    second = (await client.post(f"{API}/projects", json={"title": "Two", "slug": f"two-{uuid.uuid4().hex[:6]}",
                                                         "project_type": "frontend"}, headers=h)).json()["id"]
    assert (await _connect(client, gh, user, h, second)).status_code == 409


async def test_resync_upserts_and_archives_claims_and_keeps_manual_status(client, gh, student):
    user, h, pid = student
    await _connect(client, gh, user, h, pid)
    maps = (await _claims(client, h, pid))["city-maps"]
    resp = await client.patch(f"{API}/projects/{pid}/claims/{maps['id']}", json={"manual_status": "in_progress"}, headers=h)
    assert resp.status_code == 200
    metric = (await _claims(client, h, pid))["predict-2026"]
    assert (await client.patch(f"{API}/projects/{pid}/claims/{metric['id']}", json={"manual_status": "met"}, headers=h)).status_code == 409

    gh.files["prosho.yaml"] = MANIFEST.replace(b"Heat maps for five capitals", b"Heat maps for six capitals").replace(
        b"  - id: predict-2026\n    text: Predict 2026 heat deaths within 25%\n    metric: prediction_error_pct\n    target: { op: abs_lte, value: 25 }\n",
        b"  - id: new-claim\n    text: Something new\n")
    assert (await client.post(f"{API}/projects/{pid}/sync", headers=h)).status_code == 200
    claims = await _claims(client, h, pid)
    assert list(claims) == ["new-claim", "city-maps"]  # manifest order
    assert claims["city-maps"]["text"] == "Heat maps for six capitals"
    assert claims["city-maps"]["manual_status"] == "in_progress"

    gh.files["prosho.yaml"] = MANIFEST  # predict-2026 comes back from the archive
    await client.post(f"{API}/projects/{pid}/sync", headers=h)
    assert list(await _claims(client, h, pid)) == ["predict-2026", "city-maps"]


async def test_bad_manifest_keeps_last_good_story(client, gh, student):
    user, h, pid = student
    await _connect(client, gh, user, h, pid)
    gh.files["prosho.yaml"] = b"version: 1\ntitle: Broken\ntype: data-science\ntitel: typo\n"
    p = (await client.post(f"{API}/projects/{pid}/sync", headers=h)).json()
    assert p["title"] == "HeatRisk EU" and p["manifest_managed"]
    assert p["manifest_errors"] == [{"line": 4, "path": "titel", "message": "unknown field — check the spelling"}]

    gh.files.pop("prosho.yaml")
    assert "No prosho.yaml" in (await client.post(f"{API}/projects/{pid}/sync", headers=h)).json()["manifest_errors"][0]["message"]

    gh.fail = "Couldn't reach GitHub — try again in a minute"
    p = (await client.post(f"{API}/projects/{pid}/sync", headers=h)).json()
    assert p["manifest_errors"][0]["message"] == gh.fail and p["title"] == "HeatRisk EU"


async def test_disconnect_unlocks_story_and_archives_claims(client, gh, student):
    user, h, pid = student
    await _connect(client, gh, user, h, pid)
    p = (await client.delete(f"{API}/projects/{pid}/github", headers=h)).json()
    assert p["repo_full_name"] is None and not p["manifest_managed"] and p["title"] == "HeatRisk EU"
    assert await _claims(client, h, pid) == {}
    assert (await client.patch(f"{API}/projects/{pid}", json={"title": "Renamed"}, headers=h)).status_code == 200


def _signed(payload: dict, secret="test-secret"):
    body = json.dumps(payload).encode()
    return body, "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def _hook(client, event, payload, secret="test-secret"):
    body, sig = _signed(payload, secret)
    return await client.post(f"{API}/github/webhook", content=body,
                             headers={"X-GitHub-Event": event, "X-Hub-Signature-256": sig, "Content-Type": "application/json"})


async def test_webhook_signature_ping_and_push(client, gh, student):
    user, h, pid = student
    assert (await _hook(client, "ping", {"zen": "hi"}, secret="wrong")).status_code == 401
    assert (await client.post(f"{API}/github/webhook", content=b"{}", headers={"X-GitHub-Event": "ping"})).status_code == 401
    assert (await _hook(client, "ping", {"zen": "hi"})).json() == {"status": "pong"}

    await _connect(client, gh, user, h, pid)
    gh.files["prosho.yaml"] = MANIFEST.replace(b"title: HeatRisk EU", b"title: HeatRisk EU v2")
    push = {"ref": "refs/heads/main", "after": "b" * 40, "repository": REPO, "installation": {"id": INSTALLATION}}

    resp = await _hook(client, "push", {**push, "ref": "refs/heads/feature"})
    assert resp.json()["status"] == "ignored"

    resp = await _hook(client, "push", push)
    assert resp.json() == {"status": "queued"}
    p = (await client.get(f"{API}/projects/{pid}", headers=h)).json()  # background task ran with the request
    assert p["title"] == "HeatRisk EU v2" and p["manifest_sha"] == "b" * 40 and gh.synced_refs[-1] == "b" * 40


async def test_webhook_uninstall_marks_access_lost(client, gh, student):
    user, h, pid = student
    await _connect(client, gh, user, h, pid)
    resp = await _hook(client, "installation", {"action": "deleted", "installation": {"id": INSTALLATION}})
    assert resp.json() == {"status": "ok"}
    p = (await client.get(f"{API}/projects/{pid}", headers=h)).json()
    assert p["repo_access_lost"] and p["repo_full_name"] == "student/heatrisk"
    assert "No GitHub repo connected" in (await client.post(f"{API}/projects/{pid}/sync", headers=h)).json()["manifest_errors"][0]["message"]
