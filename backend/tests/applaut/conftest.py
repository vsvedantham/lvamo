"""Applaut test helpers. Test users have emails ending in TEST_EMAIL_DOMAIN and
shared test jobs use source TEST_SOURCE; both are removed after each test
(profiles, private jobs, assessments, documents, tasks cascade from the user)."""
import uuid

import pytest
from sqlalchemy import delete

from app.applaut.models.opportunity import Opportunity
from app.applaut.models.profile import Profile
from app.applaut.models.user import User
from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal

TEST_EMAIL_DOMAIN = "@applaut-test.invalid"
TEST_SOURCE = "applaut_test"


async def _purge_test_data():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Opportunity).where(Opportunity.source == TEST_SOURCE))
        await db.execute(delete(User).where(User.email.endswith(TEST_EMAIL_DOMAIN)))
        await db.commit()


@pytest.fixture(autouse=True)
async def _cleanup():
    yield
    await _purge_test_data()


@pytest.fixture
def make_user():
    """async make_user(**profile_fields) -> (user, profile, auth headers)"""
    async def _make(**profile_fields):
        async with AsyncSessionLocal() as db:
            user = User(email=f"{uuid.uuid4().hex[:12]}{TEST_EMAIL_DOMAIN}", name="Test User")
            db.add(user)
            await db.flush()
            profile = Profile(
                user_id=user.id,
                display_name="Test User",
                target_roles=["Data Engineer"],
                target_countries=["DE"],
                **profile_fields,
            )
            db.add(profile)
            await db.commit()
            await db.refresh(user)
            await db.refresh(profile)
        return user, profile, {"Authorization": f"Bearer {create_access_token(user.id)}"}
    return _make


@pytest.fixture
def make_opportunity():
    """async make_opportunity(owner=None, **fields) -> Opportunity (shared when owner is None)"""
    async def _make(owner: User | None = None, **fields):
        async with AsyncSessionLocal() as db:
            opp = Opportunity(
                source=fields.pop("source", "own_routine" if owner else TEST_SOURCE),
                external_id=fields.pop("external_id", uuid.uuid4().hex),
                title=fields.pop("title", "Data Engineer"),
                company_name=fields.pop("company_name", "Test GmbH"),
                country_code=fields.pop("country_code", "DE"),
                owner_user_id=owner.id if owner else None,
                is_active=True,
                raw_data={},
                **fields,
            )
            db.add(opp)
            await db.commit()
            await db.refresh(opp)
        return opp
    return _make
