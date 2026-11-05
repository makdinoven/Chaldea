"""FEAT-203 QA (tasks 6): the guard-detection roll on entry.

* ``law_core.detection_base_pct`` / ``detection_chance``: the §3.2 worked examples (60 / 55 / 100 / 10.5 / 5), every
  factor (location bases incl. the default, + per extra guard with 1..n guards, effective stealth with the subclass
  bonus and the stat caps, fame, mask — fame ignored under a mask (PM Q2) AND × 0.75 —, the level multiplier
  60..140, clamps), validation of the new settings / level bounds;
* ``law_crud.check_entry``: the FEAT-198 exits keep their order and never roll (open encounter, jailed, no guard,
  KO'd / dead guards, flee cooldown, not wanted, NPC); a slip = no encounter / no lock / a ``slipped`` law_log row
  with chance + roll and a unique key; detected = the encounter as before with chance + roll on its log row;
  ``detect_enabled`` off = always detected with NULL chance / roll; every entry rerolls; outlaw without wanted uses
  the ``outlaw_min_level`` multiplier; the readers (marker, guards, stealth, subclass, mask, fame) are real;
* ``PUT /characters/internal/{id}/update_location``: ``law_slipped`` + the progress notice AFTER the commit; a post
  in the same location never rolls; the teleport master path rolls and returns ``law_slipped``;
* ``GET/PUT /characters/admin/law/settings``: the new fields, optional on input (stored values kept), validation;
* migration 043: up / down / re-run on a fake MySQL schema; the re-run keeps edited level values.

Randomness: the ``law_crud.detection_rng`` seam (``law_world`` defaults it to «always detected»).
"""

import importlib.util
import os
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

import econ_ledger
import law_core as lc
import law_crud
import law_notify
import locations_client
import models
from tests.law_world import (  # noqa: F401  (fixtures)
    ALPHA, BETA, GUARD_POST, INTERNAL, L_FARM, L_MARKET, L_POST, L_ROAD, R_OST, R_PASHNI, USER_ALPHA, api,
    as_admin, as_user, char_row, encounter, exec_, jail_character, law_payloads, law_world, now, q, rep_world, rows,
    set_value, set_wanted,
)
from tests.shadow_world import give_mask, set_attrs, set_marker, set_renown, set_subclass

D = Decimal
S = lc.DEFAULT_SETTINGS
ADMIN_BASE = "/characters/admin/law"
SEVERITY = {"suspect": 60, "offender": 80, "criminal": 100, "villain": 120, "enemy": 140}


# =============================================================================================== rng helpers

class FixedRng:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def random(self):
        self.calls += 1
        return self.value


class ExplodingRng:
    def random(self):
        raise AssertionError("no detection roll expected on this path")


def detect_roll(monkeypatch, value):
    rng = FixedRng(value)
    monkeypatch.setattr(law_crud, "detection_rng", lambda: rng)
    return rng


def no_detect_roll(monkeypatch):
    monkeypatch.setattr(law_crud, "detection_rng", lambda: ExplodingRng())


SLIP = 0.9999        # roll 99.99 >= any chance below 100 -> slipped
DETECT = 0.0         # roll 0.00 < min 5 % -> detected


# =============================================================================================== pure: base

@pytest.mark.parametrize("marker,expected", [
    ("safe", 100), ("farm", 70), ("dangerous", 40), ("dungeon", 25), (None, 50), ("volcano", 50), ("", 50),
])
def test_detection_base_by_marker(marker, expected):
    assert lc.detection_base_pct(marker, S) == D(expected)


def test_detection_base_uses_the_settings_values():
    s = lc.LawSettings(detect_base_safe_pct=D(90), detect_base_farm_pct=D(60), detect_base_dangerous_pct=D(30),
                       detect_base_dungeon_pct=D(20), detect_base_default_pct=D(11))
    assert [lc.detection_base_pct(m, s) for m in ("safe", "farm", "dangerous", "dungeon", None)] == \
        [D(90), D(60), D(30), D(20), D(11)]


def test_marker_literals_equal_shadow_core():
    import shadow_core as sc
    assert (lc.MARKER_SAFE, lc.MARKER_FARM, lc.MARKER_DANGEROUS, lc.MARKER_DUNGEON) == (
        sc.MARKER_SAFE, sc.MARKER_FARM, sc.MARKER_DANGEROUS, sc.MARKER_DUNGEON)


# =============================================================================================== pure: chance

def chance(base=100, n=1, reduction=0, fame=0, masked=False, level=100, s=S):
    return lc.detection_chance(base, n, reduction, fame, masked, level, s)


@pytest.mark.parametrize("kwargs,expected", [
    (dict(level=60), "60.00"),                                         # suspect, settlement, 1 guard, nothing
    (dict(n=2, reduction=50, level=100), "55.00"),                     # criminal, 2 guards, eff. stealth 100
    (dict(level=140), "100.00"),                                       # enemy: 140 -> max
    (dict(masked=True, reduction=90, level=140), "10.50"),             # masked enemy, eff. stealth 180
    (dict(base=25, reduction=90, masked=True, level=60), "5.00"),      # anything tiny -> min
])
def test_worked_examples(kwargs, expected):
    assert chance(**kwargs) == D(expected)


@pytest.mark.parametrize("n,expected", [(0, "50.00"), (1, "50.00"), (2, "55.00"), (3, "60.00"), (5, "70.00"),
                                        (None, "50.00")])
def test_per_extra_guard_multiplier(n, expected):
    assert chance(base=50, n=n) == D(expected)


def test_per_guard_setting():
    s = lc.LawSettings(detect_per_guard_pct=D(25))
    assert chance(base=40, n=3, s=s) == D("60.00")            # 40 × 1.5
    assert chance(base=40, n=3, s=lc.LawSettings(detect_per_guard_pct=D(0))) == D("40.00")


@pytest.mark.parametrize("reduction,expected", [(0, "80.00"), (50, "40.00"), (87.5, "10.00"), (90, "8.00"),
                                                (-20, "80.00"), (150, "5.00")])
def test_stealth_reduction(reduction, expected):
    assert chance(base=80, reduction=reduction) == D(expected)


@pytest.mark.parametrize("fame,expected", [(0, "50.00"), (2, "51.00"), (10, "55.00"), (15, "57.50"),
                                           (-10, "50.00")])
def test_fame_raises_the_chance(fame, expected):
    assert chance(base=50, fame=fame) == D(expected)


def test_mask_ignores_fame_and_applies_the_factor():
    assert chance(base=80, masked=True) == D("60.00")                       # × 0.75
    assert chance(base=80, masked=True, fame=15) == D("60.00")              # fame dropped under a mask
    assert chance(base=80, masked=False, fame=15) == D("92.00")
    assert chance(base=80, masked=True, s=lc.LawSettings(detect_mask_factor_pct=D(50))) == D("40.00")
    assert chance(base=80, masked=True, s=lc.LawSettings(detect_mask_factor_pct=D(100))) == D("80.00")


@pytest.mark.parametrize("code,expected", [("suspect", "30.00"), ("offender", "40.00"), ("criminal", "50.00"),
                                           ("villain", "60.00"), ("enemy", "70.00")])
def test_level_multipliers(code, expected):
    level = {lv.code: lv for lv in lc.DEFAULT_LEVELS}[code]
    assert level.detect_pct == D(SEVERITY[code])
    assert chance(base=50, level=level.detect_pct) == D(expected)


def test_negative_level_pct_is_zero_then_min():
    assert chance(level=-50) == D("5.00")


def test_clamps_follow_the_settings():
    s = lc.LawSettings(detect_min_pct=D(20), detect_max_pct=D(80))
    assert chance(base=10, s=s) == D("20.00")
    assert chance(base=100, level=140, s=s) == D("80.00")
    assert chance(base=50, s=s) == D("50.00")
    zero = lc.LawSettings(detect_min_pct=D(0))
    assert chance(base=100, reduction=100, s=zero) == D("0.00")


def test_rounding_two_decimals_half_up():
    assert chance(base=D("33.335")) == D("33.34")
    assert chance(base=70, n=2, reduction=D("57.5"), fame=5, level=80) == D("27.49")   # 70×1.1×0.425×1.05×0.8


def test_all_factors_multiply():
    # dungeon 25 × (1 + 0.1×3) × (1 − 0.2) × (1 + 0.05) × 1.2 = 32.76
    assert chance(base=25, n=4, reduction=20, fame=5, level=120) == D("32.76")


def test_roll_against_the_chance():
    assert lc.roll_succeeds(D("80.00"), FixedRng(0.7999)) == (True, D("79.99"))
    assert lc.roll_succeeds(D("80.00"), FixedRng(0.8)) == (False, D("80.00"))
    assert lc.roll_succeeds(D("100.00"), FixedRng(0.99999999)) == (True, D("99.99"))


# =============================================================================================== pure: settings

def test_defaults_and_validation_ok():
    assert S.detect_enabled is True
    assert (S.detect_per_guard_pct, S.detect_mask_factor_pct, S.detect_min_pct, S.detect_max_pct) == (
        D(10), D(75), D(5), D(100))
    assert lc.validate(S, lc.DEFAULT_LEVELS) is None
    for name in lc.DETECT_PCT_FIELDS:
        assert name in lc.SETTINGS_FIELDS
    assert "detect_enabled" in lc.SETTINGS_FIELDS


def _with(**kw):
    values = {name: getattr(S, name) for name in lc.SETTINGS_FIELDS}
    values.update(kw)
    return lc.LawSettings(**values)


@pytest.mark.parametrize("name", lc.DETECT_PCT_FIELDS)
@pytest.mark.parametrize("value", [D("-0.01"), D("100.01")])
def test_validation_percent_bounds(name, value):
    extra = {}
    if name == "detect_min_pct" and value > 100:
        extra["detect_max_pct"] = D(100)
    assert lc.validate(_with(**{name: value}, **extra), lc.DEFAULT_LEVELS) == \
        "Обнаружение стражей: проценты должны быть от 0 до 100"


@pytest.mark.parametrize("name", lc.DETECT_PCT_FIELDS)
def test_validation_percent_edges_ok(name):
    for value in (D(0), D(100)):
        kw = {name: value}
        if name == "detect_min_pct" and value == 100:
            kw["detect_max_pct"] = D(100)
        if name == "detect_max_pct" and value == 0:
            kw["detect_min_pct"] = D(0)
        assert lc.validate(_with(**kw), lc.DEFAULT_LEVELS) is None


def test_validation_min_above_max():
    assert lc.validate(_with(detect_min_pct=D(60), detect_max_pct=D(50)), lc.DEFAULT_LEVELS) == \
        "Обнаружение стражей: минимум не может быть больше максимума"
    assert lc.validate(_with(detect_min_pct=D(50), detect_max_pct=D(50)), lc.DEFAULT_LEVELS) is None


def _levels(**detect):
    return [lc.Level(lv.code, lv.sort_order, lv.name, lv.min_value, lv.fine, lv.jail_hours,
                     D(str(detect.get(lv.code, lv.detect_pct)))) for lv in lc.DEFAULT_LEVELS]


@pytest.mark.parametrize("value,ok", [(0, True), (500, True), ("-0.01", False), ("500.01", False)])
def test_validation_level_detect_pct_bounds(value, ok):
    error = lc.validate(S, _levels(villain=value))
    assert (error is None) == ok
    if not ok:
        assert error == "Заметность ступени розыска: от 0 до 500 %"


def test_row_parsers():
    row = [getattr(S, n) for n in lc.SETTINGS_FIELDS]
    row[lc.SETTINGS_FIELDS.index("detect_enabled")] = 0
    row[lc.SETTINGS_FIELDS.index("detect_min_pct")] = "7.50"
    parsed = lc.settings_from_row(row)
    assert parsed.detect_enabled is False and parsed.detect_min_pct == D("7.50")
    row[lc.SETTINGS_FIELDS.index("detect_enabled")] = 1
    assert lc.settings_from_row(row).detect_enabled is True
    six = [("suspect", 1, "П", 1, 50, 2)]
    seven = [("suspect", 1, "П", 1, 50, 2, "60.00")]
    assert lc.levels_from_rows(six)[0].detect_pct == D(100)                  # an old 6-column row
    assert lc.levels_from_rows(seven)[0].detect_pct == D("60.00")
    assert "detect_pct" in lc.SQL_SELECT_LEVELS


# =============================================================================================== world helpers

def seed_severity(f, **override):
    """The 043 seed (the law_world levels come from the 039 seed = model default 100)."""
    values = dict(SEVERITY, **override)
    for code, pct in values.items():
        exec_(f, "UPDATE law_levels SET detect_pct = :p WHERE code = :c", p=pct, c=code)


def law_settings(f, **overrides):
    db = f()
    try:
        row = db.get(models.LawSettings, 1)
        for name, value in overrides.items():
            setattr(row, name, value)
        db.commit()
    finally:
        db.close()


_GUARD_SEQ = {"n": 80}


def add_guard(f, location_id=L_POST, **fields):
    _GUARD_SEQ["n"] += 1
    gid = _GUARD_SEQ["n"]
    db = f()
    try:
        with econ_ledger.allow_direct_balance_write(db):
            db.add(models.Character(id=gid, name=f"Стражник {gid}", user_id=None, id_subrace=1, id_class=1,
                                    id_race=1, appearance="-", avatar="-", is_npc=True, npc_role="guard",
                                    npc_status=fields.get("npc_status", "alive"), current_location_id=location_id,
                                    unconscious_until=fields.get("unconscious_until"), level=5,
                                    currency_balance=0))
            db.commit()
    finally:
        db.close()
    return gid


def enter(f, character_id=ALPHA, location_id=L_POST, source="move", from_location_id=L_MARKET, at=None):
    """law_crud.check_entry in its own committed transaction (as the move does); returns the EntryResult."""
    db = f()
    try:
        character = db.query(models.Character).filter(models.Character.id == character_id).first()
        character.current_location_id = location_id
        result = law_crud.check_entry(db, character, location_id, source, at, from_location_id=from_location_id)
        db.commit()
        if result.encounter is not None:                 # keep the encounter readable after the session closes
            db.refresh(result.encounter)
            db.expunge(result.encounter)
        return result
    finally:
        db.close()


LOG_COLS = ("event_key", "action", "region_id", "wanted_before", "wanted_after", "chance_pct", "roll_pct", "ref_id",
            "reason")


def law_logs(f, character_id=ALPHA, action=None):
    sql = "SELECT " + ", ".join(LOG_COLS) + " FROM law_log WHERE character_id = :c"
    params = {"c": character_id}
    if action:
        sql += " AND action = :a"
        params["a"] = action
    return [dict(zip(LOG_COLS, r)) for r in rows(f, sql + " ORDER BY id", **params)]


def dec(v):
    return None if v is None else D(str(v)).quantize(D("0.01"))


def encounters_count(f):
    return q(f, "SELECT COUNT(*) FROM law_encounters")


# =============================================================================================== entry: slip

def test_slip_has_no_encounter_no_lock_and_logs_chance_and_roll(law_world, monkeypatch):
    seed_severity(law_world)
    set_wanted(law_world, ALPHA, R_OST, 150)                                  # offender ×0.8, safe base 100
    rng = detect_roll(monkeypatch, SLIP)
    res = enter(law_world, source="quick_move")
    assert rng.calls == 1
    assert (res.encounter, res.slipped, res.chance_pct, res.roll_pct) == (None, True, D("80.00"), D("99.99"))
    assert encounters_count(law_world) == 0
    assert char_row(law_world, ALPHA).law_encounter_id is None
    (log,) = law_logs(law_world)
    assert log["action"] == lc.LOG_SLIPPED == "slipped"
    assert log["event_key"].startswith(f"law:slip:{ALPHA}:{L_POST}:")
    assert (log["region_id"], log["wanted_before"], log["wanted_after"]) == (R_OST, 150, 150)
    assert (dec(log["chance_pct"]), dec(log["roll_pct"])) == (D("80.00"), D("99.99"))
    assert (log["ref_id"], log["reason"]) == (L_POST, "quick_move")


def test_slip_keys_are_unique_even_at_the_same_instant(law_world, monkeypatch):
    seed_severity(law_world)
    set_wanted(law_world, ALPHA, R_OST, 150)
    detect_roll(monkeypatch, SLIP)
    at = now()
    enter(law_world, at=at)
    enter(law_world, at=at)
    keys = [r["event_key"] for r in law_logs(law_world, action="slipped")]
    assert len(keys) == 2 and len(set(keys)) == 2


def test_slip_sets_no_cooldown_and_every_entry_rerolls(law_world, monkeypatch):
    seed_severity(law_world)
    set_wanted(law_world, ALPHA, R_OST, 150)
    rng = detect_roll(monkeypatch, SLIP)
    for _ in range(3):
        assert enter(law_world).slipped is True
    assert rng.calls == 3
    rng.value = DETECT                                                       # the 4th entry is noticed
    res = enter(law_world)
    assert rng.calls == 4 and res.encounter is not None and res.slipped is False
    assert [r["action"] for r in law_logs(law_world)] == ["slipped"] * 3 + ["encounter"]


@pytest.mark.parametrize("value,detected", [(0.7999, True), (0.8, False)])
def test_roll_boundary_against_the_chance(law_world, monkeypatch, value, detected):
    seed_severity(law_world)
    set_wanted(law_world, ALPHA, R_OST, 150)                                  # chance 80.00
    detect_roll(monkeypatch, value)
    res = enter(law_world)
    assert (res.encounter is not None) is detected and res.slipped is (not detected)


def test_detected_encounter_log_carries_chance_and_roll(law_world, monkeypatch):
    seed_severity(law_world)
    set_wanted(law_world, ALPHA, R_OST, 150)
    detect_roll(monkeypatch, 0.4242)
    res = enter(law_world)
    enc = encounter(law_world, res.encounter.id)
    assert (enc.status, enc.level_code, enc.guard_npc_id) == ("pending", "offender", GUARD_POST)
    assert char_row(law_world, ALPHA).law_encounter_id == enc.id
    (log,) = law_logs(law_world)
    assert log["action"] == "encounter" and log["event_key"] == f"law:encounter:{enc.id}"
    assert (dec(log["chance_pct"]), dec(log["roll_pct"])) == (D("80.00"), D("42.42"))
    assert (res.chance_pct, res.roll_pct) == (D("80.00"), D("42.42"))


def test_detect_disabled_always_detects_with_null_chance(law_world, monkeypatch):
    seed_severity(law_world)
    law_settings(law_world, detect_enabled=False)
    set_wanted(law_world, ALPHA, R_OST, 150)
    no_detect_roll(monkeypatch)
    res = enter(law_world)
    assert res.encounter is not None and res.slipped is False
    assert (res.chance_pct, res.roll_pct) == (None, None)
    (log,) = law_logs(law_world)
    assert log["action"] == "encounter" and log["chance_pct"] is None and log["roll_pct"] is None


def test_evaluate_entry_wrapper_returns_none_on_a_slip(law_world, monkeypatch):
    seed_severity(law_world)                                                  # 80 < 100: a slip is possible
    set_wanted(law_world, ALPHA, R_OST, 150)
    detect_roll(monkeypatch, SLIP)
    db = law_world()
    try:
        character = db.query(models.Character).filter(models.Character.id == ALPHA).first()
        assert law_crud.evaluate_entry(db, character, L_POST, "move") is None
        db.commit()
    finally:
        db.close()
    assert [r["action"] for r in law_logs(law_world)] == ["slipped"]


# =============================================================================================== entry: exits

def test_no_roll_with_an_open_encounter(law_world, monkeypatch):
    set_wanted(law_world, ALPHA, R_OST, 150)
    assert enter(law_world).encounter is not None                            # fixture: always detected
    no_detect_roll(monkeypatch)
    assert enter(law_world) == law_crud.EntryResult()
    assert len(law_logs(law_world)) == 1


def test_no_roll_while_jailed(law_world, monkeypatch):
    set_wanted(law_world, BETA, R_OST, 150)
    jail_character(law_world, BETA)
    no_detect_roll(monkeypatch)
    assert enter(law_world, character_id=BETA) == law_crud.EntryResult()
    assert law_logs(law_world, BETA) == []


def test_no_roll_without_a_guard(law_world, monkeypatch):
    set_wanted(law_world, ALPHA, R_OST, 150)
    no_detect_roll(monkeypatch)
    assert enter(law_world, location_id=L_ROAD) == law_crud.EntryResult()


def test_no_roll_when_every_guard_is_ko_or_dead(law_world, monkeypatch):
    set_wanted(law_world, ALPHA, R_OST, 150)
    exec_(law_world, "UPDATE characters SET unconscious_until = :t WHERE id = :g",
          t=datetime.utcnow() + timedelta(hours=1), g=GUARD_POST)
    add_guard(law_world, npc_status="dead")
    no_detect_roll(monkeypatch)
    assert enter(law_world) == law_crud.EntryResult()
    assert law_logs(law_world) == []


def test_flee_cooldown_comes_before_the_roll(law_world, monkeypatch):
    set_wanted(law_world, ALPHA, R_OST, 150)
    enc_id = enter(law_world).encounter.id
    exec_(law_world, "UPDATE law_encounters SET status = 'fled', cooldown_until = :t WHERE id = :e",
          t=now() + timedelta(minutes=30), e=enc_id)
    exec_(law_world, "UPDATE characters SET law_encounter_id = NULL WHERE id = :c", c=ALPHA)
    no_detect_roll(monkeypatch)
    assert enter(law_world) == law_crud.EntryResult()                        # no roll, no slip
    assert [r["action"] for r in law_logs(law_world)] == ["encounter"]


def test_no_roll_when_not_wanted(law_world, monkeypatch):
    no_detect_roll(monkeypatch)
    assert enter(law_world) == law_crud.EntryResult()
    set_wanted(law_world, ALPHA, R_PASHNI, 500)                              # another region
    assert enter(law_world) == law_crud.EntryResult()
    assert law_logs(law_world) == []


def test_no_roll_for_npcs(law_world, monkeypatch):
    no_detect_roll(monkeypatch)
    assert enter(law_world, character_id=GUARD_POST, location_id=L_POST) == law_crud.EntryResult()


# =============================================================================================== entry: readers

def test_guard_count_excludes_ko_and_dead_guards(law_world, monkeypatch):
    seed_severity(law_world, offender=50)                                     # 100 × 0.5 = 50, room to grow
    set_wanted(law_world, ALPHA, R_OST, 150)
    detect_roll(monkeypatch, SLIP)
    assert enter(law_world).chance_pct == D("50.00")                          # 1 guard
    add_guard(law_world)
    assert enter(law_world).chance_pct == D("55.00")                          # 2 guards
    add_guard(law_world)
    assert enter(law_world).chance_pct == D("60.00")                          # 3 guards
    add_guard(law_world, unconscious_until=datetime.utcnow() + timedelta(hours=2))
    add_guard(law_world, npc_status="dead")
    add_guard(law_world, location_id=L_ROAD)                                  # elsewhere
    assert enter(law_world).chance_pct == D("60.00")
    add_guard(law_world, unconscious_until=datetime.utcnow() - timedelta(minutes=1))   # recovered
    assert enter(law_world).chance_pct == D("65.00")


@pytest.mark.parametrize("marker,expected", [("safe", "80.00"), ("farm", "56.00"), ("dangerous", "32.00"),
                                             ("dungeon", "20.00"), ("cave", "40.00")])
def test_location_marker_is_read(law_world, monkeypatch, marker, expected):
    seed_severity(law_world)
    set_wanted(law_world, ALPHA, R_OST, 150)
    set_marker(law_world, L_POST, marker)
    detect_roll(monkeypatch, SLIP)
    assert enter(law_world).chance_pct == D(expected)


def test_location_base_settings_are_used(law_world, monkeypatch):
    seed_severity(law_world)
    set_wanted(law_world, ALPHA, R_OST, 150)
    set_marker(law_world, L_POST, "farm")
    law_settings(law_world, detect_base_farm_pct=D(50))
    detect_roll(monkeypatch, SLIP)
    assert enter(law_world).chance_pct == D("40.00")


@pytest.mark.parametrize("stealth,subclass,expected", [
    (100, None, "40.00"),                       # eff 100 -> −50 %
    (100, "rogue_assassin", "34.00"),           # 130 -> eff 115 -> −57.5 %
    (100, "warrior_agent", "36.00"),            # 120 -> eff 110 -> −55 %
    (100, "mage_pyro", "40.00"),                # other subclass: no bonus
    (300, None, "10.00"),                       # eff 175 -> −87.5 %
    (400, None, "8.00"),                        # eff 200 -> 100 -> capped at −90 %
])
def test_effective_stealth_with_subclass_and_caps(law_world, monkeypatch, stealth, subclass, expected):
    seed_severity(law_world)
    set_wanted(law_world, ALPHA, R_OST, 150)
    set_attrs(law_world, ALPHA, stealth=stealth)
    if subclass:
        set_subclass(law_world, ALPHA, subclass)
    detect_roll(monkeypatch, SLIP)
    assert enter(law_world).chance_pct == D(expected)


def test_fame_counts_without_a_mask(law_world, monkeypatch):
    seed_severity(law_world)
    set_wanted(law_world, ALPHA, R_OST, 150)
    set_renown(law_world, ALPHA, fame=600)                                    # «Знаменитый» +10 %
    detect_roll(monkeypatch, SLIP)
    assert enter(law_world).chance_pct == D("88.00")


def test_mask_hides_fame_and_lowers_the_chance(law_world, monkeypatch):
    seed_severity(law_world)
    set_wanted(law_world, ALPHA, R_OST, 150)
    set_renown(law_world, ALPHA, fame=1500)                                   # «Легенда» +15 %
    give_mask(law_world, ALPHA)
    detect_roll(monkeypatch, SLIP)
    assert enter(law_world).chance_pct == D("60.00")                          # 80 × 0.75, no fame


def test_non_mask_head_item_is_no_mask(law_world, monkeypatch):
    seed_severity(law_world)
    set_wanted(law_world, ALPHA, R_OST, 150)
    give_mask(law_world, ALPHA, is_mask=0)
    detect_roll(monkeypatch, SLIP)
    assert enter(law_world).chance_pct == D("80.00")


@pytest.mark.parametrize("value,expected", [(50, "60.00"), (150, "80.00"), (300, "100.00"), (600, "100.00"),
                                            (950, "100.00")])
def test_severity_follows_the_wanted_level(law_world, monkeypatch, value, expected):
    seed_severity(law_world)
    set_wanted(law_world, ALPHA, R_OST, value)
    detect_roll(monkeypatch, SLIP)
    assert enter(law_world).chance_pct == D(expected)


@pytest.mark.parametrize("value,expected", [(50, "30.00"), (150, "40.00"), (300, "50.00"), (600, "60.00"),
                                            (950, "70.00")])
def test_severity_multipliers_on_a_lower_base(law_world, monkeypatch, value, expected):
    seed_severity(law_world)
    set_marker(law_world, L_POST, "cave")                                    # default base 50
    set_wanted(law_world, ALPHA, R_OST, value)
    detect_roll(monkeypatch, SLIP)
    assert enter(law_world).chance_pct == D(expected)


def test_outlaw_without_wanted_uses_the_outlaw_min_level(law_world, monkeypatch):
    seed_severity(law_world)
    set_marker(law_world, L_POST, "farm")                                     # base 70
    set_value(law_world, ALPHA, R_OST, -700)                                  # «Вне закона», wanted 0
    detect_roll(monkeypatch, SLIP)
    assert enter(law_world).chance_pct == D("70.00")                          # criminal ×1.0
    law_settings(law_world, outlaw_min_level="villain")
    assert enter(law_world).chance_pct == D("84.00")                          # villain ×1.2
    rng_detect = detect_roll(monkeypatch, DETECT)
    res = enter(law_world)
    assert rng_detect.calls == 1 and res.encounter.level_code == "villain" and res.encounter.is_outlaw


def test_clamp_settings_apply_on_entry(law_world, monkeypatch):
    seed_severity(law_world)
    set_wanted(law_world, ALPHA, R_OST, 150)
    set_attrs(law_world, ALPHA, stealth=400)                                  # 80 × 0.1 = 8
    law_settings(law_world, detect_min_pct=D(15), detect_max_pct=D(70))
    detect_roll(monkeypatch, SLIP)
    assert enter(law_world).chance_pct == D("15.00")
    set_attrs(law_world, ALPHA, stealth=0)
    assert enter(law_world).chance_pct == D("70.00")


# =============================================================================================== update_location

def _move(api, cid, loc, source=None, headers=INTERNAL):
    body = {"new_location_id": loc}
    if source is not None:
        body["source"] = source
    return api.put(f"/characters/internal/{cid}/update_location", json=body, headers=headers)


def test_update_location_slip_response_and_notice_after_commit(api, law_world, monkeypatch, stub_law_notify_send):
    seed_severity(law_world)
    set_wanted(law_world, ALPHA, R_OST, 150)
    detect_roll(monkeypatch, SLIP)
    committed = []

    def check_committed(payloads):           # the slip row must be visible from another session at send time
        committed.append(q(law_world, "SELECT COUNT(*) FROM law_log WHERE action = 'slipped'"))

    stub_law_notify_send.side_effect = check_committed
    resp = _move(api, ALPHA, L_POST, source="move")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["law_slipped"] is True and data["law_encounter"] is None
    assert data["current_location_id"] == L_POST
    assert "chance" not in str(data) and "roll" not in str(data)
    row = char_row(law_world, ALPHA)
    assert row.current_location_id == L_POST and row.law_encounter_id is None
    assert committed == [1]
    (payload,) = law_payloads(stub_law_notify_send)
    assert payload["ws_type"] == law_notify.WS_SLIPPED == "law_slipped"
    assert payload["category"] == "progress" and payload["target_value"] == USER_ALPHA
    assert payload["message"] == "Вы проскользнули мимо стражи в «Застава»"
    assert payload["ws_data"] == {"character_id": ALPHA, "location_id": L_POST}
    assert not any(ch.isdigit() for ch in payload["message"])                # no numbers in player text
    # free to move on (no lock)
    assert _move(api, ALPHA, L_MARKET).status_code == 200


def test_slipped_message_fallback():
    assert law_notify.slipped_message(None) == "Вы проскользнули мимо стражи"
    assert law_notify.slipped_message("Рынок") == "Вы проскользнули мимо стражи в «Рынок»"


def test_update_location_detected_has_no_slip(api, law_world, stub_law_notify_send):
    set_wanted(law_world, ALPHA, R_OST, 150)
    data = _move(api, ALPHA, L_POST).json()
    assert data["law_slipped"] is False and data["law_encounter"]["status"] == "pending"
    assert [p["ws_type"] for p in law_payloads(stub_law_notify_send)] == ["law_encounter"]


def test_update_location_not_wanted_has_false_and_no_notice(api, law_world, monkeypatch, stub_law_notify_send):
    no_detect_roll(monkeypatch)
    data = _move(api, ALPHA, L_POST).json()
    assert data["law_slipped"] is False and data["law_encounter"] is None
    assert law_payloads(stub_law_notify_send) == []


def test_post_in_the_same_location_never_rolls(api, law_world, monkeypatch, stub_law_notify_send):
    exec_(law_world, "UPDATE characters SET current_location_id = :l WHERE id = :c", l=L_POST, c=ALPHA)
    set_wanted(law_world, ALPHA, R_OST, 150)
    no_detect_roll(monkeypatch)
    resp = _move(api, ALPHA, L_POST)
    assert resp.status_code == 200, resp.text
    assert resp.json()["law_slipped"] is False and resp.json()["law_encounter"] is None
    assert law_logs(law_world) == [] and law_payloads(stub_law_notify_send) == []


def test_slip_notice_failure_does_not_fail_the_move(api, law_world, monkeypatch):
    seed_severity(law_world)                                                  # 80 < 100: a slip is possible
    set_wanted(law_world, ALPHA, R_OST, 150)
    detect_roll(monkeypatch, SLIP)

    def boom(*a, **kw):
        raise RuntimeError("names unavailable")

    monkeypatch.setattr(law_crud, "slip_notice", boom)
    resp = _move(api, ALPHA, L_POST)
    assert resp.status_code == 200 and resp.json()["law_slipped"] is True
    assert char_row(law_world, ALPHA).current_location_id == L_POST
    assert [r["action"] for r in law_logs(law_world)] == ["slipped"]


# =============================================================================================== teleport

TP_FROM, TP_TO = 70, 71


@pytest.fixture
def teleport_world(law_world, monkeypatch):
    db = law_world()
    try:
        with econ_ledger.allow_direct_balance_write(db):
            for cid, loc in ((TP_FROM, L_MARKET), (TP_TO, L_POST)):
                db.add(models.Character(id=cid, name=f"Маг {cid}", user_id=None, id_subrace=1, id_class=1,
                                        id_race=1, appearance="-", avatar="-", is_npc=True,
                                        npc_role="teleport_master", npc_status="alive", current_location_id=loc,
                                        level=5, currency_balance=0))
            db.flush()
        db.add(models.TeleportLink(id=1, from_npc_id=TP_FROM, to_npc_id=TP_TO, cost_gold=0))
        db.execute(text("UPDATE users SET current_character = :c WHERE id = :u"), {"c": ALPHA, "u": USER_ALPHA})
        db.execute(text("UPDATE characters SET current_location_id = :l WHERE id = :c"), {"l": L_MARKET, "c": ALPHA})
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(locations_client, "notify_character_left_location_sync", MagicMock())
    return law_world


def test_teleport_master_arrival_rolls_and_can_slip(api, teleport_world, monkeypatch, stub_law_notify_send):
    seed_severity(teleport_world)
    set_wanted(teleport_world, ALPHA, R_OST, 150)
    rng = detect_roll(monkeypatch, SLIP)
    as_user(USER_ALPHA)
    resp = api.post(f"/characters/npcs/{TP_FROM}/teleport", json={"link_id": 1})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert rng.calls == 1
    assert data["law_slipped"] is True and data["law_encounter"] is None
    assert "character_id" not in data and "law_encounter_id" not in data
    assert char_row(teleport_world, ALPHA).law_encounter_id is None
    (log,) = law_logs(teleport_world)
    assert (log["action"], log["reason"], log["ref_id"]) == ("slipped", "teleport", L_POST)
    (payload,) = law_payloads(stub_law_notify_send)
    assert payload["ws_type"] == "law_slipped" and payload["category"] == "progress"
    assert payload["message"] == "Вы проскользнули мимо стражи в «Застава»"


def test_teleport_detected_has_false_slip(api, teleport_world, monkeypatch):
    set_wanted(teleport_world, ALPHA, R_OST, 150)
    detect_roll(monkeypatch, DETECT)
    as_user(USER_ALPHA)
    data = api.post(f"/characters/npcs/{TP_FROM}/teleport", json={"link_id": 1}).json()
    assert data["law_slipped"] is False and data["law_encounter"]["status"] == "pending"


def test_teleport_without_wanted_never_rolls(api, teleport_world, monkeypatch, stub_law_notify_send):
    no_detect_roll(monkeypatch)
    as_user(USER_ALPHA)
    data = api.post(f"/characters/npcs/{TP_FROM}/teleport", json={"link_id": 1}).json()
    assert data["law_slipped"] is False and data["law_encounter"] is None
    assert law_payloads(stub_law_notify_send) == []


# =============================================================================================== admin settings

DETECT_FIELDS = ("detect_enabled",) + lc.DETECT_PCT_FIELDS


def _settings_body(api):
    as_admin()
    return api.get(f"{ADMIN_BASE}/settings").json()


def test_settings_get_has_the_new_fields(api, law_world):
    seed_severity(law_world)
    data = _settings_body(api)
    s = data["settings"]
    assert s["detect_enabled"] is True
    assert [s[n] for n in lc.DETECT_PCT_FIELDS] == [100.0, 70.0, 40.0, 25.0, 50.0, 10.0, 75.0, 5.0, 100.0]
    assert [lv["detect_pct"] for lv in data["levels"]] == [60.0, 80.0, 100.0, 120.0, 140.0]


def test_settings_put_stores_the_new_fields(api, law_world):
    body = _settings_body(api)
    body["settings"].update(detect_enabled=False, detect_base_farm_pct=65.5, detect_per_guard_pct=0,
                            detect_mask_factor_pct=50, detect_min_pct=10, detect_max_pct=90)
    body["levels"][4]["detect_pct"] = 500
    resp = api.put(f"{ADMIN_BASE}/settings", json=body)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["settings"]["detect_enabled"] is False and out["settings"]["detect_base_farm_pct"] == 65.5
    assert out["levels"][4]["detect_pct"] == 500.0
    assert dec(q(law_world, "SELECT detect_mask_factor_pct FROM law_settings")) == D("50.00")
    assert not q(law_world, "SELECT detect_enabled FROM law_settings")
    assert dec(q(law_world, "SELECT detect_pct FROM law_levels WHERE code = 'enemy'")) == D("500.00")


def test_settings_put_without_the_new_fields_keeps_stored_values(api, law_world):
    seed_severity(law_world, villain=133)
    law_settings(law_world, detect_enabled=False, detect_min_pct=D(12), detect_base_dungeon_pct=D(33))
    body = _settings_body(api)
    for name in DETECT_FIELDS:
        body["settings"].pop(name)
    for lv in body["levels"]:
        lv.pop("detect_pct")
    body["settings"]["escape_cooldown_hours"] = 5                            # an old admin bundle edit
    resp = api.put(f"{ADMIN_BASE}/settings", json=body)
    assert resp.status_code == 200, resp.text
    s = resp.json()["settings"]
    assert (s["detect_enabled"], s["detect_min_pct"], s["detect_base_dungeon_pct"]) == (False, 12.0, 33.0)
    assert [lv["detect_pct"] for lv in resp.json()["levels"]] == [60.0, 80.0, 100.0, 133.0, 140.0]
    assert q(law_world, "SELECT escape_cooldown_hours FROM law_settings") == 5


def test_settings_put_explicit_null_keeps_stored_values(api, law_world):
    law_settings(law_world, detect_per_guard_pct=D(20))
    body = _settings_body(api)
    body["settings"]["detect_per_guard_pct"] = None
    body["levels"][0]["detect_pct"] = None
    resp = api.put(f"{ADMIN_BASE}/settings", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["settings"]["detect_per_guard_pct"] == 20.0
    assert resp.json()["levels"][0]["detect_pct"] == 100.0                   # law_world stored value


@pytest.mark.parametrize("mutate,message", [
    (lambda b: b["settings"].update(detect_base_safe_pct=100.5), "Обнаружение стражей: проценты должны быть от 0 до 100"),
    (lambda b: b["settings"].update(detect_per_guard_pct=-1), "Обнаружение стражей: проценты должны быть от 0 до 100"),
    (lambda b: b["settings"].update(detect_mask_factor_pct=150), "Обнаружение стражей: проценты должны быть от 0 до 100"),
    (lambda b: b["settings"].update(detect_min_pct=60, detect_max_pct=50),
     "Обнаружение стражей: минимум не может быть больше максимума"),
    (lambda b: b["levels"][2].update(detect_pct=500.01), "Заметность ступени розыска: от 0 до 500 %"),
    (lambda b: b["levels"][0].update(detect_pct=-1), "Заметность ступени розыска: от 0 до 500 %"),
])
def test_settings_put_validation_messages(api, law_world, mutate, message):
    body = _settings_body(api)
    mutate(body)
    resp = api.put(f"{ADMIN_BASE}/settings", json=body)
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == message
    assert dec(q(law_world, "SELECT detect_min_pct FROM law_settings")) == D("5.00")       # nothing stored
    assert dec(q(law_world, "SELECT detect_pct FROM law_levels WHERE code = 'criminal'")) == D("100.00")


@pytest.mark.parametrize("mutate", [
    lambda b: b["settings"].update(detect_enabled="maybe"),
    lambda b: b["settings"].update(detect_min_pct="'; DROP TABLE law_settings; --"),
    lambda b: b["levels"][0].update(detect_pct="x"),
])
def test_settings_put_bad_types_are_422(api, law_world, mutate):
    body = _settings_body(api)
    mutate(body)
    assert api.put(f"{ADMIN_BASE}/settings", json=body).status_code == 422
    assert q(law_world, "SELECT COUNT(*) FROM law_settings") == 1


def test_settings_put_rbac_unchanged(api, law_world):
    body = _settings_body(api)
    body["settings"]["detect_enabled"] = False
    as_user(USER_ALPHA)
    assert api.put(f"{ADMIN_BASE}/settings", json=body).status_code == 403
    assert q(law_world, "SELECT detect_enabled FROM law_settings")


def test_admin_switch_off_then_entry_always_detected(api, law_world, monkeypatch):
    body = _settings_body(api)
    body["settings"]["detect_enabled"] = False
    assert api.put(f"{ADMIN_BASE}/settings", json=body).status_code == 200
    set_wanted(law_world, ALPHA, R_OST, 150)
    no_detect_roll(monkeypatch)
    assert enter(law_world).encounter is not None


# =============================================================================================== migration 043

_MIG_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "043_guard_detection.py")


def _load_043():
    spec = importlib.util.spec_from_file_location("migration_043_guard_detection_qa", _MIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeMySQL:
    """A tiny information_schema + DDL emulation: tables -> {column: value-per-level-row}."""

    def __init__(self, tables=("law_settings", "law_levels")):
        self.columns = {t: set() for t in tables}
        self.levels = {code: None for code in SEVERITY}               # law_levels.detect_pct per row
        self.statements = []

    # alembic.op.get_bind().execute(...)
    def execute(self, clause, params=None):
        sql = str(clause)
        result = MagicMock()
        if "information_schema.columns" in sql:
            result.scalar.return_value = int(params["c"] in self.columns.get(params["t"], set()))
        elif "information_schema.tables" in sql:
            result.scalar.return_value = int(params["t"] in self.columns)
        else:
            raise AssertionError(f"unexpected bind SQL: {sql}")
        return result

    # alembic.op.execute(...)
    def op_execute(self, sql):
        sql = str(sql)
        self.statements.append(sql)
        words = sql.split()
        if sql.startswith("ALTER TABLE") and words[3:5] == ["ADD", "COLUMN"]:
            table, column = words[2], words[5]
            assert column not in self.columns[table], f"duplicate column {column}"
            self.columns[table].add(column)
            if (table, column) == ("law_levels", "detect_pct"):
                self.levels = {code: D(100) for code in self.levels}          # DEFAULT 100.00
        elif sql.startswith("ALTER TABLE") and words[3:5] == ["DROP", "COLUMN"]:
            table, column = words[2], words[5]
            self.columns[table].remove(column)
            if (table, column) == ("law_levels", "detect_pct"):
                self.levels = {code: None for code in self.levels}
        elif sql.startswith("UPDATE law_levels SET detect_pct"):
            assert "detect_pct" in self.columns["law_levels"]
            self.levels = {code: D(SEVERITY[code]) for code in self.levels}
        else:
            raise AssertionError(f"unexpected DDL: {sql}")


@pytest.fixture
def fake_mysql(monkeypatch):
    mig = _load_043()
    db = FakeMySQL()
    monkeypatch.setattr(mig.op, "get_bind", lambda: db, raising=False)
    monkeypatch.setattr(mig.op, "execute", db.op_execute, raising=False)
    return mig, db


_ALL_SETTINGS = {"detect_enabled", *lc.DETECT_PCT_FIELDS}


def test_migration_043_revision():
    mig = _load_043()
    assert mig.revision == "043_guard_detection" and len(mig.revision) <= 32
    assert mig.down_revision == "042_country_prison"


def test_migration_043_ddl_defaults_equal_code_defaults():
    mig = _load_043()
    assert {c for t, c, _ in mig._COLUMNS if t == "law_settings"} == _ALL_SETTINGS
    for _t, column, ddl in mig._COLUMNS:
        default = ddl.split("DEFAULT ")[1]
        expected = getattr(S, column)
        assert D(default) == (D(1) if expected is True else D(expected)), column
        assert "NOT NULL" in ddl and "ENUM" not in ddl
    assert mig._LEVEL_COLUMN == ("law_levels", "detect_pct", "DECIMAL(5,2) NOT NULL DEFAULT 100.00")


def test_migration_043_orm_has_the_columns():
    assert _ALL_SETTINGS <= set(models.LawSettings.__table__.columns.keys())
    assert "detect_pct" in models.LawLevel.__table__.columns.keys()


def test_migration_043_up_seeds_levels(fake_mysql):
    mig, db = fake_mysql
    mig.upgrade()
    assert db.columns["law_settings"] == _ALL_SETTINGS
    assert db.columns["law_levels"] == {"detect_pct"}
    assert db.levels == {k: D(v) for k, v in SEVERITY.items()}
    assert sum(s.startswith("UPDATE") for s in db.statements) == 1


def test_migration_043_rerun_is_a_noop_and_keeps_edited_levels(fake_mysql):
    mig, db = fake_mysql
    mig.upgrade()
    db.levels["villain"] = D(133)                                       # an admin edit after the deploy
    before = len(db.statements)
    mig.upgrade()
    assert len(db.statements) == before                                 # nothing executed
    assert db.levels["villain"] == D(133)


def test_migration_043_down_then_up(fake_mysql):
    mig, db = fake_mysql
    mig.upgrade()
    mig.downgrade()
    assert db.columns == {"law_settings": set(), "law_levels": set()}
    mig.downgrade()                                                     # re-run of the downgrade: no-op
    mig.upgrade()
    assert db.columns["law_settings"] == _ALL_SETTINGS
    assert db.levels == {k: D(v) for k, v in SEVERITY.items()}


def test_migration_043_partial_state_adds_only_the_missing(fake_mysql):
    mig, db = fake_mysql
    db.columns["law_settings"] = {"detect_enabled", "detect_min_pct"}  # a half-applied earlier run
    db.columns["law_levels"] = {"detect_pct"}
    db.levels = {code: D(77) for code in SEVERITY}
    mig.upgrade()
    assert db.columns["law_settings"] == _ALL_SETTINGS
    assert db.levels == {code: D(77) for code in SEVERITY}             # the column existed -> not reseeded
    assert not any(s.startswith("UPDATE") for s in db.statements)


def test_migration_043_without_the_tables_is_a_noop(monkeypatch):
    mig = _load_043()
    db = FakeMySQL(tables=())
    monkeypatch.setattr(mig.op, "get_bind", lambda: db, raising=False)
    monkeypatch.setattr(mig.op, "execute", db.op_execute, raising=False)
    mig.upgrade()
    mig.downgrade()
    assert db.statements == []
