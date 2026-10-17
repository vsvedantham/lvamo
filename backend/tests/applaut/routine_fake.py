"""A stand-in for a user's routine output: the routine's two tables in a
throwaway schema of the local Postgres, read through a SELECT-only role
(like the read-only Neon role users create), and an in-memory R2 bucket.

Import the fixtures into a test module: `from tests.applaut.routine_fake import *`."""
import hashlib
import uuid
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import asyncpg
import pytest

from app.applaut.routine import source as routine_source
from app.applaut.routine import sync as routine_sync
from app.applaut.routine.source import SourceError, StoredObject
from app.config import settings

__all__ = ["fake_source", "fake_r2", "stored_files", "routine_env", "FakeSource", "FakeStorage",
           "ACCOUNT_ID", "ACCESS_KEY_ID", "SECRET", "PREFIX", "BUCKET", "connect_routine", "add_job_files"]

ACCOUNT_ID = "0123456789abcdef0123456789abcdef"
ACCESS_KEY_ID = "AKIAROUTINETEST0000abcd"
SECRET = "super-secret-r2-value-do-not-leak"
BUCKET = "job-search-automation-documents"
PREFIX = "jobautomationdocs"

JOBS_DDL = """
CREATE TABLE {s}.jobsearchautomationresults (
    uid varchar(160) PRIMARY KEY, company text, role_title text, role_family text, location text, city text,
    requisition_id text, work_mode text, seniority text, german_required text, employment_type text,
    match_score integer, matched_skills text, missing_skills text, salary_range text, posted_date text,
    deadline text, source text, jd_url text, application_url text, notes text,
    first_seen_at timestamptz, last_seen_at timestamptz, first_seen_run_id varchar(20), last_seen_run_id varchar(20),
    times_seen integer, docs_status varchar(20), docs_attempts integer, docs_error text, docs_path text,
    application_status varchar(30)
)"""
RUN_DDL = """
CREATE TABLE {s}.run_tracker (
    run_id text PRIMARY KEY, contract_version integer NOT NULL DEFAULT 1, started_at timestamptz NOT NULL,
    finished_at timestamptz, status text NOT NULL, current_step text, error text, searches_run integer,
    search_budget integer, postings_found integer, postings_assessed integer, jobs_eligible integer,
    jobs_new integer, jobs_updated integer, jobs_rejected integer, docs_done integer, docs_failed integer,
    sources_failed text, summary text, updated_at timestamptz NOT NULL DEFAULT now()
)"""


def _admin_dsn() -> str:
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


class FakeSource:
    def __init__(self):
        tag = uuid.uuid4().hex[:10]
        self.schema = f"routine_src_{tag}"
        self.role = f"applaut_ro_{tag}"
        self.password = uuid.uuid4().hex
        self.host = urlsplit(_admin_dsn()).hostname
        self.port = urlsplit(_admin_dsn()).port or 5432
        self.extra_roles: list[str] = []

    def url_for(self, role: str, password: str) -> str:
        options = quote(f"-csearch_path={self.schema}", safe="")
        return f"postgresql://{role}:{password}@{self.host}:{self.port}/lvamo?sslmode=disable&options={options}"

    @property
    def url(self) -> str:
        return self.url_for(self.role, self.password)

    async def execute(self, sql: str, *args):
        conn = await asyncpg.connect(_admin_dsn())
        try:
            return await conn.execute(sql, *args)
        finally:
            await conn.close()

    async def create(self) -> None:
        s = self.schema
        await self.execute(f"CREATE SCHEMA {s}")
        await self.execute(JOBS_DDL.format(s=s))
        await self.execute(RUN_DDL.format(s=s))
        await self.execute(f"CREATE ROLE {self.role} LOGIN PASSWORD '{self.password}'")
        await self.execute(f"GRANT USAGE ON SCHEMA {s} TO {self.role}")
        await self.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {s} TO {self.role}")

    async def writer_url(self) -> str:
        """A role that can also INSERT into the jobs table (must be refused)."""
        role, pw = f"{self.role}_w", uuid.uuid4().hex
        await self.execute(f"CREATE ROLE {role} LOGIN PASSWORD '{pw}'")
        await self.execute(f"GRANT USAGE ON SCHEMA {self.schema} TO {role}")
        await self.execute(f"GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA {self.schema} TO {role}")
        self.extra_roles.append(role)
        return self.url_for(role, pw)

    async def drop(self) -> None:
        await self.execute(f"DROP SCHEMA IF EXISTS {self.schema} CASCADE")
        for role in [self.role, *self.extra_roles]:
            await self.execute(f"DROP ROLE IF EXISTS {role}")

    async def drop_run_tracker(self) -> None:
        await self.execute(f"DROP TABLE {self.schema}.run_tracker")

    async def add_job(self, uid: str, **fields) -> None:
        now = datetime.now(timezone.utc)
        row = {
            "uid": uid, "company": "Acme GmbH", "role_title": "Data Engineer (m/w/d)", "location": "Berlin, Germany",
            "city": "Berlin", "work_mode": "hybrid", "seniority": "mid", "german_required": "none",
            "employment_type": "full-time", "match_score": 82, "matched_skills": "Python, PySpark, Airflow",
            "missing_skills": "Kafka", "jd_url": f"https://jobs.example.com/{uid}", "application_url": None,
            "notes": "Good fit", "first_seen_at": now, "last_seen_at": now, "first_seen_run_id": "20261017_0808",
            "last_seen_run_id": "20261017_0808", "times_seen": 1, "docs_status": "done", "docs_attempts": 0,
            "docs_path": f"{PREFIX}/{uid}/", "application_status": "new",
        }
        row.update(fields)
        cols = list(row)
        placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "uid")
        await self.execute(
            f"INSERT INTO {self.schema}.jobsearchautomationresults ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT (uid) DO UPDATE SET {updates}",
            *row.values(),
        )

    async def delete_job(self, uid: str) -> None:
        await self.execute(f"DELETE FROM {self.schema}.jobsearchautomationresults WHERE uid = $1", uid)

    async def add_run(self, run_id: str, started_at: datetime, **fields) -> None:
        row = {"run_id": run_id, "contract_version": 1, "started_at": started_at, "status": "running",
               "current_step": "setup", "updated_at": datetime.now(timezone.utc)}
        row.update(fields)
        cols = list(row)
        placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "run_id")
        await self.execute(
            f"INSERT INTO {self.schema}.run_tracker ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT (run_id) DO UPDATE SET {updates}",
            *row.values(),
        )


class FakeStorage:
    """An in-memory R2 bucket with the RoutineStorage interface."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.writable = False
        self.unreachable = False
        self.reads: list[str] = []

    def put(self, key: str, data: bytes) -> None:
        self.objects[key] = data

    async def list(self, prefix: str, max_keys: int = 1000) -> list[StoredObject]:
        if self.unreachable:
            raise SourceError("Can't reach R2: timed out", "r2")
        return [StoredObject(k, hashlib.md5(v).hexdigest(), len(v))
                for k, v in sorted(self.objects.items()) if k.startswith(prefix)][:max_keys]

    async def get(self, key: str, max_bytes: int) -> bytes:
        self.reads.append(key)
        if key not in self.objects:
            raise SourceError(f"{key} not found", "r2")
        data = self.objects[key]
        if len(data) > max_bytes:
            raise SourceError(f"{key.rsplit('/', 1)[-1]} is larger than {max_bytes // 1_000_000} MB", "r2")
        return data

    async def can_write(self, key: str) -> bool:
        return self.writable


def add_job_files(storage: FakeStorage, uid: str, cv: bytes = b"%PDF-1.7 cv v1", cover: bytes = b"%PDF-1.7 cl v1",
                  jd: str = "# Data Engineer\n\nBuild pipelines.") -> None:
    folder = f"{PREFIX}/{uid}/"
    storage.put(folder + "Test_Person_CV.pdf", cv)
    storage.put(folder + "Test_Person_CoverLetter.pdf", cover)
    storage.put(folder + "cv_content.json",
                b'{"headline": "Data engineer, 5 years", "experience": [{"id": "exl", "bullets": ["Built a lakehouse"]}]}')
    storage.put(folder + "cover_letter_content.json",
                b'{"subject": "Application", "salutation": "Dear Hiring Team,", "paragraphs": ["I build pipelines."]}')
    storage.put(folder + "job_description.md", jd.encode())


@pytest.fixture
async def fake_source():
    src = FakeSource()
    await src.create()
    yield src
    await src.drop()


@pytest.fixture
def fake_r2(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(routine_source, "make_storage", lambda creds: storage)
    return storage


@pytest.fixture
def stored_files(monkeypatch):
    """Applaut's own R2, stubbed: {key: (bytes, content_type)}."""
    files: dict[str, tuple[bytes, str]] = {}

    async def store(key, data, content_type):
        files[key] = (data, content_type)

    monkeypatch.setattr(routine_sync, "store_file", store)
    return files


@pytest.fixture(autouse=False)
def routine_env(monkeypatch):
    """Local Postgres is a private host; don't start the dispatcher from requests."""
    monkeypatch.setattr(settings, "applaut_routine_allow_private_hosts", True)
    monkeypatch.setattr("app.applaut.discovery.scheduler.kick_dispatcher", lambda: None)
    if not settings.applaut_credentials_key:
        from cryptography.fernet import Fernet
        monkeypatch.setattr(settings, "applaut_credentials_key", Fernet.generate_key().decode())


def connection_payload(src: FakeSource, **overrides) -> dict:
    payload = {
        "neon_url": src.url, "r2_account_id": ACCOUNT_ID, "r2_bucket": BUCKET, "r2_prefix": PREFIX,
        "r2_access_key_id": ACCESS_KEY_ID, "r2_secret": SECRET,
        "routine_url": "https://claude.ai/code/routines/trig_test", "schedule_cron": "7 6,18 * * *", "timezone": "UTC",
    }
    payload.update(overrides)
    return payload


async def connect_routine(client, headers, src: FakeSource, **overrides):
    r = await client.put("/api/v1/applaut/job-engine", json={"engine": "own_routine"}, headers=headers)
    assert r.status_code == 200, r.text
    r = await client.put("/api/v1/applaut/job-engine/routine", json=connection_payload(src, **overrides), headers=headers)
    return r


__all__ += ["connection_payload"]
