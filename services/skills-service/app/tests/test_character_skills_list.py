"""
(FEAT-151, T12) Tests for GET /skills/characters/{character_id}/skills — base costs.

T3 added base `cost_energy` / `cost_mana` / `cooldown` (int, default 0) to the
nested `skill{}` object (`CharacterSkillSummarySkill`), emitted by
`serialize_character_skill()` from the selectinload-ed `cs.skill`.

Covers:
- list items expose the 3 fields inside `skill{}` with correct BASE values;
- values stay BASE (not perk-adjusted) even when the character has selected
  perks with delta_cost_* — paired assertion against /skills/{id}/resolved,
  which DOES apply the deltas;
- skill with default/NULL costs -> 0s, no error;
- backward compatibility: all legacy keys are still present.
"""

import os
import sys
from types import SimpleNamespace

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

import database  # noqa: E402, F401

import models  # noqa: E402
import crud  # noqa: E402
import main as main_module  # noqa: E402
from main import app  # noqa: E402

_main_get_db = main_module.get_db


async def _override_get_db():
    async with _AsyncTestSessionLocal() as session:
        yield session

app.router.on_startup.clear()


_OWNER = UserRead(id=5, username="owner", role="user", permissions=[])

CHARACTER_ID = 100


@pytest_asyncio.fixture()
async def setup_db():
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    async with _AsyncTestSessionLocal() as session:
        # Shared `characters` table (owned by character-service) — needed only
        # by the /resolved ownership check used in the paired assertion.
        await session.execute(text(
            "CREATE TABLE IF NOT EXISTS characters ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)"
        ))
        await session.execute(text("DELETE FROM characters"))
        await session.execute(text(
            "INSERT INTO characters (id, user_id) VALUES (100, 5)"
        ))
        await session.commit()
    yield
    async with _async_test_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def db_session(setup_db):
    async with _AsyncTestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture()
async def client(setup_db):
    """The list endpoint itself is unauthenticated; the auth overrides are for
    the paired /resolved call."""
    async def _override():
        return _OWNER
    app.dependency_overrides[_main_get_db] = _override_get_db
    app.dependency_overrides[get_current_user_via_http] = _override
    app.dependency_overrides[allow_jwt_or_service_token] = _override
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _seed_skill_with_perks(db: AsyncSession):
    """Fireball: base costs 5/10/2, two selected perks with cost deltas
    (mana +2, energy -1, cooldown -5) and one unpicked perk."""
    skill = models.Skill(
        id=1, name="Fireball", skill_type="attack",
        skill_image="https://s3.example/fireball.webp",
        purchase_cost=200, cost_energy=5, cost_mana=10, cooldown=2,
        level_requirement=3,
    )
    db.add(skill)
    await db.flush()

    p1 = models.SkillPerk(id=100, skill_id=1, name="Searing",
                          delta_cost_mana=2, delta_cost_energy=None, delta_cooldown=0)
    p2 = models.SkillPerk(id=101, skill_id=1, name="Quick",
                          delta_cost_mana=0, delta_cost_energy=-1, delta_cooldown=-5)
    p3 = models.SkillPerk(id=102, skill_id=1, name="Unpicked",
                          delta_cost_mana=99, delta_cost_energy=99, delta_cooldown=99)
    db.add_all([p1, p2, p3])

    cs = models.CharacterSkill(id=1, character_id=CHARACTER_ID, skill_id=1, level=3)
    db.add(cs)
    await db.flush()
    db.add(models.CharacterSkillPerk(character_skill_id=cs.id, skill_perk_id=100))
    db.add(models.CharacterSkillPerk(character_skill_id=cs.id, skill_perk_id=101))
    await db.commit()


async def _seed_zero_cost_skill(db: AsyncSession):
    """Punch: costs left at column defaults (0/0/0) — the mock's 0/0/0 edge case."""
    skill = models.Skill(id=2, name="Punch", skill_type="attack")
    db.add(skill)
    cs = models.CharacterSkill(id=2, character_id=CHARACTER_ID, skill_id=2, level=0)
    db.add(cs)
    await db.commit()


LIST_URL = f"/skills/characters/{CHARACTER_ID}/skills"


class TestCharacterSkillsListBaseCosts:

    @pytest.mark.asyncio
    async def test_list_items_expose_base_costs_inside_skill(self, client, db_session):
        await _seed_skill_with_perks(db_session)
        resp = await client.get(LIST_URL)
        assert resp.status_code == 200, resp.text
        items = resp.json()
        assert len(items) == 1
        skill = items[0]["skill"]
        assert skill is not None
        assert skill["cost_energy"] == 5
        assert skill["cost_mana"] == 10
        assert skill["cooldown"] == 2

    @pytest.mark.asyncio
    async def test_costs_are_base_not_perk_adjusted(self, client, db_session):
        """The character HAS selected perks with delta_cost_* — the list must
        still return base values, while /resolved applies the deltas."""
        await _seed_skill_with_perks(db_session)

        list_resp = await client.get(LIST_URL)
        assert list_resp.status_code == 200, list_resp.text
        item = list_resp.json()[0]
        # Perks really are selected on this character_skill
        assert sorted(item["selected_perk_ids"]) == [100, 101]
        # ... yet the nested skill carries BASE values
        assert item["skill"]["cost_energy"] == 5
        assert item["skill"]["cost_mana"] == 10
        assert item["skill"]["cooldown"] == 2

        # Paired assertion: /resolved DOES apply perk deltas
        resolved_resp = await client.get(
            "/skills/1/resolved", params={"character_id": CHARACTER_ID}
        )
        assert resolved_resp.status_code == 200, resolved_resp.text
        resolved = resolved_resp.json()
        assert resolved["cost_energy"] == 4   # 5 + (None) + (-1)
        assert resolved["cost_mana"] == 12    # 10 + 2 + 0
        assert resolved["cooldown"] == 0      # 2 + 0 + (-5) -> floored at 0
        # The two responses genuinely differ -> list is not resolved
        assert (
            item["skill"]["cost_energy"],
            item["skill"]["cost_mana"],
            item["skill"]["cooldown"],
        ) != (
            resolved["cost_energy"],
            resolved["cost_mana"],
            resolved["cooldown"],
        )

    @pytest.mark.asyncio
    async def test_zero_cost_skill_returns_zeros_without_error(self, client, db_session):
        await _seed_zero_cost_skill(db_session)
        resp = await client.get(LIST_URL)
        assert resp.status_code == 200, resp.text
        items = resp.json()
        assert len(items) == 1
        skill = items[0]["skill"]
        assert skill["cost_energy"] == 0
        assert skill["cost_mana"] == 0
        assert skill["cooldown"] == 0

    def test_serializer_null_costs_coerced_to_zero(self):
        """Unit-level: NULL costs (impossible via ORM defaults but possible in
        legacy MySQL rows) must serialize as 0, not None. The schema columns
        are NOT NULL in SQLite so this is exercised on the serializer directly."""
        cs = SimpleNamespace(
            id=7, skill_id=2, character_id=CHARACTER_ID, level=None,
            selected_perks=None, reset_available_at=None,
            skill=SimpleNamespace(
                id=2, name="Punch", skill_type="attack", skill_image=None,
                cost_energy=None, cost_mana=None, cooldown=None,
            ),
        )
        data = crud.serialize_character_skill(cs)
        assert data["skill"]["cost_energy"] == 0
        assert data["skill"]["cost_mana"] == 0
        assert data["skill"]["cooldown"] == 0

    @pytest.mark.asyncio
    async def test_backward_compatible_response_shape(self, client, db_session):
        """All legacy keys are still present alongside the 3 new ones —
        consumers (frontend, battle-service skills_client) must not break."""
        await _seed_skill_with_perks(db_session)
        resp = await client.get(LIST_URL)
        assert resp.status_code == 200, resp.text
        item = resp.json()[0]

        for key in (
            "character_skill_id", "skill_id", "character_id", "level",
            "free_perk_points", "selected_perk_ids", "reset_available_at",
            "skill",
        ):
            assert key in item, f"legacy key {key!r} missing from list item"

        assert item["character_skill_id"] == 1
        assert item["skill_id"] == 1
        assert item["character_id"] == CHARACTER_ID
        assert item["level"] == 3
        assert item["free_perk_points"] == 1  # level 3 - 2 selected perks

        skill_keys = set(item["skill"].keys())
        assert {"id", "name", "skill_type", "skill_image"} <= skill_keys
        assert {"cost_energy", "cost_mana", "cooldown"} <= skill_keys
        assert item["skill"]["id"] == 1
        assert item["skill"]["name"] == "Fireball"
        assert item["skill"]["skill_type"] == "attack"
        assert item["skill"]["skill_image"] == "https://s3.example/fireball.webp"

    @pytest.mark.asyncio
    async def test_character_without_skills_returns_empty_list(self, client, db_session):
        resp = await client.get("/skills/characters/999999/skills")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_non_integer_character_id_is_rejected(self, client, db_session):
        """Path param is int-validated by FastAPI — injection-style input must
        not reach SQL (422, not 500)."""
        resp = await client.get("/skills/characters/1%20OR%201=1/skills")
        assert resp.status_code == 422
