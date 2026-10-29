"""FEAT-182 Q2: pure simulation math of the living regions (``econ_sim``, section 3.4).

Group and template data come from migration 028 (the seeded defaults), so these tests exercise the same
numbers the tick runner reads from the DB.
"""

import importlib.util
import math
import os
import random
import re

import pytest

import econ_sim as S

MIGRATION_PATH = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "028_econ_living_regions.py")


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_028_econ_living_regions", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mig = _load_migration()

GROUPS = {
    code: S.GroupDef(code=code, name=name, base_price=base, norm_per_1000=norm, norm_days=days,
                     prosperity_elasticity=pe, price_elasticity=pr, is_food=bool(food),
                     inputs=dict(mig.INPUTS.get(code, [])))
    for code, name, base, norm, days, pe, pr, food in mig.GROUPS
}
CODES = list(mig.GROUP_CODES)
TEMPLATES = {t[0]: {"noun": t[3], "gender": t[4], "pop": t[5], "tax": t[6]} for t in mig.TEMPLATES}
P = S.DEFAULT_PARAMS


def _template_goods(code):
    return {g: (prod, cmult) for g, prod, cmult in mig.template_goods(code)}


def _fresh(code, population=None):
    """(region, goods, purse) of a freshly applied template: stock = norm, prices x1, purse = 7 days of needs."""
    pop = population if population is not None else TEMPLATES[code]["pop"]
    goods = S.starting_goods(GROUPS, _template_goods(code), pop)
    region = S.RegionState(population=pop, tax_rate=TEMPLATES[code]["tax"])
    return region, goods, S.starting_purse(GROUPS, goods, pop)


def _finite(*values):
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)


# --------------------------------------------------------------------------------------------- params / seed

def test_default_params_match_the_migration_seed():
    assert S.SimParams().to_dict() == pytest.approx(mig.DEFAULT_PARAMS)


def test_params_from_partial_mapping_coerces_and_ignores_unknown():
    params = S.SimParams.from_mapping({"dt": "0.5", "treasury_release_ticks": "4", "bogus": 1, "price_max": None})
    assert params.dt == 0.5
    assert params.treasury_release_ticks == 4 and isinstance(params.treasury_release_ticks, int)
    assert params.price_max == P.price_max          # None -> default
    assert S.SimParams.from_mapping(None) == P
    assert S.SimParams.from_mapping({}) == P


@pytest.mark.parametrize("template", list(mig.RATIOS))
def test_template_production_rule_matches_migration_seed(template):
    ratios = dict(zip(CODES, mig.RATIOS[template]))
    cmults = mig.CMULT.get(template, {})
    expected = {g: prod for g, prod, _c in mig.template_goods(template)}
    assert S.template_production_per_1000(GROUPS, ratios, cmults) == pytest.approx(expected, abs=1e-3)


# --------------------------------------------------------------------------------------------- price curve

def test_price_curve_reference_points():
    assert S.price_mult(100, 100) == pytest.approx(1.0)
    assert S.price_mult(300, 100) == pytest.approx(0.5, abs=1e-3)       # r = 3 -> x0.5
    assert S.price_mult(18, 100) == pytest.approx(2.95, abs=0.06)        # r ~ 0.18 -> ~x3
    assert S.price_mult(50, 100) > 1.0 > S.price_mult(150, 100)


def test_price_curve_clamps_and_degenerate_inputs():
    assert S.price_mult(0, 100) == P.price_max
    assert S.price_mult(-5, 100) == P.price_max
    assert S.price_mult(1, 100) == P.price_max                           # r = 0.01 floor -> clamp
    assert S.price_mult(10_000, 100) == P.price_min
    assert S.price_mult(5, 0) == 1.0                                     # norm 0 -> neutral
    assert S.price_mult(0, 0) == 1.0
    custom = S.SimParams(price_min=0.8, price_max=1.5)
    assert S.price_mult(0, 100, custom) == 1.5
    assert S.price_mult(10_000, 100, custom) == 0.8


def test_price_curve_is_monotonic_non_increasing():
    prices = [S.price_mult(stock, 100) for stock in range(0, 500, 5)]
    assert all(a >= b for a, b in zip(prices, prices[1:]))
    assert all(P.price_min <= p <= P.price_max for p in prices)


# --------------------------------------------------------------------------------------------- norm stock

def test_norm_stock_of_finished_group_is_household_need():
    goods = S.starting_goods(GROUPS, _template_goods("capital"), 25000)
    jewelry = GROUPS["jewelry"]
    expected = jewelry.norm_days * jewelry.norm_per_1000 * 1.3 * 25        # cmult 1.3, pop_k 25
    assert S.norm_stock("jewelry", GROUPS, goods, 25000) == pytest.approx(expected)


def test_norm_stock_of_raw_group_includes_processing_inputs():
    goods = {c: S.GoodState(group_code=c) for c in CODES}
    goods["weapons"].production_per_1000 = 2.0
    goods["armor"].production_per_1000 = 1.0
    pop = 4000
    ore = GROUPS["ore_metal"]
    household = ore.norm_per_1000 * 4
    processing = (2.0 * 4 * 3) + (1.0 * 4 * 1)                            # weapons x3 ore, armor x1 ore
    assert S.norm_stock("ore_metal", GROUPS, goods, pop) == pytest.approx(ore.norm_days * (household + processing))
    # groups with no goods row do not contribute
    del goods["armor"]
    assert S.norm_stock("ore_metal", GROUPS, goods, pop) == pytest.approx(ore.norm_days * (household + 2.0 * 4 * 3))


def test_starting_goods_have_stock_at_norm_and_neutral_prices():
    goods = S.starting_goods(GROUPS, _template_goods("port"), 12000)
    assert set(goods) == set(CODES)
    for good in goods.values():
        assert good.stock == good.norm_stock > 0
        assert good.price_mult == 1.0
        assert S.price_mult(good.stock, good.norm_stock) == pytest.approx(1.0)


# --------------------------------------------------------------------------------------------- production chains

def _rich_purse(region, goods):
    return int(S.needs_cost_day(GROUPS, goods, region.population, params=P, base_prices=True) * 100)


def test_chain_production_is_limited_by_input_stock():
    region, goods, _purse = _fresh("fortress")
    goods["ore_metal"].stock = 1.5                                       # enough for half a weapon
    potential_weapons = goods["weapons"].production_per_1000 * region.population / 1000 * P.dt
    assert potential_weapons > 0.5
    goods["armor"].production_per_1000 = 0.0
    goods["jewelry"].production_per_1000 = 0.0
    goods["tools"].production_per_1000 = 0.0
    goods["ore_metal"].production_per_1000 = 0.0
    result = S.simulate_region(region, goods, GROUPS, purse=_rich_purse(region, goods), treasury=0)
    assert result.goods["weapons"].last_produced == pytest.approx(0.5)
    assert result.goods["ore_metal"].stock == pytest.approx(0.0)
    assert result.goods["ore_metal"].stock >= 0


def test_processing_order_weapons_first_starves_later_chains():
    region, goods, _purse = _fresh("mining")
    goods["ore_metal"].production_per_1000 = 0.0
    goods["ore_metal"].stock = 0.6                                       # 0.2 weapons, below their potential
    result = S.simulate_region(region, goods, GROUPS, purse=_rich_purse(region, goods), treasury=0)
    assert result.goods["weapons"].last_produced == pytest.approx(0.2)
    assert result.goods["armor"].last_produced == pytest.approx(0.0)    # ore already spent on weapons
    assert result.goods["tools"].last_produced == pytest.approx(0.0)


def test_no_ore_makes_weapons_more_expensive_over_time():
    region, goods, purse = _fresh("fortress")
    goods["ore_metal"].production_per_1000 = 0.0
    goods["ore_metal"].stock = 0.0
    treasury = 0
    prices = []
    for _ in range(60):
        r = S.simulate_region(region, goods, GROUPS, purse=purse, treasury=treasury)
        region, goods, purse, treasury = r.region, r.goods, r.purse_after, r.treasury_after
        assert goods["weapons"].last_produced == 0.0
        prices.append(goods["weapons"].price_mult)
    assert all(a <= b + 1e-9 for a, b in zip(prices, prices[1:]))
    assert prices[-1] > 1.5
    assert goods["ore_metal"].price_mult == P.price_max


def test_raw_production_scales_with_stability_and_hunger():
    region, goods, purse = _fresh("agrarian")
    base = S.simulate_region(region, goods, GROUPS, purse=purse, treasury=0).goods["food"].last_produced
    low_stab = S.RegionState(population=region.population, tax_rate=region.tax_rate, stability=0.0)
    assert S.simulate_region(low_stab, goods, GROUPS, purse=purse, treasury=0).goods["food"].last_produced \
        == pytest.approx(base * 0.5)
    hungry = S.RegionState(population=region.population, tax_rate=region.tax_rate, stability=70.0, hunger=1.0)
    assert S.simulate_region(hungry, goods, GROUPS, purse=purse, treasury=0).goods["food"].last_produced \
        == pytest.approx(base * (1 - P.hunger_prod_penalty))


# --------------------------------------------------------------------------------------------- affordability

def test_empty_purse_means_no_consumption_and_full_hunger():
    region, goods, _purse = _fresh("port")
    result = S.simulate_region(region, goods, GROUPS, purse=0, treasury=0)
    assert result.affordability == 0.0
    assert all(g.last_consumed == 0.0 for g in result.goods.values())
    assert result.region.hunger == pytest.approx(1.0)
    assert result.region.satisfaction == pytest.approx(0.0)
    assert result.tax == 0 and result.purse_after >= 0


def test_full_purse_and_stock_means_no_hunger():
    region, goods, purse = _fresh("port")
    result = S.simulate_region(region, goods, GROUPS, purse=purse, treasury=0)
    assert result.affordability == 1.0
    assert result.region.hunger == pytest.approx(0.0, abs=1e-9)
    assert result.region.satisfaction == pytest.approx(1.0)


def test_half_affordability_shows_as_hunger():
    region, goods, _purse = _fresh("port")
    cost = S.needs_cost_day(GROUPS, goods, region.population, region.prosperity, P)
    result = S.simulate_region(region, goods, GROUPS, purse=int(cost * 0.5), treasury=0)
    assert result.affordability == pytest.approx(0.5, abs=1e-3)
    assert result.region.hunger == pytest.approx(0.5, abs=0.01)


def test_empty_food_stock_is_hunger_even_with_money():
    region, goods, purse = _fresh("port")
    goods["food"].stock = 0.0
    goods["food"].production_per_1000 = 0.0
    result = S.simulate_region(region, goods, GROUPS, purse=purse, treasury=0)
    assert result.affordability == 1.0
    assert result.region.hunger == pytest.approx(1.0)


def test_consumption_never_exceeds_stock():
    region, goods, purse = _fresh("capital")
    for good in goods.values():
        good.stock = good.norm_stock * 0.01
    result = S.simulate_region(region, goods, GROUPS, purse=purse * 10, treasury=0)
    for good in result.goods.values():
        assert good.stock >= 0.0
        assert good.last_consumed <= good.last_demand + 1e-9


# --------------------------------------------------------------------------------------------- stability / prosperity

def test_hunger_pulls_stability_down_by_rate_down():
    region, goods, _purse = _fresh("port")
    region = S.RegionState(population=region.population, tax_rate=0.10, stability=70.0, prosperity=50.0)
    result = S.simulate_region(region, goods, GROUPS, purse=0, treasury=0)
    # hunger 1, satisfaction 0 -> target clamped to 0; moves 25 % of the gap
    assert result.region.stability == pytest.approx(70.0 - P.stab_rate_down * 70.0)


def test_good_conditions_pull_stability_up_by_rate_up():
    region, goods, purse = _fresh("port")
    region = S.RegionState(population=region.population, tax_rate=0.10, stability=40.0)
    result = S.simulate_region(region, goods, GROUPS, purse=purse, treasury=1000)
    target = P.stab_base - P.stab_goods_w * (1 - result.region.satisfaction)
    assert result.region.stability == pytest.approx(40.0 + P.stab_rate_up * (target - 40.0))
    assert result.region.stability > 40.0


def test_high_tax_and_debt_lower_the_stability_target():
    region, goods, purse = _fresh("port")
    calm = S.simulate_region(S.RegionState(population=region.population, tax_rate=0.10, stability=80.0),
                             goods, GROUPS, purse=purse, treasury=0)
    taxed = S.simulate_region(S.RegionState(population=region.population, tax_rate=0.30, stability=80.0),
                              goods, GROUPS, purse=purse, treasury=0)
    indebted = S.simulate_region(S.RegionState(population=region.population, tax_rate=0.10, stability=80.0),
                                 goods, GROUPS, purse=purse, treasury=-1_000_000)
    assert taxed.region.stability < calm.region.stability
    assert indebted.treasury_after < 0
    assert indebted.region.stability < calm.region.stability


def test_prosperity_moves_a_share_of_the_gap():
    region, goods, purse = _fresh("port")
    poor = S.simulate_region(region, goods, GROUPS, purse=0, treasury=0)
    assert poor.region.prosperity == pytest.approx(50.0 - P.prosp_rate * 50.0)   # target clamped to 0
    rich = S.simulate_region(region, goods, GROUPS, purse=purse * 100, treasury=0)
    target = 100 * (P.prosp_w_sat * rich.region.satisfaction + P.prosp_w_liq * 1.0
                    + P.prosp_w_stab * rich.region.stability / 100)
    assert rich.region.prosperity == pytest.approx(50.0 + P.prosp_rate * (target - 50.0))


def test_simulate_region_does_not_mutate_inputs():
    region, goods, purse = _fresh("magic")
    snapshot = {c: (g.stock, g.price_mult, g.norm_stock) for c, g in goods.items()}
    region_before = S.RegionState(**region.__dict__)
    S.simulate_region(region, goods, GROUPS, purse=purse, treasury=0)
    assert {c: (g.stock, g.price_mult, g.norm_stock) for c, g in goods.items()} == snapshot
    assert region == region_before


# --------------------------------------------------------------------------------------------- money

def test_wage_rule_never_makes_non_negative_treasury_negative():
    rng = random.Random(182)
    for _ in range(5000):
        treasury = rng.choice([0, 1, 7, rng.randint(0, 10_000_000)])
        target = rng.choice([0, rng.randint(0, 10_000_000)])
        net_tax = rng.randint(0, 100_000)
        grant = rng.choice([0, rng.randint(0, 100_000)])
        wages = S.wage_amount(net_tax, grant, treasury, target)
        assert wages >= 0
        assert treasury + net_tax + grant - wages >= 0, (treasury, target, net_tax, grant, wages)


def test_wage_rule_pulls_negative_treasury_back_toward_target():
    treasury = -80_000
    for _ in range(200):
        wages = S.wage_amount(net_tax=1000, grant=0, treasury_before=treasury, treasury_target=5000)
        new_treasury = treasury + 1000 - wages
        assert new_treasury >= treasury
        treasury = new_treasury
    assert treasury >= 0


def test_wage_rule_releases_surplus_above_target():
    assert S.wage_amount(100, 0, treasury_before=1800, treasury_target=1000) == 100 + 800 // 8
    assert S.wage_amount(100, 50, treasury_before=1000, treasury_target=1000) == 150
    assert S.wage_amount(0, 0, treasury_before=0, treasury_target=1_000_000) == 0


def test_tick_tax_is_capped_by_purse_and_money_balances():
    region, goods, _purse = _fresh("capital")
    result = S.simulate_region(region, goods, GROUPS, purse=7, treasury=0, grant=0, country_tax_rate=0.1)
    assert 0 <= result.tax <= 7
    assert result.purse_after >= 0
    full = S.simulate_region(region, goods, GROUPS, purse=10**9, treasury=0, grant=300, country_tax_rate=0.1)
    assert full.tax == math.floor(full.income * region.tax_rate)
    assert full.country_tax == math.floor(full.tax * 0.1)
    assert full.purse_after == 10**9 - full.tax + full.wages
    assert full.treasury_after == 0 + (full.tax - full.country_tax) + 300 - full.wages
    assert full.treasury_after >= 0
    assert full.region.treasury_target == math.floor(full.tax * 4 * P.treasury_reserve_days)


def test_country_grants_split_by_population_within_pool():
    grants = S.country_grants(100_000, {1: 1000, 2: 3000})
    assert grants == {1: 6250, 2: 18750}
    rng = random.Random(7)
    for _ in range(2000):
        balance = rng.randint(-1000, 10_000_000)
        pops = {i: rng.randint(0, 50_000) for i in range(rng.randint(1, 6))}
        grants = S.country_grants(balance, pops)
        pool = math.floor(max(0, balance) * P.country_grant_share)
        assert set(grants) == set(pops)
        assert all(g >= 0 for g in grants.values())
        assert sum(grants.values()) <= pool


def test_country_grants_nothing_for_empty_or_negative_country():
    assert S.country_grants(0, {1: 1000}) == {1: 0}
    assert S.country_grants(-500, {1: 1000, 2: 10}) == {1: 0, 2: 0}
    assert S.country_grants(1000, {1: 0, 2: 0}) == {1: 0, 2: 0}
    assert S.country_grants(1000, {}) == {}


# --------------------------------------------------------------------------------------------- card

@pytest.mark.parametrize("noun,gender,fed,rich,poor", [
    ("Город", "m", "Город сыт", "Богатый город", "Бедный город"),
    ("Крепость", "f", "Крепость сыта", "Богатая крепость", "Бедная крепость"),
    ("Село", "n", "Село сыто", "Богатое село", "Бедное село"),
    ("Округа", "F", "Округа сыта", "Богатая округа", "Бедная округа"),   # case-insensitive
    ("Край", None, "Край сыт", "Богатый край", "Бедный край"),           # missing gender -> m
])
def test_card_phrases_follow_noun_gender(noun, gender, fed, rich, poor):
    assert S.food_label("fed", noun, gender) == fed
    assert S.food_label("hunger", noun, gender) == f"{noun} голодает"
    assert S.prosperity_label("rich", noun, gender) == rich
    assert S.prosperity_label("poor", noun, gender) == poor


def test_card_state_thresholds():
    assert [S.food_state(h) for h in (0.0, 0.029, 0.03, 0.149, 0.15, 1.0)] == \
        ["fed", "fed", "tight", "tight", "hunger", "hunger"]
    assert S.treasury_state(-1, 100) == "debt"
    assert S.treasury_state(0, 0) == "ok"
    assert S.treasury_state(100, 100) == "full"
    assert S.treasury_state(40, 100) == "ok"
    assert S.treasury_state(39, 100) == "low"
    assert [S.stability_state(s) for s in (90, 70, 69.9, 45, 25, 24.9)] == \
        ["calm", "calm", "uneasy", "uneasy", "unrest", "riot"]
    assert [S.prosperity_state(p) for p in (75, 50, 25, 24.9)] == ["rich", "wealthy", "modest", "poor"]
    assert S.price_trend(1.2, 1.0) == "up" and S.price_trend(0.8, 1.0) == "down"
    assert S.price_trend(1.01, 1.0) == "flat" and S.price_trend(1.0, 0) == "flat"
    assert [S.group_level(m) for m in (0.5, 0.8, 1.0, 1.3, 2.0)] == ["very_low", "low", "normal", "high", "very_high"]


def test_region_card_lists_shortages_surpluses_and_has_no_numbers():
    region, goods, _purse = _fresh("fortress")
    goods["weapons"].price_mult = 2.5
    goods["food"].price_mult = 0.6
    region = S.RegionState(population=region.population, tax_rate=0.06, stability=30.0, prosperity=10.0,
                           hunger=0.2, treasury_target=1000)
    card = S.region_card(region, goods, GROUPS, treasury=-5, noun="Крепость", gender="f", group_order=CODES)
    assert card["food"]["label"] == "Крепость голодает"
    assert card["prosperity"]["label"] == "Бедная крепость"
    assert card["treasury"]["state"] == "debt"
    assert card["shortages"] == ["Оружие"]
    assert card["surpluses"] == ["Продовольствие"]
    assert card["phrases"][0] == "Крепость голодает"
    assert "Волнения" in card["phrases"] and "Казна в долгах" in card["phrases"]
    assert "Нехватка: оружие" in card["phrases"] and "Избыток: продовольствие" in card["phrases"]
    assert [g["code"] for g in card["groups"]] == CODES
    for phrase in card["phrases"]:
        assert not re.search(r"\d", phrase), phrase


def test_calm_region_card_is_short():
    region, goods, _purse = _fresh("port")
    region_ok = S.RegionState(population=region.population, tax_rate=0.1, treasury_target=1000)
    card = S.region_card(region_ok, goods, GROUPS, treasury=500, noun="Порт", gender="m", group_order=CODES)
    assert card["phrases"] == ["Порт сыт", "Цены обычные"]
    assert card["shortages"] == [] and card["surpluses"] == []


# --------------------------------------------------------------------------------------------- long runs

def _run(template, ticks, *, purse=None, treasury=0, country=0, mutate=None):
    region, goods, start_purse = _fresh(template)
    if mutate:
        mutate(region, goods)
    purse = start_purse if purse is None else purse
    pop = region.population
    for i in range(ticks):
        grant = S.country_grants(country, {1: pop})[1]
        country -= grant
        r = S.simulate_region(region, goods, GROUPS, purse=purse, treasury=treasury, grant=grant)
        country += r.country_tax
        prev_treasury = treasury
        region, goods, purse, treasury = r.region, r.goods, r.purse_after, r.treasury_after
        yield i, r, prev_treasury


@pytest.mark.parametrize("template", list(TEMPLATES))
def test_forty_ticks_stay_bounded(template):
    last = None
    for i, r, prev_treasury in _run(template, 40):
        region = r.region
        assert _finite(region.stability, region.prosperity, region.hunger, region.satisfaction,
                       r.needs_cost_day, r.affordability), (template, i)
        assert 0 <= region.stability <= 100 and 0 <= region.prosperity <= 100
        assert 0 <= region.hunger <= 1 and 0 <= region.satisfaction <= 1
        assert r.purse_after >= 0
        assert r.treasury_after >= 0 or prev_treasury < 0
        assert min(r.tax, r.wages, r.income, r.country_tax) >= 0
        for code, g in r.goods.items():
            assert _finite(g.stock, g.norm_stock, g.price_mult, g.last_produced, g.last_consumed), (template, code)
            assert P.price_min - 1e-9 <= g.price_mult <= P.price_max + 1e-9
            assert 0 <= g.stock <= P.stock_cap_mult * g.norm_stock + 1e-6
        last = r
    # a seeded template does not collapse in 10 days: nobody starves, nobody riots
    assert last.region.hunger < S.FOOD_HUNGER_HUNGER, template
    assert last.region.stability >= S.STABILITY_UNREST, template
    # specialties (ratio >= 1.4) end up no more expensive than the neutral price
    for code, ratio in zip(CODES, mig.RATIOS[template]):
        if ratio >= 1.4:
            assert last.goods[code].price_mult <= 1.0 + 1e-9, (template, code)


@pytest.mark.parametrize("scenario", ["starve", "broke", "debt", "nobody"])
def test_stress_scenarios_stay_finite_and_never_negative(scenario):
    kwargs = {}
    if scenario == "starve":
        kwargs["mutate"] = lambda region, goods: setattr(goods["food"], "production_per_1000", 0.0)
    elif scenario == "broke":
        kwargs["purse"] = 0
    elif scenario == "debt":
        kwargs["treasury"] = -50_000
    else:
        kwargs["mutate"] = lambda region, goods: setattr(region, "population", 0)
    last = None
    for _i, r, prev_treasury in _run("fortress", 120, **kwargs):
        assert r.purse_after >= 0
        assert r.treasury_after >= 0 or prev_treasury < 0
        assert r.treasury_after >= prev_treasury or prev_treasury >= 0   # debt only shrinks
        assert _finite(r.region.stability, r.region.prosperity, r.region.hunger)
        assert all(_finite(g.stock, g.price_mult) for g in r.goods.values())
        last = r
    if scenario in ("starve", "broke"):
        assert last.region.hunger > S.FOOD_HUNGER_HUNGER
        assert last.region.stability < S.STABILITY_UNREST
    if scenario == "nobody":
        assert last.income == 0 and last.tax == 0 and last.region.hunger == 0.0
