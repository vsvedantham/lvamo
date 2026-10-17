"""prosho.evidence, prosho.ingest_tokens, projects.module_config

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-17

ProSho Phase 2 (docs/prosho/BETA_PLAN.md §8, §9, §12).

- evidence is append-only: history is the audit trail. A row with a
  commit_sha is unique per (project, key, commit) so CI retries are
  idempotent; rows without one (scheduler checks) just accumulate.
- ingest_tokens store only a SHA-256 of the token; the token itself is shown
  once at creation.
- module_config holds the validated module section of prosho.yaml (e.g.
  `data.sources`) so scheduled checks can read it without GitHub. Generic
  JSONB, so new modules need no schema change (plan §3 criterion 7).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE prosho.projects ADD COLUMN module_config JSONB")
    op.execute("CREATE TYPE prosho.evidence_kind_enum AS ENUM ('metric', 'check', 'artifact', 'run')")
    op.execute("CREATE TYPE prosho.evidence_source_enum AS ENUM ('ci', 'webhook', 'scheduler', 'manual')")
    op.execute("""
        CREATE TABLE prosho.evidence (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES prosho.projects(id) ON DELETE CASCADE,
            claim_id UUID REFERENCES prosho.claims(id) ON DELETE SET NULL,
            module VARCHAR(30) NOT NULL,
            kind prosho.evidence_kind_enum NOT NULL,
            key VARCHAR(100) NOT NULL,
            value_num DOUBLE PRECISION,
            value_text VARCHAR(500),
            unit VARCHAR(30),
            payload JSONB,
            r2_key VARCHAR(500),
            commit_sha VARCHAR(40),
            source prosho.evidence_source_enum NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX ix_prosho_evidence_project_key_time ON prosho.evidence (project_id, key, recorded_at DESC)")
    op.execute("""
        CREATE UNIQUE INDEX uq_prosho_evidence_project_key_commit
        ON prosho.evidence (project_id, key, commit_sha) WHERE commit_sha IS NOT NULL
    """)
    op.execute("""
        CREATE TABLE prosho.ingest_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES prosho.projects(id) ON DELETE CASCADE,
            token_hash CHAR(64) NOT NULL UNIQUE,
            token_prefix VARCHAR(16) NOT NULL,
            label VARCHAR(100) NOT NULL,
            last_used_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            created_by UUID REFERENCES prosho.users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX ix_prosho_ingest_tokens_project_id ON prosho.ingest_tokens (project_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS prosho.ingest_tokens")
    op.execute("DROP TABLE IF EXISTS prosho.evidence")
    op.execute("DROP TYPE IF EXISTS prosho.evidence_source_enum")
    op.execute("DROP TYPE IF EXISTS prosho.evidence_kind_enum")
    op.execute("ALTER TABLE prosho.projects DROP COLUMN IF EXISTS module_config")
