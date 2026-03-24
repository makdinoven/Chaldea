"""
Tests for FEAT-075 Task 4.7: character-attributes-service formula changes.

Covers:
  1. compute_derived_stats() — pure unit tests for all derived stat formulas
  2. create_character_attributes() — new characters get correct derived stats from presets
  3. upgrade_attributes() — incremental stat changes (strength, intelligence, endurance, luck)
  4. recalculate_all endpoint — batch recalculation for all characters
  5. Edge cases — all stats 0 (base defaults), very high stats (no overflow)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# SQLite in-memory test engine — must be set up BEFORE importing app modules
# ---------------------------------------------------------------------------
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
from constants import (  # noqa: E402
    BASE_HEALTH, BASE_MANA, BASE_ENERGY, BASE_STAMINA,
    BASE_DODGE, BASE_CRIT, BASE_CRIT_DMG,
    HEALTH_MULTIPLIER, MANA_MULTIPLIER, ENERGY_MULTIPLIER, STAMINA_MULTIPLIER,
    STAT_BONUS_PER_POINT, ENDURANCE_RES_EFFECTS_MULTIPLIER,
    PHYSICAL_RESISTANCE_FIELDS, MAGICAL_RESISTANCE_FIELDS,
    ALL_RESISTANCE_FIELDS,
)
from auth_http import get_current_user_via_http, UserRead  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app, get_db  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_ADMIN_USER = UserRead(
    id=1, username="admin", role="admin",
    permissions=[
        "characters:create", "characters:read",
        "characters:update", "characters:delete",
        "characters:approve",
    ],
)

_PLAYER_USER = UserRead(
    id=10, username="player", role="user", permissions=[],
)


def _make_attrs(db, character_id=1, **overrides):
    """Insert a fresh CharacterAttributes row with all-zero base stats by default."""
    defaults = dict(
        character_id=character_id,
        strength=0, agility=0, intelligence=0, endurance=0,
        health=0, mana=0, energy=0, stamina=0,
        charisma=0, luck=0,
        current_health=BASE_HEALTH, max_health=BASE_HEALTH,
        current_mana=BASE_MANA, max_mana=BASE_MANA,
        current_energy=BASE_ENERGY, max_energy=BASE_ENERGY,
        current_stamina=BASE_STAMINA, max_stamina=BASE_STAMINA,
        damage=0, dodge=BASE_DODGE,
        critical_hit_chance=BASE_CRIT, critical_damage=BASE_CRIT_DMG,
        res_effects=0.0, res_physical=0.0, res_catting=0.0,
        res_crushing=0.0, res_piercing=0.0, res_magic=0.0,
        res_fire=0.0, res_ice=0.0, res_watering=0.0,
        res_electricity=0.0, res_sainting=0.0, res_wind=0.0,
        res_damning=0.0,
    )
    defaults.update(overrides)
    attr = models.CharacterAttributes(**defaults)
    db.add(attr)
    db.commit()
    db.refresh(attr)
    return attr


def _upgrade_payload(**kwargs):
    """Return a dict with all stats = 0 except those specified."""
    base = dict(
        strength=0, agility=0, intelligence=0, endurance=0,
        health=0, energy=0, mana=0, stamina=0,
        charisma=0, luck=0,
    )
    base.update(kwargs)
    return base


def _make_mock_httpx_client(stat_points=100):
    """Create a mock httpx.AsyncClient context manager for upgrade endpoint."""
    mock_profile_resp = MagicMock()
    mock_profile_resp.status_code = 200
    mock_profile_resp.json.return_value = {"stat_points": stat_points}

    mock_deduct_resp = MagicMock()
    mock_deduct_resp.status_code = 200
    mock_deduct_resp.json.return_value = {"remaining_points": 0}

    mock_instance = AsyncMock()

    async def mock_get(url, **kw):
        return mock_profile_resp

    async def mock_put(url, **kw):
        return mock_deduct_resp

    mock_instance.get = mock_get
    mock_instance.put = mock_put

    return mock_instance


def _override_get_db_factory():
    """Return a get_db override that creates a fresh session per call."""
    def override():
        session = _TestSessionLocal()
        try:
            yield session
        finally:
            session.close()
    return override


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
    """TestClient with admin auth and DB overrides."""
    def override_get_db():
        yield db_session

    def override_auth():
        return _ADMIN_USER

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_via_http] = override_auth
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def upgrade_client(db_session):
    """TestClient for upgrade endpoint with mocked httpx and auth."""
    app.dependency_overrides[get_db] = _override_get_db_factory()
    app.dependency_overrides[get_current_user_via_http] = lambda: _PLAYER_USER

    mock_instance = _make_mock_httpx_client(stat_points=100)

    p1 = patch("main.verify_character_ownership")
    p2 = patch("main.httpx.AsyncClient")
    p1.start()
    mock_cls = p2.start()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    yield TestClient(app)

    p1.stop()
    p2.stop()
    app.dependency_overrides.clear()


# ===========================================================================
# 1. compute_derived_stats() — pure unit tests
# ===========================================================================
class TestComputeDerivedStats:
    """Direct unit tests for crud.compute_derived_stats() function."""

    def test_physical_resistances_equal_strength_times_bonus(self, db_session):
        """All 4 physical resistance fields = strength * 0.1"""
        attr = _make_attrs(db_session, character_id=1, strength=30)
        crud.compute_derived_stats(attr)

        expected = 30 * STAT_BONUS_PER_POINT  # 3.0
        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(expected, abs=1e-6), \
                f"{field} should be {expected}"

    def test_magical_resistances_equal_intelligence_times_bonus(self, db_session):
        """All 8 magical resistance fields = intelligence * 0.1"""
        attr = _make_attrs(db_session, character_id=2, intelligence=40)
        crud.compute_derived_stats(attr)

        expected = 40 * STAT_BONUS_PER_POINT  # 4.0
        for field in MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(expected, abs=1e-6), \
                f"{field} should be {expected}"

    def test_res_effects_formula(self, db_session):
        """res_effects = endurance * 0.2 + luck * 0.1"""
        attr = _make_attrs(db_session, character_id=3, endurance=15, luck=20)
        crud.compute_derived_stats(attr)

        expected = 15 * ENDURANCE_RES_EFFECTS_MULTIPLIER + 20 * STAT_BONUS_PER_POINT
        assert attr.res_effects == pytest.approx(expected, abs=1e-6)

    def test_dodge_formula(self, db_session):
        """dodge = 5.0 + agility * 0.1 + luck * 0.1"""
        attr = _make_attrs(db_session, character_id=4, agility=25, luck=10)
        crud.compute_derived_stats(attr)

        expected = BASE_DODGE + 25 * STAT_BONUS_PER_POINT + 10 * STAT_BONUS_PER_POINT
        assert attr.dodge == pytest.approx(expected, abs=1e-6)

    def test_critical_hit_chance_formula(self, db_session):
        """critical_hit_chance = 20.0 + luck * 0.1"""
        attr = _make_attrs(db_session, character_id=5, luck=50)
        crud.compute_derived_stats(attr)

        expected = BASE_CRIT + 50 * STAT_BONUS_PER_POINT
        assert attr.critical_hit_chance == pytest.approx(expected, abs=1e-6)

    def test_critical_damage_is_base_constant(self, db_session):
        """critical_damage = BASE_CRIT_DMG (125), only modified by items."""
        attr = _make_attrs(db_session, character_id=6, luck=100, strength=100)
        crud.compute_derived_stats(attr)

        assert attr.critical_damage == BASE_CRIT_DMG

    def test_max_health_formula(self, db_session):
        """max_health = 100 + health * 10"""
        attr = _make_attrs(db_session, character_id=7, health=12)
        crud.compute_derived_stats(attr)

        assert attr.max_health == int(BASE_HEALTH + 12 * HEALTH_MULTIPLIER)

    def test_max_mana_formula(self, db_session):
        """max_mana = 75 + mana * 10"""
        attr = _make_attrs(db_session, character_id=8, mana=8)
        crud.compute_derived_stats(attr)

        assert attr.max_mana == int(BASE_MANA + 8 * MANA_MULTIPLIER)

    def test_max_energy_formula(self, db_session):
        """max_energy = 50 + energy * 5"""
        attr = _make_attrs(db_session, character_id=9, energy=6)
        crud.compute_derived_stats(attr)

        assert attr.max_energy == int(BASE_ENERGY + 6 * ENERGY_MULTIPLIER)

    def test_max_stamina_formula(self, db_session):
        """max_stamina = 100 + stamina * 5"""
        attr = _make_attrs(db_session, character_id=10, stamina=10)
        crud.compute_derived_stats(attr)

        assert attr.max_stamina == int(BASE_STAMINA + 10 * STAMINA_MULTIPLIER)

    def test_current_clamped_to_max(self, db_session):
        """Current resource values are clamped to not exceed new max."""
        attr = _make_attrs(
            db_session, character_id=11,
            health=0, mana=0, energy=0, stamina=0,
            current_health=999, current_mana=999,
            current_energy=999, current_stamina=999,
            max_health=999, max_mana=999,
            max_energy=999, max_stamina=999,
        )
        crud.compute_derived_stats(attr)

        # With 0 stat points, max = base values, so current is clamped
        assert attr.current_health == BASE_HEALTH
        assert attr.current_mana == BASE_MANA
        assert attr.current_energy == BASE_ENERGY
        assert attr.current_stamina == BASE_STAMINA

    def test_strength_does_not_affect_magical_resistances(self, db_session):
        """Strength only affects physical resistances, not magical ones."""
        attr = _make_attrs(db_session, character_id=12, strength=50)
        crud.compute_derived_stats(attr)

        for field in MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(0.0, abs=1e-6), \
                f"{field} should be 0 when only strength is set"

    def test_intelligence_does_not_affect_physical_resistances(self, db_session):
        """Intelligence only affects magical resistances, not physical ones."""
        attr = _make_attrs(db_session, character_id=13, intelligence=50)
        crud.compute_derived_stats(attr)

        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(0.0, abs=1e-6), \
                f"{field} should be 0 when only intelligence is set"

    def test_endurance_does_not_affect_damage_resistances(self, db_session):
        """Endurance only affects res_effects, NOT physical/magical resistances."""
        attr = _make_attrs(db_session, character_id=14, endurance=50)
        crud.compute_derived_stats(attr)

        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(0.0, abs=1e-6), \
                f"{field} should be 0 when only endurance is set"
        for field in MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(0.0, abs=1e-6), \
                f"{field} should be 0 when only endurance is set"

    def test_all_formulas_combined(self, db_session):
        """Full scenario: set all base stats and verify every derived stat."""
        attr = _make_attrs(
            db_session, character_id=15,
            strength=10, agility=20, intelligence=15, endurance=5,
            health=8, mana=6, energy=4, stamina=3,
            charisma=7, luck=12,
            # Set current resources high so clamp logic is exercised
            current_health=9999, current_mana=9999,
            current_energy=9999, current_stamina=9999,
        )
        crud.compute_derived_stats(attr)

        b = STAT_BONUS_PER_POINT

        # Resources
        assert attr.max_health == int(BASE_HEALTH + 8 * HEALTH_MULTIPLIER)
        assert attr.max_mana == int(BASE_MANA + 6 * MANA_MULTIPLIER)
        assert attr.max_energy == int(BASE_ENERGY + 4 * ENERGY_MULTIPLIER)
        assert attr.max_stamina == int(BASE_STAMINA + 3 * STAMINA_MULTIPLIER)

        # Current clamped to max
        assert attr.current_health == attr.max_health
        assert attr.current_mana == attr.max_mana
        assert attr.current_energy == attr.max_energy
        assert attr.current_stamina == attr.max_stamina

        # Combat
        assert attr.dodge == pytest.approx(BASE_DODGE + 20 * b + 12 * b, abs=1e-6)
        assert attr.critical_hit_chance == pytest.approx(BASE_CRIT + 12 * b, abs=1e-6)
        assert attr.critical_damage == BASE_CRIT_DMG

        # Physical resistances (strength only)
        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(10 * b, abs=1e-6)

        # Magical resistances (intelligence only)
        for field in MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(15 * b, abs=1e-6)

        # res_effects = endurance * 0.2 + luck * 0.1
        assert attr.res_effects == pytest.approx(
            5 * ENDURANCE_RES_EFFECTS_MULTIPLIER + 12 * b, abs=1e-6
        )


# ===========================================================================
# 2. create_character_attributes() — derived stats from preset values
# ===========================================================================
class TestCreateCharacterAttributes:
    """Test that new characters get correct derived stats from preset values."""

    def test_create_with_preset_stats(self, db_session):
        """Preset stat values (like race presets) should produce correct derived stats."""
        create_data = schemas.CharacterAttributesCreate(
            character_id=100,
            strength=10, agility=10, intelligence=10, endurance=100,
            health=10, mana=7, energy=5, stamina=10,
            charisma=1, luck=1,
        )
        attr = crud.create_character_attributes(db_session, create_data)

        b = STAT_BONUS_PER_POINT

        # Resources
        assert attr.max_health == int(BASE_HEALTH + 10 * HEALTH_MULTIPLIER)  # 200
        assert attr.max_mana == int(BASE_MANA + 7 * MANA_MULTIPLIER)        # 145
        assert attr.max_energy == int(BASE_ENERGY + 5 * ENERGY_MULTIPLIER)   # 75
        assert attr.max_stamina == int(BASE_STAMINA + 10 * STAMINA_MULTIPLIER)  # 150

        # Current should equal max for new characters
        assert attr.current_health == attr.max_health
        assert attr.current_mana == attr.max_mana
        assert attr.current_energy == attr.max_energy
        assert attr.current_stamina == attr.max_stamina

        # Physical resistances from strength
        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(10 * b, abs=1e-6)

        # Magical resistances from intelligence
        for field in MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(10 * b, abs=1e-6)

        # res_effects = endurance * 0.2 + luck * 0.1
        assert attr.res_effects == pytest.approx(
            100 * ENDURANCE_RES_EFFECTS_MULTIPLIER + 1 * b, abs=1e-6
        )

        # dodge = 5.0 + agility * 0.1 + luck * 0.1
        assert attr.dodge == pytest.approx(
            BASE_DODGE + 10 * b + 1 * b, abs=1e-6
        )

        # critical_hit_chance = 20.0 + luck * 0.1
        assert attr.critical_hit_chance == pytest.approx(
            BASE_CRIT + 1 * b, abs=1e-6
        )

    def test_create_with_zero_stats(self, db_session):
        """Zero base stats should produce base defaults for all derived stats."""
        create_data = schemas.CharacterAttributesCreate(
            character_id=101,
            strength=0, agility=0, intelligence=0, endurance=0,
            health=0, mana=0, energy=0, stamina=0,
            charisma=0, luck=0,
        )
        attr = crud.create_character_attributes(db_session, create_data)

        assert attr.max_health == BASE_HEALTH
        assert attr.max_mana == BASE_MANA
        assert attr.max_energy == BASE_ENERGY
        assert attr.max_stamina == BASE_STAMINA
        assert attr.dodge == pytest.approx(BASE_DODGE, abs=1e-6)
        assert attr.critical_hit_chance == pytest.approx(BASE_CRIT, abs=1e-6)
        assert attr.critical_damage == BASE_CRIT_DMG

        for field in PHYSICAL_RESISTANCE_FIELDS + MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(0.0, abs=1e-6)
        assert attr.res_effects == pytest.approx(0.0, abs=1e-6)

    def test_create_stores_base_stats(self, db_session):
        """Base (upgradeable) stats should be stored correctly."""
        create_data = schemas.CharacterAttributesCreate(
            character_id=102,
            strength=5, agility=10, intelligence=15, endurance=20,
            health=3, mana=4, energy=2, stamina=6,
            charisma=8, luck=7,
        )
        attr = crud.create_character_attributes(db_session, create_data)

        assert attr.strength == 5
        assert attr.agility == 10
        assert attr.intelligence == 15
        assert attr.endurance == 20
        assert attr.health == 3
        assert attr.mana == 4
        assert attr.energy == 2
        assert attr.stamina == 6
        assert attr.charisma == 8
        assert attr.luck == 7


# ===========================================================================
# 3. upgrade_attributes() — incremental stat changes
# ===========================================================================
class TestUpgradeAttributesFormulas:
    """Upgrade endpoint: verify incremental formula changes."""

    def test_strength_upgrade_affects_all_4_physical_fields(self, upgrade_client, db_session):
        """Strength +N → all 4 physical resistance fields increase by N * 0.1."""
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(strength=20)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        expected = 20 * STAT_BONUS_PER_POINT
        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert attrs[field] == pytest.approx(expected, abs=1e-6), \
                f"{field} should be {expected}"

    def test_intelligence_upgrade_affects_all_8_magical_fields(self, upgrade_client, db_session):
        """Intelligence +N → all 8 magical resistance fields increase by N * 0.1."""
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(intelligence=30)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        expected = 30 * STAT_BONUS_PER_POINT
        for field in MAGICAL_RESISTANCE_FIELDS:
            assert attrs[field] == pytest.approx(expected, abs=1e-6), \
                f"{field} should be {expected}"

    def test_endurance_upgrade_only_affects_res_effects(self, upgrade_client, db_session):
        """Endurance +N → ONLY res_effects increases by N * 0.2, NO resistance bonuses."""
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(endurance=10)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]

        # res_effects should increase
        assert attrs["res_effects"] == pytest.approx(
            10 * ENDURANCE_RES_EFFECTS_MULTIPLIER, abs=1e-6
        )

        # Physical and magical resistances should be unchanged (0.0)
        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert attrs[field] == pytest.approx(0.0, abs=1e-6), \
                f"Endurance should not affect {field}"
        for field in MAGICAL_RESISTANCE_FIELDS:
            assert attrs[field] == pytest.approx(0.0, abs=1e-6), \
                f"Endurance should not affect {field}"

    def test_luck_upgrade_affects_dodge_crit_res_effects(self, upgrade_client, db_session):
        """Luck +N → dodge +N*0.1, critical_hit_chance +N*0.1, res_effects +N*0.1."""
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(luck=20)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        luck_bonus = 20 * STAT_BONUS_PER_POINT

        assert attrs["dodge"] == pytest.approx(BASE_DODGE + luck_bonus, abs=1e-6)
        assert attrs["critical_hit_chance"] == pytest.approx(BASE_CRIT + luck_bonus, abs=1e-6)
        assert attrs["res_effects"] == pytest.approx(luck_bonus, abs=1e-6)

    def test_combined_strength_intelligence_endurance_luck(self, upgrade_client, db_session):
        """All four together produce correct combined results."""
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(strength=10, intelligence=15, endurance=5, luck=8)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        b = STAT_BONUS_PER_POINT

        # Physical resistances from strength only
        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert attrs[field] == pytest.approx(10 * b, abs=1e-6)

        # Magical resistances from intelligence only
        for field in MAGICAL_RESISTANCE_FIELDS:
            assert attrs[field] == pytest.approx(15 * b, abs=1e-6)

        # res_effects = endurance * 0.2 + luck * 0.1
        assert attrs["res_effects"] == pytest.approx(
            5 * ENDURANCE_RES_EFFECTS_MULTIPLIER + 8 * b, abs=1e-6
        )

        # dodge has luck component
        assert attrs["dodge"] == pytest.approx(BASE_DODGE + 8 * b, abs=1e-6)

        # crit has luck component
        assert attrs["critical_hit_chance"] == pytest.approx(BASE_CRIT + 8 * b, abs=1e-6)


# ===========================================================================
# 4. recalculate_all endpoint — batch recalculation
# ===========================================================================
class TestRecalculateAll:
    """Test the admin/recalculate_all endpoint for batch recalculation."""

    def test_recalculate_all_updates_multiple_characters(self, admin_client, db_session):
        """recalculate_all should recalculate derived stats for ALL characters."""
        # Create 3 characters with different base stats but wrong derived stats
        _make_attrs(
            db_session, character_id=1,
            strength=10, intelligence=5, endurance=3, luck=2,
            agility=8, health=5, mana=3, energy=2, stamina=4,
            # Deliberately wrong derived stats
            max_health=0, max_mana=0, max_energy=0, max_stamina=0,
            current_health=0, current_mana=0, current_energy=0, current_stamina=0,
            dodge=0.0, critical_hit_chance=0.0, res_physical=0.0, res_magic=0.0,
            res_effects=0.0,
        )
        _make_attrs(
            db_session, character_id=2,
            strength=20, intelligence=15, endurance=10, luck=5,
            agility=12, health=8, mana=6, energy=4, stamina=3,
            max_health=0, max_mana=0, max_energy=0, max_stamina=0,
            current_health=0, current_mana=0, current_energy=0, current_stamina=0,
            dodge=0.0, critical_hit_chance=0.0, res_physical=0.0, res_magic=0.0,
            res_effects=0.0,
        )
        _make_attrs(
            db_session, character_id=3,
            strength=0, intelligence=0, endurance=0, luck=0,
            agility=0, health=0, mana=0, energy=0, stamina=0,
            max_health=0, max_mana=0, max_energy=0, max_stamina=0,
            current_health=0, current_mana=0, current_energy=0, current_stamina=0,
            dodge=0.0, critical_hit_chance=0.0,
        )

        resp = admin_client.post("/attributes/admin/recalculate_all")
        assert resp.status_code == 200

        data = resp.json()
        assert data["count"] == 3
        assert "Recalculated 3 characters" in data["detail"]

        b = STAT_BONUS_PER_POINT

        # Verify character 1
        attr1 = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr1)
        assert attr1.max_health == int(BASE_HEALTH + 5 * HEALTH_MULTIPLIER)
        assert attr1.dodge == pytest.approx(BASE_DODGE + 8 * b + 2 * b, abs=1e-6)
        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert getattr(attr1, field) == pytest.approx(10 * b, abs=1e-6)
        for field in MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr1, field) == pytest.approx(5 * b, abs=1e-6)

        # Verify character 2
        attr2 = db_session.query(models.CharacterAttributes).filter_by(
            character_id=2
        ).first()
        db_session.refresh(attr2)
        assert attr2.max_health == int(BASE_HEALTH + 8 * HEALTH_MULTIPLIER)
        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert getattr(attr2, field) == pytest.approx(20 * b, abs=1e-6)
        for field in MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr2, field) == pytest.approx(15 * b, abs=1e-6)
        assert attr2.res_effects == pytest.approx(
            10 * ENDURANCE_RES_EFFECTS_MULTIPLIER + 5 * b, abs=1e-6
        )

        # Verify character 3 (all zeros → base defaults)
        attr3 = db_session.query(models.CharacterAttributes).filter_by(
            character_id=3
        ).first()
        db_session.refresh(attr3)
        assert attr3.max_health == BASE_HEALTH
        assert attr3.max_mana == BASE_MANA
        assert attr3.dodge == pytest.approx(BASE_DODGE, abs=1e-6)
        assert attr3.critical_hit_chance == pytest.approx(BASE_CRIT, abs=1e-6)

    def test_recalculate_all_returns_zero_for_empty_db(self, admin_client, db_session):
        """recalculate_all with no characters should return count=0."""
        resp = admin_client.post("/attributes/admin/recalculate_all")
        assert resp.status_code == 200

        data = resp.json()
        assert data["count"] == 0

    def test_recalculate_all_single_character(self, admin_client, db_session):
        """recalculate_all with one character should work correctly."""
        _make_attrs(
            db_session, character_id=1,
            strength=5, agility=10, intelligence=8, endurance=12,
            health=3, mana=2, energy=1, stamina=4, luck=6,
            # Wrong values to be corrected
            max_health=0, max_mana=0, max_energy=0, max_stamina=0,
            current_health=0, current_mana=0, current_energy=0, current_stamina=0,
            dodge=0.0, critical_hit_chance=0.0,
        )

        resp = admin_client.post("/attributes/admin/recalculate_all")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

        attr = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr)

        b = STAT_BONUS_PER_POINT
        assert attr.max_health == int(BASE_HEALTH + 3 * HEALTH_MULTIPLIER)
        assert attr.max_mana == int(BASE_MANA + 2 * MANA_MULTIPLIER)
        assert attr.max_energy == int(BASE_ENERGY + 1 * ENERGY_MULTIPLIER)
        assert attr.max_stamina == int(BASE_STAMINA + 4 * STAMINA_MULTIPLIER)
        assert attr.dodge == pytest.approx(BASE_DODGE + 10 * b + 6 * b, abs=1e-6)
        assert attr.critical_hit_chance == pytest.approx(BASE_CRIT + 6 * b, abs=1e-6)
        assert attr.res_effects == pytest.approx(
            12 * ENDURANCE_RES_EFFECTS_MULTIPLIER + 6 * b, abs=1e-6
        )


# ===========================================================================
# 5. Edge cases
# ===========================================================================
class TestEdgeCases:
    """Edge case tests for formula computations."""

    def test_all_stats_zero_gives_base_defaults(self, db_session):
        """All base stats at 0 should produce base defaults for derived stats."""
        attr = _make_attrs(db_session, character_id=200)
        crud.compute_derived_stats(attr)

        assert attr.max_health == BASE_HEALTH
        assert attr.max_mana == BASE_MANA
        assert attr.max_energy == BASE_ENERGY
        assert attr.max_stamina == BASE_STAMINA
        assert attr.dodge == pytest.approx(BASE_DODGE, abs=1e-6)
        assert attr.critical_hit_chance == pytest.approx(BASE_CRIT, abs=1e-6)
        assert attr.critical_damage == BASE_CRIT_DMG

        for field in PHYSICAL_RESISTANCE_FIELDS + MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(0.0, abs=1e-6)
        assert attr.res_effects == pytest.approx(0.0, abs=1e-6)

    def test_very_high_stats_no_overflow(self, db_session):
        """Very high stat values should compute without overflow or errors."""
        attr = _make_attrs(
            db_session, character_id=201,
            strength=10000, agility=10000, intelligence=10000,
            endurance=10000, health=10000, mana=10000,
            energy=10000, stamina=10000, luck=10000,
            # High current values to test clamp
            current_health=999999, current_mana=999999,
            current_energy=999999, current_stamina=999999,
        )
        crud.compute_derived_stats(attr)

        b = STAT_BONUS_PER_POINT

        # Resources should compute without overflow
        assert attr.max_health == int(BASE_HEALTH + 10000 * HEALTH_MULTIPLIER)
        assert attr.max_mana == int(BASE_MANA + 10000 * MANA_MULTIPLIER)
        assert attr.max_energy == int(BASE_ENERGY + 10000 * ENERGY_MULTIPLIER)
        assert attr.max_stamina == int(BASE_STAMINA + 10000 * STAMINA_MULTIPLIER)

        # Current clamped to max
        assert attr.current_health == attr.max_health
        assert attr.current_mana == attr.max_mana
        assert attr.current_energy == attr.max_energy
        assert attr.current_stamina == attr.max_stamina

        # Resistances should compute without overflow
        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(10000 * b, abs=1e-2)
        for field in MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(10000 * b, abs=1e-2)

        # Dodge and crit should compute without overflow
        assert attr.dodge == pytest.approx(
            BASE_DODGE + 10000 * b + 10000 * b, abs=1e-2
        )
        assert attr.critical_hit_chance == pytest.approx(
            BASE_CRIT + 10000 * b, abs=1e-2
        )

        # res_effects = endurance * 0.2 + luck * 0.1
        assert attr.res_effects == pytest.approx(
            10000 * ENDURANCE_RES_EFFECTS_MULTIPLIER + 10000 * b, abs=1e-2
        )

    def test_single_stat_isolation_strength(self, db_session):
        """Only strength set — only physical resistances affected."""
        attr = _make_attrs(db_session, character_id=202, strength=100)
        crud.compute_derived_stats(attr)

        # Physical resistances set
        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(100 * STAT_BONUS_PER_POINT, abs=1e-6)

        # Everything else at base/zero
        for field in MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(0.0, abs=1e-6)
        assert attr.res_effects == pytest.approx(0.0, abs=1e-6)
        assert attr.dodge == pytest.approx(BASE_DODGE, abs=1e-6)
        assert attr.critical_hit_chance == pytest.approx(BASE_CRIT, abs=1e-6)

    def test_single_stat_isolation_intelligence(self, db_session):
        """Only intelligence set — only magical resistances affected."""
        attr = _make_attrs(db_session, character_id=203, intelligence=100)
        crud.compute_derived_stats(attr)

        for field in MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(100 * STAT_BONUS_PER_POINT, abs=1e-6)

        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(0.0, abs=1e-6)
        assert attr.res_effects == pytest.approx(0.0, abs=1e-6)
        assert attr.dodge == pytest.approx(BASE_DODGE, abs=1e-6)

    def test_single_stat_isolation_endurance(self, db_session):
        """Only endurance set — only res_effects affected (at 0.2x rate)."""
        attr = _make_attrs(db_session, character_id=204, endurance=50)
        crud.compute_derived_stats(attr)

        assert attr.res_effects == pytest.approx(
            50 * ENDURANCE_RES_EFFECTS_MULTIPLIER, abs=1e-6
        )

        for field in PHYSICAL_RESISTANCE_FIELDS + MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(0.0, abs=1e-6)
        assert attr.dodge == pytest.approx(BASE_DODGE, abs=1e-6)
        assert attr.critical_hit_chance == pytest.approx(BASE_CRIT, abs=1e-6)

    def test_single_stat_isolation_luck(self, db_session):
        """Only luck set — dodge, crit, and res_effects affected."""
        attr = _make_attrs(db_session, character_id=205, luck=30)
        crud.compute_derived_stats(attr)

        b = STAT_BONUS_PER_POINT
        assert attr.dodge == pytest.approx(BASE_DODGE + 30 * b, abs=1e-6)
        assert attr.critical_hit_chance == pytest.approx(BASE_CRIT + 30 * b, abs=1e-6)
        assert attr.res_effects == pytest.approx(30 * b, abs=1e-6)

        for field in PHYSICAL_RESISTANCE_FIELDS + MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(0.0, abs=1e-6)

    def test_current_below_max_not_clamped_up(self, db_session):
        """If current < new max, current should NOT be increased (only clamped down)."""
        attr = _make_attrs(
            db_session, character_id=206,
            health=10,
            current_health=50, max_health=200,
        )
        crud.compute_derived_stats(attr)

        # max_health = 100 + 10*10 = 200
        assert attr.max_health == int(BASE_HEALTH + 10 * HEALTH_MULTIPLIER)
        # current_health was 50, which is below new max of 200, so stays at 50
        assert attr.current_health == 50
