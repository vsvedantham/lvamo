"""Create platform schema + platform.settings; copy verticals_enabled into it

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-11

`verticals_enabled` controls the LVAMO hub, which belongs to no vertical, but
was stored in `applaut.application_settings` (migration 0019) because that was
the only settings table at the time. This creates a platform-level home for it.

The old applaut row is deliberately NOT deleted here: the deployed frontend
still reads it until the hub switches to /api/v1/platform/settings. A later
migration removes it once that switch is live.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS platform")
    op.execute("""
        CREATE TABLE platform.settings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            setting_name VARCHAR(100) NOT NULL UNIQUE,
            value VARCHAR(255) NOT NULL,
            description TEXT,
            is_public BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    # Carry over the live value (prod currently hides Applaut: 'jobref'),
    # falling back to that same default if the applaut row is missing.
    op.execute("""
        INSERT INTO platform.settings (setting_name, value, description, is_public)
        SELECT
            'verticals_enabled',
            COALESCE(
                (SELECT value FROM applaut.application_settings WHERE setting_name = 'verticals_enabled'),
                'jobref'
            ),
            'Comma-separated, lowercase list of vertical names to show as cards on the LVAMO hub (frontend/src/pages/Hub.tsx). Verticals not listed here stay fully reachable by direct URL — this only controls hub visibility.',
            TRUE;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS platform.settings")
    op.execute("DROP SCHEMA IF EXISTS platform")
