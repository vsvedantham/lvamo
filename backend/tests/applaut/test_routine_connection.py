"""Engine 3's connection: credentials are encrypted and never shown back,
only read-only Neon roles and R2 keys are accepted, and leaving the engine
deletes the stored connection (docs/applaut/JOB_ENGINES_DESIGN.md §6.6, §9)."""
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.applaut.core import credentials
from app.applaut.models.audit_log import AuditLog
from app.applaut.models.engine_task import EngineTask
from app.applaut.models.routine import RoutineConnection
from app.config import settings
from app.db.session import AsyncSessionLocal
from tests.applaut.routine_fake import *  # noqa: F401,F403

API = "/api/v1/applaut/job-engine"


async def _conn(user_id) -> RoutineConnection | None:
    async with AsyncSessionLocal() as db:
        return await db.scalar(select(RoutineConnection).where(RoutineConnection.user_id == user_id))


async def _tasks(profile_id) -> list[EngineTask]:
    async with AsyncSessionLocal() as db:
        return list(await db.scalars(select(EngineTask).where(EngineTask.profile_id == profile_id)))


def test_credentials_round_trip_and_rotation(monkeypatch):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "applaut_credentials_key", old)
    token = credentials.encrypt("postgresql://u:p@h/db")
    assert "p@h" not in token
    monkeypatch.setattr(settings, "applaut_credentials_key", f"{new},{old}")
    assert credentials.decrypt(token) == "postgresql://u:p@h/db"  # old key still decrypts
    rotated = credentials.rotate(token)
    monkeypatch.setattr(settings, "applaut_credentials_key", new)
    assert credentials.decrypt(rotated) == "postgresql://u:p@h/db"


async def test_save_stores_encrypted_and_never_returns_secrets(client, make_user, fake_source, fake_r2, routine_env):
    user, profile, headers = await make_user()
    r = await connect_routine(client, headers, fake_source)
    assert r.status_code == 200, r.text
    body = r.text
    for secret in (fake_source.password, SECRET, ACCESS_KEY_ID):
        assert secret not in body
    data = r.json()
    assert data["engine"] == "own_routine"
    assert data["connection"]["r2_access_key_hint"] == ACCESS_KEY_ID[-4:]
    assert data["connection"]["status"] == "active"
    assert data["connection"]["contract_version"] == 1
    assert data["card"]["state"] == "waiting"

    conn = await _conn(user.id)
    assert fake_source.password not in conn.neon_url_enc and SECRET not in conn.r2_secret_enc
    assert credentials.decrypt(conn.neon_url_enc) == fake_source.url
    assert credentials.decrypt(conn.r2_secret_enc) == SECRET

    # GET never shows them either, and the audit log has no secrets.
    r = await client.get(API, headers=headers)
    assert fake_source.password not in r.text and SECRET not in r.text
    async with AsyncSessionLocal() as db:
        logs = list(await db.scalars(select(AuditLog).where(AuditLog.user_id == user.id)))
    assert "routine.connection_saved" in {l.action for l in logs}
    assert all(SECRET not in str(l.after_state) and fake_source.password not in str(l.after_state) for l in logs)

    # A status check and the first sync are queued.
    kinds = {(t.kind, t.status) for t in await _tasks(profile.id)}
    assert ("routine_check", "pending") in kinds and ("routine_sync", "pending") in kinds


async def test_update_keeps_secrets_not_sent(client, make_user, fake_source, fake_r2, routine_env):
    user, _, headers = await make_user()
    assert (await connect_routine(client, headers, fake_source)).status_code == 200
    r = await client.put(f"{API}/routine", json={"schedule_cron": "30 7 * * *", "timezone": "Europe/Berlin"},
                         headers=headers)
    assert r.status_code == 200, r.text
    conn = await _conn(user.id)
    assert (conn.schedule_cron, conn.timezone) == ("30 7 * * *", "Europe/Berlin")
    assert credentials.decrypt(conn.r2_secret_enc) == SECRET


async def test_refuses_neon_role_that_can_write(client, make_user, fake_source, fake_r2, routine_env):
    user, _, headers = await make_user()
    r = await connect_routine(client, headers, fake_source, neon_url=await fake_source.writer_url())
    assert r.status_code == 422
    failed = {c["key"]: c["message"] for c in r.json()["checks"] if not c["ok"]}
    assert "neon_read_only" in failed and "jobsearchautomationresults" in failed["neon_read_only"]
    assert await _conn(user.id) is None


async def test_refuses_superuser(client, make_user, fake_source, fake_r2, routine_env):
    from urllib.parse import urlsplit
    admin = urlsplit(settings.database_url.replace("+asyncpg", ""))
    url = f"postgresql://{admin.username}:{admin.password}@{admin.hostname}:{admin.port or 5432}/lvamo?sslmode=disable"
    _, _, headers = await make_user()
    r = await connect_routine(client, headers, fake_source, neon_url=url)
    assert r.status_code == 422
    assert any(c["key"] == "neon_read_only" and "superuser" in c["message"] for c in r.json()["checks"])


async def test_refuses_r2_key_that_can_write(client, make_user, fake_source, fake_r2, routine_env):
    user, _, headers = await make_user()
    fake_r2.writable = True
    r = await connect_routine(client, headers, fake_source)
    assert r.status_code == 422
    assert any(c["key"] == "r2_read_only" and not c["ok"] and "can write" in c["message"] for c in r.json()["checks"])
    assert await _conn(user.id) is None


async def test_private_hosts_refused_by_default(client, make_user, fake_source, fake_r2, routine_env, monkeypatch):
    monkeypatch.setattr(settings, "applaut_routine_allow_private_hosts", False)
    _, _, headers = await make_user()
    r = await connect_routine(client, headers, fake_source)
    assert r.status_code == 422
    assert any(c["key"] == "neon_connect" and "isn't a public address" in c["message"] for c in r.json()["checks"])


async def test_test_connection_reports_v0_and_saves_nothing(client, make_user, fake_source, fake_r2, routine_env):
    user, _, headers = await make_user()
    await fake_source.drop_run_tracker()
    r = await client.post(f"{API}/routine/test", json=connection_payload(fake_source), headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["contract_version"] == 0
    assert any(c["key"] == "contract" and "run_tracker" in c["message"] for c in r.json()["checks"])
    assert await _conn(user.id) is None


async def test_bad_input_rejected(client, make_user, fake_source, fake_r2, routine_env):
    _, _, headers = await make_user()
    await client.put(API, json={"engine": "own_routine"}, headers=headers)
    for bad in ({"r2_account_id": "nope"}, {"routine_url": "javascript:alert(1)"},
                {"routine_url": "https://evil.example.com/x"}, {"r2_prefix": "../x"}):
        r = await client.put(f"{API}/routine", json=connection_payload(fake_source, **bad), headers=headers)
        assert r.status_code == 422, bad
    r = await client.put(f"{API}/routine", json=connection_payload(fake_source, schedule_cron="*/5 * * * *"), headers=headers)
    assert r.status_code == 422 and "4 hours" in r.json()["detail"]


async def test_save_requires_engine_choice(client, make_user, fake_source, fake_r2, routine_env):
    _, _, headers = await make_user()
    r = await client.put(f"{API}/routine", json=connection_payload(fake_source), headers=headers)
    assert r.status_code == 409


async def test_switching_away_needs_confirmation_and_deletes_credentials(client, make_user, fake_source, fake_r2, routine_env):
    user, profile, headers = await make_user()
    assert (await connect_routine(client, headers, fake_source)).status_code == 200
    r = await client.put(API, json={"engine": "basic"}, headers=headers)
    assert r.status_code == 409
    assert await _conn(user.id) is not None

    r = await client.put(API, json={"engine": "basic", "confirm_delete_credentials": True}, headers=headers)
    assert r.status_code == 200 and r.json()["engine"] == "basic" and r.json()["connection"] is None
    assert await _conn(user.id) is None
    open_routine = [t for t in await _tasks(profile.id) if t.kind.startswith("routine") and t.status == "pending"]
    assert open_routine == []


async def test_applaut_ai_not_selectable(client, make_user, routine_env):
    _, _, headers = await make_user()
    r = await client.put(API, json={"engine": "applaut_ai"}, headers=headers)
    assert r.status_code == 422


async def test_remove_connection(client, make_user, fake_source, fake_r2, routine_env):
    user, _, headers = await make_user()
    assert (await connect_routine(client, headers, fake_source)).status_code == 200
    assert (await client.delete(f"{API}/routine", headers=headers)).status_code == 204
    assert await _conn(user.id) is None
    assert (await client.delete(f"{API}/routine", headers=headers)).status_code == 404


async def test_other_users_see_nothing(client, make_user, fake_source, fake_r2, routine_env):
    _, _, headers_a = await make_user()
    _, _, headers_b = await make_user()
    assert (await connect_routine(client, headers_a, fake_source)).status_code == 200
    r = await client.get(API, headers=headers_b)
    assert r.json()["connection"] is None
    assert (await client.post(f"{API}/routine/sync-now", headers=headers_b)).status_code == 404
    assert (await client.get(f"{API}/routine/runs", headers=headers_b)).json() == []
