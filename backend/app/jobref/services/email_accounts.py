"""Jobref's side of the platform's email codes (app/platform/services/email_codes.py):
how to find a Jobref account by email and set its password. Wired in main.py.

Sign-up codes apply to employees only; job seekers' email comes verified from
LinkedIn. Password reset works for both."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.jobref.models.jobref_user import JobrefUser
from app.platform.services.email_codes import VerticalAccounts

VERTICAL = "jobref"


async def _find(db: AsyncSession, email: str) -> JobrefUser | None:
    return await db.scalar(select(JobrefUser).where(func.lower(JobrefUser.email) == email.strip().lower()))


async def account_exists(db: AsyncSession, email: str) -> bool:
    return await _find(db, email) is not None


async def set_password(db: AsyncSession, email: str, new_password: str) -> bool:
    user = await _find(db, email)
    if user is None:
        return False
    user.password_hash = hash_password(new_password)
    return True


ACCOUNTS = VerticalAccounts(display_name="Jobref", account_exists=account_exists, set_password=set_password)
