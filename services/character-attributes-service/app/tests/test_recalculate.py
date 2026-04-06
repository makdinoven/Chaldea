"""
Tests for FEAT-111: save-then-recalculate flow in character-attributes-service.

Verifies that:
- PUT /attributes/admin/{id} saves base stats correctly
- POST /attributes/{id}/recalculate computes derived stats from current DB values
- Sequential flow (save then recalculate) produces correct derived stats
- Recalculate on non-existent character returns 404
- compute_derived_stats formulas produce expected values
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch
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
import crud  # noqa: E402
from constants import (  # noqa: E402
    BASE_HEALTH, BASE_MANA, BASE_ENERGY, BASE_STAMINA,
    BASE_DODGE, BASE_CRIT, BASE_CRIT_DMG,
    HEALTH_MULTIPLIER, MANA_MULTIPLIER, ENERGY_MULTIPLIER, STAMINA_MULTIPLIER,
    STAT_BONUS_PER_POINT, ENDURANCE_RES_EFFECTS_MULTIPLIER,
)
from auth_http import get_admin_user, get_current_user_via_http, UserRead  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app, get_db  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADMIN_USER = UserRead(
    id=1, username="admin", role="admin",
    permissions=[
        "characters:create", "characters:read", "characters:update", "characters:delete",
    ],
)


def _create_attributes(db, character_id=1, **overrides):
    """Create a CharacterAttributes row with sensible defaults."""
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
    yield TestClient(app)
    app.dependency_overrides.clear()


# ===========================================================================
# 1. PUT /attributes/admin/{character_id} saves base stats correctly
# ===========================================================================

class TestAdminSaveBaseStats:

    def test_save_base_stats_persisted(self, admin_client, db_session):
        """PUT saves base stats and they are persisted in DB."""
        _create_attributes(db_session, character_id=1, strength=10, agility=10)

        resp = admin_client.put(
            "/attributes/admin/1",
            json={"strength": 50, "agility": 30},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["strength"] == 50
        assert data["agility"] == 30

        # Verify in DB directly
        db_session.expire_all()
        attr = db_session.query(models.CharacterAttributes).filter(
            models.CharacterAttributes.character_id == 1
        ).first()
        assert attr.strength == 50
        assert attr.agility == 30

    def test_save_multiple_base_stats(self, admin_client, db_session):
        """PUT can update all base stats at once."""
        _create_attributes(db_session, character_id=1)

        new_stats = {
            "strength": 20,
            "agility": 25,
            "intelligence": 30,
            "endurance": 15,
            "health": 20,
            "mana": 12,
            "energy": 8,
            "stamina": 18,
            "charisma": 5,
            "luck": 10,
        }
        resp = admin_client.put("/attributes/admin/1", json=new_stats)
        assert resp.status_code == 200
        data = resp.json()
        for field, value in new_stats.items():
            assert data[field] == value


# ===========================================================================
# 2. POST /{character_id}/recalculate computes derived stats from DB values
# ===========================================================================

class TestRecalculateEndpoint:

    def test_recalculate_returns_success(self, admin_client, db_session):
        """POST recalculate returns 200 with success message."""
        _create_attributes(db_session, character_id=1)
        resp = admin_client.post("/attributes/1/recalculate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["detail"] == "Attributes recalculated"
        assert data["character_id"] == 1

    def test_recalculate_updates_derived_stats_in_db(self, admin_client, db_session):
        """After recalculate, derived stats in DB match compute_derived_stats formula."""
        attr = _create_attributes(
            db_session, character_id=1,
            strength=20, agility=15, intelligence=25, endurance=30,
            health=10, mana=7, energy=5, stamina=10, luck=5,
            # Set derived stats to wrong values to prove recalculate fixes them
            max_health=0, dodge=0.0, res_physical=0.0, res_magic=0.0,
        )

        resp = admin_client.post("/attributes/1/recalculate")
        assert resp.status_code == 200

        # Verify derived stats in DB
        db_session.expire_all()
        attr = db_session.query(models.CharacterAttributes).filter(
            models.CharacterAttributes.character_id == 1
        ).first()

        b = STAT_BONUS_PER_POINT
        assert attr.max_health == int(BASE_HEALTH + 10 * HEALTH_MULTIPLIER)
        assert attr.max_mana == int(BASE_MANA + 7 * MANA_MULTIPLIER)
        assert attr.max_energy == int(BASE_ENERGY + 5 * ENERGY_MULTIPLIER)
        assert attr.max_stamina == int(BASE_STAMINA + 10 * STAMINA_MULTIPLIER)
        assert attr.dodge == round(BASE_DODGE + 15 * b + 5 * b, 2)
        assert attr.critical_hit_chance == round(BASE_CRIT + 5 * b, 2)
        assert attr.critical_damage == BASE_CRIT_DMG
        assert attr.res_physical == round(20 * b, 2)
        assert attr.res_magic == round(25 * b, 2)
        assert attr.res_effects == round(30 * ENDURANCE_RES_EFFECTS_MULTIPLIER + 5 * b, 2)

    def test_recalculate_not_found(self, admin_client, db_session):
        """POST recalculate on non-existent character returns 404."""
        resp = admin_client.post("/attributes/99999/recalculate")
        assert resp.status_code == 404


# ===========================================================================
# 3. Sequential flow: save then recalculate
# ===========================================================================

class TestSaveThenRecalculate:

    def test_save_then_recalculate_flow(self, admin_client, db_session):
        """
        Full flow: create attrs with default base stats, PUT new base stats,
        then POST recalculate, then GET to verify derived stats match the
        new base stats (not the old ones).
        """
        _create_attributes(
            db_session, character_id=1,
            strength=10, agility=10, intelligence=10, endurance=10,
            health=10, mana=7, energy=5, stamina=10, luck=1,
        )

        # Step 1: Save new base stats via PUT
        new_base = {
            "strength": 40,
            "agility": 35,
            "intelligence": 50,
            "endurance": 20,
            "health": 25,
            "mana": 15,
            "energy": 12,
            "stamina": 20,
            "luck": 8,
        }
        save_resp = admin_client.put("/attributes/admin/1", json=new_base)
        assert save_resp.status_code == 200

        # Step 2: Recalculate derived stats
        recalc_resp = admin_client.post("/attributes/1/recalculate")
        assert recalc_resp.status_code == 200

        # Step 3: GET to verify final state
        get_resp = admin_client.get("/attributes/1")
        assert get_resp.status_code == 200
        data = get_resp.json()

        # Verify base stats were saved
        assert data["strength"] == 40
        assert data["agility"] == 35
        assert data["intelligence"] == 50
        assert data["endurance"] == 20
        assert data["health"] == 25
        assert data["luck"] == 8

        # Verify derived stats are computed from NEW base stats
        b = STAT_BONUS_PER_POINT
        assert data["max_health"] == int(BASE_HEALTH + 25 * HEALTH_MULTIPLIER)
        assert data["max_mana"] == int(BASE_MANA + 15 * MANA_MULTIPLIER)
        assert data["max_energy"] == int(BASE_ENERGY + 12 * ENERGY_MULTIPLIER)
        assert data["max_stamina"] == int(BASE_STAMINA + 20 * STAMINA_MULTIPLIER)
        assert data["dodge"] == round(BASE_DODGE + 35 * b + 8 * b, 2)
        assert data["critical_hit_chance"] == round(BASE_CRIT + 8 * b, 2)
        assert data["critical_damage"] == BASE_CRIT_DMG

        # Physical resistances from strength=40
        assert data["res_physical"] == round(40 * b, 2)
        assert data["res_catting"] == round(40 * b, 2)
        assert data["res_crushing"] == round(40 * b, 2)
        assert data["res_piercing"] == round(40 * b, 2)

        # Magical resistances from intelligence=50
        assert data["res_magic"] == round(50 * b, 2)
        assert data["res_fire"] == round(50 * b, 2)
        assert data["res_ice"] == round(50 * b, 2)

        # res_effects from endurance=20, luck=8
        assert data["res_effects"] == round(
            20 * ENDURANCE_RES_EFFECTS_MULTIPLIER + 8 * b, 2
        )

    def test_recalculate_without_save_uses_old_values(self, admin_client, db_session):
        """
        Demonstrates the original bug scenario: if recalculate is called
        WITHOUT saving first, derived stats are based on OLD db values.
        This test proves recalculate reads from DB, not from any request body.
        """
        _create_attributes(
            db_session, character_id=1,
            strength=10, agility=10, intelligence=10, endurance=10,
            health=10, mana=7, energy=5, stamina=10, luck=1,
        )

        # Call recalculate WITHOUT any prior PUT (simulating the bug)
        resp = admin_client.post("/attributes/1/recalculate")
        assert resp.status_code == 200

        # Derived stats should reflect the ORIGINAL base stats
        db_session.expire_all()
        attr = db_session.query(models.CharacterAttributes).filter(
            models.CharacterAttributes.character_id == 1
        ).first()

        b = STAT_BONUS_PER_POINT
        # These are based on original stats (strength=10, not any hypothetical new value)
        assert attr.max_health == int(BASE_HEALTH + 10 * HEALTH_MULTIPLIER)
        assert attr.dodge == round(BASE_DODGE + 10 * b + 1 * b, 2)
        assert attr.res_physical == round(10 * b, 2)
        assert attr.res_magic == round(10 * b, 2)


# ===========================================================================
# 4. Recalculate on non-existent character returns 404
# ===========================================================================

class TestRecalculate404:

    def test_recalculate_nonexistent_character(self, admin_client, db_session):
        """POST recalculate for a character that doesn't exist returns 404."""
        resp = admin_client.post("/attributes/999/recalculate")
        assert resp.status_code == 404
        assert "не найдены" in resp.json()["detail"].lower() or "not found" in resp.json()["detail"].lower()

    def test_recalculate_zero_id(self, admin_client, db_session):
        """Edge case: character_id=0 that doesn't exist returns 404."""
        resp = admin_client.post("/attributes/0/recalculate")
        assert resp.status_code == 404


# ===========================================================================
# 5. Verify compute_derived_stats formulas (unit tests)
# ===========================================================================

class TestComputeDerivedStats:
    """Unit tests for crud.compute_derived_stats — verify formulas directly."""

    def test_resource_maximums(self, db_session):
        """max_health/mana/energy/stamina follow BASE + stat * MULTIPLIER."""
        attr = _create_attributes(
            db_session, character_id=1,
            health=20, mana=15, energy=10, stamina=25,
            current_health=9999, current_mana=9999,
            current_energy=9999, current_stamina=9999,
        )

        crud.compute_derived_stats(attr)

        assert attr.max_health == int(BASE_HEALTH + 20 * HEALTH_MULTIPLIER)  # 100 + 200 = 300
        assert attr.max_mana == int(BASE_MANA + 15 * MANA_MULTIPLIER)       # 75 + 150 = 225
        assert attr.max_energy == int(BASE_ENERGY + 10 * ENERGY_MULTIPLIER)  # 50 + 50 = 100
        assert attr.max_stamina == int(BASE_STAMINA + 25 * STAMINA_MULTIPLIER)  # 100 + 125 = 225

    def test_current_resources_clamped_to_max(self, db_session):
        """Current resources are clamped to not exceed new max values."""
        attr = _create_attributes(
            db_session, character_id=1,
            health=5, mana=3, energy=2, stamina=4,
            current_health=9999, current_mana=9999,
            current_energy=9999, current_stamina=9999,
        )

        crud.compute_derived_stats(attr)

        assert attr.current_health == attr.max_health
        assert attr.current_mana == attr.max_mana
        assert attr.current_energy == attr.max_energy
        assert attr.current_stamina == attr.max_stamina

    def test_current_resources_not_increased(self, db_session):
        """If current < new max, current stays unchanged."""
        attr = _create_attributes(
            db_session, character_id=1,
            health=50,  # max_health = 100 + 500 = 600
            current_health=10,
        )

        crud.compute_derived_stats(attr)

        assert attr.max_health == int(BASE_HEALTH + 50 * HEALTH_MULTIPLIER)  # 600
        assert attr.current_health == 10  # Unchanged, well below max

    def test_dodge_formula(self, db_session):
        """dodge = BASE_DODGE + agility * b + luck * b."""
        attr = _create_attributes(
            db_session, character_id=1,
            agility=30, luck=20,
        )
        crud.compute_derived_stats(attr)

        b = STAT_BONUS_PER_POINT
        expected = round(BASE_DODGE + 30 * b + 20 * b, 2)
        assert attr.dodge == expected

    def test_critical_hit_chance_formula(self, db_session):
        """critical_hit_chance = BASE_CRIT + luck * b."""
        attr = _create_attributes(
            db_session, character_id=1,
            luck=15,
        )
        crud.compute_derived_stats(attr)

        b = STAT_BONUS_PER_POINT
        expected = round(BASE_CRIT + 15 * b, 2)
        assert attr.critical_hit_chance == expected

    def test_critical_damage_constant(self, db_session):
        """critical_damage is always BASE_CRIT_DMG (only modified by items)."""
        attr = _create_attributes(db_session, character_id=1, luck=100)
        crud.compute_derived_stats(attr)
        assert attr.critical_damage == BASE_CRIT_DMG

    def test_physical_resistances_from_strength(self, db_session):
        """Physical resistances = strength * STAT_BONUS_PER_POINT."""
        attr = _create_attributes(db_session, character_id=1, strength=50)
        crud.compute_derived_stats(attr)

        b = STAT_BONUS_PER_POINT
        expected = round(50 * b, 2)
        assert attr.res_physical == expected
        assert attr.res_catting == expected
        assert attr.res_crushing == expected
        assert attr.res_piercing == expected

    def test_magical_resistances_from_intelligence(self, db_session):
        """Magical resistances = intelligence * STAT_BONUS_PER_POINT."""
        attr = _create_attributes(db_session, character_id=1, intelligence=40)
        crud.compute_derived_stats(attr)

        b = STAT_BONUS_PER_POINT
        expected = round(40 * b, 2)
        assert attr.res_magic == expected
        assert attr.res_fire == expected
        assert attr.res_ice == expected
        assert attr.res_watering == expected
        assert attr.res_electricity == expected
        assert attr.res_wind == expected
        assert attr.res_sainting == expected
        assert attr.res_damning == expected

    def test_res_effects_formula(self, db_session):
        """res_effects = endurance * 0.2 + luck * 0.1."""
        attr = _create_attributes(
            db_session, character_id=1,
            endurance=30, luck=20,
        )
        crud.compute_derived_stats(attr)

        expected = round(
            30 * ENDURANCE_RES_EFFECTS_MULTIPLIER + 20 * STAT_BONUS_PER_POINT, 2
        )
        assert attr.res_effects == expected

    def test_zero_stats_produce_base_values(self, db_session):
        """With all base stats at 0, derived stats equal their BASE constants."""
        attr = _create_attributes(
            db_session, character_id=1,
            strength=0, agility=0, intelligence=0, endurance=0,
            health=0, mana=0, energy=0, stamina=0, charisma=0, luck=0,
            current_health=0, current_mana=0, current_energy=0, current_stamina=0,
        )
        crud.compute_derived_stats(attr)

        assert attr.max_health == int(BASE_HEALTH)
        assert attr.max_mana == int(BASE_MANA)
        assert attr.max_energy == int(BASE_ENERGY)
        assert attr.max_stamina == int(BASE_STAMINA)
        assert attr.dodge == BASE_DODGE
        assert attr.critical_hit_chance == BASE_CRIT
        assert attr.critical_damage == BASE_CRIT_DMG
        assert attr.res_physical == 0.0
        assert attr.res_magic == 0.0
        assert attr.res_effects == 0.0
