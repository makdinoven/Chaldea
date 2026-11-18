"""FEAT-216 task 3: customs planning & routing — pure, no DB (small in-memory graphs).

Focused developer checks; the full pure suite is QA task 14 (``test_customs_core.py``).
* ``econ_caravan.plan_caravans`` with ``bans`` / ``contraband_reach`` (legal first, share, markup, slots, None = legacy);
* ``economy_caravan_crud.RoutePlanner``: legal route via a post (A5), unreachable post, contraband avoiding posts and
  the buyer-gate rule (A8), sea landing-port rules (A7 / A8), customs off = legacy routes.
"""

from dataclasses import dataclass, replace

import econ_caravan as cv
import economy_caravan_crud as crud
from econ_sim import GroupDef, SimParams

P = SimParams()
ORE = GroupDef(code="ore_metal", name="Руда и металл", base_price=10, norm_per_1000=1, norm_days=1)
GROUPS = {ORE.code: ORE}
LAND = cv.Reach(cv.REACH_LAND)
SEA5 = cv.Reach(cv.REACH_SEA, freight_pct=5.0)


def good(stock, norm):
    return cv.GoodMarket(stock=float(stock), norm_stock=float(norm), price_mult=1.0)


def market(rid, country, **goods):
    return cv.RegionMarket(region_id=rid, country_id=country, purse=100_000, treasury=0, goods=goods)


SELLER = market(1, 1, ore_metal=good(200, 100))       # supply 50 (surplus share 0.5 by default)
BUYER = market(2, 2, ore_metal=good(0, 100))          # need 100
MARKETS = {1: SELLER, 2: BUYER}
OPEN_PAIR = {cv.pair_key(1, 2): cv.PairRule(1, 2, True, 10.0)}


def plan(pairs, **kw):
    return cv.plan_caravans(MARKETS, GROUPS, {}, pairs, kw.pop("params", P), **kw)


# --------------------------------------------------------------------------------------------- plan_caravans

def test_no_bans_no_contraband_reach_is_the_legacy_plan():
    assert plan(OPEN_PAIR, reach=lambda a, b: LAND) == plan(OPEN_PAIR, reach=lambda a, b: LAND, bans=None,
                                                            contraband_reach=None)
    assert plan({}, reach=lambda a, b: LAND, bans={}, contraband_reach=None) == []


def test_banned_group_becomes_contraband_with_markup_share_and_no_duty():
    [legal] = plan(OPEN_PAIR, reach=lambda a, b: LAND)
    [smuggled] = plan(OPEN_PAIR, reach=lambda a, b: LAND, bans={2: frozenset({"ore_metal"})},
                      contraband_reach=lambda a, b: LAND)
    assert not legal.contraband and smuggled.contraband
    assert smuggled.duty == 0 and smuggled.duty_pct == 0.0
    assert smuggled.markup_pct == P.customs_contraband_markup_pct
    assert smuggled.unit_price == cv.contraband_price(legal.unit_price, P.customs_contraband_markup_pct)
    assert smuggled.units == cv.floor3(min(100, legal.units) * P.customs_contraband_share)
    assert smuggled.travel_runs == max(1, int(P.caravan_travel_foreign))


def test_closed_pair_is_smuggled_but_customs_off_or_zero_share_is_legacy():
    [smuggled] = plan({}, reach=lambda a, b: LAND, bans={}, contraband_reach=lambda a, b: LAND)
    assert smuggled.contraband
    for params in (replace(P, customs_enabled=0), replace(P, customs_contraband_share=0.0)):
        assert plan({}, reach=lambda a, b: LAND, bans={}, contraband_reach=lambda a, b: LAND, params=params) == []


def test_unreachable_contraband_and_unreachable_legal_are_both_dropped():
    assert plan({}, reach=lambda a, b: LAND, bans={}, contraband_reach=lambda a, b: None) == []
    # an open pair without a legal reach is not smuggled
    assert plan(OPEN_PAIR, reach=lambda a, b: None, bans={}, contraband_reach=lambda a, b: LAND) == []


def test_domestic_trade_ignores_bans():
    markets = {1: SELLER, 3: market(3, 1, ore_metal=good(0, 100))}
    [p] = cv.plan_caravans(markets, GROUPS, {}, {}, P, reach=lambda a, b: LAND, bans={1: frozenset({"ore_metal"})},
                           contraband_reach=lambda a, b: LAND)
    assert not p.contraband and p.to_region_id == 3


def test_legal_sellers_sort_before_contraband_and_contraband_uses_physical_slots():
    markets = {1: SELLER, 2: BUYER, 4: market(4, 3, ore_metal=good(200, 100))}   # 4: closed pair with 2
    plans = cv.plan_caravans(markets, GROUPS, {}, OPEN_PAIR, P, reach=lambda a, b: LAND, bans={},
                             contraband_reach=lambda a, b: LAND)
    assert [(p.from_region_id, p.contraband) for p in plans] == [(1, False), (4, True)]
    plans = cv.plan_caravans(markets, GROUPS, {}, OPEN_PAIR, P, reach=lambda a, b: LAND, sea_slots=0, bans={},
                             contraband_reach=lambda a, b: LAND)
    assert [(p.from_region_id, p.contraband) for p in plans] == [(1, False)]


def test_sea_contraband_carries_freight():
    [p] = plan({}, reach=lambda a, b: LAND, bans={}, contraband_reach=lambda a, b: SEA5)
    assert p.contraband and p.is_sea and p.freight == cv.freight_amount(p.value, 5.0)
    assert p.paid_purse + p.paid_treasury == p.value + p.freight


# --------------------------------------------------------------------------------------------- RoutePlanner

def graph(*edges, blocked=()):
    import caravan_route
    return crud.RoadGraph(adj=caravan_route.build_adjacency(edges), blocked=set(blocked))


def gates(**by_region):
    """``r1=(gate, country)`` -> region_gates dict."""
    return {int(k[1:]): {"gate": g, "country_id": c, "override": g, "station": None, "source": "override"}
            for k, (g, c) in by_region.items()}


@dataclass(frozen=True)
class SeaPair:
    zones: int


#   10 - 11 - 12 - 13 - 14      (r1 gate 10, country 1; r2 gate 14, country 2)
#         \             /
#          20 ------- 21        posts: 21 (country 2), 12 (country 1)
LINE = graph((10, 11), (11, 12), (12, 13), (13, 14), (11, 20), (20, 21), (21, 14))
G = gates(r1=(10, 1), r2=(14, 2))


def planner(g=LINE, gs=G, posts=None, ports=(), on=True, **kw):
    return crud.RoutePlanner(g, gs, 0, 10, kw.pop("sea_pairs", None), max_active=5, posts_by_country=posts,
                             customs_ports=ports, customs_enabled=on, **kw)


def test_legal_route_goes_via_the_destination_post():
    rp = planner(posts={2: [21], 1: [12]})
    route, index, reason = rp.legal_route(1, 2)
    assert route == [10, 11, 20, 21, 14] and index == 3 and reason is None
    # the reverse direction goes via the post of country 1 (on the shortest road anyway)
    route, index, _ = rp.legal_route(2, 1)
    assert route == [14, 13, 12, 11, 10] and index == 2


def test_customs_off_or_no_posts_is_the_plain_route():
    for rp in (planner(posts={2: [21]}, on=False), planner(posts={})):
        assert rp.legal_route(1, 2) == (rp.route(1, 2)[0], None, None)
        assert rp.reach(1, 2) == LAND


def test_domestic_never_visits_a_post():
    rp = planner(gs=gates(r1=(10, 2), r2=(14, 2)), posts={2: [21]})
    assert rp.legal_route(1, 2)[1] is None


def test_unreachable_post_means_no_legal_land_route():
    rp = planner(g=graph((10, 11), (11, 14), (30, 31)), posts={2: [31]})
    assert rp.legal_route(1, 2)[0] is None and rp.reach(1, 2) is None
    assert planner(g=graph((10, 11), (11, 14), (30, 31)), posts={2: [31]}, abstract_fallback=True).reach(1, 2) == LAND


def test_post_at_the_buyer_gate_is_the_final_node():
    rp = planner(posts={2: [14]})
    route, index, _ = rp.legal_route(1, 2)
    assert route == [10, 11, 12, 13, 14] and index == 4


def test_contraband_avoids_every_post_and_never_ends_at_one():
    rp = planner(posts={2: [21], 1: [12]})
    assert rp.contraband_route(1, 2) == (None, "no_path")                 # both roads pass a post
    rp = planner(posts={2: [21]})
    assert rp.contraband_route(1, 2)[0] == [10, 11, 12, 13, 14]
    assert planner(posts={2: [14]}).contraband_route(1, 2)[0] is None      # buyer gate is a post
    assert planner(posts={1: [10]}).contraband_route(1, 2)[0] is not None  # seller gate may be one
    assert planner(posts={2: [21]}, sea_enabled=False).contraband_reach(1, 2) is None


#  r1 gate 10 - 40 (port) ~~sea~~ 50 (port) - 51 - 52 (r2 gate) ; 60 (port) - 52 ; ships 40->50, 40->60
SEA = graph((10, 40), (50, 51), (51, 52), (60, 52))
SEA_G = gates(r1=(10, 1), r2=(52, 2))
PAIRS = {(40, 50): SeaPair(2), (40, 60): SeaPair(3)}


def test_sea_land2_passes_the_landing_customs_port_or_a_post():
    rp = planner(g=SEA, gs=SEA_G, posts={2: [50]}, ports=[50], sea_pairs=PAIRS)
    sea = rp.sea_route(1, 2)
    assert (sea.alight_port, sea.customs_index) == (50, sea.split_index + 1)
    rp = planner(g=SEA, gs=SEA_G, posts={2: [51]}, sea_pairs=PAIRS)
    sea = rp.sea_route(1, 2)
    assert sea.alight_port == 50 and sea.route[sea.customs_index] == 51
    assert planner(g=SEA, gs=SEA_G, posts={}, sea_pairs=PAIRS).sea_route(1, 2).customs_index is None


def test_contraband_sea_never_lands_at_a_customs_port():
    rp = planner(g=SEA, gs=SEA_G, posts={2: [50]}, ports=[50], sea_pairs=PAIRS)
    sea = rp.contraband_sea_route(1, 2)
    assert sea.alight_port == 60 and sea.customs_index is None
    assert rp.contraband_reach(1, 2) == cv.Reach(cv.REACH_SEA, 0.0)
