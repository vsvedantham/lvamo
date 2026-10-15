"""ProSho sign-in: GitHub is the only identity source (BETA_PLAN §16.1).

Flow: /auth/github/authorize → GitHub → /auth/github/callback (upsert the
user) → redirect to the frontend with a short-lived *login code* in the URL
fragment → frontend POSTs it to /auth/exchange for the real access token.
The access token itself never appears in a URL, and the fragment is never
sent to any server or written to access logs.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import create_access_token, decode_access_token_payload
from app.db.session import get_db
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.services import github

bearer_scheme = HTTPBearer(auto_error=False)

# Stamped on every ProSho access token so it can't be replayed against
# another vertical's endpoints (CLAUDE.md: auth is isolated per vertical).
TOKEN_VERTICAL = "prosho"

STATE_PURPOSE = "prosho_github_state"
STATE_EXPIRE_MINUTES = 10
LOGIN_CODE_PURPOSE = "prosho_login_code"
LOGIN_CODE_EXPIRE_MINUTES = 2


class SignInRefused(Exception):
    """Sign-in reached GitHub fine but ProSho won't let this person in.
    `reason` is a short code the frontend turns into a message."""

    def __init__(self, reason: str):
        self.reason = reason


def _signup_allowlist() -> set[str]:
    return {
        login.strip().lower()
        for login in settings.prosho_signup_allowlist.split(",")
        if login.strip()
    }


def issue_access_token(user_id: uuid.UUID) -> str:
    return create_access_token(user_id, extra_claims={"vertical": TOKEN_VERTICAL})


def new_state() -> str:
    return create_access_token(
        "github-oauth",
        extra_claims={"purpose": STATE_PURPOSE},
        expires_minutes=STATE_EXPIRE_MINUTES,
    )


def _decode_purpose(token: str, purpose: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")
    if payload.get("purpose") != purpose:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")
    return payload


def verify_state(state: str) -> None:
    _decode_purpose(state, STATE_PURPOSE)


async def upsert_github_user(profile: dict[str, Any], email: str | None, db: AsyncSession) -> ProshoUser:
    """Find by GitHub's stable numeric id (logins can be renamed); refresh the
    display fields on every sign-in. New accounts need an invite while the
    beta is closed: `PROSHO_SIGNUP_ALLOWLIST` (GitHub logins). Existing
    accounts can always sign in unless deactivated."""
    github_id = int(profile["id"])
    user = await db.scalar(select(ProshoUser).where(ProshoUser.github_id == github_id))

    if user is None:
        if profile["login"].lower() not in _signup_allowlist():
            raise SignInRefused("not_invited")
        user = ProshoUser(github_id=github_id, github_login=profile["login"])
        db.add(user)
    elif not user.is_active:
        raise SignInRefused("inactive")

    user.github_login = profile["login"]
    user.name = profile.get("name") or None
    user.avatar_url = profile.get("avatar_url") or None
    if email:
        user.email = email
    await db.commit()
    await db.refresh(user)
    return user


async def handle_callback(code: str, state: str, db: AsyncSession) -> str:
    """Returns a login code for the frontend to exchange."""
    verify_state(state)
    user_token = await github.exchange_code(code)
    profile = await github.fetch_user(user_token)
    email = await github.fetch_primary_email(user_token)
    user = await upsert_github_user(profile, email, db)
    return create_access_token(
        user.id,
        extra_claims={"purpose": LOGIN_CODE_PURPOSE},
        expires_minutes=LOGIN_CODE_EXPIRE_MINUTES,
    )


async def exchange_login_code(code: str, db: AsyncSession) -> str:
    payload = _decode_purpose(code, LOGIN_CODE_PURPOSE)
    user = await db.get(ProshoUser, uuid.UUID(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return issue_access_token(user.id)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> ProshoUser:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    if credentials is None:
        raise unauthorized
    try:
        payload = decode_access_token_payload(credentials.credentials)
    except JWTError:
        raise unauthorized
    if payload.get("vertical") != TOKEN_VERTICAL:
        raise unauthorized
    user = await db.get(ProshoUser, uuid.UUID(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user
