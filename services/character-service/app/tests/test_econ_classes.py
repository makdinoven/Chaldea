"""FEAT-194 QA (#8): pure math of the social classes and the wealth norm (``econ_classes`` + the class path of
``econ_sim.simulate_region``, ``econ_mint.split_by_deficit``, ``econ_sim.country_grants(deficits=...)`` and the
one-shot ``class_shift`` of ``econ_events``).

Group / template data: migration 028 (goods, templates) + migration 037 (class demand weights per group, the
default class mix per template), so the numbers are the ones the tick reads from the DB.

Golden fingerprints: ``GOLDEN`` holds sha256 prefixes of 12-tick runs computed with the pre-FEAT-194 ``econ_sim``
(``git show f8f7729:services/character-service/app/econ_sim.py``). The no-class path (``classes=None``, or shares set
with ``classes_enabled = 0``) must reproduce them bit for bit.
"""

import hashlib
import importlib.util
import math
import os
import random
from dataclasses import replace
from decimal import Decimal

import pytest

import econ_classes as C
import econ_events as E
import econ_mint
import econ_sim as S
from econ_classes import ClassMix

VERSIONS = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")


def _load(name):
    spec = importlib.util.spec_from_file_location(f"migration_{name}_for_classes", os.path.join(VERSIONS, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mig = _load("028_econ_living_regions")
mig037 = _load("037_econ_social_classes")

P = S.DEFAULT_PARAMS
OFF = replace(P, classes_enabled=0)
CODES = list(mig.GROUP_CODES)
TEMPLATES = {t[0]: {"noun": t[3], "gender": t[4], "pop": t[5], "tax": t[6]} for t in mig.TEMPLATES}
MIX = {code: ClassMix(*shares) for code, shares in mig037.TEMPLATE_CLASSES.items()}


def _groups(with_classes=True):
    return {
        code: S.GroupDef(code=code, name=name, base_price=base, norm_per_1000=norm, norm_days=days,
                         prosperity_elasticity=pe, price_elasticity=pr, is_food=bool(food),
                         inputs=dict(mig.INPUTS.get(code, [])),
                         **({"class_demand": mig037.GROUP_CLASS_DEMAND[code]} if with_classes else {}))
        for code, name, base, norm, days, pe, pr, food in mig.GROUPS
    }


GROUPS = _groups()                 # with the 037 class demand weights
PLAIN = _groups(False)             # class_demand default (1, 1, 1) — what the pre-FEAT-194 code knew


def _tgoods(code):
    return {g: (prod, cmult) for g, prod, cmult in mig.template_goods(code)}


def _fresh(code, *, mix="template", pop=None, groups=None):
    """(region, goods) of a freshly applied template; ``mix='template'`` = the template's default mix (= base)."""
    groups = groups or GROUPS
    pop = TEMPLATES[code]["pop"] if pop is None else pop
    classes = MIX[code] if mix == "template" else mix
    goods = S.starting_goods(groups, _tgoods(code), pop)
    region = S.RegionState(population=pop * P.population_scale, tax_rate=TEMPLATES[code]["tax"],
                           classes=classes, class_base=MIX[code] if classes is not None else None)
    return region, goods


def _norm(region, goods, params=P, groups=None):
    return S.region_wealth_norm(groups or GROUPS, goods, region, params)


def _sum_decimal(mix):
    return sum(C.decimals(mix))


# --------------------------------------------------------------------------------------------- seeds

def test_migration_seeds_are_valid_mixes_and_weights():
    assert set(mig037.TEMPLATE_CLASSES) == set(TEMPLATES)
    assert set(mig037.GROUP_CLASS_DEMAND) == set(CODES)
    for code, shares in mig037.TEMPLATE_CLASSES.items():
        assert sum(Decimal(str(s)) for s in shares) == 1, code
        assert all(0 < s < 1 for s in shares), code
    for code, weights in mig037.GROUP_CLASS_DEMAND.items():
        assert all(0 <= w <= 20 for w in weights), code
    # the rich always want at least as much of every group as the poor
    assert all(w[2] >= w[0] for w in mig037.GROUP_CLASS_DEMAND.values())


# --------------------------------------------------------------------------------------------- demand factors (3.3)

@pytest.mark.parametrize("template", sorted(MIX))
def test_factors_are_exactly_one_at_the_template_mix(template):
    mix = MIX[template]
    factors = C.demand_factors(GROUPS, mix, mix)
    assert set(factors) == set(CODES)
    assert all(f == 1.0 for f in factors.values()), factors          # exact, not approx
    assert C.tax_factor(mix, mix, P) == 1.0
    # a copy of the same values (the DB round trip) still gives exactly 1.0
    copy = ClassMix(float(str(mix.poor)), float(str(mix.middling)), float(str(mix.rich)))
    assert all(f == 1.0 for f in C.demand_factors(GROUPS, copy, mix).values())


def test_factor_moves_with_the_mix_and_luxury_reacts_most():
    base = MIX["capital"]
    richer = ClassMix(0.33, 0.45, 0.22)
    f = C.demand_factors(GROUPS, richer, base)
    assert f["food"] == pytest.approx(1.004, abs=1e-3)               # 3.12 C
    assert f["jewelry"] == pytest.approx(1.08, abs=0.01)
    assert f["jewelry"] > f["magic"] > f["food"] > 1.0
    poorer = ClassMix(0.45, 0.45, 0.10)
    assert all(v < 1.0 for v in C.demand_factors(GROUPS, poorer, base).values() if v != 1.0)


def test_zero_weight_guard_splits_by_shares():
    group = S.GroupDef(code="x", name="x", base_price=1, norm_per_1000=1, norm_days=1, class_demand=(0, 0, 0))
    mix = ClassMix(0.5, 0.3, 0.2)
    weights, factor = C.demand_weights(group, mix, MIX["capital"])
    assert factor == 1.0 and weights == pytest.approx((0.5, 0.3, 0.2))
    weights, factor = C.demand_weights(group, ClassMix(0, 0, 0), ClassMix(0, 0, 0))
    assert factor == 1.0 and weights == pytest.approx((1 / 3, 1 / 3, 1 / 3))
    assert C.class_parts(100.0, (0.2, 0.3, 0.5), 0.0) == (0.0, 0.0, 0.0)


@pytest.mark.parametrize("template", sorted(MIX))
def test_class_parts_sum_to_the_group_total(template):
    mix = ClassMix(0.4, 0.4, 0.2)
    for group in GROUPS.values():
        weights, factor = C.demand_weights(group, mix, MIX[template])
        assert sum(weights) == pytest.approx(factor)
        parts = C.class_parts(123.456, weights, factor)
        assert sum(parts) == pytest.approx(123.456)
        assert all(p >= 0 for p in parts)


# --------------------------------------------------------------------------------------------- no-class path

GOLDEN = {
    ("normal", "capital"): "4c6023cb3694d8d8", ("normal", "port"): "ea1e84d7ccd3f8fa",
    ("normal", "mining"): "f1cdc933d5fdd61d", ("normal", "agrarian"): "38eaade8890f74b2",
    ("normal", "forest"): "47ad3b3c79baec84", ("normal", "magic"): "ae1fdfe728545d51",
    ("normal", "fortress"): "e435f43ff25fa1d3", ("normal", "rural"): "80576143c08ae1cd",
    ("broke", "capital"): "083545abeec0cb85", ("broke", "port"): "dc210f3d6f93cdc3",
    ("broke", "mining"): "1e25c595d732c6fd", ("broke", "agrarian"): "abe84ed8644bfdb0",
    ("broke", "forest"): "a34be6bc19efe87d", ("broke", "magic"): "8b297f1cdb3e9fe8",
    ("broke", "fortress"): "b8b5cdca2e331e06", ("broke", "rural"): "8f7e5be24fb58641",
    ("starve", "capital"): "9d6ae8717e6d608f", ("starve", "port"): "3b04c55b02866836",
    ("starve", "mining"): "53d652eb96510c6e", ("starve", "agrarian"): "78c56cba3a177156",
    ("starve", "forest"): "aab5e610f16037f4", ("starve", "magic"): "9366c4592d18ca8f",
    ("starve", "fortress"): "bc40ddce997d87ca", ("starve", "rural"): "9979110c10c88c4d",
}


def _fingerprint(template, scenario, *, groups, mix=None, params=P):
    """sha256 prefix of 12 ticks (every money / state / goods value, floats by repr) — same recipe as GOLDEN."""
    pop = TEMPLATES[template]["pop"]
    goods = S.starting_goods(groups, _tgoods(template), pop)
    region = S.RegionState(population=pop * 100, tax_rate=TEMPLATES[template]["tax"], classes=mix,
                           class_base=mix)
    purse = S.starting_purse(groups, goods, pop)
    if scenario == "broke":
        purse //= 5
    if scenario == "starve":
        goods["food"].production_per_1000 = 0.0
    treasury = 3000
    rows = []
    for _ in range(12):
        r = S.simulate_region(region, goods, groups, purse=purse, treasury=treasury, grant=50, country_tax_rate=0.1,
                              params=params)
        g = r.region
        rows.append((r.income, r.tax, r.country_tax, r.grant, r.wages, r.purse_after, r.treasury_after,
                     repr(r.needs_cost_day), repr(r.affordability),
                     repr(g.stability), repr(g.prosperity), repr(g.hunger), repr(g.satisfaction), g.treasury_target,
                     tuple((c, repr(x.stock), repr(x.norm_stock), repr(x.price_mult), repr(x.prev_price_mult),
                            repr(x.last_produced), repr(x.last_consumed), repr(x.last_demand), repr(x.last_spoiled))
                           for c, x in sorted(r.goods.items()))))
        assert r.wealth_tax == 0 and r.class_hunger is None and r.class_afford is None
        assert r.class_delta == (0.0, 0.0)
        assert g.classes is mix                                         # the mix is carried through untouched
        region, goods, purse, treasury = r.region, r.goods, r.purse_after, r.treasury_after
    return hashlib.sha256(repr(rows).encode()).hexdigest()[:16]


@pytest.mark.parametrize("scenario,template", sorted(GOLDEN))
def test_no_class_path_is_bit_identical_to_the_pre_feature_sim(scenario, template):
    expected = GOLDEN[(scenario, template)]
    assert _fingerprint(template, scenario, groups=PLAIN) == expected             # classes=None, old groups
    assert _fingerprint(template, scenario, groups=GROUPS) == expected            # class weights ignored w/o mix
    # shares present but the layer switched off: today's math too
    assert _fingerprint(template, scenario, groups=GROUPS, mix=MIX[template], params=OFF) == expected


def test_no_class_wealth_norm_is_the_old_starting_purse():
    region, goods = _fresh("capital", mix=None)
    pop = TEMPLATES["capital"]["pop"]
    old = int(math.floor(P.purse_start_days * S.needs_cost_day(GROUPS, goods, pop, base_prices=True)))
    assert S.starting_purse(GROUPS, goods, pop) == old
    assert _norm(region, goods) == old
    with_mix, _g = _fresh("capital")
    assert _norm(with_mix, goods, OFF) == old                        # switched off -> the old target
    r = S.simulate_region(region, goods, GROUPS, purse=old, treasury=0)
    assert r.wealth_norm == old
    assert S.class_factors(GROUPS, region) is None and S.class_factors(GROUPS, with_mix, OFF) is None
    assert S.class_report(region, goods, GROUPS, purse=1, treasury=1) is None


# --------------------------------------------------------------------------------------------- class path at the template mix

@pytest.mark.parametrize("template", sorted(MIX))
def test_class_path_at_the_template_mix_equals_the_old_math(template):
    """Factors 1.0 -> same demand / norms / prices / income tax; purse at the norm -> no wealth tax, same wages."""
    region, goods = _fresh(template)
    norm = _norm(region, goods)
    purse = min(norm, S.starting_purse(GROUPS, goods, TEMPLATES[template]["pop"]))
    old = S.simulate_region(replace(region, classes=None, class_base=None), goods, GROUPS, purse=purse,
                            treasury=4000, grant=30)
    new = S.simulate_region(region, goods, GROUPS, purse=purse, treasury=4000, grant=30)
    for code in CODES:
        a, b = old.goods[code], new.goods[code]
        assert b.last_demand == pytest.approx(a.last_demand, rel=1e-12, abs=1e-12), code
        assert b.norm_stock == pytest.approx(a.norm_stock, rel=1e-12, abs=1e-12), code
        assert b.price_mult == pytest.approx(a.price_mult, rel=1e-9), code
        assert b.last_consumed == pytest.approx(a.last_consumed, rel=1e-9, abs=1e-9), code
    assert (new.income, new.tax, new.country_tax, new.wages) == (old.income, old.tax, old.country_tax, old.wages)
    assert new.wealth_tax == 0
    assert new.region.treasury_target == old.region.treasury_target
    assert new.purse_after == old.purse_after and new.treasury_after == old.treasury_after
    assert new.region.hunger == pytest.approx(old.region.hunger, abs=1e-12)
    assert new.region.stability == pytest.approx(old.region.stability, abs=1e-9)    # class terms are 0
    assert new.region.prosperity == pytest.approx(old.region.prosperity, abs=1e-9)
    assert new.wealth_norm == norm
    assert new.class_hunger == (0.0, 0.0, 0.0)
    assert new.class_afford == (1.0, 1.0, 1.0)
    # a fresh region (prosperity 50, stability 70, fed, r <= 1) sits in the dead zone: no drift at rollout
    assert new.class_delta == (0.0, 0.0) and new.region.classes == region.classes


@pytest.mark.parametrize("template", sorted(MIX))
def test_income_tax_weights_reproduce_todays_tax_at_the_default_mix(template):
    region, goods = _fresh(template)
    norm = _norm(region, goods)
    # (at a purse below the norm the poor buy less -> stocks / prices / income differ; that is intended)
    for purse in (10 ** 9, norm, 30):                            # 30: capped by the purse as before
        old = S.simulate_region(replace(region, classes=None), goods, GROUPS, purse=purse, treasury=0)
        new = S.simulate_region(region, goods, GROUPS, purse=purse, treasury=0,
                                params=replace(P, wealth_tax_rate=0.0))
        assert new.tax == old.tax


def test_tax_factor_values():
    base = MIX["capital"]
    assert C.tax_factor(ClassMix(0.33, 0.45, 0.22), base, P) == pytest.approx(1.0356, abs=1e-4)   # 3.6 example
    assert C.tax_factor(ClassMix(0.6, 0.35, 0.05), base, P) < 1.0
    zero = replace(P, class_tax_w_poor=0, class_tax_w_middling=0, class_tax_w_rich=0)
    assert C.tax_factor(ClassMix(0.1, 0.1, 0.8), base, zero) == 1.0


# --------------------------------------------------------------------------------------------- wealth norm (3.4)

NORM_DAYS = {"capital": 9.98, "magic": 10.1, "port": 8.3, "fortress": 7.2, "forest": 7.2, "mining": 7.0,
             "agrarian": 6.7, "rural": 6.0}


@pytest.mark.parametrize("template", sorted(NORM_DAYS))
def test_wealth_norm_per_template_matches_the_design_table(template):
    pop = 40_000
    goods = S.starting_goods(GROUPS, _tgoods(template), pop)
    mix = MIX[template]
    norm, parts = C.wealth_norm(GROUPS, goods, pop, mix, mix, P)
    days = norm / S.needs_cost_day(GROUPS, goods, pop, base_prices=True)
    assert days == pytest.approx(NORM_DAYS[template], abs=0.06)
    assert norm == math.floor(sum(parts))
    # parts = norm days x the class's own needs per day at base prices
    cost = C.base_cost_parts(GROUPS, goods, pop, mix, mix)
    assert parts == pytest.approx(tuple(d * c for d, c in zip((3, 7, 21), cost)))
    # per resident: poor ≈ 2.4-2.7, middling ≈ 6.8-8.4, rich ≈ 31-40 marks (sim units)
    per = [parts[k] / (pop * mix.as_tuple()[k]) for k in range(3)]
    assert 2.3 <= per[0] <= 2.8 and 6.7 <= per[1] <= 8.5 and 30 <= per[2] <= 41


def test_capital_norm_is_well_above_the_rural_one():
    days = {}
    for template in ("capital", "rural"):
        goods = S.starting_goods(GROUPS, _tgoods(template), 40_000)
        days[template] = (C.wealth_norm(GROUPS, goods, 40_000, MIX[template], MIX[template], P)[0]
                          / S.needs_cost_day(GROUPS, goods, 40_000, base_prices=True))
    assert days["capital"] / days["rural"] == pytest.approx(1.67, abs=0.05)


def test_wealth_norm_grows_with_richer_classes_and_norm_days():
    region, goods = _fresh("port")
    base_norm = _norm(region, goods)
    richer = _norm(replace(region, classes=ClassMix(0.35, 0.45, 0.20)), goods)
    poorer = _norm(replace(region, classes=ClassMix(0.70, 0.27, 0.03)), goods)
    assert poorer < base_norm < richer
    assert _norm(region, goods, replace(P, class_norm_days_rich=42)) > base_norm
    zero = replace(P, class_norm_days_poor=0, class_norm_days_middling=0, class_norm_days_rich=0)
    assert _norm(region, goods, zero) == 0


# --------------------------------------------------------------------------------------------- purchasing power (3.5)

def test_split_money_is_proportional_to_the_norm_parts():
    assert C.split_money(1000, (1, 2, 7)) == pytest.approx((100, 200, 700))
    assert C.split_money(900, (0, 0, 0)) == pytest.approx((300, 300, 300))
    assert C.split_money(-50, (1, 1, 1)) == (0.0, 0.0, 0.0)
    assert sum(C.split_money(12345, (3.3, 1.1, 0.7))) == pytest.approx(12345)


def test_class_afford_and_allocate_units():
    assert C.class_afford(50, 100, 1) == 0.5
    assert C.class_afford(500, 100, 1) == 1.0
    assert C.class_afford(0, 0, 1) == 1.0                              # nothing to buy
    assert C.class_afford(-5, 10, 1) == 0.0
    # rich first, then middling, then poor
    assert C.allocate(100, (50, 40, 30), (1, 1, 1)) == pytest.approx((30, 40, 30))
    assert C.allocate(60, (50, 40, 30), (1, 1, 1)) == pytest.approx((0, 30, 30))
    assert C.allocate(20, (50, 40, 30), (1, 1, 1)) == pytest.approx((0, 0, 20))
    assert C.allocate(1000, (50, 40, 30), (0.5, 1, 1)) == pytest.approx((25, 40, 30))   # afford caps the want
    assert C.allocate(-3, (1, 1, 1), (1, 1, 1)) == (0.0, 0.0, 0.0)


def test_money_split_per_class_in_the_sim():
    """Every class holds the same fraction r of its own norm: at r = 0.3 the poor (3 days) afford ~0.9 of their
    basket while the middling (2.1 days) and the rich (6.3 days) still buy everything."""
    region, goods = _fresh("capital")
    norm = _norm(region, goods)
    r = S.simulate_region(region, goods, GROUPS, purse=int(norm * 0.3), treasury=0)
    poor, middling, rich = r.class_afford
    assert poor == pytest.approx(0.9, abs=0.01)
    assert middling == 1.0 and rich == 1.0
    assert r.affordability < 1.0
    # broke: nobody buys; rich enough: everybody buys
    assert S.simulate_region(region, goods, GROUPS, purse=0, treasury=0).class_afford == (0.0, 0.0, 0.0)
    assert S.simulate_region(region, goods, GROUPS, purse=norm, treasury=0).class_afford == (1.0, 1.0, 1.0)


def test_poor_drop_out_first_when_prices_rise():
    region, goods = _fresh("mining")
    norm = _norm(region, goods)
    dear = {c: replace(g, price_mult=2.5) for c, g in goods.items()}
    r = S.simulate_region(region, dear, GROUPS, purse=int(norm * 0.5), treasury=0)
    poor, middling, rich = r.class_afford
    assert poor < middling <= rich and rich == 1.0
    assert poor < 1.0


def test_shortage_is_served_rich_then_middling_then_poor():
    region, goods = _fresh("capital")
    norm = _norm(region, goods)
    goods["food"].production_per_1000 = 0.0
    probe = S.simulate_region(region, goods, GROUPS, purse=norm, treasury=0)
    demand = probe.goods["food"].last_demand
    goods["food"].stock = demand * 0.5                                 # half of what the region wants
    r = S.simulate_region(region, goods, GROUPS, purse=norm, treasury=0)
    hp, hm, hr = r.class_hunger
    assert hr == 0.0                                                    # the rich eat first
    assert 0.0 < hm < 1.0
    assert hp == pytest.approx(1.0)                                     # nothing left for the poor
    assert r.region.hunger == pytest.approx(0.5, abs=1e-6)              # the region as a whole: half fed
    assert r.goods["food"].stock == pytest.approx(0.0, abs=1e-6)
    # without classes the same shortage is one region-wide number
    old = S.simulate_region(replace(region, classes=None), goods, GROUPS, purse=norm, treasury=0)
    assert old.region.hunger == pytest.approx(r.region.hunger, abs=1e-6)


# --------------------------------------------------------------------------------------------- wealth tax (3.6)

def test_wealth_tax_unit():
    assert C.wealth_tax(1000, 1000, P) == 0
    assert C.wealth_tax(999, 1000, P) == 0
    assert C.wealth_tax(2000, 1000, P) == 20                          # 2 % of the excess
    assert C.wealth_tax(2049, 1000, P) == 20                          # floor
    assert C.wealth_tax(-5, 0, P) == 0
    assert C.wealth_tax(10, 0, replace(P, wealth_tax_rate=5.0)) == 10  # never more than the purse
    assert C.wealth_tax(5000, 1000, replace(P, wealth_tax_rate=0)) == 0


def test_wealth_tax_in_the_sim_rides_the_tax_and_is_not_paid_back_as_wages():
    region, goods = _fresh("capital")
    norm = _norm(region, goods)
    purse, treasury, grant = 2 * norm, 1000, 70
    r = S.simulate_region(region, goods, GROUPS, purse=purse, treasury=treasury, grant=grant, country_tax_rate=0.1)
    no_wt = S.simulate_region(region, goods, GROUPS, purse=purse, treasury=treasury, grant=grant,
                              country_tax_rate=0.1, params=replace(P, wealth_tax_rate=0.0))
    assert r.wealth_norm == norm
    assert r.wealth_tax == math.floor(0.02 * (purse - r.tax - norm)) > 0
    assert r.tax == no_wt.tax                                          # income tax unchanged
    assert r.country_tax == math.floor((r.tax + r.wealth_tax) * 0.1)  # the country 10 % on the combined leg
    # treasury_target from the income tax only, wages identical -> the wealth tax stays in the treasury
    assert r.region.treasury_target == no_wt.region.treasury_target == math.floor(r.tax / P.dt * 7)
    assert r.wages == no_wt.wages
    assert r.purse_after == purse - r.tax - r.wealth_tax + r.wages
    assert r.treasury_after == treasury + r.tax + r.wealth_tax - r.country_tax + grant - r.wages
    assert r.treasury_after - no_wt.treasury_after == r.wealth_tax - (r.country_tax - no_wt.country_tax)
    # money is conserved: purse + treasury + country cut = before + grant
    assert r.purse_after + r.treasury_after + r.country_tax == purse + treasury + grant


def test_no_wealth_tax_at_or_below_the_norm():
    region, goods = _fresh("rural")
    norm = _norm(region, goods)
    for purse in (0, norm // 2, norm):
        assert S.simulate_region(region, goods, GROUPS, purse=purse, treasury=0).wealth_tax == 0


# --------------------------------------------------------------------------------------------- stability (3.7)

@pytest.mark.parametrize("template", sorted(MIX))
def test_class_stability_terms_are_zero_at_defaults(template):
    assert C.stability_terms(MIX[template], 0.0, TEMPLATES[template]["tax"], P) == 0.0


def test_class_stability_terms_values_and_signs():
    assert C.stability_terms(ClassMix(0.70, 0.25, 0.05), 0.0, 0.1, P) == pytest.approx(4.0)       # many poor
    assert C.stability_terms(ClassMix(0.5, 0.4, 0.1), 0.5, 0.1, P) == pytest.approx(12.5)         # hungry poor
    assert C.stability_terms(ClassMix(0.35, 0.45, 0.20), 0.0, 0.20, P) == pytest.approx(1.6)      # taxed rich
    assert C.stability_terms(ClassMix(0.61, 0.3, 0.09), 0.0, 0.12, P) == pytest.approx(0.4)       # tax at free
    assert C.stability_terms(ClassMix(0.5, 0.4, 0.1), -1.0, 0.0, P) == 0.0                         # never negative


def test_class_stability_terms_lower_the_sim_target():
    region, goods = _fresh("rural")
    norm = _norm(region, goods)
    poor_mix = replace(region, classes=ClassMix(0.85, 0.13, 0.02))
    base = S.simulate_region(replace(region, classes=None), goods, GROUPS, purse=norm, treasury=0)
    worse = S.simulate_region(poor_mix, goods, GROUPS, purse=norm, treasury=0)
    assert worse.region.stability < base.region.stability


# --------------------------------------------------------------------------------------------- mobility (3.8)

def test_mobility_dead_zone_moves_nobody():
    mix = MIX["port"]
    for stab, prosp, hunger, r in ((70, 50, 0, 1.0), (70, 50, 0, 0.7), (65, 52, 0, 1.05), (50, 50, 0, 1.0)):
        assert abs(C.mobility_score(stab, prosp, hunger, r, P)) <= P.mob_dead_zone
        assert C.mobility(mix, stab, prosp, hunger, r, P) == (mix, 0.0, 0.0)


def test_mobility_up_and_down_directions_and_rates():
    mix = ClassMix(0.5, 0.4, 0.1)
    up, dp, dr = C.mobility(mix, 100, 100, 0.0, 2.0, P)                 # score clamped to 1 -> full rate
    assert up.poor == pytest.approx(0.5 - 0.001 * 0.5, abs=1e-6)
    assert up.rich == pytest.approx(0.1 + 0.001 * 0.5 * 0.4, abs=1e-6)
    assert dp < 0 < dr
    down, dp, dr = C.mobility(mix, 0, 0, 1.0, 0.0, P)                   # famine, broke, riot -> -1
    assert down.rich == pytest.approx(0.1 - 0.0015 * 0.1, abs=1e-6)
    assert down.poor == pytest.approx(0.5 + 0.0015 * 0.4, abs=1e-6)
    assert dp > 0 > dr
    # falling is faster than rising
    assert abs(down.poor - mix.poor) > abs(up.poor - mix.poor)
    # rich factor 0: nobody becomes rich on the way up
    flat, _dp, dr = C.mobility(mix, 100, 100, 0.0, 2.0, replace(P, mob_rich_factor=0.0))
    assert flat.rich == mix.rich and dr == 0.0 and flat.poor < mix.poor


def test_mobility_rate_scales_outside_the_dead_zone():
    mix = ClassMix(0.5, 0.4, 0.1)
    weak = C.mobility(mix, 70, 70, 0.0, 1.0, P)[1]                       # small positive score
    strong = C.mobility(mix, 90, 90, 0.0, 1.5, P)[1]
    assert strong < weak < 0


@pytest.mark.parametrize("mix", [ClassMix(0.02, 0.88, 0.10), ClassMix(0.30, 0.68, 0.02), ClassMix(0.90, 0.08, 0.02),
                                 ClassMix(0.05, 0.05, 0.90)])
def test_shift_respects_the_share_bounds(mix):
    for up, down in ((0.3, 0.0), (0.0, 0.3)):
        for _ in range(50):
            new, _dp, _dr = C.shift(mix, up, down, 0.5, P.class_share_min, P.class_share_max)
            for old_v, new_v in zip(mix.as_tuple(), new.as_tuple()):
                assert new_v >= min(old_v, P.class_share_min) - 1e-6
                assert new_v <= max(old_v, P.class_share_max) + 1e-6
            assert _sum_decimal(new) == 1
            mix = new


def test_admin_set_out_of_bounds_shares_are_never_pushed_further_out():
    too_poor = ClassMix(0.95, 0.04, 0.01)          # poor above max, rich below min
    new, _dp, _dr = C.shift(too_poor, 0.0, 0.2, 0.5, 0.02, 0.90)
    assert new.poor <= too_poor.poor and new.rich >= too_poor.rich
    new, _dp, _dr = C.shift(too_poor, 0.2, 0.0, 0.5, 0.02, 0.90)
    assert new.poor <= too_poor.poor                                  # up moves poor down — toward the bounds
    no_rich = ClassMix(0.5, 0.5, 0.0)
    assert C.shift(no_rich, 0.0, 0.3, 0.5, 0.02, 0.9)[0].rich == 0.0


def test_shift_property_sum_exactly_one_and_nothing_negative():
    rng = random.Random(194)
    for _ in range(2000):
        a, b = sorted((rng.random(), rng.random()))
        mix = ClassMix(*C.decimals(ClassMix(a, b - a, 1 - b)))
        mix = ClassMix(float(mix.poor), float(mix.middling), float(mix.rich))
        smin, smax = rng.uniform(0, 0.3), rng.uniform(0.4, 1.0)
        amount = rng.uniform(0, 0.3)
        up, down = (amount, 0.0) if rng.random() < 0.5 else (0.0, amount)     # callers move one direction
        new, dp, dr = C.shift(mix, up, down, rng.random(), smin, smax)
        assert _sum_decimal(new) == 1
        assert min(new.as_tuple()) >= 0
        for old_v, new_v in zip(mix.as_tuple(), new.as_tuple()):
            assert min(old_v, smin) - 1e-6 <= new_v <= max(old_v, smax) + 1e-6
        if new is not mix:
            assert dp == pytest.approx(new.poor - mix.poor, abs=2e-6)
            assert dr == pytest.approx(new.rich - mix.rich, abs=2e-6)


def test_decimals_store_middling_as_the_rest():
    poor, middling, rich = C.decimals(ClassMix(0.1234567, 0.5, 0.3765433))
    assert poor == Decimal("0.123457") and rich == Decimal("0.376543")
    assert middling == Decimal(1) - poor - rich and poor + middling + rich == 1


def test_mobility_in_the_sim_follows_money_above_the_norm():
    region, goods = _fresh("capital")
    norm = _norm(region, goods)
    rich_r = S.simulate_region(region, goods, GROUPS, purse=2 * norm, treasury=0)
    assert rich_r.class_delta[0] < 0 < rich_r.class_delta[1]
    assert rich_r.region.classes.poor < region.classes.poor
    assert sum(C.decimals(rich_r.region.classes)) == 1
    starving = dict(goods)
    starving["food"] = replace(goods["food"], stock=0.0, production_per_1000=0.0)
    poor_r = S.simulate_region(region, starving, GROUPS, purse=norm // 10, treasury=0)
    assert poor_r.class_delta[0] > 0 > poor_r.class_delta[1]


# --------------------------------------------------------------------------------------------- long run (3.6 equilibrium)

def test_long_run_from_twice_the_norm_does_not_run_away():
    """800 ticks (200 days) of a capital with 2x its norm, the country returning its pool as grants (no other
    inflow): money is conserved (purse + treasury + country), the excess melts, shares stay bounded with sum
    exactly 1, the region settles near its (higher) norm instead of running away or collapsing."""
    region, goods = _fresh("capital")
    norm0 = _norm(region, goods)
    purse, treasury, country = 2 * norm0, 0, 0
    total0 = purse + treasury + country
    r0 = purse / norm0
    max_r, ratios = r0, []
    pop = region.population
    for i in range(800):
        grant = S.country_grants(country, {1: pop}, deficits={1: 0})[1]
        country -= grant
        r = S.simulate_region(region, goods, GROUPS, purse=purse, treasury=treasury, grant=grant, country_tax_rate=0.1)
        country += r.country_tax
        assert r.purse_after + r.treasury_after + country == total0, i          # the world sum is conserved
        assert r.purse_after >= 0 and r.wealth_tax >= 0 and country >= 0
        mix = r.region.classes
        assert all(P.class_share_min - 1e-9 <= s <= P.class_share_max + 1e-9 for s in mix.as_tuple())
        assert sum(C.decimals(mix)) == 1
        region, goods, purse, treasury = r.region, r.goods, r.purse_after, r.treasury_after
        ratio = purse / r.wealth_norm
        assert math.isfinite(ratio)
        max_r = max(max_r, ratio)
        ratios.append(ratio)
    assert max_r <= r0 + 1e-9                                           # never richer than at the start
    assert ratios[-1] < r0 - 0.3                                        # the excess melted ...
    assert ratios[-1] > 0.9                                             # ... toward the norm, not below it
    assert abs(ratios[-1] - ratios[-50]) < 0.05                         # and it has calmed down
    assert region.classes.poor < MIX["capital"].poor                    # money pushed classes up
    assert r.wealth_norm > norm0                                          # -> a higher norm
    assert purse > norm0                                                 # the capital stays richer than it was


# --------------------------------------------------------------------------------------------- deficit, quota, grants

def test_deficit():
    assert C.deficit(1000, 200, 500, 100) == 600
    assert C.deficit(1000, 200, 1500, 0) == 0
    assert C.deficit(1000, -50, 900, 0) == 100                          # negative target counts as 0
    assert C.deficit(1000, 0, -300, 0) == 1000                          # negative purse counts as 0
    assert C.deficit(1000, 0, 0, -400) == 1400                          # a treasury in debt widens the deficit
    assert C.deficit(0, 0, 0, 0) == 0


def test_split_by_deficit():
    assert econ_mint.split_by_deficit(1000, {1: 300, 2: 100, 3: 0}) == {1: 300, 2: 100}     # capped at the deficit
    assert econ_mint.split_by_deficit(100, {1: 300, 2: 100, 3: 0}) == {1: 75, 2: 25}        # proportional
    assert econ_mint.split_by_deficit(100, {1: 0, 2: 0}) == {}                               # nobody below
    assert econ_mint.split_by_deficit(0, {1: 50}) == {}
    assert econ_mint.split_by_deficit(100, {}) == {}
    assert econ_mint.split_by_deficit(100, {5: -10, 6: 40}) == {6: 40}


def test_split_by_deficit_property_exact_sum_and_caps():
    rng = random.Random(9)
    for _ in range(500):
        deficits = {rid: rng.choice([0, rng.randint(1, 10_000)]) for rid in range(1, rng.randint(1, 9))}
        amount = rng.randint(0, 40_000)
        shares = econ_mint.split_by_deficit(amount, deficits)
        total = sum(d for d in deficits.values() if d > 0)
        assert sum(shares.values()) == (min(amount, total) if amount > 0 else 0)
        assert all(deficits[rid] > 0 and 0 < amt <= deficits[rid] for rid, amt in shares.items())


def test_country_grants_without_deficits_is_the_old_split():
    pops = {1: 100, 2: 300}
    assert S.country_grants(4000, pops) == {1: 250, 2: 750}
    assert S.country_grants(4000, pops, deficits={1: 0, 2: 0}) == S.country_grants(4000, pops)
    assert S.country_grants(0, pops, deficits={1: 100}) == {1: 0, 2: 0}


def test_country_grants_tilt_toward_regions_below_the_norm():
    pops = {1: 1, 2: 1}
    # pool 1000: tilt 250, region 1 lacks only 100 -> 100 by deficit, the remaining 900 by population
    assert S.country_grants(4000, pops, deficits={1: 100, 2: 0}) == {1: 550, 2: 450}
    # a large deficit takes the whole tilt
    assert S.country_grants(4000, pops, deficits={1: 10 ** 6, 2: 0}) == {1: 625, 2: 375}
    # tilt split proportionally between two below-norm regions
    g = S.country_grants(4000, {1: 1, 2: 1, 3: 2}, deficits={1: 3000, 2: 1000, 3: 0})
    assert g == {1: 187 + 187, 2: 62 + 187, 3: 375}
    assert S.country_grants(4000, pops, params=replace(P, grant_deficit_share=0.0), deficits={1: 5000}) == \
        S.country_grants(4000, pops)


def test_country_grants_property_sum_within_pool():
    rng = random.Random(3)
    for _ in range(500):
        pops = {rid: rng.randint(0, 50_000) for rid in range(1, rng.randint(2, 8))}
        deficits = {rid: rng.choice([0, rng.randint(1, 100_000)]) for rid in pops}
        balance = rng.randint(-100, 10 ** 7)
        params = replace(P, grant_deficit_share=rng.random())
        grants = S.country_grants(balance, pops, params, deficits=deficits)
        pool = math.floor(max(0, balance) * P.country_grant_share)
        assert set(grants) == set(pops)
        assert all(v >= 0 for v in grants.values())
        assert sum(grants.values()) <= pool


# --------------------------------------------------------------------------------------------- event class_shift (3.15)

def test_class_shift_effect_parse_bounds_and_one_shots():
    effects = E.parse_effects([{"type": "class_shift", "delta": -0.06}, {"type": "class_shift", "delta": 0.9},
                               {"type": "class_shift"}, {"type": "class_shift", "delta": "x"}])
    assert [e.delta for e in effects] == [-0.06, 0.3]                   # clamped, invalid ones skipped
    assert "class_shift" in E.ONE_SHOT_TYPES and E.EFFECT_BOUNDS["class_shift"] == ("delta", -0.3, 0.3)
    shots = E.one_shots([E.Effect("class_shift", delta=-0.2), E.Effect("class_shift", delta=-0.2)])
    assert shots.class_shift == -E.CLASS_SHIFT_LIMIT and not shots.empty
    assert E.one_shots([E.Effect("class_shift", delta=0.02), E.Effect("class_shift", delta=0.01)]).class_shift == \
        pytest.approx(0.03)
    assert E.one_shots([E.Effect("class_shift", delta=0.0)]).empty
    # per-step aggregation ignores the one-shot
    assert E.aggregate([[E.Effect("class_shift", delta=0.3)]], CODES, P).mods.tax_income_mult == 1.0


def test_event_shift_directions():
    mix = ClassMix(0.5, 0.4, 0.1)
    down, dp, dr = C.event_shift(mix, -0.06, P)                          # «Разорение»
    assert down.poor == pytest.approx(0.5 + 0.06 * 0.4, abs=1e-6) and down.rich == pytest.approx(0.1 * 0.94)
    assert dp > 0 > dr
    up, dp, dr = C.event_shift(mix, 0.02, P)                             # «Богатая жила»
    assert up.poor == pytest.approx(0.49, abs=1e-6) and up.rich == pytest.approx(0.1 + 0.02 * 0.5 * 0.4, abs=1e-6)
    assert C.event_shift(mix, 0.0, P) == (mix, 0.0, 0.0)
    assert sum(C.decimals(down)) == 1 and sum(C.decimals(up)) == 1


def test_migration_037_event_seeds():
    assert mig037.EVENT_CLASS_SHIFTS == {"riot": -0.03, "raid": -0.02, "plague": -0.02, "rich_vein": 0.02,
                                         "fair": 0.01}
    ruin = mig037.RUIN
    assert ruin["code"] == "ruin" and ruin["name"] == "Разорение" and ruin["kind"] == "bad"
    parsed = E.parse_effects(ruin["effects"])
    assert [e.type for e in parsed] == ["class_shift", "tax_income", "prosperity", "stability"]
    assert E.one_shots(parsed).class_shift == pytest.approx(-0.06)


# --------------------------------------------------------------------------------------------- card (3.11)

SEEDED_LABELS = {
    "capital": ("rich", "Богатый город"), "magic": ("rich", "Богатый город"),
    "port": ("wealthy", "Зажиточный порт"), "fortress": ("modest", "Скромная крепость"),
    "forest": ("modest", "Скромный край, много бедняков"), "mining": ("modest", "Скромный город, много бедняков"),
    "agrarian": ("modest", "Скромный край, много бедняков"), "rural": ("poor", "Бедная округа"),
}


@pytest.mark.parametrize("template", sorted(SEEDED_LABELS))
def test_seeded_templates_read_as_designed(template):
    t = TEMPLATES[template]
    state, label = SEEDED_LABELS[template]
    assert C.class_state(MIX[template]) == state
    assert C.class_phrase(MIX[template], t["noun"], t["gender"]) == label


def test_class_state_thresholds_and_gender():
    assert C.class_state(ClassMix(0.6, 0.4, 0.04)) == "poor"            # index 0.24
    assert C.class_state(ClassMix(0.5, 0.5, 0.0)) == "modest"           # 0.25
    assert C.class_state(ClassMix(0.36, 0.64, 0.0)) == "wealthy"        # 0.32
    assert C.class_state(ClassMix(0.2, 0.8, 0.0)) == "rich"             # 0.40
    mix = ClassMix(0.2, 0.8, 0.0)
    assert C.class_phrase(mix, "Город", "m") == "Богатый город"
    assert C.class_phrase(mix, "Крепость", "f") == "Богатая крепость"
    assert C.class_phrase(mix, "Поселение", "n") == "Богатое поселение"
    assert C.class_phrase(mix) == "Богатый регион"


def test_class_phrase_tails():
    assert C.class_phrase(ClassMix(0.5, 0.3, 0.2), "Город") == "Богатый город" or \
        C.class_state(ClassMix(0.5, 0.3, 0.2)) != "rich"
    assert C.class_phrase(ClassMix(0.55, 0.37, 0.08), "Город") == "Скромный город, много бедняков"
    assert C.class_phrase(ClassMix(0.70, 0.25, 0.05), "Город") == "Бедный город"         # poor state: no tail
    assert C.class_phrase(ClassMix(0.45, 0.35, 0.20), "Порт") == "Зажиточный порт, много богачей"
    assert C.class_phrase(ClassMix(0.30, 0.50, 0.20), "Город") == "Богатый город"        # rich state: no tail
    # poor tail wins over the rich tail
    assert C.class_phrase(ClassMix(0.50, 0.25, 0.25), "Город").endswith(", много бедняков")


def test_class_bar_words_and_thresholds():
    assert C.class_bar(ClassMix(0.29, 0.30, 0.0799)) == {"poor": "few", "middling": "some", "rich": "few"}
    assert C.class_bar(ClassMix(0.49, 0.50, 0.08)) == {"poor": "some", "middling": "many", "rich": "some"}
    assert C.class_bar(ClassMix(0.50, 0.33, 0.18)) == {"poor": "many", "middling": "some", "rich": "many"}
    for template, mix in MIX.items():
        bar = C.class_bar(mix)
        assert set(bar) == {"poor", "middling", "rich"} and set(bar.values()) <= {"few", "some", "many"}


def _numbers(value, path=""):
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [(path, value)]
    if isinstance(value, dict):
        return [n for k, v in value.items() for n in _numbers(v, f"{path}.{k}")]
    if isinstance(value, list):
        return [n for i, v in enumerate(value) for n in _numbers(v, f"{path}[{i}]")]
    return []


ADJECTIVES = ("Богат", "Зажиточ", "Скромн", "Бедн")


@pytest.mark.parametrize("prosperity,state", [(95, "rich"), (65, "wealthy"), (45, "modest"), (5, "poor")])
@pytest.mark.parametrize("template", ["capital", "rural", "fortress"])
def test_card_with_classes_class_phrase_first_no_duplicate_rich(template, prosperity, state):
    t = TEMPLATES[template]
    region, goods = _fresh(template)
    region = replace(region, prosperity=prosperity)
    plain = S.region_card(region, goods, GROUPS, treasury=1000, noun=t["noun"], gender=t["gender"],
                          group_order=CODES)
    card = S.region_card(region, goods, GROUPS, treasury=1000, noun=t["noun"], gender=t["gender"],
                         group_order=CODES, classes=region.classes)
    assert "classes" not in plain and plain["phrases"][0] == plain["prosperity"]["label"]
    assert set(card) == set(plain) | {"classes"}
    assert card["classes"] == C.class_card(region.classes, t["noun"], t["gender"])
    assert card["phrases"][0] == card["classes"]["label"]
    assert card["prosperity"]["state"] == plain["prosperity"]["state"] == state
    assert card["prosperity"]["label"] == f"{t['noun']} {S.PROSPERITY_PHRASES[state]}"
    # exactly one phrase carries a class-like adjective
    assert sum(1 for p in card["phrases"] if p.startswith(ADJECTIVES)) == 1
    if state in ("rich", "poor"):
        assert card["prosperity"]["label"] in card["phrases"]
    else:
        assert card["prosperity"]["label"] not in card["phrases"]
    assert _numbers(card) == []
    # everything else is untouched
    for key in ("food", "treasury", "stability", "price_level", "shortages", "surpluses", "groups"):
        assert card[key] == plain[key]


def test_class_report_shape():
    region, goods = _fresh("capital")
    norm = _norm(region, goods)
    rep = S.class_report(replace(region, treasury_target=500), goods, GROUPS, purse=norm // 2, treasury=100)
    assert set(rep) == {"classes", "wealth_norm", "money_norm", "deficit", "r"}
    assert set(rep["classes"]) == {"poor", "middling", "rich"}
    for item in rep["classes"].values():
        assert set(item) == {"share", "base_share", "norm_days", "norm_per_resident", "money_per_resident",
                             "needs_per_resident_day", "afford"}
    assert rep["wealth_norm"] == norm and rep["money_norm"] == norm + 500
    assert rep["deficit"] == norm + 500 - norm // 2 - 100
    assert rep["r"] == pytest.approx(0.5, abs=1e-3)
    assert rep["classes"]["rich"]["norm_per_resident"] > rep["classes"]["poor"]["norm_per_resident"]
    assert [rep["classes"][k]["norm_days"] for k in ("poor", "middling", "rich")] == [3.0, 7.0, 21.0]
