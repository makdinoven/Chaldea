"""NPC caravans (FEAT-192, sections 3.3 / 3.5 / 3.6) — pure functions, no DB, no clock, no RNG.

The tick pass (``econ_tick._caravan_pass`` via ``economy_caravan_crud``) loads a snapshot of the participating
regions, calls :func:`plan_caravans` once per run and executes every :class:`CaravanPlan` in its own transaction,
re-clamping it against the locked rows with :func:`clamp_dispatch`.

Rules (user decisions, section 1 of the feature file):
* inside a country caravans always run (no duty, ``caravan_travel_domestic`` recounts on the road); between two
  countries only when the admin enabled the pair (duty ``duty_pct`` on top, ``caravan_travel_foreign`` recounts);
* a seller ships at most ``caravan_surplus_share`` of its surplus above the norm per group per recount and always
  keeps at least the norm; a buyer receives at most up to its norm, counting goods already on the road;
* the buyer's residents pay (``caravan_purse_share`` of the purse per recount, all groups together); food may be
  topped up from the buyer's region treasury (``caravan_treasury_food_share`` of its positive balance);
* signal = ``stock / norm_stock`` (event price mods never trigger shipments); price = the seller's stored market
  price ``base_price x price_mult``.

Money is int (floored), units are 3-decimal floats (``econ_region_goods.stock`` is DECIMAL(16,3)).
"""

from dataclasses import dataclass, field, replace
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Dict, List, Mapping, Optional, Tuple

from econ_sim import GroupDef, SimParams

_THOUSANDTH = Decimal("0.001")
_PRICE_STEP = Decimal("0.0001")      # econ_caravans.unit_price DECIMAL(14,4)
_HUNDRED = Decimal(100)


# --------------------------------------------------------------------------------------------- value objects

@dataclass(frozen=True)
class GoodMarket:
    """One group of one region as the planner sees it (live stock, previous-run norm / price)."""

    stock: float
    norm_stock: float
    price_mult: float


@dataclass(frozen=True)
class RegionMarket:
    """A participating region that has not ticked in this run yet."""

    region_id: int
    country_id: int
    halted: bool = False                       # «Набег» / «Бунт» (merchants_halt): no exports, imports allowed
    purse: int = 0                             # population purse balance
    treasury: int = 0                          # region treasury balance (may be negative)
    goods: Mapping[str, GoodMarket] = field(default_factory=dict)


@dataclass(frozen=True)
class PairRule:
    """Trade permission of two countries (normalised ``country_a < country_b``)."""

    country_a: int
    country_b: int
    is_enabled: bool
    duty_pct: float


@dataclass(frozen=True)
class Route:
    travel_runs: int
    duty_pct: float


@dataclass(frozen=True)
class CaravanPlan:
    """One caravan to dispatch. ``paid_purse + paid_treasury == value + duty``."""

    from_region_id: int
    to_region_id: int
    from_country_id: int
    to_country_id: int
    group_code: str
    is_food: bool
    units: float
    unit_price: float
    value: int
    duty: int
    duty_pct: float
    travel_runs: int
    paid_purse: int
    paid_treasury: int

    @property
    def cost(self) -> int:
        return self.value + self.duty


# --------------------------------------------------------------------------------------------- helpers

def _dec(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def floor3(value) -> float:
    """Round down to 3 decimals (units); NaN / inf / garbage -> 0."""
    try:
        dec = _dec(value)
    except Exception:
        return 0.0
    if not dec.is_finite():
        return 0.0
    return float(dec.quantize(_THOUSANDTH, rounding=ROUND_FLOOR))


def pair_key(country_a: int, country_b: int) -> Tuple[int, int]:
    """Normalised pair key ``(min, max)``."""
    a, b = int(country_a), int(country_b)
    return (a, b) if a < b else (b, a)


def unit_price(base_price, price_mult) -> float:
    """The agreed price of one unit: ``base_price x seller.price_mult`` rounded to 4 decimals."""
    price = _dec(base_price) * _dec(price_mult)
    if price <= 0:
        return 0.0
    return float(price.quantize(_PRICE_STEP, rounding=ROUND_HALF_UP))


def route(from_country: Optional[int], to_country: Optional[int], pairs: Mapping[Tuple[int, int], PairRule],
          params: SimParams) -> Optional[Route]:
    """Same country -> domestic route without duty; an enabled pair -> foreign route with its duty; else None."""
    if from_country is None or to_country is None:
        return None
    if int(from_country) == int(to_country):
        return Route(max(1, int(params.caravan_travel_domestic)), 0.0)
    rule = pairs.get(pair_key(from_country, to_country))
    if rule is None or not rule.is_enabled:
        return None
    return Route(max(1, int(params.caravan_travel_foreign)), float(rule.duty_pct))


def price_caravan(units, price, duty_pct) -> Tuple[int, int]:
    """``value = floor(units x price)``, ``duty = floor(value x duty_pct / 100)``; both >= 0."""
    units_d, price_d, pct = _dec(units), _dec(price), _dec(duty_pct)
    if units_d <= 0 or price_d <= 0:
        return 0, 0
    value = int((units_d * price_d).to_integral_value(rounding=ROUND_FLOOR))
    duty = int((_dec(value) * max(pct, Decimal(0)) / _HUNDRED).to_integral_value(rounding=ROUND_FLOOR))
    return max(0, value), max(0, duty)


def affordable_units(budget, price, duty_pct) -> float:
    """The most units a budget pays for, price and duty included: ``floor3(budget / (price x (1 + duty%)))``.

    ``price_caravan`` of the result never exceeds the budget (both parts are floored).
    """
    budget_d, price_d = _dec(budget), _dec(price)
    if budget_d <= 0 or price_d <= 0:
        return 0.0
    factor = price_d * (Decimal(1) + max(_dec(duty_pct), Decimal(0)) / _HUNDRED)
    return floor3(budget_d / factor)


def split_payment(cost: int, purse_left: int, treasury_left: int, is_food: bool) -> Optional[Tuple[int, int]]:
    """Who pays ``cost``: the purse first, the region treasury tops up **food only**.

    Returns ``(paid_purse, paid_treasury)`` or None when the budgets cannot cover the cost.
    """
    cost = int(cost)
    if cost <= 0:
        return 0, 0
    paid_purse = min(cost, max(0, int(purse_left)))
    rest = cost - paid_purse
    if rest <= 0:
        return paid_purse, 0
    if not is_food or rest > max(0, int(treasury_left)):
        return None
    return paid_purse, rest


# --------------------------------------------------------------------------------------------- planning

def _group_order(groups: Mapping[str, GroupDef]) -> List[GroupDef]:
    """Food first (it may use the treasury), then by code."""
    return sorted(groups.values(), key=lambda g: (0 if g.is_food else 1, g.code))


def plan_caravans(
    markets: Mapping[int, RegionMarket],
    groups: Mapping[str, GroupDef],
    inbound: Mapping[Tuple[int, str], float],
    pairs: Mapping[Tuple[int, int], PairRule],
    params: SimParams,
) -> List[CaravanPlan]:
    """Match surplus regions with deficit regions (3.5). Deterministic: same input -> same plan."""
    if not int(params.caravans_enabled):
        return []
    max_count = max(0, int(params.caravan_max_per_run))
    min_value = max(1, int(params.caravan_min_value))
    surplus_share = _dec(params.caravan_surplus_share)
    purse_share = _dec(params.caravan_purse_share)
    treasury_share = _dec(params.caravan_treasury_food_share)

    purse_left: Dict[int, int] = {}
    treasury_left: Dict[int, int] = {}
    for rid, market in markets.items():
        purse_left[rid] = int((_dec(max(0, int(market.purse))) * purse_share).to_integral_value(rounding=ROUND_FLOOR))
        treasury_left[rid] = int((_dec(max(0, int(market.treasury))) * treasury_share)
                                 .to_integral_value(rounding=ROUND_FLOOR))

    plans: List[CaravanPlan] = []
    if max_count <= 0:
        return plans
    region_ids = sorted(markets)

    for group in _group_order(groups):
        code = group.code
        supply: Dict[int, float] = {}
        prices: Dict[int, float] = {}
        need: Dict[int, float] = {}
        level: Dict[int, float] = {}
        for rid in region_ids:
            market = markets[rid]
            good = market.goods.get(code)
            if good is None or good.norm_stock <= 0:
                continue
            stock, norm = float(good.stock), float(good.norm_stock)
            if stock > norm and not market.halted:
                amount = floor3(surplus_share * (_dec(stock) - _dec(norm)))
                if amount > 0:
                    supply[rid] = amount
                    prices[rid] = unit_price(group.base_price, good.price_mult)
            on_road = float(inbound.get((rid, code), 0.0) or 0.0)
            gap = floor3(_dec(norm) - _dec(stock) - _dec(on_road))
            if gap > 0:
                need[rid] = gap
                level[rid] = (stock + on_road) / norm
        if not supply or not need:
            continue

        for buyer_id in sorted(need, key=lambda r: (level[r], r)):
            buyer = markets[buyer_id]
            candidates = []
            for seller_id, amount in supply.items():
                if seller_id == buyer_id or amount <= 0 or prices.get(seller_id, 0) <= 0:
                    continue
                way = route(markets[seller_id].country_id, buyer.country_id, pairs, params)
                if way is None:
                    continue
                candidates.append((way.travel_runs, prices[seller_id], seller_id, way))
            candidates.sort(key=lambda c: (c[0], c[1], c[2]))

            for _travel, price, seller_id, way in candidates:
                if len(plans) >= max_count:
                    return plans
                if supply[seller_id] <= 0:
                    continue
                want = min(need[buyer_id], supply[seller_id])
                budget = purse_left[buyer_id] + (treasury_left[buyer_id] if group.is_food else 0)
                units = min(want, affordable_units(budget, price, way.duty_pct))
                value, duty = price_caravan(units, price, way.duty_pct)
                if units <= 0 or value < min_value:
                    continue
                parts = split_payment(value + duty, purse_left[buyer_id], treasury_left[buyer_id], group.is_food)
                if parts is None:       # cannot happen (affordable_units), kept as a guard
                    continue
                paid_purse, paid_treasury = parts
                purse_left[buyer_id] -= paid_purse
                treasury_left[buyer_id] -= paid_treasury
                supply[seller_id] = floor3(_dec(supply[seller_id]) - _dec(units))
                need[buyer_id] = floor3(_dec(need[buyer_id]) - _dec(units))
                seller = markets[seller_id]
                plans.append(CaravanPlan(
                    from_region_id=seller_id, to_region_id=buyer_id, from_country_id=int(seller.country_id),
                    to_country_id=int(buyer.country_id), group_code=code, is_food=bool(group.is_food),
                    units=units, unit_price=price, value=value, duty=duty, duty_pct=float(way.duty_pct),
                    travel_runs=int(way.travel_runs), paid_purse=paid_purse, paid_treasury=paid_treasury,
                ))
                left = purse_left[buyer_id] + (treasury_left[buyer_id] if group.is_food else 0)
                if need[buyer_id] <= 0 or left <= 0:
                    break
    return plans


# --------------------------------------------------------------------------------------------- execution clamp

def clamp_dispatch(plan: CaravanPlan, seller_stock, seller_norm, purse_balance, treasury_balance, *,
                   min_value: int = 1) -> Optional[CaravanPlan]:
    """Re-check a plan against the locked rows (3.7 step 3); None = do not send.

    * units <= plan units and <= ``stock - norm`` (the seller keeps at least its norm);
    * the purse pays at most ``min(plan.paid_purse, purse balance)``, the treasury at most
      ``min(plan.paid_treasury, positive treasury)`` (food only) — so a caravan never spends more than planned
      and ``InsufficientFunds`` cannot happen;
    * value / duty / parts recomputed with the plan's price and duty; below ``min_value`` -> None.
    """
    room = floor3(_dec(seller_stock) - _dec(seller_norm))
    units = min(float(plan.units), room)
    if units <= 0:
        return None
    purse_cap = max(0, min(int(plan.paid_purse), int(purse_balance or 0)))
    treasury_cap = max(0, min(int(plan.paid_treasury), int(treasury_balance or 0))) if plan.is_food else 0
    units = min(units, affordable_units(purse_cap + treasury_cap, plan.unit_price, plan.duty_pct))
    value, duty = price_caravan(units, plan.unit_price, plan.duty_pct)
    if units <= 0 or value < max(1, int(min_value)):
        return None
    parts = split_payment(value + duty, purse_cap, treasury_cap, plan.is_food)
    if parts is None:
        return None
    return replace(plan, units=units, value=value, duty=duty, paid_purse=parts[0], paid_treasury=parts[1])
