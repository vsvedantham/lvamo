"""ProSho test helpers. Test users get GitHub ids from 9_100_000_000 up (far
above real ids) and everything they own is removed after each test."""
import itertools

import pytest
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.prosho.models import ProshoAuditLog, ProshoProject, ProshoUser
from app.prosho.services.auth import issue_access_token

TEST_ID_MIN, TEST_ID_MAX = 9_100_000_000, 9_199_999_999
_ids = itertools.count(TEST_ID_MIN + 1000)


async def _purge_test_data():
    async with AsyncSessionLocal() as db:
        user_ids = select(ProshoUser.id).where(ProshoUser.github_id.between(TEST_ID_MIN, TEST_ID_MAX))
        project_ids = select(ProshoProject.id).where(ProshoProject.owner_id.in_(user_ids))
        await db.execute(delete(ProshoAuditLog).where(
            ProshoAuditLog.actor_id.in_(user_ids) | ProshoAuditLog.entity_id.in_(project_ids)))
        await db.execute(delete(ProshoUser).where(ProshoUser.github_id.between(TEST_ID_MIN, TEST_ID_MAX)))
        await db.commit()


@pytest.fixture(autouse=True)
async def _cleanup():
    yield
    await _purge_test_data()


@pytest.fixture
def make_user():
    """async make_user(login) -> (user, auth headers)"""
    async def _make(login: str = "student", **fields):
        async with AsyncSessionLocal() as db:
            user = ProshoUser(github_id=next(_ids), github_login=login, **fields)
            db.add(user)
            await db.commit()
            await db.refresh(user)
        return user, {"Authorization": f"Bearer {issue_access_token(user.id)}"}
    return _make
