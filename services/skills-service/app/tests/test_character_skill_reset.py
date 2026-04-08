"""
(FEAT-125) Tests for POST /skills/characters/{cid}/skills/{sid}/reset:

- Successful reset clears all selected perks, sets reset_available_at,
  drops level back to 0 (no XP refund).
- Resetting again within 24h returns 409.
- Resetting a level-0 skill returns 409.
- After cooldown expires, reset works again.
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from auth_http import get_current_user_via_http, UserRead


_async_test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
)
_AsyncTestSessionLocal = async_sessionmaker(
    _async_test_engine, expire_on_commit=False, class_=AsyncSession,
)


import database  # noqa: E402

import models  # noqa: E402
import main as main_module  # noqa: E402
from main import app  # noqa: E402

_main_get_db = main_module.get_db


async def _override_get_db():
    async with _AsyncTestSessionLocal() as session:
        yield session

app.router.on_startup.clear()


_OWNER = UserRead(id=5, username="owner", role="user", permissions=[])


def _override_owner():
    return _OWNER


@pytest_asyncio.fixture()
async def setup_db():
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    async with _AsyncTestSessionLocal() as session:
        await session.execute(
            text("CREATE TABLE IF NOT EXISTS characters ("
                 "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)")
        )
        await session.execute(text("DELETE FROM characters"))
        await session.execute(text("INSERT INTO characters (id, user_id) VALUES (100, 5)"))
        await session.commit()
    yield
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def db_session(setup_db):
    async with _AsyncTestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture()
async def owner_client(setup_db):
    app.dependency_overrides[_main_get_db] = _override_get_db
    app.dependency_overrides[get_current_user_via_http] = _override_owner
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def _seed(db: AsyncSession, *, level: int, picked_perks: int = 0,
                reset_available_at=None):
    skill = models.Skill(id=1, name="Fireball", skill_type="Attack", purchase_cost=100)
    db.add(skill)
    await db.flush()
    for i in range(4):
        db.add(models.SkillPerk(id=100 + i, skill_id=1, name=f"P{i}"))
    cs = models.CharacterSkill(
        id=1, character_id=100, skill_id=1, level=level,
        reset_available_at=reset_available_at,
    )
    db.add(cs)
    await db.flush()
    for i in range(picked_perks):
        db.add(models.CharacterSkillPerk(character_skill_id=cs.id, skill_perk_id=100 + i))
    await db.commit()
    return cs


# ---------------------------------------------------------------------------

class TestResetCharacterSkill:

    @pytest.mark.asyncio
    async def test_reset_clears_perks_and_sets_cooldown(self, owner_client, db_session):
        await _seed(db_session, level=4, picked_perks=4)
        before = datetime.utcnow()
        resp = await owner_client.post("/skills/characters/100/skills/1/reset")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["level"] == 0
        assert data["selected_perk_ids"] == []
        assert data["free_perk_points"] == 0
        assert data["reset_available_at"] is not None

        # cooldown ~ 24h ahead
        ts = datetime.fromisoformat(data["reset_available_at"])
        delta = ts - before
        assert timedelta(hours=23, minutes=55) < delta < timedelta(hours=24, minutes=5)

    @pytest.mark.asyncio
    async def test_reset_level_0_rejected(self, owner_client, db_session):
        await _seed(db_session, level=0)
        resp = await owner_client.post("/skills/characters/100/skills/1/reset")
        assert resp.status_code == 409
        assert "0" in resp.json()["detail"] or "сброс" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_reset_within_cooldown_rejected(self, owner_client, db_session):
        future = datetime.utcnow() + timedelta(hours=10)
        await _seed(db_session, level=2, picked_perks=2, reset_available_at=future)
        resp = await owner_client.post("/skills/characters/100/skills/1/reset")
        assert resp.status_code == 409
        assert "сброс" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_reset_after_cooldown_expired_works(self, owner_client, db_session):
        past = datetime.utcnow() - timedelta(hours=1)
        await _seed(db_session, level=3, picked_perks=3, reset_available_at=past)
        resp = await owner_client.post("/skills/characters/100/skills/1/reset")
        assert resp.status_code == 200
        assert resp.json()["level"] == 0
        assert resp.json()["selected_perk_ids"] == []

    @pytest.mark.asyncio
    async def test_reset_nonexistent_skill_404(self, owner_client, db_session):
        resp = await owner_client.post("/skills/characters/100/skills/999/reset")
        assert resp.status_code == 404
