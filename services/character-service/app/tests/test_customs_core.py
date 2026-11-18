"""FEAT-216 task 14: customs & smuggling — the pure layer (no DB, no I/O, small in-memory graphs).

Complements ``test_customs_planning.py`` (task 3 developer checks); the cases there are not repeated here.
* ``econ_caravan``: ``plan_caravans`` with bans / closed pairs / share / markup / legal-first ordering / the
  customs switch, ``contraband_price``, the money helpers with ``duty_paid`` (``settled_duty``, ``remaining_payout``,
  ``refund_split``, ``raid_marks_cap``);
* ``customs_core``: detection / patrol chance clamps, caravan stealth, legality, officer money, ban-code validation;
* ``economy_caravan_crud.RoutePlanner``: legal routing via a post (A5), contraband routing (A8), sea landing-port rules
  (A7), ``contraband_reach``.
"""

from dataclasses import replace
from decimal import Decimal

import pytest

import caravan_route
import customs_core as cc
import econ_caravan as cv
import law_core
from econ_sim import GroupDef, SimParams
from tests.test_customs_planning import SeaPair, gates, graph, planner

P = SimParams()
ORE = GroupDef(code="ore_metal", name="Руда и металл", base_price=10, norm_per_1000=1, norm_days=1)
CLOTH = GroupDef(code="cloth", name="Ткани", base_price=8, norm_per_1000=1, norm_days=1)
GROUPS = {ORE.code: ORE}
LAND = cv.Reach(cv.REACH_LAND)
SEA5 = cv.Reach(cv.REACH_SEA, freight_pct=5.0)
BAN_ORE_IN_2 = {2: frozenset({"ore_metal"})}


def good(stock, norm, mult=1.0):
    return cv.GoodMarket(stock=float(stock), norm_stock=float(norm), price_mult=float(mult))


def market(rid, country, **goods):
    return cv.RegionMarket(region_id=rid, country_id=country, purse=100_000, treasury=0, goods=goods)


SELLER = market(1, 1, ore_metal=good(200, 100))
BUYER = market(2, 2, ore_metal=good(0, 100))
CLOSED_SELLER = market(4, 3, ore_metal=good(200, 100))     # country 3 has no pair with country 2
OPEN_PAIR = {cv.pair_key(1, 2): cv.PairRule(1, 2, True, 10.0)}


def land(_a, _b):
    return LAND


def plan(markets, pairs, params=P, groups=GROUPS, **kw):
    return cv.plan_caravans(markets, groups, {}, pairs, params, **kw)


# ============================================================================================ plan_caravans

def test_customs_off_with_contraband_reach_is_the_legacy_plan():
    markets = {1: SELLER, 2: BUYER, 4: CLOSED_SELLER}
    off = replace(P, customs_enabled=0)
    legacy = plan(markets, OPEN_PAIR, off, reach=land)
    assert legacy and all(not p.contraband and p.markup_pct == 0.0 for p in legacy)
    assert plan(markets, OPEN_PAIR, off, reach=land, bans=None, contraband_reach=land) == legacy
    # customs on but no contraband_reach (and no bans) → legacy as well
    assert plan(markets, OPEN_PAIR, P, reach=land, bans=None, contraband_reach=None) == legacy


def test_bans_without_contraband_reach_drop_the_deal():
    assert plan({1: SELLER, 2: BUYER}, OPEN_PAIR, reach=land, bans=BAN_ORE_IN_2, contraband_reach=None) == []


def test_ban_in_the_seller_country_or_a_third_country_does_not_block_the_import():
    for bans in ({1: frozenset({"ore_metal"})}, {7: frozenset({"ore_metal"})}, {2: frozenset({"cloth"})}):
        [p] = plan({1: SELLER, 2: BUYER}, OPEN_PAIR, reach=land, bans=bans, contraband_reach=land)
        assert not p.contraband and p.duty_pct == 10.0


def test_only_the_banned_group_is_smuggled():
    seller = market(1, 1, ore_metal=good(200, 100), cloth=good(200, 100))
    buyer = market(2, 2, ore_metal=good(0, 100), cloth=good(0, 100))
    plans = plan({1: seller, 2: buyer}, OPEN_PAIR, groups={ORE.code: ORE, CLOTH.code: CLOTH}, reach=land,
                 bans={2: frozenset({"cloth"})}, contraband_reach=land)
    assert {(p.group_code, p.contraband) for p in plans} == {("cloth", True), ("ore_metal", False)}
    by_code = {p.group_code: p for p in plans}
    assert by_code["cloth"].duty == 0 and by_code["ore_metal"].duty > 0


@pytest.mark.parametrize("markup", [0.0, 50.0, 100.0, 250.0])
def test_contraband_unit_price_carries_the_markup(markup):
    params = replace(P, customs_contraband_markup_pct=markup)
    [legal] = plan({1: SELLER, 2: BUYER}, OPEN_PAIR, params, reach=land)
    [smuggled] = plan({1: SELLER, 2: BUYER}, OPEN_PAIR, params, reach=land, bans=BAN_ORE_IN_2,
                      contraband_reach=land)
    assert smuggled.markup_pct == markup
    assert smuggled.unit_price == pytest.approx(legal.unit_price * (1 + markup / 100))
    assert smuggled.value + smuggled.duty + smuggled.freight == smuggled.paid_purse + smuggled.paid_treasury


def test_negative_markup_param_counts_as_zero():
    params = replace(P, customs_contraband_markup_pct=-30.0)
    [legal] = plan({1: SELLER, 2: BUYER}, OPEN_PAIR, params, reach=land)
    [smuggled] = plan({1: SELLER, 2: BUYER}, OPEN_PAIR, params, reach=land, bans=BAN_ORE_IN_2,
                      contraband_reach=land)
    assert smuggled.markup_pct == 0.0 and smuggled.unit_price == legal.unit_price


def test_full_share_smuggles_the_whole_blocked_deal():
    params = replace(P, customs_contraband_share=1.0)
    [legal] = plan({1: SELLER, 2: BUYER}, OPEN_PAIR, params, reach=land)
    [smuggled] = plan({1: SELLER, 2: BUYER}, {}, params, reach=land, bans={}, contraband_reach=land)
    assert smuggled.contraband and smuggled.units == legal.units


def test_legal_seller_first_even_when_contraband_is_cheaper_or_by_sea():
    pricey = market(1, 1, ore_metal=good(200, 100, mult=3.0))
    markets = {1: pricey, 2: BUYER, 4: CLOSED_SELLER}
    plans = plan(markets, OPEN_PAIR, reach=land, bans={}, contraband_reach=land)
    assert [(p.from_region_id, p.contraband) for p in plans] == [(1, False), (4, True)]
    assert plans[1].unit_price < plans[0].unit_price         # cheaper contraband still comes second
    assert plans[0].markup_pct == 0.0 and plans[1].markup_pct == P.customs_contraband_markup_pct

    # a legal SEA deal also beats a contraband land deal — and takes the last physical slot
    sea_for_1 = lambda a, b: SEA5 if a == 1 else LAND   # noqa: E731
    plans = plan(markets, OPEN_PAIR, reach=sea_for_1, bans={}, contraband_reach=land)
    assert [(p.from_region_id, p.contraband, p.kind) for p in plans] == [(1, False, cv.REACH_SEA),
                                                                         (4, True, cv.REACH_LAND)]
    plans = plan(markets, OPEN_PAIR, reach=sea_for_1, sea_slots=1, bans={}, contraband_reach=land)
    assert [(p.from_region_id, p.contraband) for p in plans] == [(1, False)]


def test_each_contraband_plan_takes_one_physical_slot_legal_land_takes_none():
    markets = {1: SELLER, 2: BUYER, 4: CLOSED_SELLER, 5: market(5, 4, ore_metal=good(200, 100))}
    plans = plan(markets, OPEN_PAIR, reach=land, sea_slots=1, bans={}, contraband_reach=land)
    assert [(p.from_region_id, p.contraband) for p in plans] == [(1, False), (4, True)]
    plans = plan(markets, OPEN_PAIR, reach=land, sea_slots=2, bans={}, contraband_reach=land)
    assert [(p.from_region_id, p.contraband) for p in plans] == [(1, False), (4, True), (5, True)]


def test_open_pair_without_legal_reach_is_not_smuggled_even_if_banned_elsewhere():
    # allowed + not banned in the buyer country, but no legal road (e.g. the post is unreachable) → no deal at all
    no_reach = lambda a, b: None   # noqa: E731
    assert plan({1: SELLER, 2: BUYER}, OPEN_PAIR, reach=no_reach, bans={1: frozenset({"ore_metal"})},
                contraband_reach=land) == []


def test_domestic_trade_ignores_bans_and_closed_pairs_never_matter_domestically():
    home = market(3, 2, ore_metal=good(200, 100))
    [p] = plan({3: home, 2: BUYER}, {}, reach=land, bans=BAN_ORE_IN_2, contraband_reach=land)
    assert not p.contraband and p.duty == 0 and p.from_region_id == 3


def test_contraband_plan_is_deterministic():
    markets = {1: SELLER, 2: BUYER, 4: CLOSED_SELLER}
    kw = dict(reach=land, bans=BAN_ORE_IN_2, contraband_reach=land)
    assert plan(markets, OPEN_PAIR, **kw) == plan(markets, OPEN_PAIR, **kw)


def test_contraband_price_helper():
    assert cv.contraband_price(10, 50) == 15.0
    assert cv.contraband_price(10, 0) == 10.0
    assert cv.contraband_price(10, -20) == 10.0
    assert cv.contraband_price(0, 50) == 0.0
    assert cv.contraband_price(-5, 50) == 0.0
    assert cv.contraband_price(1.23456, 0) == 1.2346          # 4 decimals, half up
    assert cv.contraband_price(3.3333, 50) == 5.0             # 4.99995 → 5.0000


# ============================================================================================ money helpers

def test_settled_duty_only_once_the_inspection_started():
    assert cv.settled_duty(None, 50) is None
    assert cv.settled_duty(cc.STATE_PENDING, 50) is None
    assert cv.settled_duty(cc.STATE_INSPECTING, 50) == 50
    assert cv.settled_duty(cc.STATE_CLEARED, 50) == 50
    assert cv.settled_duty(cc.STATE_CLEARED, None) == 0
    assert cv.settled_duty(cc.STATE_INSPECTING, -7) == 0


def test_remaining_payout_with_duty_paid():
    # legacy (not settled): the duty is still in the escrow
    assert cv.remaining_payout(1000, 100, 1100, 0) == (1000, 100)
    assert cv.remaining_payout(1000, 100, 1100, 0, duty_paid=None) == (1000, 100)
    assert cv.remaining_payout(1000, 100, 1100, 200) == (819, 81)
    # settled at the post: the seller gets the rest, no duty part left
    assert cv.remaining_payout(1000, 100, 1100, 0, duty_paid=100) == (1000, 0)
    assert cv.remaining_payout(1000, 100, 1100, 200, duty_paid=100) == (800, 0)
    assert cv.remaining_payout(1000, 100, 1150, 200, freight=50, duty_paid=100) == (800, 0)
    # pro-rated duty (raided before the post) is what was settled
    assert cv.remaining_payout(1000, 100, 1100, 200, duty_paid=81) == (819, 0)
    # zero duty settled (duty-free pair) and never negative
    assert cv.remaining_payout(1000, 0, 1000, 0, duty_paid=0) == (1000, 0)
    assert cv.remaining_payout(1000, 100, 1100, 1000, duty_paid=500) == (0, 0)


def test_refund_split_with_duty_paid():
    assert cv.refund_split(600, 400, 0) == (600, 400)
    assert cv.refund_split(600, 400, 0, duty_paid=0) == (600, 400)
    assert cv.refund_split(600, 400, 0, duty_paid=100) == (540, 360)
    assert cv.refund_split(600, 400, 100, 50, 100) == (450, 300)
    back = cv.refund_split(700, 300, 33, 17, 101)
    assert sum(back) == 1000 - 33 - 17 - 101
    assert cv.refund_split(600, 400, 900, duty_paid=500) == (0, 0)   # capped at what was paid
    assert cv.refund_split(0, 0, 0, duty_paid=10) == (0, 0)


def test_raid_marks_cap_with_duty_paid():
    assert cv.raid_marks_cap(1150, 50, 200) == 900
    assert cv.raid_marks_cap(1150, 50, 200, 100) == 800
    assert cv.raid_marks_cap(1150, 50, 200, duty_paid=None) == 900
    assert cv.raid_marks_cap(100, 0, 50, 100) == 0


# ============================================================================================ customs_core

def test_constants():
    assert cc.KINDS == ("raid", "customs", "patrol") and cc.ENFORCEMENT_KINDS == ("customs", "patrol")
    assert cc.DUTY_SETTLED_STATES == (cc.STATE_INSPECTING, cc.STATE_CLEARED)
    assert cc.STATE_PENDING not in cc.DUTY_SETTLED_STATES
    assert cc.SEIZURE_REASONS == ("seized_customs", "seized_patrol")
    assert cc.CRIME_SMUGGLING == law_core.CRIME_SMUGGLING == "smuggling"
    assert cc.CUSTOMS_ROLE == "customs"


@pytest.mark.parametrize("args, expected", [
    ((35, 20, 20, 5, 90), "33.60"),          # 35 × 1.2 × 0.8
    ((35, 0, 0, 5, 90), "35.00"),
    ((80, 50, 0, 5, 90), "90.00"),           # 120 → hi
    ((35, 0, 99, 5, 90), "5.00"),            # 0.35 → lo
    ((35, 0, 150, 5, 90), "5.00"),           # reduction clamped to 100 → 0 → lo
    ((35, 0, -50, 5, 90), "35.00"),          # negative reduction counts as 0
    ((35, -50, 0, 5, 90), "35.00"),          # negative attention counts as 0
    ((35, 0, 0, 50, 20), "20.00"),           # lo > hi → lo = hi
    ((80, 100, 0, 0, 500), "100.00"),        # hi clamped to 100
    ((10, 0, "33.333", 0, 100), "6.67"),     # 2 decimals, half up
    ((None, None, None, 5, 90), "5.00"),
    (("35", "20", "20", "5", "90"), "33.60"),
])
def test_detection_chance(args, expected):
    value = cc.detection_chance(*args)
    assert isinstance(value, Decimal) and value == Decimal(expected)


@pytest.mark.parametrize("args, expected", [
    ((5, 20, 90), "4.00"),
    ((5, 0, 90), "5.00"),
    ((5, 150, 90), "0.00"),
    ((50, 0, 10), "10.00"),
    ((-5, 0, 90), "0.00"),
    ((5, 0, 200), "5.00"),
    ((150, 0, 200), "100.00"),
    ((5, "33.333", 90), "3.33"),
])
def test_patrol_chance(args, expected):
    value = cc.patrol_chance(*args)
    assert isinstance(value, Decimal) and value == Decimal(expected)


def test_caravan_stealth():
    assert cc.caravan_stealth(20, [5, 30, -10]) == 50       # base + the best escort only
    assert cc.caravan_stealth(20, []) == 20
    assert cc.caravan_stealth(20, None) == 20
    assert cc.caravan_stealth(20, [-3]) == 20
    assert cc.caravan_stealth(-5, [10]) == 10
    assert cc.caravan_stealth(20.9, [3.7, Decimal("2.2")]) == 23
    assert cc.caravan_stealth(0, (x for x in (4, 9))) == 9


def test_illegal_in_and_is_banned():
    bans = {3: frozenset({"ore_metal"}), 4: ["cloth"]}
    assert cc.illegal_in(2, 2, "ore_metal", bans)              # the destination country
    assert cc.illegal_in(2, 2, None, None)
    assert cc.illegal_in(3, 2, "ore_metal", bans)              # banned on the way
    assert cc.illegal_in("4", 2, "cloth", bans)
    assert not cc.illegal_in(4, 2, "ore_metal", bans)
    assert not cc.illegal_in(5, 2, "ore_metal", bans)          # neither destination nor banning
    assert not cc.illegal_in(None, 2, "ore_metal", bans)       # no country → never
    assert not cc.illegal_in(3, None, None, bans)
    assert cc.illegal_in(3, None, "ore_metal", bans)
    assert not cc.illegal_in(3, 2, "ore_metal", None)

    assert cc.is_banned(bans, 3, "ore_metal") and cc.is_banned(bans, "4", "cloth")
    assert not cc.is_banned(bans, 3, "cloth")
    assert not cc.is_banned(bans, None, "ore_metal")
    assert not cc.is_banned(bans, 3, "") and not cc.is_banned(bans, 3, None)
    assert not cc.is_banned(None, 3, "ore_metal") and not cc.is_banned({}, 3, "ore_metal")


def test_officer_split_and_pool():
    assert cc.officer_split(10, 3) == (3, 1)
    assert cc.officer_split(9, 3) == (3, 0)
    assert cc.officer_split(2, 5) == (0, 2)
    assert cc.officer_split(10, 0) == (0, 10)
    assert cc.officer_split(10, -1) == (0, 10)
    assert cc.officer_split(-10, 2) == (0, 0)
    assert cc.officer_split(None, None) == (0, 0)
    for pool, n in ((101, 7), (1, 1), (0, 4)):
        each, rest = cc.officer_split(pool, n)
        assert each * n + rest == pool and 0 <= rest < n

    assert cc.officer_pool(1000, 0.2) == 200
    assert cc.officer_pool(999, 0.2) == 199                   # floor
    assert cc.officer_pool(1000, "0.333") == 333
    assert cc.officer_pool(1000, 1.5) == 1000                 # never above the rest
    assert cc.officer_pool(1000, -0.2) == 0
    assert cc.officer_pool(-50, 0.2) == 0
    assert cc.officer_pool(None, None) == 0
    assert cc.officer_pool(1000, 0) == 0


def test_normalize_ban_codes():
    known = ["food", "ore_metal", "cloth", "wood"]
    assert cc.normalize_ban_codes([" cloth ", "food", "cloth", "", None], known) == ["food", "cloth"]
    assert cc.normalize_ban_codes(None, known) == []
    assert cc.normalize_ban_codes([], known) == []
    with pytest.raises(ValueError) as err:
        cc.normalize_ban_codes(["cloth", "spice"], known)
    assert str(err.value) == "spice"
    with pytest.raises(ValueError):
        cc.normalize_ban_codes(["'; DROP TABLE econ_country_bans --"], known)
    many = [f"g{i}" for i in range(cc.MAX_BANNED_GROUPS + 1)]
    assert len(cc.normalize_ban_codes(many[:-1], many)) == cc.MAX_BANNED_GROUPS
    with pytest.raises(ValueError) as err:
        cc.normalize_ban_codes(many, many)
    assert str(err.value) == "too_many"


# ============================================================================================ RoutePlanner

#   10 - 11 - 12 - 13 - 14      (r1 gate 10, country 1; r2 gate 14, country 2)
#         \             /
#          20 ------- 21
LINE = graph((10, 11), (11, 12), (12, 13), (13, 14), (11, 20), (20, 21), (21, 14))
G = gates(r1=(10, 1), r2=(14, 2))


def test_legal_route_is_a_three_tuple_with_reasons():
    rp = planner(posts={2: [21]})
    route, index, reason = rp.legal_route(1, 2)
    assert route[index] == 21 and reason is None
    assert rp.legal_route(1, 2) is rp.legal_route(1, 2)                       # cached
    # unknown region / missing gate
    assert planner(posts={2: [21]}).legal_route(1, 9) == (None, None, caravan_route.NO_ROAD_NO_GATE)
    # both regions on the same gate with a post rule
    same = planner(gs=gates(r1=(10, 1), r2=(10, 2)), posts={2: [21]})
    assert same.legal_route(1, 2) == (None, None, caravan_route.NO_ROAD_NO_GATE)
    # unreachable post
    rp = planner(g=graph((10, 11), (11, 14), (30, 31)), posts={2: [31]})
    assert rp.legal_route(1, 2) == (None, None, caravan_route.NO_ROAD_NO_PATH)


def test_legal_route_picks_the_nearest_post_and_breaks_ties_by_id():
    # 21 (via 20) and 13 are both 4 hops in total; 13 is on the plain road
    rp = planner(posts={2: [21, 13]})
    route, index, _ = rp.legal_route(1, 2)
    assert route == [10, 11, 12, 13, 14] and route[index] == 13
    # two equal detours: 30 and 31 each hang off 12 → the lower id wins
    g = graph((10, 11), (11, 12), (12, 13), (13, 14), (12, 31), (12, 30))
    route, index, _ = planner(g=g, posts={2: [31, 30]}).legal_route(1, 2)
    assert route == [10, 11, 12, 30, 12, 13, 14] and index == 3                # dead-end post: in and back out


def test_posts_of_other_countries_are_ignored_by_legal_routes():
    rp = planner(posts={3: [12], 2: [14]})
    route, index, _ = rp.legal_route(1, 2)
    assert route == [10, 11, 12, 13, 14] and index == 4    # passes country 3's post 12 freely, stops at 14


def test_legal_route_via_a_post_respects_max_steps():
    # the only post detour is 5 hops while the plain road is 4
    g = graph((10, 11), (11, 12), (12, 13), (13, 14), (11, 20), (20, 22), (22, 21), (21, 14))
    assert planner(g=g, posts={2: [22]}).legal_route(1, 2)[0] is not None
    rp = crud_planner(g, max_steps=4, posts={2: [22]})
    assert rp.legal_route(1, 2) == (None, None, caravan_route.NO_ROAD_NO_PATH)
    assert rp.route(1, 2)[0] == [10, 11, 12, 13, 14]           # the plain road would have fit
    assert rp.reach(1, 2) is None


def test_post_at_the_seller_gate_gives_customs_index_zero():
    rp = planner(posts={2: [10]})
    route, index, _ = rp.legal_route(1, 2)
    assert route == [10, 11, 12, 13, 14] and index == 0


def test_dungeons_stay_blocked_for_legal_and_contraband_routes():
    g = graph((10, 11), (11, 12), (12, 13), (13, 14), (11, 20), (20, 21), (21, 14), blocked={12})
    route, index, _ = planner(g=g, posts={2: [13]}).legal_route(1, 2)          # reach post 13 around the dungeon
    assert route == [10, 11, 20, 21, 14, 13, 14] and index == 5
    assert planner(g=g, posts={2: [21]}).contraband_route(1, 2) == (None, caravan_route.NO_ROAD_NO_PATH)
    assert planner(g=g, posts={}).contraband_route(1, 2)[0] == [10, 11, 20, 21, 14]


def test_contraband_route_reasons_and_buyer_gate_post():
    assert planner(posts={2: [14]}).contraband_route(1, 2) == (None, caravan_route.NO_ROAD_NO_PATH)
    assert planner(posts={5: [14]}).contraband_route(1, 2) == (None, caravan_route.NO_ROAD_NO_PATH)  # any country
    assert planner(posts={}).contraband_route(1, 9) == (None, caravan_route.NO_ROAD_NO_GATE)
    # a third country's post blocks the shortest road → the detour
    assert planner(posts={3: [12]}).contraband_route(1, 2)[0] == [10, 11, 20, 21, 14]


def test_contraband_reach_kinds_and_freight():
    assert planner(posts={2: [21]}).contraband_reach(1, 2) == LAND
    assert planner(posts={2: [14]}).contraband_reach(1, 2) is None           # buyer gate is a post, no sea
    rp = planner(g=SEA, gs=SEA_G, posts={2: [51]}, sea_pairs=PAIRS, freight_pct=7.0)
    assert rp.contraband_route(1, 2)[0] is None
    assert rp.contraband_reach(1, 2) == cv.Reach(cv.REACH_SEA, 7.0)
    # contraband is never abstract
    rp = planner(g=graph((10, 11), (30, 14)), posts={}, abstract_fallback=True)
    assert rp.reach(1, 2) == LAND and rp.contraband_reach(1, 2) is None


#  r1 gate 10 - 40 (port) ~~sea~~ 50 (port) - 51 - 52 (r2 gate) ; 60 (port) - 52 ; ships 40->50, 40->60
SEA = graph((10, 40), (50, 51), (51, 52), (60, 52))
SEA_G = gates(r1=(10, 1), r2=(52, 2))
PAIRS = {(40, 50): SeaPair(2), (40, 60): SeaPair(3)}


def crud_planner(g, max_steps, **kw):
    import economy_caravan_crud as crud
    return crud.RoutePlanner(g, kw.pop("gs", G), 0, max_steps, kw.pop("sea_pairs", None), max_active=5,
                             posts_by_country=kw.pop("posts", None), customs_ports=kw.pop("ports", ()),
                             customs_enabled=kw.pop("on", True), **kw)


def test_sea_route_customs_index_maths():
    rp = planner(g=SEA, gs=SEA_G, posts={2: [51]}, sea_pairs=PAIRS)
    sea = rp.sea_route(1, 2)
    assert sea.route == [10, 40, 50, 51, 52] and sea.split_index == 1
    assert sea.customs_offset == 1 and sea.customs_index == 3 and sea.route[sea.customs_index] == 51


def test_sea_legal_skips_a_landing_port_whose_land_leg_misses_every_post():
    # post 61 sits between port 60 and the gate: landing at 50 would need a 52-61-52 detour, so 60 wins
    g = graph((10, 40), (50, 51), (51, 52), (60, 61), (61, 52))
    rp = planner(g=g, gs=SEA_G, posts={2: [61]}, sea_pairs=PAIRS)
    sea = rp.sea_route(1, 2)
    assert sea.alight_port == 60 and sea.route[sea.customs_index] == 61
    # no post reachable from any landing port → no legal sea route; no land route either → no reach
    rp = planner(g=g, gs=SEA_G, posts={2: [99]}, sea_pairs=PAIRS)
    assert rp.sea_route(1, 2) is None and rp.reach(1, 2) is None


def test_sea_landing_at_a_non_customs_port_still_passes_the_post():
    g = graph((10, 40), (50, 51), (51, 52), (60, 52))
    # equal sea legs: landing right at the customs port 50 (offset 0) is the shortest
    rp = planner(g=g, gs=SEA_G, posts={2: [50]}, ports=[50], sea_pairs={(40, 50): SeaPair(2), (40, 60): SeaPair(2)})
    sea = rp.sea_route(1, 2)
    assert sea.alight_port == 50 and sea.customs_offset == 0 and sea.customs_index == sea.split_index + 1
    # a much shorter crossing to the plain port 60 is allowed only with land leg 2 walking to the post and back
    short60 = {(40, 50): SeaPair(5), (40, 60): SeaPair(1)}
    sea = planner(g=g, gs=SEA_G, posts={2: [50]}, ports=[50], sea_pairs=short60).sea_route(1, 2)
    assert sea.alight_port == 60 and sea.land2 == [60, 52, 51, 50, 51, 52] and sea.route[sea.customs_index] == 50
    # customs off → plain cheapest pair, no post
    sea = planner(g=g, gs=SEA_G, posts={2: [50]}, ports=[50], on=False, sea_pairs=short60).sea_route(1, 2)
    assert sea.alight_port == 60 and sea.land2 == [60, 52] and sea.customs_index is None


def test_domestic_sea_route_has_no_customs():
    rp = planner(g=SEA, gs=gates(r1=(10, 2), r2=(52, 2)), posts={2: [50]}, ports=[50], sea_pairs=PAIRS)
    sea = rp.sea_route(1, 2)
    assert sea.customs_index is None and sea.alight_port == 50


def test_reach_goes_to_sea_when_the_land_post_is_unreachable():
    # land road 10-11-52 has no post of country 2; walking to the post 50 and back is 6 hops > max 5,
    # while landing at the customs port 50 keeps both land legs short
    g = graph((10, 11), (11, 52), (10, 40), (50, 51), (51, 52))
    rp = crud_planner(g, 5, gs=SEA_G, posts={2: [50]}, ports=[50], sea_pairs={(40, 50): SeaPair(2)},
                      freight_pct=5.0)
    assert rp.legal_route(1, 2)[0] is None
    assert rp.reach(1, 2) == SEA5
    # smugglers take the post-free land road instead
    assert rp.contraband_reach(1, 2) == LAND and rp.contraband_route(1, 2)[0] == [10, 11, 52]


def test_contraband_sea_rules():
    # board port may be a customs post (exports are not inspected)
    rp = planner(g=SEA, gs=SEA_G, posts={1: [40]}, ports=[40], sea_pairs=PAIRS)
    assert rp.contraband_sea_route(1, 2).board_port == 40
    # landing port that is a post (of any country) is skipped even if not flagged as a customs port
    rp = planner(g=SEA, gs=SEA_G, posts={3: [50]}, sea_pairs=PAIRS)
    assert rp.contraband_sea_route(1, 2).alight_port == 60
    # land leg 2 avoids posts: 51 is a post → landing at 50 has no clean leg → 60
    rp = planner(g=SEA, gs=SEA_G, posts={2: [51]}, sea_pairs=PAIRS)
    assert rp.contraband_sea_route(1, 2).alight_port == 60
    # buyer gate is a post → no contraband sea route at all
    rp = planner(g=SEA, gs=SEA_G, posts={2: [52]}, sea_pairs=PAIRS)
    assert rp.contraband_sea_route(1, 2) is None and rp.contraband_reach(1, 2) is None
    # both landing ports are customs ports → None
    rp = planner(g=SEA, gs=SEA_G, posts={2: [50, 60]}, ports=[50, 60], sea_pairs=PAIRS)
    assert rp.contraband_sea_route(1, 2) is None
    # contraband sea routes never carry a customs offset
    rp = planner(g=SEA, gs=SEA_G, posts={}, sea_pairs=PAIRS)
    assert rp.contraband_sea_route(1, 2).customs_index is None
