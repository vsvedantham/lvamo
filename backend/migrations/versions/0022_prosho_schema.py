"""Create prosho schema + prosho.users

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-13

ProSho Phase 0 (docs/prosho/BETA_PLAN.md §12). Only the users table for now;
the rest of the §8 schema arrives with the phases that use it. Users sign in
with GitHub only, so there is no password column.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS prosho")
    op.execute("CREATE TYPE prosho.user_role_enum AS ENUM ('student', 'mentor', 'admin')")
    op.execute("""
        CREATE TABLE prosho.users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            github_id BIGINT NOT NULL UNIQUE,
            github_login VARCHAR(100) NOT NULL,
            name VARCHAR(255),
            email VARCHAR(255),
            avatar_url VARCHAR(500),
            role prosho.user_role_enum NOT NULL DEFAULT 'student',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS prosho.users")
    op.execute("DROP TYPE IF EXISTS prosho.user_role_enum")
    op.execute("DROP SCHEMA IF EXISTS prosho")
