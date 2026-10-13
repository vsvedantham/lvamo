from fastapi import APIRouter

from app.prosho.api.v1.routers import health

router = APIRouter()
router.include_router(health.router, tags=["prosho-health"])
