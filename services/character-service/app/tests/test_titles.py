"""
Tests for Character Titles system (FEAT-080, updated: XP rewards instead of bonuses).

Covers:
1. Admin CRUD: create/update/delete title with conditions + XP rewards
2. Grant/Revoke: admin grant (is_custom=True), idempotent grant, revoke
3. Set/Unset Active Title: cosmetic title selection
4. Title Evaluation: auto-grant via cumulative stats / character level
5. Notification: RabbitMQ producer mock for title unlock
6. Error Cases: invalid rarity, nonexistent title/character
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy import text as sa_text

import database
import models
import crud
import schemas
from database import Base
from main import app, get_db
from auth_http import (
    get_admin_user,
    get_current_user_via_http,
    OAUTH2_SCHEME,
    UserRead,
)
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TITLE_ADMIN_USER = UserRead(
    id=1,
    username="admin",
    role="admin",
    permissions=[
        "titles:read", "titles:create", "titles:update",
        "titles:delete", "titles:grant",
        "characters:create", "characters:read", "characters:update",
    ],
)

_REGULAR_USER = UserRead(
    id=2,
    username="player",
    role="user",
    permissions=[],
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session(test_engine, seed_fk_data):
    """Real SQLite session with FK reference data seeded."""
    Base.metadata.create_all(bind=test_engine)
    session = database.SessionLocal()
    seed_fk_data(session)

    # Pre-create shared-DB tables that belong to other services but are
    # queried via raw SQL by crud.evaluate_titles / get_character_titles_with_progress.
    session.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS character_attributes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            strength INTEGER DEFAULT 0,
            agility INTEGER DEFAULT 0,
            intelligence INTEGER DEFAULT 0,
            endurance INTEGER DEFAULT 0,
            charisma INTEGER DEFAULT 0,
            luck INTEGER DEFAULT 0,
            health INTEGER DEFAULT 0,
            max_health INTEGER DEFAULT 0,
            current_health INTEGER DEFAULT 0,
            mana INTEGER DEFAULT 0,
            max_mana INTEGER DEFAULT 0,
            current_mana INTEGER DEFAULT 0,
            energy INTEGER DEFAULT 0,
            max_energy INTEGER DEFAULT 0,
            current_energy INTEGER DEFAULT 0,
            stamina INTEGER DEFAULT 0,
            max_stamina INTEGER DEFAULT 0,
            current_stamina INTEGER DEFAULT 0,
            damage INTEGER DEFAULT 0,
            dodge INTEGER DEFAULT 0,
            res_effects INTEGER DEFAULT 0,
            res_physical INTEGER DEFAULT 0,
            res_catting INTEGER DEFAULT 0,
            res_crushing INTEGER DEFAULT 0,
            res_piercing INTEGER DEFAULT 0,
            res_magic INTEGER DEFAULT 0,
            res_fire INTEGER DEFAULT 0,
            res_ice INTEGER DEFAULT 0,
            res_watering INTEGER DEFAULT 0,
            res_electricity INTEGER DEFAULT 0,
            res_wind INTEGER DEFAULT 0,
            res_sainting INTEGER DEFAULT 0,
            res_damning INTEGER DEFAULT 0,
            critical_hit_chance INTEGER DEFAULT 0,
            critical_damage INTEGER DEFAULT 0,
            vul_effects INTEGER DEFAULT 0,
            vul_physical INTEGER DEFAULT 0,
            vul_catting INTEGER DEFAULT 0,
            vul_crushing INTEGER DEFAULT 0,
            vul_piercing INTEGER DEFAULT 0,
            vul_magic INTEGER DEFAULT 0,
            vul_fire INTEGER DEFAULT 0,
            vul_ice INTEGER DEFAULT 0,
            vul_watering INTEGER DEFAULT 0,
            vul_electricity INTEGER DEFAULT 0,
            vul_sainting INTEGER DEFAULT 0,
            vul_wind INTEGER DEFAULT 0,
            vul_damning INTEGER DEFAULT 0,
            passive_experience INTEGER DEFAULT 0,
            active_experience INTEGER DEFAULT 0
        )
    """))
    session.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS character_cumulative_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            pve_kills INTEGER DEFAULT 0,
            pvp_wins INTEGER DEFAULT 0,
            pvp_losses INTEGER DEFAULT 0,
            total_battles INTEGER DEFAULT 0,
            total_damage_dealt INTEGER DEFAULT 0,
            total_damage_received INTEGER DEFAULT 0,
            max_damage_single_battle INTEGER DEFAULT 0,
            max_win_streak INTEGER DEFAULT 0,
            current_win_streak INTEGER DEFAULT 0,
            total_rounds_survived INTEGER DEFAULT 0,
            low_hp_wins INTEGER DEFAULT 0,
            total_gold_earned INTEGER DEFAULT 0,
            total_gold_spent INTEGER DEFAULT 0,
            items_bought INTEGER DEFAULT 0,
            items_sold INTEGER DEFAULT 0,
            locations_visited INTEGER DEFAULT 0,
            total_transitions INTEGER DEFAULT 0,
            skills_used INTEGER DEFAULT 0,
            items_equipped INTEGER DEFAULT 0
        )
    """))
    session.commit()

    try:
        yield session
    finally:
        # Drop raw-SQL tables that are not in Base.metadata
        session.execute(sa_text("DROP TABLE IF EXISTS character_attributes"))
        session.execute(sa_text("DROP TABLE IF EXISTS character_cumulative_stats"))
        session.commit()
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def title_client(db_session):
    """TestClient with real SQLite DB and admin auth overrides."""

    def override_get_db():
        yield db_session

    def override_admin():
        return _TITLE_ADMIN_USER

    def override_token():
        return "fake-admin-token"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_admin
    app.dependency_overrides[get_current_user_via_http] = override_admin
    app.dependency_overrides[OAUTH2_SCHEME] = override_token
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def user_client(db_session):
    """TestClient with real SQLite DB and regular user auth overrides."""

    def override_get_db():
        yield db_session

    def override_user():
        return _REGULAR_USER

    def override_token():
        return "fake-user-token"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_via_http] = override_user
    app.dependency_overrides[OAUTH2_SCHEME] = override_token
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_character(db, user_id=2, name="TestHero", level=1):
    """Insert a minimal character record into the DB."""
    char = models.Character(
        name=name,
        id_subrace=1,
        id_race=1,
        id_class=1,
        biography="test",
        personality="test",
        appearance="test",
        background="test",
        age=20,
        weight="80",
        height="180",
        avatar="test.png",
        user_id=user_id,
        level=level,
    )
    db.add(char)
    db.commit()
    db.refresh(char)
    return char


def _create_title_direct(db, name="Test Title", rarity="common",
                         conditions=None, reward_passive_exp=0,
                         reward_active_exp=0):
    """Insert a title directly into DB."""
    title = models.Title(
        name=name,
        description="A test title",
        rarity=rarity,
        conditions=conditions,
        reward_passive_exp=reward_passive_exp,
        reward_active_exp=reward_active_exp,
        sort_order=0,
    )
    db.add(title)
    db.commit()
    db.refresh(title)
    return title


def _create_character_attributes(db, character_id, **overrides):
    """Insert a character_attributes row via raw SQL (shared DB table)."""
    defaults = {
        "character_id": character_id,
        "strength": 10, "agility": 10, "intelligence": 10,
        "endurance": 10, "charisma": 5, "luck": 5,
        "health": 10, "max_health": 100, "current_health": 100,
        "mana": 10, "max_mana": 100, "current_mana": 100,
        "energy": 10, "max_energy": 50, "current_energy": 50,
        "stamina": 10, "max_stamina": 50, "current_stamina": 50,
        "damage": 5, "dodge": 3,
    }
    defaults.update(overrides)

    # Build the CREATE TABLE if it doesn't exist (SQLite test env)
    db.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS character_attributes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            strength INTEGER DEFAULT 0,
            agility INTEGER DEFAULT 0,
            intelligence INTEGER DEFAULT 0,
            endurance INTEGER DEFAULT 0,
            charisma INTEGER DEFAULT 0,
            luck INTEGER DEFAULT 0,
            health INTEGER DEFAULT 0,
            max_health INTEGER DEFAULT 0,
            current_health INTEGER DEFAULT 0,
            mana INTEGER DEFAULT 0,
            max_mana INTEGER DEFAULT 0,
            current_mana INTEGER DEFAULT 0,
            energy INTEGER DEFAULT 0,
            max_energy INTEGER DEFAULT 0,
            current_energy INTEGER DEFAULT 0,
            stamina INTEGER DEFAULT 0,
            max_stamina INTEGER DEFAULT 0,
            current_stamina INTEGER DEFAULT 0,
            damage INTEGER DEFAULT 0,
            dodge INTEGER DEFAULT 0,
            res_effects INTEGER DEFAULT 0,
            res_physical INTEGER DEFAULT 0,
            res_catting INTEGER DEFAULT 0,
            res_crushing INTEGER DEFAULT 0,
            res_piercing INTEGER DEFAULT 0,
            res_magic INTEGER DEFAULT 0,
            res_fire INTEGER DEFAULT 0,
            res_ice INTEGER DEFAULT 0,
            res_watering INTEGER DEFAULT 0,
            res_electricity INTEGER DEFAULT 0,
            res_wind INTEGER DEFAULT 0,
            res_sainting INTEGER DEFAULT 0,
            res_damning INTEGER DEFAULT 0,
            critical_hit_chance INTEGER DEFAULT 0,
            critical_damage INTEGER DEFAULT 0,
            vul_effects INTEGER DEFAULT 0,
            vul_physical INTEGER DEFAULT 0,
            vul_catting INTEGER DEFAULT 0,
            vul_crushing INTEGER DEFAULT 0,
            vul_piercing INTEGER DEFAULT 0,
            vul_magic INTEGER DEFAULT 0,
            vul_fire INTEGER DEFAULT 0,
            vul_ice INTEGER DEFAULT 0,
            vul_watering INTEGER DEFAULT 0,
            vul_electricity INTEGER DEFAULT 0,
            vul_sainting INTEGER DEFAULT 0,
            vul_wind INTEGER DEFAULT 0,
            vul_damning INTEGER DEFAULT 0,
            passive_experience INTEGER DEFAULT 0,
            active_experience INTEGER DEFAULT 0
        )
    """))

    cols = ", ".join(defaults.keys())
    placeholders = ", ".join(f":{k}" for k in defaults.keys())
    db.execute(sa_text(f"INSERT INTO character_attributes ({cols}) VALUES ({placeholders})"), defaults)
    db.commit()


def _create_cumulative_stats(db, character_id, **stats):
    """Insert a character_cumulative_stats row via raw SQL."""
    db.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS character_cumulative_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            pve_kills INTEGER DEFAULT 0,
            pvp_wins INTEGER DEFAULT 0,
            pvp_losses INTEGER DEFAULT 0,
            total_battles INTEGER DEFAULT 0,
            total_damage_dealt INTEGER DEFAULT 0,
            total_damage_received INTEGER DEFAULT 0,
            max_damage_single_battle INTEGER DEFAULT 0,
            max_win_streak INTEGER DEFAULT 0,
            current_win_streak INTEGER DEFAULT 0,
            total_rounds_survived INTEGER DEFAULT 0,
            low_hp_wins INTEGER DEFAULT 0,
            total_gold_earned INTEGER DEFAULT 0,
            total_gold_spent INTEGER DEFAULT 0,
            items_bought INTEGER DEFAULT 0,
            items_sold INTEGER DEFAULT 0,
            locations_visited INTEGER DEFAULT 0,
            total_transitions INTEGER DEFAULT 0,
            skills_used INTEGER DEFAULT 0,
            items_equipped INTEGER DEFAULT 0
        )
    """))

    defaults = {"character_id": character_id}
    defaults.update(stats)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join(f":{k}" for k in defaults.keys())
    db.execute(sa_text(f"INSERT INTO character_cumulative_stats ({cols}) VALUES ({placeholders})"), defaults)
    db.commit()


def _get_attr(db, character_id, attr_name):
    """Read a single attribute from character_attributes."""
    row = db.execute(
        sa_text(f"SELECT {attr_name} FROM character_attributes WHERE character_id = :cid"),
        {"cid": character_id},
    ).fetchone()
    return row[0] if row else None


# ═══════════════════════════════════════════════════════════════════════════
# 1. Admin CRUD Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestAdminCreateTitle:
    """Test admin title creation endpoint."""

    def test_create_title_with_conditions_and_xp_rewards(self, title_client):
        """Create title with full fields and verify all saved."""
        payload = {
            "name": "Убийца драконов",
            "description": "Награда за убийство 100 мобов",
            "rarity": "legendary",
            "conditions": [
                {"type": "cumulative_stat", "stat": "pve_kills", "operator": ">=", "value": 100}
            ],
            "reward_passive_exp": 500,
            "reward_active_exp": 200,
            "icon": "dragon_slayer.png",
            "sort_order": 10,
        }
        resp = title_client.post("/characters/admin/titles", json=payload)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "Убийца драконов"
        assert data["rarity"] == "legendary"
        assert data["conditions"] is not None
        assert len(data["conditions"]) == 1
        assert data["conditions"][0]["type"] == "cumulative_stat"
        assert data["reward_passive_exp"] == 500
        assert data["reward_active_exp"] == 200
        assert data["icon"] == "dragon_slayer.png"
        assert data["sort_order"] == 10
        assert data["is_active"] is True
        assert data["id_title"] is not None

    def test_create_title_minimal(self, title_client):
        """Create title with only name — defaults applied."""
        payload = {"name": "Новичок"}
        resp = title_client.post("/characters/admin/titles", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["rarity"] == "common"
        assert data["is_active"] is True

    def test_create_title_invalid_rarity(self, title_client):
        """Invalid rarity should be rejected by Pydantic validator."""
        payload = {"name": "Bad Title", "rarity": "mythical"}
        resp = title_client.post("/characters/admin/titles", json=payload)
        assert resp.status_code == 422  # Pydantic validation error


class TestAdminUpdateTitle:
    """Test admin title update endpoint."""

    def test_update_title_fields(self, db_session, title_client):
        """Update title name and rarity, verify changes."""
        title = _create_title_direct(db_session, name="Old Name", rarity="common")
        payload = {"name": "New Name", "rarity": "rare"}
        resp = title_client.put(f"/characters/admin/titles/{title.id_title}", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["rarity"] == "rare"

    def test_update_title_xp_rewards(self, db_session, title_client):
        """Update title XP reward fields."""
        title = _create_title_direct(
            db_session, name="Reward Title",
            reward_passive_exp=100, reward_active_exp=50,
        )

        payload = {"reward_passive_exp": 200, "reward_active_exp": 100}
        resp = title_client.put(f"/characters/admin/titles/{title.id_title}", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["reward_passive_exp"] == 200
        assert data["reward_active_exp"] == 100

    def test_update_nonexistent_title(self, title_client):
        """Updating a nonexistent title returns 404."""
        payload = {"name": "Ghost"}
        resp = title_client.put("/characters/admin/titles/99999", json=payload)
        assert resp.status_code == 404


class TestAdminDeleteTitle:
    """Test admin title deletion endpoint."""

    def test_delete_title_clears_active_and_records(self, db_session, title_client):
        """Delete title clears current_title_id for holders and deletes character_titles records."""
        title = _create_title_direct(db_session, name="Delete Me")
        char = _create_character(db_session)

        # Grant and activate
        ct = models.CharacterTitle(character_id=char.id, title_id=title.id_title, is_custom=True)
        db_session.add(ct)
        char.current_title_id = title.id_title
        db_session.commit()

        # Delete title
        resp = title_client.delete(f"/characters/admin/titles/{title.id_title}")
        assert resp.status_code == 200

        # Verify current_title_id cleared
        db_session.refresh(char)
        assert char.current_title_id is None

        # Verify character_titles record deleted
        ct_count = db_session.query(models.CharacterTitle).filter(
            models.CharacterTitle.title_id == title.id_title
        ).count()
        assert ct_count == 0

    def test_delete_nonexistent_title(self, title_client):
        """Deleting a nonexistent title returns 404."""
        resp = title_client.delete("/characters/admin/titles/99999")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 2. Grant/Revoke Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestGrantTitle:
    """Test admin grant title endpoint."""

    def test_grant_title_to_character(self, db_session, title_client):
        """Grant title creates character_titles record with is_custom=True."""
        title = _create_title_direct(db_session, name="Granted Title")
        char = _create_character(db_session)

        resp = title_client.post(
            "/characters/admin/titles/grant",
            json={"character_id": char.id, "title_id": title.id_title},
        )
        assert resp.status_code == 200

        ct = db_session.query(models.CharacterTitle).filter(
            models.CharacterTitle.character_id == char.id,
            models.CharacterTitle.title_id == title.id_title,
        ).first()
        assert ct is not None
        assert ct.is_custom is True

    def test_grant_duplicate_is_idempotent(self, db_session, title_client):
        """Granting same title twice should not error."""
        title = _create_title_direct(db_session, name="Dup Title")
        char = _create_character(db_session)

        resp1 = title_client.post(
            "/characters/admin/titles/grant",
            json={"character_id": char.id, "title_id": title.id_title},
        )
        assert resp1.status_code == 200

        resp2 = title_client.post(
            "/characters/admin/titles/grant",
            json={"character_id": char.id, "title_id": title.id_title},
        )
        assert resp2.status_code == 200

        # Only one record
        count = db_session.query(models.CharacterTitle).filter(
            models.CharacterTitle.character_id == char.id,
            models.CharacterTitle.title_id == title.id_title,
        ).count()
        assert count == 1

    def test_grant_nonexistent_title(self, db_session, title_client):
        """Granting nonexistent title returns error."""
        char = _create_character(db_session)
        resp = title_client.post(
            "/characters/admin/titles/grant",
            json={"character_id": char.id, "title_id": 99999},
        )
        assert resp.status_code in (404, 400)


class TestRevokeTitle:
    """Test admin revoke title endpoint."""

    def test_revoke_title(self, db_session, title_client):
        """Revoke removes character_titles record."""
        title = _create_title_direct(db_session, name="Revokable")
        char = _create_character(db_session)

        ct = models.CharacterTitle(character_id=char.id, title_id=title.id_title, is_custom=True)
        db_session.add(ct)
        db_session.commit()

        resp = title_client.delete(f"/characters/admin/titles/grant/{char.id}/{title.id_title}")
        assert resp.status_code == 200

        remaining = db_session.query(models.CharacterTitle).filter(
            models.CharacterTitle.character_id == char.id,
            models.CharacterTitle.title_id == title.id_title,
        ).first()
        assert remaining is None

    def test_revoke_active_title_clears_current(self, db_session, title_client):
        """Revoking active title clears current_title_id."""
        title = _create_title_direct(db_session, name="Active Revoke")
        char = _create_character(db_session)

        ct = models.CharacterTitle(character_id=char.id, title_id=title.id_title, is_custom=True)
        db_session.add(ct)
        char.current_title_id = title.id_title
        db_session.commit()

        # Revoke
        resp = title_client.delete(f"/characters/admin/titles/grant/{char.id}/{title.id_title}")
        assert resp.status_code == 200

        # current_title_id cleared
        db_session.refresh(char)
        assert char.current_title_id is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. Set/Unset Active Title Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSetActiveTitle:
    """Test set/unset active title endpoints."""

    def test_set_active_title_cosmetic(self, db_session, title_client):
        """Setting active title sets current_title_id (cosmetic only)."""
        title = _create_title_direct(db_session, name="Active Title")
        char = _create_character(db_session, user_id=_TITLE_ADMIN_USER.id)

        # Grant title
        ct = models.CharacterTitle(character_id=char.id, title_id=title.id_title, is_custom=True)
        db_session.add(ct)
        db_session.commit()

        # Set active
        resp = title_client.post(f"/characters/{char.id}/current-title/{title.id_title}")
        assert resp.status_code == 200

        # Verify current_title_id set
        db_session.refresh(char)
        assert char.current_title_id == title.id_title

    def test_swap_active_title(self, db_session, title_client):
        """Swapping active title just changes current_title_id."""
        title_a = _create_title_direct(db_session, name="Title A")
        title_b = _create_title_direct(db_session, name="Title B")
        char = _create_character(db_session, user_id=_TITLE_ADMIN_USER.id)

        # Grant both titles
        for t in [title_a, title_b]:
            db_session.add(models.CharacterTitle(character_id=char.id, title_id=t.id_title, is_custom=True))
        db_session.commit()

        # Activate title A
        resp = title_client.post(f"/characters/{char.id}/current-title/{title_a.id_title}")
        assert resp.status_code == 200
        db_session.refresh(char)
        assert char.current_title_id == title_a.id_title

        # Swap to title B
        resp = title_client.post(f"/characters/{char.id}/current-title/{title_b.id_title}")
        assert resp.status_code == 200
        db_session.refresh(char)
        assert char.current_title_id == title_b.id_title

    def test_unset_active_title(self, db_session, title_client):
        """Unsetting active title clears current_title_id."""
        title = _create_title_direct(db_session, name="Unset Me")
        char = _create_character(db_session, user_id=_TITLE_ADMIN_USER.id)

        ct = models.CharacterTitle(character_id=char.id, title_id=title.id_title, is_custom=True)
        db_session.add(ct)
        db_session.commit()

        # Activate
        title_client.post(f"/characters/{char.id}/current-title/{title.id_title}")

        # Unset
        resp = title_client.delete(f"/characters/{char.id}/current-title")
        assert resp.status_code == 200

        db_session.refresh(char)
        assert char.current_title_id is None

    def test_set_title_not_owned_returns_error(self, db_session, title_client):
        """Setting a title the character doesn't own returns error."""
        title = _create_title_direct(db_session, name="Not Owned")
        char = _create_character(db_session, user_id=_TITLE_ADMIN_USER.id)

        resp = title_client.post(f"/characters/{char.id}/current-title/{title.id_title}")
        assert resp.status_code in (403, 400)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Title Evaluation (Auto-Grant) Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestEvaluateTitles:
    """Test evaluate_titles (auto-grant) logic via CRUD function."""

    def test_evaluate_cumulative_stat_condition_met(self, db_session):
        """Title with cumulative_stat condition is auto-granted when met."""
        title = _create_title_direct(
            db_session, name="Mob Slayer",
            conditions=[{"type": "cumulative_stat", "stat": "pve_kills", "operator": ">=", "value": 50}],
        )
        char = _create_character(db_session)
        _create_cumulative_stats(db_session, char.id, pve_kills=100)

        newly_unlocked = crud.evaluate_titles(db_session, char.id)

        assert len(newly_unlocked) == 1
        assert newly_unlocked[0]["name"] == "Mob Slayer"

        # Verify character_titles record created
        ct = db_session.query(models.CharacterTitle).filter(
            models.CharacterTitle.character_id == char.id,
            models.CharacterTitle.title_id == title.id_title,
        ).first()
        assert ct is not None
        assert ct.is_custom is False

    def test_evaluate_condition_not_met(self, db_session):
        """Title is NOT granted when conditions not met."""
        _create_title_direct(
            db_session, name="Elite Slayer",
            conditions=[{"type": "cumulative_stat", "stat": "pve_kills", "operator": ">=", "value": 500}],
        )
        char = _create_character(db_session)
        _create_cumulative_stats(db_session, char.id, pve_kills=10)

        newly_unlocked = crud.evaluate_titles(db_session, char.id)
        assert len(newly_unlocked) == 0

    def test_evaluate_character_level_condition(self, db_session):
        """Title with character_level condition auto-granted when met."""
        title = _create_title_direct(
            db_session, name="Veteran",
            conditions=[{"type": "character_level", "operator": ">=", "value": 10}],
        )
        char = _create_character(db_session, level=15)
        _create_cumulative_stats(db_session, char.id)

        newly_unlocked = crud.evaluate_titles(db_session, char.id)
        assert len(newly_unlocked) == 1
        assert newly_unlocked[0]["name"] == "Veteran"

    def test_evaluate_level_condition_not_met(self, db_session):
        """Level condition not met — title not granted."""
        _create_title_direct(
            db_session, name="Master",
            conditions=[{"type": "character_level", "operator": ">=", "value": 50}],
        )
        char = _create_character(db_session, level=5)
        _create_cumulative_stats(db_session, char.id)

        newly_unlocked = crud.evaluate_titles(db_session, char.id)
        assert len(newly_unlocked) == 0

    def test_evaluate_admin_grant_title_not_auto_granted(self, db_session):
        """Titles with only admin_grant condition should not auto-unlock."""
        _create_title_direct(
            db_session, name="Admin Only",
            conditions=[{"type": "admin_grant"}],
        )
        char = _create_character(db_session)
        _create_cumulative_stats(db_session, char.id)

        newly_unlocked = crud.evaluate_titles(db_session, char.id)
        assert len(newly_unlocked) == 0

    def test_evaluate_already_earned_not_duplicated(self, db_session):
        """Already earned title is not granted again."""
        title = _create_title_direct(
            db_session, name="Already Earned",
            conditions=[{"type": "cumulative_stat", "stat": "pvp_wins", "operator": ">=", "value": 1}],
        )
        char = _create_character(db_session)
        _create_cumulative_stats(db_session, char.id, pvp_wins=10)

        # Pre-grant
        ct = models.CharacterTitle(character_id=char.id, title_id=title.id_title, is_custom=False)
        db_session.add(ct)
        db_session.commit()

        newly_unlocked = crud.evaluate_titles(db_session, char.id)
        assert len(newly_unlocked) == 0

    def test_evaluate_no_conditions_not_auto_granted(self, db_session):
        """Titles with no conditions should NOT auto-unlock."""
        _create_title_direct(db_session, name="Cosmetic Only")
        char = _create_character(db_session)
        _create_cumulative_stats(db_session, char.id)

        newly_unlocked = crud.evaluate_titles(db_session, char.id)
        assert len(newly_unlocked) == 0

    def test_evaluate_multiple_conditions_all_must_pass(self, db_session):
        """Title with multiple conditions: all must be met (AND logic)."""
        _create_title_direct(
            db_session, name="Double Req",
            conditions=[
                {"type": "cumulative_stat", "stat": "pve_kills", "operator": ">=", "value": 10},
                {"type": "character_level", "operator": ">=", "value": 5},
            ],
        )
        char = _create_character(db_session, level=3)  # level not met
        _create_cumulative_stats(db_session, char.id, pve_kills=20)

        newly_unlocked = crud.evaluate_titles(db_session, char.id)
        assert len(newly_unlocked) == 0  # level condition fails

    def test_evaluate_multiple_conditions_both_met(self, db_session):
        """Title with multiple conditions: all met — granted."""
        title = _create_title_direct(
            db_session, name="Double Met",
            conditions=[
                {"type": "cumulative_stat", "stat": "pve_kills", "operator": ">=", "value": 10},
                {"type": "character_level", "operator": ">=", "value": 5},
            ],
        )
        char = _create_character(db_session, level=10)
        _create_cumulative_stats(db_session, char.id, pve_kills=20)

        newly_unlocked = crud.evaluate_titles(db_session, char.id)
        assert len(newly_unlocked) == 1
        assert newly_unlocked[0]["name"] == "Double Met"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Notification Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestTitleNotification:
    """Test that notifications are sent when titles are auto-granted."""

    @patch("main.send_title_unlocked_notification", new_callable=AsyncMock)
    def test_notification_sent_on_auto_grant(self, mock_notify, db_session, title_client):
        """Evaluate titles endpoint sends notification for newly unlocked title."""
        title = _create_title_direct(
            db_session, name="Notify Me",
            conditions=[{"type": "cumulative_stat", "stat": "pvp_wins", "operator": ">=", "value": 1}],
        )
        char = _create_character(db_session, user_id=5)
        _create_cumulative_stats(db_session, char.id, pvp_wins=10)

        resp = title_client.post(
            "/characters/internal/evaluate-titles",
            json={"character_id": char.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["newly_unlocked_titles"]) == 1
        assert data["newly_unlocked_titles"][0]["name"] == "Notify Me"

        # Verify notification was called
        mock_notify.assert_called_once_with(5, "Notify Me")

    @patch("main.send_title_unlocked_notification", new_callable=AsyncMock)
    def test_no_notification_when_no_titles_unlocked(self, mock_notify, db_session, title_client):
        """No notification sent when no titles are unlocked."""
        char = _create_character(db_session, user_id=5)
        _create_cumulative_stats(db_session, char.id)

        resp = title_client.post(
            "/characters/internal/evaluate-titles",
            json={"character_id": char.id},
        )
        assert resp.status_code == 200
        assert len(resp.json()["newly_unlocked_titles"]) == 0
        mock_notify.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# 6. Error Cases
# ═══════════════════════════════════════════════════════════════════════════

class TestErrorCases:
    """Test error handling for edge cases."""

    def test_delete_nonexistent_title_returns_error(self, title_client):
        """Deleting a title that doesn't exist returns 404."""
        resp = title_client.delete("/characters/admin/titles/99999")
        assert resp.status_code == 404

    def test_set_active_title_nonexistent_character(self, db_session, title_client):
        """Setting active title on a nonexistent character returns error."""
        title = _create_title_direct(db_session, name="Orphan Title")
        resp = title_client.post(f"/characters/99999/current-title/{title.id_title}")
        assert resp.status_code in (404, 400)

    def test_unset_title_nonexistent_character(self, title_client):
        """Unsetting title on a nonexistent character returns error."""
        resp = title_client.delete("/characters/99999/current-title")
        assert resp.status_code in (404, 400)

    def test_grant_title_nonexistent_character(self, db_session, title_client):
        """Granting title to nonexistent character returns error."""
        title = _create_title_direct(db_session, name="No Char")
        resp = title_client.post(
            "/characters/admin/titles/grant",
            json={"character_id": 99999, "title_id": title.id_title},
        )
        assert resp.status_code in (404, 400)

    def test_list_titles_admin(self, db_session, title_client):
        """Admin list titles endpoint returns paginated results."""
        _create_title_direct(db_session, name="List Title 1")
        _create_title_direct(db_session, name="List Title 2", rarity="rare")

        resp = title_client.get("/characters/admin/titles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        assert len(data["items"]) >= 2

    def test_list_titles_filter_by_rarity(self, db_session, title_client):
        """Admin list titles with rarity filter."""
        _create_title_direct(db_session, name="Common T", rarity="common")
        _create_title_direct(db_session, name="Rare T", rarity="rare")

        resp = title_client.get("/characters/admin/titles?rarity=rare")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["rarity"] == "rare"


# ═══════════════════════════════════════════════════════════════════════════
# 7. CRUD Unit Tests (direct function calls)
# ═══════════════════════════════════════════════════════════════════════════

class TestCrudFunctions:
    """Direct unit tests for CRUD functions."""

    def test_compare_function(self):
        """Test _compare helper with various operators."""
        assert crud._compare(10, ">=", 5) is True
        assert crud._compare(5, ">=", 5) is True
        assert crud._compare(4, ">=", 5) is False
        assert crud._compare(10, ">", 5) is True
        assert crud._compare(5, ">", 5) is False
        assert crud._compare(5, "==", 5) is True
        assert crud._compare(3, "<=", 5) is True
        assert crud._compare(3, "<", 5) is True

    def test_grant_title_xp_reward(self, db_session):
        """Grant title with XP rewards updates character_attributes."""
        title = _create_title_direct(
            db_session, name="XP Title",
            reward_passive_exp=100, reward_active_exp=50,
        )
        char = _create_character(db_session)
        _create_character_attributes(db_session, char.id, passive_experience=0, active_experience=0)

        result, status = crud.grant_title(db_session, char.id, title.id_title)
        assert status == "granted"

        # Check XP was added
        row = db_session.execute(
            sa_text("SELECT passive_experience, active_experience FROM character_attributes WHERE character_id = :cid"),
            {"cid": char.id},
        ).fetchone()
        assert row[0] == 100  # passive
        assert row[1] == 50   # active
