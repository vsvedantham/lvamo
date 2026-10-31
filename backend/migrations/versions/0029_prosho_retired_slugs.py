"""prosho.retired_slugs

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-31

When a page that was ever shared is deleted, its address is retired so
nobody else can take over a link that's already on CVs and LinkedIn. Only
the slug is kept — no link back to the deleted project or person.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE prosho.retired_slugs (
            slug VARCHAR(60) PRIMARY KEY,
            retired_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS prosho.retired_slugs")
