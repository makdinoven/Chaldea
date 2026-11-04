"""FEAT-198 QA (task 9): law_core pure maths, the migration contract and the activity-lock texts.

* decay without fraction loss, levels, options matrix (outlaw / no jail / flee used), chance clamp, extension cap
  (§3.14-ANSWERED A4: 168 h), bail price, settings validation (A1: jail_hours 1..168);
* migration 039: the seed terms 2/12/24/72/168, the defaults, and the SQLite ORM tables carry exactly the
  migration's columns (so the SQLite tests exercise the real schema);
* activity lock: jail > law_encounter > unconscious priority, relative «— осталось …» messages (A8).
"""

import re
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

import activity_lock
import law_core as lc
import models
from tests.law_world import FixedRng, load_migration

NOW = datetime(2026, 11, 4, 12, 0, 0)


# =============================================================================================== migration / seeds

def test_migration_seed_terms_and_fines_match_a1():
    mig = load_migration()
    assert mig.revision == "039_law" and len(mig.revision) <= 32
    assert mig.down_revision == "038_reputation"
    by_code = {row[0]: row for row in mig.LEVELS}
    assert [row[0] for row in sorted(mig.LEVELS, key=lambda r: r[1])] == list(lc.LEVEL_CODES)
    assert [by_code[c][5] for c in lc.LEVEL_CODES] == [2, 12, 24, 72, 168]       # A1 jail hours
    assert [by_code[c][4] for c in lc.LEVEL_CODES] == [50, 150, 400, 1000, 2500]  # fines unchanged
    assert [by_code[c][3] for c in lc.LEVEL_CODES] == [1, 100, 300, 600, 900]
    # the pure defaults are the same as the seed
    assert [(lv.code, lv.sort_order, lv.name, lv.min_value, lv.fine, lv.jail_hours) for lv in lc.DEFAULT_LEVELS] \
        == [tuple(r) for r in sorted(mig.LEVELS, key=lambda r: r[1])]


def test_default_settings_a1():
    s = lc.DEFAULT_SETTINGS
    assert s.max_remaining_jail_hours == 168
    assert (s.decay_per_day, s.heavy_wanted, s.outlaw_min_level) == (Decimal(50), 600, "criminal")
    assert (s.encounter_timeout_hours, s.guard_ko_hours, s.escape_cooldown_hours) == (24, 6, 6)
    assert s.bail_multiplier == Decimal(2) and s.escape_fail_extend_pct == Decimal(50)
    mig_text = open(load_migration().__file__, encoding="utf-8").read()
    assert "max_remaining_jail_hours INT NOT NULL DEFAULT 168" in mig_text
    assert lc.FLEE_GUARD_COOLDOWN == timedelta(hours=1)          # A7


def _migration_columns(sql_text, table):
    body = re.search(r"CREATE TABLE IF NOT EXISTS %s \((.*?)\n        \) " % table, sql_text, re.S).group(1)
    cols = set()
    for line in body.splitlines():
        line = line.strip()
        if not line or line.split()[0] in ("UNIQUE", "KEY", "CONSTRAINT", "ON"):
            continue
        cols.add(line.split()[0])
    return cols


@pytest.mark.parametrize("table", ["character_wanted", "law_settings", "law_levels", "law_crimes",
                                   "law_encounters", "law_jail_terms", "law_log"])
def test_orm_tables_match_migration_columns(table):
    sql_text = open(load_migration().__file__, encoding="utf-8").read()
    expected = _migration_columns(sql_text, table)
    if table == "law_crimes":               # FEAT-199: migration 040 adds the deferred-crime snapshot columns
        import importlib.util
        import os
        path = os.path.join(os.path.dirname(load_migration().__file__), "040_shadow_renown.py")
        spec = importlib.util.spec_from_file_location("migration_040_shadow_renown", path)
        mig040 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig040)
        expected |= {c for c, _ddl in mig040._CRIME_COLUMNS}
    assert expected == set(models.Base.metadata.tables[table].columns.keys())


def test_character_columns_match_migration():
    mig = load_migration()
    names = {c for c, _ddl in mig._CHARACTER_COLUMNS}
    assert names == {"jailed_until", "jail_region_id", "law_encounter_id"}
    assert names <= set(models.Base.metadata.tables["characters"].columns.keys())


# =============================================================================================== decay

def test_materialise_without_fraction_loss():
    start = NOW - timedelta(hours=10)                        # 50/day -> 20.83 points
    value, anchor = lc.materialise(300, start, NOW, 50)
    assert value == 280
    assert anchor == start + timedelta(seconds=20 * 86400 // 50)      # exactly the time 20 points took
    # many small steps give the same result as one big one
    v, a = 300, start
    for step in range(1, 11):
        v, a = lc.materialise(v, a, start + timedelta(hours=step), 50)
    assert (v, a) == (value, anchor)
    assert lc.effective_wanted(300, start, NOW, 50) == 280


def test_materialise_edges():
    assert lc.materialise(0, NOW, NOW, 50) == (0, None)
    assert lc.materialise(100, None, NOW, 50) == (100, None)
    assert lc.materialise(100, NOW - timedelta(days=5), NOW, 0) == (100, NOW - timedelta(days=5))   # decay off
    assert lc.materialise(100, NOW - timedelta(days=30), NOW, 50) == (0, None)                       # to zero
    assert lc.materialise(100, NOW + timedelta(hours=1), NOW, 50)[0] == 100
    assert lc.materialise(100, "2026-11-04 00:00:00", NOW, 50)[0] == 75                               # SQLite str


def test_add_wanted_clamp_and_floor():
    s = lc.DEFAULT_SETTINGS
    assert lc.add_wanted(100, 150, s) == 250
    assert lc.add_wanted(900, 500, s) == 1000                          # max_wanted clamp
    assert lc.add_wanted(0, 300, s, floor=600) == 600                 # heavy floor
    assert lc.add_wanted(700, 300, s, floor=600) == 1000
    assert lc.add_wanted(0, 0, s, floor=None) == 0


def test_next_decay_at():
    old_anchor = NOW - timedelta(days=1)
    assert lc.next_decay_at(0, 100, None, NOW) == NOW                 # starts decaying now
    assert lc.next_decay_at(50, 100, old_anchor, NOW) == old_anchor   # keeps the anchor
    assert lc.next_decay_at(50, 0, old_anchor, NOW) is None


def test_crime_weight_negative_only():
    assert lc.crime_weight(-150) == 150
    assert lc.crime_weight(-300) == 300
    assert lc.crime_weight(20) == 0                                   # bandit is not a crime
    assert lc.crime_weight(0) == 0 and lc.crime_weight(None) == 0


# =============================================================================================== levels

def test_level_for_and_at_least():
    levels = list(lc.DEFAULT_LEVELS)
    assert lc.level_for(0, levels) is None
    assert lc.level_for(1, levels).code == "suspect"
    assert lc.level_for(99, levels).code == "suspect"
    assert lc.level_for(100, levels).code == "offender"
    assert lc.level_for(600, levels).code == "villain"
    assert lc.level_for(1000, levels).code == "enemy"
    assert lc.level_at_least(None, "criminal", levels).code == "criminal"
    assert lc.level_at_least(lc.level_for(150, levels), "criminal", levels).code == "criminal"
    assert lc.level_at_least(lc.level_for(950, levels), "criminal", levels).code == "enemy"
    assert lc.level_at_least(lc.level_for(150, levels), "nope", levels).code == "offender"


# =============================================================================================== options

@pytest.mark.parametrize("outlaw,has_jail,flee_used,expected", [
    (False, True, False, ["fine", "surrender", "flee", "fight"]),
    (False, True, True, ["fine", "surrender", "fight"]),
    (False, False, False, ["fine", "flee", "fight"]),
    (False, False, True, ["fine", "fight"]),
    (True, True, False, ["surrender", "fight"]),
    (True, True, True, ["surrender", "fight"]),
    (True, False, False, ["fight"]),                                   # outlaw without a jail: only the fight
])
def test_options_matrix(outlaw, has_jail, flee_used, expected):
    assert lc.options(outlaw, has_jail, flee_used) == expected


def test_chance_clamp_and_rounding():
    assert lc.chance(20, "0.25", 5, 85, 40, 20) == Decimal("35.00")
    assert lc.chance(20, "0.25", 5, 85, 400, 400) == Decimal("85.00")            # max clamp
    assert lc.chance(0, 0, 5, 85, 0, 0) == Decimal("5.00")                        # min clamp
    assert lc.chance(5, "0.15", 2, 50, 3, 0) == Decimal("5.45")
    assert lc.chance(20, "0.25", 5, 85, -50, -50) == Decimal("20.00")             # negative stats ignored


def test_roll_succeeds():
    assert lc.roll_succeeds(Decimal("35"), FixedRng(0.3499)) == (True, Decimal("34.99"))
    assert lc.roll_succeeds(Decimal("35"), FixedRng(0.35)) == (False, Decimal("35.00"))
    ok, roll = lc.roll_succeeds(Decimal("100"), FixedRng(0.999999))
    assert ok and roll == Decimal("99.99")


# =============================================================================================== jail maths

def test_extended_until_plus_half_and_cap_168():
    until = NOW + timedelta(hours=10)
    assert lc.extended_until(NOW, until, 50, 168) == NOW + timedelta(hours=15)
    long_until = NOW + timedelta(hours=150)
    assert lc.extended_until(NOW, long_until, 50, 168) == NOW + timedelta(hours=168)     # A4 cap
    assert lc.extended_until(NOW, NOW - timedelta(hours=1), 50, 168) == NOW               # already over


def test_failed_escape_never_shortens_the_term():
    """max_remaining_jail_hours may be set to 1..168 while a level term is up to 168 h: with the cap at 24 h a
    failed escape from a 72 h term leaves 24 h — failing to escape is rewarded."""
    until = NOW + timedelta(hours=72)
    assert lc.extended_until(NOW, until, 50, 24) >= until


def test_bail_price():
    assert lc.bail_price(150, 2) == 300
    assert lc.bail_price(50, Decimal("1.5")) == 75
    assert lc.bail_price(33, Decimal("1.5")) == 50                                         # ceil
    assert lc.bail_price(0, 2) == 1                                                        # never free


# =============================================================================================== validation

def _levels(**override):
    out = []
    for lv in lc.DEFAULT_LEVELS:
        values = dict(code=lv.code, sort_order=lv.sort_order, name=lv.name, min_value=lv.min_value, fine=lv.fine,
                      jail_hours=lv.jail_hours)
        values.update(override.get(lv.code, {}))
        out.append(lc.Level(**values))
    return out


def test_validate_defaults_ok():
    assert lc.validate(lc.DEFAULT_SETTINGS, list(lc.DEFAULT_LEVELS)) is None


@pytest.mark.parametrize("hours,ok", [(0, False), (1, True), (168, True), (169, False)])
def test_validate_jail_hours_1_168(hours, ok):
    err = lc.validate(lc.DEFAULT_SETTINGS, _levels(enemy={"jail_hours": hours}))
    assert (err is None) == ok
    if not ok:
        assert "168" in err


def test_validate_levels():
    assert lc.validate(lc.DEFAULT_SETTINGS, _levels()[:4]) == "Нужны ровно 5 ступеней розыска"
    assert "строго возрастать" in lc.validate(lc.DEFAULT_SETTINGS, _levels(offender={"min_value": 1}))
    assert "строго возрастать" in lc.validate(lc.DEFAULT_SETTINGS, _levels(suspect={"min_value": 0}))
    assert "превышать" in lc.validate(lc.DEFAULT_SETTINGS, _levels(enemy={"min_value": 1001}))
    assert "Штраф" in lc.validate(lc.DEFAULT_SETTINGS, _levels(enemy={"fine": -1}))
    assert "Название" in lc.validate(lc.DEFAULT_SETTINGS, _levels(enemy={"name": "   "}))


@pytest.mark.parametrize("field,value,fragment", [
    ("max_remaining_jail_hours", 169, "Предел срока"),
    ("max_remaining_jail_hours", 0, "Предел срока"),
    ("encounter_timeout_hours", 0, "Время на ответ"),
    ("heavy_wanted", 1001, "тяжёлого"),
    ("outlaw_min_level", "boss", "Вне закона"),
    ("flee_min_pct", Decimal(90), "минимум не может"),
    ("escape_max_pct", Decimal(101), "от 0 до 100"),
    ("bail_multiplier", Decimal("0.5"), "Множитель"),
    ("bail_multiplier", Decimal(11), "Множитель"),
    ("decay_per_day", Decimal(-1), "Спад"),
])
def test_validate_settings_bounds(field, value, fragment):
    from dataclasses import replace
    err = lc.validate(replace(lc.DEFAULT_SETTINGS, **{field: value}), list(lc.DEFAULT_LEVELS))
    assert err is not None and fragment in err


def test_settings_from_row_and_levels_fallback():
    assert lc.settings_from_row(None) == lc.DEFAULT_SETTINGS
    assert lc.levels_from_rows([]) == list(lc.DEFAULT_LEVELS)
    row = [1000, "50.00", 600, "criminal", 24, 6, "20", "0.25", "5", "85", "5", "0.15", "2", "50", 6, "50", 168, "2"]
    assert lc.settings_from_row(row) == lc.DEFAULT_SETTINGS


# =============================================================================================== activity lock

def test_lock_priority_jail_encounter_unconscious():
    future = NOW + timedelta(hours=2)
    lock = activity_lock.compute_lock(5, future, NOW, jailed_until=future, law_encounter_id=9)
    assert (lock["reason"], lock["until"], lock["law_encounter_id"]) == ("jail", future.isoformat(), None)
    lock = activity_lock.compute_lock(5, future, NOW, jailed_until=NOW - timedelta(seconds=1), law_encounter_id=9)
    assert (lock["reason"], lock["law_encounter_id"]) == ("law_encounter", 9)
    lock = activity_lock.compute_lock(5, future, NOW, law_encounter_id=None)
    assert lock["reason"] == "unconscious" and lock["law_encounter_id"] is None
    assert activity_lock.compute_lock(None, None, NOW, jailed_until=NOW)["locked"] is False   # past = free (lazy)
    assert activity_lock.compute_lock(None, None, NOW, law_encounter_id=0)["locked"] is False


def test_format_remaining():
    assert activity_lock.format_remaining(NOW + timedelta(days=2, hours=5, minutes=13), NOW) == "2 д 5 ч"
    assert activity_lock.format_remaining(NOW + timedelta(days=1), NOW) == "1 д"
    assert activity_lock.format_remaining(NOW + timedelta(hours=3, minutes=10), NOW) == "3 ч 10 мин"
    assert activity_lock.format_remaining(NOW + timedelta(minutes=12), NOW) == "12 мин"
    assert activity_lock.format_remaining(NOW - timedelta(minutes=5), NOW) == "1 мин"         # never «0 мин»


def test_lock_messages_relative_no_clock_time():
    until = (datetime.utcnow() + timedelta(hours=26, seconds=30)).isoformat()
    msg = activity_lock.lock_message({"locked": True, "reason": "jail", "until": until})
    assert msg == "Персонаж в тюрьме — осталось 1 д 2 ч"
    assert "МСК" not in msg and not re.search(r"\d\d:\d\d", msg)
    assert activity_lock.lock_message({"locked": True, "reason": "jail", "until": None}) == "Персонаж в тюрьме"
    assert activity_lock.lock_message({"locked": True, "reason": "law_encounter"}, subject="Альфа") == \
        "Альфа остановлен стражей — сначала нужно решить, как поступить"
    unc = activity_lock.lock_message({"locked": True, "reason": "unconscious",
                                      "until": (datetime.utcnow() + timedelta(minutes=30)).isoformat()})
    assert unc.startswith("Персонаж без сознания — осталось") and "МСК" not in unc


def test_lock_for_character_reads_law_columns():
    class C:
        dungeon_session_id = None
        unconscious_until = None
        jailed_until = datetime.utcnow() + timedelta(hours=1)
        law_encounter_id = None
    assert activity_lock.lock_for_character(C())["reason"] == "jail"
    C.jailed_until, C.law_encounter_id = None, 4
    assert activity_lock.lock_for_character(C())["law_encounter_id"] == 4


def test_law_player_texts_are_relative_durations():
    """§3.14-ANSWERED A8: the UI shows live countdowns, so the texts carry «срок 3 д 4 ч», never «до DD.MM МСК»."""
    import law_crud
    import law_flows
    import law_notify
    until = NOW + timedelta(days=3, hours=4)
    jailed = law_notify.jailed_message("Ост", until, NOW)
    assert jailed == "Стража края «Ост» заключила вас под стражу — срок 3 д 4 ч"
    stop = law_notify.encounter_message(None, NOW + timedelta(minutes=30), NOW)
    assert stop.endswith("Решите, как поступить, в течение 30 мин")
    assert law_crud._escape_message(False, NOW + timedelta(days=4, hours=2), NOW) == \
        "Побег не удался — срок увеличен, осталось 4 д 2 ч"
    assert law_crud.MSG_ESCAPE_COOLDOWN.format(time=activity_lock.format_remaining(
        NOW + timedelta(hours=5, minutes=10), NOW)) == "Следующая попытка побега — через 5 ч 10 мин"
    texts = [jailed, stop, law_flows.MSG_JAILED, law_flows.MSG_AUTO_JAIL, law_crud.MSG_ESCAPE_COOLDOWN]
    assert all("МСК" not in t and not re.search(r"\d\d[.:]\d\d", t) for t in texts)
    assert law_notify.remaining(None) == "—"
