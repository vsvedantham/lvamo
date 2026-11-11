"""Email codes (platform): sign-up codes for Applaut and Jobref employees,
password reset for both, switched per vertical by the
`otp_verification_enabled` platform setting. No real mail: a console sender
catches every message."""
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select, update

from app.applaut.models.application_setting import ApplicationSetting
from app.applaut.models.user import User
from app.core import rate_limit
from app.core.email import ConsoleEmailSender, set_email_sender
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.jobref.models.jobref_user import JobrefUser
from app.platform.models.email_code import EmailCode
from app.platform.models.platform_setting import PlatformSetting

PLATFORM = "/api/v1/platform/auth"
APPLAUT = "/api/v1/applaut"
JOBREF = "/api/v1/jobref"
DOMAIN = "@otp-test.example.com"  # email-validator refuses .invalid at sign-up
SETTING = "otp_verification_enabled"


async def _set_platform(value: str | None) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(PlatformSetting).where(PlatformSetting.setting_name == SETTING))
        if value is not None:
            db.add(PlatformSetting(setting_name=SETTING, value=value, is_public=True))
        await db.commit()


async def _set_applaut(name: str, value: str | None) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(ApplicationSetting).where(ApplicationSetting.setting_name == name))
        if value is not None:
            db.add(ApplicationSetting(setting_name=name, value=value))
        await db.commit()


@pytest.fixture(autouse=True)
async def _env():
    """Codes on for applaut+jobref, Applaut sign-up open, a console sender;
    the local database's own settings come back afterwards."""
    async with AsyncSessionLocal() as db:
        platform_before = await db.scalar(select(PlatformSetting).where(PlatformSetting.setting_name == SETTING))
        platform_before = (platform_before.value, platform_before.description) if platform_before else None
        applaut_before = {s.setting_name: s.value for s in await db.scalars(select(ApplicationSetting).where(
            ApplicationSetting.setting_name.in_(("allow_new_registrations", "max_users"))))}
    await _set_platform("applaut,jobref")
    await _set_applaut("allow_new_registrations", "1")
    await _set_applaut("max_users", None)
    rate_limit.reset()
    sender = ConsoleEmailSender()
    set_email_sender(sender)
    yield sender
    set_email_sender(None)
    rate_limit.reset()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(EmailCode).where(EmailCode.email.endswith(DOMAIN)))
        await db.execute(delete(User).where(User.email.endswith(DOMAIN)))
        await db.execute(delete(JobrefUser).where(JobrefUser.email.endswith(DOMAIN)))
        await db.execute(delete(PlatformSetting).where(PlatformSetting.setting_name == SETTING))
        if platform_before:
            db.add(PlatformSetting(setting_name=SETTING, value=platform_before[0],
                                   description=platform_before[1], is_public=True))
        await db.commit()
    for name in ("allow_new_registrations", "max_users"):
        await _set_applaut(name, applaut_before.get(name))


def _email() -> str:
    return f"{uuid.uuid4().hex[:10]}{DOMAIN}"


def _last_code(sender: ConsoleEmailSender, to: str) -> str:
    message = [m for m in sender.outbox if m.to == to][-1]
    return re.search(r"\b(\d{6})\b", message.text).group(1)


async def _ask(client, vertical: str, email: str, purpose: str = "register"):
    return await client.post(f"{PLATFORM}/email-codes", json={"vertical": vertical, "email": email, "purpose": purpose})


def _applaut_signup(email: str, code: str | None = None) -> dict:
    body = {"name": "Asha Rao", "email": email, "password": "a-long-password"}
    if code is not None:
        body["email_code"] = code
    return body


def _jobref_employee(email: str, code: str | None = None) -> dict:
    body = {
        "user_type": "employee", "first_name": "Asha", "last_name": "Rao", "email": email,
        "phone": "+49 151 2345678", "password": "a-long-password", "domain": "Data Engineering",
        "employee": {
            "company_name": "Test GmbH", "working_since": "2022-01-01", "daily_referral_view_cap": "up_to_5",
            "refer_frequency": "weekly", "referral_capacity": "up_to_5",
            "company_careers_url": "https://example.com/careers",
        },
    }
    if code is not None:
        body["email_code"] = code
    return body


async def _applaut_user(email: str, password: str = "old-password-1") -> None:
    async with AsyncSessionLocal() as db:
        db.add(User(email=email, name="Asha Rao", password_hash=hash_password(password)))
        await db.commit()


# --- switched off ----------------------------------------------------------

async def test_off_means_no_codes_and_signup_as_before(client, _env):
    await _set_platform("jobref")  # applaut not listed
    email = _email()
    assert (await _ask(client, "applaut", email)).status_code == 404
    r = await client.post(f"{APPLAUT}/auth/register", json=_applaut_signup(email))
    assert r.status_code == 201, r.text
    assert _env.outbox == []
    async with AsyncSessionLocal() as db:
        assert (await db.scalar(select(User).where(User.email == email))).is_verified is False


async def test_missing_setting_is_off(client):
    await _set_platform(None)
    assert (await _ask(client, "applaut", _email())).status_code == 404


async def test_unwired_vertical_is_refused(client):
    await _set_platform("applaut,jobref,prosho")
    assert (await _ask(client, "prosho", _email())).status_code == 404


async def test_public_setting_is_readable(client):
    r = await client.get("/api/v1/platform/settings/otp_verification_enabled")
    assert r.status_code == 200 and r.json()["value"] == "applaut,jobref"


# --- Applaut sign-up -------------------------------------------------------

async def test_applaut_signup_needs_the_emailed_code(client, _env):
    email = _email()
    r = await _ask(client, "applaut", email)
    assert r.status_code == 202, r.text
    assert r.json() == {"resend_after_seconds": 60, "expires_in_seconds": 600}
    message = _env.outbox[-1]
    assert message.to == email and "Applaut verification code" in message.subject
    code = _last_code(_env, email)

    r = await client.post(f"{APPLAUT}/auth/register", json=_applaut_signup(email))
    assert r.status_code == 400 and "code" in r.json()["detail"]
    wrong = "000000" if code != "000000" else "111111"
    r = await client.post(f"{APPLAUT}/auth/register", json=_applaut_signup(email, wrong))
    assert r.status_code == 400 and "4 tries left" in r.json()["detail"]

    r = await client.post(f"{APPLAUT}/auth/register", json=_applaut_signup(email, code))
    assert r.status_code == 201, r.text
    assert r.json()["access_token"]
    async with AsyncSessionLocal() as db:
        assert (await db.scalar(select(User).where(User.email == email))).is_verified is True
        row = await db.scalar(select(EmailCode).where(EmailCode.email == email))
        assert row.consumed_at is not None and row.code_hash != code


async def test_code_is_bound_to_vertical_and_email(client, _env):
    email, other = _email(), _email()
    await _ask(client, "jobref", email)
    code = _last_code(_env, email)
    # a Jobref code doesn't open Applaut, nor does it work for another address
    assert (await client.post(f"{APPLAUT}/auth/register", json=_applaut_signup(email, code))).status_code == 400
    assert (await client.post(f"{APPLAUT}/auth/register", json=_applaut_signup(other, code))).status_code == 400


async def test_existing_email_gets_no_signup_code(client, _env):
    email = _email()
    await _applaut_user(email)
    r = await _ask(client, "applaut", email.upper())
    assert r.status_code == 409
    assert _env.outbox == []


async def test_resend_waits_a_minute_and_retires_the_old_code(client, _env):
    email = _email()
    await _ask(client, "applaut", email)
    first = _last_code(_env, email)
    r = await _ask(client, "applaut", email)
    assert r.status_code == 429 and "Retry-After" in r.headers
    # pretend the minute has passed
    async with AsyncSessionLocal() as db:
        await db.execute(update(EmailCode).where(EmailCode.email == email)
                         .values(created_at=datetime.now(timezone.utc) - timedelta(seconds=61)))
        await db.commit()
    assert (await _ask(client, "applaut", email)).status_code == 202
    second = _last_code(_env, email)
    if first != second:
        r = await client.post(f"{APPLAUT}/auth/register", json=_applaut_signup(email, first))
        assert r.status_code == 400
    r = await client.post(f"{APPLAUT}/auth/register", json=_applaut_signup(email, second))
    assert r.status_code == 201, r.text


async def test_five_wrong_tries_use_the_code_up(client, _env):
    email = _email()
    await _ask(client, "applaut", email)
    code = _last_code(_env, email)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert (await client.post(f"{APPLAUT}/auth/register", json=_applaut_signup(email, wrong))).status_code == 400
    r = await client.post(f"{APPLAUT}/auth/register", json=_applaut_signup(email, code))
    assert r.status_code == 400 and "expired" in r.json()["detail"]


async def test_expired_code_is_refused(client, _env):
    email = _email()
    await _ask(client, "applaut", email)
    code = _last_code(_env, email)
    async with AsyncSessionLocal() as db:
        await db.execute(update(EmailCode).where(EmailCode.email == email)
                         .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await db.commit()
    r = await client.post(f"{APPLAUT}/auth/register", json=_applaut_signup(email, code))
    assert r.status_code == 400 and "expired" in r.json()["detail"]


async def test_closed_signup_still_wins(client, _env):
    email = _email()
    await _ask(client, "applaut", email)
    code = _last_code(_env, email)
    await _set_applaut("allow_new_registrations", "0")
    assert (await client.post(f"{APPLAUT}/auth/register", json=_applaut_signup(email, code))).status_code == 403


# --- Jobref sign-up --------------------------------------------------------

async def test_jobref_employee_signup_needs_the_code(client, _env):
    email = _email()
    assert (await client.post(f"{JOBREF}/auth/register", json=_jobref_employee(email))).status_code == 400
    await _ask(client, "jobref", email)
    assert "Jobref verification code" in _env.outbox[-1].subject
    r = await client.post(f"{JOBREF}/auth/register", json=_jobref_employee(email, _last_code(_env, email)))
    assert r.status_code == 201, r.text


async def test_jobref_off_keeps_employee_signup_as_before(client):
    await _set_platform("applaut")
    r = await client.post(f"{JOBREF}/auth/register", json=_jobref_employee(_email()))
    assert r.status_code == 201, r.text


# --- password reset --------------------------------------------------------

async def test_applaut_password_reset(client, _env):
    email = _email()
    await _applaut_user(email)
    r = await _ask(client, "applaut", email, "reset_password")
    assert r.status_code == 202
    assert "password reset code" in _env.outbox[-1].subject
    code = _last_code(_env, email)

    body = {"vertical": "applaut", "email": email, "code": "x" + code[1:], "new_password": "brand-new-password"}
    assert (await client.post(f"{PLATFORM}/password-reset", json=body)).status_code == 400
    body["code"] = code
    r = await client.post(f"{PLATFORM}/password-reset", json=body)
    assert r.status_code == 204, r.text
    # the code works once
    assert (await client.post(f"{PLATFORM}/password-reset", json=body)).status_code == 400

    old = await client.post(f"{APPLAUT}/auth/login", json={"email": email, "password": "old-password-1"})
    new = await client.post(f"{APPLAUT}/auth/login", json={"email": email, "password": "brand-new-password"})
    assert old.status_code == 401 and new.status_code == 200
    async with AsyncSessionLocal() as db:
        assert (await db.scalar(select(User).where(User.email == email))).is_verified is True


async def test_reset_for_unknown_email_looks_the_same_but_sends_nothing(client, _env):
    email = _email()
    r = await _ask(client, "applaut", email, "reset_password")
    assert r.status_code == 202
    assert _env.outbox == []
    assert (await _ask(client, "applaut", email, "reset_password")).status_code == 429  # same limits as a real one


async def test_jobref_password_reset(client, _env):
    email = _email()
    await _set_platform("applaut")  # sign up without a code first
    assert (await client.post(f"{JOBREF}/auth/register", json=_jobref_employee(email))).status_code == 201
    await _set_platform("applaut,jobref")
    await _ask(client, "jobref", email, "reset_password")
    body = {"vertical": "jobref", "email": email, "code": _last_code(_env, email), "new_password": "brand-new-password"}
    assert (await client.post(f"{PLATFORM}/password-reset", json=body)).status_code == 204
    r = await client.post(f"{JOBREF}/auth/login", json={"email": email, "password": "brand-new-password"})
    assert r.status_code == 200


async def test_reset_refused_when_vertical_is_off(client, _env):
    email = _email()
    await _applaut_user(email)
    await _set_platform("jobref")
    assert (await _ask(client, "applaut", email, "reset_password")).status_code == 404
    body = {"vertical": "applaut", "email": email, "code": "123456", "new_password": "brand-new-password"}
    assert (await client.post(f"{PLATFORM}/password-reset", json=body)).status_code == 404


async def test_per_ip_limit(client):
    for _ in range(5):
        await _ask(client, "applaut", _email())
    assert (await _ask(client, "applaut", _email())).status_code == 429
