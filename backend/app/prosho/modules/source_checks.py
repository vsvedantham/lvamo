"""Data-science module: daily data-source health checks (BETA_PLAN §2, §12).

Each source listed under `data.sources` in prosho.yaml is fetched through
the SSRF guard; the result is a `check` evidence row keyed
`source.<hash of url>` (pass/fail), recorded by LVAMO, not the student.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, engine
from app.prosho.models.enums import EvidenceKind, EvidenceSource, ProjectType
from app.prosho.models.prosho_evidence import ProshoEvidence
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.services import safe_fetch

log = logging.getLogger(__name__)

KEY_PREFIX = "source."
MODULE = ProjectType.data_science.value
DAILY_MIN_GAP = timedelta(hours=20)     # a second worker / restart within this window skips
ON_DEMAND_MIN_GAP = timedelta(minutes=10)
CONCURRENCY = 5
ADVISORY_LOCK_ID = 0x50524F53484F01     # "PROSHO" + job 1; any constant unique in this DB


def source_key(url: str) -> str:
    return KEY_PREFIX + hashlib.sha256(url.encode()).hexdigest()[:12]


def configured_sources(project: ProshoProject) -> list[dict[str, Any]]:
    return ((project.module_config or {}).get("data") or {}).get("sources") or []


async def last_checked_at(project_id, db: AsyncSession) -> Optional[datetime]:
    return await db.scalar(select(func.max(ProshoEvidence.recorded_at)).where(
        ProshoEvidence.project_id == project_id, ProshoEvidence.key.startswith(KEY_PREFIX)))


async def check_project_sources(project: ProshoProject, db: AsyncSession, *, trigger: str) -> int:
    sources = configured_sources(project)
    sem = asyncio.Semaphore(CONCURRENCY)

    async def one(src: dict[str, Any]):
        async with sem:
            return src, await safe_fetch.check_url(src["url"])

    for src, r in await asyncio.gather(*(one(s) for s in sources)):
        db.add(ProshoEvidence(
            project_id=project.id, module=MODULE, kind=EvidenceKind.check, key=source_key(src["url"]),
            value_text="pass" if r.ok else "fail", source=EvidenceSource.scheduler,
            payload={"name": src.get("name"), "url": src["url"], "status_code": r.status_code,
                     "elapsed_ms": r.elapsed_ms, "error": r.error, "final_url": r.final_url, "trigger": trigger},
        ))
    await db.commit()
    return len(sources)


async def run_daily_checks() -> None:
    """Scheduled job. Production runs several uvicorn workers, each with its
    own scheduler, so: an advisory lock lets only one worker run at a time,
    and a project checked in the last 20 hours is skipped (covers a worker
    that fires after the first one already finished)."""
    async with engine.connect() as lock_conn:
        if not await lock_conn.scalar(text("SELECT pg_try_advisory_lock(:id)"), {"id": ADVISORY_LOCK_ID}):
            return
        try:
            async with AsyncSessionLocal() as db:
                projects = list(await db.scalars(select(ProshoProject).where(
                    ProshoProject.is_active.is_(True), ProshoProject.project_type == ProjectType.data_science,
                    ProshoProject.module_config.is_not(None))))
                now = datetime.now(timezone.utc)
                checked = 0
                for p in projects:
                    if not configured_sources(p):
                        continue
                    last = await last_checked_at(p.id, db)
                    if last and now - last < DAILY_MIN_GAP:
                        continue
                    try:
                        checked += await check_project_sources(p, db, trigger="daily")
                    except Exception:
                        await db.rollback()
                        log.exception("prosho: source checks failed for project %s", p.id)
                log.info("prosho: daily source checks done, %d sources checked", checked)
        finally:
            await lock_conn.scalar(text("SELECT pg_advisory_unlock(:id)"), {"id": ADVISORY_LOCK_ID})
