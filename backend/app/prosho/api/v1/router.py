from fastapi import APIRouter

from app.prosho.api.v1.routers import auth, health

router = APIRouter()
router.include_router(health.router, tags=["prosho-health"])
router.include_router(auth.router, tags=["prosho-auth"])
