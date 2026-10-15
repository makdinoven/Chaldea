"""
`secondary_magnitude` — generic second value of a skill/perk effect row
(Burn: `magnitude` = damage per turn, `secondary_magnitude` = dodge reduction
in percentage points).

Pinned here:
  * admin base-effect create/update round-trips the value (read back from DB);
  * admin perk create/update round-trips the value on perk effects;
  * GET /skills/{id}/resolved (the payload battle-service consumes) carries the
    key on every effect dict, and base + perk duplicates are SUMMED;
  * `_merge_resolved_effects` sums it, None only if both sides are None.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from auth_http import get_current_user_via_http, UserRead, allow_jwt_or_service_token


_async_test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
)
_AsyncTestSessionLocal = async_sessionmaker(
    _async_test_engine, expire_on_commit=False, class_=AsyncSession,
)

import database  # noqa: E402,F401

import models  # noqa: E402
import crud  # noqa: E402
import main as main_module  # noqa: E402
from main import app  # noqa: E402

_main_get_db = main_module.get_db


async def _override_get_db():
    async with _AsyncTestSessionLocal() as session:
        yield session

app.router.on_startup.clear()


_ADMIN = UserRead(
    id=1, username="admin", role="admin",
    permissions=["skills:create", "skills:read", "skills:update", "skills:delete"],
)


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
        await session.execute(text("INSERT INTO characters (id, user_id) VALUES (100, 1)"))
        await session.commit()
    yield
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def db_session(setup_db):
    async with _AsyncTestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture()
async def admin_client(setup_db):
    async def _admin():
        return _ADMIN
    app.dependency_overrides[_main_get_db] = _override_get_db
    app.dependency_overrides[get_current_user_via_http] = _admin
    app.dependency_overrides[allow_jwt_or_service_token] = _admin
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def _seed_skill(db: AsyncSession) -> None:
    db.add(models.Skill(id=1, name="Огненный шар", skill_type="Attack",
                        purchase_cost=10, cost_energy=5, cost_mana=10, cooldown=1))
    await db.commit()


_BURN = {
    "target_side": "enemy", "effect_name": "Burn", "chance": 100,
    "duration": 3, "magnitude": 4.0, "secondary_magnitude": 10.0,
}


async def _stored(model, **filters):
    async with _AsyncTestSessionLocal() as s:
        res = await s.execute(select(model).filter_by(**filters).order_by(model.id))
        return res.scalars().all()


# ---------------------------------------------------------------------------
# Admin round-trip
# ---------------------------------------------------------------------------

class TestAdminRoundTrip:

    @pytest.mark.asyncio
    async def test_base_effect_create_and_update(self, admin_client, db_session):
        await _seed_skill(db_session)

        resp = await admin_client.post("/skills/admin/skills/1/base_effects", json=_BURN)
        assert resp.status_code == 201, resp.text
        assert resp.json()["secondary_magnitude"] == 10.0
        effect_id = resp.json()["id"]
        rows = await _stored(models.SkillBaseEffect, skill_id=1)
        assert [r.secondary_magnitude for r in rows] == [10.0]

        resp = await admin_client.put(
            f"/skills/admin/skills/1/base_effects/{effect_id}",
            json=dict(_BURN, secondary_magnitude=20.5),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["secondary_magnitude"] == 20.5
        rows = await _stored(models.SkillBaseEffect, skill_id=1)
        assert [r.secondary_magnitude for r in rows] == [20.5]

    @pytest.mark.asyncio
    async def test_base_effect_defaults_to_null(self, admin_client, db_session):
        await _seed_skill(db_session)
        body = {k: v for k, v in _BURN.items() if k != "secondary_magnitude"}
        resp = await admin_client.post("/skills/admin/skills/1/base_effects", json=body)
        assert resp.status_code == 201, resp.text
        assert resp.json()["secondary_magnitude"] is None
        rows = await _stored(models.SkillBaseEffect, skill_id=1)
        assert rows[0].secondary_magnitude is None

    @pytest.mark.asyncio
    async def test_perk_effect_create_and_update(self, admin_client, db_session):
        await _seed_skill(db_session)
        payload = {"name": "Жар", "sort_order": 0, "damage_entries": [],
                   "effects": [dict(_BURN, secondary_magnitude=7.0)]}

        resp = await admin_client.post("/skills/admin/skills/1/perks", json=payload)
        assert resp.status_code == 201, resp.text
        perk_id = resp.json()["id"]
        assert resp.json()["effects"][0]["secondary_magnitude"] == 7.0

        payload["effects"] = [dict(_BURN, secondary_magnitude=3.5)]
        resp = await admin_client.put(f"/skills/admin/skill_perks/{perk_id}", json=payload)
        assert resp.status_code == 200, resp.text
        # NB: the PUT response itself may carry the pre-update collection
        # (identity-map staleness in crud.update_perk, see docs/ISSUES.md), so
        # verify through a fresh GET and the DB instead.
        got = await admin_client.get(f"/skills/admin/skill_perks/{perk_id}")
        assert got.status_code == 200, got.text
        assert got.json()["effects"][0]["secondary_magnitude"] == 3.5
        rows = await _stored(models.SkillPerkEffect, skill_perk_id=perk_id)
        assert [r.secondary_magnitude for r in rows] == [3.5]


# ---------------------------------------------------------------------------
# Resolved payload (battle-service contract)
# ---------------------------------------------------------------------------

async def _seed_resolved(db: AsyncSession, perk_secondary):
    await _seed_skill(db)
    db.add(models.SkillBaseEffect(skill_id=1, effect_name="Burn", target_side="enemy",
                                  chance=100, duration=2, magnitude=4.0,
                                  secondary_magnitude=10.0))
    db.add(models.SkillBaseEffect(skill_id=1, effect_name="Bleeding", target_side="enemy",
                                  chance=100, duration=2, magnitude=3.0))
    db.add(models.SkillPerk(id=50, skill_id=1, name="Жар"))
    await db.flush()
    db.add(models.SkillPerkEffect(skill_perk_id=50, effect_name="Burn", target_side="enemy",
                                  chance=0, duration=1, magnitude=1.0,
                                  secondary_magnitude=perk_secondary))
    cs = models.CharacterSkill(id=1, character_id=100, skill_id=1, level=1)
    db.add(cs)
    await db.flush()
    db.add(models.CharacterSkillPerk(character_skill_id=cs.id, skill_perk_id=50))
    await db.commit()


class TestResolvedPayload:

    @pytest.mark.asyncio
    async def test_key_present_and_summed(self, admin_client, db_session):
        await _seed_resolved(db_session, perk_secondary=5.0)
        resp = await admin_client.get("/skills/1/resolved", params={"character_id": 100})
        assert resp.status_code == 200, resp.text
        effects = {e["effect_name"]: e for e in resp.json()["effects"]}

        for e in resp.json()["effects"]:
            assert "secondary_magnitude" in e

        assert effects["Burn"]["magnitude"] == 5.0
        assert effects["Burn"]["secondary_magnitude"] == 15.0
        assert effects["Bleeding"]["secondary_magnitude"] is None

    @pytest.mark.asyncio
    async def test_null_side_does_not_wipe_value(self, admin_client, db_session):
        await _seed_resolved(db_session, perk_secondary=None)
        resp = await admin_client.get("/skills/1/resolved", params={"character_id": 100})
        assert resp.status_code == 200, resp.text
        burn = [e for e in resp.json()["effects"] if e["effect_name"] == "Burn"][0]
        assert burn["secondary_magnitude"] == 10.0


# ---------------------------------------------------------------------------
# _merge_resolved_effects unit
# ---------------------------------------------------------------------------

def _eff(sec, mag=1.0):
    return {"effect_name": "Burn", "target_side": "enemy", "attribute_key": None,
            "magnitude": mag, "duration": 1, "chance": 100,
            "secondary_magnitude": sec}


class TestMergeSecondaryMagnitude:

    @pytest.mark.parametrize("a, b, expected", [
        (10.0, 5.0, 15.0),
        (10.0, None, 10.0),
        (None, 4.0, 4.0),
        (None, None, None),
        (2.5, -1.0, 1.5),
    ])
    def test_sum_rules(self, a, b, expected):
        merged = crud._merge_resolved_effects([_eff(a), _eff(b)])
        assert len(merged) == 1
        assert merged[0]["secondary_magnitude"] == expected
        assert merged[0]["magnitude"] == 2.0

    def test_single_effect_untouched(self):
        merged = crud._merge_resolved_effects([_eff(7.0)])
        assert merged[0]["secondary_magnitude"] == 7.0

    def test_missing_key_treated_as_none(self):
        legacy = _eff(None)
        legacy.pop("secondary_magnitude")
        merged = crud._merge_resolved_effects([legacy, _eff(3.0)])
        assert merged[0]["secondary_magnitude"] == 3.0
