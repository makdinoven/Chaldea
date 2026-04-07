"""
Tests for FEAT-120: `q` filter on GET /skills/admin/skills/.

Verifies the optional `q` query parameter on `admin_list_skills`:
- omitted / empty → returns all skills (backward compatibility)
- name substring (case-insensitive) match
- numeric `q` matches by id
- no match → empty list
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from auth_http import get_current_user_via_http, UserRead


# ---------------------------------------------------------------------------
# Async SQLite setup
# ---------------------------------------------------------------------------

_async_test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
)

_AsyncTestSessionLocal = async_sessionmaker(
    _async_test_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


import database  # noqa: E402

_original_get_db = database.get_db


async def _override_get_db():
    async with _AsyncTestSessionLocal() as session:
        yield session


import models  # noqa: E402
from main import app  # noqa: E402

app.router.on_startup.clear()


_ADMIN_USER = UserRead(
    id=1,
    username="admin",
    role="admin",
    permissions=["skills:read", "skills:create", "skills:update", "skills:delete"],
)


def _override_admin_user():
    return _ADMIN_USER


@pytest_asyncio.fixture()
async def setup_db():
    database.engine = _async_test_engine
    database.async_session = _AsyncTestSessionLocal
    database.get_db = _override_get_db
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    yield
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def admin_client(setup_db):
    app.dependency_overrides[_original_get_db] = _override_get_db
    app.dependency_overrides[get_current_user_via_http] = _override_admin_user
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def _seed_skills():
    """Insert a deterministic set of skills for filter tests."""
    async with _AsyncTestSessionLocal() as session:
        session.add_all(
            [
                models.Skill(id=1, name="Fireball", skill_type="Attack", description="fire"),
                models.Skill(id=2, name="Ice Shard", skill_type="Attack", description="ice"),
                models.Skill(id=3, name="Heal", skill_type="Support", description="heal"),
                models.Skill(id=42, name="Lightning Bolt", skill_type="Attack", description="zap"),
            ]
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_q_omitted_returns_all_skills(admin_client):
    """No `q` query param → full list (backward compatibility)."""
    await _seed_skills()
    resp = await admin_client.get("/skills/admin/skills/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4
    assert {s["id"] for s in data} == {1, 2, 3, 42}


@pytest.mark.asyncio
async def test_q_empty_string_returns_all_skills(admin_client):
    """Empty `q` → full list (treated like omitted)."""
    await _seed_skills()
    resp = await admin_client.get("/skills/admin/skills/", params={"q": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4


@pytest.mark.asyncio
async def test_q_name_substring_case_insensitive(admin_client):
    """Substring match on name, case-insensitive."""
    await _seed_skills()
    resp = await admin_client.get("/skills/admin/skills/", params={"q": "fire"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Fireball"

    # Upper-case query should match too
    resp_upper = await admin_client.get("/skills/admin/skills/", params={"q": "ICE"})
    assert resp_upper.status_code == 200
    data_upper = resp_upper.json()
    assert len(data_upper) == 1
    assert data_upper[0]["name"] == "Ice Shard"


@pytest.mark.asyncio
async def test_q_numeric_matches_skill_id(admin_client):
    """Numeric `q` matches a skill by exact id."""
    await _seed_skills()
    resp = await admin_client.get("/skills/admin/skills/", params={"q": "42"})
    assert resp.status_code == 200
    data = resp.json()
    ids = {s["id"] for s in data}
    assert 42 in ids
    # Name "Lightning Bolt" doesn't contain "42", so id-match is the only reason it's here.
    assert any(s["id"] == 42 and s["name"] == "Lightning Bolt" for s in data)


@pytest.mark.asyncio
async def test_q_no_match_returns_empty_list(admin_client):
    """`q` matching nothing → empty list (200, not 404)."""
    await _seed_skills()
    resp = await admin_client.get(
        "/skills/admin/skills/", params={"q": "nonexistent_skill_xyz"}
    )
    assert resp.status_code == 200
    assert resp.json() == []
