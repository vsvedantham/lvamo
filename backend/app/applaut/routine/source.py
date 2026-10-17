"""Read-only access to a user's routine output: their Neon Postgres and their
Cloudflare R2 bucket (docs/applaut/JOB_ENGINES_DESIGN.md §6.2, §6.6).

Everything here only reads. Credentials are checked on save: a Neon role that
can write anything, or an R2 key that can write to the bucket, is refused.
Everything read back is untrusted text."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import ssl as ssl_lib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from urllib.parse import parse_qs, unquote, urlsplit

import asyncpg

from app.config import settings

JOBS_TABLE = "jobsearchautomationresults"
RUN_TABLE = "run_tracker"
CONNECT_TIMEOUT_SECONDS = 15
STATEMENT_TIMEOUT = "30s"
MAX_JOB_ROWS = 2000  # §6.9: a sync reads at most this many rows


class SourceError(Exception):
    """Something about the user's Neon or R2 that they need to fix. The
    message is shown to them as is, so it never contains a secret."""

    def __init__(self, message: str, where: str = "neon"):
        super().__init__(message)
        self.where = where


class NotReadOnly(SourceError):
    pass


# ----------------------------------------------------------------------------- Neon

@dataclass
class NeonTarget:
    host: str
    port: int
    user: str
    password: str
    database: str
    sslmode: str
    options: str | None


def parse_neon_url(url: str) -> NeonTarget:
    url = (url or "").strip()
    parts = urlsplit(url)
    if parts.scheme not in ("postgres", "postgresql"):
        raise SourceError("The Neon connection string must start with postgresql://")
    if not parts.hostname or not parts.username:
        raise SourceError("The Neon connection string needs a user and a host")
    query = {k: v[-1] for k, v in parse_qs(parts.query).items()}
    sslmode = query.get("sslmode") or ("prefer" if _is_local_name(parts.hostname) else "require")
    if sslmode not in ("disable", "allow", "prefer", "require", "verify-ca", "verify-full"):
        raise SourceError(f"Unsupported sslmode {sslmode!r} in the Neon connection string")
    try:
        port = parts.port or 5432
    except ValueError:
        raise SourceError("The port in the Neon connection string isn't a number") from None
    return NeonTarget(
        host=parts.hostname,
        port=port,
        user=unquote(parts.username),
        password=unquote(parts.password or ""),
        database=unquote(parts.path.lstrip("/")) or "neondb",
        sslmode=sslmode,
        # Passed through as the `options` startup parameter: Neon uses it for
        # `endpoint=…`, and a test can set `-c search_path=…`.
        options=query.get("options"),
    )


def _is_local_name(host: str) -> bool:
    return host in ("localhost", "postgres") or host.endswith(".local")


async def ensure_public_host(host: str, where: str) -> None:
    """Refuse hosts that resolve to private, loopback or link-local
    addresses, so a connection can't be pointed at Applaut's own network."""
    if settings.applaut_routine_allow_private_hosts:
        return
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    except socket.gaierror:
        raise SourceError(f"The host {host} can't be found", where) from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise SourceError(f"The host {host} isn't a public address", where)


def neon_host(url: str) -> str:
    return parse_neon_url(url).host


async def connect_neon(url: str) -> asyncpg.Connection:
    target = parse_neon_url(url)
    await ensure_public_host(target.host, "neon")
    ssl: Any = target.sslmode
    if target.sslmode == "verify-full":
        ssl = ssl_lib.create_default_context()
    try:
        return await asyncpg.connect(
            host=target.host, port=target.port, user=target.user, password=target.password,
            database=target.database, ssl=ssl, timeout=CONNECT_TIMEOUT_SECONDS,
            # Works through Neon's pooler (PgBouncer, transaction mode) too.
            statement_cache_size=0,
            server_settings={"options": target.options} if target.options else None,
        )
    except asyncpg.InvalidPasswordError:
        raise SourceError("Neon refused the user name or password") from None
    except asyncpg.InvalidCatalogNameError:
        raise SourceError(f"The database {target.database!r} doesn't exist") from None
    except (OSError, asyncio.TimeoutError) as exc:
        raise SourceError(f"Can't reach {target.host}: {_short(exc)}") from None
    except asyncpg.PostgresError as exc:
        raise SourceError(f"Neon refused the connection: {_short(exc)}") from None


def _short(exc: BaseException) -> str:
    text = str(exc).strip() or type(exc).__name__
    return text.splitlines()[0][:300]


class NeonReader:
    """One short read-only session on the user's Neon. Use as
    `async with NeonReader(url) as src: ...`; every query runs in a
    READ ONLY transaction with a statement timeout."""

    def __init__(self, url: str):
        self.url = url
        self.conn: asyncpg.Connection | None = None

    async def __aenter__(self) -> "NeonReader":
        self.conn = await connect_neon(self.url)
        return self

    async def __aexit__(self, *exc) -> None:
        if self.conn is not None:
            try:
                await asyncio.wait_for(self.conn.close(), timeout=5)
            except Exception:  # noqa: BLE001
                self.conn.terminate()

    async def _read(self, fn):
        try:
            async with self.conn.transaction(readonly=True):
                await self.conn.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
                return await fn(self.conn)
        except SourceError:
            raise
        except (OSError, asyncio.TimeoutError) as exc:
            raise SourceError(f"Lost the connection to Neon: {_short(exc)}") from None
        except asyncpg.PostgresError as exc:
            raise SourceError(f"Neon query failed: {_short(exc)}") from None

    async def check_read_only(self) -> str:
        """Raise NotReadOnly unless this role can only read. Returns the role name."""
        async def q(conn):
            role = await conn.fetchrow(
                "SELECT current_user AS name, rolsuper, rolcreaterole, rolcreatedb "
                "FROM pg_roles WHERE rolname = current_user"
            )
            writable = await conn.fetch("""
                SELECT n.nspname AS schema, c.relname AS name
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
                  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
                  AND n.nspname NOT LIKE 'pg\\_toast%'
                  AND (has_table_privilege(c.oid, 'INSERT') OR has_table_privilege(c.oid, 'UPDATE')
                       OR has_table_privilege(c.oid, 'DELETE') OR has_table_privilege(c.oid, 'TRUNCATE'))
                ORDER BY 1, 2 LIMIT 5
            """)
            return role, writable

        role, writable = await self._read(q)
        name = role["name"] if role else "?"
        powers = [label for flag, label in (("rolsuper", "is a superuser"), ("rolcreaterole", "can create roles"),
                                            ("rolcreatedb", "can create databases")) if role and role[flag]]
        if powers:
            raise NotReadOnly(f"The Neon role {name} {' and '.join(powers)}. "
                              "Please connect with a read-only role (see the setup guide).")
        if writable:
            tables = ", ".join(f"{r['schema']}.{r['name']}" for r in writable)
            raise NotReadOnly(f"The Neon role {name} can change data in {tables}. "
                              "Please connect with a read-only role (SELECT only).")
        return name

    async def contract_version(self) -> int:
        """0 = no run_tracker table (jobs only); otherwise its highest contract_version."""
        async def q(conn):
            jobs = await conn.fetchval("SELECT to_regclass($1)::text", JOBS_TABLE)
            if jobs is None:
                raise SourceError(f"The table {JOBS_TABLE} wasn't found in this database")
            if not await conn.fetchval("SELECT has_table_privilege(to_regclass($1), 'SELECT')", JOBS_TABLE):
                raise SourceError(f"This role can't read {JOBS_TABLE}; grant it SELECT")
            if await conn.fetchval("SELECT to_regclass($1)::text", RUN_TABLE) is None:
                return 0
            if not await conn.fetchval("SELECT has_table_privilege(to_regclass($1), 'SELECT')", RUN_TABLE):
                raise SourceError(f"This role can't read {RUN_TABLE}; grant it SELECT")
            return int(await conn.fetchval(f"SELECT COALESCE(MAX(contract_version), 1) FROM {RUN_TABLE}"))
        return await self._read(q)

    async def count_jobs(self) -> int:
        return await self._read(lambda conn: conn.fetchval(f"SELECT count(*) FROM {JOBS_TABLE}"))

    async def runs_since(self, since: datetime, limit: int = 50) -> list[dict]:
        async def q(conn):
            rows = await conn.fetch(
                f"SELECT * FROM {RUN_TABLE} WHERE started_at >= $1 OR updated_at >= $1 "
                "ORDER BY started_at DESC LIMIT $2",
                since, limit,
            )
            return [dict(r) for r in rows]
        return await self._read(q)

    async def latest_job_seen_at(self) -> datetime | None:
        return await self._read(lambda conn: conn.fetchval(f"SELECT MAX(last_seen_at) FROM {JOBS_TABLE}"))

    async def job_index(self) -> tuple[list[dict], int]:
        """(uid, last_seen_at, docs_status) of the newest MAX_JOB_ROWS jobs, and the total count."""
        async def q(conn):
            total = await conn.fetchval(f"SELECT count(*) FROM {JOBS_TABLE}")
            rows = await conn.fetch(
                f"SELECT uid, last_seen_at, docs_status FROM {JOBS_TABLE} "
                "ORDER BY last_seen_at DESC NULLS LAST LIMIT $1",
                MAX_JOB_ROWS,
            )
            return [dict(r) for r in rows], int(total)
        return await self._read(q)

    async def jobs(self, uids: list[str]) -> list[dict]:
        if not uids:
            return []
        async def q(conn):
            return [dict(r) for r in await conn.fetch(f"SELECT * FROM {JOBS_TABLE} WHERE uid = ANY($1::text[])", uids)]
        return await self._read(q)


# ----------------------------------------------------------------------------- R2

@dataclass
class R2Credentials:
    account_id: str
    bucket: str
    prefix: str
    access_key_id: str
    secret: str


@dataclass
class StoredObject:
    key: str
    etag: str
    size: int


@dataclass
class R2Report:
    objects_seen: int = 0
    notes: list[str] = field(default_factory=list)


class RoutineStorage(Protocol):
    async def list(self, prefix: str, max_keys: int = 1000) -> list[StoredObject]: ...
    async def get(self, key: str, max_bytes: int) -> bytes: ...
    async def can_write(self, key: str) -> bool: ...


class R2RoutineStorage:
    """boto3 against the user's bucket, run in a thread."""

    def __init__(self, creds: R2Credentials):
        import boto3
        from botocore.config import Config
        self.bucket = creds.bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{creds.account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=creds.access_key_id,
            aws_secret_access_key=creds.secret,
            config=Config(signature_version="s3v4", connect_timeout=10, read_timeout=30,
                          retries={"max_attempts": 3, "mode": "standard"}),
            region_name="auto",
        )

    @staticmethod
    def _explain(exc: Exception) -> SourceError:
        from botocore.exceptions import ClientError
        if isinstance(exc, ClientError):
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("AccessDenied", "403", "Forbidden"):
                return SourceError("R2 denied access with this key", "r2")
            if code in ("NoSuchBucket", "404"):
                return SourceError("The R2 bucket wasn't found", "r2")
            if code in ("InvalidAccessKeyId", "SignatureDoesNotMatch", "Unauthorized", "401"):
                return SourceError("R2 rejected the access key id or secret", "r2")
            return SourceError(f"R2 error: {code or _short(exc)}", "r2")
        return SourceError(f"Can't reach R2: {_short(exc)}", "r2")

    async def list(self, prefix: str, max_keys: int = 1000) -> list[StoredObject]:
        def run():
            out, token = [], None
            while True:
                kw = {"Bucket": self.bucket, "Prefix": prefix, "MaxKeys": min(max_keys, 1000)}
                if token:
                    kw["ContinuationToken"] = token
                resp = self.client.list_objects_v2(**kw)
                for o in resp.get("Contents", []):
                    out.append(StoredObject(o["Key"], o.get("ETag", "").strip('"'), int(o.get("Size", 0))))
                token = resp.get("NextContinuationToken")
                if not token or len(out) >= max_keys:
                    return out[:max_keys]
        try:
            return await asyncio.to_thread(run)
        except Exception as exc:  # noqa: BLE001
            raise self._explain(exc) from None

    async def get(self, key: str, max_bytes: int) -> bytes:
        def run():
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
            if int(resp.get("ContentLength") or 0) > max_bytes:
                resp["Body"].close()
                raise SourceError(f"{key.rsplit('/', 1)[-1]} is larger than {max_bytes // 1_000_000} MB", "r2")
            return resp["Body"].read(max_bytes + 1)
        try:
            data = await asyncio.to_thread(run)
        except SourceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._explain(exc) from None
        if len(data) > max_bytes:
            raise SourceError(f"{key.rsplit('/', 1)[-1]} is larger than {max_bytes // 1_000_000} MB", "r2")
        return data

    async def can_write(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        def run():
            try:
                self.client.put_object(Bucket=self.bucket, Key=key, Body=b"")
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in ("AccessDenied", "403", "Forbidden", "Unauthorized"):
                    return False
                raise
            try:
                self.client.delete_object(Bucket=self.bucket, Key=key)
            except Exception:  # noqa: BLE001  (refusing the key matters more)
                pass
            return True
        try:
            return await asyncio.to_thread(run)
        except Exception as exc:  # noqa: BLE001
            raise self._explain(exc) from None


def make_storage(creds: R2Credentials) -> RoutineStorage:
    """The one place a storage client is built (tests replace it)."""
    return R2RoutineStorage(creds)


async def check_r2(creds: R2Credentials) -> R2Report:
    """Bucket listable under the prefix, and the key can't write (§6.6)."""
    storage = make_storage(creds)
    seen = await storage.list(f"{creds.prefix}/", max_keys=5)
    if await storage.can_write(f"applaut-permission-check/{uuid.uuid4().hex}"):
        raise NotReadOnly("This key can write to your bucket. Please create a read-only key "
                          "(Object Read only, for this bucket).", "r2")
    report = R2Report(objects_seen=len(seen))
    if not seen:
        report.notes.append(f"No files under {creds.prefix}/ yet")
    return report
