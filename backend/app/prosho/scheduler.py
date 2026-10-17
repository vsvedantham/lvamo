"""ProSho's own scheduler (one per worker process — jobs guard themselves
against running twice, see modules/source_checks.py)."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.prosho.modules.source_checks import run_daily_checks

log = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")


def start_scheduler() -> None:
    scheduler.add_job(run_daily_checks, CronTrigger(hour=5, minute=0), id="prosho_daily_source_checks",
                      replace_existing=True, coalesce=True, misfire_grace_time=3600)
    scheduler.start()
    log.info("ProSho scheduler started")


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
