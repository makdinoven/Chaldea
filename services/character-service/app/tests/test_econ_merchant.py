"""FEAT-183 Q3: pure background trade of NPC merchants (``econ_merchant``, contract 3.4 + «Changed by B5»).

No database: the step is fed dataclasses and its output is checked against the hand-computed numbers of the
default params (resident share 0.2 / max 0.6, purse share 0.05, take share 0.25, wholesale 0.5, cash target x2,
cap x3, release 0.25).
"""

import copy
import dataclasses
import random
from collections import defaultdict

import pytest

import econ_core as core
import econ_merchant as em
from econ_sim import DEFAULT_PARAMS

ADMIN = core.SHOP_ORIGIN_ADMIN
PLAYER = core.SHOP_ORIGIN_PLAYER

# Group base prices like migration 028 (food 2, ore 10, tools 40, weapons 120).
GROUP_BASE = {"food": 2, "ore_metal": 10, "tools": 40, "weapons": 120}


def _row(row_id, group="food", *, base_ask=10, stock=0, target=10, origin=ADMIN, off_market=False, base_bid=0):
    return em.ShopRow(row_id=row_id, group=group, off_market=off_market, origin=origin, base_ask=base_ask,
                      base_bid=base_bid, stock=stock, restock_target=target)


def _market(*, purse=10_000, tax_rate=0.1, goods=None, group_base=None, region_id=7):
    goods = goods if goods is not None else {"food": (1000, 1000, 1.0)}
    return em.RegionMarket(
        region_id=region_id, tax_rate=tax_rate, purse=purse,
        goods={code: em.MarketGood(*g) for code, g in goods.items()},
        group_base=dict(GROUP_BASE if group_base is None else group_base),
    )


def _merchant(npc_id, cash, *rows):
    return em.MerchantIn(npc_id=npc_id, cash=cash, rows=tuple(rows))


def _row_res(step, row_id):
    for m in step.merchants:
        for r in m.rows:
            if r.row_id == row_id:
                return r
    raise KeyError(row_id)


def _deltas(legs):
    out = defaultdict(int)
    for leg in legs:
        out[leg.src] -= leg.amount
        out[leg.dst] += leg.amount
    return out


def _check_invariants(market, merchants, step):
    """Every guarantee of 3.4 on one step result."""
    by_id = {int(m.npc_id): m for m in merchants}
    purse = core.AccountRef.purse(market.region_id)
    region = core.AccountRef.region(market.region_id)
    deltas = _deltas(step.legs)

    assert sum(deltas.values()) == 0
    assert all(leg.amount > 0 for leg in step.legs)
    assert step.purse_after >= 0
    assert step.purse_after - step.purse_before == deltas.get(purse, 0)
    assert step.sold_value <= step.purse_budget
    assert deltas.get(region, 0) == step.tax
    assert {leg.leg_type for leg in step.legs} <= {core.LEG_MAIN, core.LEG_TRADE_TAX}
    for m in step.merchants:
        assert m.cash_after >= 0
        assert m.cash_after - m.cash_before == deltas.get(core.AccountRef.character(m.npc_id), 0)
        assert m.cash_before == max(0, int(by_id[m.npc_id].cash))
        assert m.tax == core.trade_tax(m.sold_value, market.tax_rate)
        for r in m.rows:
            assert r.stock_after >= 0 and r.stock_before >= 0
            assert r.stock_after == r.stock_before - r.sold + r.restocked
    for g, value in step.stock_after.items():
        assert value >= 0
        start = max(0.0, float(market.goods[g].stock))
        assert value == pytest.approx(start + step.stock_delta[g])


# --------------------------------------------------------------------------------------------- residents buy

@pytest.mark.parametrize("stock,mult,expected", [
    (5, 1.0, 1),          # 1.0
    (3, 1.0, 1),          # 0.6 -> 1 (floor would freeze the row)
    (2, 1.0, 0),          # 0.4 -> 0
    (5, 2.5, 3),          # share 0.5 -> 2.5 -> 3 (half up)
    (10, 1.25, 3),        # share 0.25 -> 2.5 -> 3
    (10, 4.0, 6),         # 0.8 capped at 0.6
    (0, 1.0, 0),
    (1, 3.0, 1),          # 0.6 -> 1, never more than the stock
])
def test_resident_purchases_round_half_up(stock, mult, expected):
    market = _market(goods={"food": (1000, 1000, mult)})
    step = em.merchant_step(market, [_merchant(1, 0, _row(1, stock=stock, target=0))])
    row = _row_res(step, 1)
    assert row.sold == expected
    assert row.stock_after == stock - expected
    assert row.ask == core.market_ask(10, mult)
    m = step.merchants[0]
    assert m.sold_value == expected * row.ask
    # the goods go to the region stock: n x units (base_ask 10 / food base 2 = 5 units)
    if expected:
        assert step.stock_delta["food"] == pytest.approx(expected * 5)
    else:
        assert step.stock_delta == {}


def test_purse_budget_is_shared_by_all_merchants():
    # purse 500 -> budget floor(500 x 0.05) = 25; each row would sell 2 x 10 = 20
    market = _market(purse=500)
    merchants = [_merchant(2, 0, _row(20, stock=10, target=0)), _merchant(1, 0, _row(10, stock=10, target=0))]
    step = em.merchant_step(market, merchants)
    assert step.purse_budget == 25
    assert [m.npc_id for m in step.merchants] == [1, 2]
    assert _row_res(step, 10).sold == 2                     # lower npc id first
    assert _row_res(step, 20).sold == 0                     # 5 left < ask 10
    assert step.sold_value == 20 <= step.purse_budget
    assert step.purse_after == 480 + step.merchants[0].restock_value + step.merchants[0].upkeep
    _check_invariants(market, merchants, step)


def test_purse_budget_caps_the_count_not_only_the_merchant():
    # budget 25, ask 10, row wants 6 -> only 2 bought
    market = _market(purse=500, goods={"food": (1000, 1000, 3.0)})
    step = em.merchant_step(market, [_merchant(1, 0, _row(1, base_ask=4, stock=10, target=0))])
    row = _row_res(step, 1)
    assert row.ask == 12 and row.sold == 2                  # 25 // 12
    assert step.sold_value == 24


def test_empty_purse_buys_nothing():
    market = _market(purse=0)
    step = em.merchant_step(market, [_merchant(1, 0, _row(1, stock=10, target=0))])
    assert step.purse_budget == 0 and step.sold_value == 0 and step.legs == []


# --------------------------------------------------------------------------------------------- tax

def test_trade_tax_goes_to_the_region_treasury():
    market = _market(tax_rate=0.15)
    step = em.merchant_step(market, [_merchant(5, 0, _row(1, stock=10, target=0))])   # sells 2 x 10
    m = step.merchants[0]
    assert m.sold_value == 20 and m.tax == 3
    assert m.cash_after == 17
    legs = [(l.src, l.dst, l.amount, l.leg_type) for l in step.legs]
    assert legs == [
        (core.AccountRef.purse(7), core.AccountRef.character(5), 20, core.LEG_MAIN),
        (core.AccountRef.character(5), core.AccountRef.region(7), 3, core.LEG_TRADE_TAX),
    ]
    assert step.tax == 3


# --------------------------------------------------------------------------------------------- restock

def test_take_budget_is_shared_by_all_merchants():
    # food stock 100 -> take 25 units; base_ask 10 = 5 units/item -> 5 items for the whole region
    market = _market(purse=0, goods={"food": (100, 100, 1.0)})
    merchants = [_merchant(1, 10_000, _row(1, stock=0, target=10)), _merchant(2, 10_000, _row(2, stock=0, target=10))]
    step = em.merchant_step(market, merchants)
    assert _row_res(step, 1).restocked == 5
    assert _row_res(step, 2).restocked == 0
    assert step.stock_after["food"] == pytest.approx(75)
    assert step.stock_delta["food"] == pytest.approx(-25)
    m1 = step.merchants[0]
    assert m1.restock_value == 5 * core.wholesale_price(10, 1, 0.5) == 25
    _check_invariants(market, merchants, step)


@pytest.mark.parametrize("stock,norm,want,expected", [
    (30, 100, 10, 3),      # fill 0.3 -> 3
    (30, 100, 5, 2),       # 1.5 -> ceil 2
    (30, 100, 1, 1),       # 0.3 -> ceil 1 (a deficit of 1 is refilled)
    (100, 100, 4, 4),      # full
    (500, 100, 4, 4),      # fill capped at 1
    (10, 0, 2, 2),         # norm 0 -> fill 1
])
def test_fill_ratio_and_ceil_restock(stock, norm, want, expected):
    # food item base_ask 2 -> 1 unit per item; take budget 0.25 x stock is large enough here
    market = _market(purse=0, goods={"food": (stock, norm, 1.0)})
    step = em.merchant_step(market, [_merchant(1, 10_000, _row(1, base_ask=2, stock=0, target=want))])
    assert _row_res(step, 1).restocked == expected


def test_restock_capped_by_cash():
    market = _market(purse=0, goods={"food": (1000, 1000, 1.0)})
    # wholesale floor(10 x 1 x 0.5) = 5; cash 12 -> 2 items
    step = em.merchant_step(market, [_merchant(1, 12, _row(1, stock=0, target=10))])
    m = step.merchants[0]
    assert m.restock_items == 2 and m.restock_value == 10 and m.cash_after == 2


def test_restock_capped_by_region_stock_and_never_below_zero():
    # take_share 1 so only the region stock limits: 7 units, 5 units per item -> 1 item
    params = dataclasses.replace(DEFAULT_PARAMS, merchant_take_share=1.0)
    market = _market(purse=0, goods={"food": (7, 7, 1.0)})
    step = em.merchant_step(market, [_merchant(1, 10_000, _row(1, stock=0, target=10))], params)
    assert _row_res(step, 1).restocked == 1
    assert step.stock_after["food"] == pytest.approx(2)


def test_restock_nothing_when_region_has_no_stock():
    market = _market(purse=0, goods={"food": (0, 100, 1.0)})
    step = em.merchant_step(market, [_merchant(1, 200, _row(1, stock=0, target=10))])     # 200 < cap 300
    assert _row_res(step, 1).restocked == 0 and step.legs == []


def test_restock_uses_regional_wholesale_price():
    market = _market(purse=0, goods={"food": (1000, 1000, 2.0)})
    step = em.merchant_step(market, [_merchant(1, 10_000, _row(1, stock=0, target=3))])
    row = _row_res(step, 1)
    assert row.wholesale == core.wholesale_price(10, 2, 0.5) == 10
    assert step.merchants[0].restock_value == 3 * 10


def test_player_origin_row_sells_but_does_not_restock():
    market = _market()
    step = em.merchant_step(market, [_merchant(1, 10_000, _row(1, stock=10, target=0, origin=PLAYER))])
    row = _row_res(step, 1)
    assert row.sold == 2 and row.restocked == 0 and row.stock_after == 8


def test_small_target_rows_keep_trading_over_many_steps():
    """B5 fix: target 5, stock 4 — with floor the row froze; now every tick sells and refills."""
    cash, stock = 10_000, 4
    for _ in range(8):
        market = _market(purse=100_000)
        step = em.merchant_step(market, [_merchant(1, cash, _row(1, stock=stock, target=5))])
        row = _row_res(step, 1)
        assert row.sold >= 1 and row.restocked >= 1
        cash, stock = step.merchants[0].cash_after, row.stock_after
        assert stock == 5


# --------------------------------------------------------------------------------------------- cash target / upkeep

def test_cash_target_counts_only_restockable_admin_rows():
    rows = [
        _row(1, base_ask=10, target=10),                              # 10 x 5 = 50
        _row(2, base_ask=7, target=4),                                # 4 x floor(3.5)=3 -> 12
        _row(3, base_ask=100, target=10, origin=PLAYER),              # player-origin
        _row(4, base_ask=100, target=10, off_market=True),            # off-market
        _row(5, group=None, base_ask=100, target=10),                 # no group
        _row(6, base_ask=1, target=-3),                               # negative target -> 0
    ]
    assert em.cash_target(rows) == 2 * (50 + 12) == 124
    assert em.cash_target([]) == 0


@pytest.mark.parametrize("cash,target,expected", [
    (700, 100, 100),          # cap 300, excess 400 x 0.25
    (300, 100, 0),            # exactly the cap
    (301, 100, 0),            # floor(0.25)
    (304, 100, 1),
    (10 ** 12, 0, 0),         # target 0: the merchant keeps his cash
    (0, 100, 0),
])
def test_upkeep_amount(cash, target, expected):
    assert em.upkeep_amount(cash, target) == expected


def test_upkeep_in_the_step_releases_excess_to_the_purse():
    # no sales (purse 0), stock at target -> only upkeep. target = 2 x 10 x 5 = 100, cap 300
    market = _market(purse=0)
    step = em.merchant_step(market, [_merchant(3, 700, _row(1, stock=10, target=10))])
    m = step.merchants[0]
    assert m.cash_target == 100
    assert m.upkeep == 100 and m.cash_after == 600
    assert step.purse_after == 100
    assert [(l.src, l.dst, l.amount) for l in step.legs] == [
        (core.AccountRef.character(3), core.AccountRef.purse(7), 100)]


def test_no_upkeep_without_restockable_rows():
    market = _market(purse=0)
    step = em.merchant_step(market, [_merchant(3, 10 ** 9, _row(1, stock=10, target=0, origin=PLAYER))])
    m = step.merchants[0]
    assert m.cash_target == 0 and m.upkeep == 0 and m.cash_after == 10 ** 9


def test_huge_cash_converges_near_the_cap():
    cash = 1_000_000
    for _ in range(200):
        step = em.merchant_step(_market(purse=0), [_merchant(1, cash, _row(1, stock=10, target=10))])
        cash = step.merchants[0].cash_after
    assert 300 <= cash <= 304                     # cap 300 + floor-rounding residue


# --------------------------------------------------------------------------------------------- skipped rows

def test_rows_that_cannot_trade_are_skipped():
    market = _market(goods={"food": (1000, 1000, 1.0)}, group_base={**GROUP_BASE, "tools": 0})
    rows = [
        _row(1, off_market=True, stock=10),
        _row(2, group=None, stock=10),
        _row(3, group="jewelry", stock=10),       # group the region has no row for
        _row(4, group="tools", stock=10),         # not in market.goods either
        _row(5, base_ask=0, stock=10),            # 0 units per item
    ]
    step = em.merchant_step(market, [_merchant(1, 0, *rows)])     # no cash: no upkeep leg either
    for row_id in range(1, 6):
        r = _row_res(step, row_id)
        assert (r.sold, r.restocked, r.stock_after, r.ask, r.wholesale) == (0, 0, 10, 0, 0)
    assert step.legs == [] and step.stock_delta == {}
    assert step.new_row_stock == {i: 10 for i in range(1, 6)}


def test_group_base_zero_skips_the_row():
    market = _market(group_base={"food": 0})
    step = em.merchant_step(market, [_merchant(1, 100, _row(1, stock=10, target=20))])
    assert _row_res(step, 1).sold == 0 and _row_res(step, 1).restocked == 0


def test_null_and_negative_stock_become_zero():
    market = _market(purse=0)
    step = em.merchant_step(market, [_merchant(1, 10_000, _row(1, stock=None, target=2), _row(2, stock=-5, target=0))])
    assert _row_res(step, 1).stock_before == 0 and _row_res(step, 1).stock_after == 2
    assert _row_res(step, 2).stock_before == 0 and _row_res(step, 2).stock_after == 0
    assert step.new_row_stock == {1: 2, 2: 0}


def test_negative_cash_and_purse_are_clamped():
    market = _market(purse=-500)
    step = em.merchant_step(market, [_merchant(1, -40, _row(1, stock=10, target=20))])
    assert step.purse_before == 0 and step.purse_budget == 0
    m = step.merchants[0]
    assert m.cash_before == 0 and m.cash_after == 0 and step.legs == []


def test_no_merchants():
    step = em.merchant_step(_market(), [])
    assert step.merchants == [] and step.legs == [] and step.purse_after == step.purse_before == 10_000


# --------------------------------------------------------------------------------------------- order / purity

def test_deterministic_order_independent_of_input_order():
    rows_a = [_row(4, stock=10, target=12), _row(2, base_ask=2, stock=3, target=8)]
    rows_b = [_row(9, stock=6, target=10), _row(7, base_ask=2, stock=1, target=4)]
    market = _market(purse=2_000, goods={"food": (200, 300, 1.3)})
    a = em.merchant_step(market, [_merchant(11, 100, *rows_a), _merchant(3, 50, *rows_b)])
    b = em.merchant_step(market, [_merchant(3, 50, *reversed(rows_b)), _merchant(11, 100, *reversed(rows_a))])
    assert [m.npc_id for m in a.merchants] == [3, 11]
    assert [r.row_id for r in a.merchants[0].rows] == [7, 9]
    assert a.legs == b.legs
    assert a.new_row_stock == b.new_row_stock
    assert a.stock_after == b.stock_after
    assert a.metadata() == b.metadata()
    assert a.metadata()["merchants"]["3"] == a.merchants[0].summary()


def test_inputs_are_not_mutated():
    goods = {"food": em.MarketGood(200, 300, 1.3), "ore_metal": em.MarketGood(50, 40, 0.8)}
    group_base = dict(GROUP_BASE)
    market = em.RegionMarket(region_id=1, tax_rate=0.1, purse=5_000, goods=goods, group_base=group_base)
    rows = [_row(1, stock=10, target=12), _row(2, group="ore_metal", base_ask=30, stock=1, target=5)]
    merchants = [_merchant(1, 300, *rows)]
    snapshot = copy.deepcopy((market, merchants, goods, group_base))
    em.merchant_step(market, merchants)
    assert (market, merchants, goods, group_base) == snapshot


def test_legs_order_and_omitted_zero_legs():
    # sells (purse -> npc), tax, restock (npc -> purse), upkeep (npc -> purse)
    market = _market(purse=100_000, tax_rate=0.2)
    step = em.merchant_step(market, [_merchant(1, 5_000, _row(1, stock=5, target=10))])
    m = step.merchants[0]
    assert m.sold_value > 0 and m.tax > 0 and m.restock_value > 0 and m.upkeep > 0
    npc, purse = core.AccountRef.character(1), core.AccountRef.purse(7)
    assert [(l.src, l.dst, l.amount, l.leg_type) for l in step.legs] == [
        (purse, npc, m.sold_value, core.LEG_MAIN),
        (npc, core.AccountRef.region(7), m.tax, core.LEG_TRADE_TAX),
        (npc, purse, m.restock_value, core.LEG_MAIN),
        (npc, purse, m.upkeep, core.LEG_MAIN),
    ]


def test_market_from_sim_accepts_good_states():
    class _G:
        def __init__(self, stock, norm, mult):
            self.stock, self.norm_stock, self.price_mult = stock, norm, mult

    market = em.market_from_sim(4, "0.12", "900", {"food": _G(10, 20, 1.5)}, {"food": 2})
    assert market.region_id == 4 and market.purse == 900 and market.tax_rate == pytest.approx(0.12)
    assert market.goods["food"] == em.MarketGood(10.0, 20.0, 1.5)


# --------------------------------------------------------------------------------------------- property

@pytest.mark.parametrize("seed", range(40))
def test_random_worlds_keep_every_guarantee(seed):
    rnd = random.Random(seed)
    groups = ["food", "ore_metal", "tools", "weapons"]
    goods = {g: (rnd.choice([0, 0.5, 3, 40, 400, 5000]), rnd.choice([0, 10, 300, 4000]),
                 rnd.choice([0.5, 0.85, 1, 1.37, 2.5, 3])) for g in groups if rnd.random() < 0.85}
    market = _market(purse=rnd.choice([0, 1, 37, 1_000, 250_000]), tax_rate=rnd.choice([0, 0.06, 0.15, 1]),
                     goods=goods)
    merchants, row_id = [], 1
    for npc_id in rnd.sample(range(1, 50), rnd.randint(1, 4)):
        rows = []
        for _ in range(rnd.randint(0, 5)):
            rows.append(_row(row_id, group=rnd.choice(groups + [None, "jewelry"]),
                             base_ask=rnd.choice([0, 1, 3, 10, 120, 999]),
                             stock=rnd.choice([None, -2, 0, 1, 3, 5, 40]),
                             target=rnd.choice([0, 1, 3, 5, 10, 50]),
                             origin=rnd.choice([ADMIN, ADMIN, PLAYER]), off_market=rnd.random() < 0.15))
            row_id += 1
        merchants.append(_merchant(npc_id, rnd.choice([-10, 0, 3, 500, 10 ** 7]), *rows))
    snapshot = copy.deepcopy((market, merchants))
    step = em.merchant_step(market, merchants)
    assert (market, merchants) == snapshot
    _check_invariants(market, merchants, step)
    # region stock moved exactly by the items: + sold x units, - restocked x units
    moved = defaultdict(float)
    rows_by_id = {r.row_id: r for m in merchants for r in m.rows}
    for m in step.merchants:
        for r in m.rows:
            src = rows_by_id[r.row_id]
            if r.sold or r.restocked:
                units = core.units_per_item(src.base_ask, GROUP_BASE[src.group])
                moved[src.group] += (r.sold - r.restocked) * units
    for g, delta in step.stock_delta.items():
        assert delta == pytest.approx(moved[g])
    # the take budget: restocked units of a group <= take_share x its stock at step start
    for g in step.stock_delta:
        taken = sum(r.restocked * core.units_per_item(rows_by_id[r.row_id].base_ask, GROUP_BASE[g])
                    for m in step.merchants for r in m.rows if rows_by_id[r.row_id].group == g)
        assert taken <= DEFAULT_PARAMS.merchant_take_share * max(0.0, float(market.goods[g].stock)) + 1e-6
