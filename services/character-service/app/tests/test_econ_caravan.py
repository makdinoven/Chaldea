"""FEAT-192 QA (#8): pure caravan math (``econ_caravan``) — no DB, no clock, no RNG.

Contract cases of the ledger (caravan op types / escrow kind) live in ``econ_contract_cases.py`` and run in all four
econ services through ``test_econ_contract.py``; they are not repeated here.
"""

import itertools
from dataclasses import replace

import pytest

import econ_caravan as cv
from econ_sim import GroupDef, SimParams

FOOD = GroupDef(code="food", name="Продовольствие", base_price=2, norm_per_1000=1, norm_days=1, is_food=True)
ORE = GroupDef(code="ore_metal", name="Руда и металл", base_price=10, norm_per_1000=1, norm_days=1)
WOOD = GroupDef(code="wood", name="Древесина", base_price=5, norm_per_1000=1, norm_days=1)
GROUPS = {g.code: g for g in (ORE, WOOD, FOOD)}            # insertion order deliberately not the plan order

P = SimParams()


def good(stock, norm, mult=1.0):
    return cv.GoodMarket(stock=float(stock), norm_stock=float(norm), price_mult=float(mult))


def market(rid, country=1, *, purse=10_000, treasury=0, halted=False, **goods):
    return cv.RegionMarket(region_id=rid, country_id=country, halted=halted, purse=purse, treasury=treasury,
                           goods=goods)


def plan(markets, *, inbound=None, pairs=None, params=P, groups=GROUPS):
    return cv.plan_caravans({m.region_id: m for m in markets}, groups, inbound or {}, pairs or {}, params)


def enabled(a, b, duty=10.0, on=True):
    key = cv.pair_key(a, b)
    return {key: cv.PairRule(key[0], key[1], on, duty)}


# --------------------------------------------------------------------------------------------- small helpers

@pytest.mark.parametrize("value, expected", [
    (1.23456, 1.234), (1.2349999, 1.234), (2, 2.0), (0, 0.0), (-0.0001, -0.001), ("5.5559", 5.555),
    (float("nan"), 0.0), (float("inf"), 0.0), ("garbage", 0.0), (None, 0.0),
])
def test_floor3(value, expected):
    assert cv.floor3(value) == expected


def test_pair_key_is_normalised():
    assert cv.pair_key(7, 3) == (3, 7) == cv.pair_key(3, 7)
    assert cv.pair_key("2", 1) == (1, 2)


@pytest.mark.parametrize("base, mult, expected", [
    (2, 1.0, 2.0), (2, 0.33333, 0.6667), (10, 1.23456, 12.3456), (3, 0.00005, 0.0002), (0, 1.5, 0.0),
    (5, 0, 0.0), (5, -1, 0.0),
])
def test_unit_price_rounds_half_up_to_four_decimals(base, mult, expected):
    assert cv.unit_price(base, mult) == expected


def test_route_same_country_is_domestic_without_duty():
    assert cv.route(1, 1, {}, P) == cv.Route(1, 0.0)
    # even a (nonsensical) pair row for the same country does not add a duty
    assert cv.route(4, 4, enabled(4, 5, 50), P) == cv.Route(1, 0.0)


def test_route_between_countries_needs_an_enabled_pair():
    pairs = enabled(2, 1, duty=12.5)
    assert cv.route(1, 2, pairs, P) == cv.Route(2, 12.5)
    assert cv.route(2, 1, pairs, P) == cv.Route(2, 12.5)          # symmetric, normalised key
    assert cv.route(1, 3, pairs, P) is None                       # missing pair = forbidden (default)
    assert cv.route(1, 2, enabled(1, 2, on=False), P) is None     # disabled pair
    assert cv.route(None, 2, pairs, P) is None and cv.route(1, None, pairs, P) is None


def test_route_uses_travel_params_with_a_floor_of_one():
    params = replace(P, caravan_travel_domestic=3, caravan_travel_foreign=5)
    assert cv.route(1, 1, {}, params).travel_runs == 3
    assert cv.route(1, 2, enabled(1, 2), params).travel_runs == 5
    zero = replace(P, caravan_travel_domestic=0, caravan_travel_foreign=0)
    assert cv.route(1, 1, {}, zero).travel_runs == 1
    assert cv.route(1, 2, enabled(1, 2), zero).travel_runs == 1


@pytest.mark.parametrize("units, price, pct, expected", [
    (10, 1.5, 0, (15, 0)),
    (3.333, 3, 10, (9, 0)),           # value floor(9.999) = 9, duty floor(0.9) = 0
    (100, 1, 10, (100, 10)),
    (100, 1, 100, (100, 100)),
    (99.999, 1, 10, (99, 9)),         # duty from the floored value
    (12.5, 1.6, 0, (20, 0)),
    (0, 5, 10, (0, 0)), (-1, 5, 10, (0, 0)), (5, 0, 10, (0, 0)),
    (10, 2, -5, (20, 0)),             # a negative duty is ignored
])
def test_price_caravan_floors_value_and_duty(units, price, pct, expected):
    assert cv.price_caravan(units, price, pct) == expected


@pytest.mark.parametrize("budget, price, pct, expected", [
    (100, 1, 0, 100.0), (100, 1, 100, 50.0), (10, 3, 0, 3.333), (110, 1, 10, 100.0),
    (0, 1, 0, 0.0), (-5, 1, 0, 0.0), (100, 0, 0, 0.0),
])
def test_affordable_units(budget, price, pct, expected):
    assert cv.affordable_units(budget, price, pct) == expected


def test_affordable_units_never_cost_more_than_the_budget():
    for budget, price, pct in itertools.product((1, 7, 10, 99, 1000, 123_457), (0.1, 0.6667, 1, 2.5, 12.3456, 300),
                                                (0, 3.5, 10, 33.33, 100)):
        units = cv.affordable_units(budget, price, pct)
        value, duty = cv.price_caravan(units, price, pct)
        assert value + duty <= budget, (budget, price, pct, units)


@pytest.mark.parametrize("cost, purse, treasury, food, expected", [
    (100, 150, 0, False, (100, 0)),
    (100, 150, 500, True, (100, 0)),           # the purse pays first
    (100, 60, 50, True, (60, 40)),             # food: the treasury tops up
    (100, 60, 50, False, None),                # non-food never touches the treasury
    (100, 60, 30, True, None),                 # both budgets short
    (100, 0, 100, True, (0, 100)),
    (100, -20, 100, True, (0, 100)),           # negative budgets count as 0
    (100, 50, -10, True, None),
    (0, 0, 0, False, (0, 0)),
])
def test_split_payment(cost, purse, treasury, food, expected):
    assert cv.split_payment(cost, purse, treasury, food) == expected


# --------------------------------------------------------------------------------------------- plan_caravans

def test_basic_domestic_plan():
    plans = plan([market(1, food=good(1000, 200, 0.5)), market(2, food=good(0, 300))])
    assert len(plans) == 1
    p = plans[0]
    assert (p.from_region_id, p.to_region_id, p.from_country_id, p.to_country_id) == (1, 2, 1, 1)
    assert (p.group_code, p.is_food, p.travel_runs, p.duty_pct, p.duty) == ("food", True, 1, 0.0, 0)
    # supply = 25 % x (1000 - 200) = 200; price = 2 x 0.5 (the seller's market price)
    assert (p.units, p.unit_price, p.value, p.paid_purse, p.paid_treasury) == (200.0, 1.0, 200, 200, 0)
    assert p.cost == p.value + p.duty == p.paid_purse + p.paid_treasury


@pytest.mark.parametrize("share", [0.1, 0.25, 0.5, 1.0])
def test_seller_ships_at_most_share_of_surplus_and_keeps_its_norm(share):
    params = replace(P, caravan_surplus_share=share)
    buyers = [market(rid, food=good(0, 1000)) for rid in (2, 3, 4, 5)]
    plans = plan([market(1, food=good(700, 300))] + buyers, params=params)
    shipped = sum(p.units for p in plans if p.from_region_id == 1)
    assert shipped == pytest.approx(cv.floor3(share * 400))
    assert 700 - shipped >= 300


def test_zero_surplus_share_sends_nothing():
    assert plan([market(1, food=good(1000, 100)), market(2, food=good(0, 100))],
                params=replace(P, caravan_surplus_share=0)) == []


def test_buyer_never_above_its_norm_counting_goods_on_the_road():
    sellers = [market(1, food=good(5000, 100)), market(3, food=good(5000, 100))]
    plans = plan(sellers + [market(2, food=good(40, 300))], inbound={(2, "food"): 210.0})
    assert sum(p.units for p in plans) == 50.0                   # 300 - 40 - 210
    assert plan(sellers + [market(2, food=good(40, 300))], inbound={(2, "food"): 260.0}) == []
    # inbound of another group / region does not count
    plans = plan(sellers + [market(2, food=good(40, 300))], inbound={(2, "ore_metal"): 999, (9, "food"): 999})
    assert sum(p.units for p in plans) == 260.0


def test_a_region_is_never_seller_and_buyer_of_one_group():
    markets = [market(1, food=good(1000, 100)), market(2, food=good(0, 100)), market(3, food=good(100, 100))]
    plans = plan(markets)
    assert {p.from_region_id for p in plans}.isdisjoint({p.to_region_id for p in plans})
    assert all(3 not in (p.from_region_id, p.to_region_id) for p in plans)      # exactly at norm: neither


def test_most_deprived_buyer_first():
    # one seller with 200 to spare; buyer 3 (0 %) beats buyer 2 (33 %) though it has the bigger id
    plans = plan([market(1, food=good(1000, 200)), market(2, food=good(100, 300)), market(3, food=good(0, 300))])
    assert [(p.to_region_id, p.units) for p in plans] == [(3, 200.0)]


def test_ties_between_buyers_go_to_the_lower_region_id():
    plans = plan([market(1, food=good(1000, 600)), market(5, food=good(0, 300)), market(4, food=good(0, 300))])
    assert [(p.to_region_id, p.units) for p in plans] == [(4, 100.0)]


def test_domestic_then_cheap_sellers_first():
    pairs = enabled(1, 2, duty=10)
    markets = [
        market(2, food=good(0, 1000)),                            # buyer, country 1
        market(1, food=good(1000, 200, 1.5)),                     # domestic, dear: supply 200
        market(4, food=good(1000, 200, 1.0)),                     # domestic, cheaper: supply 200
        market(3, country=2, food=good(1000, 200, 0.5)),          # foreign, cheapest: supply 200
    ]
    plans = plan(markets, pairs=pairs)
    assert [p.from_region_id for p in plans] == [4, 1, 3]
    foreign = plans[2]
    assert (foreign.travel_runs, foreign.duty_pct, foreign.from_country_id, foreign.to_country_id) == (2, 10.0, 2, 1)
    assert (foreign.unit_price, foreign.value, foreign.duty) == (1.0, 200, 20)
    assert foreign.paid_purse + foreign.paid_treasury == foreign.value + foreign.duty
    # forbidden pair: the foreign seller is never used
    assert [p.from_region_id for p in plan(markets)] == [4, 1]


def test_seller_ties_go_to_the_lower_region_id():
    plans = plan([market(2, food=good(0, 1000)), market(7, food=good(1000, 600)), market(5, food=good(1000, 600))])
    assert [p.from_region_id for p in plans] == [5, 7]


def test_halted_region_does_not_export_but_imports():
    # region 1 has a surplus but a raid: no exports
    assert plan([market(1, halted=True, food=good(1000, 100)), market(2, food=good(0, 100))]) == []
    # region 1 is halted and hungry: it still buys
    plans = plan([market(1, halted=True, food=good(0, 100)), market(2, food=good(1000, 100))])
    assert [(p.from_region_id, p.to_region_id) for p in plans] == [(2, 1)]


def test_zero_norm_group_is_skipped_on_both_sides():
    assert plan([market(1, food=good(1000, 0)), market(2, food=good(0, 100))]) == []
    assert plan([market(1, food=good(1000, 100)), market(2, food=good(0, 0))]) == []
    assert plan([market(1, food=good(1000, 100)), market(2)]) == []                 # the buyer has no row


def test_min_value_drops_dust_caravans():
    markets = [market(1, food=good(1000, 100)), market(2, food=good(96, 100))]     # need 4 x price 2 = 8
    assert plan(markets) == []
    plans = plan(markets, params=replace(P, caravan_min_value=8))
    assert [(p.units, p.value) for p in plans] == [(4.0, 8)]


def test_min_value_skips_a_small_seller_but_tries_the_next():
    markets = [market(2, food=good(0, 1000)), market(1, food=good(104, 100)),     # supply 1 -> value 2 < 10
               market(3, food=good(1000, 100, 1.2))]
    plans = plan(markets)
    assert [p.from_region_id for p in plans] == [3]


def test_max_per_run_caps_the_whole_plan():
    buyers = [market(rid, food=good(0, 100), ore_metal=good(0, 100)) for rid in (2, 3, 4)]
    sellers = [market(1, food=good(10_000, 100), ore_metal=good(10_000, 100))]
    assert len(plan(sellers + buyers)) == 6
    capped = plan(sellers + buyers, params=replace(P, caravan_max_per_run=2))
    assert len(capped) == 2
    assert capped == plan(sellers + buyers)[:2]
    assert plan(sellers + buyers, params=replace(P, caravan_max_per_run=0)) == []


def test_caravans_disabled_plans_nothing():
    assert plan([market(1, food=good(1000, 100)), market(2, food=good(0, 100))],
                params=replace(P, caravans_enabled=0)) == []


def test_food_first_and_purse_budget_shared_by_all_groups():
    # purse 400 -> 25 % = 100 marks for the whole run; food (price 1) takes it all, ore gets nothing
    markets = [market(1, food=good(1000, 200, 0.5), ore_metal=good(1000, 200)),
               market(2, purse=400, food=good(0, 300), ore_metal=good(0, 300))]
    plans = plan(markets)
    assert [(p.group_code, p.units, p.value, p.paid_purse) for p in plans] == [("food", 100.0, 100, 100)]


def test_non_food_groups_follow_code_order_after_food():
    markets = [market(1, food=good(1000, 100), ore_metal=good(1000, 100), wood=good(1000, 100)),
               market(2, purse=1_000_000, food=good(0, 100), ore_metal=good(0, 100), wood=good(0, 100))]
    assert [p.group_code for p in plan(markets)] == ["food", "ore_metal", "wood"]


def test_food_is_topped_up_from_the_treasury():
    # purse 40 -> 10 marks; treasury 1000 -> 500 marks for food
    markets = [market(1, food=good(1000, 200, 0.5)), market(2, purse=40, treasury=1000, food=good(0, 300))]
    plans = plan(markets)
    assert [(p.units, p.value, p.paid_purse, p.paid_treasury) for p in plans] == [(200.0, 200, 10, 190)]


def test_non_food_never_uses_the_treasury():
    markets = [market(1, ore_metal=good(1000, 200)), market(2, purse=40, treasury=1_000_000, ore_metal=good(0, 300))]
    plans = plan(markets)
    assert [(p.units, p.value, p.paid_purse, p.paid_treasury) for p in plans] == [(1.0, 10, 10, 0)]


def test_negative_treasury_pays_nothing():
    markets = [market(1, food=good(1000, 200, 0.5)), market(2, purse=40, treasury=-5000, food=good(0, 300))]
    assert [(p.units, p.paid_purse, p.paid_treasury) for p in plan(markets)] == [(10.0, 10, 0)]


def test_cannot_pay_ships_what_is_affordable():
    markets = [market(1, food=good(1000, 200)), market(2, purse=100, food=good(0, 300))]     # 25 marks, price 2
    assert [(p.units, p.value) for p in plan(markets)] == [(12.5, 25)]
    assert plan([market(1, food=good(1000, 200)), market(2, purse=0, food=good(0, 300))]) == []
    assert plan([market(1, food=good(1000, 200)), market(2, purse=-100, food=good(0, 300))]) == []


def test_budget_with_duty_stays_within_the_purse_share():
    pairs = enabled(1, 2, duty=50)
    markets = [market(1, country=2, food=good(10_000, 100, 1.5)), market(2, purse=1000, food=good(0, 10_000))]
    plans = plan(markets, pairs=pairs)
    assert len(plans) == 1
    p = plans[0]
    assert p.value + p.duty <= 250 and p.paid_purse == p.value + p.duty
    assert (p.unit_price, p.units, p.value, p.duty) == (3.0, 55.555, 166, 83)


def test_budget_is_spent_across_several_sellers_and_buyers():
    markets = [market(1, food=good(1000, 200)), market(3, food=good(1000, 200)),
               market(2, purse=1200, food=good(0, 1000))]                      # 300 marks, price 2 -> 150 units
    plans = plan(markets)
    assert sum(p.value for p in plans) <= 300
    assert sum(p.units for p in plans) == 150.0
    assert [p.from_region_id for p in plans] == [1]


def test_plan_is_deterministic_and_order_independent():
    markets = [
        market(1, food=good(900, 100, 0.8), ore_metal=good(10, 300), wood=good(500, 100)),
        market(2, purse=5000, treasury=300, food=good(10, 200), ore_metal=good(900, 100)),
        market(3, country=2, purse=7000, food=good(0, 400), wood=good(0, 300), ore_metal=good(0, 100)),
        market(4, halted=True, food=good(5000, 100), wood=good(20, 100)),
        market(5, country=2, food=good(800, 100, 1.4), ore_metal=good(50, 100)),
    ]
    pairs = enabled(1, 2, 15)
    inbound = {(3, "food"): 40.0}
    first = plan(markets, pairs=pairs, inbound=inbound)
    assert first
    assert plan(markets, pairs=pairs, inbound=inbound) == first
    assert plan(list(reversed(markets)), pairs=pairs, inbound=inbound) == first
    reordered_groups = dict(reversed(list(GROUPS.items())))
    assert plan(markets, pairs=pairs, inbound=inbound, groups=reordered_groups) == first
    # invariants of every plan
    by_market = {m.region_id: m for m in markets}
    for p in first:
        assert p.paid_purse + p.paid_treasury == p.value + p.duty
        assert p.value >= P.caravan_min_value and p.units > 0
        assert not by_market[p.from_region_id].halted
        if not p.is_food:
            assert p.paid_treasury == 0
        if p.from_country_id == p.to_country_id:
            assert (p.duty, p.travel_runs) == (0, 1)
        else:
            assert p.travel_runs == 2 and p.duty_pct == 15.0
    for rid, m in by_market.items():
        spent_purse = sum(p.paid_purse for p in first if p.to_region_id == rid)
        spent_treasury = sum(p.paid_treasury for p in first if p.to_region_id == rid)
        assert spent_purse <= int(max(0, m.purse) * P.caravan_purse_share)
        assert spent_treasury <= int(max(0, m.treasury) * P.caravan_treasury_food_share)
        for code, g in m.goods.items():
            out = sum(p.units for p in first if p.from_region_id == rid and p.group_code == code)
            inn = sum(p.units for p in first if p.to_region_id == rid and p.group_code == code)
            assert out <= max(0.0, P.caravan_surplus_share * (g.stock - g.norm_stock)) + 1e-9
            assert g.stock - out >= min(g.stock, g.norm_stock) - 1e-9
            assert g.stock + inbound.get((rid, code), 0) + inn <= max(g.norm_stock, g.stock) + 1e-9


# --------------------------------------------------------------------------------------------- clamp_dispatch

def _plan(**kw):
    data = dict(from_region_id=1, to_region_id=2, from_country_id=1, to_country_id=1, group_code="food",
                is_food=True, units=200.0, unit_price=1.0, value=200, duty=0, duty_pct=0.0, travel_runs=1,
                paid_purse=150, paid_treasury=50)
    data.update(kw)
    return cv.CaravanPlan(**data)


def test_clamp_unchanged_when_nothing_moved():
    p = _plan()
    assert cv.clamp_dispatch(p, 1000, 200, 10_000, 10_000) == p


def test_clamp_seller_keeps_its_norm():
    got = cv.clamp_dispatch(_plan(), 250, 200, 10_000, 10_000)
    assert (got.units, got.value, got.paid_purse, got.paid_treasury) == (50.0, 50, 50, 0)
    assert cv.clamp_dispatch(_plan(), 200, 200, 10_000, 10_000) is None
    assert cv.clamp_dispatch(_plan(), 150, 200, 10_000, 10_000) is None


def test_clamp_to_locked_balances_never_above_the_plan():
    got = cv.clamp_dispatch(_plan(), 1000, 200, 100, 10_000)        # purse shrank 150 -> 100
    assert (got.units, got.value, got.paid_purse, got.paid_treasury) == (150.0, 150, 100, 50)
    got = cv.clamp_dispatch(_plan(), 1000, 200, 10_000, -30)        # treasury went negative
    assert (got.units, got.paid_purse, got.paid_treasury) == (150.0, 150, 0)
    got = cv.clamp_dispatch(_plan(), 1000, 200, 0, 0)
    assert got is None


def test_clamp_non_food_ignores_the_treasury():
    p = _plan(group_code="ore_metal", is_food=False, paid_purse=200, paid_treasury=0)
    got = cv.clamp_dispatch(p, 1000, 200, 80, 1_000_000)
    assert (got.units, got.value, got.paid_purse, got.paid_treasury) == (80.0, 80, 80, 0)


def test_clamp_keeps_duty_on_top():
    p = _plan(duty_pct=10.0, value=200, duty=20, paid_purse=220, paid_treasury=0, is_food=False,
              group_code="ore_metal")
    got = cv.clamp_dispatch(p, 1000, 200, 110, 0)
    assert (got.units, got.value, got.duty, got.paid_purse) == (100.0, 100, 10, 110)


def test_clamp_below_min_value_is_dropped():
    assert cv.clamp_dispatch(_plan(), 205, 200, 10_000, 10_000, min_value=10) is None
    got = cv.clamp_dispatch(_plan(), 205, 200, 10_000, 10_000, min_value=5)
    assert (got.units, got.value) == (5.0, 5)
