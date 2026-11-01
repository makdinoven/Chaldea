"""Guild orders (FEAT-193, sections 3.3 / 3.5 / 3.6 / 3.6a) — pure functions, no DB, no clock, no RNG.

* :func:`budgets` / :func:`plan_orders` — the region step (``econ_tick._process_region`` via
  ``economy_guild_crud.guild_step``) fixes the guild's per-recount allowance and decides, per goods group, whether an
  order is open and how big it is;
* :func:`unit_price` — what the guild pays per piece: the local price plus the markup, never above
  ``floor(cheapest ask x 0.5)`` of an item a merchant of the region sells, never below the best merchant bid;
* :func:`refusal` — why an item is not accepted (first failing rule);
* :func:`accept` — how many pieces are taken (whole pieces while the order still needs anything, the last one may
  overshoot; bounded by the money) and who pays (purse first, the treasury tops up food only);
* :func:`guild_xp` — XP for a hand-in (10 % / 5 % of the marks, daily cap in base XP, the quest XP book after it).

Money is int (floored), units are 3-decimal floats (``econ_region_goods.stock`` is DECIMAL(16,3)).
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Dict, Iterable, Optional, Tuple

import econ_core as core
from econ_caravan import split_payment
from econ_sim import SimParams

_THOUSANDTH = Decimal("0.001")
_HUNDRED = Decimal(100)

# econ_guild_orders.status
STATUS_OPEN = "open"
STATUS_FILLED = "filled"
STATUS_CLOSED = "closed"
ORDER_STATUSES = (STATUS_OPEN, STATUS_FILLED, STATUS_CLOSED)

# econ_guild_orders.close_reason
CLOSE_FILLED = "filled"
CLOSE_NO_SHORTAGE = "no_shortage"
CLOSE_NO_MONEY = "no_money"
CLOSE_DISABLED = "disabled"
CLOSE_REGION_LEFT = "region_left"

# refusal codes (economy_guild_crud maps them to Russian texts)
REFUSE_OFF_MARKET = "off_market"          # no group / scroll / recipe / legendary+ / admin off-market override
REFUSE_QUEST = "quest"                    # a collect / deliver quest objective
REFUSE_NO_ORDER = "no_order"              # no open order for the item's group in this region
REFUSE_NOT_WORTH = "not_worth"            # unit price <= 0

# why fewer pieces than requested were accepted
LIMIT_VOLUME = "volume"
LIMIT_MONEY = "money"

MAX_QUANTITY = 10_000                     # one request / one offer row


def _dec(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def floor3(value) -> float:
    """Round down to 3 decimals; NaN / inf / garbage -> 0."""
    try:
        dec = _dec(value)
    except Exception:
        return 0.0
    if not dec.is_finite():
        return 0.0
    return float(dec.quantize(_THOUSANDTH, rounding=ROUND_FLOOR))


def round3(value) -> Decimal:
    """Half-up to 3 decimals (DECIMAL(16,3) columns)."""
    return _dec(value).quantize(_THOUSANDTH, rounding=ROUND_HALF_UP)


def _floor(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


# --------------------------------------------------------------------------------------------- recount (3.3 / 3.4)

@dataclass(frozen=True)
class GroupShortage:
    """One goods group of a region as the guild step sees it (final stock of the step)."""

    group_code: str
    stock: float
    norm_stock: float
    price_mult: float
    base_price: float
    is_food: bool
    inbound: float = 0.0                    # caravans on the road to this region (units)


@dataclass(frozen=True)
class OrderPlan:
    """Decision for one group: open (with ``volume`` units) or closed with ``close_reason``."""

    group_code: str
    open: bool
    volume: float = 0.0
    value: int = 0                          # volume x base x mult (marks at the local price, no markup)
    close_reason: Optional[str] = None


def budgets(purse: int, treasury: int, params: SimParams) -> Tuple[int, int]:
    """The guild's allowance for one recount: ``(floor(max(0, purse) x purse_share),
    floor(max(0, treasury) x treasury_food_share))``; both 0 when the guild is disabled."""
    if not int(params.guild_enabled):
        return 0, 0
    budget = _floor(_dec(max(0, int(purse))) * _dec(params.guild_purse_share))
    food_budget = _floor(_dec(max(0, int(treasury))) * _dec(params.guild_treasury_food_share))
    return max(0, budget), max(0, food_budget)


def payable(is_food: bool, budget: int, food_budget: int) -> bool:
    """Some budget exists for the group: the purse share, plus the treasury share for food."""
    if int(budget) > 0:
        return True
    return bool(is_food) and int(budget) + int(food_budget) > 0


def plan_order(group: GroupShortage, params: SimParams, budget: int, food_budget: int) -> OrderPlan:
    """Open iff enabled, norm > 0, stock + inbound < threshold, value >= min value and payable (3.3)."""
    code = group.group_code
    norm = _dec(group.norm_stock)
    if not int(params.guild_enabled) or norm <= 0:
        return OrderPlan(code, False, close_reason=CLOSE_DISABLED)
    covered = _dec(group.stock) + max(_dec(group.inbound), Decimal(0))
    threshold = norm * _dec(params.guild_open_threshold_pct) / _HUNDRED
    volume = floor3(norm - covered)
    value = _floor(_dec(volume) * _dec(group.base_price) * _dec(group.price_mult)) if volume > 0 else 0
    if covered >= threshold or volume <= 0 or value < int(params.guild_min_order_value):
        return OrderPlan(code, False, volume, value, CLOSE_NO_SHORTAGE)
    if not payable(group.is_food, budget, food_budget):
        return OrderPlan(code, False, volume, value, CLOSE_NO_MONEY)
    return OrderPlan(code, True, volume, value)


def plan_orders(groups: Iterable[GroupShortage], params: SimParams, budget: int,
                food_budget: int) -> Dict[str, OrderPlan]:
    """{group_code: OrderPlan} for every group of the region (deterministic, no hysteresis)."""
    return {g.group_code: plan_order(g, params, budget, food_budget) for g in groups}


# --------------------------------------------------------------------------------------------- price (3.5)

@dataclass(frozen=True)
class Price:
    unit_price: int
    offer: int                              # local price + markup before the merchant cap
    capped_by_merchants: bool               # the merchant ask cap lowered the price below `offer`


def unit_price(item_base: int, price_mult, markup_pct, cheapest_ask: Optional[int], best_bid: int) -> Price:
    """``max(best_bid, min(floor(item_base x mult x (1 + markup%)), floor(cheapest_ask x 0.5)))``; the ask cap
    applies only when a merchant of the region sells the item (``cheapest_ask`` not None)."""
    offer = _floor(_dec(max(0, int(item_base))) * _dec(price_mult) * (Decimal(1) + _dec(markup_pct) / _HUNDRED))
    offer = max(0, offer)
    capped = offer
    if cheapest_ask is not None:
        capped = min(offer, max(0, core.ask_discount_floor(cheapest_ask)))
    price = max(max(0, int(best_bid or 0)), capped)
    return Price(unit_price=price, offer=offer, capped_by_merchants=price < offer)


def refusal(group: Optional[str], off_market: bool, is_quest: bool, has_open_order: bool,
            price: Optional[int]) -> Optional[str]:
    """First failing rule (3.6): off-market / no group -> quest item -> no open order -> price <= 0; None = OK.
    ``price`` may be None when the order check already failed (not computed)."""
    if group is None or off_market:
        return REFUSE_OFF_MARKET
    if is_quest:
        return REFUSE_QUEST
    if not has_open_order:
        return REFUSE_NO_ORDER
    if price is None or int(price) <= 0:
        return REFUSE_NOT_WORTH
    return None


# --------------------------------------------------------------------------------------------- acceptance (3.6)

@dataclass(frozen=True)
class Acceptance:
    accepted: int
    total: int
    paid_purse: int
    paid_treasury: int
    by_volume: int
    by_money: int
    limited_by: Optional[str]               # None (all accepted) | volume | money


def pieces_by_volume(units_left, units_per_piece) -> int:
    """``ceil(units_left / units_per_piece)``: whole pieces while the order still needs anything."""
    left, per = _dec(units_left), _dec(units_per_piece)
    if left <= 0 or per <= 0:
        return 0
    return int((left / per).to_integral_value(rounding=ROUND_CEILING))


def pieces_by_money(price: int, purse_left: int, treasury_left: int, is_food: bool) -> int:
    """``floor((purse_left [+ treasury_left for food]) / price)``."""
    price = int(price)
    if price <= 0:
        return 0
    money = max(0, int(purse_left)) + (max(0, int(treasury_left)) if is_food else 0)
    return money // price


def max_accept(have: int, units_left, units_per_piece, price: int, purse_left: int, treasury_left: int,
               is_food: bool) -> int:
    """View hint: ``min(have, by_volume, by_money, MAX_QUANTITY)``."""
    return max(0, min(int(have), pieces_by_volume(units_left, units_per_piece),
                      pieces_by_money(price, purse_left, treasury_left, is_food), MAX_QUANTITY))


def accept(quantity: int, units_left, units_per_piece, price: int, purse_left: int, treasury_left: int,
           is_food: bool) -> Acceptance:
    """How many of ``quantity`` pieces the guild takes now and who pays (3.6 step 7). ``accepted = 0`` -> nothing."""
    quantity = max(0, int(quantity))
    by_volume = pieces_by_volume(units_left, units_per_piece)
    by_money = pieces_by_money(price, purse_left, treasury_left, is_food)
    accepted = min(quantity, by_volume, by_money)
    limited_by = None
    if accepted < quantity:
        limited_by = LIMIT_VOLUME if by_volume <= by_money else LIMIT_MONEY
    if accepted <= 0:
        return Acceptance(0, 0, 0, 0, by_volume, by_money, limited_by)
    total = accepted * int(price)
    split = split_payment(total, purse_left, treasury_left if is_food else 0, is_food)
    if split is None:                       # cannot happen: by_money bounds the total
        return Acceptance(0, 0, 0, 0, by_volume, by_money, LIMIT_MONEY)
    return Acceptance(accepted, total, split[0], split[1], by_volume, by_money, limited_by)


# --------------------------------------------------------------------------------------------- XP (3.6a)

@dataclass(frozen=True)
class GuildXp:
    base: int                               # base XP granted (counts against the daily cap)
    granted: int                            # base x quest XP book multiplier (floored)
    capped: bool                            # the daily cap cut the base XP


def guild_xp(total_marks: int, rate, daily_cap: int, used_today: int, multiplier: Optional[float]) -> GuildXp:
    """``base = min(floor(total x rate), max(0, cap - used))``; cap 0 = guild XP off (not «capped»);
    ``granted = int(base x multiplier)`` (crud.multiply_xp rule: the book applies after the cap)."""
    cap = int(daily_cap)
    if cap <= 0:
        return GuildXp(0, 0, False)
    raw = max(0, _floor(_dec(max(0, int(total_marks))) * _dec(rate)))
    left = max(0, cap - max(0, int(used_today)))
    base = min(raw, left)
    granted = base
    if base > 0 and multiplier is not None:
        granted = int(base * float(multiplier))
    return GuildXp(base, max(0, granted), base < raw)
