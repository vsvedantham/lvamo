"""Evidence: CI ingestion and reading the latest values back.

Evidence is append-only. Keys starting with `source.` are reserved for
LVAMO's own scheduled data-source checks, so CI can't fake them.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.enums import EvidenceKind, EvidenceSource
from app.prosho.models.prosho_claim import ProshoClaim
from app.prosho.models.prosho_evidence import ProshoEvidence
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.schemas.evidence import IngestItem, IngestItemResult, IngestRequest, IngestResponse

RESERVED_PREFIX = "source."


def _first_error(e: ValidationError) -> str:
    err = e.errors()[0]
    where = ".".join(str(p) for p in err["loc"])
    msg = err["msg"].removeprefix("Value error, ")
    return f"{where}: {msg}" if where else msg


async def ingest(project: ProshoProject, body: IngestRequest, db: AsyncSession) -> IngestResponse:
    claim_ids = {key: cid for key, cid in (await db.execute(
        select(ProshoClaim.key, ProshoClaim.id)
        .where(ProshoClaim.project_id == project.id, ProshoClaim.archived_at.is_(None))
    )).all()}

    results: list[IngestItemResult] = []
    for i, raw in enumerate(body.items):
        key = raw.get("key") if isinstance(raw, dict) else None
        key = key if isinstance(key, str) else None
        try:
            item = IngestItem.model_validate(raw)
        except ValidationError as e:
            results.append(IngestItemResult(index=i, key=key, result="rejected", reason=_first_error(e)))
            continue
        if item.key.startswith(RESERVED_PREFIX):
            results.append(IngestItemResult(index=i, key=key, result="rejected",
                                            reason=f"keys starting with '{RESERVED_PREFIX}' are reserved for LVAMO's own checks"))
            continue
        if item.claim is not None and item.claim not in claim_ids:
            results.append(IngestItemResult(index=i, key=key, result="rejected",
                                            reason=f"no claim with id '{item.claim}' in prosho.yaml"))
            continue

        values = dict(
            project_id=project.id,
            claim_id=claim_ids.get(item.claim) if item.claim else None,
            module=project.project_type.value,
            kind=EvidenceKind(item.kind),
            key=item.key,
            value_num=item.value_num,
            value_text=item.value_text,
            unit=item.unit,
            payload=item.payload,
            commit_sha=body.commit_sha,
            source=EvidenceSource.ci,
        )
        stmt = insert(ProshoEvidence).values(id=uuid.uuid4(), **values)
        if body.commit_sha:
            # Same key from the same commit = a CI retry → keep the first.
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["project_id", "key", "commit_sha"],
                index_where=ProshoEvidence.commit_sha.is_not(None),
            )
        inserted = (await db.execute(stmt.returning(ProshoEvidence.id))).first()
        results.append(IngestItemResult(index=i, key=item.key, result="accepted" if inserted else "duplicate"))

    await db.commit()
    count = lambda r: sum(1 for x in results if x.result == r)  # noqa: E731
    return IngestResponse(accepted=count("accepted"), duplicate=count("duplicate"), rejected=count("rejected"),
                          items=results)


async def history(project: ProshoProject, db: AsyncSession, key: Optional[str] = None, limit: int = 50) -> list[ProshoEvidence]:
    q = select(ProshoEvidence).where(ProshoEvidence.project_id == project.id)
    if key:
        q = q.where(ProshoEvidence.key == key)
    return list(await db.scalars(q.order_by(ProshoEvidence.recorded_at.desc()).limit(limit)))


async def latest_by_key(project_id: uuid.UUID, db: AsyncSession, kinds: Optional[list[EvidenceKind]] = None,
                        key_prefix: Optional[str] = None) -> dict[str, ProshoEvidence]:
    """The newest evidence row per key (Postgres DISTINCT ON)."""
    q = (select(ProshoEvidence)
         .where(ProshoEvidence.project_id == project_id)
         .distinct(ProshoEvidence.key)
         .order_by(ProshoEvidence.key, ProshoEvidence.recorded_at.desc()))
    if kinds:
        q = q.where(ProshoEvidence.kind.in_(kinds))
    if key_prefix:
        q = q.where(ProshoEvidence.key.startswith(key_prefix))
    return {e.key: e for e in await db.scalars(q)}


def evidence_summary(e: ProshoEvidence) -> dict[str, Any]:
    return {"value_num": e.value_num, "value_text": e.value_text, "unit": e.unit,
            "recorded_at": e.recorded_at, "commit_sha": e.commit_sha}
