"""
Tests for FEAT-078 perks system in character-attributes-service:
- Perk CRUD (create, update, delete, list)
- Grant / Revoke perks
- Perk condition evaluator (check_condition, compare, evaluate_perks)
- Player perks endpoint GET /attributes/{id}/perks
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Patch database BEFORE importing main
_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(_test_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

import database  # noqa: E402
database.engine = _test_engine
database.SessionLocal = _TestSessionLocal

import models  # noqa: E402
import schemas  # noqa: E402
import crud  # noqa: E402
from auth_http import get_admin_user, get_current_user_via_http, require_permission, UserRead  # noqa: E402
from perk_evaluator import compare, check_condition, evaluate_perks  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app, get_db  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADMIN_USER = UserRead(
    id=1, username="admin", role="admin",
    permissions=[
        "perks:create", "perks:read", "perks:update", "perks:delete", "perks:grant",
        "characters:create", "characters:read", "characters:update", "characters:delete",
    ],
)
_REGULAR_USER = UserRead(id=2, username="player", role="user", permissions=[])


def _make_perk_payload(**overrides):
    """Return a valid PerkCreate JSON payload with sensible defaults."""
    defaults = {
        "name": "Test Perk",
        "description": "A test perk",
        "category": "combat",
        "rarity": "common",
        "icon": "sword.png",
        "conditions": [
            {"type": "cumulative_stat", "stat": "pvp_wins", "operator": ">=", "value": 10}
        ],
        "bonuses": {
            "flat": {"strength": 5},
            "percent": {},
            "contextual": {},
            "passive": {},
        },
        "sort_order": 0,
    }
    defaults.update(overrides)
    return defaults


def _create_attributes(db, character_id=1, **overrides):
    """Create a CharacterAttributes row and return it."""
    defaults = dict(
        character_id=character_id,
        current_health=100,
        max_health=100,
        current_mana=75,
        max_mana=75,
        current_energy=50,
        max_energy=50,
        current_stamina=50,
        max_stamina=50,
        strength=10,
        agility=10,
        intelligence=10,
        endurance=10,
        health=10,
        mana=7,
        energy=5,
        stamina=10,
        charisma=1,
        luck=1,
        damage=0,
    )
    defaults.update(overrides)
    attr = models.CharacterAttributes(**defaults)
    db.add(attr)
    db.commit()
    db.refresh(attr)
    return attr


def _create_perk_in_db(db, **overrides):
    """Create a Perk row directly in DB and return it."""
    defaults = dict(
        name="DB Perk",
        description="Direct DB perk",
        category="combat",
        rarity="common",
        icon="icon.png",
        conditions=[{"type": "cumulative_stat", "stat": "pvp_wins", "operator": ">=", "value": 10}],
        bonuses={"flat": {"strength": 5}, "percent": {}, "contextual": {}, "passive": {}},
        sort_order=0,
        is_active=True,
    )
    defaults.update(overrides)
    perk = models.Perk(**defaults)
    db.add(perk)
    db.commit()
    db.refresh(perk)
    return perk


def _create_cumulative_stats(db, character_id=1, **overrides):
    """Create a CharacterCumulativeStats row and return it."""
    row = models.CharacterCumulativeStats(character_id=character_id, **overrides)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
    database.Base.metadata.create_all(bind=_test_engine)
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        database.Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture()
def admin_client(db_session):
    def override_get_db():
        yield db_session

    def override_admin():
        return _ADMIN_USER

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = override_admin
    app.dependency_overrides[get_current_user_via_http] = override_admin
    # Override all require_permission variants used by perk endpoints
    for perm in ["perks:read", "perks:create", "perks:update", "perks:delete", "perks:grant",
                 "characters:update", "characters:delete"]:
        app.dependency_overrides[require_permission(perm)] = override_admin
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def public_client(db_session):
    """Client without auth overrides — only overrides get_db for public endpoints."""
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ===========================================================================
# CRUD Tests — Admin Perk endpoints
# ===========================================================================

class TestCreatePerk:

    def test_create_perk_valid(self, admin_client, db_session):
        payload = _make_perk_payload()
        resp = admin_client.post("/attributes/admin/perks", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Perk"
        assert data["category"] == "combat"
        assert data["rarity"] == "common"
        assert data["is_active"] is True

    def test_create_perk_invalid_category(self, admin_client):
        payload = _make_perk_payload(category="invalid_category")
        resp = admin_client.post("/attributes/admin/perks", json=payload)
        assert resp.status_code == 400
        assert "категория" in resp.json()["detail"].lower() or "категори" in resp.json()["detail"].lower()

    def test_create_perk_invalid_flat_bonus_key(self, admin_client):
        payload = _make_perk_payload(bonuses={
            "flat": {"nonexistent_stat": 10},
            "percent": {},
            "contextual": {},
            "passive": {},
        })
        resp = admin_client.post("/attributes/admin/perks", json=payload)
        assert resp.status_code == 400
        assert "ключ" in resp.json()["detail"].lower() or "бонус" in resp.json()["detail"].lower()

    def test_create_perk_invalid_rarity(self, admin_client):
        payload = _make_perk_payload(rarity="mythic")
        resp = admin_client.post("/attributes/admin/perks", json=payload)
        assert resp.status_code == 400
        assert "редкость" in resp.json()["detail"].lower()


class TestUpdatePerk:

    def test_update_perk_partial(self, admin_client, db_session):
        # Create a perk first
        perk = _create_perk_in_db(db_session, name="Original Name")
        resp = admin_client.put(
            f"/attributes/admin/perks/{perk.id}",
            json={"name": "Updated Name"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Name"
        # Category should remain unchanged
        assert data["category"] == "combat"

    def test_update_perk_not_found(self, admin_client):
        resp = admin_client.put(
            "/attributes/admin/perks/99999",
            json={"name": "Ghost"},
        )
        assert resp.status_code == 404


class TestDeletePerk:

    def test_delete_perk_returns_affected(self, admin_client, db_session):
        perk = _create_perk_in_db(db_session)
        _create_attributes(db_session, character_id=10)
        # Grant perk to a character
        cp = models.CharacterPerk(character_id=10, perk_id=perk.id, is_custom=True)
        db_session.add(cp)
        db_session.commit()

        resp = admin_client.delete(f"/attributes/admin/perks/{perk.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["affected_characters"] == 1

    def test_delete_perk_reverses_flat_bonuses(self, admin_client, db_session):
        perk = _create_perk_in_db(
            db_session,
            bonuses={"flat": {"strength": 10}, "percent": {}, "contextual": {}, "passive": {}},
        )
        attr = _create_attributes(db_session, character_id=10, strength=20)
        # Grant the perk (applies +10 strength)
        cp = models.CharacterPerk(character_id=10, perk_id=perk.id, is_custom=True)
        db_session.add(cp)
        db_session.commit()
        # Apply bonus manually as grant_perk would
        crud._apply_modifiers_internal(db_session, 10, {"strength": 10})
        db_session.commit()
        db_session.refresh(attr)
        strength_after_grant = attr.strength  # Should be 30

        # Delete perk — should reverse the +10 bonus
        resp = admin_client.delete(f"/attributes/admin/perks/{perk.id}")
        assert resp.status_code == 200

        db_session.refresh(attr)
        assert attr.strength == strength_after_grant - 10

    def test_delete_perk_not_found(self, admin_client):
        resp = admin_client.delete("/attributes/admin/perks/99999")
        assert resp.status_code == 404


class TestGetPerksPaginated:
    """
    NOTE: GET /attributes/admin/perks is shadowed by GET /attributes/{character_id}
    (defined earlier in router), causing 422 because "admin" is not a valid int.
    This is a known routing-order bug — see docs/ISSUES.md.
    These tests exercise the underlying crud.get_perks_paginated directly.
    """

    def test_get_perks_with_category_filter(self, db_session):
        _create_perk_in_db(db_session, name="Combat Perk 1", category="combat", rarity="common")
        _create_perk_in_db(db_session, name="Trade Perk", category="trade", rarity="rare")
        _create_perk_in_db(db_session, name="Combat Perk 2", category="combat", rarity="legendary")

        items, total = crud.get_perks_paginated(db_session, category="combat")
        assert total == 2
        assert all(p.category == "combat" for p in items)

    def test_get_perks_with_rarity_filter(self, db_session):
        _create_perk_in_db(db_session, name="Combat Perk 1", category="combat", rarity="common")
        _create_perk_in_db(db_session, name="Trade Perk", category="trade", rarity="rare")

        items, total = crud.get_perks_paginated(db_session, rarity="rare")
        assert total == 1
        assert items[0].name == "Trade Perk"

    def test_get_perks_with_search_filter(self, db_session):
        _create_perk_in_db(db_session, name="Combat Perk 1", category="combat")
        _create_perk_in_db(db_session, name="Trade Perk", category="trade")

        items, total = crud.get_perks_paginated(db_session, search="Combat")
        assert total == 1
        assert items[0].name == "Combat Perk 1"

    def test_get_perks_pagination(self, db_session):
        for i in range(5):
            _create_perk_in_db(db_session, name=f"Perk {i}", sort_order=i)

        items, total = crud.get_perks_paginated(db_session, page=1, per_page=2)
        assert total == 5
        assert len(items) == 2

    @pytest.mark.xfail(reason="GET /attributes/admin/perks shadowed by /{character_id} route — routing bug")
    def test_admin_perks_endpoint_routing(self, admin_client, db_session):
        """Endpoint-level test — expected to fail until routing order is fixed."""
        _create_perk_in_db(db_session, name="Test Perk")
        resp = admin_client.get("/attributes/admin/perks")
        assert resp.status_code == 200


# ===========================================================================
# Grant / Revoke Tests
# ===========================================================================

class TestGrantPerk:

    def test_grant_perk_happy_path(self, admin_client, db_session):
        perk = _create_perk_in_db(
            db_session,
            bonuses={"flat": {"strength": 5}, "percent": {}, "contextual": {}, "passive": {}},
        )
        _create_attributes(db_session, character_id=10, strength=10)

        resp = admin_client.post(
            "/attributes/admin/perks/grant",
            json={"character_id": 10, "perk_id": perk.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "выдан" in data["detail"].lower() or "Перк выдан" in data["detail"]

        # Verify character_perk row exists
        cp = db_session.query(models.CharacterPerk).filter(
            models.CharacterPerk.character_id == 10,
            models.CharacterPerk.perk_id == perk.id,
        ).first()
        assert cp is not None
        assert cp.is_custom is True

        # Verify flat bonus was applied
        db_session.refresh(
            db_session.query(models.CharacterAttributes).filter(
                models.CharacterAttributes.character_id == 10
            ).first()
        )
        attr = db_session.query(models.CharacterAttributes).filter(
            models.CharacterAttributes.character_id == 10
        ).first()
        assert attr.strength == 15  # 10 + 5

    def test_grant_same_perk_twice_idempotent(self, admin_client, db_session):
        perk = _create_perk_in_db(db_session)
        _create_attributes(db_session, character_id=10)

        # First grant
        resp1 = admin_client.post(
            "/attributes/admin/perks/grant",
            json={"character_id": 10, "perk_id": perk.id},
        )
        assert resp1.status_code == 200

        # Second grant — idempotent, no error
        resp2 = admin_client.post(
            "/attributes/admin/perks/grant",
            json={"character_id": 10, "perk_id": perk.id},
        )
        assert resp2.status_code == 200
        assert "уже" in resp2.json()["detail"].lower()

    def test_grant_nonexistent_perk(self, admin_client, db_session):
        _create_attributes(db_session, character_id=10)
        resp = admin_client.post(
            "/attributes/admin/perks/grant",
            json={"character_id": 10, "perk_id": 99999},
        )
        assert resp.status_code == 404


class TestRevokePerk:

    def test_revoke_perk_reverses_bonuses(self, admin_client, db_session):
        perk = _create_perk_in_db(
            db_session,
            bonuses={"flat": {"strength": 5}, "percent": {}, "contextual": {}, "passive": {}},
        )
        attr = _create_attributes(db_session, character_id=10, strength=10)

        # Grant perk first
        admin_client.post(
            "/attributes/admin/perks/grant",
            json={"character_id": 10, "perk_id": perk.id},
        )
        db_session.refresh(attr)
        assert attr.strength == 15

        # Revoke
        resp = admin_client.delete(f"/attributes/admin/perks/grant/10/{perk.id}")
        assert resp.status_code == 200

        db_session.refresh(attr)
        assert attr.strength == 10  # Reverted

    def test_revoke_nonexistent_grant(self, admin_client, db_session):
        perk = _create_perk_in_db(db_session)
        resp = admin_client.delete(f"/attributes/admin/perks/grant/10/{perk.id}")
        assert resp.status_code == 404


# ===========================================================================
# Evaluator Tests — unit tests for perk_evaluator.py
# ===========================================================================

class TestCompare:

    def test_gte(self):
        assert compare(10, ">=", 10) is True
        assert compare(11, ">=", 10) is True
        assert compare(9, ">=", 10) is False

    def test_lte(self):
        assert compare(10, "<=", 10) is True
        assert compare(9, "<=", 10) is True
        assert compare(11, "<=", 10) is False

    def test_eq(self):
        assert compare(10, "==", 10) is True
        assert compare(9, "==", 10) is False

    def test_gt(self):
        assert compare(11, ">", 10) is True
        assert compare(10, ">", 10) is False

    def test_lt(self):
        assert compare(9, "<", 10) is True
        assert compare(10, "<", 10) is False

    def test_unknown_operator(self):
        assert compare(10, "!=", 10) is False

    def test_invalid_values(self):
        assert compare("abc", ">=", 10) is False
        assert compare(10, ">=", "abc") is False
        assert compare(None, ">=", 10) is False


class TestCheckCondition:

    def test_cumulative_stat_true(self, db_session):
        """check_condition returns True when cumulative stat meets the condition."""
        cumulative = _create_cumulative_stats(db_session, character_id=1, pvp_wins=15)
        condition = {"type": "cumulative_stat", "stat": "pvp_wins", "operator": ">=", "value": 10}
        assert check_condition(condition, cumulative, None, None) is True

    def test_cumulative_stat_false(self, db_session):
        """check_condition returns False when cumulative stat does not meet the condition."""
        cumulative = _create_cumulative_stats(db_session, character_id=1, pvp_wins=5)
        condition = {"type": "cumulative_stat", "stat": "pvp_wins", "operator": ">=", "value": 10}
        assert check_condition(condition, cumulative, None, None) is False

    def test_attribute_type(self, db_session):
        """check_condition with attribute type checks character attributes."""
        attr = _create_attributes(db_session, character_id=1, strength=50)
        condition = {"type": "attribute", "stat": "strength", "operator": ">=", "value": 40}
        assert check_condition(condition, None, attr, None) is True

        condition_fail = {"type": "attribute", "stat": "strength", "operator": ">=", "value": 60}
        assert check_condition(condition_fail, None, attr, None) is False

    def test_unknown_type_returns_false(self):
        """Unknown condition type returns False."""
        condition = {"type": "completely_unknown", "stat": "x", "operator": ">=", "value": 1}
        assert check_condition(condition, None, None, None) is False

    def test_admin_grant_returns_false(self):
        """admin_grant conditions always return False (manual grant only)."""
        condition = {"type": "admin_grant", "stat": None, "operator": ">=", "value": 0}
        assert check_condition(condition, None, None, None) is False

    def test_character_level(self):
        """check_condition with character_level type."""
        condition = {"type": "character_level", "stat": None, "operator": ">=", "value": 10}
        assert check_condition(condition, None, None, 15) is True
        assert check_condition(condition, None, None, 5) is False
        assert check_condition(condition, None, None, None) is False

    def test_quest_returns_false(self):
        """Quest condition type always returns False (not implemented)."""
        condition = {"type": "quest", "stat": "quest_123", "operator": ">=", "value": 1}
        assert check_condition(condition, None, None, None) is False

    def test_cumulative_stat_no_stats_object(self):
        """Returns False when cumulative_stats is None."""
        condition = {"type": "cumulative_stat", "stat": "pvp_wins", "operator": ">=", "value": 1}
        assert check_condition(condition, None, None, None) is False

    def test_attribute_no_attrs_object(self):
        """Returns False when attributes is None."""
        condition = {"type": "attribute", "stat": "strength", "operator": ">=", "value": 1}
        assert check_condition(condition, None, None, None) is False


class TestEvaluatePerks:

    @patch("perk_evaluator._fetch_character_level")
    def test_auto_unlocks_when_condition_met(self, mock_level, db_session):
        """evaluate_perks auto-unlocks a perk when its cumulative_stat condition is met."""
        mock_level.return_value = None

        perk = _create_perk_in_db(
            db_session,
            conditions=[{"type": "cumulative_stat", "stat": "pvp_wins", "operator": ">=", "value": 10}],
            bonuses={"flat": {"strength": 3}, "percent": {}, "contextual": {}, "passive": {}},
        )
        _create_attributes(db_session, character_id=1, strength=10)
        _create_cumulative_stats(db_session, character_id=1, pvp_wins=15)

        result = evaluate_perks(db_session, 1)

        assert len(result) == 1
        assert result[0]["id"] == perk.id
        assert result[0]["bonuses_applied"] is True

        # Verify character_perk row was created
        cp = db_session.query(models.CharacterPerk).filter(
            models.CharacterPerk.character_id == 1,
            models.CharacterPerk.perk_id == perk.id,
        ).first()
        assert cp is not None
        assert cp.is_custom is False

    @patch("perk_evaluator._fetch_character_level")
    def test_skips_perks_with_no_conditions(self, mock_level, db_session):
        """Perks with empty conditions list should NOT auto-unlock."""
        mock_level.return_value = None

        _create_perk_in_db(db_session, conditions=[], bonuses={"flat": {}, "percent": {}, "contextual": {}, "passive": {}})
        _create_attributes(db_session, character_id=1)

        result = evaluate_perks(db_session, 1)
        assert len(result) == 0

    @patch("perk_evaluator._fetch_character_level")
    def test_skips_already_unlocked_perks(self, mock_level, db_session):
        """evaluate_perks skips perks the character already has."""
        mock_level.return_value = None

        perk = _create_perk_in_db(
            db_session,
            conditions=[{"type": "cumulative_stat", "stat": "pvp_wins", "operator": ">=", "value": 1}],
        )
        _create_attributes(db_session, character_id=1)
        _create_cumulative_stats(db_session, character_id=1, pvp_wins=100)

        # Manually grant the perk
        cp = models.CharacterPerk(character_id=1, perk_id=perk.id, is_custom=False)
        db_session.add(cp)
        db_session.commit()

        result = evaluate_perks(db_session, 1)
        assert len(result) == 0

    @patch("perk_evaluator._fetch_character_level")
    def test_does_not_unlock_when_condition_not_met(self, mock_level, db_session):
        """evaluate_perks does not unlock when condition threshold is not reached."""
        mock_level.return_value = None

        _create_perk_in_db(
            db_session,
            conditions=[{"type": "cumulative_stat", "stat": "pvp_wins", "operator": ">=", "value": 100}],
        )
        _create_attributes(db_session, character_id=1)
        _create_cumulative_stats(db_session, character_id=1, pvp_wins=5)

        result = evaluate_perks(db_session, 1)
        assert len(result) == 0

    @patch("perk_evaluator._fetch_character_level")
    def test_skips_admin_grant_only_perks(self, mock_level, db_session):
        """Perks with only admin_grant conditions should not auto-unlock."""
        mock_level.return_value = None

        _create_perk_in_db(
            db_session,
            conditions=[{"type": "admin_grant", "stat": None, "operator": ">=", "value": 0}],
        )
        _create_attributes(db_session, character_id=1)

        result = evaluate_perks(db_session, 1)
        assert len(result) == 0

    @patch("perk_evaluator._fetch_character_level")
    def test_character_level_condition(self, mock_level, db_session):
        """evaluate_perks fetches character level and uses it for condition check."""
        mock_level.return_value = 20

        perk = _create_perk_in_db(
            db_session,
            conditions=[{"type": "character_level", "stat": None, "operator": ">=", "value": 10}],
            bonuses={"flat": {}, "percent": {}, "contextual": {}, "passive": {}},
        )
        _create_attributes(db_session, character_id=1)

        result = evaluate_perks(db_session, 1)
        assert len(result) == 1
        assert result[0]["id"] == perk.id
        mock_level.assert_called_once_with(1)


# ===========================================================================
# Player Perks Endpoint Tests
# ===========================================================================

class TestPlayerPerksEndpoint:

    def test_get_perks_returns_all_with_status(self, public_client, db_session):
        """GET /attributes/{id}/perks returns all active perks with unlock status."""
        perk1 = _create_perk_in_db(db_session, name="Perk A")
        perk2 = _create_perk_in_db(db_session, name="Perk B")
        _create_attributes(db_session, character_id=1)

        # Grant perk1 to character 1. Admin-granted (is_custom=True) so the
        # dynamic reconcile-on-view keeps it even though its condition is unmet.
        cp = models.CharacterPerk(character_id=1, perk_id=perk1.id, is_custom=True)
        db_session.add(cp)
        db_session.commit()

        resp = public_client.get("/attributes/1/perks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["character_id"] == 1
        perks = data["perks"]
        assert len(perks) == 2

        # Find each perk by id and check unlock status
        perk_map = {p["id"]: p for p in perks}
        assert perk_map[perk1.id]["is_unlocked"] is True
        assert perk_map[perk2.id]["is_unlocked"] is False

    def test_get_perks_includes_progress(self, public_client, db_session):
        """GET /attributes/{id}/perks includes progress data for cumulative_stat conditions."""
        perk = _create_perk_in_db(
            db_session,
            conditions=[{"type": "cumulative_stat", "stat": "pvp_wins", "operator": ">=", "value": 50}],
        )
        _create_attributes(db_session, character_id=1)
        _create_cumulative_stats(db_session, character_id=1, pvp_wins=25)

        resp = public_client.get("/attributes/1/perks")
        assert resp.status_code == 200
        data = resp.json()
        perks = data["perks"]
        assert len(perks) == 1

        perk_data = perks[0]
        assert "progress" in perk_data
        assert "pvp_wins" in perk_data["progress"]
        assert perk_data["progress"]["pvp_wins"]["current"] == 25
        assert perk_data["progress"]["pvp_wins"]["required"] == 50

    def test_get_perks_attribute_progress(self, public_client, db_session):
        """GET /attributes/{id}/perks includes progress for attribute type conditions."""
        perk = _create_perk_in_db(
            db_session,
            conditions=[{"type": "attribute", "stat": "strength", "operator": ">=", "value": 100}],
        )
        _create_attributes(db_session, character_id=1, strength=42)

        resp = public_client.get("/attributes/1/perks")
        assert resp.status_code == 200
        perks = resp.json()["perks"]
        assert len(perks) == 1
        assert perks[0]["progress"]["strength"]["current"] == 42
        assert perks[0]["progress"]["strength"]["required"] == 100

    def test_get_perks_empty_when_no_perks(self, public_client, db_session):
        """GET /attributes/{id}/perks returns empty list when no perks exist."""
        _create_attributes(db_session, character_id=1)
        resp = public_client.get("/attributes/1/perks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["perks"] == []


# ===========================================================================
# CRUD unit-level tests (direct function calls)
# ===========================================================================

class TestCrudFunctions:

    def test_build_perk_modifiers_dict_positive(self, db_session):
        perk = _create_perk_in_db(
            db_session,
            bonuses={"flat": {"strength": 5, "health": 2}, "percent": {}, "contextual": {}, "passive": {}},
        )
        result = crud.build_perk_modifiers_dict(perk, negative=False)
        assert result == {"strength": 5, "health": 2}

    def test_build_perk_modifiers_dict_negative(self, db_session):
        perk = _create_perk_in_db(
            db_session,
            bonuses={"flat": {"strength": 5, "damage": 3}, "percent": {}, "contextual": {}, "passive": {}},
        )
        result = crud.build_perk_modifiers_dict(perk, negative=True)
        assert result == {"strength": -5, "damage": -3}

    def test_build_perk_modifiers_dict_skips_zero(self, db_session):
        perk = _create_perk_in_db(
            db_session,
            bonuses={"flat": {"strength": 0, "damage": 3}, "percent": {}, "contextual": {}, "passive": {}},
        )
        result = crud.build_perk_modifiers_dict(perk, negative=False)
        assert result == {"damage": 3}

    def test_build_perk_modifiers_dict_empty_bonuses(self, db_session):
        perk = _create_perk_in_db(
            db_session,
            bonuses={"flat": {}, "percent": {}, "contextual": {}, "passive": {}},
        )
        result = crud.build_perk_modifiers_dict(perk, negative=False)
        assert result == {}

    def test_apply_modifiers_internal_simple(self, db_session):
        attr = _create_attributes(db_session, character_id=1, strength=10, damage=5)
        result = crud._apply_modifiers_internal(db_session, 1, {"strength": 3, "damage": 2})
        assert result is True
        db_session.refresh(attr)
        assert attr.strength == 13
        assert attr.damage == 7

    def test_apply_modifiers_internal_nonexistent_character(self, db_session):
        result = crud._apply_modifiers_internal(db_session, 99999, {"strength": 3})
        assert result is False

    def test_validate_perk_data_valid(self):
        """Valid data does not raise."""
        crud.validate_perk_data(
            category="combat",
            rarity="rare",
            conditions=[schemas.PerkCondition(type="cumulative_stat", stat="pvp_wins", operator=">=", value=10)],
            bonuses=schemas.PerkBonuses(flat={"strength": 5}),
        )

    def test_validate_perk_data_invalid_condition_type(self):
        with pytest.raises(ValueError, match="неизвестный тип"):
            crud.validate_perk_data(
                conditions=[schemas.PerkCondition(type="invalid_type", stat="x", operator=">=", value=1)],
            )

    def test_validate_perk_data_invalid_operator(self):
        with pytest.raises(ValueError, match="неизвестный оператор"):
            crud.validate_perk_data(
                conditions=[schemas.PerkCondition(type="cumulative_stat", stat="pvp_wins", operator="!=", value=1)],
            )

    def test_grant_perk_crud(self, db_session):
        perk = _create_perk_in_db(db_session)
        _create_attributes(db_session, character_id=1, strength=10)
        success, already_had, returned_perk = crud.grant_perk(db_session, 1, perk.id)
        assert success is True
        assert already_had is False
        assert returned_perk.id == perk.id

    def test_grant_perk_idempotent(self, db_session):
        perk = _create_perk_in_db(db_session)
        _create_attributes(db_session, character_id=1)
        crud.grant_perk(db_session, 1, perk.id)
        success, already_had, _ = crud.grant_perk(db_session, 1, perk.id)
        assert success is True
        assert already_had is True

    def test_revoke_perk_crud(self, db_session):
        perk = _create_perk_in_db(
            db_session,
            bonuses={"flat": {"strength": 5}, "percent": {}, "contextual": {}, "passive": {}},
        )
        _create_attributes(db_session, character_id=1, strength=10)
        crud.grant_perk(db_session, 1, perk.id)

        success, returned_perk = crud.revoke_perk(db_session, 1, perk.id)
        assert success is True
        assert returned_perk.id == perk.id

        # Verify strength was reversed
        attr = db_session.query(models.CharacterAttributes).filter(
            models.CharacterAttributes.character_id == 1
        ).first()
        assert attr.strength == 10

    def test_revoke_nonexistent(self, db_session):
        perk = _create_perk_in_db(db_session)
        success, returned_perk = crud.revoke_perk(db_session, 1, perk.id)
        assert success is None
        assert returned_perk is None

    def test_get_perks_paginated_no_filters(self, db_session):
        _create_perk_in_db(db_session, name="P1")
        _create_perk_in_db(db_session, name="P2")
        items, total = crud.get_perks_paginated(db_session)
        assert total == 2
        assert len(items) == 2

    def test_get_perks_paginated_by_category(self, db_session):
        _create_perk_in_db(db_session, name="P1", category="combat")
        _create_perk_in_db(db_session, name="P2", category="trade")
        items, total = crud.get_perks_paginated(db_session, category="trade")
        assert total == 1
        assert items[0].name == "P2"

    def test_get_perks_paginated_search(self, db_session):
        _create_perk_in_db(db_session, name="Warrior Spirit")
        _create_perk_in_db(db_session, name="Merchant Eye")
        items, total = crud.get_perks_paginated(db_session, search="Warrior")
        assert total == 1
        assert items[0].name == "Warrior Spirit"


# ===========================================================================
# Security Tests
# ===========================================================================

class TestSecurityPerks:

    def test_sql_injection_in_search(self, db_session):
        """SQL injection in search param should not crash — tested via CRUD directly
        because GET /attributes/admin/perks has a routing conflict (see docs/ISSUES.md)."""
        # Inject via CRUD function directly
        items, total = crud.get_perks_paginated(db_session, search="' OR 1=1 --")
        assert total == 0  # No crash, just no results

    def test_create_perk_xss_in_name(self, admin_client, db_session):
        payload = _make_perk_payload(name="<script>alert('xss')</script>")
        resp = admin_client.post("/attributes/admin/perks", json=payload)
        # Should accept the input (sanitization is frontend concern) or reject it, not 500
        assert resp.status_code in (201, 400)


class TestPerkStatDerivedPropagation:
    """FEAT-143: a perk that grants a primary attribute must also grant that
    attribute's derived effects (resists / dodge / crit / res_effects), exactly
    like a normal stat upgrade — and reverse them on revoke."""

    def _b(self):
        from constants import STAT_BONUS_PER_POINT
        return STAT_BONUS_PER_POINT

    def test_strength_propagates_to_physical_resists(self, db_session):
        from constants import PHYSICAL_RESISTANCE_FIELDS
        attr = _create_attributes(db_session, character_id=201, strength=10)
        before = {f: getattr(attr, f) for f in PHYSICAL_RESISTANCE_FIELDS}
        crud._apply_modifiers_internal(db_session, 201, {"strength": 5})
        db_session.refresh(attr)
        assert attr.strength == 15
        for f in PHYSICAL_RESISTANCE_FIELDS:
            assert getattr(attr, f) == pytest.approx(before[f] + 5 * self._b())

    def test_intelligence_propagates_to_magical_resists(self, db_session):
        from constants import MAGICAL_RESISTANCE_FIELDS
        attr = _create_attributes(db_session, character_id=202, intelligence=10)
        before = {f: getattr(attr, f) for f in MAGICAL_RESISTANCE_FIELDS}
        crud._apply_modifiers_internal(db_session, 202, {"intelligence": 4})
        db_session.refresh(attr)
        assert attr.intelligence == 14
        for f in MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, f) == pytest.approx(before[f] + 4 * self._b())

    def test_agility_propagates_to_dodge(self, db_session):
        attr = _create_attributes(db_session, character_id=203, agility=10)
        dodge_before = attr.dodge
        crud._apply_modifiers_internal(db_session, 203, {"agility": 6})
        db_session.refresh(attr)
        assert attr.agility == 16
        assert attr.dodge == pytest.approx(dodge_before + 6 * self._b())

    def test_endurance_propagates_to_res_effects(self, db_session):
        from constants import ENDURANCE_RES_EFFECTS_MULTIPLIER
        attr = _create_attributes(db_session, character_id=204, endurance=10)
        re_before = attr.res_effects
        crud._apply_modifiers_internal(db_session, 204, {"endurance": 5})
        db_session.refresh(attr)
        assert attr.endurance == 15
        assert attr.res_effects == pytest.approx(
            re_before + 5 * ENDURANCE_RES_EFFECTS_MULTIPLIER
        )

    def test_luck_propagates_to_dodge_crit_res_effects(self, db_session):
        attr = _create_attributes(db_session, character_id=205, luck=1)
        d0, c0, r0 = attr.dodge, attr.critical_hit_chance, attr.res_effects
        crud._apply_modifiers_internal(db_session, 205, {"luck": 3})
        db_session.refresh(attr)
        assert attr.luck == 4
        assert attr.dodge == pytest.approx(d0 + 3 * self._b())
        assert attr.critical_hit_chance == pytest.approx(c0 + 3 * self._b())
        assert attr.res_effects == pytest.approx(r0 + 3 * self._b())

    def test_negative_modifiers_reverse_derived(self, db_session):
        from constants import PHYSICAL_RESISTANCE_FIELDS
        attr = _create_attributes(db_session, character_id=206, strength=10)
        before = {f: getattr(attr, f) for f in PHYSICAL_RESISTANCE_FIELDS}
        crud._apply_modifiers_internal(db_session, 206, {"strength": 5})
        crud._apply_modifiers_internal(db_session, 206, {"strength": -5})
        db_session.refresh(attr)
        assert attr.strength == 10
        for f in PHYSICAL_RESISTANCE_FIELDS:
            assert getattr(attr, f) == pytest.approx(before[f])

    def test_direct_resist_bonus_still_added(self, db_session):
        # A perk can also bonus a resist directly; that must stack independently
        # of the strength-derived contribution.
        attr = _create_attributes(db_session, character_id=207, strength=10)
        rp0 = attr.res_physical
        crud._apply_modifiers_internal(
            db_session, 207, {"strength": 5, "res_physical": 2}
        )
        db_session.refresh(attr)
        # +2 direct  +  5*b from strength
        assert attr.res_physical == pytest.approx(rp0 + 2 + 5 * self._b())


class TestReconcilePerks:
    """FEAT-143 dynamic perks: active iff conditions currently met; bonuses
    applied on grant and reversed on revoke; admin perks untouched."""

    _ATTR_COND = [{"type": "attribute", "stat": "strength", "operator": ">=", "value": 15}]
    _BONUS = {"flat": {"damage": 3}, "percent": {}, "contextual": {}, "passive": {}}

    def test_grants_when_condition_met(self, db_session):
        from perk_evaluator import reconcile_perks
        _create_attributes(db_session, character_id=301, strength=20, damage=0)
        _create_cumulative_stats(db_session, character_id=301)
        perk = _create_perk_in_db(db_session, conditions=self._ATTR_COND, bonuses=self._BONUS)
        res = reconcile_perks(db_session, 301)
        assert perk.id in [g["id"] for g in res["granted"]]
        cp = db_session.query(models.CharacterPerk).filter_by(character_id=301, perk_id=perk.id).first()
        assert cp is not None
        attr = db_session.query(models.CharacterAttributes).filter_by(character_id=301).first()
        assert attr.damage == 3

    def test_revokes_when_condition_no_longer_met(self, db_session):
        from perk_evaluator import reconcile_perks
        attr = _create_attributes(db_session, character_id=302, strength=20, damage=0)
        _create_cumulative_stats(db_session, character_id=302)
        perk = _create_perk_in_db(db_session, conditions=self._ATTR_COND, bonuses=self._BONUS)
        reconcile_perks(db_session, 302)  # grant
        attr.strength = 10  # simulate unequipping the gear
        db_session.commit()
        res = reconcile_perks(db_session, 302)
        assert perk.id in [r["id"] for r in res["revoked"]]
        assert db_session.query(models.CharacterPerk).filter_by(character_id=302, perk_id=perk.id).first() is None
        db_session.refresh(attr)
        assert attr.damage == 0  # bonus reversed

    def test_cumulative_perk_stays_active(self, db_session):
        from perk_evaluator import reconcile_perks
        _create_attributes(db_session, character_id=303)
        _create_cumulative_stats(db_session, character_id=303, pvp_wins=10)
        perk = _create_perk_in_db(
            db_session,
            conditions=[{"type": "cumulative_stat", "stat": "pvp_wins", "operator": ">=", "value": 10}],
            bonuses=self._BONUS,
        )
        reconcile_perks(db_session, 303)
        res = reconcile_perks(db_session, 303)  # second pass — must not flip
        assert res["revoked"] == []
        assert db_session.query(models.CharacterPerk).filter_by(character_id=303, perk_id=perk.id).first() is not None

    def test_admin_perk_not_auto_revoked(self, db_session):
        from perk_evaluator import reconcile_perks
        _create_attributes(db_session, character_id=304, strength=5)
        _create_cumulative_stats(db_session, character_id=304)
        perk = _create_perk_in_db(
            db_session,
            conditions=[{"type": "attribute", "stat": "strength", "operator": ">=", "value": 100}],
            bonuses=self._BONUS,
        )
        db_session.add(models.CharacterPerk(character_id=304, perk_id=perk.id, is_custom=True))
        db_session.commit()
        res = reconcile_perks(db_session, 304)
        assert res["revoked"] == []
        assert db_session.query(models.CharacterPerk).filter_by(character_id=304, perk_id=perk.id).first() is not None

    def test_not_granted_when_condition_unmet(self, db_session):
        from perk_evaluator import reconcile_perks
        _create_attributes(db_session, character_id=305, strength=5)
        _create_cumulative_stats(db_session, character_id=305)
        _create_perk_in_db(
            db_session,
            conditions=[{"type": "attribute", "stat": "strength", "operator": ">=", "value": 50}],
            bonuses=self._BONUS,
        )
        res = reconcile_perks(db_session, 305)
        assert res["granted"] == []
