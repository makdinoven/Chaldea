"""
Tests for FEAT-021 admin endpoints in skills-service:
- PUT /skills/admin/character_skills/{cs_id}
- DELETE /skills/admin/character_skills/by_character/{character_id}

skills-service is ASYNC (aiomysql), so we use httpx.AsyncClient + ASGITransport.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import httpx
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from auth_http import get_admin_user, UserRead


# ---------------------------------------------------------------------------
# Async SQLite setup for skills-service
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


# ---------------------------------------------------------------------------
# Patch database before importing main
# ---------------------------------------------------------------------------
import database  # noqa: E402
database.engine = _async_test_engine
database.async_session = _AsyncTestSessionLocal


async def _override_get_db():
    async with _AsyncTestSessionLocal() as session:
        yield session


# Replace the module-level get_db as well
database.get_db = _override_get_db

# Also replace create_tables to use our test engine
async def _test_create_tables():
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)

database.create_tables = _test_create_tables

import models  # noqa: E402

# Patch the startup event to avoid RabbitMQ connection
import main as main_module  # noqa: E402
from main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Auth overrides
# ---------------------------------------------------------------------------

_ADMIN_USER = UserRead(id=1, username="admin", role="admin")


def _override_admin():
    return _ADMIN_USER


def _override_non_admin():
    from fastapi import HTTPException
    raise HTTPException(status_code=403, detail="Admin access required")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def setup_db():
    """Create and drop tables for each test."""
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    yield
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def db_session(setup_db):
    async with _AsyncTestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture()
async def admin_client(setup_db):
    app.dependency_overrides[database.get_db] = _override_get_db
    app.dependency_overrides[get_admin_user] = _override_admin
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def non_admin_client(setup_db):
    app.dependency_overrides[database.get_db] = _override_get_db
    app.dependency_overrides[get_admin_user] = _override_non_admin
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

async def _seed_skill(db: AsyncSession):
    """Create a Skill with two SkillRanks."""
    skill = models.Skill(id=1, name="Fireball", skill_type="Attack", description="Fire spell")
    db.add(skill)
    await db.flush()

    rank1 = models.SkillRank(id=1, skill_id=1, rank_number=1, rank_name="Rank I")
    rank2 = models.SkillRank(id=2, skill_id=1, rank_number=2, rank_name="Rank II")
    db.add(rank1)
    db.add(rank2)
    await db.commit()
    return skill, rank1, rank2


async def _seed_character_skill(db: AsyncSession, cs_id=1, character_id=1, skill_rank_id=1):
    """Create a CharacterSkill row."""
    cs = models.CharacterSkill(id=cs_id, character_id=character_id, skill_rank_id=skill_rank_id)
    db.add(cs)
    await db.commit()
    await db.refresh(cs)
    return cs


# ===========================================================================
# PUT /skills/admin/character_skills/{cs_id}
# ===========================================================================

class TestAdminUpdateCharacterSkillRank:

    @pytest.mark.asyncio
    async def test_update_rank_success(self, admin_client, db_session):
        await _seed_skill(db_session)
        await _seed_character_skill(db_session, cs_id=1, skill_rank_id=1)

        resp = await admin_client.put(
            "/skills/admin/character_skills/1",
            json={"skill_rank_id": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["skill_rank"]["id"] == 2

    @pytest.mark.asyncio
    async def test_update_rank_not_found(self, admin_client, db_session):
        resp = await admin_client.put(
            "/skills/admin/character_skills/999",
            json={"skill_rank_id": 1},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_rank_forbidden(self, non_admin_client, db_session):
        resp = await non_admin_client.put(
            "/skills/admin/character_skills/1",
            json={"skill_rank_id": 1},
        )
        assert resp.status_code == 403


# ===========================================================================
# DELETE /skills/admin/character_skills/by_character/{character_id}
# ===========================================================================

class TestAdminDeleteAllCharacterSkills:

    @pytest.mark.asyncio
    async def test_bulk_delete_success(self, admin_client, db_session):
        await _seed_skill(db_session)
        await _seed_character_skill(db_session, cs_id=1, character_id=1, skill_rank_id=1)
        await _seed_character_skill(db_session, cs_id=2, character_id=1, skill_rank_id=2)

        resp = await admin_client.delete("/skills/admin/character_skills/by_character/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["detail"] == "All character skills deleted"
        assert data["count"] == 2

    @pytest.mark.asyncio
    async def test_bulk_delete_empty_case(self, admin_client, db_session):
        """No skills to delete — should return count=0."""
        resp = await admin_client.delete("/skills/admin/character_skills/by_character/999")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_bulk_delete_forbidden(self, non_admin_client, db_session):
        resp = await non_admin_client.delete("/skills/admin/character_skills/by_character/1")
        assert resp.status_code == 403
