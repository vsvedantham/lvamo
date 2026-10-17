from fastapi import APIRouter

from app.applaut.api.v1.routers import applications, audit, auth, documents, health, job_engine, notifications, opportunity, profile, resume, scheduler, scoring, settings, stats

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(settings.router, tags=["settings"])
router.include_router(auth.router, tags=["auth"])
router.include_router(profile.router, tags=["profiles"])
router.include_router(resume.router, tags=["resumes"])
router.include_router(opportunity.router, tags=["opportunities"])
router.include_router(scoring.router, tags=["scoring"])
router.include_router(documents.router, tags=["documents"])
router.include_router(applications.router, tags=["applications"])
router.include_router(stats.router, tags=["stats"])
router.include_router(scheduler.router, tags=["scheduler"])
router.include_router(notifications.router, tags=["notifications"])
router.include_router(audit.router, tags=["audit"])
router.include_router(job_engine.router, tags=["job-engine"])
