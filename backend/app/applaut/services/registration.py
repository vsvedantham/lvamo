"""Whether Applaut takes new sign-ups.

Two rows in `applaut.application_settings`:
- `allow_new_registrations`: '1' opens sign-up, anything else closes it.
- `max_users` (optional): the most Applaut accounts there may be. Once that
  many exist, sign-up is closed even while `allow_new_registrations` is '1'.
  No row = no cap; a value that isn't a whole number keeps sign-up closed.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.applaut.models.application_setting import ApplicationSetting
from app.applaut.models.user import User

OPEN = "allow_new_registrations"
MAX_USERS = "max_users"


async def registration_open(db: AsyncSession, lock: bool = False) -> bool:
    """`lock` holds the `allow_new_registrations` row until the caller commits,
    so two sign-ups at once can't both take the last place."""
    query = select(ApplicationSetting).where(ApplicationSetting.setting_name == OPEN)
    if lock:
        query = query.with_for_update()
    setting = await db.scalar(query)
    if setting is None or setting.value != "1":
        return False
    cap = await db.scalar(select(ApplicationSetting.value).where(ApplicationSetting.setting_name == MAX_USERS))
    if cap is None:
        return True
    try:
        limit = int(cap)
    except ValueError:
        return False
    return await db.scalar(select(func.count()).select_from(User)) < limit
