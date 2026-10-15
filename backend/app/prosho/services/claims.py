import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.enums import ClaimManualStatus
from app.prosho.models.prosho_claim import ProshoClaim
from app.prosho.models.prosho_project import ProshoProject
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.services import audit


async def list_claims(project: ProshoProject, db: AsyncSession) -> list[ProshoClaim]:
    rows = await db.scalars(select(ProshoClaim)
                            .where(ProshoClaim.project_id == project.id, ProshoClaim.archived_at.is_(None))
                            .order_by(ProshoClaim.position))
    return list(rows)


async def set_manual_status(project: ProshoProject, claim_id: uuid.UUID, new_status: ClaimManualStatus,
                            user: ProshoUser, db: AsyncSession) -> ProshoClaim:
    claim = await db.get(ProshoClaim, claim_id)
    if not claim or claim.project_id != project.id or claim.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    if claim.metric_key is not None:
        # Explainable, not typed in: a measured claim's status only ever
        # comes from its evidence (BETA_PLAN §7).
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="This claim's status comes from its metric — it can't be set by hand")
    if claim.manual_status != new_status:
        audit.record(db, actor_id=user.id, action="claim.update", entity="claim", entity_id=claim.id,
                     before={"manual_status": claim.manual_status}, after={"manual_status": new_status})
        claim.manual_status = new_status
        await db.commit()
        await db.refresh(claim)
    return claim
