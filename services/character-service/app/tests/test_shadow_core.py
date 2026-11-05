"""FEAT-199 QA (task 7): shadow_core pure maths + the migration 040 contract.

* witness (FEAT-201, multiplicative): base by marker type × (1 − stealth reduction) × fame (a masked member is
  anonymous), subclass stealth points before the cap, group = max member × size multiplier, clamps 5..100;
* reveal chance (suspicion, mask factor, clamps), suspicion states, infamy gain, fame from reputation per action;
* renown tiers / progress, settings row / tier row loaders, settings validation;
* law_core.chance with Decimal (effective) points; stat_caps effective values;
* migration 040 (+ the 041 column swap): revision id, seeds == code defaults, DDL columns == ORM columns.
"""

import importlib.util
import os
import re
from decimal import Decimal

import pytest

import law_core as lc
import models
import shadow_core as sc
import stat_caps

S = sc.DEFAULT_SETTINGS
D = Decimal


def _s(**kw):
    values = {name: getattr(S, name) for name in sc.SETTINGS_FIELDS}
    values.update(kw)
    return sc.ShadowSettings(**values)


# =============================================================================================== witnesses

@pytest.mark.parametrize("marker,expected", [
    ("safe", 100), ("farm", 70), ("dangerous", 40), ("dungeon", 25), (None, 50), ("", 50), ("volcano", 50),
])
def test_base_pct_by_marker(marker, expected):
    assert sc.base_pct(marker, S) == D(expected)


@pytest.mark.parametrize("key,expected", [
    ("warrior_agent", 20), ("rogue_assassin", 30), ("rogue_trickster", 30), ("warrior_berserk", 0), (None, 0),
    ("ROGUE_ASSASSIN", 0),
])
def test_subclass_stealth_points_only_for_the_three_keys(key, expected):
    assert sc.subclass_stealth_points(key, S) == expected


@pytest.mark.parametrize("raw,points,eff", [
    (0, 0, "0.00"), (100, 0, "100.00"), (0, 30, "30.00"), (100, 30, "115.00"), (400, 0, "200.00"), (-20, 30, "30.00"),
])
def test_effective_stealth_adds_subclass_before_the_cap(raw, points, eff):
    assert sc.effective_stealth(raw, points) == D(eff)


@pytest.mark.parametrize("eff,expected", [("0", "0.00"), ("100", "50.00"), ("115", "57.50"), ("200", "90.00"),
                                          ("-5", "0.00")])
def test_stealth_reduction_pct(eff, expected):
    assert sc.stealth_reduction_pct(D(eff), S) == D(expected)


def _alone(base, raw, subclass=None, masked=False, fame=0):
    red = sc.stealth_reduction_pct(sc.effective_stealth(raw, sc.subclass_stealth_points(subclass, S)), S)
    return sc.group_chance([sc.member_chance(base, red, masked, fame)], 1, S)


@pytest.mark.parametrize("base,raw,subclass,masked,fame,expected", [
    (100, 0, None, False, 0, "100.00"),                # settlement, stealth 0: reaches 100
    (100, 100, None, False, 0, "50.00"),
    (40, 100, None, False, 0, "20.00"),
    (100, 0, "rogue_assassin", False, 0, "85.00"),
    (100, 100, "rogue_assassin", False, 0, "42.50"),
    (100, 400, None, False, 0, "10.00"),               # reduction capped at 90
    (25, 400, None, False, 0, "5.00"),                 # 2.50 -> min clamp
    (40, 0, None, False, 15, "46.00"),                 # legend fame multiplier
    (40, 0, None, True, 15, "40.00"),                  # masked: fame ignored, no flat mask bonus
])
def test_witness_worked_numbers(base, raw, subclass, masked, fame, expected):
    assert _alone(base, raw, subclass, masked, D(fame)) == D(expected)


def test_member_chance_formula():
    assert sc.member_chance(70, D(50), False, 0) == D(35)
    assert sc.member_chance(70, D(50), False, D(10)) == D("38.5")
    assert sc.member_chance(70, D(0), True, D(10)) == D(70)


def test_member_chance_reduction_is_bounded():
    assert sc.member_chance(70, D(-20), False, 0) == D(70)
    assert sc.member_chance(70, D(150), False, 0) == D(0)


def test_member_chance_is_unclamped():
    assert sc.member_chance(200, D(0), False, D(50)) == D(300)


def test_group_chance_max_member_times_size_multiplier():
    assert sc.group_chance([D(50), D(20)], 2, S) == D("55.00")
    assert sc.group_chance([D(30)], 1, S) == D("30.00")
    assert sc.group_chance([D(30), D(20), D(10)], 3, S) == D("36.00")


@pytest.mark.parametrize("chances,n,expected", [
    ([D(-30)], 1, "5.00"), ([D(4.99)], 1, "5.00"), ([D(90)], 3, "100.00"), ([D(200)], 1, "100.00"),
    ([D("12.345")], 1, "12.35"),
])
def test_group_chance_clamps_and_rounds(chances, n, expected):
    assert sc.group_chance(chances, n, S) == D(expected)


def test_group_chance_custom_bounds():
    s = _s(witness_min_pct=D(20), witness_max_pct=D(60))
    assert sc.group_chance([D(1)], 1, s) == D(20) and sc.group_chance([D(99)], 1, s) == D(60)


def test_group_chance_without_members_is_the_default_base():
    assert sc.group_chance([], 0, S) == D("50.00")


# =============================================================================================== reveal / suspicion

@pytest.mark.parametrize("susp,masked,expected", [
    (0, False, "15.00"), (50, False, "35.00"), (50, True, "17.50"), (0, True, "7.50"), (500, False, "90.00"),
    (-30, False, "15.00"), (None, False, "15.00"),
])
def test_reveal_chance(susp, masked, expected):
    assert sc.reveal_chance(susp, masked, S) == D(expected)


def test_reveal_chance_min_clamp():
    assert sc.reveal_chance(0, True, _s(reveal_mask_factor_pct=D(0))) == D("1.00")


@pytest.mark.parametrize("masked,snapshot,expected", [
    (False, D(50), "17.50"), (True, D(50), "8.75"), (False, None, "35.00"), (False, 0, "35.00"),
    (False, D(90), "3.50"),
])
def test_reveal_chance_times_stealth_snapshot(masked, snapshot, expected):
    assert sc.reveal_chance(50, masked, S, snapshot) == D(expected)


@pytest.mark.parametrize("value,expected", [
    (0, None), (19, None), (20, ("uneasy", "В крае неспокойно")), (49, ("uneasy", "В крае неспокойно")),
    (50, ("alarmed", "Край встревожен")), (80, ("fear", "Край охвачен страхом")), (100, ("fear", "Край охвачен страхом")),
])
def test_suspicion_state_labels(value, expected):
    assert sc.suspicion_state(value, S) == expected


def test_add_suspicion_clamps():
    assert sc.add_suspicion(95, 20, S) == 100
    assert sc.add_suspicion(0, 10, S) == 10
    assert sc.add_suspicion(5, -50, S) == 0


@pytest.mark.parametrize("points,ratio,min_gain,expected", [
    (150, 1, 10, 150), (0, 1, 10, 10), (5, 1, 10, 10), (151, D("0.5"), 10, 75), (40, 2, 0, 80), (0, 1, 0, 0),
])
def test_infamy_gain(points, ratio, min_gain, expected):
    assert sc.infamy_gain(points, _s(infamy_ratio=D(str(ratio)), infamy_min_gain=min_gain)) == expected


@pytest.mark.parametrize("action,delta,expected", [
    ("npc_kill", 20, 10), ("npc_kill", 1, 0), ("npc_kill", -150, 0), ("npc_kill", 0, 0), ("quest_complete", 10, 0),
    ("guild_delivery", 2, 0), ("staff_adjust", 9, 4),
])
def test_fame_from_reputation_default_ratios(action, delta, expected):
    assert sc.fame_from_reputation(action, delta, S) == expected


def test_fame_from_reputation_guild_ratio_configurable():
    assert sc.fame_from_reputation("guild_delivery", 4, _s(fame_guild_ratio=D(1))) == 4
    assert sc.fame_from_reputation("npc_kill", 4, _s(fame_rep_ratio=D(0))) == 0


# =============================================================================================== renown tiers

FAME = sc.scale_tiers(sc.DEFAULT_TIERS, "fame")
INFAMY = sc.scale_tiers(sc.DEFAULT_TIERS, "infamy")


@pytest.mark.parametrize("value,code", [
    (0, "nameless"), (49, "nameless"), (50, "familiar"), (199, "familiar"), (200, "known"), (600, "famous"),
    (1499, "famous"), (1500, "legend"), (10 ** 7, "legend"), (None, "nameless"),
])
def test_fame_tier_for(value, code):
    assert sc.renown_tier_for(value, FAME).code == code


def test_infamy_tiers_and_no_witness_pct():
    assert [t.code for t in INFAMY] == list(sc.INFAMY_CODES)
    assert sc.renown_tier_for(2500, INFAMY).code == "dreaded"
    assert all(t.witness_pct == 0 for t in INFAMY)
    assert [t.witness_pct for t in FAME] == [D(0), D(2), D(5), D(10), D(15)]


def test_renown_progress_and_next():
    familiar = sc.renown_tier_for(125, FAME)
    assert sc.renown_progress(125, familiar, FAME) == 0.5
    legend = sc.renown_tier_for(5000, FAME)
    assert sc.renown_progress(5000, legend, FAME) == 1.0 and sc.next_tier(legend, FAME) is None
    assert sc.next_tier(familiar, FAME).code == "known"
    assert sc.renown_progress(0, FAME[0], FAME) == 0.0


def test_settings_from_row():
    assert sc.settings_from_row(None) is sc.DEFAULT_SETTINGS
    row = [getattr(S, n) for n in sc.SETTINGS_FIELDS]
    row[sc.SETTINGS_FIELDS.index("witness_enabled")] = 0
    row[sc.SETTINGS_FIELDS.index("reveal_days")] = "5"
    row[sc.SETTINGS_FIELDS.index("witness_base_safe_pct")] = 66.5
    s = sc.settings_from_row(row)
    assert s.witness_enabled is False and s.reveal_days == 5 and s.witness_base_safe_pct == D("66.5")


def test_tiers_from_rows_falls_back_per_scale():
    assert sc.tiers_from_rows([]) == list(sc.DEFAULT_TIERS)
    rows = [("fame", c, i + 1, f"F{i}", i * 10, 1) for i, c in enumerate(sc.FAME_CODES)]
    tiers = sc.tiers_from_rows(rows)
    assert [t.name for t in sc.scale_tiers(tiers, "fame")] == ["F0", "F1", "F2", "F3", "F4"]
    assert sc.scale_tiers(tiers, "infamy") == INFAMY


# =============================================================================================== validation

def test_defaults_are_valid():
    assert sc.validate(S, sc.DEFAULT_TIERS) is None


@pytest.mark.parametrize("kw,fragment", [
    ({"witness_base_safe_pct": D(101)}, "от 0 до 100"),
    ({"stealth_max_reduction_pct": D(101)}, "Предел снижения скрытностью"),
    ({"stealth_max_reduction_pct": D(-1)}, "от 0 до 100"),
    ({"stealth_assassin_points": 501}, "Скрытность подкласса «Ассасин»"),
    ({"stealth_trickster_points": -1}, "Скрытность подкласса «Фокусник»"),
    ({"stealth_agent_points": 501}, "Скрытность подкласса «Агент»"),
    ({"witness_max_pct": D(101)}, "от 0 до 100"),
    ({"witness_min_pct": D(60), "witness_max_pct": D(50)}, "минимум не может быть больше максимума"),
    ({"reveal_min_pct": D(60), "reveal_max_pct": D(50)}, "минимум не может быть больше максимума"),
    ({"stealth_pct_per_point": D(11)}, "Снижение за очко скрытности: от 0 до 10"),
    ({"reveal_days": 0}, "Срок раскрытия"), ({"reveal_days": 31}, "Срок раскрытия"),
    ({"suspicion_max": 0}, "Максимальное подозрение"),
    ({"suspicion_unwitnessed": 101}, "Подозрение за незамеченное"),
    ({"suspicion_decay_per_day": D(-1)}, "Спад подозрения"),
    ({"suspicion_uneasy_at": 50, "suspicion_alarmed_at": 50}, "Пороги подозрения"),
    ({"suspicion_fear_at": 101}, "Пороги подозрения"),
    ({"suspicion_uneasy_at": 0}, "Пороги подозрения"),
    ({"infamy_ratio": D(11)}, "Множитель дурной славы"),
    ({"fame_quest_default": 1001}, "Слава за задание"),
    ({"infamy_min_gain": -1}, "Минимальная дурная слава"),
])
def test_validate_rejects(kw, fragment):
    error = sc.validate(_s(**kw), sc.DEFAULT_TIERS)
    assert error is not None and fragment in error


def _tiers(changes):
    out = []
    for t in sc.DEFAULT_TIERS:
        patch = changes.get((t.scale, t.code), {})
        out.append(sc.RenownTier(t.scale, patch.get("code", t.code), t.sort_order, patch.get("name", t.name),
                                 patch.get("min_value", t.min_value), patch.get("witness_pct", t.witness_pct)))
    return out


@pytest.mark.parametrize("changes,fragment", [
    ({("fame", "nameless"): {"min_value": 1}}, "должна начинаться с 0"),
    ({("fame", "known"): {"min_value": 50}}, "строго возрастать"),
    ({("infamy", "dreaded"): {"min_value": 999}}, "строго возрастать"),
    ({("fame", "legend"): {"witness_pct": D(51)}}, "Узнаваемость"),
    ({("fame", "legend"): {"name": "   "}}, "Название ступени"),
    ({("fame", "legend"): {"name": "x" * 61}}, "Название ступени"),
    ({("fame", "legend"): {"code": "godlike"}}, "ровно 5 ступеней"),
    ({("fame", "legend"): {"min_value": 10 ** 8}}, "слишком большой"),
])
def test_validate_tiers(changes, fragment):
    error = sc.validate(S, _tiers(changes))
    assert error is not None and fragment in error


def test_validate_missing_tier():
    assert "ровно 5" in sc.validate(S, [t for t in sc.DEFAULT_TIERS if t.code != "dreaded"])


def test_infamy_witness_pct_is_ignored_by_validation():
    assert sc.validate(S, _tiers({("infamy", "dreaded"): {"witness_pct": D(99)}})) is None


# =============================================================================================== effective stats

@pytest.mark.parametrize("raw,eff", [(0, 0), (100, 100), (150, 125), (200, 150), (300, 175), (-5, -5)])
def test_stat_caps_copy(raw, eff):
    assert stat_caps.effective_stat(raw) == eff


def test_law_chance_accepts_decimal_points_and_ints_unchanged():
    assert lc.chance(10, D(1), 0, 100, D("12.5"), 3) == D("25.50")
    assert lc.chance(10, D(1), 0, 100, D("12.5")) == D("22.50")              # FEAT-201: one stat (escape)
    assert lc.chance(20, D("0.25"), 5, 85, 40, 20) == D("35.00")
    assert lc.chance(20, D("0.25"), 5, 85, D(40), D(20)) == D("35.00")


# =============================================================================================== migration 040

_VERSIONS = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")


def _mig040():
    spec = importlib.util.spec_from_file_location("migration_040_shadow_renown",
                                                  os.path.join(_VERSIONS, "040_shadow_renown.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_revision():
    mig = _mig040()
    assert mig.revision == "040_shadow_renown" and len(mig.revision) <= 32
    assert mig.down_revision == "039_law"


def test_migration_tier_seeds_equal_code_defaults():
    mig = _mig040()
    assert [(s, c, o, n, m, D(w)) for s, c, o, n, m, w in mig.TIERS] == \
        [(t.scale, t.code, t.sort_order, t.name, t.min_value, t.witness_pct) for t in sc.DEFAULT_TIERS]


def _ddl_columns(sql_text, table):
    body = re.search(r"CREATE TABLE IF NOT EXISTS %s \((.*?)\n        \) " % table, sql_text, re.S).group(1)
    cols = {}
    for line in body.splitlines():
        line = line.strip().rstrip(",")
        if not line or line.split()[0] in ("UNIQUE", "KEY", "CONSTRAINT", "ON", "PRIMARY"):
            continue
        cols[line.split()[0]] = line
    return cols


@pytest.mark.parametrize("table", ["shadow_settings", "region_suspicion", "character_renown", "renown_tiers",
                                   "renown_log"])
def test_migration_ddl_columns_equal_orm(table):
    text_ = open(_mig040().__file__, encoding="utf-8").read()
    cols = _ddl_columns(text_, table)
    if table == "shadow_settings":
        cols = _apply_041(cols)
    assert set(cols) == set(models.Base.metadata.tables[table].columns.keys())


def _mig041():
    spec = importlib.util.spec_from_file_location("migration_041_stealth", os.path.join(_VERSIONS, "041_stealth.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply_041(cols):
    """The 040 shadow_settings DDL after 041: old knobs dropped, stealth columns added, bases / max re-defaulted."""
    mig = _mig041()
    cols = {k: v for k, v in cols.items() if k not in {c for c, _ in mig._OLD_SHADOW_COLUMNS}}
    for column, ddl in mig._NEW_SHADOW_COLUMNS:
        cols[column] = f"{column} {ddl}"
    for column, new, _old in mig._BASES:
        cols[column] = f"{column} DECIMAL(5,2) NOT NULL DEFAULT {new}"
    return cols


def test_migration_settings_defaults_equal_code_defaults():
    text_ = open(_mig040().__file__, encoding="utf-8").read()
    cols = _apply_041(_ddl_columns(text_, "shadow_settings"))
    for name in sc.SETTINGS_FIELDS:
        default = re.search(r"DEFAULT (\S+)", cols[name]).group(1)
        value = getattr(S, name)
        if isinstance(value, bool):
            assert int(default) == int(value), name
        else:
            assert D(default) == D(str(value)), name
    assert set(sc.SETTINGS_FIELDS) | {"id", "updated_at"} == set(cols)


def test_migration_crime_columns_on_orm_and_index():
    mig = _mig040()
    crime_cols = set(models.Base.metadata.tables["law_crimes"].columns.keys())
    assert {c for c, _ in mig._CRIME_COLUMNS} <= crime_cols
    text_ = open(mig.__file__, encoding="utf-8").read()
    assert "CREATE INDEX ix_law_crime_reveal ON law_crimes (status, next_roll_at)" in text_
    # no ALTER of `items` / no ENUM column type (memory: «ENUM на items»)
    assert "ALTER TABLE items" not in text_ and not re.search(r"\bENUM\s*\(", text_)
