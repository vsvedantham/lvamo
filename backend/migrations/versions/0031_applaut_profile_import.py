"""applaut: master profile drafted from the user's CV (profile_imports, queue kind import_profile)

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-08

APPLAUT_AI_V2_PLAN.md §5 (the rest of step 7): the writer reads the user's
CV (only its text lines are kept) and points at the lines that make up each
part of a master profile; code builds the draft from those lines.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE applaut.profile_imports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES applaut.users(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'reading' CHECK (status IN ('reading', 'ready', 'failed')),
            file_name VARCHAR(255) NOT NULL,
            lines JSONB,
            draft JSONB,
            notes JSONB NOT NULL DEFAULT '[]',
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at TIMESTAMPTZ,
            closed_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX ix_applaut_profile_imports_user ON applaut.profile_imports (user_id, created_at)")
    op.execute("ALTER TABLE applaut.ai_queue ADD COLUMN profile_import_id UUID "
               "REFERENCES applaut.profile_imports(id) ON DELETE CASCADE")
    op.execute("ALTER TABLE applaut.ai_queue DROP CONSTRAINT ai_queue_kind_check")
    op.execute("ALTER TABLE applaut.ai_queue ADD CONSTRAINT ai_queue_kind_check CHECK (kind IN "
               "('score_job', 'write_docs', 'draft_bullets', 'build_template', 'import_profile'))")
    op.execute("ALTER TABLE applaut.ai_queue DROP CONSTRAINT ai_queue_check")
    op.execute("""
        ALTER TABLE applaut.ai_queue ADD CONSTRAINT ai_queue_check CHECK (
            (kind IN ('score_job', 'write_docs')) = (assessment_id IS NOT NULL)
            AND (kind = 'draft_bullets') = (bullet_draft_id IS NOT NULL)
            AND (kind = 'build_template') = (cv_template_id IS NOT NULL)
            AND (kind = 'import_profile') = (profile_import_id IS NOT NULL))
    """)


def downgrade() -> None:
    op.execute("DELETE FROM applaut.ai_queue WHERE kind = 'import_profile'")
    op.execute("ALTER TABLE applaut.ai_queue DROP CONSTRAINT ai_queue_check")
    op.execute("""
        ALTER TABLE applaut.ai_queue ADD CONSTRAINT ai_queue_check CHECK (
            (kind IN ('score_job', 'write_docs')) = (assessment_id IS NOT NULL)
            AND (kind = 'draft_bullets') = (bullet_draft_id IS NOT NULL)
            AND (kind = 'build_template') = (cv_template_id IS NOT NULL))
    """)
    op.execute("ALTER TABLE applaut.ai_queue DROP CONSTRAINT ai_queue_kind_check")
    op.execute("ALTER TABLE applaut.ai_queue ADD CONSTRAINT ai_queue_kind_check CHECK (kind IN "
               "('score_job', 'write_docs', 'draft_bullets', 'build_template'))")
    op.execute("ALTER TABLE applaut.ai_queue DROP COLUMN profile_import_id")
    op.execute("DROP TABLE applaut.profile_imports")
