"""
Tests for FEAT-043 Task #2: character-attributes-service upgrade formulas
and recalculate endpoint.

Covers:
  (a) Upgrade with endurance — all 13 resistance fields
  (b) Upgrade with luck — dodge, critical_hit_chance, res_effects
  (c) Upgrade with stamina — max_stamina from base 100
  (d) Upgrade with strength — res_physical
  (e) Upgrade with agility — dodge
  (f) Upgrade with intelligence — res_magic
  (g) Upgrade with health/energy/mana — resource maximums
  (h) Recalculate endpoint — derived stats from base values
  (i) New character defaults — max_stamina=100, current_stamina=100
  (j) Charisma upgrade — counter only, no derived changes
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
    STAT_BONUS_PER_POINT, ENDURANCE_RES_EFFECTS_MULTIPLIER,
    PHYSICAL_RESISTANCE_FIELDS, MAGICAL_RESISTANCE_FIELDS,
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


def _make_mock_httpx_client(stat_points=100):
    """Create a mock httpx.AsyncClient context manager for upgrade endpoint."""
    total_needed = [0]  # mutable to capture actual total

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
    """
    Return a get_db override that creates a fresh session per call.

    The upgrade endpoint uses ``with db.begin()`` which requires the session
    to have no active transaction.  A fresh session from _TestSessionLocal
    (autocommit=False) satisfies this because SQLAlchemy 2.x defers the
    actual BEGIN until the first operation inside ``with session.begin()``.
    """
    def override():
        session = _TestSessionLocal()
        try:
            yield session
        finally:
            session.close()
    return override


@pytest.fixture()
def upgrade_client(db_session):
    """
    TestClient for the upgrade endpoint with:
    - Player auth
    - verify_character_ownership mocked out
    - httpx.AsyncClient mocked to return stat_points=100
    """
    # Seed data through db_session (which shares the same in-memory DB
    # via StaticPool), but let the endpoint use its own session.
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


@pytest.fixture()
def upgrade_client_low_points(db_session):
    """Upgrade client with only 5 stat points available."""
    app.dependency_overrides[get_db] = _override_get_db_factory()
    app.dependency_overrides[get_current_user_via_http] = lambda: _PLAYER_USER

    mock_instance = _make_mock_httpx_client(stat_points=5)

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
# (a) Upgrade with endurance — all 13 resistance fields
# ===========================================================================
class TestUpgradeEndurance:

    def test_endurance_only_affects_res_effects(self, upgrade_client, db_session):
        """Endurance should add +0.2 per point to res_effects ONLY."""
        _make_attrs(db_session, character_id=1)
        endurance_points = 10
        payload = _upgrade_payload(endurance=endurance_points)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        expected_res_effects = endurance_points * ENDURANCE_RES_EFFECTS_MULTIPLIER  # 2.0

        # Endurance does NOT affect any damage resistances
        for field in [
            "res_physical", "res_catting", "res_crushing", "res_piercing",
            "res_magic", "res_fire", "res_ice", "res_watering",
            "res_electricity", "res_sainting", "res_wind", "res_damning",
        ]:
            assert attrs[field] == pytest.approx(0.0, abs=1e-6), \
                f"{field} should be 0.0, got {attrs[field]}"

        # res_effects gets endurance bonus at 0.2x
        assert attrs["res_effects"] == pytest.approx(expected_res_effects, abs=1e-6)

    def test_endurance_does_not_affect_res_physical_or_res_magic(self, upgrade_client, db_session):
        """res_physical and res_magic should NOT include endurance component."""
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(endurance=5)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        # With only endurance=5 and strength=0, res_physical = 0
        assert attrs["res_physical"] == pytest.approx(0.0, abs=1e-6)
        # With only endurance=5 and intelligence=0, res_magic = 0
        assert attrs["res_magic"] == pytest.approx(0.0, abs=1e-6)


# ===========================================================================
# (b) Upgrade with luck — dodge, critical_hit_chance, res_effects
# ===========================================================================
class TestUpgradeLuck:

    def test_luck_increments_dodge(self, upgrade_client, db_session):
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(luck=10)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        assert attrs["dodge"] == pytest.approx(
            BASE_DODGE + 10 * STAT_BONUS_PER_POINT, abs=1e-6
        )

    def test_luck_increments_critical_hit_chance(self, upgrade_client, db_session):
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(luck=10)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        assert attrs["critical_hit_chance"] == pytest.approx(
            BASE_CRIT + 10 * STAT_BONUS_PER_POINT, abs=1e-6
        )

    def test_luck_increments_res_effects(self, upgrade_client, db_session):
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(luck=10)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        assert attrs["res_effects"] == pytest.approx(
            10 * STAT_BONUS_PER_POINT, abs=1e-6
        )


# ===========================================================================
# (c) Upgrade with stamina — max_stamina from base 100
# ===========================================================================
class TestUpgradeStamina:

    def test_stamina_increments_max_stamina(self, upgrade_client, db_session):
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(stamina=5)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attr = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr)
        # max_stamina = BASE_STAMINA (100) + 5 * 5 = 125
        assert attr.max_stamina == BASE_STAMINA + 5 * 5
        assert attr.current_stamina == BASE_STAMINA + 5 * 5


# ===========================================================================
# (d) Upgrade with strength — res_physical
# ===========================================================================
class TestUpgradeStrength:

    def test_strength_increments_all_physical_resistances(self, upgrade_client, db_session):
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(strength=20)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        expected = 20 * STAT_BONUS_PER_POINT
        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert attrs[field] == pytest.approx(expected, abs=1e-6), \
                f"{field} should be {expected}, got {attrs[field]}"

    def test_strength_does_not_affect_other_stats(self, upgrade_client, db_session):
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(strength=10)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        assert attrs["dodge"] == pytest.approx(BASE_DODGE, abs=1e-6)
        assert attrs["critical_hit_chance"] == pytest.approx(BASE_CRIT, abs=1e-6)
        assert attrs["res_magic"] == pytest.approx(0.0, abs=1e-6)
        # Strength should not affect magical resistances
        for field in MAGICAL_RESISTANCE_FIELDS:
            assert attrs[field] == pytest.approx(0.0, abs=1e-6)


# ===========================================================================
# (e) Upgrade with agility — dodge
# ===========================================================================
class TestUpgradeAgility:

    def test_agility_increments_dodge(self, upgrade_client, db_session):
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(agility=15)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        assert attrs["dodge"] == pytest.approx(
            BASE_DODGE + 15 * STAT_BONUS_PER_POINT, abs=1e-6
        )

    def test_agility_does_not_affect_resistances(self, upgrade_client, db_session):
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(agility=10)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        assert attrs["res_physical"] == pytest.approx(0.0, abs=1e-6)
        assert attrs["res_magic"] == pytest.approx(0.0, abs=1e-6)


# ===========================================================================
# (f) Upgrade with intelligence — res_magic
# ===========================================================================
class TestUpgradeIntelligence:

    def test_intelligence_increments_all_magical_resistances(self, upgrade_client, db_session):
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(intelligence=20)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        expected = 20 * STAT_BONUS_PER_POINT
        for field in MAGICAL_RESISTANCE_FIELDS:
            assert attrs[field] == pytest.approx(expected, abs=1e-6), \
                f"{field} should be {expected}, got {attrs[field]}"

    def test_intelligence_does_not_affect_dodge_crit_or_physical(self, upgrade_client, db_session):
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(intelligence=10)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        assert attrs["dodge"] == pytest.approx(BASE_DODGE, abs=1e-6)
        assert attrs["critical_hit_chance"] == pytest.approx(BASE_CRIT, abs=1e-6)
        # Intelligence should not affect physical resistances
        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert attrs[field] == pytest.approx(0.0, abs=1e-6)


# ===========================================================================
# (g) Upgrade with health/energy/mana — resource maximums
# ===========================================================================
class TestUpgradeResources:

    def test_health_upgrade(self, upgrade_client, db_session):
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(health=5)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attr = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr)
        assert attr.max_health == BASE_HEALTH + 5 * 10
        assert attr.current_health == BASE_HEALTH + 5 * 10

    def test_energy_upgrade(self, upgrade_client, db_session):
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(energy=5)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attr = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr)
        assert attr.max_energy == BASE_ENERGY + 5 * 5
        assert attr.current_energy == BASE_ENERGY + 5 * 5

    def test_mana_upgrade(self, upgrade_client, db_session):
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(mana=5)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attr = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr)
        assert attr.max_mana == BASE_MANA + 5 * 10
        assert attr.current_mana == BASE_MANA + 5 * 10


# ===========================================================================
# (h) Recalculate endpoint — derived stats from base values
# ===========================================================================
class TestRecalculateEndpoint:

    def test_recalculate_resource_stats(self, admin_client, db_session):
        """Recalculate should compute max_health/mana/energy/stamina from base stats."""
        _make_attrs(
            db_session, character_id=1,
            health=10, mana=5, energy=8, stamina=4,
            max_health=999, max_mana=999, max_energy=999, max_stamina=999,
            current_health=50, current_mana=50, current_energy=50, current_stamina=50,
        )

        resp = admin_client.post("/attributes/1/recalculate")
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Attributes recalculated"

        attr = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr)

        assert attr.max_health == BASE_HEALTH + 10 * 10   # 200
        assert attr.max_mana == BASE_MANA + 5 * 10        # 125
        assert attr.max_energy == BASE_ENERGY + 8 * 5      # 90
        assert attr.max_stamina == BASE_STAMINA + 4 * 5    # 120

    def test_recalculate_clamps_current_to_max(self, admin_client, db_session):
        """Current resource values should be clamped to not exceed new max."""
        _make_attrs(
            db_session, character_id=1,
            health=0, mana=0, energy=0, stamina=0,
            max_health=500, max_mana=500, max_energy=500, max_stamina=500,
            current_health=300, current_mana=300, current_energy=300, current_stamina=300,
        )

        resp = admin_client.post("/attributes/1/recalculate")
        assert resp.status_code == 200

        attr = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr)

        assert attr.max_health == BASE_HEALTH
        assert attr.current_health == BASE_HEALTH
        assert attr.max_mana == BASE_MANA
        assert attr.current_mana == BASE_MANA
        assert attr.max_energy == BASE_ENERGY
        assert attr.current_energy == BASE_ENERGY
        assert attr.max_stamina == BASE_STAMINA
        assert attr.current_stamina == BASE_STAMINA

    def test_recalculate_dodge(self, admin_client, db_session):
        """dodge = BASE_DODGE + agility * 0.1 + luck * 0.1"""
        _make_attrs(db_session, character_id=1, agility=20, luck=10, dodge=0.0)

        resp = admin_client.post("/attributes/1/recalculate")
        assert resp.status_code == 200

        attr = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr)

        expected = BASE_DODGE + 20 * STAT_BONUS_PER_POINT + 10 * STAT_BONUS_PER_POINT
        assert attr.dodge == pytest.approx(expected, abs=1e-6)

    def test_recalculate_critical_hit_chance(self, admin_client, db_session):
        """critical_hit_chance = BASE_CRIT + luck * 0.1"""
        _make_attrs(db_session, character_id=1, luck=30, critical_hit_chance=0.0)

        resp = admin_client.post("/attributes/1/recalculate")
        assert resp.status_code == 200

        attr = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr)

        expected = BASE_CRIT + 30 * STAT_BONUS_PER_POINT
        assert attr.critical_hit_chance == pytest.approx(expected, abs=1e-6)

    def test_recalculate_res_physical(self, admin_client, db_session):
        """res_physical = strength * 0.1 (endurance no longer contributes)"""
        _make_attrs(
            db_session, character_id=1,
            strength=15, endurance=10, res_physical=0.0,
        )

        resp = admin_client.post("/attributes/1/recalculate")
        assert resp.status_code == 200

        attr = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr)

        expected = 15 * STAT_BONUS_PER_POINT
        assert attr.res_physical == pytest.approx(expected, abs=1e-6)

    def test_recalculate_res_magic(self, admin_client, db_session):
        """res_magic = intelligence * 0.1 (endurance no longer contributes)"""
        _make_attrs(
            db_session, character_id=1,
            intelligence=20, endurance=5, res_magic=0.0,
        )

        resp = admin_client.post("/attributes/1/recalculate")
        assert resp.status_code == 200

        attr = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr)

        expected = 20 * STAT_BONUS_PER_POINT
        assert attr.res_magic == pytest.approx(expected, abs=1e-6)

    def test_recalculate_res_effects(self, admin_client, db_session):
        """res_effects = endurance * 0.2 + luck * 0.1"""
        _make_attrs(
            db_session, character_id=1,
            endurance=10, luck=20, res_effects=0.0,
        )

        resp = admin_client.post("/attributes/1/recalculate")
        assert resp.status_code == 200

        attr = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr)

        expected = 10 * ENDURANCE_RES_EFFECTS_MULTIPLIER + 20 * STAT_BONUS_PER_POINT
        assert attr.res_effects == pytest.approx(expected, abs=1e-6)

    def test_recalculate_physical_resistances_from_strength(self, admin_client, db_session):
        """Physical resistances (catting, crushing, piercing) = strength * 0.1"""
        _make_attrs(db_session, character_id=1, strength=15, endurance=10)

        resp = admin_client.post("/attributes/1/recalculate")
        assert resp.status_code == 200

        attr = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr)

        expected = 15 * STAT_BONUS_PER_POINT
        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(expected, abs=1e-6), \
                f"{field} should be {expected}, got {getattr(attr, field)}"

    def test_recalculate_magical_resistances_from_intelligence(self, admin_client, db_session):
        """Magical resistances (fire, ice, etc.) = intelligence * 0.1"""
        _make_attrs(db_session, character_id=1, intelligence=15, endurance=10)

        resp = admin_client.post("/attributes/1/recalculate")
        assert resp.status_code == 200

        attr = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr)

        expected = 15 * STAT_BONUS_PER_POINT
        for field in MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(expected, abs=1e-6), \
                f"{field} should be {expected}, got {getattr(attr, field)}"

    def test_recalculate_critical_damage_unchanged(self, admin_client, db_session):
        """critical_damage = BASE_CRIT_DMG (125), only modified by items."""
        _make_attrs(db_session, character_id=1, critical_damage=50)

        resp = admin_client.post("/attributes/1/recalculate")
        assert resp.status_code == 200

        attr = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr)
        assert attr.critical_damage == BASE_CRIT_DMG

    def test_recalculate_not_found(self, admin_client, db_session):
        resp = admin_client.post("/attributes/999/recalculate")
        assert resp.status_code == 404

    def test_recalculate_full_scenario(self, admin_client, db_session):
        """Full integration: set various base stats and verify all derived stats."""
        _make_attrs(
            db_session, character_id=1,
            strength=10, agility=20, intelligence=15, endurance=5,
            health=8, mana=6, energy=4, stamina=3,
            charisma=7, luck=12,
            max_health=0, max_mana=0, max_energy=0, max_stamina=0,
            current_health=0, current_mana=0, current_energy=0, current_stamina=0,
            dodge=0.0, critical_hit_chance=0.0, critical_damage=0,
            res_physical=0.0, res_magic=0.0, res_effects=0.0,
        )

        resp = admin_client.post("/attributes/1/recalculate")
        assert resp.status_code == 200

        attr = db_session.query(models.CharacterAttributes).filter_by(
            character_id=1
        ).first()
        db_session.refresh(attr)

        b = STAT_BONUS_PER_POINT

        assert attr.max_health == BASE_HEALTH + 8 * 10
        assert attr.max_mana == BASE_MANA + 6 * 10
        assert attr.max_energy == BASE_ENERGY + 4 * 5
        assert attr.max_stamina == BASE_STAMINA + 3 * 5

        assert attr.dodge == pytest.approx(
            BASE_DODGE + 20 * b + 12 * b, abs=1e-6
        )
        assert attr.critical_hit_chance == pytest.approx(
            BASE_CRIT + 12 * b, abs=1e-6
        )
        assert attr.critical_damage == BASE_CRIT_DMG

        # Physical resistances from strength only
        assert attr.res_physical == pytest.approx(10 * b, abs=1e-6)
        for field in PHYSICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(10 * b, abs=1e-6)

        # Magical resistances from intelligence only
        assert attr.res_magic == pytest.approx(15 * b, abs=1e-6)
        for field in MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, field) == pytest.approx(15 * b, abs=1e-6)

        # res_effects = endurance * 0.2 + luck * 0.1
        assert attr.res_effects == pytest.approx(
            5 * ENDURANCE_RES_EFFECTS_MULTIPLIER + 12 * b, abs=1e-6
        )


# ===========================================================================
# (i) New character defaults — max_stamina=100, current_stamina=100
# ===========================================================================
class TestNewCharacterDefaults:

    def test_model_defaults_stamina_100(self, db_session):
        """CharacterAttributes model should default max_stamina=100, current_stamina=100."""
        attr = models.CharacterAttributes(character_id=999)
        db_session.add(attr)
        db_session.commit()
        db_session.refresh(attr)

        assert attr.max_stamina == 100
        assert attr.current_stamina == 100

    def test_create_character_attributes_stamina_base(self, db_session):
        """crud.create_character_attributes should use BASE_STAMINA=100."""
        create_data = schemas.CharacterAttributesCreate(
            character_id=998,
            strength=0, agility=0, intelligence=0, endurance=0,
            health=0, mana=0, energy=0, stamina=0,
            charisma=0, luck=0,
        )
        attr = crud.create_character_attributes(db_session, create_data)

        assert attr.max_stamina == BASE_STAMINA
        assert attr.current_stamina == BASE_STAMINA
        assert attr.max_health == BASE_HEALTH
        assert attr.max_mana == BASE_MANA
        assert attr.max_energy == BASE_ENERGY

    def test_create_character_attributes_with_stamina_points(self, db_session):
        """Stamina points should add to BASE_STAMINA of 100."""
        create_data = schemas.CharacterAttributesCreate(
            character_id=997,
            strength=0, agility=0, intelligence=0, endurance=0,
            health=0, mana=0, energy=0, stamina=10,
            charisma=0, luck=0,
        )
        attr = crud.create_character_attributes(db_session, create_data)

        assert attr.max_stamina == BASE_STAMINA + 10 * 5
        assert attr.current_stamina == BASE_STAMINA + 10 * 5


# ===========================================================================
# (j) Charisma upgrade — counter only, no derived stat changes
# ===========================================================================
class TestUpgradeCharisma:

    def test_charisma_only_increments_counter(self, upgrade_client, db_session):
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(charisma=10)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        assert attrs["charisma"] == 10

        # No derived stats should change
        assert attrs["dodge"] == pytest.approx(BASE_DODGE, abs=1e-6)
        assert attrs["critical_hit_chance"] == pytest.approx(BASE_CRIT, abs=1e-6)
        assert attrs["res_physical"] == pytest.approx(0.0, abs=1e-6)
        assert attrs["res_magic"] == pytest.approx(0.0, abs=1e-6)
        assert attrs["res_effects"] == pytest.approx(0.0, abs=1e-6)


# ===========================================================================
# Combined upgrade tests
# ===========================================================================
class TestUpgradeCombined:

    def test_endurance_and_luck_combined_on_res_effects(
        self, upgrade_client, db_session
    ):
        """Both endurance (0.2x) and luck (0.1x) contribute to res_effects."""
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(endurance=10, luck=5)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        assert attrs["res_effects"] == pytest.approx(
            10 * ENDURANCE_RES_EFFECTS_MULTIPLIER + 5 * STAT_BONUS_PER_POINT, abs=1e-6
        )

    def test_agility_and_luck_combined_on_dodge(self, upgrade_client, db_session):
        """Both agility and luck contribute to dodge."""
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(agility=10, luck=5)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        assert attrs["dodge"] == pytest.approx(
            BASE_DODGE + 10 * STAT_BONUS_PER_POINT + 5 * STAT_BONUS_PER_POINT,
            abs=1e-6,
        )

    def test_strength_and_endurance_combined_on_res_physical(
        self, upgrade_client, db_session
    ):
        """Only strength contributes to res_physical (endurance does not)."""
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(strength=10, endurance=5)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        # Only strength contributes to physical resistances
        assert attrs["res_physical"] == pytest.approx(
            10 * STAT_BONUS_PER_POINT, abs=1e-6
        )

    def test_intelligence_and_endurance_combined_on_res_magic(
        self, upgrade_client, db_session
    ):
        """Only intelligence contributes to res_magic (endurance does not)."""
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(intelligence=10, endurance=5)

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 200

        attrs = resp.json()["updated_attributes"]
        # Only intelligence contributes to magical resistances
        assert attrs["res_magic"] == pytest.approx(
            10 * STAT_BONUS_PER_POINT, abs=1e-6
        )

    def test_upgrade_zero_stats_rejected(self, upgrade_client, db_session):
        """Upgrade with all zeroes should be rejected."""
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload()

        resp = upgrade_client.post("/attributes/1/upgrade", json=payload)
        assert resp.status_code == 400

    def test_upgrade_not_enough_points(
        self, upgrade_client_low_points, db_session
    ):
        """Upgrade requesting more points than available should be rejected."""
        _make_attrs(db_session, character_id=1)
        payload = _upgrade_payload(strength=50)

        resp = upgrade_client_low_points.post(
            "/attributes/1/upgrade", json=payload
        )
        assert resp.status_code == 400


# ===========================================================================
# Recalculate endpoint — CRUD unit test
# ===========================================================================
class TestRecalculateCrud:

    def test_recalculate_returns_none_for_missing_character(self, db_session):
        result = crud.recalculate_attributes(db_session, character_id=99999)
        assert result is None

    def test_recalculate_sets_all_fields(self, db_session):
        """Direct test of crud.recalculate_attributes function."""
        _make_attrs(
            db_session, character_id=1,
            strength=10, agility=20, intelligence=15, endurance=5,
            health=8, mana=6, energy=4, stamina=3,
            luck=12,
        )

        result = crud.recalculate_attributes(db_session, character_id=1)
        assert result is not None

        b = STAT_BONUS_PER_POINT

        assert result.max_health == int(BASE_HEALTH + 8 * 10)
        assert result.max_mana == int(BASE_MANA + 6 * 10)
        assert result.max_energy == int(BASE_ENERGY + 4 * 5)
        assert result.max_stamina == int(BASE_STAMINA + 3 * 5)

        assert result.dodge == pytest.approx(
            BASE_DODGE + 20 * b + 12 * b, abs=1e-6
        )
        assert result.critical_hit_chance == pytest.approx(
            BASE_CRIT + 12 * b, abs=1e-6
        )
        assert result.critical_damage == BASE_CRIT_DMG

        assert result.res_physical == pytest.approx(10 * b, abs=1e-6)
        assert result.res_magic == pytest.approx(15 * b, abs=1e-6)
        assert result.res_effects == pytest.approx(
            5 * ENDURANCE_RES_EFFECTS_MULTIPLIER + 12 * b, abs=1e-6
        )
