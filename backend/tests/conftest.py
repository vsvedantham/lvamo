"""Shared test setup. Tests run inside the dev backend container against the
local dev database (`docker compose exec backend pytest`), so every test that
writes rows must clean them up."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import engine
from app.main import app


@pytest.fixture(autouse=True)
async def _dispose_engine():
    # The async engine's pooled connections belong to the event loop that
    # opened them; pytest-asyncio gives each test a fresh loop.
    yield
    await engine.dispose()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
