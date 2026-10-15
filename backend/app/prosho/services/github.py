"""Thin GitHub HTTP client for ProSho's single GitHub App (`lvamo-prosho`).

The App does three jobs (see docs/prosho/BETA_PLAN.md §11): user sign-in via
its OAuth web flow, reading `prosho.yaml` with installation tokens, and push
webhooks. Plain httpx, no GitHub SDK.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status

from app.config import settings

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
API = "https://api.github.com"
TIMEOUT = 10.0


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
