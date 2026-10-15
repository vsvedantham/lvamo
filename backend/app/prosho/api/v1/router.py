from fastapi import APIRouter

from app.prosho.api.v1.routers import auth, health, projects

router = APIRouter()
router.include_router(health.router, tags=["prosho-health"])
router.include_router(auth.router, tags=["prosho-auth"])
router.include_router(projects.router, tags=["prosho-projects"])
