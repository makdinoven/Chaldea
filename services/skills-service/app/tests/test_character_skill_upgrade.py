"""
(FEAT-125) Tests for the per-character skill perk upgrade flow in skills-service:

- POST /skills/characters/{cid}/skills/{sid}/upgrade
- POST /skills/characters/{cid}/skills/{sid}/perks/{perk_id}

Covers purchase -> upgrade x4 -> pick perks, free-point constraints,
double-pick rejection, level cap and XP deduction via mocks.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, AsyncMock

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
            text(
                "CREATE TABLE IF NOT EXISTS characters ("
                "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)"
            )
        )
        await session.execute(text("DELETE FROM characters"))
        await session.execute(
            text("INSERT INTO characters (id, user_id) VALUES (100, 5)")
        )
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


async def _seed_skill_with_perks(db: AsyncSession, perk_count: int = 5):
    skill = models.Skill(
        id=1, name="Fireball", skill_type="Attack",
        purchase_cost=100, cost_energy=5, cost_mana=10, cooldown=2, level_requirement=1,
    )
    db.add(skill)
    await db.flush()
    perks = []
    for i in range(perk_count):
        perk = models.SkillPerk(
            id=100 + i, skill_id=1, name=f"Perk{i}", sort_order=i,
            delta_cost_mana=1, delta_cooldown=0,
        )
        db.add(perk)
        perks.append(perk)
    await db.commit()
    return skill, perks


async def _seed_character_skill(db: AsyncSession, cs_id: int = 1, level: int = 0):
    cs = models.CharacterSkill(id=cs_id, character_id=100, skill_id=1, level=level)
    db.add(cs)
    await db.commit()
    await db.refresh(cs)
    return cs


# ---------------------------------------------------------------------------
# Upgrade endpoint
# ---------------------------------------------------------------------------

@patch.object(main_module, "deduct_active_experience", new_callable=AsyncMock)
@patch.object(main_module, "get_active_experience", new_callable=AsyncMock)
class TestUpgradeFlow:

    @pytest.mark.asyncio
    async def test_upgrade_from_level_0_to_1(self, mock_get_exp, mock_deduct, owner_client, db_session):
        mock_get_exp.return_value = 1000
        await _seed_skill_with_perks(db_session)
        await _seed_character_skill(db_session, level=0)

        resp = await owner_client.post("/skills/characters/100/skills/1/upgrade")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["level"] == 1
        assert data["free_perk_points"] == 1
        # cost = floor(100 / 2) = 50
        mock_deduct.assert_called_once_with(100, 50)

    @pytest.mark.asyncio
    async def test_cannot_upgrade_with_unspent_perk_point(self, mock_get_exp, mock_deduct, owner_client, db_session):
        mock_get_exp.return_value = 1000
        await _seed_skill_with_perks(db_session)
        await _seed_character_skill(db_session, level=1)  # 1 free point unspent

        resp = await owner_client.post("/skills/characters/100/skills/1/upgrade")
        assert resp.status_code == 409
        assert "очко" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cannot_upgrade_without_enough_xp(self, mock_get_exp, mock_deduct, owner_client, db_session):
        mock_get_exp.return_value = 10  # cost=50
        await _seed_skill_with_perks(db_session)
        await _seed_character_skill(db_session)

        resp = await owner_client.post("/skills/characters/100/skills/1/upgrade")
        assert resp.status_code == 402
        assert "опыт" in resp.json()["detail"].lower()
        mock_deduct.assert_not_called()

    @pytest.mark.asyncio
    async def test_cannot_upgrade_nonexistent_character_skill(self, mock_get_exp, mock_deduct, owner_client, db_session):
        mock_get_exp.return_value = 1000
        await _seed_skill_with_perks(db_session)
        # no character_skill seeded
        resp = await owner_client.post("/skills/characters/100/skills/1/upgrade")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_exceed_max_level(self, mock_get_exp, mock_deduct, owner_client, db_session):
        mock_get_exp.return_value = 1000
        await _seed_skill_with_perks(db_session)
        # Level 4 with 4 perks picked (no free point)
        cs = await _seed_character_skill(db_session, level=4)
        async with _AsyncTestSessionLocal() as s:
            for i in range(4):
                s.add(models.CharacterSkillPerk(character_skill_id=cs.id, skill_perk_id=100 + i))
            await s.commit()

        resp = await owner_client.post("/skills/characters/100/skills/1/upgrade")
        assert resp.status_code == 409
        assert "максим" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_full_upgrade_pick_cycle_to_level_4(self, mock_get_exp, mock_deduct, owner_client, db_session):
        """Purchase -> upgrade x4 picking a distinct perk each time."""
        mock_get_exp.return_value = 10000
        await _seed_skill_with_perks(db_session)
        await _seed_character_skill(db_session, level=0)

        for level in range(1, 5):
            r = await owner_client.post("/skills/characters/100/skills/1/upgrade")
            assert r.status_code == 200
            assert r.json()["level"] == level
            assert r.json()["free_perk_points"] == 1

            perk_id = 100 + (level - 1)
            r = await owner_client.post(
                f"/skills/characters/100/skills/1/perks/{perk_id}"
            )
            assert r.status_code == 200, r.text
            assert r.json()["free_perk_points"] == 0
            assert perk_id in r.json()["selected_perk_ids"]

        # At level 4 with 4 perks -> further upgrade must 409
        r = await owner_client.post("/skills/characters/100/skills/1/upgrade")
        assert r.status_code == 409


# ---------------------------------------------------------------------------
# Perk pick endpoint
# ---------------------------------------------------------------------------

class TestPickPerk:

    @pytest.mark.asyncio
    async def test_cannot_pick_without_free_point(self, owner_client, db_session):
        await _seed_skill_with_perks(db_session)
        await _seed_character_skill(db_session, level=0)

        resp = await owner_client.post("/skills/characters/100/skills/1/perks/100")
        assert resp.status_code == 409
        assert "очк" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cannot_pick_same_perk_twice(self, owner_client, db_session):
        await _seed_skill_with_perks(db_session)
        cs = await _seed_character_skill(db_session, level=2)
        async with _AsyncTestSessionLocal() as s:
            s.add(models.CharacterSkillPerk(character_skill_id=cs.id, skill_perk_id=100))
            await s.commit()

        # Try to pick perk 100 again — 1 free point exists but duplicate.
        resp = await owner_client.post("/skills/characters/100/skills/1/perks/100")
        assert resp.status_code == 409
        assert "уже выбран" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cannot_pick_perk_of_another_skill(self, owner_client, db_session):
        await _seed_skill_with_perks(db_session)
        # Second skill with its own perk
        other = models.Skill(id=2, name="Ice", skill_type="Attack", purchase_cost=50)
        db_session.add(other)
        await db_session.flush()
        foreign_perk = models.SkillPerk(id=999, skill_id=2, name="Foreign")
        db_session.add(foreign_perk)
        await db_session.commit()
        await _seed_character_skill(db_session, level=1)

        resp = await owner_client.post("/skills/characters/100/skills/1/perks/999")
        assert resp.status_code == 400
        assert "не относится" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_pick_nonexistent_perk(self, owner_client, db_session):
        await _seed_skill_with_perks(db_session)
        await _seed_character_skill(db_session, level=1)
        resp = await owner_client.post("/skills/characters/100/skills/1/perks/77777")
        assert resp.status_code == 404
