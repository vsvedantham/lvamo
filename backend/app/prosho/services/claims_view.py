"""Claims with their status resolved — shared by the owner dashboard and the
public page so both always agree."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.enums import EvidenceKind
from app.prosho.models.prosho_claim import ProshoClaim
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.schemas.public import PublicClaim
from app.prosho.services.claim_status import computed_status
from app.prosho.services.evidence import latest_by_key


async def active_claims(project: ProshoProject, db: AsyncSession) -> list[ProshoClaim]:
    return list(await db.scalars(select(ProshoClaim)
                                 .where(ProshoClaim.project_id == project.id, ProshoClaim.archived_at.is_(None))
                                 .order_by(ProshoClaim.position)))


async def resolve(project: ProshoProject, claims: list[ProshoClaim], db: AsyncSession) -> list[PublicClaim]:
    metrics = await latest_by_key(project.id, db, kinds=[EvidenceKind.metric]) if any(c.metric_key for c in claims) else {}
    out = []
    for c in claims:
        e = metrics.get(c.metric_key) if c.metric_key else None
        out.append(PublicClaim(
            key=c.key, text=c.text, self_reported=c.metric_key is None,
            status=(computed_status(c.target_op, c.target_value, c.target_value_hi, e.value_num if e else None)
                    if c.metric_key else c.manual_status.value),
            metric_key=c.metric_key, target_op=c.target_op.value if c.target_op else None,
            target_value=c.target_value, target_value_hi=c.target_value_hi,
            latest_value=e.value_num if e else None, latest_unit=e.unit if e else None,
            latest_at=e.recorded_at if e else None, latest_commit=e.commit_sha if e else None,
        ))
    return out
