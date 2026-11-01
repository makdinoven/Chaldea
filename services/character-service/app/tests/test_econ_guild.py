"""FEAT-193 QA (#8): pure guild-order math (``econ_guild``) — no DB, no clock, no RNG.

Covers the recount (budgets / plan_orders, 3.3 / 3.4), the unit price (3.5 incl. the PM correction: never below the
best merchant bid, never above floor(cheapest ask x 0.5) of an item a regional merchant sells), the refusal order
(3.6), acceptance with the last-piece overshoot and the purse / treasury split (3.6 step 7) and the guild XP
(3.6a: 10 % / 5 %, daily cap in base XP, the quest book after the cap).

Ledger contract cases of ``guild_order`` and of the lifted shop helpers live in ``econ_contract_cases.py`` and run in
all four econ services through ``test_econ_contract.py``; they are not repeated here.
"""

import itertools
from dataclasses import replace
from decimal import Decimal

import pytest

import econ_core as core
import econ_guild as g
from econ_sim import SimParams

P = SimParams()


def shortage(stock, norm=100, *, mult=1.0, base=5, food=False, inbound=0.0, code="wood"):
    return g.GroupShortage(group_code=code, stock=float(stock), norm_stock=float(norm), price_mult=float(mult),
                           base_price=float(base), is_food=food, inbound=float(inbound))


def plan(group, *, params=P, budget=1000, food_budget=0):
    return g.plan_order(group, params, budget, food_budget)


# --------------------------------------------------------------------------------------------- defaults (3.4)

def test_default_params_match_the_design():
    assert (P.guild_enabled, P.guild_markup_pct, P.guild_open_threshold_pct, P.guild_min_order_value) == \
        (1, 20.0, 80.0, 50)
    assert (P.guild_purse_share, P.guild_treasury_food_share) == (0.25, 0.25)
    assert (P.guild_xp_per_mark, P.guild_xp_per_mark_merchant_items, P.guild_xp_daily_cap) == (0.1, 0.05, 200)


# --------------------------------------------------------------------------------------------- budgets

def test_budgets_are_floored_shares_of_purse_and_positive_treasury():
    assert g.budgets(1000, 400, P) == (250, 100)
    assert g.budgets(1003, 7, P) == (250, 1)                  # floor(250.75), floor(1.75)
    assert g.budgets(1000, -5000, P) == (250, 0)              # a negative treasury gives nothing
    assert g.budgets(-10, 400, P) == (0, 100)
    assert g.budgets(0, 0, P) == (0, 0)


def test_budgets_follow_the_shares_and_the_switch():
    params = replace(P, guild_purse_share=0.5, guild_treasury_food_share=0.0)
    assert g.budgets(1000, 400, params) == (500, 0)
    assert g.budgets(1000, 400, replace(P, guild_enabled=0)) == (0, 0)


def test_payable_rule():
    assert g.payable(False, 1, 0) is True
    assert g.payable(False, 0, 500) is False                  # the treasury tops up FOOD only
    assert g.payable(True, 0, 500) is True
    assert g.payable(True, 0, 0) is False


# --------------------------------------------------------------------------------------------- plan_orders (3.3)

def test_order_opens_below_threshold_and_fills_to_the_full_norm():
    p = plan(shortage(70))
    assert p.open is True and p.close_reason is None
    assert p.volume == 30.0                                    # norm - stock, not threshold - stock
    assert p.value == 150                                      # 30 x 5 x 1


def test_threshold_boundary_is_strict():
    assert plan(shortage(80)).open is False                    # covered == 80 % of norm -> no order
    assert plan(shortage(80)).close_reason == g.CLOSE_NO_SHORTAGE
    p = plan(shortage(79.999))
    assert p.open is True and p.volume == pytest.approx(20.001)
    assert p.value == 100                                      # floor(20.001 x 5)


def test_threshold_is_a_param():
    params = replace(P, guild_open_threshold_pct=50.0)
    assert plan(shortage(60), params=params).open is False
    assert plan(shortage(49), params=params).open is True
    assert plan(shortage(49), params=params).volume == 51.0    # still filled to the full norm


def test_inbound_caravans_count_for_the_open_check_and_the_volume():
    assert plan(shortage(60, inbound=25)).open is False        # 85 >= 80
    p = plan(shortage(60, inbound=10))
    assert p.open is True and p.volume == 30.0                 # 100 - 60 - 10
    assert plan(shortage(60, inbound=-50)).volume == 40.0      # negative inbound ignored


def test_min_order_value_uses_local_price_without_markup():
    group = shortage(70, mult=0.3)                             # value floor(30 x 5 x 0.3) = 45
    p = plan(group)
    assert (p.open, p.value, p.close_reason) == (False, 45, g.CLOSE_NO_SHORTAGE)
    assert plan(group, params=replace(P, guild_min_order_value=45)).open is True
    assert plan(group, params=replace(P, guild_min_order_value=46)).open is False


def test_norm_zero_and_switch_off_close_as_disabled():
    assert plan(shortage(0, norm=0)).close_reason == g.CLOSE_DISABLED
    p = plan(shortage(10), params=replace(P, guild_enabled=0))
    assert (p.open, p.close_reason) == (False, g.CLOSE_DISABLED)


def test_no_budget_closes_as_no_money_food_payable_via_treasury_only():
    assert plan(shortage(10), budget=0, food_budget=500).close_reason == g.CLOSE_NO_MONEY
    assert plan(shortage(10, food=True, code="food", base=2), budget=0, food_budget=500).open is True
    assert plan(shortage(10, food=True, code="food", base=2), budget=0, food_budget=0).close_reason == \
        g.CLOSE_NO_MONEY


def test_no_shortage_wins_over_no_money():
    assert plan(shortage(95), budget=0).close_reason == g.CLOSE_NO_SHORTAGE


def test_plan_orders_is_deterministic_and_keyed_by_group():
    groups = [shortage(10, code="wood"), shortage(95, code="ore_metal", base=10),
              shortage(5, code="food", base=2, food=True)]
    first = g.plan_orders(groups, P, 0, 300)
    second = g.plan_orders(list(reversed(groups)), P, 0, 300)
    assert first == second
    assert {k: (v.open, v.close_reason) for k, v in first.items()} == {
        "wood": (False, g.CLOSE_NO_MONEY), "ore_metal": (False, g.CLOSE_NO_SHORTAGE), "food": (True, None)}


# --------------------------------------------------------------------------------------------- unit_price (3.5)

def test_price_is_local_price_plus_markup_floored():
    p = g.unit_price(10, Decimal("1.5"), Decimal("20.00"), None, 0)
    assert (p.unit_price, p.offer, p.capped_by_merchants) == (18, 18, False)
    assert g.unit_price(7, Decimal("1.290"), Decimal("20.00"), None, 0).unit_price == 10    # floor(10.836)
    assert g.unit_price(10, 1, 0, None, 0).unit_price == 10                                  # markup 0


def test_ask_cap_applies_only_when_a_merchant_sells_the_item():
    p = g.unit_price(10, Decimal("1.5"), 20, 30, 0)            # cap floor(30 x 0.5) = 15 < 18
    assert (p.unit_price, p.offer, p.capped_by_merchants) == (15, 18, True)
    assert g.unit_price(10, Decimal("1.5"), 20, 31, 0).unit_price == 15     # floor(15.5)
    assert g.unit_price(10, Decimal("1.5"), 20, 100, 0).unit_price == 18    # cap above the offer: not binding


def test_best_bid_floor_wins_over_a_lower_offer():
    p = g.unit_price(10, Decimal("1.5"), 20, 30, 16)           # capped 15, a merchant pays 16 -> 16
    assert (p.unit_price, p.capped_by_merchants) == (16, True)
    p = g.unit_price(10, Decimal("1.5"), 20, None, 25)         # bid above even the offer
    assert (p.unit_price, p.offer, p.capped_by_merchants) == (25, 18, False)


def test_item_base_zero_or_tiny_ask_gives_zero_price():
    assert g.unit_price(0, 1, 20, None, 0).unit_price == 0
    assert g.unit_price(10, 1, 20, 1, 0).unit_price == 0       # floor(1 x 0.5) = 0 -> refused (not worth)
    assert g.unit_price(10, 1, 20, 1, 3).unit_price == 3       # ... unless a merchant buys it


def test_price_zero_item_valued_at_group_base():
    item_base = core.item_base_price(0, 5)                     # items.price 0 -> group base
    assert item_base == 5
    assert g.unit_price(item_base, 1, 20, None, 0).unit_price == 6


@pytest.mark.parametrize("item_base, mult, markup, ask, bid", list(itertools.product(
    (0, 1, 7, 10, 99, 1000), ("0.5", "1", "1.29", "3"), (0, 20, 200), (None, 1, 2, 13, 40, 2001), (0, 1, 9, 600))))
def test_price_never_below_bid_and_never_a_profit_loop(item_base, mult, markup, ask, bid):
    price = g.unit_price(item_base, Decimal(mult), markup, ask, bid).unit_price
    assert price >= bid                                         # «гильдия не платит меньше торговца»
    assert price >= 0
    offer = int((Decimal(item_base) * Decimal(mult) * (1 + Decimal(markup) / 100)).to_integral_value(
        rounding="ROUND_FLOOR"))
    if ask is not None:
        if bid <= core.ask_discount_floor(ask):
            # buying at max charisma (ceil(ask x 0.5)) and handing in never earns marks
            assert price <= core.discounted_ask(ask, 50)
            assert price <= core.ask_discount_floor(ask)
    else:
        assert price == max(bid, offer)


# --------------------------------------------------------------------------------------------- refusal (3.6)

def test_refusal_order_of_rules():
    assert g.refusal(None, False, True, True, 10) == g.REFUSE_OFF_MARKET     # no group first
    assert g.refusal("wood", True, True, False, 0) == g.REFUSE_OFF_MARKET    # scroll / recipe / legendary
    assert g.refusal("wood", False, True, False, 0) == g.REFUSE_QUEST
    assert g.refusal("wood", False, False, False, 0) == g.REFUSE_NO_ORDER
    assert g.refusal("wood", False, False, True, None) == g.REFUSE_NOT_WORTH
    assert g.refusal("wood", False, False, True, 0) == g.REFUSE_NOT_WORTH
    assert g.refusal("wood", False, False, True, -3) == g.REFUSE_NOT_WORTH
    assert g.refusal("wood", False, False, True, 1) is None


# --------------------------------------------------------------------------------------------- accept (3.6 step 7)

def test_accept_by_volume_last_piece_may_overshoot():
    a = g.accept(5, 10, 3, 7, 10_000, 0, False)                # ceil(10 / 3) = 4 pieces (12 units > 10)
    assert (a.accepted, a.by_volume, a.total, a.paid_purse, a.paid_treasury, a.limited_by) == \
        (4, 4, 28, 28, 0, g.LIMIT_VOLUME)
    a = g.accept(3, Decimal("0.001"), Decimal("2.5"), 7, 10_000, 0, False)   # an expensive piece fills a crumb
    assert (a.accepted, a.limited_by) == (1, g.LIMIT_VOLUME)


def test_accept_everything_when_nothing_limits():
    a = g.accept(3, 10, 1, 7, 10_000, 0, False)
    assert (a.accepted, a.total, a.limited_by) == (3, 21, None)


def test_accept_by_money_non_food_uses_purse_only():
    a = g.accept(5, 100, 1, 7, 20, 1000, False)                # floor(20 / 7) = 2; treasury ignored
    assert (a.accepted, a.by_money, a.total, a.paid_purse, a.paid_treasury, a.limited_by) == \
        (2, 2, 14, 14, 0, g.LIMIT_MONEY)


def test_accept_food_purse_first_then_treasury():
    a = g.accept(5, 100, 1, 7, 10, 20, True)                   # floor(30 / 7) = 4 -> 28 = 10 purse + 18 treasury
    assert (a.accepted, a.total, a.paid_purse, a.paid_treasury, a.limited_by) == (4, 28, 10, 18, g.LIMIT_MONEY)
    a = g.accept(1, 100, 1, 7, 50, 20, True)                   # the purse alone suffices
    assert (a.paid_purse, a.paid_treasury) == (7, 0)


def test_accept_zero_cases():
    assert g.accept(5, 100, 1, 7, 0, 0, False).accepted == 0
    assert g.accept(5, 100, 1, 7, 0, 0, False).limited_by == g.LIMIT_MONEY
    assert g.accept(5, 0, 1, 7, 100, 0, False).limited_by == g.LIMIT_VOLUME
    a = g.accept(0, 100, 1, 7, 100, 0, False)
    assert (a.accepted, a.total, a.limited_by) == (0, 0, None)
    assert g.accept(5, 100, 0, 7, 100, 0, False).accepted == 0     # units_per_item 0
    assert g.accept(5, 100, 1, 0, 100, 0, False).accepted == 0     # price 0


def test_accept_tie_reports_volume():
    a = g.accept(5, 2, 1, 10, 20, 0, False)                    # by_volume 2 == by_money 2
    assert (a.accepted, a.limited_by) == (2, g.LIMIT_VOLUME)


@pytest.mark.parametrize("qty, left, per, price, purse, treasury, food", list(itertools.product(
    (1, 3, 50), ("0.5", "7", "100"), ("0.2", "1", "2.5"), (1, 7, 40), (0, 13, 500), (0, 9, 300), (False, True))))
def test_accept_never_exceeds_the_budget(qty, left, per, price, purse, treasury, food):
    a = g.accept(qty, Decimal(left), Decimal(per), price, purse, treasury, food)
    assert 0 <= a.accepted <= qty
    assert a.total == a.accepted * price == a.paid_purse + a.paid_treasury
    assert a.paid_purse <= purse
    assert a.paid_treasury <= (treasury if food else 0)
    if a.accepted:
        # whole pieces only while the order still needs something: at most one piece overshoots
        assert Decimal(per) * (a.accepted - 1) < Decimal(left)


def test_max_accept_hint():
    assert g.max_accept(14, 120.25, 1.0, 7, 10_000, 0, False) == 14
    assert g.max_accept(20_000, 1_000_000, 1, 1, 10**9, 0, False) == g.MAX_QUANTITY
    assert g.max_accept(14, 3, 1, 7, 10_000, 0, False) == 3
    assert g.max_accept(14, 100, 1, 7, 20, 0, False) == 2
    assert g.max_accept(14, 100, 1, 7, 20, 50, True) == 10
    assert g.max_accept(0, 100, 1, 7, 20, 0, False) == 0


def test_floor3_and_round3():
    assert g.floor3(1.23456) == 1.234
    assert g.floor3(float("nan")) == 0.0 and g.floor3(float("inf")) == 0.0
    assert g.floor3("garbage") == 0.0
    assert g.round3("1.2345") == Decimal("1.235")
    assert g.round3(2) == Decimal("2.000")


# --------------------------------------------------------------------------------------------- guild XP (3.6a)

def test_xp_rates_ten_and_five_percent_floored():
    assert g.guild_xp(155, 0.1, 200, 0, 1.0) == g.GuildXp(15, 15, False)
    assert g.guild_xp(155, 0.05, 200, 0, 1.0) == g.GuildXp(7, 7, False)      # floor(7.75)
    assert g.guild_xp(9, 0.1, 200, 0, 1.0) == g.GuildXp(0, 0, False)         # below one XP
    assert g.guild_xp(100, 0.29, 200, 0, None).base == 29                    # Decimal maths, no 28.999…


def test_xp_daily_cap_reached_or_partly_left():
    assert g.guild_xp(155, 0.1, 200, 190, 1.0) == g.GuildXp(10, 10, True)
    assert g.guild_xp(155, 0.1, 200, 200, 1.0) == g.GuildXp(0, 0, True)
    assert g.guild_xp(155, 0.1, 200, 250, 1.0) == g.GuildXp(0, 0, True)      # over-used day: never negative
    assert g.guild_xp(100, 0.1, 200, 190, 1.0) == g.GuildXp(10, 10, False)   # exactly fits: not «capped»


def test_xp_cap_zero_turns_guild_xp_off():
    assert g.guild_xp(10_000, 0.1, 0, 0, 2.0) == g.GuildXp(0, 0, False)


def test_xp_book_multiplies_after_the_cap():
    assert g.guild_xp(155, 0.1, 200, 0, 1.5) == g.GuildXp(15, 22, False)     # int(15 x 1.5)
    assert g.guild_xp(155, 0.1, 200, 190, 2.0) == g.GuildXp(10, 20, True)    # cap counts base XP
    assert g.guild_xp(155, 0.1, 200, 0, None) == g.GuildXp(15, 15, False)
    # the same rule as crud.multiply_xp
    import crud
    assert crud.multiply_xp(15, 1.5) == g.guild_xp(155, 0.1, 200, 0, 1.5).granted
