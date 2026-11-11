from fastapi import APIRouter

from app.platform.api.v1.routers import email_codes, settings

router = APIRouter()
router.include_router(settings.router, tags=["platform-settings"])
router.include_router(email_codes.router, tags=["platform-email-codes"])
