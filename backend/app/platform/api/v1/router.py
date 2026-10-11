from fastapi import APIRouter

from app.platform.api.v1.routers import settings

router = APIRouter()
router.include_router(settings.router, tags=["platform-settings"])
