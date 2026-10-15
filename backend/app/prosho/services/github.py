"""Thin GitHub HTTP client for ProSho's single GitHub App (`lvamo-prosho`).

The App does three jobs (see docs/prosho/BETA_PLAN.md §11): user sign-in via
its OAuth web flow, reading `prosho.yaml` with installation tokens, and push
webhooks. Plain httpx, no GitHub SDK.
"""
from __future__ import annotations

import base64
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from jose import jwt

from app.config import settings

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
API = "https://api.github.com"
TIMEOUT = 10.0
RAW = "application/vnd.github.raw+json"


def _api_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _bad_gateway(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)


def build_authorize_url(state: str) -> str:
    # GitHub Apps take no `scope` — what a user token can do is fixed by the
    # App's own permissions (Email addresses: read is what sign-in needs).
    params = {
        "client_id": settings.prosho_github_client_id,
        "redirect_uri": settings.prosho_github_redirect_uri,
        "state": state,
        "allow_signup": "true",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.prosho_github_client_id,
                "client_secret": settings.prosho_github_client_secret,
                "code": code,
                "redirect_uri": settings.prosho_github_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
    # GitHub answers 200 even for a bad/expired code, with an `error` field.
    token = resp.json().get("access_token") if resp.status_code == 200 else None
    if not token:
        raise _bad_gateway("GitHub sign-in failed — could not exchange authorization code")
    return token


async def fetch_user(user_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"{API}/user", headers=_api_headers(user_token))
    if resp.status_code != 200:
        raise _bad_gateway("GitHub sign-in failed — could not fetch profile")
    return resp.json()


async def fetch_primary_email(user_token: str) -> str | None:
    """The user's primary *verified* email, or None. A missing email never
    blocks sign-in — GitHub identity is the account, email is a nicety."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"{API}/user/emails", headers=_api_headers(user_token))
    if resp.status_code != 200:
        return None
    for entry in resp.json():
        if entry.get("primary") and entry.get("verified"):
            return entry.get("email")
    return None


# --- GitHub App calls (App JWT / installation tokens) ------------------------


class GitHubError(Exception):
    """A GitHub call failed in a way the student should see (e.g. on the
    manifest status). `message` is safe to show."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _app_jwt() -> str:
    now = int(time.time())
    key = base64.b64decode(settings.prosho_github_private_key_b64).decode()
    # iat backdated 60 s for clock drift; GitHub caps exp at 10 minutes.
    return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": settings.prosho_github_app_id}, key, algorithm="RS256")


async def _get(client: httpx.AsyncClient, url: str, token: str, accept: str | None = None, **params) -> httpx.Response:
    headers = _api_headers(token)
    if accept:
        headers["Accept"] = accept
    try:
        return await client.get(url, headers=headers, params=params or None)
    except httpx.HTTPError:
        raise GitHubError("Couldn't reach GitHub — try again in a minute")


async def get_user_installation(login: str) -> dict[str, Any] | None:
    """The App's installation on a *personal* account, or None."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await _get(client, f"{API}/users/{login}/installation", _app_jwt())
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise GitHubError("Couldn't check your GitHub installation")
    return resp.json()


async def installation_token(installation_id: int) -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(f"{API}/app/installations/{installation_id}/access_tokens",
                                     headers=_api_headers(_app_jwt()))
        except httpx.HTTPError:
            raise GitHubError("Couldn't reach GitHub — try again in a minute")
    if resp.status_code in (403, 404):
        raise GitHubError("The ProSho GitHub App no longer has access — reconnect the repo")
    if resp.status_code != 201:
        raise GitHubError("Couldn't get access to your repo from GitHub")
    return resp.json()["token"]


async def list_installation_repos(token: str) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for page in range(1, 11):  # up to 1,000 repos
            resp = await _get(client, f"{API}/installation/repositories", token, per_page=100, page=page)
            if resp.status_code != 200:
                raise GitHubError("Couldn't list your repos")
            batch = resp.json().get("repositories", [])
            repos += batch
            if len(batch) < 100:
                break
    return repos


async def get_repo(token: str, repo_id: int) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await _get(client, f"{API}/repositories/{repo_id}", token)
    if resp.status_code == 404:
        raise GitHubError("The repo can't be found — it may have been deleted or removed from the ProSho app")
    if resp.status_code != 200:
        raise GitHubError("Couldn't read the repo from GitHub")
    return resp.json()


async def get_branch_head_sha(token: str, full_name: str, branch: str) -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await _get(client, f"{API}/repos/{full_name}/commits/{branch}", token,
                          accept="application/vnd.github.sha")
    if resp.status_code != 200:
        raise GitHubError(f"Couldn't read the latest commit on {branch}")
    return resp.text.strip()


async def get_file(token: str, full_name: str, path: str, ref: str, max_bytes: int) -> bytes | None:
    """File contents at `ref`, None if it doesn't exist. Raises if larger
    than `max_bytes` (checked before the body is read in full)."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            async with client.stream("GET", f"{API}/repos/{full_name}/contents/{path}",
                                     headers={**_api_headers(token), "Accept": RAW},
                                     params={"ref": ref}) as resp:
                if resp.status_code == 404:
                    return None
                if resp.status_code != 200:
                    raise GitHubError(f"Couldn't read {path} from GitHub")
                body = b""
                async for chunk in resp.aiter_bytes():
                    body += chunk
                    if len(body) > max_bytes:
                        raise GitHubError(f"{path} is larger than {max_bytes // 1024} KB")
                return body
        except httpx.HTTPError:
            raise GitHubError("Couldn't reach GitHub — try again in a minute")


def install_url(state: str) -> str:
    return f"https://github.com/apps/{settings.prosho_github_app_slug}/installations/new?state={state}"


def installation_settings_url(installation_id: int) -> str:
    return f"https://github.com/settings/installations/{installation_id}"
