"""platform: email one-time codes (sign-up, password reset) + otp_verification_enabled setting

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-11

One table for every vertical (app/platform/services/email_codes.py). The
setting row starts empty, so no vertical sends codes until it is set, e.g. to
'applaut,jobref'. It is public: the sign-up, sign-in and password reset
pages read it to know whether to ask for a code.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE platform.email_codes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vertical VARCHAR(32) NOT NULL,
            email VARCHAR(255) NOT NULL,
            purpose VARCHAR(20) NOT NULL
                CONSTRAINT email_codes_purpose_check CHECK (purpose IN ('register', 'reset_password')),
            code_hash VARCHAR(64) NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            requester_ip VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_platform_email_codes_lookup "
               "ON platform.email_codes (vertical, email, purpose, created_at)")
    op.execute("""
        INSERT INTO platform.settings (setting_name, value, description, is_public)
        VALUES (
            'otp_verification_enabled',
            '',
            'Comma-separated, lowercase vertical names (e.g. applaut,jobref) whose sign-up asks for a code emailed to the user, and whose sign-in page offers password reset by emailed code. Empty = off everywhere. ProSho signs in with GitHub only, so it has nothing to use this for.',
            TRUE
        )
        ON CONFLICT (setting_name) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM platform.settings WHERE setting_name = 'otp_verification_enabled'")
    op.execute("DROP TABLE IF EXISTS platform.email_codes")
