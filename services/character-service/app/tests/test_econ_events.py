"""FEAT-187 Q1: pure region-events maths (``econ_events``) and the ``mods`` hook of ``econ_sim.simulate_region``.

Extends ``test_econ_events_basic.py`` (B2) without repeating it: stacking / caps in detail, identity paths of the sim,
direction of every lever, one-shot edge cases, roll frequency (statistical, seeded), seeding determinism across
processes, eligibility, weighted pick, spread / chain lifetime chances, riot clock and the merchant / bank param
overrides. Tick-level behaviour (neighbour map, same-country fallback, inserts) is covered by Q2 against SQLite.
"""

import os
import random
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import econ_events as E
import econ_sim as S
from tests.test_econ_events_basic import GROUPS, GROUP_CODES, TEMPLATES, mig028, mig033

P = S.DEFAULT_PARAMS
APP_DIR = os.path.join(os.path.dirname(__file__), "..")


def _region(code="agrarian"):
    pop = TEMPLATES[code][5]
    tgoods = {g: (prod, cmult) for g, prod, cmult in mig028.template_goods(code)}
    goods = S.starting_goods(GROUPS, tgoods, pop)
    purse = S.starting_purse(GROUPS, goods, pop)
    return S.RegionState(population=pop * 100, tax_rate=TEMPLATES[code][6]), goods, purse


def _step(mods=None, code="agrarian", region=None, **over):
    reg, goods, purse = _region(code)
    kw = dict(purse=purse, treasury=5000, grant=100, country_tax_rate=0.1, params=P)
    kw.update(over)
    return S.simulate_region(region or reg, goods, GROUPS, mods=mods, **kw)


def _run(mods, ticks, code, absent=False):
    region, goods, purse = _region(code)
    treasury = 3000
    out = []
    for _ in range(ticks):
        kw = {} if absent else {"mods": mods}
        r = S.simulate_region(region, goods, GROUPS, purse=purse, treasury=treasury, grant=50,
                              country_tax_rate=0.15, params=P, **kw)
        out.append(asdict(r))
        region, goods, purse, treasury = r.region, r.goods, r.purse_after, r.treasury_after
    return out


# --------------------------------------------------------------------------------------------- sim identity

@pytest.mark.parametrize("code", sorted(TEMPLATES))
def test_identity_mods_bit_identical_for_every_region_template(code):
    base = _run(None, 8, code, absent=True)
    assert _run(None, 8, code) == base
    assert _run(S.RegionModifiers(), 8, code) == base
    # aggregate() of nothing / of one-shots only is the identity too
    assert E.aggregate([], GROUP_CODES, P).mods == S.RegionModifiers()
    assert E.aggregate([[]], GROUP_CODES, P).mods == S.RegionModifiers()
    one_shot_only = [[E.Effect("stock_loss", groups=("*",), share=0.5), E.Effect("treasury_expense", share=0.3),
                      E.Effect("population", pct=-0.2)]]
    agg = E.aggregate(one_shot_only, GROUP_CODES, P)
    assert agg.mods == S.RegionModifiers() and agg == E.EventEffects()
    assert _run(agg.mods, 8, code) == base


def test_explicit_identity_multipliers_equal_no_mods():
    """Maps with 1.0 / deltas 0 are numerically the identity (x * 1.0 == x)."""
    base = _step()
    ones = {c: 1.0 for c in GROUP_CODES}
    same = _step(S.RegionModifiers(production=ones, consumption=ones, price=ones, tax_income_mult=1.0))
    assert asdict(same) == asdict(base)


# --------------------------------------------------------------------------------------------- lever directions

def test_production_lever_lowers_and_raises_output():
    base = _step()
    low = _step(S.RegionModifiers(production={"food": 0.5}))
    high = _step(S.RegionModifiers(production={"food": 2.0}))
    assert low.goods["food"].last_produced < base.goods["food"].last_produced < high.goods["food"].last_produced
    # other groups untouched in the step that changes only food production
    assert low.goods["wood"].last_produced == base.goods["wood"].last_produced
    zero = _step(S.RegionModifiers(production={"food": 0.0}))
    assert zero.goods["food"].last_produced == 0.0


def test_consumption_lever_moves_demand():
    base = _step()
    more = _step(S.RegionModifiers(consumption={"food": 2.0}))
    less = _step(S.RegionModifiers(consumption={"food": 0.5}))
    assert less.goods["food"].last_demand < base.goods["food"].last_demand < more.goods["food"].last_demand


def test_consumption_lever_is_not_persisted_on_inputs():
    reg, goods, purse = _region()
    before = {c: (g.production_per_1000, g.consumption_mult) for c, g in goods.items()}
    S.simulate_region(reg, goods, GROUPS, purse=purse, treasury=0,
                      mods=S.RegionModifiers(production={"food": 3}, consumption={"food": 3}))
    assert {c: (g.production_per_1000, g.consumption_mult) for c, g in goods.items()} == before


def test_labor_via_aggregate_lowers_every_group():
    ev = E.aggregate([[E.Effect("labor", mult=0.5)]], GROUP_CODES, P)
    base = _step()
    sick = _step(ev.mods)
    produced_any = False
    for code in GROUP_CODES:
        if base.goods[code].last_produced > 0:
            produced_any = True
            assert sick.goods[code].last_produced < base.goods[code].last_produced
    assert produced_any


def test_price_lever_both_directions_and_clamped():
    base = _step()
    up = _step(S.RegionModifiers(price={"food": 1.3}))
    down = _step(S.RegionModifiers(price={"food": 0.7}))
    assert down.goods["food"].price_mult < base.goods["food"].price_mult < up.goods["food"].price_mult
    huge = _step(S.RegionModifiers(price={"food": 100.0}))
    tiny = _step(S.RegionModifiers(price={"food": 0.0001}))
    assert huge.goods["food"].price_mult == P.price_max
    assert tiny.goods["food"].price_mult == P.price_min
    # unknown group in the map is ignored
    assert asdict(_step(S.RegionModifiers(price={"no_such_group": 2.0}))) == asdict(base)


def test_tax_income_lever():
    base = _step()
    assert base.tax > 0
    assert _step(S.RegionModifiers(tax_income_mult=0.0)).tax == 0
    assert _step(S.RegionModifiers(tax_income_mult=0.5)).tax < base.tax
    rich = _step(S.RegionModifiers(tax_income_mult=2.0))
    assert rich.tax >= base.tax
    # never more than the purse holds
    capped = _step(S.RegionModifiers(tax_income_mult=1000.0), purse=10)
    assert capped.tax <= 10


def test_stability_and_prosperity_deltas_clamped_to_0_100():
    base = _step()
    assert _step(S.RegionModifiers(stability_delta=3)).region.stability == pytest.approx(
        min(100.0, base.region.stability + 3))
    assert _step(S.RegionModifiers(prosperity_delta=-4)).region.prosperity < base.region.prosperity
    low = S.RegionState(population=TEMPLATES["agrarian"][5] * 100, tax_rate=TEMPLATES["agrarian"][6],
                        stability=1.0, prosperity=1.0)
    floor = _step(S.RegionModifiers(stability_delta=-50, prosperity_delta=-50), region=low)
    assert floor.region.stability == 0.0 and floor.region.prosperity == 0.0
    high = S.RegionState(population=TEMPLATES["agrarian"][5] * 100, tax_rate=TEMPLATES["agrarian"][6],
                         stability=99.0, prosperity=99.0)
    top = _step(S.RegionModifiers(stability_delta=50, prosperity_delta=50), region=high)
    assert top.region.stability == 100.0 and top.region.prosperity == 100.0


def test_drought_template_effects_cause_hunger_over_time():
    """Real seed effects: a drought lowers food stock / raises hunger relative to no event over several steps."""
    drought = next(t for t in mig033.EVENT_TEMPLATES if t["code"] == "drought")
    ev = E.aggregate([E.parse_effects(drought["effects"])], GROUP_CODES, P)
    base = _run(None, 15, "agrarian")[-1]
    hit = _run(ev.mods, 15, "agrarian")[-1]
    assert hit["goods"]["food"]["stock"] < base["goods"]["food"]["stock"]
    assert hit["region"]["hunger"] >= base["region"]["hunger"]
    assert hit["region"]["stability"] < base["region"]["stability"]


# --------------------------------------------------------------------------------------------- aggregation / caps

def test_aggregate_multipliers_multiply_and_clamp_high():
    effs = [[E.Effect("production", groups=("food",), mult=1.5)], [E.Effect("production", groups=("food",), mult=1.5)]]
    assert E.aggregate(effs, GROUP_CODES, P).mods.production == {"food": pytest.approx(2.25)}
    effs.append([E.Effect("production", groups=("food",), mult=5.0)])
    assert E.aggregate(effs, GROUP_CODES, P).mods.production["food"] == P.event_mult_max


def test_aggregate_each_map_and_tax_clamped_by_params():
    params = S.SimParams(event_mult_min=0.5, event_mult_max=1.5, event_delta_max=2.0)
    ev = E.aggregate([[E.Effect("consumption", groups=("food",), mult=4.0),
                       E.Effect("consumption", groups=("wood",), mult=0.1),
                       E.Effect("price", groups=("tools",), mult=0.2),
                       E.Effect("tax_income", mult=0.0),
                       E.Effect("stability", delta=5), E.Effect("prosperity", delta=-5),
                       E.Effect("loan_boom", mult=5.0)]], GROUP_CODES, params)
    assert ev.mods.consumption == {"food": 1.5, "wood": 0.5}
    assert ev.mods.price == {"tools": 0.5}
    assert ev.mods.tax_income_mult == 0.5
    assert ev.mods.stability_delta == 2.0 and ev.mods.prosperity_delta == -2.0
    assert ev.loan_boom_mult == 1.5
    assert ev.mods.production == {}                                  # untouched lever stays empty


def test_aggregate_deltas_add_across_events_within_cap():
    ev = E.aggregate([[E.Effect("stability", delta=-2)], [E.Effect("stability", delta=-2)],
                      [E.Effect("prosperity", delta=1.5)], [E.Effect("prosperity", delta=0.5)]], GROUP_CODES, P)
    assert ev.mods.stability_delta == pytest.approx(-4)
    assert ev.mods.prosperity_delta == pytest.approx(2)


def test_aggregate_labor_folds_into_production_of_every_group():
    ev = E.aggregate([[E.Effect("labor", mult=0.8)], [E.Effect("labor", mult=0.5)],
                      [E.Effect("production", groups=("ore_metal",), mult=2.0)]], GROUP_CODES, P)
    assert set(ev.mods.production) == set(GROUP_CODES)
    assert ev.mods.production["ore_metal"] == pytest.approx(0.8)
    assert ev.mods.production["food"] == pytest.approx(0.4)
    assert ev.mods.consumption == {}                                 # labor does not touch consumption
    # with a labor mult below event_mult_min the per-group clamp applies
    tiny = E.aggregate([[E.Effect("labor", mult=0.0)]], GROUP_CODES, P)
    assert all(v == P.event_mult_min for v in tiny.mods.production.values())


def test_aggregate_star_groups_and_flags():
    ev = E.aggregate([[E.Effect("consumption", groups=("*",), mult=1.2), E.Effect("merchants_halt")],
                      [E.Effect("bank_panic")]], GROUP_CODES, P)
    assert ev.mods.consumption == {c: pytest.approx(1.2) for c in GROUP_CODES}
    assert ev.merchants_halt and ev.bank_panic and ev.loan_boom_mult == 1.0
    # tax only touched -> exact product, no tax effect -> 1.0
    assert E.aggregate([[E.Effect("tax_income", mult=1.2)], [E.Effect("tax_income", mult=1.5)]],
                       GROUP_CODES, P).mods.tax_income_mult == pytest.approx(1.8)


# --------------------------------------------------------------------------------------------- merchant / bank params

def test_param_overrides_return_same_object_when_nothing_applies():
    ev = E.aggregate([[E.Effect("production", groups=("food",), mult=0.5), E.Effect("stability", delta=-1)]],
                     GROUP_CODES, P)
    assert E.merchant_params(P, ev) is P and E.bank_params(P, ev) is P
    assert E.merchant_params(P, None) is P and E.bank_params(P, None) is P
    assert E.merchant_params(P, E.EventEffects()) is P and E.bank_params(P, E.EventEffects()) is P


def test_param_overrides_are_independent_and_capped():
    halt = E.EventEffects(merchants_halt=True)
    assert E.bank_params(P, halt) is P                                # merchants halt does not touch the bank
    mp = E.merchant_params(P, halt)
    assert mp.merchant_take_share == 0.0 and mp is not P
    assert asdict(mp) == dict(asdict(P), merchant_take_share=0.0)     # nothing else changed
    panic = E.EventEffects(bank_panic=True)
    assert E.merchant_params(P, panic) is P
    bp = E.bank_params(P, panic)
    assert bp.bank_resident_deposit_share == 0.0 and bp.bank_resident_loan_share == P.bank_resident_loan_share
    boom = E.bank_params(P, E.EventEffects(loan_boom_mult=1000.0))
    assert boom.bank_resident_loan_share == E.BANK_LOAN_SHARE_MAX
    assert boom.bank_resident_deposit_share == P.bank_resident_deposit_share
    assert S.DEFAULT_PARAMS.merchant_take_share == 0.25 and S.DEFAULT_PARAMS.bank_resident_deposit_share == 0.2


# --------------------------------------------------------------------------------------------- one-shots

def test_one_shots_stock_loss_star_and_cap():
    shots = E.one_shots([E.Effect("stock_loss", groups=("*",), share=0.3),
                         E.Effect("stock_loss", groups=("food",), share=0.9),
                         E.Effect("stock_loss", groups=("food",), share=0.9)], GROUP_CODES)
    assert shots.stock_loss["food"] == E.MAX_ONE_SHOT_SHARE          # 1 - 0.7*0.1*0.1 = 0.993 -> 0.9
    assert shots.stock_loss["wood"] == pytest.approx(0.3)
    assert set(shots.stock_loss) == set(GROUP_CODES)
    # "*" without known group codes expands to nothing
    assert E.one_shots([E.Effect("stock_loss", groups=("*",), share=0.3)]).stock_loss == {}
    # zero share disappears
    assert E.one_shots([E.Effect("stock_loss", groups=("food",), share=0.0)]).empty


def test_one_shots_population_and_treasury_combination():
    s = E.one_shots([E.Effect("population", pct=-0.4), E.Effect("population", pct=-0.4),
                     E.Effect("treasury_expense", share=0.2)])
    assert s.population_pct == -E.POPULATION_PCT_LIMIT and s.treasury_share == pytest.approx(0.2)
    g = E.one_shots([E.Effect("population", pct=0.3), E.Effect("population", pct=0.3)])
    assert g.population_pct == E.POPULATION_PCT_LIMIT
    # per-step effects are ignored by one_shots
    assert E.one_shots([E.Effect("production", groups=("food",), mult=0.1), E.Effect("merchants_halt")]).empty
    assert E.one_shots([]).empty


def test_stock_after_loss_edges():
    assert E.stock_after_loss(-10, 0.5) == (0.0, 0.0)
    new, lost = E.stock_after_loss(100, 5.0)                          # share clamped to 0.9
    assert lost == pytest.approx(90) and new == pytest.approx(10)
    assert E.stock_after_loss(100, -1) == (100.0, 0.0)
    new, lost = E.stock_after_loss(123.4, 0.25)
    assert new + lost == pytest.approx(123.4)


def test_treasury_expense_only_from_positive_balance():
    assert E.treasury_expense(0, 0.5) == 0
    assert E.treasury_expense(-1, 0.9) == 0
    assert E.treasury_expense(1000, 0.0) == 0
    assert E.treasury_expense(1000, 2.0) == 900                       # share capped at 0.9
    assert E.treasury_expense(999, 0.5) == 499                        # floor
    assert isinstance(E.treasury_expense(10, 0.3), int)


def test_population_after_floor_and_growth_cap():
    assert E.population_after(1000, -0.5, 0) == 500
    assert E.population_after(1, -0.5, 0) == 1                       # floor max(1, scale) with scale 0
    assert E.population_after(2, -0.5, 0) == 1
    assert E.population_after(120, -0.5, 100) == 100                 # floor = scale
    assert E.population_after(1000, -0.9, 100) == 500                # pct clamped to -50 %
    assert E.population_after(1000, 0.9, 100) == 1500                # growth clamped to +50 %
    assert E.population_after(E.POPULATION_MAX, 0.5, 100) == E.POPULATION_MAX
    assert E.population_after(0, 0.5, 100) == 0 and E.population_after(-5, -0.5, 100) == -5
    assert E.population_after(100, 0.001, 100) == 100                # rounds to no change, never drops on growth


# --------------------------------------------------------------------------------------------- rolls

def test_tick_chance_scales_with_params():
    assert E.tick_chance(S.SimParams(event_rate_per_season=2.0)) == pytest.approx(2 / 196)
    assert E.tick_chance(S.SimParams(event_season_days=98.0)) == pytest.approx(1 / 392)
    assert E.tick_chance(S.SimParams(event_season_days=0)) == 0.0


def test_roll_frequency_one_event_per_region_per_season():
    """196 scheduled slots of one 49-day season x 300 regions, seeded per (slot, region): ~1 success per region."""
    chance = E.tick_chance(P)
    slots = int(P.event_season_days * E.DAY / E.TICK_SECONDS)
    assert slots == 196
    regions = 300
    hits = sum(1 for slot in range(slots) for rid in range(1, regions + 1)
               if E.rng_for(slot, rid, "auto").random() < chance)
    mean = hits / regions
    assert 0.85 <= mean <= 1.15                                       # sd of the mean ~0.058


def test_spread_lifetime_chance_matches_spread_chance():
    """A spread / chain chance is per lifetime: rolled each slot with per_tick_chance it hits ~chance overall."""
    for chance, days in ((0.25, 6), (0.4, 12)):
        duration = days * E.DAY
        per = E.per_tick_chance(chance, duration)
        n_slots = int(duration // E.TICK_SECONDS)
        trials = 2000
        hits = 0
        for t in range(trials):
            if any(E.rng_for(slot, t, "spread:e1").random() < per for slot in range(n_slots)):
                hits += 1
        assert abs(hits / trials - chance) < 0.04
    # an event shorter than one slot gets the whole chance in its single slot
    assert E.per_tick_chance(0.3, 60) == pytest.approx(0.3)
    assert E.per_tick_chance(5, E.DAY) == 1.0 and E.per_tick_chance(-1, E.DAY) == 0.0


def test_rng_for_distinct_streams_and_stable_across_processes():
    a = [E.rng_for(10, 3, "auto").random() for _ in range(3)]
    assert len(set(a)) == 1
    vals = {E.rng_for(10, 3, "auto").random(), E.rng_for(11, 3, "auto").random(),
            E.rng_for(10, 4, "auto").random(), E.rng_for(10, 3, "spread:e1").random()}
    assert len(vals) == 4
    code = "import econ_events as E; print(repr(E.rng_for(10, 3, 'auto').random()))"
    outs = set()
    for seed in ("0", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        res = subprocess.run([sys.executable, "-c", code], cwd=APP_DIR, env=env, capture_output=True, text=True,
                             timeout=20)
        assert res.returncode == 0, res.stderr
        outs.add(res.stdout.strip())
    assert outs == {repr(E.rng_for(10, 3, "auto").random())}


# --------------------------------------------------------------------------------------------- eligibility / pick

def _tpl(code, **kw):
    base = dict(code=code, is_enabled=True, trigger_kind="random", weight=1, region_templates=None, seasons=None)
    base.update(kw)
    return base


def test_eligible_filters():
    templates = [
        _tpl("any"),
        _tpl("off", is_enabled=False),
        _tpl("manual", trigger_kind="manual"),
        _tpl("riot", trigger_kind="low_stability"),
        _tpl("zero", weight=0),
        _tpl("badw", weight="abc"),
        _tpl("mine_only", region_templates=["mining"]),
        _tpl("mine_json", region_templates='["mining"]'),
        _tpl("empty_lists", region_templates=[], seasons=[]),
        _tpl("winter", seasons=["winter", "imbolc"]),
        _tpl("winter_json", seasons='["winter"]'),
        _tpl("active"),
    ]
    got = [t["code"] for t in E.eligible(templates, region_template="agrarian", segment="winter",
                                         active_codes=("active",))]
    assert got == ["any", "empty_lists", "winter", "winter_json"]
    got = [t["code"] for t in E.eligible(templates, region_template="mining", segment=None, active_codes=())]
    assert got == ["any", "mine_only", "mine_json", "empty_lists", "active"]
    got = [t["code"] for t in E.eligible(templates, region_template="mining", segment="summer", active_codes=())]
    assert "winter" not in got and "mine_only" in got


def test_eligible_accepts_orm_like_rows():
    rows = [SimpleNamespace(**_tpl("a")), SimpleNamespace(**_tpl("b", seasons=["summer"]))]
    assert [r.code for r in E.eligible(rows, region_template=None, segment="spring", active_codes=[])] == ["a"]


def test_seed_eligibility_by_season_and_region_template():
    seed = [dict(t, is_enabled=True) for t in mig033.EVENT_TEMPLATES]
    for segment in E.GAME_SEGMENTS:
        for rtpl in TEMPLATES:
            for t in E.eligible(seed, region_template=rtpl, segment=segment, active_codes=()):
                assert t["trigger_kind"] == "random"
                assert not t["region_templates"] or rtpl in t["region_templates"]
                assert not t["seasons"] or segment in t["seasons"]
    # riot is never a random pick
    assert all(t["code"] != "riot" for t in E.eligible(seed, region_template="capital", segment="summer",
                                                       active_codes=()))


def test_pick_weighted_proportional_and_deterministic():
    items = [{"code": "a", "weight": 1}, {"code": "b", "weight": 3}, {"code": "z", "weight": 0},
             {"code": "inf", "weight": float("inf")}, {"code": "bad", "weight": "x"}]
    rng = random.Random(42)
    counts = {}
    n = 20000
    for _ in range(n):
        code = E.pick_weighted(rng, items)["code"]
        counts[code] = counts.get(code, 0) + 1
    assert set(counts) == {"a", "b"}
    assert counts["b"] / n == pytest.approx(0.75, abs=0.02)
    seq1 = [E.pick_weighted(E.rng_for(s, 1, "auto"), items)["code"] for s in range(30)]
    seq2 = [E.pick_weighted(E.rng_for(s, 1, "auto"), items)["code"] for s in range(30)]
    assert seq1 == seq2
    assert E.pick_weighted(rng, []) is None
    assert E.pick_weighted(rng, [SimpleNamespace(weight=2, code="o")]).code == "o"


def test_roll_duration_edges():
    assert E.roll_duration_seconds(random.Random(1), 3, 3) == 3 * E.DAY
    assert E.roll_duration_seconds(random.Random(1), 0, 0) == 60
    assert E.roll_duration_seconds(random.Random(1), 5, 2) == 5 * E.DAY   # max < min -> min
    assert E.roll_duration_seconds(E.rng_for(1, 1, "dur"), 2, 9) == E.roll_duration_seconds(E.rng_for(1, 1, "dur"),
                                                                                            2, 9)


# --------------------------------------------------------------------------------------------- chains / riot

def test_seed_chains_flood_to_plague_and_drought_to_livestock():
    by_code = {t["code"]: t for t in mig033.EVENT_TEMPLATES}
    assert {"code": "plague", "chance": 0.3} in by_code["flood"]["chains"]
    assert any(c["code"] == "livestock" for c in by_code["drought"]["chains"])
    for t in mig033.EVENT_TEMPLATES:
        for c in t["chains"]:
            assert 0 < c["chance"] <= 1
        assert 0 <= t["spread_chance"] <= 1
    assert by_code["riot"]["trigger_kind"] == "low_stability"


def test_riot_due_by_wall_clock():
    now = datetime(2026, 10, 30, 12)
    low = now - timedelta(days=3, seconds=-1)
    assert not E.riot_due(low, None, False, now, 3)                   # one second short
    assert E.riot_due(low, None, False, now + timedelta(seconds=1), 3)
    # after a riot ended the clock restarts from its end, even if stability stayed low the whole time
    ended = now - timedelta(days=2)
    assert not E.riot_due(now - timedelta(days=30), ended, False, now, 3)
    assert E.riot_due(now - timedelta(days=30), ended, False, now + timedelta(days=1), 3)
    # an old riot before the current low period does not matter
    assert E.riot_due(now - timedelta(days=4), now - timedelta(days=40), False, now, 3)
    # fractional days
    assert E.riot_due(now - timedelta(hours=6), None, False, now, 0.25)
    assert not E.riot_due(now - timedelta(hours=5), None, False, now, 0.25)


# --------------------------------------------------------------------------------------------- parse

def test_parse_effects_more_edges():
    raw = ('[{"type": "price", "groups": ["food", "food", "", 5], "mult": 0.01},'
           ' {"type": "loan_boom", "mult": true},'
           ' {"type": "population", "pct": "Infinity"},'
           ' {"type": "stability", "delta": "-3"},'
           ' {"type": "labor", "mult": 2}]')
    assert E.parse_effects(raw) == [E.Effect("price", groups=("food",), mult=0.2),
                                    E.Effect("stability", delta=-3.0),
                                    E.Effect("labor", mult=1.5)]
    assert E.parse_effects({"type": "labor"}) == []
    assert E.parse_effects(b'[{"type": "bank_panic"}]') == [E.Effect("bank_panic")]
