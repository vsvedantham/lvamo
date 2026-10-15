"""prosho.projects + prosho.audit_logs

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-15

ProSho Phase 1 (docs/prosho/BETA_PLAN.md §8). `public` visibility requires the
owner's supervisor confirmation (§11), enforced here as well as in the API.
The GitHub/manifest columns are filled by the repo connection and
prosho.yaml sync (later in Phase 1); `repo_id` is GitHub's stable numeric id,
so a renamed repo still matches.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE prosho.project_type_enum AS ENUM ('data_science', 'frontend')")
    op.execute("CREATE TYPE prosho.visibility_enum AS ENUM ('private', 'unlisted', 'public')")
    op.execute("CREATE TYPE prosho.demo_kind_enum AS ENUM ('streamlit', 'url', 'video')")
    op.execute("""
        CREATE TABLE prosho.projects (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_id UUID NOT NULL REFERENCES prosho.users(id) ON DELETE CASCADE,
            slug VARCHAR(60) NOT NULL UNIQUE,
            title VARCHAR(200) NOT NULL,
            summary VARCHAR(300),
            problem TEXT,
            project_type prosho.project_type_enum NOT NULL,
            university VARCHAR(200),
            programme VARCHAR(200),
            visibility prosho.visibility_enum NOT NULL DEFAULT 'private',
            supervisor_ok_at TIMESTAMPTZ,
            repo_full_name VARCHAR(200),
            repo_id BIGINT,
            github_installation_id BIGINT,
            demo_kind prosho.demo_kind_enum,
            demo_url VARCHAR(500),
            manifest_sha VARCHAR(40),
            manifest_synced_at TIMESTAMPTZ,
            manifest_errors JSONB,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            published_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT prosho_projects_public_needs_supervisor
                CHECK (visibility <> 'public' OR supervisor_ok_at IS NOT NULL),
            CONSTRAINT prosho_projects_demo_pair
                CHECK ((demo_kind IS NULL) = (demo_url IS NULL))
        );
    """)
    op.execute("CREATE INDEX ix_prosho_projects_owner_id ON prosho.projects (owner_id)")
    # One project per repo: a webhook push must map to exactly one page.
    op.execute("CREATE UNIQUE INDEX uq_prosho_projects_repo_id ON prosho.projects (repo_id) WHERE repo_id IS NOT NULL")

    op.execute("""
        CREATE TABLE prosho.audit_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_id UUID REFERENCES prosho.users(id) ON DELETE SET NULL,
            action VARCHAR(50) NOT NULL,
            entity VARCHAR(50) NOT NULL,
            entity_id UUID,
            before JSONB,
            after JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX ix_prosho_audit_logs_entity ON prosho.audit_logs (entity, entity_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS prosho.audit_logs")
    op.execute("DROP TABLE IF EXISTS prosho.projects")
    op.execute("DROP TYPE IF EXISTS prosho.demo_kind_enum")
    op.execute("DROP TYPE IF EXISTS prosho.visibility_enum")
    op.execute("DROP TYPE IF EXISTS prosho.project_type_enum")
