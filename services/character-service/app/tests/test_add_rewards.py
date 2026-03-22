"""
Tests for battle rewards and internal mob endpoints (Tasks #18, #20 — Phase 4).

Covers:
1. POST /characters/{id}/add_rewards
   - Correctly adds gold to currency_balance
   - Correctly adds XP to passive_experience
   - Triggers level-up when XP reaches threshold
   - Returns updated balance and XP
   - 404 for non-existent character
   - Validation: negative values rejected

2. GET /characters/internal/mob-reward-data/{character_id}
   - Returns correct reward data for a mob character
   - Returns 404 for non-mob characters
   - Includes loot table entries
"""

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import String, text

import database
import models

# Patch Enum columns to String for SQLite compatibility
for tbl in [
    models.Character,
    models.CharacterRequest,
    models.MobTemplate,
    models.MobLootTable,
    models.MobTemplateSkill,
    models.LocationMobSpawn,
    models.ActiveMob,
]:
    for col in tbl.__table__.columns:
        if type(col.type).__name__ == "Enum":
            col.type = String(50)

from fastapi.testclient import TestClient
from main import app, get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_reference_data(session):
    """Insert minimal FK reference data."""
    for rid, name in [(1, "Человек")]:
        if not session.query(models.Race).filter_by(id_race=rid).first():
            session.add(models.Race(id_race=rid, name=name))
    session.flush()
    for sid, rid, name in [(1, 1, "Норд")]:
        if not session.query(models.Subrace).filter_by(id_subrace=sid).first():
            session.add(models.Subrace(id_subrace=sid, id_race=rid, name=name))
    session.flush()
    for cid, name in [(1, "Воин")]:
        if not session.query(models.Class).filter_by(id_class=cid).first():
            session.add(models.Class(id_class=cid, name=name))
    session.commit()


def _create_character(session, character_id=1, name="TestChar", currency_balance=100,
                      is_npc=False, npc_role=None, user_id=10):
    """Create a minimal Character record."""
    char = models.Character(
        id=character_id,
        name=name,
        id_subrace=1,
        biography="bio",
        personality="pers",
        id_class=1,
        currency_balance=currency_balance,
        user_id=user_id,
        appearance="appearance",
        sex="male",
        id_race=1,
        avatar="/avatar.jpg",
        is_npc=is_npc,
        npc_role=npc_role,
        level=1,
        stat_points=0,
    )
    session.add(char)
    session.commit()
    return char


def _insert_character_attributes(session, character_id, passive_experience=0):
    """Insert a row into the character_attributes table using the session."""
    session.execute(
        text("INSERT INTO character_attributes (character_id, passive_experience) VALUES (:cid, :xp)"),
        {"cid": character_id, "xp": passive_experience},
    )
    session.commit()


def _create_mob_template(session, template_id=1, name="Волк", tier="normal",
                         xp_reward=50, gold_reward=10, level=3):
    """Create a MobTemplate record."""
    tpl = models.MobTemplate(
        id=template_id,
        name=name,
        tier=tier,
        level=level,
        xp_reward=xp_reward,
        gold_reward=gold_reward,
        id_race=1,
        id_subrace=1,
        id_class=1,
        sex="genderless",
    )
    session.add(tpl)
    session.commit()
    return tpl


def _create_active_mob(session, active_mob_id=1, mob_template_id=1,
                       character_id=1, location_id=1, status="alive"):
    """Create an ActiveMob record."""
    am = models.ActiveMob(
        id=active_mob_id,
        mob_template_id=mob_template_id,
        character_id=character_id,
        location_id=location_id,
        status=status,
        spawn_type="random",
    )
    session.add(am)
    session.commit()
    return am


def _create_loot_entry(session, mob_template_id=1, item_id=10,
                       drop_chance=50.0, min_quantity=1, max_quantity=3):
    """Create a MobLootTable entry."""
    entry = models.MobLootTable(
        mob_template_id=mob_template_id,
        item_id=item_id,
        drop_chance=drop_chance,
        min_quantity=min_quantity,
        max_quantity=max_quantity,
    )
    session.add(entry)
    session.commit()
    return entry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session(test_engine, test_session_factory):
    """Real SQLite session with all tables created."""
    # Drop everything first to ensure clean state (StaticPool reuses connection)
    models.Base.metadata.drop_all(bind=test_engine)
    models.Base.metadata.create_all(bind=test_engine)
    session = test_session_factory()
    # Create character_attributes table (not an ORM model in character-service)
    # Using session so that it shares the same connection via StaticPool
    session.execute(text("DROP TABLE IF EXISTS character_attributes"))
    session.execute(text(
        "CREATE TABLE character_attributes ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  character_id INTEGER NOT NULL,"
        "  passive_experience INTEGER DEFAULT 0"
        ")"
    ))
    session.commit()
    _seed_reference_data(session)
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client_with_db(db_session):
    """FastAPI TestClient with real SQLite DB session."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False), db_session
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Tests: POST /characters/{id}/add_rewards
# ═══════════════════════════════════════════════════════════════════════════


class TestAddRewards:
    """Tests for the add_rewards endpoint."""

    def test_adds_gold_correctly(self, client_with_db):
        """Gold is added to currency_balance."""
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=100)
        _insert_character_attributes(session, character_id=1, passive_experience=0)

        response = client.post("/characters/1/add_rewards", json={"xp": 0, "gold": 50})

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["new_balance"] == 150  # 100 + 50

    def test_adds_xp_correctly(self, client_with_db):
        """XP is added to passive_experience via shared DB."""
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=0)
        _insert_character_attributes(session, character_id=1, passive_experience=100)

        response = client.post("/characters/1/add_rewards", json={"xp": 50, "gold": 0})

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["new_xp"] == 150  # 100 + 50

    def test_adds_both_xp_and_gold(self, client_with_db):
        """Both XP and gold are added in a single call."""
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=200)
        _insert_character_attributes(session, character_id=1, passive_experience=500)

        response = client.post("/characters/1/add_rewards", json={"xp": 100, "gold": 30})

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["new_balance"] == 230
        assert data["new_xp"] == 600

    @patch("crud.check_and_update_level")
    def test_triggers_level_up_check(self, mock_level_check, client_with_db):
        """check_and_update_level is called when XP is updated."""
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=0)
        _insert_character_attributes(session, character_id=1, passive_experience=900)

        response = client.post("/characters/1/add_rewards", json={"xp": 200, "gold": 0})

        assert response.status_code == 200
        # check_and_update_level should have been called with new_xp=1100
        mock_level_check.assert_called_once_with(session, 1, 1100)

    def test_character_not_found_returns_404(self, client_with_db):
        """Returns 404 for non-existent character."""
        client, session = client_with_db

        response = client.post("/characters/9999/add_rewards", json={"xp": 10, "gold": 5})

        assert response.status_code == 404

    def test_negative_xp_rejected(self, client_with_db):
        """Negative XP value is rejected by validator."""
        client, session = client_with_db
        _create_character(session, character_id=1)

        response = client.post("/characters/1/add_rewards", json={"xp": -10, "gold": 5})

        assert response.status_code == 422  # Pydantic validation error

    def test_negative_gold_rejected(self, client_with_db):
        """Negative gold value is rejected by validator."""
        client, session = client_with_db
        _create_character(session, character_id=1)

        response = client.post("/characters/1/add_rewards", json={"xp": 5, "gold": -10})

        assert response.status_code == 422

    def test_zero_rewards(self, client_with_db):
        """Zero XP and gold does not change values."""
        client, session = client_with_db
        _create_character(session, character_id=1, currency_balance=50)
        _insert_character_attributes(session, character_id=1, passive_experience=200)

        response = client.post("/characters/1/add_rewards", json={"xp": 0, "gold": 0})

        assert response.status_code == 200
        data = response.json()
        assert data["new_balance"] == 50
        assert data["new_xp"] == 200


# ═══════════════════════════════════════════════════════════════════════════
# Tests: GET /characters/internal/mob-reward-data/{character_id}
# ═══════════════════════════════════════════════════════════════════════════


class TestMobRewardData:
    """Tests for the mob-reward-data endpoint."""

    def test_returns_reward_data_for_mob(self, client_with_db):
        """Returns correct reward data for a mob character."""
        client, session = client_with_db
        _create_character(session, character_id=42, name="Волк", is_npc=True, npc_role="mob")
        _create_mob_template(session, template_id=1, name="Волк", xp_reward=50, gold_reward=10)
        _create_active_mob(session, active_mob_id=1, mob_template_id=1, character_id=42)

        response = client.get("/characters/internal/mob-reward-data/42")

        assert response.status_code == 200
        data = response.json()
        assert data["xp_reward"] == 50
        assert data["gold_reward"] == 10
        assert data["template_name"] == "Волк"
        assert data["tier"] == "normal"
        assert data["loot_table"] == []

    def test_returns_reward_data_with_loot_table(self, client_with_db):
        """Returns loot table entries in reward data."""
        client, session = client_with_db
        _create_character(session, character_id=42, name="Тролль", is_npc=True, npc_role="mob")
        _create_mob_template(session, template_id=1, name="Тролль", tier="elite",
                             xp_reward=150, gold_reward=40)
        _create_active_mob(session, active_mob_id=1, mob_template_id=1, character_id=42)
        _create_loot_entry(session, mob_template_id=1, item_id=10,
                           drop_chance=50.0, min_quantity=1, max_quantity=3)
        _create_loot_entry(session, mob_template_id=1, item_id=20,
                           drop_chance=10.0, min_quantity=1, max_quantity=1)

        response = client.get("/characters/internal/mob-reward-data/42")

        assert response.status_code == 200
        data = response.json()
        assert data["xp_reward"] == 150
        assert data["gold_reward"] == 40
        assert data["tier"] == "elite"
        assert len(data["loot_table"]) == 2
        loot_ids = {entry["item_id"] for entry in data["loot_table"]}
        assert loot_ids == {10, 20}
        for entry in data["loot_table"]:
            if entry["item_id"] == 10:
                assert entry["drop_chance"] == 50.0
                assert entry["min_quantity"] == 1
                assert entry["max_quantity"] == 3

    def test_returns_404_for_non_mob_character(self, client_with_db):
        """Returns 404 when character exists but is not a mob."""
        client, session = client_with_db
        _create_character(session, character_id=1, name="Player", is_npc=False)

        response = client.get("/characters/internal/mob-reward-data/1")

        assert response.status_code == 404

    def test_returns_404_for_npc_without_mob_role(self, client_with_db):
        """Returns 404 for NPC that is not a mob (e.g., npc_role='questgiver')."""
        client, session = client_with_db
        _create_character(session, character_id=1, name="QuestNPC", is_npc=True, npc_role="questgiver")

        response = client.get("/characters/internal/mob-reward-data/1")

        assert response.status_code == 404

    def test_returns_404_for_nonexistent_character(self, client_with_db):
        """Returns 404 for character_id that does not exist."""
        client, session = client_with_db

        response = client.get("/characters/internal/mob-reward-data/9999")

        assert response.status_code == 404

    def test_returns_404_for_mob_without_active_mob_record(self, client_with_db):
        """Returns 404 when mob character exists but has no active_mob record."""
        client, session = client_with_db
        _create_character(session, character_id=42, name="OrphanMob", is_npc=True, npc_role="mob")

        response = client.get("/characters/internal/mob-reward-data/42")

        assert response.status_code == 404
