"""FEAT-215 QA (#8): pure sea-caravan logic — no DB, no clock, no RNG.

* ``sea_core.reached_from`` / ``serves`` (§3.3): pendulum, loop, revisit cut-off, start at the first leg leaving ``a``;
* ``econ_caravan.plan_caravans`` with ``reach`` / ``sea_slots`` / freight, ``clamp_dispatch`` with freight;
* money helpers with freight (§3.7): ``freight_amount``, ``remaining_payout``, ``refund_split``, ``raid_marks_cap``;
* monster loss share (§3.8): ``econ_caravan.cargo_loss_units``;
* migration ``054_sea_caravans`` metadata and single head.
"""

import importlib.util
import os
from dataclasses import dataclass, replace

import pytest

import econ_caravan as cv
import sea_core
from econ_sim import GroupDef, SimParams

P = SimParams()
ORE = GroupDef(code="ore_metal", name="Руда и металл", base_price=10, norm_per_1000=1, norm_days=1)
FOOD = GroupDef(code="food", name="Продовольствие", base_price=2, norm_per_1000=1, norm_days=1, is_food=True)
GROUPS = {g.code: g for g in (ORE, FOOD)}

LAND = cv.Reach(cv.REACH_LAND)
SEA5 = cv.Reach(cv.REACH_SEA, freight_pct=5.0)


# --------------------------------------------------------------------------------------------- sea_core.serves

@dataclass(frozen=True)
class Leg:
    from_port: int
    to_port: int
    zones: int


def legs(*hops):
    """``legs((1, 2, 3), (2, 5, 4))`` -> Leg objects (from, to, zones)."""
    return [Leg(*h) for h in hops]


# pendulum 1 -> 2 -> 3 -> 2 -> 1 (zones 2, 3, 3, 2)
PENDULUM = legs((1, 2, 2), (2, 3, 3), (3, 2, 3), (2, 1, 2))
# loop 1 -> 2 -> 3 -> 1, two rounds (plan horizon 2 × stops)
LOOP = legs((1, 2, 1), (2, 3, 2), (3, 1, 4)) * 2


def test_reached_from_pendulum_accumulates_zones_through_intermediate_stops():
    assert sea_core.reached_from(PENDULUM, 1) == {2: 2, 3: 5}
    assert sea_core.serves(PENDULUM, 1, 3) == 5          # cargo stays in the hold at port 2
    assert sea_core.serves(PENDULUM, 3, 1) == 5          # return half: 3 -> 2 -> 1


def test_reached_from_starts_at_the_first_leg_leaving_a_and_stops_on_revisit():
    # from 2 the first departure goes to 3 and the ship comes back to 2 before ever reaching 1
    assert sea_core.reached_from(PENDULUM, 2) == {3: 3}
    assert sea_core.serves(PENDULUM, 2, 1) is None
    # when the plan starts on the return half, the first leg leaving 2 goes to 1
    assert sea_core.serves(PENDULUM[2:], 2, 1) == 2


def test_reached_from_loop_wraps_around_but_never_past_a():
    assert sea_core.reached_from(LOOP, 1) == {2: 1, 3: 3}
    assert sea_core.reached_from(LOOP, 3) == {1: 4, 2: 5}     # 3 -> 1 -> 2, then back at 3: cut
    assert sea_core.serves(LOOP, 2, 1) == 6                   # 2 -> 3 -> 1


def test_reached_from_keeps_the_first_arrival_only():
    plan = legs((1, 2, 1), (2, 3, 1), (3, 2, 5), (2, 4, 1))
    assert sea_core.reached_from(plan, 1) == {2: 1, 3: 2, 4: 8}


def test_serves_edge_cases():
    assert sea_core.reached_from(PENDULUM, 99) == {}
    assert sea_core.reached_from([], 1) == {}
    assert sea_core.serves(PENDULUM, 1, 1) is None
    assert sea_core.serves(PENDULUM, None, 2) is None and sea_core.serves(PENDULUM, 1, None) is None
    assert sea_core.serves(PENDULUM, 1, 77) is None
    assert sea_core.serves(legs(("1", "2", "3")), 1, "2") == 3          # ids are coerced


# --------------------------------------------------------------------------------------------- plan_caravans

def good(stock, norm, mult=1.0):
    return cv.GoodMarket(stock=float(stock), norm_stock=float(norm), price_mult=float(mult))


def market(rid, country=1, *, purse=100_000, treasury=0, **goods):
    return cv.RegionMarket(region_id=rid, country_id=country, purse=purse, treasury=treasury, goods=goods)


def plan(markets, *, reach=None, sea_slots=None, params=P):
    return cv.plan_caravans({m.region_id: m for m in markets}, GROUPS, {}, {}, params, reach=reach,
                            sea_slots=sea_slots)


def reach_table(table):
    """``{(from, to): Reach}``; missing pair -> None (unreachable)."""
    return lambda a, b: table.get((a, b))


SELLER = market(1, ore_metal=good(900, 100))       # supply floor3(0.25 × 800) = 200 units @ 10
BUYER = market(2, ore_metal=good(0, 100))          # need 100 units


def _money_ok(p):
    assert p.paid_purse + p.paid_treasury == p.value + p.duty + p.freight == p.cost


def test_unreachable_pair_is_never_planned():
    assert plan([SELLER, BUYER], reach=reach_table({})) == []
    # only the reverse direction is reachable — still nothing to sell 1 -> 2
    assert plan([SELLER, BUYER], reach=reach_table({(2, 1): LAND})) == []


def test_land_reach_matches_the_legacy_plan():
    legacy = plan([SELLER, BUYER])
    land = plan([SELLER, BUYER], reach=reach_table({(1, 2): LAND}))
    assert legacy == land and len(land) == 1
    assert land[0].kind == cv.REACH_LAND and land[0].freight == 0 and land[0].freight_pct == 0.0
    _money_ok(land[0])


def test_land_reach_ignores_a_stray_freight_pct():
    p, = plan([SELLER, BUYER], reach=reach_table({(1, 2): cv.Reach(cv.REACH_LAND, freight_pct=30.0)}))
    assert p.freight == 0 and p.freight_pct == 0.0


def test_sea_pair_gets_freight_on_top_of_value_and_duty():
    p, = plan([SELLER, BUYER], reach=reach_table({(1, 2): SEA5}))
    assert p.kind == cv.REACH_SEA and p.is_sea
    assert p.units == 100.0 and p.value == 1000 and p.duty == 0
    assert p.freight_pct == 5.0 and p.freight == cv.freight_amount(p.value, 5.0) == 50
    _money_ok(p)


def test_sea_freight_is_affordable_within_a_tight_budget():
    poor = market(2, purse=4000, ore_metal=good(0, 1000))        # purse_left 1000, need 1000 units
    p, = plan([SELLER, poor], reach=reach_table({(1, 2): SEA5}))
    assert p.cost <= 1000
    assert p.units == cv.affordable_units(1000, 10.0, 5.0)
    _money_ok(p)


def test_land_seller_is_preferred_over_sea_seller_at_equal_terms():
    sea_seller = market(1, ore_metal=good(900, 100))
    land_seller = market(3, ore_metal=good(900, 100))
    plans = plan([sea_seller, BUYER, land_seller], reach=reach_table({(1, 2): SEA5, (3, 2): LAND}))
    assert [(p.from_region_id, p.kind) for p in plans] == [(3, cv.REACH_LAND)]


def test_sea_slots_limit_sea_plans_only():
    buyers = [market(rid, ore_metal=good(0, 100)) for rid in (2, 3, 4)]
    table = {(1, 2): SEA5, (1, 3): SEA5, (1, 4): LAND}
    seller = market(1, ore_metal=good(5000, 100))
    assert {(p.to_region_id, p.kind) for p in plan([seller, *buyers], reach=reach_table(table), sea_slots=0)} == \
        {(4, cv.REACH_LAND)}
    one = plan([seller, *buyers], reach=reach_table(table), sea_slots=1)
    assert sum(p.is_sea for p in one) == 1 and sum(not p.is_sea for p in one) == 1
    unlimited = plan([seller, *buyers], reach=reach_table(table), sea_slots=None)
    assert sum(p.is_sea for p in unlimited) == 2
    assert plan([seller, *buyers], reach=reach_table(table), sea_slots=-3) == \
        plan([seller, *buyers], reach=reach_table(table), sea_slots=0)
    for p in unlimited:
        _money_ok(p)


def test_sea_plan_is_deterministic():
    table = reach_table({(1, 2): SEA5, (3, 2): SEA5})
    markets = [SELLER, BUYER, market(3, ore_metal=good(700, 100, 1.1))]
    assert plan(markets, reach=table, sea_slots=5) == plan(list(reversed(markets)), reach=table, sea_slots=5)


# --------------------------------------------------------------------------------------------- clamp_dispatch

def _sea_plan():
    p, = plan([SELLER, BUYER], reach=reach_table({(1, 2): SEA5}))
    return p


def test_clamp_keeps_a_fully_covered_sea_plan():
    p = _sea_plan()
    assert cv.clamp_dispatch(p, 900, 100, 10**6, 0) == p


def test_clamp_recomputes_freight_when_units_shrink():
    p = _sea_plan()
    c = cv.clamp_dispatch(p, 150, 100, 10**6, 0)                 # room = 50 units
    assert c.units == 50.0 and c.value == 500 and c.freight == 25 and c.freight_pct == 5.0
    _money_ok(c)


def test_clamp_freight_fits_a_shrunk_purse():
    p = _sea_plan()
    c = cv.clamp_dispatch(p, 900, 100, 300, 0)
    assert c.cost <= 300 and c.paid_purse <= 300 and c.freight == cv.freight_amount(c.value, 5.0)
    _money_ok(c)


def test_clamp_land_plan_never_gets_freight():
    p, = plan([SELLER, BUYER])
    c = cv.clamp_dispatch(p, 150, 100, 10**6, 0)
    assert c.freight == 0
    _money_ok(c)


# --------------------------------------------------------------------------------------------- money helpers

@pytest.mark.parametrize("value, pct, expected", [
    (1000, 5.0, 50), (999, 5.0, 49), (19, 5.0, 0), (1000, 0, 0), (1000, -5, 0), (-10, 5, 0), (None, 5, 0),
    (333, 12.5, 41), (100, 50.0, 50),
])
def test_freight_amount(value, pct, expected):
    assert cv.freight_amount(value, pct) == expected


def test_remaining_payout_excludes_freight():
    # value 1000, duty 100, freight 50 -> paid 1150; nothing raided: seller 1000, duty 100
    assert cv.remaining_payout(1000, 100, 1150, 0, freight=50) == (1000, 100)
    # raided 220: rest = 1150 - 50 - 220 = 880; duty' = 100 × 880 // 1100 = 80
    assert cv.remaining_payout(1000, 100, 1150, 220, freight=50) == (800, 80)
    # freight default 0 keeps the legacy behaviour
    assert cv.remaining_payout(1000, 100, 1100, 220) == (800, 80)
    # never negative
    assert cv.remaining_payout(1000, 100, 1150, 5000, freight=50) == (0, 0)


def test_refund_split_with_freight():
    # uncharged freight is refunded with the rest
    assert cv.refund_split(1050, 0, 0, freight_paid=0) == (1050, 0)
    # charged freight is gone, pro rata like the raid
    assert cv.refund_split(600, 450, 0, freight_paid=50) == (600 - 50 * 600 // 1050, 450 - 50 + 50 * 600 // 1050)
    back = cv.refund_split(600, 450, 100, freight_paid=50)
    assert sum(back) == 1050 - 150 and all(x >= 0 for x in back)
    # raid + freight above the total -> nothing back, never negative
    assert cv.refund_split(100, 0, 90, freight_paid=50) == (0, 0)
    assert cv.refund_split(600, 450, 100) == cv.refund_split(600, 450, 100, freight_paid=0)


@pytest.mark.parametrize("paid, freight, raid, expected", [
    (1150, 50, 0, 1100), (1150, 50, 1000, 100), (1150, 50, 1200, 0), (1150, 0, 150, 1000), (1150, None, 0, 1150),
    (0, 50, 0, 0),
])
def test_raid_marks_cap(paid, freight, raid, expected):
    assert cv.raid_marks_cap(paid, freight, raid) == expected


def test_escrow_drains_to_zero_after_delivery_with_freight():
    """paid_total = seller + duty + freight + raid (§3.7 sub-invariant)."""
    value, duty, freight, raid = 1000, 100, 50, 220
    paid = value + duty + freight
    seller, duty_part = cv.remaining_payout(value, duty, paid, raid, freight=freight)
    assert seller + duty_part + freight + raid == paid
    assert raid <= cv.raid_marks_cap(paid, freight, 0)


# --------------------------------------------------------------------------------------------- loss share (§3.8)

_LOSS_HELPER_NAMES = ("cargo_loss_units", "sea_loss_units", "loss_units")


def _loss_helper():
    for mod in (sea_core, cv):
        for name in _LOSS_HELPER_NAMES:
            fn = getattr(mod, name, None)
            if callable(fn):
                return fn
    pytest.skip("pending FEAT-215 task 5: no pure loss-share helper "
                f"({' / '.join(_LOSS_HELPER_NAMES)} in sea_core / econ_caravan) yet; expected signature "
                "(units_left, loss_pct, lost_groups, decided_groups) -> floor3(left × pct/100 × lost/decided)")


@pytest.mark.parametrize("left, pct, lost, decided, expected", [
    (100, 25.0, 1, 1, 25.0),       # every group lost
    (100, 25.0, 1, 2, 12.5),       # 1 won, 1 lost
    (100, 25.0, 0, 2, 0.0),        # all won
    (100, 25.0, 0, 0, 0.0),        # nothing decided (aborted / expired only) -> no loss
    (10, 33.3, 1, 3, 1.11),        # floor3
    (0, 25.0, 1, 1, 0.0),
    (100, 0.0, 2, 2, 0.0),
])
def test_loss_share(left, pct, lost, decided, expected):
    fn = _loss_helper()
    assert fn(left, pct, lost, decided) == pytest.approx(expected)


# --------------------------------------------------------------------------------------------- migration 054

_VERSIONS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic", "versions")


def _load(fn):
    spec = importlib.util.spec_from_file_location(f"mig215_{fn[:-3]}", os.path.join(_VERSIONS, fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_054_metadata():
    mod = _load("054_sea_caravans.py")
    assert mod.revision == "054_sea_caravans" and len(mod.revision) <= 32
    assert mod.down_revision == "053_sea_storms_raids"
    cols = {(t, c) for t, c, _d in mod._COLUMNS}
    assert {("econ_caravans", c) for c in ("sea_stage", "sea_split_index", "sea_board_port_id",
                                           "sea_alight_port_id", "sea_ship_id", "freight", "freight_paid",
                                           "sunk_units")} <= cols
    assert ("sea_ships", "cargo_capacity") in cols
    assert ("sea_raids", "caravan_ids") in cols and ("sea_raids", "cargo_settled_at") in cols
    assert callable(mod.upgrade) and callable(mod.downgrade)


def test_migration_054_is_followed_by_055_single_head():
    revs, downs = set(), set()
    for fn in os.listdir(_VERSIONS):
        if fn.endswith(".py") and not fn.startswith("__"):
            mod = _load(fn)
            revs.add(mod.revision)
            d = getattr(mod, "down_revision", None)
            downs.update(r for r in (d if isinstance(d, (tuple, list)) else (d,)) if r)
    # FEAT-216: 055_customs_smuggling follows 054 and is now the single head
    assert "054_sea_caravans" in downs
    assert revs - downs == {"055_customs_smuggling"}
