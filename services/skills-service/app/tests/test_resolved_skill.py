"""
(FEAT-125) Tests for GET /skills/{skill_id}/resolved?character_id=...

Verifies the server-authoritative resolver:
- numeric scalars summed (cost_energy / cost_mana / cooldown)
- damage_entries / effects concatenated (base + selected perks)
- cooldown floored at 0
- level_requirement clamped to base
- 404 / 403 / 409 error paths
- byte-compatibility (R1) of damage_entries / effects with old SkillRank* shape
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from auth_http import get_current_user_via_http, UserRead, allow_jwt_or_service_token


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
_OTHER = UserRead(id=99, username="other", role="user", permissions=[])
_ADMIN = UserRead(id=1, username="admin", role="admin", permissions=[])


@pytest_asyncio.fixture()
async def setup_db():
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    async with _AsyncTestSessionLocal() as session:
        await session.execute(text(
            "CREATE TABLE IF NOT EXISTS characters ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)"
        ))
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


def _make_client(user):
    async def _override():
        return user
    app.dependency_overrides[_main_get_db] = _override_get_db
    app.dependency_overrides[get_current_user_via_http] = _override
    app.dependency_overrides[allow_jwt_or_service_token] = _override
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest_asyncio.fixture()
async def owner_client(setup_db):
    async with _make_client(_OWNER) as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def other_client(setup_db):
    async with _make_client(_OTHER) as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def admin_client(setup_db):
    async with _make_client(_ADMIN) as client:
        yield client
    app.dependency_overrides.clear()


async def _seed_full_skill(db: AsyncSession):
    """
    Skill with base stats + 2 base damage entries + 1 base effect, and 3 perks
    of which two are picked by the test character.
    """
    skill = models.Skill(
        id=1, name="Fireball", skill_type="Attack",
        purchase_cost=200, cost_energy=5, cost_mana=10, cooldown=2, level_requirement=3,
    )
    db.add(skill)
    await db.flush()

    # base
    db.add(models.SkillBaseDamage(skill_id=1, damage_type="fire", amount=10.0,
                                  chance=100, target_side="enemy", weapon_slot="main_weapon"))
    db.add(models.SkillBaseDamage(skill_id=1, damage_type="fire", amount=2.0,
                                  chance=100, target_side="enemy"))
    db.add(models.SkillBaseEffect(skill_id=1, effect_name="burn", target_side="enemy",
                                  chance=100, duration=2, magnitude=1.0))

    # perks
    p1 = models.SkillPerk(id=100, skill_id=1, name="Searing",
                          delta_cost_mana=2, delta_cost_energy=None, delta_cooldown=0)
    p2 = models.SkillPerk(id=101, skill_id=1, name="Quick",
                          delta_cost_mana=0, delta_cost_energy=-1, delta_cooldown=-5)
    p3 = models.SkillPerk(id=102, skill_id=1, name="Unpicked",
                          delta_cost_mana=99, delta_cost_energy=99, delta_cooldown=99)
    db.add_all([p1, p2, p3])
    await db.flush()
    db.add(models.SkillPerkDamage(skill_perk_id=100, damage_type="fire",
                                  amount=3.0, chance=100, target_side="enemy"))
    db.add(models.SkillPerkEffect(skill_perk_id=101, effect_name="slow",
                                  target_side="enemy", chance=100, duration=1, magnitude=2.0))

    cs = models.CharacterSkill(id=1, character_id=100, skill_id=1, level=2)
    db.add(cs)
    await db.flush()
    db.add(models.CharacterSkillPerk(character_skill_id=cs.id, skill_perk_id=100))
    db.add(models.CharacterSkillPerk(character_skill_id=cs.id, skill_perk_id=101))
    await db.commit()


# ---------------------------------------------------------------------------

class TestResolvedSkill:

    @pytest.mark.asyncio
    async def test_resolved_sums_and_concats(self, owner_client, db_session):
        await _seed_full_skill(db_session)
        resp = await owner_client.get("/skills/1/resolved", params={"character_id": 100})
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["skill_id"] == 1
        assert data["character_id"] == 100
        assert data["level"] == 2
        assert sorted(data["selected_perk_ids"]) == [100, 101]
        assert data["skill_type"] == "Attack"

        # cost_energy: base 5 + (None) + (-1) = 4
        assert data["cost_energy"] == 4
        # cost_mana: base 10 + 2 + 0 = 12
        assert data["cost_mana"] == 12
        # cooldown: base 2 + 0 + (-5) = -3 -> floored at 0
        assert data["cooldown"] == 0
        # level_requirement clamped to base value
        assert data["level_requirement"] == 3

        # damage_entries concatenated: 2 base + 1 from perk 100 = 3
        assert len(data["damage_entries"]) == 3
        # All entries preserve byte-compatible field names
        for de in data["damage_entries"]:
            assert "damage_type" in de
            assert "amount" in de
            assert "chance" in de
            assert "target_side" in de
            assert "weapon_slot" in de

        # effects concatenated: 1 base + 1 from perk 101 = 2
        assert len(data["effects"]) == 2
        for ef in data["effects"]:
            assert "effect_name" in ef
            assert "duration" in ef
            assert "magnitude" in ef
            assert "target_side" in ef

    @pytest.mark.asyncio
    async def test_no_perks_picked_returns_base_only(self, owner_client, db_session):
        await _seed_full_skill(db_session)
        # Wipe picks
        async with _AsyncTestSessionLocal() as s:
            await s.execute(text("DELETE FROM character_skill_perks"))
            await s.execute(text("UPDATE character_skills SET level=0 WHERE id=1"))
            await s.commit()

        resp = await owner_client.get("/skills/1/resolved", params={"character_id": 100})
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == 0
        assert data["selected_perk_ids"] == []
        assert data["cost_energy"] == 5
        assert data["cost_mana"] == 10
        assert data["cooldown"] == 2
        assert len(data["damage_entries"]) == 2
        assert len(data["effects"]) == 1

    @pytest.mark.asyncio
    async def test_skill_not_found(self, owner_client, db_session):
        resp = await owner_client.get("/skills/999/resolved", params={"character_id": 100})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_character_does_not_own_skill(self, owner_client, db_session):
        # Seed only the skill but not the character_skill row
        skill = models.Skill(id=1, name="Fireball", skill_type="Attack", purchase_cost=10)
        db_session.add(skill)
        await db_session.commit()

        resp = await owner_client.get("/skills/1/resolved", params={"character_id": 100})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_other_user_forbidden(self, other_client, db_session):
        await _seed_full_skill(db_session)
        resp = await other_client.get("/skills/1/resolved", params={"character_id": 100})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_bypasses_ownership(self, admin_client, db_session):
        await _seed_full_skill(db_session)
        resp = await admin_client.get("/skills/1/resolved", params={"character_id": 100})
        assert resp.status_code == 200
