"""applaut: opportunities.last_seen_at (closed postings leave the job list)

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-18

Discovery marks every posting it lists as seen; one unseen for three days is
closed (app/applaut/discovery/engine.py expire_unseen). Existing rows start as
seen now, so each gets three nights to show up again before it closes.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE applaut.opportunities ADD COLUMN last_seen_at TIMESTAMPTZ")
    op.execute("UPDATE applaut.opportunities SET last_seen_at = now() WHERE owner_user_id IS NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE applaut.opportunities DROP COLUMN last_seen_at")
