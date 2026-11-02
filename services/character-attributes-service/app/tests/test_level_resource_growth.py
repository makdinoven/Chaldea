"""
FEAT-196 — per-level resource growth by class (character-attributes-service).

max_R = BASE_R + floor(m_R * eff(R)) + level * rate(class, R)
  warrior (1): health 15, mana/energy/stamina 10
  rogue   (2): energy 15, health/mana/stamina 10
  mage    (3): mana   15, health/energy/stamina 10
The level term is outside the FEAT-195 cap; unknown/None class or a missing /
non-positive level gives no bonus.

Covers:
  * crud.level_resource_bonus / resource_max: full rate table, L1/L7/L50
    (750/500), unknown class, level None/0/negative, cap not applied to bonus;
  * POST /attributes/ (create): body level/id_class, body wins over the DB,
    partial body + DB fallback, DB fallback only, no row -> no bonus, mob row;
  * POST /attributes/internal/{id}/sync-level: auth (401), 404, level up
    (current += diff), level down (clamp), multi-level jump, class change,
    idempotency, unknown class, missing characters row, drift healing,
    settle_regen before the change;
  * apply_attribute_modifiers unaffected: equip/upgrade/unequip with a level
    bonus present is exactly reversible, max == resource_max(..., level, class);
  * rebuild_derived_stats / recalculate / recalculate_all: bonus included,
    idempotent, == create + sync, no top-up, players + NPC + mob rows,
    an SQL error on `characters` surfaces (batch skipped, never a silent
    "no bonus").

All expectations are computed independently from the hard-coded rate table
below and the FEAT-195 formula, and asserted on the real stored columns.
"""
import math
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

import database  # noqa: E402

database.engine = _test_engine
database.SessionLocal = _TestSessionLocal

import auth_http  # noqa: E402
import constants  # noqa: E402
import crud  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import regen  # noqa: E402
from auth_http import UserRead, get_current_user_via_http  # noqa: E402
from constants import (  # noqa: E402
    BASE_HEALTH, BASE_MANA, BASE_ENERGY, BASE_STAMINA,
    HEALTH_MULTIPLIER, MANA_MULTIPLIER, ENERGY_MULTIPLIER, STAMINA_MULTIPLIER,
)
from fastapi.testclient import TestClient  # noqa: E402
from main import app, get_db  # noqa: E402
from stat_caps import effective_stat  # noqa: E402
from tests.regen_shared_tables import (  # noqa: E402
    add_character,
    create_shared_tables,
    drop_shared_tables,
)

TOKEN = "test-internal-token"
INTERNAL_HEADERS = {"X-Internal-Token": TOKEN}
CID = 41

RESOURCES = ("health", "mana", "energy", "stamina")
MAX_FIELDS = tuple(f"max_{r}" for r in RESOURCES)
CUR_FIELDS = tuple(f"current_{r}" for r in RESOURCES)

WARRIOR, ROGUE, MAGE = 1, 2, 3
# Hard-coded from the feature brief (independent of constants.py).
RATES = {
    WARRIOR: {"health": 15, "mana": 10, "energy": 10, "stamina": 10},
    ROGUE: {"health": 10, "mana": 10, "energy": 15, "stamina": 10},
    MAGE: {"health": 10, "mana": 15, "energy": 10, "stamina": 10},
}
_BASE = {
    "health": (BASE_HEALTH, HEALTH_MULTIPLIER),
    "mana": (BASE_MANA, MANA_MULTIPLIER),
    "energy": (BASE_ENERGY, ENERGY_MULTIPLIER),
    "stamina": (BASE_STAMINA, STAMINA_MULTIPLIER),
}

_ADMIN = UserRead(id=1, username="admin", role="admin",
                  permissions=["characters:read", "characters:update"])


def bonus(resource, cls, level):
    if cls not in RATES or level is None or level < 1:
        return 0
    return level * RATES[cls][resource]


def expected_max(resource, value, level=None, cls=None):
    base, mult = _BASE[resource]
    return base + math.floor(mult * effective_stat(value)) + bonus(resource, cls, level)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _pin_internal_token(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)


@pytest.fixture()
def db():
    create_shared_tables(_test_engine)
    models.Base.metadata.create_all(bind=_test_engine)
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        drop_shared_tables(_test_engine)
        models.Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture()
def client(db):
    """Fresh session per request, like production."""
    def _override_get_db():
        s = _TestSessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user_via_http] = lambda: _ADMIN
    with patch("main._fetch_equipment_modifiers",
               side_effect=lambda ids: {cid: {} for cid in ids}):
        yield TestClient(app)
    app.dependency_overrides.clear()


STATS = dict(strength=10, agility=10, intelligence=10, endurance=10,
             health=40, mana=25, energy=15, stamina=30, charisma=1, luck=1)


def _create(client, character_id=CID, **extra):
    body = dict(STATS, character_id=character_id)
    body.update(extra)
    resp = client.post("/attributes/", json=body, headers=INTERNAL_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _reload(db, character_id=CID):
    db.expire_all()
    return db.query(models.CharacterAttributes).filter_by(character_id=character_id).one()


def _set_char(db, character_id=CID, level=None, id_class=None):
    db.execute(text("UPDATE characters SET level = :l, id_class = :c WHERE id = :id"),
               {"l": level, "c": id_class, "id": character_id})
    db.commit()


def _set_attr(db, character_id=CID, **values):
    attr = _reload(db, character_id)
    for k, v in values.items():
        setattr(attr, k, v)
    db.commit()


def _sync(client, character_id=CID, headers=INTERNAL_HEADERS):
    return client.post(f"/attributes/internal/{character_id}/sync-level", headers=headers)


def _maxes(attr):
    return {f: getattr(attr, f) for f in MAX_FIELDS}


def _currents(attr):
    return {f: getattr(attr, f) for f in CUR_FIELDS}


def _expected_maxes(level, cls, stats=STATS):
    return {f"max_{r}": expected_max(r, stats[r], level, cls) for r in RESOURCES}


# ===========================================================================
# 1. Rate table
# ===========================================================================

class TestRateTable:

    def test_constants(self):
        assert constants.MAIN_RESOURCE_PER_LEVEL == 15
        assert constants.OTHER_RESOURCE_PER_LEVEL == 10
        assert constants.CLASS_MAIN_RESOURCE == {1: "health", 2: "energy", 3: "mana"}
        assert constants.LEVEL_RESOURCE_GROWTH == RATES

    @pytest.mark.parametrize("cls", [WARRIOR, ROGUE, MAGE])
    @pytest.mark.parametrize("resource", RESOURCES)
    @pytest.mark.parametrize("level", [1, 7, 50])
    def test_bonus_per_class_resource_level(self, cls, resource, level):
        assert crud.level_resource_bonus(resource, cls, level) == level * RATES[cls][resource]

    def test_level_50_gives_750_and_500(self):
        assert crud.level_resource_bonus("health", WARRIOR, 50) == 750
        assert crud.level_resource_bonus("mana", WARRIOR, 50) == 500
        assert crud.level_resource_bonus("energy", ROGUE, 50) == 750
        assert crud.level_resource_bonus("health", ROGUE, 50) == 500
        assert crud.level_resource_bonus("mana", MAGE, 50) == 750
        assert crud.level_resource_bonus("stamina", MAGE, 50) == 500

    def test_level_1_already_gives_bonus(self):
        assert crud.level_resource_bonus("health", WARRIOR, 1) == 15
        assert crud.level_resource_bonus("stamina", WARRIOR, 1) == 10

    @pytest.mark.parametrize("cls", [None, 0, 4, 99, -1, "1"])
    @pytest.mark.parametrize("resource", RESOURCES)
    def test_unknown_class_is_zero(self, cls, resource):
        assert crud.level_resource_bonus(resource, cls, 30) == 0

    @pytest.mark.parametrize("level", [None, 0, -5])
    @pytest.mark.parametrize("cls", [WARRIOR, ROGUE, MAGE])
    def test_missing_or_nonpositive_level_is_zero(self, level, cls):
        for resource in RESOURCES:
            assert crud.level_resource_bonus(resource, cls, level) == 0

    def test_unknown_resource_is_zero(self):
        assert crud.level_resource_bonus("strength", WARRIOR, 10) == 0

    def test_resource_max_defaults_unchanged(self):
        for resource in RESOURCES:
            for value in (0, 10, 99, 100, 150, 250):
                assert crud.resource_max(resource, value) == expected_max(resource, value)

    @pytest.mark.parametrize("cls", [WARRIOR, ROGUE, MAGE])
    @pytest.mark.parametrize("value", [0, 40, 100, 180, 200, 1000])
    def test_resource_max_with_level(self, cls, value):
        for resource in RESOURCES:
            assert crud.resource_max(resource, value, 23, cls) == expected_max(resource, value, 23, cls)

    def test_bonus_bypasses_the_stat_cap(self):
        # Past the soft/hard caps the stat part is diminished (x0.5 / x0.25);
        # the level part is never run through eff() and adds in full.
        for value in (50, 150, 200, 1000):
            capped = crud.resource_max("health", value)
            assert capped == expected_max("health", value)
            assert crud.resource_max("health", value, 50, WARRIOR) == capped + 750
        # the stat at 1000 is worth far less than 1000 points at full rate
        assert crud.resource_max("health", 1000) < BASE_HEALTH + HEALTH_MULTIPLIER * 1000


# ===========================================================================
# 2. Creation
# ===========================================================================

class TestCreate:

    def test_body_level_and_class(self, client, db):
        add_character(db, CID)  # row exists but its level/class are NULL
        _create(client, level=1, id_class=WARRIOR)
        attr = _reload(db)
        exp = _expected_maxes(1, WARRIOR)
        assert _maxes(attr) == exp
        assert attr.max_health == expected_max("health", 40) + 15
        assert attr.max_mana == expected_max("mana", 25) + 10
        # fresh row: current == max
        assert _currents(attr) == {f"current_{r}": exp[f"max_{r}"] for r in RESOURCES}

    def test_response_carries_bonus(self, client, db):
        body = _create(client, level=50, id_class=MAGE)
        assert body["max_mana"] == expected_max("mana", 25) + 750
        assert body["max_health"] == expected_max("health", 40) + 500
        assert body["current_mana"] == body["max_mana"]

    def test_body_wins_over_db(self, client, db):
        add_character(db, CID, level=9, id_class=MAGE)
        _create(client, level=2, id_class=ROGUE)
        assert _maxes(_reload(db)) == _expected_maxes(2, ROGUE)

    def test_partial_body_level_class_from_db(self, client, db):
        add_character(db, CID, level=9, id_class=ROGUE)
        _create(client, level=3)
        assert _maxes(_reload(db)) == _expected_maxes(3, ROGUE)

    def test_partial_body_class_level_from_db(self, client, db):
        add_character(db, CID, level=6, id_class=ROGUE)
        _create(client, id_class=WARRIOR)
        assert _maxes(_reload(db)) == _expected_maxes(6, WARRIOR)

    def test_db_fallback(self, client, db):
        add_character(db, CID, level=4, id_class=MAGE)
        _create(client)
        attr = _reload(db)
        assert attr.max_mana == expected_max("mana", 25) + 60
        assert _maxes(attr) == _expected_maxes(4, MAGE)

    def test_no_row_no_body_no_bonus(self, client, db):
        _create(client)
        assert _maxes(_reload(db)) == _expected_maxes(None, None)

    def test_db_row_with_null_level(self, client, db):
        add_character(db, CID, level=None, id_class=WARRIOR)
        _create(client)
        assert _maxes(_reload(db)) == _expected_maxes(None, None)

    def test_unknown_class_in_body(self, client, db):
        _create(client, level=10, id_class=77)
        assert _maxes(_reload(db)) == _expected_maxes(None, None)

    def test_mob_row(self, client, db):
        add_character(db, CID, is_npc=True)
        _create(client, level=10, id_class=WARRIOR)
        attr = _reload(db)
        assert attr.max_health == expected_max("health", 40) + 150
        assert _maxes(attr) == _expected_maxes(10, WARRIOR)

    def test_create_requires_internal_token(self, client, db):
        body = dict(STATS, character_id=CID, level=5, id_class=1)
        assert client.post("/attributes/", json=body).status_code == 401
        assert db.query(models.CharacterAttributes).count() == 0


# ===========================================================================
# 3. POST /attributes/internal/{id}/sync-level
# ===========================================================================

def _seed(client, db, level, cls, is_npc=False, character_id=CID):
    """Player row in `characters` + attributes created through the endpoint."""
    add_character(db, character_id, is_npc=is_npc, level=level, id_class=cls)
    _create(client, character_id=character_id)
    attr = _reload(db, character_id)
    assert _maxes(attr) == _expected_maxes(level, cls)
    return attr


class TestSyncLevelAuth:

    def test_missing_token_401(self, client, db):
        _seed(client, db, 3, WARRIOR)
        _set_char(db, level=10, id_class=WARRIOR)
        before = _maxes(_reload(db))
        assert _sync(client, headers={}).status_code == 401
        assert _maxes(_reload(db)) == before

    def test_wrong_token_401(self, client, db):
        _seed(client, db, 3, WARRIOR)
        _set_char(db, level=10, id_class=WARRIOR)
        before = _maxes(_reload(db))
        assert _sync(client, headers={"X-Internal-Token": "nope"}).status_code == 401
        assert _maxes(_reload(db)) == before

    def test_unknown_id_404(self, client, db):
        resp = _sync(client, character_id=987654)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Атрибуты персонажа не найдены"


class TestSyncLevel:

    def test_level_up_raises_max_and_current_by_diff(self, client, db):
        _seed(client, db, 3, WARRIOR)
        _set_attr(db, current_health=50, current_mana=0, current_energy=20, current_stamina=5)
        _set_char(db, level=5, id_class=WARRIOR)

        resp = _sync(client)
        assert resp.status_code == 200, resp.text
        attr = _reload(db)
        exp = _expected_maxes(5, WARRIOR)
        assert _maxes(attr) == exp
        assert attr.max_health == expected_max("health", 40) + 75
        assert attr.current_health == 50 + 30
        assert attr.current_mana == 0 + 20
        assert attr.current_energy == 20 + 20
        assert attr.current_stamina == 5 + 20
        assert resp.json() == dict(character_id=CID, level=5, id_class=WARRIOR, **exp)

    def test_idempotent(self, client, db):
        _seed(client, db, 3, ROGUE)
        _set_attr(db, current_energy=10)
        _set_char(db, level=8, id_class=ROGUE)
        assert _sync(client).status_code == 200
        first = _reload(db)
        snap = (_maxes(first), _currents(first))
        assert first.current_energy == 10 + 5 * 15
        for _ in range(3):
            assert _sync(client).status_code == 200
            again = _reload(db)
            assert (_maxes(again), _currents(again)) == snap

    def test_no_change_is_noop(self, client, db):
        attr = _seed(client, db, 4, MAGE)
        _set_attr(db, current_mana=3)
        before = (_maxes(_reload(db)), _currents(_reload(db)))
        assert _sync(client).status_code == 200
        after = _reload(db)
        assert (_maxes(after), _currents(after)) == before
        assert attr.character_id == CID

    def test_level_down_clamps_current(self, client, db):
        _seed(client, db, 10, WARRIOR)  # current == max (full)
        _set_attr(db, current_mana=5)   # well below the new max: stays
        _set_char(db, level=2, id_class=WARRIOR)

        assert _sync(client).status_code == 200
        attr = _reload(db)
        exp = _expected_maxes(2, WARRIOR)
        assert _maxes(attr) == exp
        assert attr.current_health == exp["max_health"]   # clamped
        assert attr.current_energy == exp["max_energy"]   # clamped
        assert attr.current_stamina == exp["max_stamina"]  # clamped
        assert attr.current_mana == 5                      # not lowered by diff

    def test_level_down_partial_clamp(self, client, db):
        _seed(client, db, 10, WARRIOR)
        new_max_hp = expected_max("health", 40) + 15 * 2
        _set_attr(db, current_health=new_max_hp - 7)
        _set_char(db, level=2, id_class=WARRIOR)
        assert _sync(client).status_code == 200
        # current below the new max is kept as is (clamp, not "minus diff")
        assert _reload(db).current_health == new_max_hp - 7

    def test_level_down_to_zero_current_stays_zero(self, client, db):
        _seed(client, db, 10, MAGE)
        _set_attr(db, current_health=0, current_mana=0, current_energy=0, current_stamina=0)
        _set_char(db, level=1, id_class=MAGE)
        assert _sync(client).status_code == 200
        assert _currents(_reload(db)) == {f: 0 for f in CUR_FIELDS}

    def test_multi_level_jump(self, client, db):
        _seed(client, db, 1, MAGE)
        _set_attr(db, current_mana=1)
        _set_char(db, level=50, id_class=MAGE)
        assert _sync(client).status_code == 200
        attr = _reload(db)
        assert _maxes(attr) == _expected_maxes(50, MAGE)
        assert attr.max_mana == expected_max("mana", 25) + 750
        assert attr.current_mana == 1 + 49 * 15

    def test_class_change(self, client, db):
        _seed(client, db, 20, WARRIOR)  # full
        _set_attr(db, current_mana=40)
        _set_char(db, level=20, id_class=MAGE)
        assert _sync(client).status_code == 200
        attr = _reload(db)
        exp = _expected_maxes(20, MAGE)
        assert _maxes(attr) == exp
        assert exp["max_health"] == _expected_maxes(20, WARRIOR)["max_health"] - 100
        assert attr.current_health == exp["max_health"]   # clamped down
        assert attr.current_mana == 40 + 100              # grew by diff
        assert attr.current_energy == exp["max_energy"]   # unchanged, still full

    def test_unknown_class_removes_bonus(self, client, db):
        _seed(client, db, 5, ROGUE)
        _set_char(db, level=5, id_class=99)
        resp = _sync(client)
        assert resp.status_code == 200
        assert resp.json()["id_class"] == 99
        assert _maxes(_reload(db)) == _expected_maxes(None, None)

    def test_missing_characters_row_no_bonus(self, client, db):
        _create(client, level=5, id_class=WARRIOR)  # no `characters` row at all
        resp = _sync(client)
        assert resp.status_code == 200
        assert resp.json()["level"] is None and resp.json()["id_class"] is None
        assert _maxes(_reload(db)) == _expected_maxes(None, None)

    def test_heals_corrupted_max(self, client, db):
        _seed(client, db, 7, ROGUE)
        _set_attr(db, max_energy=1, current_energy=1)
        assert _sync(client).status_code == 200
        attr = _reload(db)
        assert attr.max_energy == _expected_maxes(7, ROGUE)["max_energy"]
        assert attr.current_energy == attr.max_energy  # 1 + diff

    def test_mob_row(self, client, db):
        _seed(client, db, 3, ROGUE, is_npc=True)
        _set_char(db, level=12, id_class=ROGUE)
        assert _sync(client).status_code == 200
        assert _maxes(_reload(db)) == _expected_maxes(12, ROGUE)

    def test_settle_regen_runs_before_the_change(self, client, db):
        _seed(client, db, 3, WARRIOR)
        _set_char(db, level=6, id_class=WARRIOR)
        old_max = _reload(db).max_health
        calls = []
        real_settle = regen.settle_regen
        real_sync = crud.sync_level_resources

        def spy_settle(session, attr, *a, **kw):
            calls.append(("settle", attr.max_health))
            return real_settle(session, attr, *a, **kw)

        def spy_sync(attr, level, class_id):
            calls.append(("sync", attr.max_health))
            return real_sync(attr, level, class_id)

        with patch.object(main.regen, "settle_regen", side_effect=spy_settle), \
                patch.object(main.crud, "sync_level_resources", side_effect=spy_sync):
            assert _sync(client).status_code == 200
        assert calls == [("settle", old_max), ("sync", old_max)]
        assert _reload(db).max_health == old_max + 45

    def test_settle_credits_regen_against_old_max(self, client, db):
        _seed(client, db, 2, WARRIOR)
        _set_attr(db, current_health=10,
                  regen_anchor_at=datetime.utcnow() - timedelta(hours=1))
        _set_char(db, level=4, id_class=WARRIOR)
        assert _sync(client).status_code == 200
        attr = _reload(db)
        # regen was credited (anchor moved) and the +30 growth landed on top
        assert attr.max_health == _expected_maxes(4, WARRIOR)["max_health"]
        assert attr.current_health >= 10 + 30
        assert attr.current_health <= attr.max_health


# ===========================================================================
# 4. apply_attribute_modifiers unaffected by the level term
# ===========================================================================

class TestModifiersWithLevelBonus:

    def test_upgrade_across_100_keeps_absolute_max(self, client, db):
        _seed(client, db, 20, WARRIOR)
        attr = _reload(db)
        crud.apply_attribute_modifiers(attr, {"health": 95, "mana": 180})
        db.commit()
        attr = _reload(db)
        assert attr.health == 135 and attr.mana == 205
        assert attr.max_health == expected_max("health", 135, 20, WARRIOR)
        assert attr.max_mana == expected_max("mana", 205, 20, WARRIOR)
        assert attr.max_energy == expected_max("energy", 15, 20, WARRIOR)

    def test_equip_unequip_exactly_reversible_http(self, client, db):
        _seed(client, db, 33, MAGE)
        _set_attr(db, current_health=77, current_mana=12)
        before = _reload(db)
        snap = (_maxes(before), _currents(before),
                {r: getattr(before, r) for r in RESOURCES})
        gear = {"health": 120, "mana": 90, "energy": 210, "stamina": 3, "strength": 50}
        r = client.post(f"/attributes/{CID}/apply_modifiers", json=gear, headers=INTERNAL_HEADERS)
        assert r.status_code == 200, r.text
        mid = _reload(db)
        assert mid.max_mana == expected_max("mana", 25 + 90, 33, MAGE)
        assert mid.max_energy == expected_max("energy", 15 + 210, 33, MAGE)
        undo = {k: -v for k, v in gear.items()}
        r = client.post(f"/attributes/{CID}/apply_modifiers", json=undo, headers=INTERNAL_HEADERS)
        assert r.status_code == 200, r.text
        after = _reload(db)
        assert (_maxes(after), _currents(after),
                {r: getattr(after, r) for r in RESOURCES}) == snap

    def test_upgrade_then_rebuild_matches(self, client, db):
        _seed(client, db, 15, ROGUE)
        _set_attr(db, regen_anchor_at=None)
        attr = _reload(db)
        crud.apply_attribute_modifiers(attr, {"energy": 140, "health": 7})
        db.commit()
        incremental = _maxes(_reload(db))
        attr = _reload(db)
        crud.rebuild_derived_stats(db, attr, {})
        db.commit()
        assert _maxes(_reload(db)) == incremental


# ===========================================================================
# 5. rebuild_derived_stats / recalculate / recalculate_all
# ===========================================================================

def _legacy_row(db, character_id, level, cls, is_npc=False, **stats):
    """A pre-FEAT-196 row: maxes without the level term, current full."""
    add_character(db, character_id, is_npc=is_npc, level=level, id_class=cls)
    values = dict(STATS, **stats)
    attr = models.CharacterAttributes(character_id=character_id, **values)
    for r in RESOURCES:
        setattr(attr, f"current_{r}", None)
    crud.compute_derived_stats(attr)  # no level/class -> legacy maxes
    db.add(attr)
    db.commit()
    return _reload(db, character_id)


class TestRebuild:

    def test_rebuild_adds_bonus_without_top_up(self, db):
        legacy = _legacy_row(db, CID, 12, ROGUE)
        old_cur = _currents(legacy)
        assert _maxes(legacy) == _expected_maxes(None, None, dict(STATS))
        crud.rebuild_derived_stats(db, legacy, {})
        db.commit()
        attr = _reload(db)
        assert _maxes(attr) == _expected_maxes(12, ROGUE)
        assert attr.max_energy == expected_max("energy", 15) + 180
        assert _currents(attr) == old_cur  # rebuild never tops up

    def test_rebuild_idempotent(self, db):
        _legacy_row(db, CID, 9, WARRIOR)
        for _ in range(3):
            attr = _reload(db)
            crud.rebuild_derived_stats(db, attr, {})
            db.commit()
        attr = _reload(db)
        assert _maxes(attr) == _expected_maxes(9, WARRIOR)

    def test_rebuild_clamps_current_on_lower_level(self, db):
        add_character(db, CID, level=30, id_class=WARRIOR)
        attr = models.CharacterAttributes(character_id=CID, **STATS)
        for r in RESOURCES:
            setattr(attr, f"current_{r}", None)
        crud.compute_derived_stats(attr, class_id=WARRIOR, level=30)
        db.add(attr)
        db.commit()
        _set_char(db, level=1, id_class=WARRIOR)
        attr = _reload(db)
        crud.rebuild_derived_stats(db, attr, {})
        db.commit()
        attr = _reload(db)
        exp = _expected_maxes(1, WARRIOR)
        assert _maxes(attr) == exp
        assert _currents(attr) == {f"current_{r}": exp[f"max_{r}"] for r in RESOURCES}

    def test_rebuild_equals_create_plus_sync(self, client, db):
        _seed(client, db, 1, MAGE)
        _set_char(db, level=17, id_class=MAGE)
        assert _sync(client).status_code == 200
        via_sync = _maxes(_reload(db))
        attr = _reload(db)
        crud.rebuild_derived_stats(db, attr, {})
        db.commit()
        assert _maxes(_reload(db)) == via_sync == _expected_maxes(17, MAGE)

    def test_rebuild_missing_characters_row_no_bonus(self, db):
        attr = models.CharacterAttributes(character_id=CID, **STATS)
        for r in RESOURCES:
            setattr(attr, f"current_{r}", None)
        crud.compute_derived_stats(attr, class_id=WARRIOR, level=10)
        db.add(attr)
        db.commit()
        attr = _reload(db)
        crud.rebuild_derived_stats(db, attr, {})
        db.commit()
        assert _maxes(_reload(db)) == _expected_maxes(None, None)

    def test_get_level_and_class_reads_real_columns(self, db):
        add_character(db, CID, level=13, id_class=ROGUE)
        assert crud.get_level_and_class(db, CID) == (13, ROGUE)
        assert crud.get_level_and_class(db, 999) == (None, None)

    def test_get_level_and_class_sql_error_propagates(self, db):
        with _test_engine.begin() as conn:
            conn.execute(text("DROP TABLE characters"))
        with pytest.raises(OperationalError):
            crud.get_level_and_class(db, CID)
        db.rollback()

    def test_recalculate_single_includes_bonus(self, client, db):
        _legacy_row(db, CID, 8, MAGE)
        resp = client.post(f"/attributes/{CID}/recalculate")
        assert resp.status_code == 200, resp.text
        assert _maxes(_reload(db)) == _expected_maxes(8, MAGE)

    def test_recalculate_all_players_npcs_mobs(self, client, db):
        _legacy_row(db, 1, 5, WARRIOR)
        _legacy_row(db, 2, 11, ROGUE, is_npc=True)   # NPC / mob row
        _legacy_row(db, 3, 40, MAGE, is_npc=True)    # mob row
        _legacy_row(db, 4, None, None)               # no level/class -> no bonus
        _legacy_row(db, 5, 3, 42)                    # unknown class -> no bonus

        body = client.post("/attributes/admin/recalculate_all").json()
        assert body["count"] == 5 and body["skipped"] == []
        expected = {
            1: _expected_maxes(5, WARRIOR),
            2: _expected_maxes(11, ROGUE),
            3: _expected_maxes(40, MAGE),
            4: _expected_maxes(None, None),
            5: _expected_maxes(None, None),
        }
        for cid, exp in expected.items():
            assert _maxes(_reload(db, cid)) == exp, cid
        assert _reload(db, 3).max_mana == expected_max("mana", 25) + 600

        snap = {cid: (_maxes(_reload(db, cid)), _currents(_reload(db, cid))) for cid in expected}
        body = client.post("/attributes/admin/recalculate_all").json()
        assert body["skipped"] == []
        for cid in expected:
            assert (_maxes(_reload(db, cid)), _currents(_reload(db, cid))) == snap[cid]

    def test_recalculate_all_sql_error_skips_batch(self, client, db):
        legacy = _legacy_row(db, CID, 10, WARRIOR)
        before = _maxes(legacy)
        with _test_engine.begin() as conn:
            conn.execute(text("DROP TABLE characters"))
        body = client.post("/attributes/admin/recalculate_all").json()
        assert body["skipped"] == [CID] and body["count"] == 0
        assert _maxes(_reload(db)) == before  # nothing written, not "rebuilt without bonus"
