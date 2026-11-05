"""
FEAT-201 — the stealth stat (character-attributes-service).

Stealth is the 11th primary: stored as a TOTAL (points + gear + perks + food),
like charisma it has NO derived field (it only lowers the witness chance in
character-service). Locked down here:

  * lists / schemas: in PRIMARY_ATTRIBUTE_KEYS, not in PRIMARY_DERIVED_EFFECTS;
    StatsUpgradeRequest / AdminAttributeUpdate / responses carry it; the create
    default is 0 (NOT 1 like charisma/luck); negatives rejected;
  * create: default 0 in the DB, explicit value stored, derived stats identical;
  * apply_attribute_modifiers: moves stealth only (no derived stat), reversal exact;
  * upgrade endpoint: points are consumed (deduct payload), the total rises, the
    response carries it, not-enough-points / negative / injection rejected;
    an attribute-condition perk on stealth is granted by the upgrade;
  * perk flat bonus `stealth`: validation, modifiers dict, apply + reversal,
    progress shown for an attribute condition on stealth;
  * satiety (food) with stealth: applied, then reversed exactly on expiry;
  * admin PUT writes stealth; /recalculate never touches it;
  * migration 009_add_stealth: real Alembic Operations on SQLite — NOT NULL
    default 0, existing rows 0, idempotent, downgrade drops, chain head.
"""

import importlib.util
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

import database  # noqa: E402

database.engine = _test_engine
database.SessionLocal = _TestSessionLocal

import constants  # noqa: E402
import crud  # noqa: E402
import models  # noqa: E402
import perk_evaluator  # noqa: E402
import regen  # noqa: E402
import schemas  # noqa: E402
from auth_http import UserRead, get_current_user_via_http  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app, get_db  # noqa: E402

from tests.regen_shared_tables import (  # noqa: E402
    add_character,
    create_shared_tables,
    drop_shared_tables,
)

CID = 21
INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}
_ADMIN = UserRead(id=1, username="admin", role="admin",
                  permissions=["characters:read", "characters:update"])
_PLAYER = UserRead(id=10, username="player", role="user", permissions=[])

# every derived / resource column a primary stat could move
_DERIVED_COLUMNS = [
    "max_health", "current_health", "max_mana", "current_mana", "max_energy", "current_energy",
    "max_stamina", "current_stamina", "damage", "dodge", "critical_hit_chance", "critical_damage",
    "res_effects", "res_physical", "res_catting", "res_crushing", "res_piercing", "res_magic",
    "res_fire", "res_ice", "res_watering", "res_electricity", "res_sainting", "res_wind", "res_damning",
]
_OTHER_PRIMARIES = ["strength", "agility", "intelligence", "endurance", "charisma", "luck",
                    "health", "mana", "energy", "stamina"]


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _pin_internal_token(monkeypatch):
    import auth_http
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", INTERNAL_HEADERS["X-Internal-Token"])


@pytest.fixture(autouse=True)
def _setup_tables():
    create_shared_tables(_test_engine)
    models.Base.metadata.create_all(bind=_test_engine)
    yield
    drop_shared_tables(_test_engine)
    models.Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture()
def db():
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _fresh_session():
    s = _TestSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def client():
    app.dependency_overrides[get_db] = _fresh_session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_client():
    app.dependency_overrides[get_db] = _fresh_session
    app.dependency_overrides[get_current_user_via_http] = lambda: _ADMIN
    with patch("main._fetch_equipment_modifiers", side_effect=lambda ids: {cid: {} for cid in ids}):
        yield TestClient(app)
    app.dependency_overrides.clear()


def _now():
    return datetime.utcnow().replace(microsecond=0)


def seed(db, character_id=CID, **values):
    add_character(db, character_id)
    base = dict(
        strength=10, agility=10, intelligence=10, endurance=10, charisma=0, luck=10,
        current_health=100, max_health=100, current_mana=75, max_mana=75,
        current_energy=50, max_energy=50, current_stamina=100, max_stamina=100,
        dodge=5.0, critical_hit_chance=20.0, critical_damage=125,
        regen_anchor_at=_now(),
    )
    base.update(values)
    db.add(models.CharacterAttributes(character_id=character_id, **base))
    db.commit()


def reload(db, character_id=CID):
    db.expire_all()
    return db.query(models.CharacterAttributes).filter_by(character_id=character_id).one()


def _snapshot(attr):
    return {c: getattr(attr, c) for c in _DERIVED_COLUMNS + _OTHER_PRIMARIES}


# ===========================================================================
# 1. Stat lists and schemas
# ===========================================================================

class TestListsAndSchemas:

    def test_stealth_is_a_primary_without_derived_effects(self):
        assert "stealth" in constants.PRIMARY_ATTRIBUTE_KEYS
        assert "stealth" not in constants.PRIMARY_DERIVED_EFFECTS
        assert "stealth" not in constants.RESOURCE_STATS

    def test_upgrade_request_covers_every_primary_and_resource(self):
        """Guard: a primary missing from the upgrade body could never be bought."""
        fields = set(schemas.StatsUpgradeRequest.__fields__)
        assert set(constants.PRIMARY_ATTRIBUTE_KEYS) | set(constants.RESOURCE_STATS) <= fields

    def test_admin_update_and_response_carry_every_primary(self):
        for model in (schemas.AdminAttributeUpdate, schemas.CharacterAttributesResponse):
            assert set(constants.PRIMARY_ATTRIBUTE_KEYS) <= set(model.__fields__), model.__name__

    def test_flat_bonus_keys_accept_every_primary(self):
        assert set(constants.PRIMARY_ATTRIBUTE_KEYS) <= crud.VALID_FLAT_BONUS_KEYS

    def test_create_default_is_zero_not_one(self):
        body = schemas.CharacterAttributesCreate(character_id=1)
        assert body.stealth == 0
        # the trap the architect warned about: charisma/luck do default to 1
        assert body.charisma == 1 and body.luck == 1

    def test_create_rejects_negative_stealth(self):
        with pytest.raises(ValidationError):
            schemas.CharacterAttributesCreate(character_id=1, stealth=-1)

    def test_upgrade_default_is_zero(self):
        assert schemas.StatsUpgradeRequest().stealth == 0

    def test_admin_update_default_is_unset(self):
        assert "stealth" not in schemas.AdminAttributeUpdate().dict(exclude_unset=True)

    def test_model_column_not_null(self):
        col = models.CharacterAttributes.__table__.c.stealth
        assert col.nullable is False


# ===========================================================================
# 2. Create
# ===========================================================================

class TestCreate:

    def test_crud_create_defaults_stealth_to_zero(self, db):
        add_character(db, CID)
        row = crud.create_character_attributes(db, schemas.CharacterAttributesCreate(character_id=CID))
        assert reload(db).stealth == 0
        assert row.stealth == 0

    def test_crud_create_stores_explicit_stealth_without_derived_effect(self, db):
        add_character(db, 1)
        add_character(db, 2)
        plain = crud.create_character_attributes(db, schemas.CharacterAttributesCreate(character_id=1))
        sneaky = crud.create_character_attributes(
            db, schemas.CharacterAttributesCreate(character_id=2, stealth=40))
        assert sneaky.stealth == 40
        assert {c: getattr(plain, c) for c in _DERIVED_COLUMNS} == \
            {c: getattr(sneaky, c) for c in _DERIVED_COLUMNS}

    def test_create_endpoint_returns_stealth(self, client, db):
        add_character(db, CID)
        resp = client.post("/attributes/", json={"character_id": CID, "stealth": 7},
                           headers=INTERNAL_HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json()["stealth"] == 7
        assert reload(db).stealth == 7

    def test_create_endpoint_without_stealth_is_zero(self, client, db):
        add_character(db, CID)
        resp = client.post("/attributes/", json={"character_id": CID}, headers=INTERNAL_HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json()["stealth"] == 0

    def test_create_endpoint_negative_stealth_422(self, client, db):
        add_character(db, CID)
        resp = client.post("/attributes/", json={"character_id": CID, "stealth": -5},
                           headers=INTERNAL_HEADERS)
        assert resp.status_code == 422

    def test_get_attributes_carries_stealth(self, client, db):
        seed(db, stealth=13)               # add_character -> user_id NULL = publicly readable
        resp = client.get(f"/attributes/{CID}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["stealth"] == 13


# ===========================================================================
# 3. apply_attribute_modifiers
# ===========================================================================

class TestApplyModifiers:

    @pytest.mark.parametrize("delta", [1, 30, 150, 400])
    def test_moves_stealth_only_and_reverses_exactly(self, db, delta):
        seed(db, stealth=5)
        attr = reload(db)
        before = _snapshot(attr)
        crud.apply_attribute_modifiers(attr, {"stealth": delta})
        assert attr.stealth == 5 + delta
        assert _snapshot(attr) == before
        crud.apply_attribute_modifiers(attr, {"stealth": -delta})
        assert attr.stealth == 5
        assert _snapshot(attr) == before

    def test_combined_with_other_stats(self, db):
        seed(db)
        attr = reload(db)
        crud.apply_attribute_modifiers(attr, {"stealth": 4, "agility": 10})
        assert attr.stealth == 4 and attr.agility == 20

    def test_endpoint_apply_and_revert(self, client, db):
        seed(db, stealth=2)
        url = f"/attributes/{CID}/apply_modifiers"
        assert client.post(url, json={"stealth": 6}, headers=INTERNAL_HEADERS).status_code == 200
        assert reload(db).stealth == 8
        assert client.post(url, json={"stealth": -6}, headers=INTERNAL_HEADERS).status_code == 200
        assert reload(db).stealth == 2

    def test_endpoint_requires_internal_token(self, client, db):
        seed(db)
        resp = client.post(f"/attributes/{CID}/apply_modifiers", json={"stealth": 50})
        assert resp.status_code in (401, 403)
        assert reload(db).stealth == 0


# ===========================================================================
# 4. Upgrade endpoint
# ===========================================================================

def _upgrade_client(stat_points):
    """Player client; character-service profile/deduct mocked. Returns (client, puts)."""
    puts = []

    profile = MagicMock(status_code=200)
    profile.json.return_value = {"stat_points": stat_points}

    async def _get(url, **kw):
        return profile

    async def _put(url, **kw):
        puts.append(kw.get("json"))
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"remaining_points": stat_points - kw["json"]["points_to_deduct"]}
        return resp

    instance = AsyncMock()
    instance.get = _get
    instance.put = _put
    return instance, puts


@pytest.fixture()
def upgrade(request):
    stat_points = getattr(request, "param", 100)
    instance, puts = _upgrade_client(stat_points)
    app.dependency_overrides[get_db] = _fresh_session
    app.dependency_overrides[get_current_user_via_http] = lambda: _PLAYER
    with patch("main.verify_character_ownership"), patch("main.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__ = AsyncMock(return_value=instance)
        cls.return_value.__aexit__ = AsyncMock(return_value=False)
        yield TestClient(app), puts
    app.dependency_overrides.clear()


class TestUpgrade:

    def test_stealth_consumes_points_and_raises_total(self, upgrade, db):
        c, puts = upgrade
        seed(db, stealth=3)
        before = _snapshot(reload(db))
        resp = c.post(f"/attributes/{CID}/upgrade", json={"stealth": 5})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["updated_attributes"]["stealth"] == 5 + 3
        assert body["stat_points_remaining"] == 95
        assert puts == [{"points_to_deduct": 5}]
        after = reload(db)
        assert after.stealth == 8
        assert _snapshot(after) == before          # no derived field moves

    def test_stealth_counts_with_other_stats(self, upgrade, db):
        c, puts = upgrade
        seed(db)
        resp = c.post(f"/attributes/{CID}/upgrade", json={"stealth": 4, "agility": 3, "luck": 2})
        assert resp.status_code == 200, resp.text
        assert puts == [{"points_to_deduct": 9}]
        attr = reload(db)
        assert (attr.stealth, attr.agility, attr.luck) == (4, 13, 12)

    @pytest.mark.parametrize("upgrade", [5], indirect=True)
    def test_not_enough_points_rejected_and_nothing_spent(self, upgrade, db):
        c, puts = upgrade
        seed(db)
        resp = c.post(f"/attributes/{CID}/upgrade", json={"stealth": 6})
        assert resp.status_code == 400
        assert puts == []
        assert reload(db).stealth == 0

    def test_only_zero_is_400(self, upgrade, db):
        c, puts = upgrade
        seed(db)
        assert c.post(f"/attributes/{CID}/upgrade", json={"stealth": 0}).status_code == 400
        assert puts == []

    @pytest.mark.parametrize("value", [-1, -50, "abc", "1; DROP TABLE character_attributes"])
    def test_invalid_values_422(self, upgrade, db, value):
        c, puts = upgrade
        seed(db)
        resp = c.post(f"/attributes/{CID}/upgrade", json={"stealth": value, "agility": 60})
        assert resp.status_code == 422
        assert puts == []
        attr = reload(db)
        assert (attr.stealth, attr.agility) == (0, 10)

    def test_negative_stealth_cannot_fund_another_stat(self, upgrade, db):
        """The point-shuffling exploit: −20 stealth to pay for +21 agility."""
        c, puts = upgrade
        seed(db, stealth=20)
        resp = c.post(f"/attributes/{CID}/upgrade", json={"stealth": -20, "agility": 21})
        assert resp.status_code == 422
        assert reload(db).stealth == 20

    def test_upgrade_grants_an_attribute_perk_on_stealth(self, upgrade, db):
        """FEAT-143 reconcile after the upgrade sees the new stealth total."""
        c, _ = upgrade
        seed(db)
        db.add(models.Perk(
            name="Тень среди теней", category="exploration", rarity="common",
            conditions=[{"type": "attribute", "stat": "stealth", "operator": ">=", "value": 5}],
            bonuses={"flat": {"stealth": 3}},
        ))
        db.commit()
        assert c.post(f"/attributes/{CID}/upgrade", json={"stealth": 5}).status_code == 200
        assert reload(db).stealth == 8                   # 5 points + 3 from the perk
        assert db.query(models.CharacterPerk).filter_by(character_id=CID).count() == 1


# ===========================================================================
# 5. Perks
# ===========================================================================

class TestPerks:

    def test_flat_bonus_stealth_is_valid(self):
        crud.validate_perk_data(category="exploration", rarity="common",
                                conditions=[], bonuses={"flat": {"stealth": 5}})

    def test_unknown_flat_bonus_key_still_rejected(self):
        with pytest.raises(ValueError):
            crud.validate_perk_data(bonuses={"flat": {"stelth": 5}})

    def test_perk_modifiers_dict_and_reversal(self, db):
        seed(db, stealth=1)
        perk = models.Perk(name="p", category="exploration", rarity="common", conditions=[],
                           bonuses={"flat": {"stealth": 7}})
        mods = crud.build_perk_modifiers_dict(perk)
        assert mods == {"stealth": 7}
        assert crud.build_perk_modifiers_dict(perk, negative=True) == {"stealth": -7}

        crud._apply_modifiers_internal(db, CID, mods)
        db.commit()
        assert reload(db).stealth == 8
        crud._apply_modifiers_internal(db, CID, crud.build_perk_modifiers_dict(perk, negative=True))
        db.commit()
        assert reload(db).stealth == 1

    def test_attribute_condition_on_stealth(self, db):
        seed(db, stealth=12)
        attr = reload(db)
        cond = {"type": "attribute", "stat": "stealth", "operator": ">=", "value": 10}
        assert perk_evaluator.check_condition(cond, None, attr, None) is True
        assert perk_evaluator.check_condition(dict(cond, value=13), None, attr, None) is False

    def test_progress_for_a_stealth_condition(self, db):
        seed(db, stealth=12)
        db.add(models.Perk(
            name="Неуловимый", category="exploration", rarity="rare",
            conditions=[{"type": "attribute", "stat": "stealth", "operator": ">=", "value": 30}],
            bonuses={"flat": {}},
        ))
        db.commit()
        perks = crud.get_character_perks(db, CID)
        assert len(perks) == 1
        progress = perks[0]["progress"] if isinstance(perks[0], dict) else perks[0].progress
        assert progress["stealth"] == {"current": 12, "required": 30}


# ===========================================================================
# 6. Food (satiety) and expiry reversal
# ===========================================================================

class TestSatiety:

    def _eat(self, client, modifiers):
        return client.post(f"/attributes/internal/{CID}/satiety", headers=INTERNAL_HEADERS, json={
            "item_id": 501, "source_item_name": "Тихий ужин", "rarity": "common",
            "modifiers": modifiers,
            "recovery": {"health_recovery": 0, "mana_recovery": 0, "energy_recovery": 0, "stamina_recovery": 0},
        })

    def test_food_stealth_applied_then_reversed_on_expiry(self, client, db):
        seed(db, stealth=10)
        before = _snapshot(reload(db))
        resp = self._eat(client, {"stealth": 6})
        assert resp.status_code == 201, resp.text
        assert reload(db).stealth == 16

        row = db.query(models.CharacterSatiety).filter_by(character_id=CID).one()
        row.expires_at = _now() - timedelta(seconds=1)
        db.commit()

        attr = regen.lock_attributes(db, CID)
        assert regen.settle_regen(db, attr) is True
        db.commit()
        after = reload(db)
        assert after.stealth == 10
        assert {c: getattr(after, c) for c in _OTHER_PRIMARIES} == \
            {c: before[c] for c in _OTHER_PRIMARIES}
        assert db.query(models.CharacterSatiety).filter_by(character_id=CID).count() == 0

    def test_negative_food_stealth_reverses_too(self, client, db):
        seed(db, stealth=10)
        assert self._eat(client, {"stealth": -4}).status_code == 201
        assert reload(db).stealth == 6
        row = db.query(models.CharacterSatiety).filter_by(character_id=CID).one()
        row.expires_at = _now() - timedelta(seconds=1)
        db.commit()
        attr = regen.lock_attributes(db, CID)
        regen.settle_regen(db, attr)
        db.commit()
        assert reload(db).stealth == 10


# ===========================================================================
# 7. Admin PUT and /recalculate
# ===========================================================================

class TestAdminAndRecalculate:

    def test_admin_put_writes_stealth(self, admin_client, db):
        seed(db, stealth=3)
        resp = admin_client.put(f"/attributes/admin/{CID}", json={"stealth": 44})
        assert resp.status_code == 200, resp.text
        assert resp.json()["stealth"] == 44
        assert reload(db).stealth == 44

    def test_admin_put_without_stealth_keeps_it(self, admin_client, db):
        seed(db, stealth=9)
        assert admin_client.put(f"/attributes/admin/{CID}", json={"agility": 1}).status_code == 200
        assert reload(db).stealth == 9

    def test_admin_put_forbidden_for_player(self, db):
        seed(db, stealth=3)
        app.dependency_overrides[get_db] = _fresh_session
        app.dependency_overrides[get_current_user_via_http] = lambda: _PLAYER
        try:
            resp = TestClient(app).put(f"/attributes/admin/{CID}", json={"stealth": 999})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 403
        assert reload(db).stealth == 3

    def test_recalculate_keeps_stealth(self, admin_client, db):
        seed(db, stealth=77)
        resp = admin_client.post(f"/attributes/{CID}/recalculate")
        assert resp.status_code == 200, resp.text
        assert reload(db).stealth == 77

    def test_recalculate_with_stealth_gear_keeps_total_and_derived(self, db):
        """Gear stealth is already inside the stored total: the rebuild must not add it again,
        and it must not produce any derived value."""
        seed(db, stealth=50)
        seed(db, character_id=CID + 1, stealth=0)
        a, b = reload(db), reload(db, CID + 1)
        crud.rebuild_derived_stats(db, a, {"stealth": 20})
        crud.rebuild_derived_stats(db, b, {})
        db.commit()
        a, b = reload(db), reload(db, CID + 1)
        assert a.stealth == 50
        assert {c: getattr(a, c) for c in _DERIVED_COLUMNS} == {c: getattr(b, c) for c in _DERIVED_COLUMNS}


# ===========================================================================
# 8. Migration 009_add_stealth
# ===========================================================================

_VERSIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic", "versions"))


def _load(filename):
    spec = importlib.util.spec_from_file_location(filename[:-3], os.path.join(_VERSIONS_DIR, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def migration_db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    conn = engine.connect()
    conn.execute(text("CREATE TABLE character_attributes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                      "character_id INTEGER NOT NULL, luck INTEGER DEFAULT 0)"))
    conn.execute(text("INSERT INTO character_attributes (character_id, luck) VALUES (1, 5)"))
    conn.commit()
    mod = _load("009_add_stealth.py")
    mod.op = Operations(MigrationContext.configure(conn))
    yield conn, mod
    conn.close()
    engine.dispose()


def _cols(conn):
    return {c["name"]: c for c in inspect(conn).get_columns("character_attributes")}


class TestMigration009:

    def test_revision_chain_and_head(self):
        mod = _load("009_add_stealth.py")
        assert mod.revision == "009_add_stealth"
        assert mod.down_revision == "008_add_regen_and_satiety"
        assert len(mod.revision) <= 32
        downs = set()
        revisions = set()
        for name in os.listdir(_VERSIONS_DIR):
            if name.endswith(".py"):
                m = _load(name)
                revisions.add(m.revision)
                downs.add(m.down_revision)
        assert revisions - downs == {"009_add_stealth"}

    def test_upgrade_downgrade_upgrade(self, migration_db):
        conn, mod = migration_db
        mod.upgrade()
        conn.commit()
        cols = _cols(conn)
        assert "stealth" in cols and cols["stealth"]["nullable"] is False
        assert conn.execute(text("SELECT stealth FROM character_attributes")).scalar() == 0
        conn.execute(text("INSERT INTO character_attributes (character_id) VALUES (2)"))
        assert conn.execute(text("SELECT stealth FROM character_attributes WHERE character_id = 2")).scalar() == 0

        mod.upgrade()                         # idempotent re-run
        conn.commit()

        mod.downgrade()
        conn.commit()
        assert "stealth" not in _cols(conn)
        assert conn.execute(text("SELECT COUNT(*) FROM character_attributes")).scalar() == 2
        mod.downgrade()                       # idempotent too
        conn.commit()

        mod.upgrade()
        conn.commit()
        assert "stealth" in _cols(conn)

    def test_migration_does_not_touch_other_columns(self, migration_db):
        conn, mod = migration_db
        mod.upgrade()
        conn.commit()
        assert conn.execute(text("SELECT luck FROM character_attributes WHERE character_id = 1")).scalar() == 5
