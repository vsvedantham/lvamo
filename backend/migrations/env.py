import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Load .env so DATABASE_URL is available when running alembic directly
from dotenv import load_dotenv
load_dotenv()

# Import Base and all models so their tables are registered with metadata
from app.db.base import Base  # noqa: E402
from app.applaut.models import (  # noqa: E402, F401
    User, Profile, Resume, Opportunity, Score,
    Application, GeneratedDocument, Notification, AuditLog, JobAssessment, EngineTask,
    RoutineConnection, RoutineRun, RoutineSync, RoutineJob,
)
from app.applaut.models.application_setting import ApplicationSetting  # noqa: E402, F401
from app.jobref.models import (  # noqa: E402, F401
    JobrefCompany, JobrefReferralRequest, JobrefUser,
)
from app.platform.models import PlatformSetting  # noqa: E402, F401
from app.prosho.models import (  # noqa: E402, F401
    ProshoAuditLog, ProshoClaim, ProshoEvidence, ProshoIngestToken, ProshoProject, ProshoUser,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return os.environ["DATABASE_URL"]


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = get_url()
    connectable = async_engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
