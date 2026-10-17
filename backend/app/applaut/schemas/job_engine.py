import re
import uuid
from datetime import datetime
from typing import Literal, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

from app.applaut.models.enums import JobEngineEnum

_ACCOUNT_RE = re.compile(r"^[0-9a-f]{32}$")
_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
_PREFIX_RE = re.compile(r"^[A-Za-z0-9._\-/]{1,200}$")
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9]{16,128}$")
ROUTINE_HOSTS = ("claude.ai", "claude.com")


class SetEngineRequest(BaseModel):
    engine: JobEngineEnum
    # Leaving "your own Claude routine" deletes its stored credentials (§9.4).
    confirm_delete_credentials: bool = False


class RoutineConnectionInput(BaseModel):
    """Create: everything except routine_url is required. Update: send only
    what changes; a missing secret keeps the stored one. Secrets are write-only."""
    neon_url: Optional[str] = Field(default=None, max_length=2000)
    r2_account_id: Optional[str] = None
    r2_bucket: Optional[str] = None
    r2_prefix: Optional[str] = None
    r2_access_key_id: Optional[str] = None
    r2_secret: Optional[str] = Field(default=None, max_length=200)
    routine_url: Optional[str] = Field(default=None, max_length=2000)
    schedule_cron: Optional[str] = Field(default=None, max_length=100)
    timezone: Optional[str] = Field(default=None, max_length=64)

    @field_validator("neon_url", "r2_access_key_id", "r2_secret", "r2_account_id", "r2_bucket", "r2_prefix",
                     "schedule_cron", "timezone", "routine_url")
    @classmethod
    def _strip(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if isinstance(v, str) else v

    @field_validator("r2_account_id")
    @classmethod
    def _account(cls, v: Optional[str]) -> Optional[str]:
        if v and not _ACCOUNT_RE.match(v.lower()):
            raise ValueError("A Cloudflare account id is 32 hexadecimal characters")
        return v.lower() if v else v

    @field_validator("r2_bucket")
    @classmethod
    def _bucket(cls, v: Optional[str]) -> Optional[str]:
        if v and not _BUCKET_RE.match(v):
            raise ValueError("Bucket names use 3–63 lower-case letters, digits and hyphens")
        return v

    @field_validator("r2_prefix")
    @classmethod
    def _prefix(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip("/")
        if not _PREFIX_RE.match(v) or ".." in v:
            raise ValueError("The folder may use letters, digits, '.', '_', '-' and '/'")
        return v

    @field_validator("r2_access_key_id")
    @classmethod
    def _key_id(cls, v: Optional[str]) -> Optional[str]:
        if v and not _KEY_ID_RE.match(v):
            raise ValueError("That doesn't look like an R2 access key id")
        return v

    @field_validator("routine_url")
    @classmethod
    def _routine_url(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        parts = urlsplit(v)
        host = (parts.hostname or "").lower()
        if parts.scheme != "https" or not any(host == h or host.endswith("." + h) for h in ROUTINE_HOSTS):
            raise ValueError("The routine link must be an https://claude.ai/… address")
        return v


class ConnectionTestRequest(RoutineConnectionInput):
    pass


class CheckResult(BaseModel):
    key: str
    label: str
    ok: bool
    message: str


class ConnectionTestResponse(BaseModel):
    ok: bool
    checks: list[CheckResult]
    contract_version: Optional[int] = None


class RoutineConnectionInfo(BaseModel):
    """What the browser may see of a connection: never a secret."""
    neon_host: str
    neon_saved: bool = True
    r2_account_id: str
    r2_bucket: str
    r2_prefix: str
    r2_access_key_hint: str
    r2_secret_saved: bool = True
    routine_url: Optional[str]
    schedule_cron: str
    timezone: str
    contract_version: Optional[int]
    status: str
    verified_at: Optional[datetime]
    last_check_at: Optional[datetime]
    last_error: Optional[str]
    consecutive_failures: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RoutineRunInfo(BaseModel):
    id: uuid.UUID
    run_id: Optional[str]
    expected_at: Optional[datetime]
    outcome: str
    message: str = ""
    contract_version: Optional[int]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    status: Optional[str]
    current_step: Optional[str]
    error: Optional[str]
    searches_run: Optional[int]
    search_budget: Optional[int]
    postings_found: Optional[int]
    postings_assessed: Optional[int]
    jobs_eligible: Optional[int]
    jobs_new: Optional[int]
    jobs_updated: Optional[int]
    jobs_rejected: Optional[int]
    docs_done: Optional[int]
    docs_failed: Optional[int]
    sources_failed: Optional[str]
    summary: Optional[str]

    model_config = {"from_attributes": True}


class RoutineSyncInfo(BaseModel):
    id: uuid.UUID
    trigger: str
    run_id: Optional[str]
    status: str
    started_at: datetime
    finished_at: Optional[datetime]
    rows_read: int
    jobs_new: int
    jobs_updated: int
    jobs_removed: int
    docs_copied: int
    docs_skipped: int
    problems: list[str]
    error: Optional[str]

    model_config = {"from_attributes": True}


CardState = Literal[
    "setup_incomplete", "waiting", "running", "healthy", "problems", "failed",
    "stopped", "didnt_run", "cant_connect", "no_run_details",
]


class EngineCard(BaseModel):
    """The engine-3 dashboard card (§6.8)."""
    state: CardState
    label: str
    message: str
    paused: bool = False
    last_run: Optional[RoutineRunInfo] = None
    last_sync: Optional[RoutineSyncInfo] = None
    next_run_at: Optional[datetime] = None
    next_sync_at: Optional[datetime] = None
    next_sync_estimated: bool = False
    sync_running: bool = False
    sync_now_available_at: Optional[datetime] = None
    routine_url: Optional[str] = None


class JobEngineResponse(BaseModel):
    engine: str
    engine_changed_at: Optional[datetime]
    credentials_storage_ready: bool
    connection: Optional[RoutineConnectionInfo] = None
    card: Optional[EngineCard] = None


class SyncNowResponse(BaseModel):
    queued: bool
    message: str
    card: EngineCard
