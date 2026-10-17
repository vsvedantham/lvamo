"""applaut job engines: engine choice, private opportunities, AI assessments, engine_tasks

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-17

Phase 1 (shared core) of docs/applaut/JOB_ENGINES_DESIGN.md.

- profiles.job_engine: which engine finds jobs for this profile
  (basic | applaut_ai | own_routine). Everyone starts on basic.
- opportunities.owner_user_id: NULL = found by Applaut Basic and shared;
  set = brought in by an AI engine for that user only. The old
  UNIQUE (source, external_id) becomes one partial unique index per kind.
- job_assessments: an AI engine's verdict on a job, kept apart from scores
  so rule-based scoring (which rewrites scores every run) never touches it.
- generated_documents.engine / content_type / content_sha256: documents can
  now be PDFs produced by an AI engine.
- engine_tasks: the database-driven schedule (one dispatcher claims due rows
  with FOR UPDATE SKIP LOCKED), replacing one APScheduler job per profile in
  every uvicorn worker.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE applaut.job_engine_enum AS ENUM ('basic', 'applaut_ai', 'own_routine')")

    op.execute("ALTER TABLE applaut.profiles ADD COLUMN job_engine applaut.job_engine_enum NOT NULL DEFAULT 'basic'")
    op.execute("ALTER TABLE applaut.profiles ADD COLUMN job_engine_changed_at TIMESTAMPTZ")

    op.execute("""
        ALTER TABLE applaut.opportunities
        ADD COLUMN owner_user_id UUID REFERENCES applaut.users(id) ON DELETE CASCADE
    """)
    op.execute("ALTER TABLE applaut.opportunities DROP CONSTRAINT opportunities_source_external_id_key")
    op.execute("""
        CREATE UNIQUE INDEX uq_applaut_opportunities_shared_source_external_id
        ON applaut.opportunities (source, external_id) WHERE owner_user_id IS NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_applaut_opportunities_owned_source_external_id
        ON applaut.opportunities (owner_user_id, source, external_id) WHERE owner_user_id IS NOT NULL
    """)

    op.execute("""
        CREATE TABLE applaut.job_assessments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES applaut.users(id) ON DELETE CASCADE,
            profile_id UUID NOT NULL REFERENCES applaut.profiles(id) ON DELETE CASCADE,
            opportunity_id UUID NOT NULL REFERENCES applaut.opportunities(id) ON DELETE CASCADE,
            engine applaut.job_engine_enum NOT NULL,
            match_score SMALLINT CHECK (match_score BETWEEN 0 AND 100),
            matched_skills TEXT[] NOT NULL DEFAULT '{}',
            missing_skills TEXT[] NOT NULL DEFAULT '{}',
            german_required VARCHAR(50),
            seniority VARCHAR(50),
            notes TEXT,
            flags TEXT[] NOT NULL DEFAULT '{}',
            model VARCHAR(100),
            raw JSONB NOT NULL DEFAULT '{}',
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            times_seen INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_applaut_job_assessments_profile_opportunity_engine
                UNIQUE (profile_id, opportunity_id, engine)
        )
    """)
    op.execute("CREATE INDEX ix_applaut_job_assessments_opportunity_id ON applaut.job_assessments (opportunity_id)")

    op.execute("ALTER TABLE applaut.generated_documents ADD COLUMN engine applaut.job_engine_enum NOT NULL DEFAULT 'basic'")
    op.execute("ALTER TABLE applaut.generated_documents ADD COLUMN content_type VARCHAR(100) NOT NULL DEFAULT 'text/markdown'")
    op.execute("ALTER TABLE applaut.generated_documents ADD COLUMN content_sha256 CHAR(64)")

    op.execute("""
        CREATE TABLE applaut.engine_tasks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            kind VARCHAR(50) NOT NULL,
            user_id UUID REFERENCES applaut.users(id) ON DELETE CASCADE,
            profile_id UUID REFERENCES applaut.profiles(id) ON DELETE CASCADE,
            due_at TIMESTAMPTZ NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'done', 'failed', 'cancelled')),
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            payload JSONB NOT NULL DEFAULT '{}',
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_applaut_engine_tasks_due ON applaut.engine_tasks (due_at) WHERE status = 'pending'")
    op.execute("CREATE INDEX ix_applaut_engine_tasks_profile_id ON applaut.engine_tasks (profile_id)")
    # At most one queued or running task of a kind per profile.
    op.execute("""
        CREATE UNIQUE INDEX uq_applaut_engine_tasks_open_kind_profile
        ON applaut.engine_tasks (kind, profile_id) WHERE status IN ('pending', 'running')
    """)


def downgrade() -> None:
    op.execute("DROP TABLE applaut.engine_tasks")
    op.execute("ALTER TABLE applaut.generated_documents DROP COLUMN content_sha256")
    op.execute("ALTER TABLE applaut.generated_documents DROP COLUMN content_type")
    op.execute("ALTER TABLE applaut.generated_documents DROP COLUMN engine")
    op.execute("DROP TABLE applaut.job_assessments")
    op.execute("DELETE FROM applaut.opportunities WHERE owner_user_id IS NOT NULL")
    op.execute("DROP INDEX applaut.uq_applaut_opportunities_owned_source_external_id")
    op.execute("DROP INDEX applaut.uq_applaut_opportunities_shared_source_external_id")
    op.execute("""
        ALTER TABLE applaut.opportunities
        ADD CONSTRAINT opportunities_source_external_id_key UNIQUE (source, external_id)
    """)
    op.execute("ALTER TABLE applaut.opportunities DROP COLUMN owner_user_id")
    op.execute("ALTER TABLE applaut.profiles DROP COLUMN job_engine_changed_at")
    op.execute("ALTER TABLE applaut.profiles DROP COLUMN job_engine")
    op.execute("DROP TYPE applaut.job_engine_enum")
