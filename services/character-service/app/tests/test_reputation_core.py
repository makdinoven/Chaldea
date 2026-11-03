"""FEAT-197 QA (task 9): reputation_core pure maths + parity of the migration 038 seeds / DDL with the code.

The parity tests guard the "fixture of the wrong schema" trap: the ORM models (used by every SQLite test) and the
MySQL migration must name the same columns, and the migration seeds must equal the code defaults the SQLite tests
fall back to.
"""

import importlib.util
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

import models
import reputation_core as rc

NOW = datetime(2026, 11, 3, 12, 0, 0)
S = rc.DEFAULT_SETTINGS
T = list(rc.DEFAULT_TIERS)

_MIGRATION = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "038_reputation.py")


def _migration():
    spec = importlib.util.spec_from_file_location("mig_038_reputation", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------------------------- tiers

@pytest.mark.parametrize("value,code", [
    (-1000, "outlaw"), (-600, "outlaw"), (-599, "outcast"), (-300, "outcast"), (-299, "watched"),
    (-100, "watched"), (-99, "wanderer"), (0, "wanderer"), (99, "wanderer"), (100, "familiar"), (299, "familiar"),
    (300, "trusted"), (599, "trusted"), (600, "defender"), (899, "defender"), (900, "legend"), (1000, "legend"),
])
def test_tier_for_user_thresholds(value, code):
    assert rc.tier_for(value, T).code == code


def test_tier_for_ignores_input_order():
    assert rc.tier_for(350, list(reversed(T))).code == "trusted"


def test_meets_and_rank():
    assert rc.meets(300, "trusted", T) and not rc.meets(299, "trusted", T)
    assert rc.meets(-1000, None, T) and rc.meets(-1000, "", T)
    assert rc.meets(-1000, "no_such_tier", T)                  # unknown code = no gate
    assert rc.tier_rank("legend", T) == 8 and rc.tier_rank("x", T) is None


def test_gate_message_uses_the_tier_name():
    assert rc.gate_message("trusted", T) == "Нужна репутация: Свой человек"


@pytest.mark.parametrize("value,expected", [
    (0, 0.497), (-99, 0.0), (99, 0.995), (100, 0.0), (200, 0.5), (950, 0.5), (1000, 1.0), (-1000, 0.0),
    (-800, round(200 / 401, 3)),
])
def test_progress_inside_band(value, expected):
    assert rc.progress(value, T, S) == expected


def test_price_and_sell_modifiers():
    assert rc.tier_price_pct(950, T) == Decimal(15)
    assert rc.tier_price_pct(-400, T) == Decimal(-25)
    assert rc.tier_sell_pct(-200, T) == Decimal(-10)
    assert rc.tier_sell_pct(950, T) == Decimal(0)               # high tiers never raise bids
    assert rc.trade_refused(-600, T) and not rc.trade_refused(-599, T)


def test_tier_sell_pct_never_positive_even_if_misconfigured():
    tiers = [rc.Tier(t.code, t.sort_order, t.name, t.min_value, t.price_pct, Decimal(30), t.trade_refused)
             for t in T]
    assert rc.tier_sell_pct(0, tiers) == Decimal(0)


def test_tiers_from_rows_falls_back_without_all_codes():
    assert rc.tiers_from_rows([]) == list(T)
    partial = [("outlaw", 1, "X", None, 0, 0, 1)]
    assert rc.tiers_from_rows(partial) == list(T)
    full = [(t.code, t.sort_order, t.name + "!", t.min_value, t.price_pct, t.sell_pct, int(t.trade_refused))
            for t in reversed(T)]
    loaded = rc.tiers_from_rows(full)
    assert [t.code for t in loaded] == list(rc.TIER_CODES) and loaded[0].name == "Вне закона!"


def test_settings_from_row():
    assert rc.settings_from_row(None) == S
    s = rc.settings_from_row((-500, 500, "12.50", "3.00"))
    assert (s.min_value, s.max_value, s.echo_pct, s.decay_per_day) == (-500, 500, Decimal("12.50"), Decimal("3.00"))


# --------------------------------------------------------------------------------------------- deltas

@pytest.mark.parametrize("delta,pct,expected", [
    (10, 20, 2), (7, 20, 1), (-7, 20, -1), (4, 20, 0), (-4, 20, 0), (-150, 20, -30), (-1000, 20, -200),
    (100, 0, 0), (100, 100, 100), (3, "33.33", 0), (-9, "12.5", -1),
])
def test_echo_delta_truncates_toward_zero(delta, pct, expected):
    assert rc.echo_delta(delta, pct) == expected


def test_clamp():
    assert rc.clamp(5000, S) == 1000 and rc.clamp(-5000, S) == -1000 and rc.clamp(3, S) == 3


def test_kill_points_priority():
    w = dict(rc.DEFAULT_NPC_ROLE_WEIGHTS)
    assert rc.kill_points(None, "bandit", w) == 20
    assert rc.kill_points(None, "guard", w) == -300
    assert rc.kill_points(None, "king", w) == -1000
    assert rc.kill_points(None, "merchant", w) == -150
    assert rc.kill_points(None, None, w) == -150                # '*'
    assert rc.kill_points(None, "scribe", {"*": -77}) == -77
    assert rc.kill_points(40, "guard", w) == 40                 # override wins, may be positive
    assert rc.kill_points(0, "guard", w) == 0
    assert rc.kill_points(None, "x", {}) == -150                # no '*' row at all -> built-in fallback


def test_default_role_weights_match_the_user_decision():
    w = rc.DEFAULT_NPC_ROLE_WEIGHTS
    assert (w["bandit"], w["mercenary"], w["guard"], w["ruler"], w["king"], w["*"]) == (20, -30, -300, -1000,
                                                                                         -1000, -150)
    for role in ("merchant", "blacksmith", "alchemist", "bard", "sage", "priest", "healer", "hunter", "wanderer",
                 "auctioneer", "banker", "minter", "guild", "teleport_master", "hero"):
        assert w[role] == -150, role


# --------------------------------------------------------------------------------------------- decay

def test_decay_only_negative():
    assert rc.materialise_decay(50, NOW - timedelta(days=9), NOW, 10) == (50, None, 0)
    assert rc.materialise_decay(0, None, NOW, 10) == (0, None, 0)


def test_decay_no_anchor_zero_rate_or_future_anchor():
    assert rc.materialise_decay(-100, None, NOW, 10) == (-100, None, 0)
    anchor = NOW - timedelta(days=3)
    assert rc.materialise_decay(-100, anchor, NOW, 0) == (-100, anchor, 0)
    future = NOW + timedelta(hours=1)
    assert rc.materialise_decay(-100, future, NOW, 10) == (-100, future, 0)


def test_decay_moves_anchor_by_exactly_the_time_used():
    anchor = NOW - timedelta(days=1.55)
    new_value, new_anchor, points = rc.materialise_decay(-100, anchor, NOW, 10)
    assert (new_value, points) == (-85, 15)
    assert new_anchor == anchor + timedelta(days=1.5)           # 0.05 day remainder is kept
    assert rc.materialise_decay(new_value, new_anchor, NOW, 10) == (-85, new_anchor, 0)
    later = NOW + timedelta(days=0.05)
    assert rc.materialise_decay(new_value, new_anchor, later, 10)[:1] == (-84,)


def test_decay_stops_at_zero_and_clears_anchor():
    assert rc.materialise_decay(-30, NOW - timedelta(days=100), NOW, 10) == (0, None, 30)


def test_decay_frequent_runs_lose_no_fractions():
    start = NOW - timedelta(days=10)
    v, a = -500, start
    t = start
    for _ in range(10 * 24 * 7):                                 # every 7 minutes (≈ 8.2 days)
        t = t + timedelta(minutes=7)
        v, a, _p = rc.materialise_decay(v, a, t, 10)
    single = rc.materialise_decay(-500, start, t, 10)[0]
    # 1680 × 7 min = 11760 min = 8.1666 days -> floor(81.66) = 81 points, whether in one call or in 1680
    assert v == single == -419


def test_decay_fractional_rate():
    v, a, p = rc.materialise_decay(-100, NOW - timedelta(days=4), NOW, "2.5")
    assert (v, p, a) == (-90, 10, NOW)


def test_decay_accepts_sqlite_string_anchor():
    anchor = (NOW - timedelta(days=2)).isoformat(sep=" ")
    assert rc.materialise_decay(-100, anchor, NOW, 10)[:1] == (-80,)


def test_effective_value_matches_materialise():
    assert rc.effective_value(-100, NOW - timedelta(days=3), NOW, 10) == -70
    assert rc.effective_value(200, None, NOW, 10) == 200


def test_next_decay_at():
    old_anchor = NOW - timedelta(days=1)
    assert rc.next_decay_at(0, -10, None, NOW) == NOW
    assert rc.next_decay_at(-10, -20, old_anchor, NOW) == old_anchor
    assert rc.next_decay_at(-10, 5, old_anchor, NOW) is None
    assert rc.next_decay_at(-10, -5, None, NOW) == NOW


# --------------------------------------------------------------------------------------------- validation

def _tiers(**changes):
    out = []
    for t in T:
        c = changes.get(t.code, {})
        out.append(rc.Tier(t.code, c.get("sort_order", t.sort_order), c.get("name", t.name),
                           c.get("min_value", t.min_value), Decimal(str(c.get("price_pct", t.price_pct))),
                           Decimal(str(c.get("sell_pct", t.sell_pct))), c.get("trade_refused", t.trade_refused)))
    return out


def test_validate_defaults_ok():
    assert rc.validate(S, T) is None


@pytest.mark.parametrize("settings,tiers", [
    (rc.Settings(min_value=0, max_value=1000), T),
    (rc.Settings(min_value=-1000, max_value=-1), T),
    (rc.Settings(min_value=-10 ** 6, max_value=1000), T),
    (rc.Settings(echo_pct=Decimal(101)), T),
    (rc.Settings(echo_pct=Decimal(-1)), T),
    (rc.Settings(decay_per_day=Decimal(-1)), T),
    (rc.Settings(decay_per_day=Decimal(1001)), T),
    (S, T[:7]),
    (S, _tiers(outlaw={"min_value": -900})),
    (S, _tiers(outcast={"min_value": None})),
    (S, _tiers(watched={"min_value": -700})),               # not strictly increasing
    (S, _tiers(legend={"min_value": 1001})),                # above max_value
    (S, _tiers(trusted={"price_pct": 51})),
    (S, _tiers(outcast={"price_pct": -101})),
    (S, _tiers(watched={"sell_pct": 1})),
    (S, _tiers(watched={"sell_pct": -101})),
    (S, _tiers(trusted={"name": "  "})),
    (S, _tiers(trusted={"name": "x" * 61})),
    (S, _tiers(wanderer={"min_value": 1})),                 # 0 no longer in the start tier
    (S, _tiers(trusted={"sort_order": 7}, defender={"sort_order": 6})),
])
def test_validate_rejects(settings, tiers):
    assert rc.validate(settings, tiers)


def test_validate_allows_renames_and_refusal_on_any_tier():
    assert rc.validate(S, _tiers(legend={"name": "Свет края"}, outcast={"trade_refused": True})) is None


def test_action_and_role_regexes_reject_injection():
    assert re.match(rc.ACTION_CODE_RE, "bribe_guard")
    for bad in ("x'; DROP TABLE reputation_log; --", "AB", "1abc", "ab", "a" * 41, "a-b-c"):
        assert not re.match(rc.ACTION_CODE_RE, bad), bad
    assert re.match(rc.ROLE_RE, "*") and re.match(rc.ROLE_RE, "teleport_master")
    assert not re.match(rc.ROLE_RE, "guard' OR 1=1")


# --------------------------------------------------------------------------------------------- migration parity

def test_migration_revision_id_fits_mysql_limit():
    mig = _migration()
    assert mig.revision == "038_reputation" and len(mig.revision) <= 32
    assert mig.down_revision == "037_econ_social_classes"


def test_migration_tier_seeds_equal_code_defaults():
    mig = _migration()
    seeded = [rc.Tier(code, order, name, min_value, Decimal(price), Decimal(sell), bool(refused))
              for code, order, name, min_value, price, sell, refused in mig.TIERS]
    assert seeded == list(rc.DEFAULT_TIERS)
    assert rc.validate(rc.DEFAULT_SETTINGS, seeded) is None


def test_migration_action_and_role_seeds_equal_code_defaults():
    mig = _migration()
    assert [(c, n, p, cap, bool(src), o) for c, n, p, cap, src, o in mig.ACTIONS] == \
        [(c, n, p, cap, bool(src), o) for c, n, p, cap, src, o in rc.DEFAULT_ACTIONS]
    assert dict(mig.ROLE_WEIGHTS) == rc.DEFAULT_NPC_ROLE_WEIGHTS
    assert len(mig.ROLE_WEIGHTS) == len(dict(mig.ROLE_WEIGHTS))      # no duplicate role rows


def test_migration_settings_seed_matches_answered_defaults():
    src = open(_MIGRATION, encoding="utf-8").read()
    assert "SELECT 1, -1000, 1000, 20.00, 10.00" in src              # §3.14 A2: 10 points/day
    assert rc.DEFAULT_SETTINGS.decay_per_day == Decimal(10)


def _ddl_columns(src, table):
    m = re.search(r"CREATE TABLE IF NOT EXISTS %s \((.*?)\n\s*\) \{_TABLE_OPTS\}" % table, src, re.S)
    assert m, table
    cols = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.split()[0] in ("UNIQUE", "KEY", "CONSTRAINT", "PRIMARY"):
            continue
        cols.append(line.split()[0])
    return set(cols)


@pytest.mark.parametrize("table,model", [
    ("character_reputation", "CharacterReputation"), ("reputation_log", "ReputationLog"),
    ("reputation_settings", "ReputationSettings"), ("reputation_tiers", "ReputationTier"),
    ("reputation_actions", "ReputationAction"), ("reputation_npc_role_weights", "ReputationNpcRoleWeight"),
])
def test_migration_ddl_columns_equal_orm_columns(table, model):
    src = open(_MIGRATION, encoding="utf-8").read()
    orm = getattr(models, model).__table__
    assert orm.name == table
    assert _ddl_columns(src, table) == {c.name for c in orm.columns}


def test_migration_added_columns_exist_on_orm_models():
    mig = _migration()
    tables = {"characters": models.Character, "econ_banks": models.EconBank, "teleport_links": models.TeleportLink}
    for table, cols in mig._COLUMNS.items():
        orm_cols = {c.name for c in tables[table].__table__.columns}
        for column, _ddl in cols:
            assert column in orm_cols, (table, column)


def test_sql_constants_select_existing_columns():
    tiers = {c.name for c in models.ReputationTier.__table__.columns}
    for col in ("code", "sort_order", "name", "min_value", "price_pct", "sell_pct", "trade_refused"):
        assert col in tiers and col in rc.SQL_SELECT_TIERS
    for col in ("min_value", "max_value", "echo_pct", "decay_per_day"):
        assert col in rc.SQL_SELECT_SETTINGS
