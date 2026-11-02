"""FEAT-195: charisma discount through the soft/hard stat cap (econ_core, character-service copy).

charisma_discount_pct(c) = min(eff(c) * 0.1, 50) with eff = full to 100, half to 200, quarter above.
The 50 % ceiling (MAX_CHARISMA_DISCOUNT) is kept as a safety net and is first reached at charisma 1600.
Everything the ceiling protects - merchant bid, ask_discount_floor, the FEAT-193 guild payout cap - must
stay arbitrage-free at ANY charisma, including the ceiling itself.
"""

import itertools
from decimal import Decimal

import pytest

import econ_core as core
import econ_guild as g


def _eff_float(x: float) -> float:
    """Independent float twin of stat_caps.effective_stat (the canonical copy lives in
    character-attributes-service, which this service does not ship)."""
    if x <= 100:
        return x
    if x <= 200:
        return 100 + (x - 100) * 0.5
    return 150 + (x - 200) * 0.25


def test_constants():
    assert core.CHARISMA_DISCOUNT_PER_POINT == Decimal("0.1")
    assert core.MAX_CHARISMA_DISCOUNT == Decimal("0.5")
    assert (core.STAT_SOFT_CAP, core.STAT_HARD_CAP) == (100, 200)
    assert (core.STAT_SOFT_RATE, core.STAT_HARD_RATE) == (Decimal("0.5"), Decimal("0.25"))


@pytest.mark.parametrize("charisma,expected", [
    (0, Decimal(0)), (100, Decimal(10)), (250, Decimal("16.25")), (530, Decimal("23.25")),
])
def test_spec_values(charisma, expected):
    assert core.charisma_discount_pct(charisma) == expected


def test_matches_stat_caps_formula_everywhere_below_ceiling():
    for c in range(1, 1601):
        assert float(core.charisma_discount_pct(c)) == pytest.approx(_eff_float(c) * 0.1, abs=1e-12), c


def test_ceiling_first_reached_at_1600_and_never_exceeded():
    assert core.charisma_discount_pct(1599) < 50
    assert core.charisma_discount_pct(1600) == 50
    for c in (1601, 5000, 10 ** 9, "1e30"):
        assert core.charisma_discount_pct(c) == 50


def test_marginal_rate_halves_then_quarters():
    pct = core.charisma_discount_pct
    assert pct(100) - pct(99) == Decimal("0.1")
    assert pct(101) - pct(100) == Decimal("0.05")
    assert pct(201) - pct(200) == Decimal("0.025")


@pytest.mark.parametrize("garbage", [None, True, False, "", "abc", "NaN", "-Infinity", -1, [5], {}])
def test_garbage_is_zero(garbage):
    assert core.charisma_discount_pct(garbage) == 0


def test_injection_like_string_is_zero():
    assert core.charisma_discount_pct("530; DROP TABLE characters; --") == 0


_ASKS = (1, 2, 3, 7, 19, 20, 21, 99, 100, 101, 2500, 99999)
_CHARISMAS = (0, 50, 100, 150, 250, 530, 1000, 1600, 10 ** 6)


def test_no_buy_and_sell_back_profit_at_any_charisma():
    """Bid caps (market_bid / ask_discount_floor) never exceed the cheapest discounted ask."""
    for ask, c in itertools.product(_ASKS, _CHARISMAS):
        cheapest = core.discounted_ask(ask, core.charisma_discount_pct(c))
        assert core.ask_discount_floor(ask) <= cheapest, (ask, c)
        for base_bid in (1, ask // 2, ask, 3 * ask):
            assert core.market_bid(base_bid, "1", ask) <= cheapest, (ask, c, base_bid)


def test_guild_payout_never_beats_discounted_merchant_ask():
    """FEAT-193: a guild order capped by merchants never pays more than a player with any charisma pays."""
    for ask, c in itertools.product(_ASKS, _CHARISMAS):
        cheapest = core.discounted_ask(ask, core.charisma_discount_pct(c))
        for item_base, mult, markup in ((ask, "1", 0), (ask * 3, "2.5", 50), (1, "0.5", 0)):
            best_bid = core.market_bid(item_base // 2, "1", ask)
            price = g.unit_price(item_base, Decimal(mult), Decimal(markup), ask, best_bid)
            assert price.unit_price <= cheapest, (ask, c, item_base, mult, markup)


def test_discounted_ask_at_extremes_unchanged():
    assert core.discounted_ask(1000, core.charisma_discount_pct(10 ** 6)) == 500
    assert core.discounted_ask(1000, core.charisma_discount_pct(530)) == 768   # ceil(767.5)
    assert core.discounted_ask(1, core.charisma_discount_pct(10 ** 6)) == 1
