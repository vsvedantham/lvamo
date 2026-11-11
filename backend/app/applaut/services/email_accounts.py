"""Applaut's side of the platform's email codes (app/platform/services/email_codes.py):
how to find an Applaut account by email and set its password. Wired in main.py."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.models.user import User
from app.core.security import hash_password
from app.platform.services.email_codes import VerticalAccounts

VERTICAL = "applaut"


async def _find(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))


async def account_exists(db: AsyncSession, email: str) -> bool:
    return await _find(db, email) is not None


async def set_password(db: AsyncSession, email: str, new_password: str) -> bool:
    user = await _find(db, email)
    if user is None:
        return False
    user.password_hash = hash_password(new_password)
    user.is_verified = True  # the reset code proved they own the address
    return True


ACCOUNTS = VerticalAccounts(display_name="Applaut", account_exists=account_exists, set_password=set_password)
