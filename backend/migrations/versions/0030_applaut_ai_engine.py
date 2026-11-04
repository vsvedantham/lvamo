"""applaut ai engine: master profiles and assessment pipeline states

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-31

docs/applaut/APPLAUT_AI_ENGINE_DESIGN.md (Applaut AI on an in-house model).
On branch applaut-ai-local; not deployed.

- master_profiles: one per user, the routine's master_profile.yaml shape
  (JSONB, validated in app code), versioned on each save.
- job_assessments.status (raw | scored | failed) and docs_status
  (not_needed | pending | done | failed). Existing rows are engine 3's
  synced assessments: scored, and their documents come from the routine.
- night_runs: one row per night (what each stage did).
- ai_queue: the model's work, served first in, first out by `seq` (a retry
  takes a new seq, so it goes to the back) by the ai-worker's lanes, one per
  model host; `host` is the one that served it.
- generated_documents.details: what an Applaut AI CV is built from, so a
  bullet can be switched between its tailored and original wording.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE applaut.master_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL UNIQUE REFERENCES applaut.users(id) ON DELETE CASCADE,
            data JSONB NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            source VARCHAR(20) NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'yaml')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        ALTER TABLE applaut.job_assessments
            ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'scored'
                CHECK (status IN ('raw', 'scored', 'failed')),
            ADD COLUMN docs_status VARCHAR(20) NOT NULL DEFAULT 'not_needed'
                CHECK (docs_status IN ('not_needed', 'pending', 'done', 'failed'))
    """)
    op.execute("""
        CREATE INDEX ix_applaut_job_assessments_docs_pending
            ON applaut.job_assessments (profile_id) WHERE docs_status = 'pending'
    """)
    op.execute("""
        CREATE TABLE applaut.night_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_date DATE NOT NULL UNIQUE,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            discovery_done_at TIMESTAMPTZ,
            users INTEGER NOT NULL DEFAULT 0,
            jobs_found INTEGER NOT NULL DEFAULT 0,
            jobs_queued INTEGER NOT NULL DEFAULT 0,
            stats JSONB NOT NULL DEFAULT '{}'
        )
    """)
    op.execute("CREATE SEQUENCE applaut.ai_queue_seq")
    op.execute("""
        CREATE TABLE applaut.ai_queue (
            id BIGSERIAL PRIMARY KEY,
            seq BIGINT NOT NULL DEFAULT nextval('applaut.ai_queue_seq'),
            kind VARCHAR(30) NOT NULL CHECK (kind IN ('score_job', 'write_docs')),
            night_run_id UUID REFERENCES applaut.night_runs(id) ON DELETE SET NULL,
            user_id UUID NOT NULL REFERENCES applaut.users(id) ON DELETE CASCADE,
            profile_id UUID NOT NULL REFERENCES applaut.profiles(id) ON DELETE CASCADE,
            assessment_id UUID NOT NULL REFERENCES applaut.job_assessments(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'done', 'failed')),
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            enqueued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            host VARCHAR(100),
            model VARCHAR(100),
            prompt_tokens INTEGER,
            output_tokens INTEGER,
            duration_ms INTEGER
        )
    """)
    op.execute("CREATE INDEX ix_applaut_ai_queue_pending ON applaut.ai_queue (seq) WHERE status = 'pending'")
    op.execute("ALTER TABLE applaut.generated_documents ADD COLUMN details JSONB")
    # one open item per job and kind, so a job is never queued twice
    op.execute("""
        CREATE UNIQUE INDEX uq_applaut_ai_queue_open ON applaut.ai_queue (assessment_id, kind)
            WHERE status IN ('pending', 'running')
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE applaut.generated_documents DROP COLUMN details")
    op.execute("DROP TABLE applaut.ai_queue")
    op.execute("DROP SEQUENCE applaut.ai_queue_seq")
    op.execute("DROP TABLE applaut.night_runs")
    op.execute("DROP INDEX applaut.ix_applaut_job_assessments_docs_pending")
    op.execute("ALTER TABLE applaut.job_assessments DROP COLUMN docs_status, DROP COLUMN status")
    op.execute("DROP TABLE applaut.master_profiles")
