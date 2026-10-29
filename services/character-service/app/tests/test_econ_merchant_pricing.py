"""FEAT-183 Q1: extra unit tests of the merchant pricing functions in econ_core (character-service copy).

The shared table (tests/econ_contract_cases.py PRICING_CASES & co.) runs in all 4 services; this file adds
edge cases on top of it: rounding at the boundaries, Decimal / int / str / float inputs giving the same
result, zero / negative / huge values, charisma bounds, the no-profit bid cap, multiplier 1 for legacy and
off-market items, units mapping with a non-positive base, trade tax rate bounds, every merchant_status
reason with its precedence, and that the shop SQL is parameterized (values never reach the SQL text).
"""

import itertools
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

import econ_core as core
from tests import econ_contract_cases as cc

HUGE = core.MAX_AMOUNT  # 10 ** 15, the largest amount the ledger accepts


# ---------------------------------------------------------------------------
# market_ask
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("base,mult,expected", [
    (10, "1.0001", 11),        # a hair above an integer rounds up
    (10, "0.9999", 10),        # a hair below an integer rounds up to it
    (10, "1.1", 11),           # exact product: no rounding
    (3, "0.5", 2),             # 1.5 -> 2 (ceil, not half-even)
    (5, "0.5", 3),             # 2.5 -> 3 (ceil, not banker's 2)
    (1, "0.001", 1),           # floor of 1 coin
    (0, "1", 1),
    (-100, "2", 1),            # garbage base never yields a non-positive price
    (100, "0", 1),
    (100, "-1", 1),
    (HUGE, "3", 3 * HUGE),     # exact: no float precision loss
    (HUGE, "1.000000001", HUGE + 10 ** 6),
    (HUGE + 1, "1", HUGE + 1),
])
def test_market_ask_edges(base, mult, expected):
    assert core.market_ask(base, mult) == expected


@pytest.mark.parametrize("base", [7, "7", Decimal("7"), 7.0])
@pytest.mark.parametrize("mult", ["1.1", Decimal("1.1"), 1.1])
def test_market_ask_input_types_agree(base, mult):
    # 7 * 1.1 = 7.7 -> 8 regardless of the input type (floats go through str, not their binary value)
    assert core.market_ask(base, mult) == 8


def test_market_ask_returns_int():
    assert type(core.market_ask(Decimal("7"), Decimal("1.1"))) is int


# ---------------------------------------------------------------------------
# market_bid (cap = floor(ask * 0.5))
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("base_bid,mult,ask,expected", [
    (10, "1", 21, 10),              # 21 / 2 = 10.5 -> 10
    (11, "1", 21, 10),              # cap wins
    (9, "1", 21, 9),                # own price below the cap
    (10, "1.15", 100, 11),          # 11.5 -> 11 (floor)
    (10, "0.99", 100, 9),
    (10, "0", 20, 0),               # mult 0 -> nothing to pay -> «does not buy»
    (10, "1", 0, 0),
    (10, "1", -10, 0),
    (Decimal("0.5"), "1", 20, 0),   # fractional base below one coin
    (Decimal("1.5"), "1", 20, 1),
    (1, "1", 2, 1),                 # the smallest buyable pair
    (1, "1", 1, 0),
    (HUGE, "1", 2 * HUGE, HUGE),
    (HUGE, "3", 2 * HUGE, HUGE),    # cap bounds even a huge own bid
])
def test_market_bid_edges(base_bid, mult, ask, expected):
    assert core.market_bid(base_bid, mult, ask) == expected


@pytest.mark.parametrize("base_bid", [15, "15", Decimal("15"), 15.0])
@pytest.mark.parametrize("ask", [25, Decimal("25"), "25"])
def test_market_bid_input_types_agree(base_bid, ask):
    # min(floor(15 * 1.25) = 18, floor(25 * 0.5) = 12) = 12
    assert core.market_bid(base_bid, Decimal("1.25"), ask) == 12


_GRID_BASES = (1, 2, 3, 5, 7, 11, 19, 20, 37, 99, 100, 101, 2500, 99999)
_GRID_MULTS = ("0.1", "0.333", "0.5", "0.85", "0.999", "1", "1.001", "1.17", "1.5", "2.5", "3", "5")


def test_bid_never_beats_any_ask_and_never_exceeds_own_price():
    """No buy->sell-back profit at max charisma, wholesale never above the ask, bid never above floor(base*mult)."""
    max_pct = core.charisma_discount_pct(250)
    for base_ask, mult in itertools.product(_GRID_BASES, _GRID_MULTS):
        ask = core.market_ask(base_ask, mult)
        cheapest = core.discounted_ask(ask, max_pct)
        assert core.wholesale_price(base_ask, mult, "0.5") <= ask
        for base_bid in (1, base_ask // 2, base_ask, 3 * base_ask):
            bid = core.market_bid(base_bid, mult, ask)
            assert 0 <= bid <= cheapest, (base_ask, base_bid, mult)
            assert bid <= max(0, int(Decimal(base_bid) * Decimal(mult)))
            assert 2 * bid <= ask


def test_legacy_and_off_market_rows_price_at_mult_one():
    """A legacy merchant / off-market item prices exactly at the admin base (mult 1), whatever the region says."""
    mults = {"food": Decimal("2.5"), "weapons": Decimal("0.5")}
    cases = [
        (False, "food", False),     # legacy merchant
        (True, "food", True),       # off-market item
        (True, None, False),        # no group
        (True, "tools", False),     # group absent from the region
    ]
    for living, group, off_market in cases:
        mult = core.market_mult(living, group, off_market, mults)
        assert mult == 1
        assert core.market_ask(37, mult) == 37
        assert core.market_bid(10, mult, 37) == 10
        assert core.price_level(mult) == core.PRICE_LEVEL_NORMAL
    assert core.market_mult(True, "food", False, mults) == Decimal("2.5")


@pytest.mark.parametrize("value,expected", [
    (Decimal("1.3"), Decimal("1.3")),
    ("1.3", Decimal("1.3")),
    (1.3, Decimal("1.3")),
    (None, Decimal(1)),
    (-2, Decimal(1)),
    (Decimal("0.000"), Decimal(1)),
])
def test_market_mult_value_types(value, expected):
    assert core.market_mult(True, "food", False, {"food": value}) == expected


# ---------------------------------------------------------------------------
# wholesale_price
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("base,mult,share,expected", [
    (20, "1", "0", 1),             # share 0 still costs one coin
    (20, "1", "1", 20),
    (20, "1", "-0.5", 1),
    (3, "1", "0.5", 1),            # 1.5 -> 1 (floor)
    (21, "1.1", "0.5", 11),        # 11.55 -> 11
    (0, "1", "0.5", 1),
    (HUGE, "2", "0.5", HUGE),
    (Decimal("20"), Decimal("1.25"), Decimal("0.5"), 12),
    (20.0, 1.25, 0.5, 12),
])
def test_wholesale_price_edges(base, mult, share, expected):
    assert core.wholesale_price(base, mult, share) == expected


# ---------------------------------------------------------------------------
# charisma_discount_pct / discounted_ask
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("charisma,expected", [
    (0, Decimal(0)),
    (1, Decimal("0.2")),
    (250, Decimal(50)),
    (251, Decimal(50)),
    (10 ** 30, Decimal(50)),
    (249.5, Decimal("49.9")),
    ("100", Decimal(20)),
    (Decimal("125"), Decimal(25)),
    (True, Decimal(0)),             # bool is not a charisma value
    (False, Decimal(0)),
    ("", Decimal(0)),
    ("inf", Decimal(0)),
    ("-inf", Decimal(0)),
    ("nan", Decimal(0)),
    (float("inf"), Decimal(0)),
    ([], Decimal(0)),
    (-10 ** 30, Decimal(0)),
])
def test_charisma_discount_pct_bounds(charisma, expected):
    assert core.charisma_discount_pct(charisma) == expected


@pytest.mark.parametrize("ask,pct,expected", [
    (3, 50, 2),                    # 1.5 -> 2: the player rounds up
    (1, Decimal("49.8"), 1),
    (2, 50, 1),
    (100, Decimal("0.2"), 100),    # 99.8 -> 100
    (HUGE, 50, HUGE // 2),
    (HUGE + 1, 50, HUGE // 2 + 1),
    (20, Decimal(10 ** 30), 10),   # clamped to 50 %
    (20, "6", 19),
    (20, 6.0, 19),
])
def test_discounted_ask_edges(ask, pct, expected):
    assert core.discounted_ask(ask, pct) == expected


def test_discount_is_monotonic_in_charisma():
    prices = [core.discounted_ask(1000, core.charisma_discount_pct(c)) for c in range(0, 300)]
    assert prices[0] == 1000
    assert prices[250] == prices[299] == 500
    assert all(a >= b for a, b in zip(prices, prices[1:]))


# ---------------------------------------------------------------------------
# units_per_item
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("base,group_base", [(0, 10), (-5, 10), (-1, 1), (None, 10)])
def test_units_per_item_non_positive_base_never_trades(base, group_base):
    # econ_merchant skips rows with units <= 0; a non-positive base must never produce positive units
    assert core.units_per_item(base, group_base) <= 0


@pytest.mark.parametrize("group_base", [0, -10, None, Decimal("0"), "0"])
def test_units_per_item_without_group_base_is_zero(group_base):
    assert core.units_per_item(100, group_base) == 0.0


@pytest.mark.parametrize("base,group_base,expected", [
    (2500, 10, 250.0),
    (Decimal("2500"), Decimal("10"), 250.0),
    ("2500", "10", 250.0),
    (HUGE, 1, float(HUGE)),
    (1, HUGE, 1e-15),
])
def test_units_per_item_types_and_scale(base, group_base, expected):
    value = core.units_per_item(base, group_base)
    assert type(value) is float
    assert value == pytest.approx(expected)


def test_units_per_item_one_third():
    assert core.units_per_item(1, 3) == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# trade_tax
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("amount,rate,expected", [
    (100, "1", 100),                   # upper bound inclusive
    (100, "1.0000001", 100),           # clamped to 1
    (100, Decimal("99"), 100),
    (100, "0", 0),
    (100, "-0.0001", 0),
    (100, None, 0),
    (9999, "0.0001", 0),               # 0.9999 -> 0 (floor)
    (10000, "0.0001", 1),
    (30, 0.1, 3),                      # float 0.1 goes through str: exactly 3, not 2
    (HUGE, "0.15", 15 * 10 ** 13),
    (Decimal("199.9"), "0.1", 19),     # amount is an int of coins
    (199.9, "0.1", 19),
    (1, "0.9999", 0),
])
def test_trade_tax_bounds(amount, rate, expected):
    assert core.trade_tax(amount, rate) == expected


def test_trade_tax_never_exceeds_the_amount():
    for amount in (0, 1, 7, 99, 100, 101, 12345, HUGE):
        for rate in ("0", "0.05", "0.1", "0.15", "0.5", "0.9999", "1", "2"):
            tax = core.trade_tax(amount, rate)
            assert 0 <= tax <= amount


# ---------------------------------------------------------------------------
# default_bid / item_base_price
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("item_base,share,expected", [
    (0, "0.5", 0),
    (-10, "0.5", 0),
    (100, "0", 0),
    (100, "1", 100),
    (HUGE, "0.5", HUGE // 2),
    (3, Decimal("0.5"), 1),
])
def test_default_bid_edges(item_base, share, expected):
    assert core.default_bid(item_base, share) == expected


def test_merchant_bid_share_clamps_and_survives_garbage():
    assert core.merchant_bid_share({"merchant_bid_share": "nan"}) == core.DEFAULT_MERCHANT_BID_SHARE
    assert core.merchant_bid_share({"merchant_bid_share": "inf"}) == core.DEFAULT_MERCHANT_BID_SHARE
    assert core.merchant_bid_share({"merchant_bid_share": [1]}) == core.DEFAULT_MERCHANT_BID_SHARE
    assert core.merchant_bid_share({"merchant_bid_share": 0}) == Decimal(0)
    assert core.merchant_bid_share({"merchant_bid_share": 1}) == Decimal(1)
    assert core.merchant_bid_share(bytearray(b"\xff\xfe")) == core.DEFAULT_MERCHANT_BID_SHARE


# ---------------------------------------------------------------------------
# merchant_status: every reason and the documented precedence
# ---------------------------------------------------------------------------

_REGION = (10, "capital", 1200, "0.15")


@pytest.mark.parametrize("npc_row,region_row,expected", [
    ((5, 1, "alive", 1000, "safe"), _REGION, (True, None)),
    ((5, 1, None, 1000, None), _REGION, (True, None)),                      # status / marker unknown
    ((5, 1, "alive", 1000, "safe"), (10, "rural", "5", "0.1"), (True, None)),
    # not_npc beats everything
    (None, None, (False, "not_npc")),
    ((5, None, "dead", None, "dungeon"), None, (False, "not_npc")),
    ((5, False, "alive", 1000, "safe"), _REGION, (False, "not_npc")),
    # dead beats no_location / dungeon / no_region
    ((5, 1, "dead", None, None), None, (False, "dead")),
    # no_location beats dungeon / no_region
    ((5, 1, "alive", None, "dungeon"), None, (False, "no_location")),
    # dungeon beats no_region / not_simulated
    ((5, 1, "alive", 1000, "dungeon"), None, (False, "dungeon")),
    ((5, 1, "alive", 1000, "dungeon"), (10, None, 0, "0.1"), (False, "dungeon")),
    # no_region
    ((5, 1, "alive", 1000, "safe"), None, (False, "no_region")),
    # not_simulated
    ((5, 1, "alive", 1000, "safe"), (10, "capital", -3, "0.1"), (False, "not_simulated")),
    ((5, 1, "alive", 1000, "safe"), (10, None, 0, None), (False, "not_simulated")),
])
def test_merchant_status_reasons_and_precedence(npc_row, region_row, expected):
    assert core.merchant_status(npc_row, region_row) == expected


def test_merchant_status_reaches_every_legacy_reason():
    seen = {core.merchant_status(n, r)[1] for n, r, _ in cc.MERCHANT_STATUS_CASES} - {None}
    assert seen == set(core.MERCHANT_LEGACY_REASONS)
    assert core.MERCHANT_REASON_NOT_NPC in core.MERCHANT_LEGACY_REASONS


# ---------------------------------------------------------------------------
# Security: shop SQL is parameterized
# ---------------------------------------------------------------------------

_HOSTILE = "1) OR 1=1; DROP TABLE items; --"


def test_in_params_puts_values_in_params_not_in_sql():
    placeholders, params = core.in_params("i", [_HOSTILE, 7])
    assert placeholders == ":i0, :i1"
    assert params == {"i0": _HOSTILE, "i1": 7}
    for sql in (core.sql_item_market(placeholders), core.sql_lock_shop_rows(placeholders, True),
                core.sql_lock_shop_rows(placeholders, False, by="id")):
        assert "IN (:i0, :i1)" in sql
        assert _HOSTILE not in sql and "DROP" not in sql


def test_shop_row_key_is_whitelisted():
    with pytest.raises(core.EconomyError):
        core.sql_lock_shop_rows(":n0", False, by="npc_id = 1 OR 1")
    with pytest.raises(core.EconomyError):
        core.sql_lock_shop_rows(":n0", False, by="item_id")


def test_for_update_is_only_a_suffix_toggle():
    base = core.sql_lock_shop_rows(":n0", False)
    assert core.sql_lock_shop_rows(":n0", True) == base + " FOR UPDATE"
    assert core.sql_shop_row_by_item(True) == core.sql_shop_row_by_item(False) + " FOR UPDATE"
    assert "FOR UPDATE" not in base


@pytest.mark.parametrize("name", [
    "SQL_NPC_PLACE", "SQL_REGION_ECON", "SQL_REGION_MARKET", "SQL_SIM_PARAMS",
    "SQL_SHOP_STOCK_TAKE", "SQL_SHOP_STOCK_ADD", "SQL_SHOP_STOCK_SET",
])
def test_merchant_sql_constants_have_no_unformatted_slots(name):
    sql = getattr(core, name)
    assert "{" not in sql and "}" not in sql and "%" not in sql
    assert "'" not in sql            # no literal values: everything goes through :named binds


def test_merchant_sql_generators_bind_named_params():
    sql = core.sql_shop_row_by_item(False)
    assert ":npc_id" in sql and ":item_id" in sql
    assert ":q" in core.SQL_SHOP_STOCK_TAKE and ":id" in core.SQL_SHOP_STOCK_TAKE


@pytest.fixture()
def merchant_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as conn:
        for ddl in cc.MERCHANT_SQLITE_DDL:
            conn.execute(text(ddl))
        for sql, params in cc.MERCHANT_SEED_SQL:
            conn.execute(text(sql), params)
    try:
        yield engine
    finally:
        engine.dispose()


def test_hostile_values_are_bound_not_executed(merchant_engine):
    with merchant_engine.begin() as conn:
        ph, params = core.in_params("i", [_HOSTILE])
        assert conn.execute(text(core.sql_item_market(ph)), params).fetchall() == []
        ph, params = core.in_params("n", [_HOSTILE])
        assert conn.execute(text(core.sql_lock_shop_rows(ph, False)), params).fetchall() == []
        rows = conn.execute(text(core.sql_shop_row_by_item(False)),
                            {"npc_id": "31 OR 1=1", "item_id": "1 OR 1=1"}).fetchall()
        assert rows == []
        assert conn.execute(text(core.SQL_NPC_PLACE), {"id": "31 OR 1=1"}).fetchall() == []
        # tables are intact
        assert conn.execute(text("SELECT COUNT(*) FROM items")).scalar() == 7
        assert conn.execute(text("SELECT COUNT(*) FROM npc_shop_items")).scalar() == 4
