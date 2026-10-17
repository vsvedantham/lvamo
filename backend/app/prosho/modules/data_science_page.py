"""Data-science module panels for the project page (BETA_PLAN §2): data
source health, metrics vs targets, pipeline runs. Built from evidence only."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.enums import EvidenceKind
from app.prosho.models.prosho_claim import ProshoClaim
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.modules.source_checks import KEY_PREFIX, configured_sources, source_key
from app.prosho.schemas.public import DataModule, MetricPanelItem, RunPanelItem, SourcePanelItem
from app.prosho.services.claim_status import computed_status
from app.prosho.services.evidence import latest_by_key

MAX_METRICS = 20
MAX_RUN_KEYS = 5
RUN_PAYLOAD_FIELDS = ("duration_s", "tests_passed", "tests_total", "url")


async def build(project: ProshoProject, claims: list[ProshoClaim], db: AsyncSession) -> DataModule:
    checks = await latest_by_key(project.id, db, kinds=[EvidenceKind.check], key_prefix=KEY_PREFIX)
    sources = []
    for src in configured_sources(project):
        e = checks.get(source_key(src["url"]))
        payload: dict[str, Any] = (e.payload or {}) if e else {}
        sources.append(SourcePanelItem(
            name=src.get("name") or src["url"], url=src["url"], licence=src.get("licence"),
            status=e.value_text if e else "unchecked", checked_at=e.recorded_at if e else None,
            detail=payload.get("error"), status_code=payload.get("status_code"),
        ))

    by_metric = {c.metric_key: c for c in claims if c.metric_key}
    metric_rows = await latest_by_key(project.id, db, kinds=[EvidenceKind.metric])
    metrics = []
    for key in sorted(metric_rows)[:MAX_METRICS]:
        e, claim = metric_rows[key], by_metric.get(key)
        metrics.append(MetricPanelItem(
            key=key, value=e.value_num, unit=e.unit, recorded_at=e.recorded_at, commit_sha=e.commit_sha,
            claim_text=claim.text if claim else None,
            target_op=claim.target_op.value if claim and claim.target_op else None,
            target_value=claim.target_value if claim else None,
            target_value_hi=claim.target_value_hi if claim else None,
            status=computed_status(claim.target_op, claim.target_value, claim.target_value_hi, e.value_num) if claim else None,
        ))

    run_rows = await latest_by_key(project.id, db, kinds=[EvidenceKind.run])
    runs = [
        RunPanelItem(key=e.key, status=e.value_text, recorded_at=e.recorded_at, commit_sha=e.commit_sha,
                     details={k: (e.payload or {})[k] for k in RUN_PAYLOAD_FIELDS if k in (e.payload or {})})
        for e in sorted(run_rows.values(), key=lambda e: e.recorded_at, reverse=True)[:MAX_RUN_KEYS]
    ]
    return DataModule(sources=sources, metrics=metrics, runs=runs)
