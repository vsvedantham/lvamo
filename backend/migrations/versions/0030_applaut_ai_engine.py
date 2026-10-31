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


def downgrade() -> None:
    op.execute("DROP INDEX applaut.ix_applaut_job_assessments_docs_pending")
    op.execute("ALTER TABLE applaut.job_assessments DROP COLUMN docs_status, DROP COLUMN status")
    op.execute("DROP TABLE applaut.master_profiles")
