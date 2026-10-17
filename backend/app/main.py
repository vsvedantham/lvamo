from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.applaut.api.v1.router import router as applaut_v1_router
from app.applaut.discovery.scheduler import start_scheduler, stop_scheduler
from app.jobref.api.v1.router import router as jobref_v1_router
from app.platform.api.v1.router import router as platform_v1_router
from app.prosho.api.v1.router import router as prosho_v1_router
from app.prosho.scheduler import start_scheduler as start_prosho_scheduler
from app.prosho.scheduler import stop_scheduler as stop_prosho_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    start_prosho_scheduler()
    yield
    stop_prosho_scheduler()
    stop_scheduler()


app = FastAPI(
    title="LVAMO API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# LVAMO-wide endpoints (no single vertical owns them), then one mount per vertical.
app.include_router(platform_v1_router, prefix="/api/v1/platform")
app.include_router(applaut_v1_router, prefix="/api/v1/applaut")
app.include_router(jobref_v1_router, prefix="/api/v1/jobref")
app.include_router(prosho_v1_router, prefix="/api/v1/prosho")
