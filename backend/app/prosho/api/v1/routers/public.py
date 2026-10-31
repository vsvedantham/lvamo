from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.prosho.models.prosho_user import ProshoUser
from app.prosho.schemas.public import PageEventIn, PublicProject
from app.prosho.services import page_stats
from app.prosho.services.auth import get_optional_user
from app.prosho.services.public import get_public_project

router = APIRouter(prefix="/public")


@router.get("/projects/{slug}", response_model=PublicProject)
async def public_project(slug: str, response: Response, viewer: ProshoUser | None = Depends(get_optional_user),
                         db: AsyncSession = Depends(get_db)):
    page = await get_public_project(slug, viewer, db)
    # No reuse without asking again: making a page private (or changing it)
    # must take effect at once, and an owner preview must never be stored.
    response.headers["Cache-Control"] = "private, no-store" if page.preview else "no-cache"
    return page


@router.post("/projects/{slug}/events", status_code=status.HTTP_204_NO_CONTENT)
async def page_event(slug: str, body: PageEventIn, db: AsyncSession = Depends(get_db)):
    """A page view or a click to the LVAMO hub. Always 204, counted or not,
    so it can't be used to find private pages."""
    await page_stats.record(slug, body.event, body.referrer, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
