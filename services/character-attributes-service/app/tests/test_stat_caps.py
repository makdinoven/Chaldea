"""
FEAT-195 — soft/hard stat caps in character-attributes-service.

Covers:
  * stat_caps.effective_stat / effective_delta: breakpoints, floats, negatives,
    garbage input, monotonicity, exactness (multiples of 0.25), telescoping;
  * byte-identical copies of stat_caps.py in battle-service / dungeon-service;
  * crud.apply_attribute_modifiers: per-primary derived deltas across 100/200,
    resources with floor(m * eff), current clamping, flats, unknown keys;
  * path independence: equip -> upgrade -> unequip, random equip/unequip
    sequences in any order, incremental == absolute formula;
  * POST /attributes/{id}/upgrade across 100 and 200;
  * POST /attributes/{id}/apply_modifiers (gear now propagates derived stats,
    exact reversal, internal token, unknown/injection keys ignored);
  * perk grant/revoke across a threshold;
  * satiety apply/expiry moves derived stats and reverts them exactly;
  * crud.rebuild_derived_stats: == incremental build with gear + perk + food,
    idempotent, keeps primaries/damage/crit damage/vul_*, no top-up;
  * POST /attributes/{id}/recalculate (gear-aware, 502 nothing written),
    POST /attributes/admin/recalculate_all (batches, `skipped`), RBAC 403,
    main._fetch_equipment_modifiers (URL, token header, failures -> None).
"""

import hashlib
import math
import os
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
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
import crud  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
import regen  # noqa: E402
import stat_caps  # noqa: E402
from auth_http import UserRead, get_current_user_via_http  # noqa: E402
from constants import (  # noqa: E402
    ALL_RESISTANCE_FIELDS,
    BASE_CRIT,
    BASE_CRIT_DMG,
    BASE_DODGE,
    BASE_ENERGY,
    BASE_HEALTH,
    BASE_MANA,
    BASE_STAMINA,
    MAGICAL_RESISTANCE_FIELDS,
    PHYSICAL_RESISTANCE_FIELDS,
)
from fastapi.testclient import TestClient  # noqa: E402
from main import app, get_db  # noqa: E402
from stat_caps import effective_delta, effective_stat  # noqa: E402
from tests.regen_shared_tables import (  # noqa: E402
    add_character,
    create_shared_tables,
    drop_shared_tables,
    skip_or_fail_missing,
)

TOKEN = "test-internal-token"
INTERNAL_HEADERS = {"X-Internal-Token": TOKEN}
CID = 31

PRIMARIES = ("strength", "agility", "intelligence", "endurance", "charisma", "luck")
RESOURCES = ("health", "mana", "energy", "stamina")
DERIVED_FLOAT_FIELDS = tuple(ALL_RESISTANCE_FIELDS) + ("dodge", "critical_hit_chance")
MAX_FIELDS = tuple(f"max_{r}" for r in RESOURCES)
UNTOUCHED_BY_REBUILD = (
    PRIMARIES + RESOURCES
    + ("damage", "critical_damage", "vul_effects", "vul_physical", "vul_fire", "vul_damning")
)

_ADMIN = UserRead(id=1, username="admin", role="admin",
                  permissions=["characters:read", "characters:update"])
_EDITOR_NO_UPDATE = UserRead(id=2, username="editor", role="editor",
                             permissions=["characters:read"])
_PLAYER = UserRead(id=10, username="player", role="user", permissions=[])


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
    """Fresh session per request (endpoints use `with db.begin()`)."""
    def _override_get_db():
        s = _TestSessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user_via_http] = lambda: _ADMIN
    yield TestClient(app)
    app.dependency_overrides.clear()


def _attr_values(**primaries):
    """Column values for a row whose derived stats follow the FEAT-195 formula."""
    values = dict(
        strength=0, agility=0, intelligence=0, endurance=0, charisma=0, luck=0,
        health=0, mana=0, energy=0, stamina=0,
        current_health=0, current_mana=0, current_energy=0, current_stamina=0,
        max_health=0, max_mana=0, max_energy=0, max_stamina=0,
        damage=0, dodge=0.0, critical_hit_chance=0.0, critical_damage=BASE_CRIT_DMG,
    )
    for field in ALL_RESISTANCE_FIELDS:
        values[field] = 0.0
    values.update(primaries)
    return values


def _fresh_attr(character_id=CID, current_full=True, **primaries):
    """Transient row with derived stats from the absolute (creation) formula."""
    attr = models.CharacterAttributes(character_id=character_id, **_attr_values(**primaries))
    for r in RESOURCES:
        setattr(attr, f"current_{r}", 10 ** 6 if current_full else 0)
    for f in ("vul_effects", "vul_physical", "vul_catting", "vul_crushing", "vul_piercing",
              "vul_magic", "vul_fire", "vul_ice", "vul_watering", "vul_electricity",
              "vul_sainting", "vul_wind", "vul_damning"):
        setattr(attr, f, 0.0)
    crud.compute_derived_stats(attr)  # current is clamped to max
    return attr


def _seed(db, character_id=CID, **primaries):
    """Persisted row (character exists, regen anchor now) with formula-correct derived."""
    add_character(db, character_id)
    attr = _fresh_attr(character_id, **primaries)
    attr.regen_anchor_at = datetime.utcnow().replace(microsecond=0)
    db.add(attr)
    db.commit()
    return attr


def _reload(db, character_id=CID):
    db.expire_all()
    return db.query(models.CharacterAttributes).filter_by(character_id=character_id).one()


def _snapshot(attr):
    fields = PRIMARIES + RESOURCES + DERIVED_FLOAT_FIELDS + MAX_FIELDS + tuple(
        f"current_{r}" for r in RESOURCES) + ("damage", "critical_damage", "vul_fire")
    return {f: getattr(attr, f) for f in fields}


def _assert_same(actual: dict, expected: dict):
    for field, value in expected.items():
        if field in DERIVED_FLOAT_FIELDS or isinstance(value, float):
            assert actual[field] == pytest.approx(value, abs=1e-9), field
        else:
            assert actual[field] == value, field


def _expected_derived(**totals):
    """Absolute FEAT-195 formula, written out independently of crud."""
    g = lambda k: effective_stat(totals.get(k, 0))  # noqa: E731
    out = {}
    for f in PHYSICAL_RESISTANCE_FIELDS:
        out[f] = 0.1 * g("strength")
    for f in MAGICAL_RESISTANCE_FIELDS:
        out[f] = 0.1 * g("intelligence")
    out["dodge"] = BASE_DODGE + 0.1 * g("agility") + 0.1 * g("luck")
    out["critical_hit_chance"] = BASE_CRIT + 0.1 * g("luck")
    out["res_effects"] = 0.2 * g("endurance") + 0.1 * g("luck")
    out["max_health"] = BASE_HEALTH + math.floor(10 * g("health"))
    out["max_mana"] = BASE_MANA + math.floor(10 * g("mana"))
    out["max_energy"] = BASE_ENERGY + math.floor(5 * g("energy"))
    out["max_stamina"] = BASE_STAMINA + math.floor(5 * g("stamina"))
    return out


# ===========================================================================
# 1. stat_caps
# ===========================================================================

class TestEffectiveStat:

    @pytest.mark.parametrize("value, expected", [
        (0, 0.0), (1, 1.0), (99, 99.0), (100, 100.0), (101, 100.5), (150, 125.0),
        (199, 149.5), (200, 150.0), (201, 150.25), (250, 162.5), (530, 232.5),
        (10000, 2600.0), (-10, -10.0), (-250, -250.0),
        (99.5, 99.5), (100.4, 100.2), (200.8, 150.2), (0.25, 0.25),
    ])
    def test_breakpoints_and_floats(self, value, expected):
        assert effective_stat(value) == pytest.approx(expected, abs=1e-12)

    @pytest.mark.parametrize("garbage", [None, True, False, "abc", [], {}, object(), float("nan")])
    def test_garbage_is_zero(self, garbage):
        assert effective_stat(garbage) == 0.0

    def test_numeric_strings_and_decimals(self):
        assert effective_stat("150") == 125.0
        assert effective_stat(Decimal("250")) == 162.5

    def test_constants(self):
        assert (stat_caps.SOFT_CAP, stat_caps.HARD_CAP) == (100, 200)
        assert (stat_caps.SOFT_RATE, stat_caps.HARD_RATE) == (0.5, 0.25)

    def test_continuous_at_thresholds(self):
        for t in (stat_caps.SOFT_CAP, stat_caps.HARD_CAP):
            assert effective_stat(t - 1e-9) == pytest.approx(effective_stat(t), abs=1e-6)
            assert effective_stat(t + 1e-9) == pytest.approx(effective_stat(t), abs=1e-6)

    def test_monotonic_and_marginal_rate(self):
        prev = effective_stat(-50)
        for x in range(-49, 1001):
            cur = effective_stat(x)
            assert cur > prev
            rate = cur - prev
            if x <= 100:
                assert rate == 1.0
            elif x <= 200:
                assert rate == 0.5
            else:
                assert rate == 0.25
            prev = cur

    def test_integers_are_exact_quarters(self):
        """eff of an integer is a multiple of 0.25 -> m*eff is exact for m in {5, 10}."""
        for x in range(-20, 1200):
            e = effective_stat(x)
            assert (e * 4).is_integer()
            assert (5 * e * 4).is_integer() and (10 * e * 4).is_integer()

    @pytest.mark.parametrize("old, new, expected", [
        (95, 105, 7.5), (195, 205, 3.75), (180, 230, 17.5), (80, 130, 35.0),
        (0, 530, 232.5), (250, 250, 0.0), (-10, 10, 20.0),
    ])
    def test_effective_delta_values(self, old, new, expected):
        assert effective_delta(old, new) == pytest.approx(expected)
        assert effective_delta(new, old) == pytest.approx(-expected)

    def test_effective_delta_telescopes(self):
        rng = random.Random(195)
        for _ in range(50):
            path = [rng.randint(-50, 600) for _ in range(12)]
            total = sum(effective_delta(a, b) for a, b in zip(path, path[1:]))
            assert total == pytest.approx(effective_delta(path[0], path[-1]), abs=1e-9)


class TestStatCapsCopies:
    """The battle/dungeon copies must stay byte-identical (also checked by
    scripts/check_econ_copies.sh in CI)."""

    @pytest.mark.parametrize("service", ["battle-service", "dungeon-service"])
    def test_copy_identical(self, service):
        here = os.path.join(os.path.dirname(__file__), "..", "stat_caps.py")
        other = os.path.normpath(os.path.join(
            os.path.dirname(__file__), "..", "..", "..", service, "app", "stat_caps.py"))
        if not os.path.exists(other):
            skip_or_fail_missing(other, f"{service} stat_caps.py")
        digest = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()  # noqa: E731
        assert digest(here) == digest(other)


# ===========================================================================
# 2. crud.apply_attribute_modifiers (pure)
# ===========================================================================

class TestApplyAttributeModifiers:

    def test_strength_across_soft_cap(self):
        attr = _fresh_attr(strength=95)
        before = attr.res_physical
        crud.apply_attribute_modifiers(attr, {"strength": 10})
        assert attr.strength == 105
        for f in PHYSICAL_RESISTANCE_FIELDS:
            assert getattr(attr, f) == pytest.approx(before + 0.75)  # 0.1*(102.5-95)
        for f in MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, f) == 0.0

    def test_strength_across_hard_cap(self):
        attr = _fresh_attr(strength=195)
        before = attr.res_piercing
        crud.apply_attribute_modifiers(attr, {"strength": 10})
        assert attr.res_piercing == pytest.approx(before + 0.375)  # 0.1*(151.25-147.5)

    def test_intelligence_moves_all_eight_magical(self):
        attr = _fresh_attr(intelligence=150)
        crud.apply_attribute_modifiers(attr, {"intelligence": 100})  # 150 -> 250
        for f in MAGICAL_RESISTANCE_FIELDS:
            assert getattr(attr, f) == pytest.approx(16.25)  # 0.1*eff(250)

    def test_agility_and_endurance(self):
        attr = _fresh_attr(agility=190, endurance=100)
        crud.apply_attribute_modifiers(attr, {"agility": 20, "endurance": 100})
        assert attr.dodge == pytest.approx(BASE_DODGE + 0.1 * 152.5)
        assert attr.res_effects == pytest.approx(0.2 * 150)

    def test_luck_moves_dodge_crit_res_effects(self):
        attr = _fresh_attr(luck=250)
        d, c, r = attr.dodge, attr.critical_hit_chance, attr.res_effects
        crud.apply_attribute_modifiers(attr, {"luck": 50})  # 162.5 -> 175
        assert attr.dodge == pytest.approx(d + 1.25)
        assert attr.critical_hit_chance == pytest.approx(c + 1.25)
        assert attr.res_effects == pytest.approx(r + 1.25)

    def test_charisma_has_no_stored_derived(self):
        attr = _fresh_attr(charisma=90)
        before = _snapshot(attr)
        crud.apply_attribute_modifiers(attr, {"charisma": 500})
        after = _snapshot(attr)
        assert after.pop("charisma") == 590
        before.pop("charisma")
        _assert_same(after, before)

    def test_negative_stats_are_linear(self):
        attr = _fresh_attr(strength=5)
        crud.apply_attribute_modifiers(attr, {"strength": -10})
        assert attr.strength == -5
        assert attr.res_physical == pytest.approx(-0.5)
        crud.apply_attribute_modifiers(attr, {"strength": 10})
        assert attr.res_physical == pytest.approx(0.5)

    @pytest.mark.parametrize("resource, start, steps, max_deltas", [
        ("energy", 100, [1, 1, 1, 1], [2, 3, 2, 3]),        # 5*eff: 500, 502.5, 505, 507.5, 510
        ("stamina", 200, [1, 1, 1, 1], [1, 1, 1, 2]),       # 750, 751.25, 752.5, 753.75, 755
        ("health", 99, [2], [15]),                          # 990 -> 1005
        ("mana", 199, [2], [7]),                            # 10*149.5=1495 -> 10*150.25=1502.5 -> 1502
    ])
    def test_resources_floor_steps(self, resource, start, steps, max_deltas):
        attr = _fresh_attr(**{resource: start})
        for step, expected in zip(steps, max_deltas):
            before_max = getattr(attr, f"max_{resource}")
            before_cur = getattr(attr, f"current_{resource}")
            crud.apply_attribute_modifiers(attr, {resource: step})
            assert getattr(attr, f"max_{resource}") - before_max == expected
            assert getattr(attr, f"current_{resource}") - before_cur == expected
        # The incremental max equals the absolute formula of the total.
        total = start + sum(steps)
        assert getattr(attr, f"max_{resource}") == crud.resource_max(resource, total)

    def test_resource_max_floor_reverses_exactly(self):
        attr = _fresh_attr(energy=100, stamina=201)
        start = _snapshot(attr)
        for _ in range(3):
            crud.apply_attribute_modifiers(attr, {"energy": 1, "stamina": 1})
        for _ in range(3):
            crud.apply_attribute_modifiers(attr, {"energy": -1, "stamina": -1})
        _assert_same(_snapshot(attr), start)

    def test_current_resource_clamped_to_zero_and_max(self):
        attr = _fresh_attr(health=150)
        attr.current_health = 30
        crud.apply_attribute_modifiers(attr, {"health": -100})  # max -500 (eff 125 -> 50)
        assert attr.health == 50
        assert attr.max_health == BASE_HEALTH + 500
        assert attr.current_health == 0
        attr.current_health = attr.max_health + 999  # stale over-max value
        crud.apply_attribute_modifiers(attr, {"health": 1})
        assert attr.current_health == attr.max_health

    def test_resource_value_never_negative(self):
        attr = _fresh_attr(mana=5)
        crud.apply_attribute_modifiers(attr, {"mana": -50})
        assert attr.mana == 0
        assert attr.max_mana == BASE_MANA

    def test_flats_are_plain_adds(self):
        attr = _fresh_attr(strength=250)
        crud.apply_attribute_modifiers(attr, {
            "res_fire": 4.0, "dodge": 1.5, "critical_hit_chance": 2.0,
            "damage": 7, "critical_damage": 10, "vul_fire": 3.0,
        })
        assert attr.res_fire == pytest.approx(4.0)
        assert attr.dodge == pytest.approx(BASE_DODGE + 1.5)
        assert attr.critical_hit_chance == pytest.approx(BASE_CRIT + 2.0)
        assert attr.damage == 7  # NOT eff(strength): damage is a pure bonus
        assert attr.critical_damage == BASE_CRIT_DMG + 10
        assert attr.vul_fire == pytest.approx(3.0)

    def test_unknown_and_injection_keys_ignored(self):
        attr = _fresh_attr(strength=50)
        before = _snapshot(attr)
        crud.apply_attribute_modifiers(attr, {
            "current_health": 999, "max_health": 999, "id": 5, "character_id": 99,
            "strength; DROP TABLE character_attributes; --": 1, "experience": 10 ** 6,
        })
        _assert_same(_snapshot(attr), before)
        assert attr.character_id == CID

    @pytest.mark.parametrize("empty", [None, {}, {"strength": 0, "health": 0}])
    def test_empty_is_noop(self, empty):
        attr = _fresh_attr(strength=120, health=120)
        before = _snapshot(attr)
        crud.apply_attribute_modifiers(attr, empty)
        _assert_same(_snapshot(attr), before)


# ===========================================================================
# 3. Path independence (the eff-delta invariant)
# ===========================================================================

class TestPathIndependence:

    def test_worked_example_equip_upgrade_unequip(self):
        """Spec 3.2: str 80, equip +50 (+3.5), upgrade +20 (+1.0), unequip -50 (-2.5)."""
        attr = _fresh_attr(strength=80)
        start = attr.res_physical
        crud.apply_attribute_modifiers(attr, {"strength": 50})
        assert attr.res_physical - start == pytest.approx(3.5)
        crud.apply_attribute_modifiers(attr, {"strength": 20})
        assert attr.res_physical - start == pytest.approx(4.5)
        crud.apply_attribute_modifiers(attr, {"strength": -50})
        assert attr.strength == 100
        assert attr.res_physical - start == pytest.approx(2.0)
        assert attr.res_physical == pytest.approx(0.1 * effective_stat(100))

    def test_order_within_and_between_dicts_is_irrelevant(self):
        a = _fresh_attr(strength=150, luck=90, health=180)
        b = _fresh_attr(strength=150, luck=90, health=180)
        m1 = {"strength": 70, "luck": 30, "res_fire": 1.0}
        m2 = {"strength": -40, "health": 40, "dodge": 0.5}
        crud.apply_attribute_modifiers(a, m1)
        crud.apply_attribute_modifiers(a, m2)
        crud.apply_attribute_modifiers(b, m2)
        crud.apply_attribute_modifiers(b, m1)
        _assert_same(_snapshot(a), _snapshot(b))

    @pytest.mark.parametrize("seed", range(8))
    def test_random_equip_unequip_in_any_order_restores_start(self, seed):
        rng = random.Random(seed)
        start_stats = {k: rng.randint(0, 260) for k in PRIMARIES + RESOURCES}
        attr = _fresh_attr(**start_stats)
        start = _snapshot(attr)

        items = []
        for _ in range(6):
            keys = rng.sample(PRIMARIES + RESOURCES, 4)
            mods = {k: rng.randint(1, 150) for k in keys}
            mods["res_fire"] = rng.choice([0, 1.5, 2.0])
            items.append(mods)
        for mods in items:  # equip all
            crud.apply_attribute_modifiers(attr, mods)

        # Interleaved "upgrade" (points) that stays.
        crud.apply_attribute_modifiers(attr, {"strength": 37, "energy": 13})

        rng.shuffle(items)
        for mods in items:  # unequip in another order
            crud.apply_attribute_modifiers(attr, {k: -v for k, v in mods.items()})
        crud.apply_attribute_modifiers(attr, {"strength": -37, "energy": -13})

        _assert_same(_snapshot(attr), start)

    @pytest.mark.parametrize("seed", range(5))
    def test_incremental_equals_absolute_formula(self, seed):
        rng = random.Random(1000 + seed)
        totals = {k: rng.randint(0, 120) for k in PRIMARIES + RESOURCES}
        attr = _fresh_attr(**totals)
        for _ in range(10):
            key = rng.choice(PRIMARIES + RESOURCES)
            delta = rng.randint(-60, 200)
            if key in RESOURCES and totals[key] + delta < 0:
                delta = -totals[key]
            totals[key] += delta
            crud.apply_attribute_modifiers(attr, {key: delta})
        for field, value in _expected_derived(**totals).items():
            assert getattr(attr, field) == pytest.approx(value, abs=1e-9), field


# ===========================================================================
# 4. compute_derived_stats (creation) through eff
# ===========================================================================

class TestComputeDerivedStats:

    def test_creation_formula_is_capped(self):
        totals = dict(strength=250, agility=150, intelligence=530, endurance=201,
                      luck=101, health=250, mana=150, energy=201, stamina=101)
        attr = _fresh_attr(**totals)
        for field, value in _expected_derived(**totals).items():
            assert getattr(attr, field) == pytest.approx(value, abs=1e-9), field
        assert attr.res_physical == pytest.approx(16.25)
        assert attr.res_magic == pytest.approx(23.25)
        assert attr.max_health == BASE_HEALTH + 1625
        assert attr.max_energy == BASE_ENERGY + 751   # floor(5 * 150.25)
        assert attr.max_stamina == BASE_STAMINA + 502  # floor(5 * 100.5)
        assert attr.damage == 0

    def test_below_soft_cap_unchanged_from_linear(self):
        attr = _fresh_attr(strength=40, agility=30, luck=20, health=40, energy=33)
        assert attr.res_physical == pytest.approx(4.0)
        assert attr.dodge == pytest.approx(BASE_DODGE + 5.0)
        assert attr.max_health == BASE_HEALTH + 400
        assert attr.max_energy == BASE_ENERGY + 165


# ===========================================================================
# 5. Upgrade endpoint across thresholds
# ===========================================================================

@pytest.fixture()
def upgrade_client(db):
    profile = MagicMock(status_code=200)
    profile.json.return_value = {"stat_points": 1000}
    deduct = MagicMock(status_code=200)
    deduct.json.return_value = {"remaining_points": 0}
    inst = AsyncMock()
    inst.get = AsyncMock(return_value=profile)
    inst.put = AsyncMock(return_value=deduct)

    def _override_get_db():
        s = _TestSessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user_via_http] = lambda: _PLAYER
    with patch("main.verify_character_ownership"), patch("main.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__ = AsyncMock(return_value=inst)
        cls.return_value.__aexit__ = AsyncMock(return_value=False)
        yield TestClient(app)
    app.dependency_overrides.clear()


def _upgrade(client, **points):
    body = {k: 0 for k in PRIMARIES + RESOURCES}
    body.update(points)
    return client.post(f"/attributes/{CID}/upgrade", json=body)


class TestUpgradeAcrossThresholds:

    def test_strength_95_plus_10(self, upgrade_client, db):
        _seed(db, strength=95)
        resp = _upgrade(upgrade_client, strength=10)
        assert resp.status_code == 200, resp.text
        attr = _reload(db)
        assert attr.strength == 105
        assert attr.res_physical == pytest.approx(10.25)

    def test_strength_195_plus_10(self, upgrade_client, db):
        _seed(db, strength=195)
        assert _upgrade(upgrade_client, strength=10).status_code == 200
        assert _reload(db).res_crushing == pytest.approx(15.125)  # 0.1 * eff(205)

    def test_resources_floor_at_101_and_201(self, upgrade_client, db):
        _seed(db, energy=100, stamina=200, health=100, mana=200)
        assert _upgrade(upgrade_client, energy=1, stamina=1, health=1, mana=1).status_code == 200
        attr = _reload(db)
        assert attr.max_energy == BASE_ENERGY + 502     # floor(5 * 100.5)
        assert attr.max_stamina == BASE_STAMINA + 751   # floor(5 * 150.25)
        assert attr.max_health == BASE_HEALTH + 1005
        assert attr.max_mana == BASE_MANA + 1502        # floor(10 * 150.25)
        assert attr.current_energy == attr.max_energy   # moved with max
        assert _upgrade(upgrade_client, energy=1, stamina=1).status_code == 200
        attr = _reload(db)
        assert attr.max_energy == BASE_ENERGY + 505
        assert attr.max_stamina == BASE_STAMINA + 752   # floor(5 * 150.5)

    def test_luck_across_both_caps(self, upgrade_client, db):
        _seed(db, luck=90)
        assert _upgrade(upgrade_client, luck=130).status_code == 200  # 90 -> 220
        attr = _reload(db)
        assert attr.critical_hit_chance == pytest.approx(BASE_CRIT + 15.5)  # 0.1*eff(220)=15.5
        assert attr.dodge == pytest.approx(BASE_DODGE + 15.5)
        assert attr.res_effects == pytest.approx(15.5)


# ===========================================================================
# 6. HTTP apply_modifiers (gear)
# ===========================================================================

GEAR = {"strength": 60, "agility": 15, "intelligence": 120, "endurance": 30,
        "luck": 20, "health": 7, "energy": 3, "res_fire": 3.0, "damage": 12}


class TestApplyModifiersEndpoint:

    def _post(self, client, body, headers=INTERNAL_HEADERS, cid=CID):
        return client.post(f"/attributes/{cid}/apply_modifiers", json=body, headers=headers)

    def test_gear_primaries_propagate_and_unequip_reverts(self, client, db):
        _seed(db, strength=150, agility=95, intelligence=100, endurance=180,
              luck=190, health=99, energy=200)
        start = _snapshot(_reload(db))

        assert self._post(client, GEAR).status_code == 200
        attr = _reload(db)
        totals = dict(strength=210, agility=110, intelligence=220, endurance=210,
                      luck=210, health=106, energy=203)
        expected = _expected_derived(**totals)
        expected["res_fire"] += 3.0
        for field, value in expected.items():
            assert getattr(attr, field) == pytest.approx(value, abs=1e-9), field
        assert attr.damage == 12

        assert self._post(client, {k: -v for k, v in GEAR.items()}).status_code == 200
        _assert_same(_snapshot(_reload(db)), start)

    def test_without_token_401_and_nothing_written(self, client, db):
        _seed(db, strength=150)
        before = _snapshot(_reload(db))
        resp = self._post(client, GEAR, headers={})
        assert resp.status_code == 401
        resp = self._post(client, GEAR, headers={"X-Internal-Token": "wrong"})
        assert resp.status_code in (401, 403)
        _assert_same(_snapshot(_reload(db)), before)

    def test_unknown_keys_ignored(self, client, db):
        _seed(db, strength=150)
        before = _snapshot(_reload(db))
        resp = self._post(client, {"max_health": 9999, "' OR 1=1 --": 5, "current_mana": 1})
        assert resp.status_code == 200
        _assert_same(_snapshot(_reload(db)), before)

    def test_missing_character_404(self, client, db):
        assert self._post(client, GEAR, cid=999999).status_code == 404


# ===========================================================================
# 7. Perks
# ===========================================================================

def _make_perk(db, flat, name="Перк силы"):
    perk = models.Perk(name=name, category="combat", rarity="common", conditions=[],
                       bonuses={"flat": flat, "percent": {}, "contextual": {}, "passive": {}})
    db.add(perk)
    db.commit()
    return perk


class TestPerksAcrossThreshold:

    def test_grant_and_revoke(self, db):
        _seed(db, strength=90, luck=180)
        start = _snapshot(_reload(db))
        perk = _make_perk(db, {"strength": 30, "luck": 40, "dodge": 2.0})

        ok, already, _ = crud.grant_perk(db, CID, perk.id)
        assert ok and not already
        attr = _reload(db)
        assert attr.strength == 120
        assert attr.res_physical == pytest.approx(11.0)       # 0.1 * eff(120)
        # luck 180 -> 220: 0.1 * (155 - 140) = 1.5; plus flat dodge 2
        assert attr.critical_hit_chance == pytest.approx(start["critical_hit_chance"] + 1.5)
        assert attr.dodge == pytest.approx(start["dodge"] + 1.5 + 2.0)

        ok, _ = crud.revoke_perk(db, CID, perk.id)
        assert ok
        _assert_same(_snapshot(_reload(db)), start)


# ===========================================================================
# 8. Satiety (food)
# ===========================================================================

class TestSatietyPropagation:

    def test_apply_and_expiry_revert_exactly(self, client, db):
        _seed(db, strength=95, luck=195, stamina=200)
        start = _snapshot(_reload(db))
        resp = client.post(
            f"/attributes/internal/{CID}/satiety", headers=INTERNAL_HEADERS,
            json={"item_id": 1, "source_item_name": "Пирог", "rarity": "common",
                  "modifiers": {"strength": 10, "luck": 10, "stamina": 2, "res_ice": 1.5},
                  "recovery": {"health_recovery": 0, "mana_recovery": 0,
                               "energy_recovery": 0, "stamina_recovery": 0}},
        )
        assert resp.status_code == 201, resp.text
        attr = _reload(db)
        assert attr.res_physical == pytest.approx(start["res_physical"] + 0.75)
        assert attr.critical_hit_chance == pytest.approx(start["critical_hit_chance"] + 0.375)
        assert attr.res_ice == pytest.approx(1.5)
        assert attr.max_stamina == start["max_stamina"] + 2  # 750 -> 752.5 -> 752

        row = regen.get_satiety(db, CID)
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
        regen.settle_character(db, CID)

        assert regen.get_satiety(db, CID) is None
        after = _snapshot(_reload(db))
        start.pop("current_stamina")
        after.pop("current_stamina")  # passive regen may credit it; max is exact
        _assert_same(after, start)


# ===========================================================================
# 9. rebuild_derived_stats
# ===========================================================================

POINTS = dict(strength=150, agility=90, intelligence=180, endurance=120, luck=60,
              charisma=300, health=95, mana=30, energy=101, stamina=199)
EQUIPMENT = {"strength": 60, "luck": 50, "health": 10, "energy": 3,
             "res_fire": 4.0, "dodge": 1.5, "critical_hit_chance": 2.0,
             "damage": 7, "critical_damage": 15, "vul_fire": 3.0}
PERK_FLAT = {"intelligence": 40, "dodge": 2.0, "res_physical": 1.0}
FOOD = {"agility": 25, "res_ice": 1.5, "stamina": 2}


def _build_incrementally(db):
    """Points -> gear -> perk -> food through the real code paths."""
    _seed(db, **POINTS)
    crud._apply_modifiers_internal(db, CID, EQUIPMENT)
    db.commit()
    perk = _make_perk(db, PERK_FLAT)
    crud.grant_perk(db, CID, perk.id)
    crud._apply_modifiers_internal(db, CID, FOOD)
    now = datetime.utcnow()
    db.add(models.CharacterSatiety(
        character_id=CID, item_id=1, source_item_name="Еда", rarity="common",
        regen_bonus=0.5, modifiers=FOOD, started_at=now, expires_at=now + timedelta(hours=24)))
    db.commit()
    return _reload(db)


def _corrupt_derived(db):
    attr = _reload(db)
    for f in DERIVED_FLOAT_FIELDS:
        setattr(attr, f, 999.0)
    for f in MAX_FIELDS:
        setattr(attr, f, 1)
    db.commit()


class TestRebuildDerivedStats:

    def test_rebuild_equals_incremental_build(self, db):
        attr = _build_incrementally(db)
        incremental = _snapshot(attr)
        # sanity: gear + perk + food really moved things
        assert attr.strength == 210 and attr.intelligence == 220 and attr.agility == 115
        assert attr.res_fire == pytest.approx(4.0 + 0.1 * effective_stat(220))

        _corrupt_derived(db)
        attr = _reload(db)
        crud.rebuild_derived_stats(db, attr, EQUIPMENT)
        db.commit()
        rebuilt = _snapshot(_reload(db))
        for key in ("current_health", "current_mana", "current_energy", "current_stamina"):
            rebuilt.pop(key)
            incremental.pop(key)
        _assert_same(rebuilt, incremental)

    def test_rebuild_is_idempotent(self, db):
        attr = _build_incrementally(db)
        crud.rebuild_derived_stats(db, attr, EQUIPMENT)
        db.commit()
        first = _snapshot(_reload(db))
        attr = _reload(db)
        crud.rebuild_derived_stats(db, attr, EQUIPMENT)
        db.commit()
        assert _snapshot(_reload(db)) == first  # exactly equal, not just approx

    def test_rebuild_keeps_primaries_damage_crit_damage_vul(self, db):
        attr = _build_incrementally(db)
        attr.damage = 41
        attr.critical_damage = 177
        for f in ("vul_effects", "vul_physical", "vul_fire", "vul_damning"):
            setattr(attr, f, 6.5)
        db.commit()
        before = {f: getattr(_reload(db), f) for f in UNTOUCHED_BY_REBUILD}
        attr = _reload(db)
        crud.rebuild_derived_stats(db, attr, EQUIPMENT)
        db.commit()
        attr = _reload(db)
        assert {f: getattr(attr, f) for f in UNTOUCHED_BY_REBUILD} == before

    def test_rebuild_does_not_top_up_current(self, db):
        _seed(db, health=150)
        attr = _reload(db)
        attr.current_health = 40
        attr.current_mana = 10 ** 6  # over max -> clamped down
        db.commit()
        attr = _reload(db)
        crud.rebuild_derived_stats(db, attr, {})
        db.commit()
        attr = _reload(db)
        assert attr.current_health == 40
        assert attr.current_mana == attr.max_mana

    def test_rebuild_primary_keys_in_gear_are_not_double_counted(self, db):
        """Equipment primaries are already inside the stored totals."""
        _seed(db, strength=210)
        attr = _reload(db)
        crud.rebuild_derived_stats(db, attr, {"strength": 60, "res_physical": 1.0})
        db.commit()
        assert _reload(db).res_physical == pytest.approx(1.0 + 0.1 * effective_stat(210))

    def test_rebuild_ignores_garbage_flat_values(self, db):
        _seed(db, intelligence=50)
        attr = _reload(db)
        crud.rebuild_derived_stats(db, attr, {"res_fire": "abc", "res_ice": None,
                                              "dodge": [1], "res_wind": 2})
        db.commit()
        attr = _reload(db)
        assert attr.res_fire == pytest.approx(5.0)
        assert attr.res_wind == pytest.approx(7.0)
        assert attr.dodge == pytest.approx(BASE_DODGE)


# ===========================================================================
# 10. Recalculate endpoints
# ===========================================================================

class TestRecalculateEndpoints:

    def test_single_is_gear_aware(self, client, db):
        _seed(db, strength=210, intelligence=50)
        _corrupt_derived(db)
        with patch("main._fetch_equipment_modifiers",
                   return_value={CID: {"strength": 60, "res_fire": 4.0, "damage": 9}}) as f:
            resp = client.post(f"/attributes/{CID}/recalculate")
        assert resp.status_code == 200, resp.text
        f.assert_called_once_with([CID])
        attr = _reload(db)
        assert attr.res_fire == pytest.approx(4.0 + 5.0)
        assert attr.res_physical == pytest.approx(0.1 * effective_stat(210))
        assert attr.max_health == BASE_HEALTH
        assert attr.damage == 0  # gear damage is not re-added by a rebuild

    def test_single_inventory_down_502_nothing_written(self, client, db):
        _seed(db, strength=150)
        _corrupt_derived(db)
        before = _snapshot(_reload(db))
        with patch("main._fetch_equipment_modifiers", return_value=None):
            resp = client.post(f"/attributes/{CID}/recalculate")
        assert resp.status_code == 502
        assert resp.json()["detail"] == "Не удалось получить снаряжение персонажа"
        _assert_same(_snapshot(_reload(db)), before)

    def test_single_404(self, client, db):
        with patch("main._fetch_equipment_modifiers", return_value={}) as f:
            assert client.post("/attributes/424242/recalculate").status_code == 404
        f.assert_not_called()

    def test_all_batches_and_skipped(self, client, db):
        for cid in range(1, 6):
            _seed(db, character_id=cid, strength=100 + cid * 40)
            _corrupt_derived_for(db, cid)

        def fake_fetch(ids):
            if 3 in ids:
                return None
            return {cid: {"res_fire": 1.0} for cid in ids}

        with patch("main.RECALCULATE_BATCH_SIZE", 2), \
                patch("main._fetch_equipment_modifiers", side_effect=fake_fetch) as f:
            resp = client.post("/attributes/admin/recalculate_all")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["count"] == 3
        assert body["skipped"] == [3, 4]
        assert body["detail"] == "Recalculated 3 characters"
        assert [c.args[0] for c in f.call_args_list] == [[1, 2], [3, 4], [5]]
        for cid in (1, 2, 5):
            attr = _reload(db, cid)
            assert attr.res_physical == pytest.approx(0.1 * effective_stat(100 + cid * 40))
            assert attr.res_fire == pytest.approx(1.0)
        for cid in (3, 4):
            assert _reload(db, cid).res_physical == 999.0  # untouched

    def test_all_empty_skipped_when_inventory_ok(self, client, db):
        _seed(db, character_id=1, luck=300)
        with patch("main._fetch_equipment_modifiers",
                   side_effect=lambda ids: {cid: {} for cid in ids}):
            body = client.post("/attributes/admin/recalculate_all").json()
        assert body == {"detail": "Recalculated 1 characters", "count": 1, "skipped": []}
        assert _reload(db, 1).critical_hit_chance == pytest.approx(BASE_CRIT + 17.5)

    @pytest.mark.parametrize("user", [_EDITOR_NO_UPDATE, _PLAYER])
    def test_rbac_403(self, client, db, user):
        _seed(db, strength=150)
        app.dependency_overrides[get_current_user_via_http] = lambda: user
        with patch("main._fetch_equipment_modifiers") as f:
            assert client.post(f"/attributes/{CID}/recalculate").status_code == 403
            assert client.post("/attributes/admin/recalculate_all").status_code == 403
        f.assert_not_called()


def _corrupt_derived_for(db, cid):
    attr = _reload(db, cid)
    for f in DERIVED_FLOAT_FIELDS:
        setattr(attr, f, 999.0)
    db.commit()


class TestFetchEquipmentModifiers:

    def _resp(self, status=200, payload=None, json_exc=None):
        r = MagicMock(status_code=status)
        if json_exc:
            r.json.side_effect = json_exc
        else:
            r.json.return_value = payload
        return r

    def test_success_converts_keys_and_sends_token(self):
        with patch("main.httpx.post", return_value=self._resp(
                payload={"modifiers": {"12": {"strength": 15}, "13": None}})) as post:
            out = main._fetch_equipment_modifiers([12, 13])
        assert out == {12: {"strength": 15}, 13: {}}
        args, kwargs = post.call_args
        assert args[0].endswith("/inventory/internal/equipment-modifiers")
        assert "//internal" not in args[0]
        assert kwargs["json"] == {"character_ids": [12, 13]}
        assert "X-Internal-Token" in kwargs["headers"]

    @pytest.mark.parametrize("response", [
        "conn_error", "status_500", "status_401", "bad_json", "no_modifiers", "list_modifiers",
    ])
    def test_failures_return_none(self, response):
        if response == "conn_error":
            ctx = patch("main.httpx.post", side_effect=httpx.ConnectError("down"))
        else:
            r = {
                "status_500": self._resp(500, {}),
                "status_401": self._resp(401, {}),
                "bad_json": self._resp(json_exc=ValueError("not json")),
                "no_modifiers": self._resp(payload={}),
                "list_modifiers": self._resp(payload={"modifiers": [1, 2]}),
            }[response]
            ctx = patch("main.httpx.post", return_value=r)
        with ctx:
            assert main._fetch_equipment_modifiers([1]) is None
