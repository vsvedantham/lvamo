from fastapi import APIRouter

from app.prosho.api.v1.routers import auth, github, github_webhook, health, projects

router = APIRouter()
router.include_router(health.router, tags=["prosho-health"])
router.include_router(auth.router, tags=["prosho-auth"])
router.include_router(projects.router, tags=["prosho-projects"])
router.include_router(github.router, tags=["prosho-github"])
router.include_router(github_webhook.router, tags=["prosho-github"])
