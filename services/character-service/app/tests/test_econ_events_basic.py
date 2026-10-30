"""FEAT-187 B2: basic tests of the pure region-events module, the ``mods`` hook of the sim, the 10 sim params and the
starter seed of migration 033. (QA extends these in ``test_econ_events.py``.)"""

import importlib.util
import os
import random
from dataclasses import asdict
from datetime import datetime, timedelta

import pytest

import econ_events as E
import econ_sim as S
from schemas import ECON_SIM_INT_PARAMS, ECON_SIM_PARAM_BOUNDS, EconSimParamsIn

VERSIONS = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")


def _load(filename, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(VERSIONS, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mig028 = _load("028_econ_living_regions.py", "migration_028_for_events")
mig033 = _load("033_econ_region_events.py", "migration_033_for_events")

GROUPS = {
    code: S.GroupDef(code=code, name=name, base_price=base, norm_per_1000=norm, norm_days=days,
                     prosperity_elasticity=pe, price_elasticity=pr, is_food=bool(food),
                     inputs=dict(mig028.INPUTS.get(code, [])))
    for code, name, base, norm, days, pe, pr, food in mig028.GROUPS
}
GROUP_CODES = list(GROUPS)
TEMPLATES = {t[0]: t for t in mig028.TEMPLATES}
EVENT_PARAMS = ("events_enabled", "event_rate_per_season", "event_season_days", "event_max_active",
                "event_mult_min", "event_mult_max", "event_delta_max", "event_spread_max_depth",
                "event_riot_stability", "event_riot_after_days")


def _region(code="agrarian"):
    pop = TEMPLATES[code][5]
    tgoods = {g: (prod, cmult) for g, prod, cmult in mig028.template_goods(code)}
    goods = S.starting_goods(GROUPS, tgoods, pop)
    purse = S.starting_purse(GROUPS, goods, pop)
    return S.RegionState(population=pop * 100, tax_rate=TEMPLATES[code][6]), goods, purse


def _run(mods, ticks=20, code="agrarian"):
    region, goods, purse = _region(code)
    treasury = 0
    out = []
    for _ in range(ticks):
        kwargs = {} if mods == "absent" else {"mods": mods}
        r = S.simulate_region(region, goods, GROUPS, purse=purse, treasury=treasury, grant=0,
                              country_tax_rate=0.1, params=S.DEFAULT_PARAMS, **kwargs)
        out.append(asdict(r))
        region, goods, purse, treasury = r.region, r.goods, r.purse_after, r.treasury_after
    return out


# --------------------------------------------------------------------------------------------- sim hook

@pytest.mark.parametrize("code", ["agrarian", "capital", "mining"])
def test_mods_none_and_identity_are_bit_identical(code):
    base = _run("absent", code=code)
    assert _run(None, code=code) == base
    assert _run(S.RegionModifiers(), code=code) == base


def test_levers_move_outputs():
    region, goods, purse = _region()
    kw = dict(purse=purse, treasury=0, grant=0, country_tax_rate=0.1, params=S.DEFAULT_PARAMS)
    base = S.simulate_region(region, goods, GROUPS, **kw)
    low_food = S.simulate_region(region, goods, GROUPS, mods=S.RegionModifiers(production={"food": 0.5}), **kw)
    assert low_food.goods["food"].last_produced == pytest.approx(base.goods["food"].last_produced * 0.5)
    pricey = S.simulate_region(region, goods, GROUPS, mods=S.RegionModifiers(price={"food": 1.5}), **kw)
    assert pricey.goods["food"].price_mult > base.goods["food"].price_mult
    assert pricey.goods["food"].price_mult <= S.DEFAULT_PARAMS.price_max
    taxed = S.simulate_region(region, goods, GROUPS, mods=S.RegionModifiers(tax_income_mult=0.5), **kw)
    assert taxed.tax < base.tax
    calm = S.simulate_region(region, goods, GROUPS, mods=S.RegionModifiers(stability_delta=-5,
                                                                           prosperity_delta=3), **kw)
    assert calm.region.stability == pytest.approx(base.region.stability - 5)
    assert calm.region.prosperity > base.region.prosperity
    # inputs are not mutated
    assert goods["food"].production_per_1000 == base.goods["food"].production_per_1000


# --------------------------------------------------------------------------------------------- params

def test_event_params_defaults_and_bounds():
    p = S.DEFAULT_PARAMS
    assert (p.events_enabled, p.event_rate_per_season, p.event_season_days, p.event_max_active) == (1, 1.0, 49.0, 3)
    for name in EVENT_PARAMS:
        lo, hi = ECON_SIM_PARAM_BOUNDS[name]
        assert lo <= getattr(p, name) <= hi
        assert name in EconSimParamsIn.__fields__
    assert {"events_enabled", "event_max_active", "event_spread_max_depth"} <= ECON_SIM_INT_PARAMS
    assert S.SimParams.from_mapping({"event_max_active": "5"}).event_max_active == 5
    with pytest.raises(Exception):
        EconSimParamsIn(event_rate_per_season=11)


# --------------------------------------------------------------------------------------------- parse / aggregate

def test_parse_effects_is_lenient_and_clamps():
    effects = E.parse_effects([
        {"type": "production", "groups": ["food"], "mult": 9},
        {"type": "nonsense"},
        {"type": "price", "groups": [], "mult": 2},
        {"type": "stability", "delta": "x"},
        {"type": "merchants_halt"},
        "junk",
    ])
    assert effects == [E.Effect("production", groups=("food",), mult=5.0), E.Effect("merchants_halt")]
    assert E.parse_effects(None) == [] and E.parse_effects("not json") == []


def test_aggregate_stacking_and_caps():
    params = S.DEFAULT_PARAMS
    drought = [E.Effect("production", groups=("food",), mult=0.5), E.Effect("stability", delta=-6)]
    plague = [E.Effect("labor", mult=0.75), E.Effect("stability", delta=-6)]
    ev = E.aggregate([drought, plague], GROUP_CODES, params)
    assert ev.mods.production["food"] == pytest.approx(0.375)
    assert ev.mods.production["wood"] == pytest.approx(0.75)          # labor hits every group
    assert ev.mods.stability_delta == -params.event_delta_max          # -12 capped at -10
    third = [E.Effect("production", groups=("food",), mult=0.2)]
    assert E.aggregate([drought, plague, third], GROUP_CODES, params).mods.production["food"] == 0.1
    empty = E.aggregate([], GROUP_CODES, params)
    assert empty.mods == S.RegionModifiers() and not empty.merchants_halt and empty.loan_boom_mult == 1.0
    star = E.aggregate([[E.Effect("price", groups=("*",), mult=1.2)]], GROUP_CODES, params)
    assert set(star.mods.price) == set(GROUP_CODES)


def test_merchant_and_bank_params_do_not_leak():
    params = S.DEFAULT_PARAMS
    ev = E.aggregate([[E.Effect("merchants_halt"), E.Effect("bank_panic"), E.Effect("loan_boom", mult=2)]],
                     GROUP_CODES, params)
    assert E.merchant_params(params, ev).merchant_take_share == 0.0
    bp = E.bank_params(params, ev)
    assert bp.bank_resident_deposit_share == 0.0
    assert bp.bank_resident_loan_share == pytest.approx(params.bank_resident_loan_share * 2)
    assert params.merchant_take_share == 0.25 and params.bank_resident_deposit_share == 0.2
    none = E.aggregate([], GROUP_CODES, params)
    assert E.merchant_params(params, none) is params and E.bank_params(params, none) is params


# --------------------------------------------------------------------------------------------- one-shots

def test_one_shots_and_helpers():
    shots = E.one_shots([E.Effect("stock_loss", groups=("food",), share=0.5),
                         E.Effect("stock_loss", groups=("food",), share=0.5),
                         E.Effect("treasury_expense", share=0.6), E.Effect("treasury_expense", share=0.6),
                         E.Effect("population", pct=-0.03)])
    assert shots.stock_loss["food"] == pytest.approx(0.75)
    assert shots.treasury_share == 0.9 and shots.population_pct == pytest.approx(-0.03)
    assert E.stock_after_loss(100, 0.25) == (75.0, 25.0)
    assert E.treasury_expense(-500, 0.5) == 0 and E.treasury_expense(1001, 0.1) == 100
    assert E.population_after(1_000_000, -0.03, 100) == 970_000
    assert E.population_after(1_000_000, 0, 100) == 1_000_000
    assert E.population_after(150, -0.5, 100) == 100                 # floor = scale
    assert E.population_after(50, -0.5, 100) == 50                   # already below floor: never raised
    assert E.population_after(1000, 0.003, 100) == 1003


# --------------------------------------------------------------------------------------------- rolls

def test_tick_chance_and_per_tick_chance():
    assert E.tick_chance(S.DEFAULT_PARAMS) == pytest.approx(1 / 196)
    assert E.tick_chance(S.SimParams(event_rate_per_season=0)) == 0
    assert E.tick_chance(S.SimParams(event_rate_per_season=10, event_season_days=1)) == 1.0
    dur = 10 * E.DAY
    per = E.per_tick_chance(0.3, dur)
    assert 1 - (1 - per) ** (dur / E.TICK_SECONDS) == pytest.approx(0.3)
    assert E.per_tick_chance(0, dur) == 0 and E.per_tick_chance(1, dur) == 1


def test_eligible_pick_duration_rng():
    templates = [dict(t, is_enabled=True) for t in mig033.EVENT_TEMPLATES]
    summer_agr = E.eligible(templates, region_template="agrarian", segment="summer", active_codes=["harvest"])
    codes = {t["code"] for t in summer_agr}
    assert "drought" in codes and "harvest" not in codes and "riot" not in codes and "good_catch" not in codes
    unknown = {t["code"] for t in E.eligible(templates, region_template="agrarian", segment=None, active_codes=[])}
    assert "drought" not in unknown and "plague" in unknown
    a = E.pick_weighted(E.rng_for(5, 7, "auto"), summer_agr)
    assert a is E.pick_weighted(E.rng_for(5, 7, "auto"), summer_agr)
    assert E.pick_weighted(random.Random(1), [{"weight": 0}]) is None
    for seed in range(50):
        d = E.roll_duration_seconds(random.Random(seed), 2, 4)
        assert 2 * E.DAY <= d <= 4 * E.DAY and d % 60 == 0
    assert E.rng_for(1, 2, "x").random() == E.rng_for(1, 2, "x").random()


def test_riot_due():
    now = datetime(2026, 10, 30, 12)
    assert E.riot_due(now - timedelta(days=3), None, False, now, 3)
    assert not E.riot_due(now - timedelta(days=2), None, False, now, 3)
    assert not E.riot_due(now - timedelta(days=5), None, True, now, 3)
    assert not E.riot_due(None, None, False, now, 3)
    assert not E.riot_due(now - timedelta(days=10), now - timedelta(days=1), False, now, 3)


# --------------------------------------------------------------------------------------------- seed

def test_seed_templates_are_valid():
    seed = mig033.EVENT_TEMPLATES
    codes = [t["code"] for t in seed]
    assert len(seed) == 14 and len(set(codes)) == 14
    assert mig033.revision == "033_econ_region_events" and len(mig033.revision) <= 32
    assert mig033.down_revision == "032_econ_population_scale"
    region_templates = set(TEMPLATES)
    for t in seed:
        assert t["kind"] in E.KINDS and t["trigger_kind"] in E.TRIGGERS and t["scope"] in E.SCOPES
        assert t["icon"] in E.EVENT_ICONS
        assert 0 < t["duration_min_days"] <= t["duration_max_days"]
        assert set(t["region_templates"]) <= region_templates
        assert set(t["seasons"]) <= set(E.GAME_SEGMENTS)
        assert all(c["code"] in codes and c["code"] != t["code"] for c in t["chains"])
        assert 1 <= len(t["effects"]) <= E.MAX_EFFECTS
        parsed = E.parse_effects(t["effects"])
        assert len(parsed) == len(t["effects"])                       # nothing skipped, nothing clamped below
        for raw, eff in zip(t["effects"], parsed):
            assert set(raw) - {"type"} == set(E.EFFECT_FIELDS[raw["type"]])
            assert set(eff.groups) <= set(GROUP_CODES)
            name = E.EFFECT_BOUNDS.get(raw["type"], (None,))[0]
            if name:
                assert getattr(eff, name) == raw[name]
        assert any("а" <= ch <= "я" for ch in t["player_text"].lower())
    assert [t["code"] for t in seed if t["trigger_kind"] == "low_stability"] == ["riot"]
