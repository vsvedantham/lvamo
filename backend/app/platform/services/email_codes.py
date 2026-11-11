"""Email one-time codes (OTP) for sign-up and password reset, shared by every
vertical.

Which verticals use them is the `otp_verification_enabled` row in
`platform.settings`: a comma-separated list such as `applaut,jobref`. A
vertical not listed there sends no codes and signs up exactly as before.

The platform never imports a vertical. Each vertical hands its own account
lookups to `register_vertical()` (wired in `main.py`), and its sign-up
endpoint calls `require_code()` itself.

Rules: 6-digit codes, stored as an HMAC (never the code itself), valid for
10 minutes and 5 tries. A new code retires the previous one. One code a
minute and 5 an hour per (vertical, email, purpose).
"""
import hashlib
import hmac
import logging
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.email import EmailSendError, OutgoingEmail, get_email_sender
from app.platform.models.email_code import EmailCode
from app.platform.models.platform_setting import PlatformSetting

log = logging.getLogger(__name__)

SETTING_NAME = "otp_verification_enabled"
PURPOSES = ("register", "reset_password")
CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
RESEND_AFTER = timedelta(seconds=60)
MAX_SENDS_PER_HOUR = 5


@dataclass(frozen=True)
class VerticalAccounts:
    """What the platform needs from a vertical's own users table."""

    display_name: str  # shown in the email, e.g. "Applaut"
    # (db, email) -> does an account with this email exist? Case-insensitive.
    account_exists: Callable[[AsyncSession, str], Awaitable[bool]]
    # (db, email, new_password) -> False if no such account. Must not commit.
    set_password: Callable[[AsyncSession, str, str], Awaitable[bool]]


_verticals: dict[str, VerticalAccounts] = {}


def register_vertical(key: str, accounts: VerticalAccounts) -> None:
    _verticals[key] = accounts


def normalize(email: str) -> str:
    return email.strip().lower()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def enabled_verticals(db: AsyncSession) -> set[str]:
    value = await db.scalar(select(PlatformSetting.value).where(PlatformSetting.setting_name == SETTING_NAME))
    return {v.strip().lower() for v in (value or "").split(",") if v.strip()}


async def is_enabled(db: AsyncSession, vertical: str) -> bool:
    return vertical in _verticals and vertical in await enabled_verticals(db)


async def enabled_accounts(db: AsyncSession, vertical: str) -> VerticalAccounts:
    """The vertical's account hooks, or 404 when codes are off for it."""
    if not await is_enabled(db, vertical):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Email codes are not enabled for this product")
    return _verticals[vertical]


def _hash(vertical: str, email: str, purpose: str, code: str) -> str:
    msg = f"{vertical}:{email}:{purpose}:{code}".encode()
    return hmac.new(settings.secret_key.encode(), msg, hashlib.sha256).hexdigest()


def _message(product: str, email: str, purpose: str, code: str) -> OutgoingEmail:
    minutes = int(CODE_TTL.total_seconds() // 60)
    if purpose == "register":
        subject = f"{code} is your {product} verification code"
        lead = f"Use this code to finish creating your {product} account:"
    else:
        subject = f"{code} is your {product} password reset code"
        lead = f"Use this code to set a new password for your {product} account:"
    ignore = "If you didn't ask for this, you can ignore this email. Nothing changes without the code."
    text = (f"{lead}\n\n    {code}\n\nThe code works for {minutes} minutes.\n\n{ignore}\n\n"
            f"— LVAMO ({product})\n")
    html = f"""<!doctype html><html><body style="margin:0;padding:24px;background:#f5f5f7;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1d1d1f">
<div style="max-width:440px;margin:0 auto;background:#fff;border-radius:12px;padding:28px">
<p style="margin:0 0 4px;font-size:12px;font-weight:700;letter-spacing:.12em;color:#6b5cff">LVAMO · {escape(product).upper()}</p>
<p style="margin:16px 0;font-size:15px;line-height:1.5">{escape(lead)}</p>
<p style="margin:0 0 16px;font-size:32px;font-weight:700;letter-spacing:.3em;font-family:Menlo,Consolas,monospace">{code}</p>
<p style="margin:0 0 16px;font-size:13px;color:#6e6e73">The code works for {minutes} minutes.</p>
<p style="margin:0;font-size:13px;color:#6e6e73">{escape(ignore)}</p>
</div></body></html>"""
    return OutgoingEmail(to=email, subject=subject, text=text, html=html)


def _too_many(detail: str, retry_after: int) -> HTTPException:
    return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail,
                         headers={"Retry-After": str(max(retry_after, 1))})


async def send_code(
    db: AsyncSession,
    vertical: str,
    email: str,
    purpose: str,
    *,
    deliver: bool = True,
    requester_ip: str | None = None,
) -> None:
    """Issues a new code and emails it. With deliver=False (password reset
    for an address with no account) the row is still written, so the resend
    limits behave the same and the response can't reveal which addresses
    have accounts, but nothing is sent. Commits."""
    if purpose not in PURPOSES:
        raise ValueError(f"unknown purpose {purpose!r}")
    accounts = _verticals[vertical]
    email = normalize(email)
    now = _now()

    recent = list(await db.scalars(
        select(EmailCode.created_at)
        .where(EmailCode.vertical == vertical, EmailCode.email == email, EmailCode.purpose == purpose,
               EmailCode.created_at > now - timedelta(hours=1))
        .order_by(EmailCode.created_at.desc())
    ))
    if recent and now - recent[0] < RESEND_AFTER:
        wait = int((RESEND_AFTER - (now - recent[0])).total_seconds()) + 1
        raise _too_many(f"Please wait {wait} seconds before asking for another code.", wait)
    if len(recent) >= MAX_SENDS_PER_HOUR:
        wait = int((recent[-1] + timedelta(hours=1) - now).total_seconds()) + 1
        raise _too_many("Too many codes asked for this email. Please try again later.", wait)

    # A new code retires any earlier one still open.
    await db.execute(
        update(EmailCode)
        .where(EmailCode.vertical == vertical, EmailCode.email == email, EmailCode.purpose == purpose,
               EmailCode.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    code = f"{secrets.randbelow(10**6):06d}"
    db.add(EmailCode(
        vertical=vertical, email=email, purpose=purpose,
        code_hash=_hash(vertical, email, purpose, code),
        expires_at=now + CODE_TTL, created_at=now,
        requester_ip=(requester_ip or "")[:64] or None,
    ))
    await db.flush()

    if deliver:
        try:
            await get_email_sender().send(_message(accounts.display_name, email, purpose, code))
        except EmailSendError as exc:
            await db.rollback()
            log.error("email code for %s/%s not sent: %s", vertical, purpose, exc)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="We couldn't send the email just now. Please try again in a few minutes.")
    await db.commit()


async def consume_code(db: AsyncSession, vertical: str, email: str, purpose: str, code: str | None) -> None:
    """Checks the code and marks it used, without committing: the caller
    commits it together with what the code allowed (the new account, the new
    password), so a failure after this leaves the code usable. A wrong code
    counts one attempt, committed straight away."""
    email = normalize(email)
    code = (code or "").strip()
    now = _now()
    row = await db.scalar(
        select(EmailCode)
        .where(EmailCode.vertical == vertical, EmailCode.email == email, EmailCode.purpose == purpose,
               EmailCode.consumed_at.is_(None))
        .order_by(EmailCode.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Enter the code we emailed you.")
    if row is None or row.expires_at <= now or row.attempts >= MAX_ATTEMPTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="This code has expired. Ask for a new one.")
    if not hmac.compare_digest(row.code_hash, _hash(vertical, email, purpose, code)):
        row.attempts += 1
        left = MAX_ATTEMPTS - row.attempts
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"That code is not right. {left} {'try' if left == 1 else 'tries'} left."
                    if left else "That code is not right, and this one is now used up. Ask for a new one."),
        )
    row.consumed_at = now


async def require_code(db: AsyncSession, vertical: str, email: str, purpose: str, code: str | None) -> bool:
    """For a vertical's own sign-up: when codes are on for it, the code must
    be right (raises otherwise). Returns whether a code was checked, i.e.
    whether the email is now proven."""
    if not await is_enabled(db, vertical):
        return False
    await consume_code(db, vertical, email, purpose, code)
    return True
