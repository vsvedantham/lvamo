"""GitHub sign-in. GitHub's three HTTP calls are faked; everything else
(state/login-code JWTs, upsert, allowlist, redirects, /me) is real."""
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.config import settings
from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.prosho.models import ProshoUser
from app.prosho.services import auth as auth_service
from app.prosho.services import github

BASE = "/api/v1/prosho/auth"
GH_ID = 9_100_000_001  # in the test id range; conftest cleans up after each test


@pytest.fixture
def fake_github(monkeypatch):
    profile = {"id": GH_ID, "login": "test-student", "name": "Test Student", "avatar_url": "https://avatars.example/1"}

    async def exchange_code(code):
        assert code == "good-code"
        return "gh-user-token"

    async def fetch_user(token):
        return dict(profile)

    async def fetch_primary_email(token):
        return "student@example.com"

    monkeypatch.setattr(github, "exchange_code", exchange_code)
    monkeypatch.setattr(github, "fetch_user", fetch_user)
    monkeypatch.setattr(github, "fetch_primary_email", fetch_primary_email)
    monkeypatch.setattr(settings, "prosho_signup_allowlist", "Other-User, TEST-student")
    return profile


async def _callback(client, code="good-code", state=None):
    state = state if state is not None else auth_service.new_state()
    return await client.get(f"{BASE}/github/callback", params={"code": code, "state": state})


def _login_error(resp):
    assert resp.status_code == 307
    loc = urlparse(resp.headers["location"])
    assert loc.path == "/prosho/login"
    return parse_qs(loc.query)["error"][0]


async def _get_user():
    async with AsyncSessionLocal() as db:
        return await db.scalar(select(ProshoUser).where(ProshoUser.github_id == GH_ID))


async def test_authorize_redirects_to_github_with_signed_state(client):
    resp = await client.get(f"{BASE}/github/authorize")
    assert resp.status_code == 307
    loc = urlparse(resp.headers["location"])
    assert (loc.netloc, loc.path) == ("github.com", "/login/oauth/authorize")
    q = parse_qs(loc.query)
    assert q["client_id"] == [settings.prosho_github_client_id]
    assert q["redirect_uri"] == [settings.prosho_github_redirect_uri]
    auth_service.verify_state(q["state"][0])  # raises if not our state


async def test_full_sign_in_flow(client, fake_github):
    resp = await _callback(client)
    assert resp.status_code == 307
    loc = urlparse(resp.headers["location"])
    assert loc.path == "/prosho/auth/callback" and loc.query == ""
    code = parse_qs(loc.fragment)["code"][0]

    user = await _get_user()
    assert (user.github_login, user.name, user.email, user.role.value) == (
        "test-student", "Test Student", "student@example.com", "student")

    resp = await client.post(f"{BASE}/exchange", json={"code": code})
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    resp = await client.get(f"{BASE}/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["github_login"] == "test-student"


async def test_denied_and_bad_state(client, fake_github):
    resp = await client.get(f"{BASE}/github/callback", params={"error": "access_denied"})
    assert _login_error(resp) == "denied"
    assert _login_error(await _callback(client, state="forged")) == "failed"
    assert await _get_user() is None


async def test_new_user_not_on_allowlist_is_refused(client, fake_github, monkeypatch):
    monkeypatch.setattr(settings, "prosho_signup_allowlist", "")
    assert _login_error(await _callback(client)) == "not_invited"
    assert await _get_user() is None


async def test_existing_user_signs_in_without_invite_and_details_refresh(client, fake_github, monkeypatch):
    await _callback(client)
    monkeypatch.setattr(settings, "prosho_signup_allowlist", "")
    fake_github["login"] = "renamed-student"
    resp = await _callback(client)
    assert urlparse(resp.headers["location"]).path == "/prosho/auth/callback"
    assert (await _get_user()).github_login == "renamed-student"


async def test_inactive_user_is_refused(client, fake_github):
    await _callback(client)
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(ProshoUser).where(ProshoUser.github_id == GH_ID))
        user.is_active = False
        await db.commit()
    assert _login_error(await _callback(client)) == "inactive"


async def test_exchange_rejects_non_login_codes(client, fake_github):
    await _callback(client)
    user = await _get_user()
    access_token = auth_service.issue_access_token(user.id)  # right user, wrong purpose
    resp = await client.post(f"{BASE}/exchange", json={"code": access_token})
    assert resp.status_code == 400


async def test_me_rejects_other_verticals_tokens_and_no_token(client, fake_github):
    await _callback(client)
    user = await _get_user()
    jobref_token = create_access_token(user.id, extra_claims={"vertical": "jobref"})
    assert (await client.get(f"{BASE}/me", headers={"Authorization": f"Bearer {jobref_token}"})).status_code == 401
    assert (await client.get(f"{BASE}/me")).status_code == 401
