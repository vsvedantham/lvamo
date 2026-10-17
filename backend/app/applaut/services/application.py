from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.models.application import Application
from app.applaut.models.enums import ApplicationStatusEnum
from app.applaut.models.opportunity import Opportunity
from app.applaut.models.user import User
from app.applaut.schemas.application import ApplicationResponse
from app.applaut.services.profile import get_active_profile
from app.applaut.services.visibility import get_visible_opportunity, require_visible_opportunity

VALID_STATUSES = {s.value for s in ApplicationStatusEnum}

# Statuses that set applied_at / submitted_at timestamps
APPLIED_STATUSES = {"submitted", "interviewing", "offered", "rejected", "withdrawn", "closed"}
SUBMITTED_STATUSES = {"submitted", "interviewing", "offered", "rejected", "withdrawn", "closed"}


def _to_response(app: Application, opp: Opportunity) -> ApplicationResponse:
    return ApplicationResponse(
        id=app.id,
        opportunity_id=app.opportunity_id,
        profile_id=app.profile_id,
        score_id=app.score_id,
        status=app.status,
        notes=app.notes,
        applied_at=app.applied_at,
        submitted_at=app.submitted_at,
        created_at=app.created_at,
        updated_at=app.updated_at,
        opportunity_title=opp.title if opp else "",
        opportunity_company=opp.company_name if opp else "",
        opportunity_location=opp.location_raw if opp else None,
        opportunity_url=opp.application_url if opp else None,
    )


async def create_application(
    opportunity_id: str,
    score_id: str | None,
    notes: str | None,
    user: User,
    db: AsyncSession,
) -> ApplicationResponse:
    opp = await require_visible_opportunity(opportunity_id, user.id, db)

    # Prevent duplicates
    existing = await db.scalar(
        select(Application).where(
            Application.user_id == user.id,
            Application.opportunity_id == opp.id,
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Application already exists for this opportunity",
        )

    profile = await get_active_profile(user, db)

    app = Application(
        user_id=user.id,
        opportunity_id=opp.id,
        profile_id=profile.id,
        score_id=score_id,
        notes=notes,
        status=ApplicationStatusEnum.pending_review,
    )
    db.add(app)

    from app.applaut.services.audit import log_action
    await log_action(
        action="application.create",
        db=db,
        user_id=str(user.id),
        entity_type="opportunity",
        entity_id=str(opp.id),
        after_state={"status": "pending_review", "company": opp.company_name, "title": opp.title},
    )

    await db.commit()
    await db.refresh(app)
    return _to_response(app, opp)


async def list_applications(
    user: User,
    db: AsyncSession,
    status_filter: str | None = None,
) -> list[ApplicationResponse]:
    query = select(Application).where(Application.user_id == user.id)
    if status_filter and status_filter in VALID_STATUSES:
        query = query.where(Application.status == status_filter)

    apps = await db.scalars(query.order_by(Application.created_at.desc()))
    results = []
    for app in apps:
        opp = await get_visible_opportunity(app.opportunity_id, user.id, db)
        results.append(_to_response(app, opp))
    return results


async def get_application(
    application_id: str,
    user: User,
    db: AsyncSession,
) -> ApplicationResponse:
    app = await db.get(Application, application_id)
    if not app or app.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    opp = await get_visible_opportunity(app.opportunity_id, user.id, db)
    return _to_response(app, opp)


async def update_application(
    application_id: str,
    new_status: str | None,
    notes: str | None,
    user: User,
    db: AsyncSession,
) -> ApplicationResponse:
    app = await db.get(Application, application_id)
    if not app or app.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    if new_status is not None:
        if new_status not in VALID_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
            )
        now = datetime.now(timezone.utc)
        if new_status in APPLIED_STATUSES and app.applied_at is None:
            app.applied_at = now
        if new_status in SUBMITTED_STATUSES and app.submitted_at is None:
            app.submitted_at = now
        app.status = new_status

    if notes is not None:
        app.notes = notes

    opp = await get_visible_opportunity(app.opportunity_id, user.id, db)

    from app.applaut.services.audit import log_action
    await log_action(
        action="application.status_change",
        db=db,
        user_id=str(user.id),
        entity_type="application",
        entity_id=str(app.id),
        after_state={"status": app.status, "company": opp.company_name if opp else None, "title": opp.title if opp else None},
    )

    await db.commit()
    await db.refresh(app)
    return _to_response(app, opp)


async def delete_application(
    application_id: str,
    user: User,
    db: AsyncSession,
) -> None:
    app = await db.get(Application, application_id)
    if not app or app.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    await db.delete(app)
    await db.commit()
