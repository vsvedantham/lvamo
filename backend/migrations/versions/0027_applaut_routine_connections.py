"""applaut routine connections: engine 3 (the user's own Claude routine)

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-17

Phase 2 of docs/applaut/JOB_ENGINES_DESIGN.md (§6).

- routine_connections: one per user. The Neon URL and R2 keys are stored
  Fernet-encrypted (APPLAUT_CREDENTIALS_KEY); only non-secret hints
  (Neon host, last 4 characters of the R2 key id) are kept in clear.
- routine_runs: Applaut's copy of the routine's run_tracker rows, plus rows
  Applaut infers itself (a scheduled run that never started).
- routine_syncs: one row per sync (what was read, created, copied, failed).
- routine_jobs: one row per job uid in the user's routine database, linking
  it to the opportunity it became (private, or a shared Basic posting with
  the same apply URL), with the R2 ETags of the PDFs already copied and
  when the job disappeared from the routine's database.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE applaut.routine_connections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL UNIQUE REFERENCES applaut.users(id) ON DELETE CASCADE,
            neon_url_enc TEXT NOT NULL,
            neon_host VARCHAR(255) NOT NULL,
            r2_account_id VARCHAR(64) NOT NULL,
            r2_bucket VARCHAR(63) NOT NULL,
            r2_prefix VARCHAR(200) NOT NULL DEFAULT 'jobautomationdocs',
            r2_access_key_id_enc TEXT NOT NULL,
            r2_access_key_hint VARCHAR(8) NOT NULL,
            r2_secret_enc TEXT NOT NULL,
            routine_url VARCHAR(2000),
            schedule_cron VARCHAR(100) NOT NULL DEFAULT '7 6,18 * * *',
            timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
            contract_version SMALLINT,
            status VARCHAR(20) NOT NULL DEFAULT 'setup'
                CHECK (status IN ('setup', 'active', 'error', 'paused')),
            verified_at TIMESTAMPTZ,
            last_check_at TIMESTAMPTZ,
            last_error TEXT,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            last_manual_sync_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE applaut.routine_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES applaut.users(id) ON DELETE CASCADE,
            run_id VARCHAR(100),
            expected_at TIMESTAMPTZ,
            outcome VARCHAR(20) NOT NULL
                CHECK (outcome IN ('running', 'succeeded', 'problems', 'failed', 'stopped', 'missed')),
            contract_version SMALLINT,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            status VARCHAR(20),
            current_step VARCHAR(50),
            error TEXT,
            searches_run INTEGER,
            search_budget INTEGER,
            postings_found INTEGER,
            postings_assessed INTEGER,
            jobs_eligible INTEGER,
            jobs_new INTEGER,
            jobs_updated INTEGER,
            jobs_rejected INTEGER,
            docs_done INTEGER,
            docs_failed INTEGER,
            sources_failed TEXT,
            summary TEXT,
            source_updated_at TIMESTAMPTZ,
            notified_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_applaut_routine_runs_user_run_id
        ON applaut.routine_runs (user_id, run_id) WHERE run_id IS NOT NULL
    """)
    # A run Applaut expected but never saw has no run_id; one row per expected time.
    op.execute("""
        CREATE UNIQUE INDEX uq_applaut_routine_runs_user_missed
        ON applaut.routine_runs (user_id, expected_at) WHERE run_id IS NULL
    """)
    op.execute("CREATE INDEX ix_applaut_routine_runs_user_started ON applaut.routine_runs (user_id, started_at DESC)")

    op.execute("""
        CREATE TABLE applaut.routine_syncs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES applaut.users(id) ON DELETE CASCADE,
            trigger VARCHAR(20) NOT NULL CHECK (trigger IN ('scheduled', 'manual', 'initial')),
            run_id VARCHAR(100),
            status VARCHAR(20) NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'succeeded', 'partial', 'failed')),
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ,
            rows_read INTEGER NOT NULL DEFAULT 0,
            jobs_new INTEGER NOT NULL DEFAULT 0,
            jobs_updated INTEGER NOT NULL DEFAULT 0,
            jobs_removed INTEGER NOT NULL DEFAULT 0,
            docs_copied INTEGER NOT NULL DEFAULT 0,
            docs_skipped INTEGER NOT NULL DEFAULT 0,
            watermark TIMESTAMPTZ,
            problems TEXT[] NOT NULL DEFAULT '{}',
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_applaut_routine_syncs_user_started ON applaut.routine_syncs (user_id, started_at DESC)")

    op.execute("""
        CREATE TABLE applaut.routine_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES applaut.users(id) ON DELETE CASCADE,
            uid VARCHAR(200) NOT NULL,
            opportunity_id UUID NOT NULL REFERENCES applaut.opportunities(id) ON DELETE CASCADE,
            linked_to_shared BOOLEAN NOT NULL DEFAULT FALSE,
            source_last_seen_at TIMESTAMPTZ,
            docs_status VARCHAR(20),
            docs_error TEXT,
            cv_etag VARCHAR(200),
            cover_letter_etag VARCHAR(200),
            removed_at TIMESTAMPTZ,
            first_synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_applaut_routine_jobs_user_uid UNIQUE (user_id, uid)
        )
    """)
    op.execute("CREATE INDEX ix_applaut_routine_jobs_opportunity_id ON applaut.routine_jobs (opportunity_id)")


def downgrade() -> None:
    op.execute("DROP TABLE applaut.routine_jobs")
    op.execute("DROP TABLE applaut.routine_syncs")
    op.execute("DROP TABLE applaut.routine_runs")
    op.execute("DROP TABLE applaut.routine_connections")
