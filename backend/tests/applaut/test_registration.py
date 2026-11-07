"""Sign-up opens with `allow_new_registrations` and closes once `max_users`
accounts exist; the sign-up page reads the same answer."""
import uuid

import pytest
from sqlalchemy import delete, func, select

from app.applaut.models.application_setting import ApplicationSetting
from app.applaut.models.user import User
from app.db.session import AsyncSessionLocal

API = "/api/v1/applaut"
# email-validator refuses .invalid addresses at sign-up, so these use example.com
DOMAIN = "@applaut-signup-test.example.com"


async def _set(name: str, value: str | None) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(ApplicationSetting).where(ApplicationSetting.setting_name == name))
        if value is not None:
            db.add(ApplicationSetting(setting_name=name, value=value))
        await db.commit()


async def _users() -> int:
    async with AsyncSessionLocal() as db:
        return await db.scalar(select(func.count()).select_from(User))


@pytest.fixture(autouse=True)
async def _settings():
    """Keep the local database's own sign-up settings as they were."""
    async with AsyncSessionLocal() as db:
        before = {s.setting_name: s.value for s in await db.scalars(select(ApplicationSetting).where(
            ApplicationSetting.setting_name.in_(("allow_new_registrations", "max_users"))))}
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.email.endswith(DOMAIN)))
        await db.commit()
    for name in ("allow_new_registrations", "max_users"):
        await _set(name, before.get(name))


def _signup() -> dict:
    return {"name": "Asha Rao", "email": f"{uuid.uuid4().hex[:10]}{DOMAIN}", "password": "a-long-password"}


async def _open(client) -> str:
    r = await client.get(f"{API}/settings/allow_new_registrations")
    assert r.status_code == 200
    return r.json()["value"]


async def test_closed(client):
    await _set("allow_new_registrations", "0")
    await _set("max_users", None)
    assert await _open(client) == "0"
    assert (await client.post(f"{API}/auth/register", json=_signup())).status_code == 403


async def test_open_without_cap(client):
    await _set("allow_new_registrations", "1")
    await _set("max_users", None)
    assert await _open(client) == "1"
    assert (await client.post(f"{API}/auth/register", json=_signup())).status_code == 201


async def test_cap_closes_signup_at_the_limit(client):
    await _set("allow_new_registrations", "1")
    await _set("max_users", str(await _users() + 2))  # room for two more
    for _ in range(2):
        assert await _open(client) == "1"
        r = await client.post(f"{API}/auth/register", json=_signup())
        assert r.status_code == 201, r.text
    assert await _open(client) == "0"
    r = await client.post(f"{API}/auth/register", json=_signup())
    assert r.status_code == 403
    assert "closed" in r.json()["detail"]
    # a place opens again if an account goes
    async with AsyncSessionLocal() as db:
        one = await db.scalar(select(User).where(User.email.endswith(DOMAIN)).limit(1))
        await db.delete(one)
        await db.commit()
    assert await _open(client) == "1"


async def test_broken_cap_keeps_signup_closed(client):
    await _set("allow_new_registrations", "1")
    await _set("max_users", "five")
    assert await _open(client) == "0"
    assert (await client.post(f"{API}/auth/register", json=_signup())).status_code == 403
