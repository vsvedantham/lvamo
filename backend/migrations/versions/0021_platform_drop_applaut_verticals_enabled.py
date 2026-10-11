"""Remove the old verticals_enabled row from applaut.application_settings

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-11

Migration 0020 copied verticals_enabled into platform.settings and kept the
applaut row while the deployed hub still read it. The hub now reads
/api/v1/platform/settings (live since commit 9ae3ac4), so the applaut copy
is dead and would only drift out of sync.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM applaut.application_settings WHERE setting_name = 'verticals_enabled'")


def downgrade() -> None:
    # Restore the applaut copy from the platform value, as 0019 created it.
    op.execute("""
        INSERT INTO applaut.application_settings (setting_name, value, description)
        SELECT
            'verticals_enabled',
            value,
            'Comma-separated, lowercase list of vertical names to show as cards on the LVAMO hub (frontend/src/pages/Hub.tsx). Verticals not listed here stay fully reachable by direct URL — this only controls hub visibility.'
        FROM platform.settings
        WHERE setting_name = 'verticals_enabled'
        ON CONFLICT (setting_name) DO NOTHING;
    """)
