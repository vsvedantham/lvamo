"""prosho.claims + projects.manifest_checked_at

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-15

Claims come from prosho.yaml (BETA_PLAN §7). They're upserted on every
successful sync, keyed by (project_id, key); a claim dropped from the manifest
is archived, not deleted. A claim with a metric gets a computed status from
evidence (Phase 2); without one, the student sets `manual_status` and the page
labels it self-reported.

`manifest_checked_at` records every sync attempt, including failed ones;
`manifest_synced_at` stays the time of the last *successful* sync.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE prosho.projects ADD COLUMN manifest_checked_at TIMESTAMPTZ")
    op.execute("CREATE TYPE prosho.claim_target_op_enum AS ENUM ('gte', 'lte', 'abs_lte', 'between', 'eq')")
    op.execute("CREATE TYPE prosho.claim_manual_status_enum AS ENUM ('not_started', 'in_progress', 'met', 'not_met')")
    op.execute("""
        CREATE TABLE prosho.claims (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES prosho.projects(id) ON DELETE CASCADE,
            key VARCHAR(60) NOT NULL,
            text VARCHAR(300) NOT NULL,
            metric_key VARCHAR(100),
            target_op prosho.claim_target_op_enum,
            target_value DOUBLE PRECISION,
            target_value_hi DOUBLE PRECISION,
            manual_status prosho.claim_manual_status_enum NOT NULL DEFAULT 'not_started',
            position INTEGER NOT NULL DEFAULT 0,
            archived_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_prosho_claims_project_key UNIQUE (project_id, key),
            CONSTRAINT prosho_claims_metric_target
                CHECK ((metric_key IS NULL) = (target_op IS NULL) AND (target_op IS NULL) = (target_value IS NULL)),
            CONSTRAINT prosho_claims_between_hi
                CHECK (COALESCE(target_op = 'between', FALSE) = (target_value_hi IS NOT NULL))
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS prosho.claims")
    op.execute("DROP TYPE IF EXISTS prosho.claim_manual_status_enum")
    op.execute("DROP TYPE IF EXISTS prosho.claim_target_op_enum")
    op.execute("ALTER TABLE prosho.projects DROP COLUMN IF EXISTS manifest_checked_at")
