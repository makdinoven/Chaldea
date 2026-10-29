"""NPC merchants' background trade (FEAT-183, section 3.4) — pure functions, no DB.

The tick runner (``econ_tick.py``) loads the living merchants of one region with their shop rows, converts them into
the dataclasses below and calls :func:`merchant_step` once per region, **after** the ``region_tick`` posting (prices
already recomputed, purse after tax / wages known). It then writes the new row stocks, applies the region stock deltas
and posts :attr:`MerchantStepResult.legs` as one ``merchant_trade`` operation. Everything here is deterministic and
side-effect free; inputs are never mutated.

Per merchant (ascending npc id), per on-market row (ascending row id; off-market rows are skipped):

1. **Residents buy** ``round_half_up(stock x min(resident_share x mult, resident_share_max))`` items (at most the
   row stock) at the market ask, capped by the region-wide purse budget ``floor(purse x purse_share)`` (shared by all
   merchants); the goods go to the region stock (``n x units``).
2. **Trade tax** on the merchant's takings: ``trade_tax(sold_value, tax_rate)`` -> region treasury.
3. **Restock** ``ceil(deficit x fill)`` toward ``restock_target`` (fill = the group's ``stock_g / norm_g``), capped by the
   group take budget (``take_share x stock_g`` at step start, shared by all merchants), by the region stock and by the
   cash left; the merchant pays the wholesale price to the residents' purse.
4. **Upkeep**: cash above ``cash_cap_mult x cash_target`` releases ``cash_release`` of the excess to the purse.

Money only moves purse <-> NPC and NPC -> region treasury (the ledger adds the country's share of the trade tax), so
the world invariant holds; no NPC balance, purse or region stock ever goes negative.
"""

import math
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Mapping, Optional, Sequence

import econ_core as core
from econ_sim import DEFAULT_PARAMS, GoodState, SimParams

# Float slack for the abstract (float) region stock vs. the integer item counts.
_UNITS_EPS = 1e-9


# --------------------------------------------------------------------------------------------- inputs

@dataclass(frozen=True)
class ShopRow:
    """One ``npc_shop_items`` row with its item resolved (``econ_core.effective_item_group``)."""

    row_id: int
    group: Optional[str]
    off_market: bool
    origin: str                      # core.SHOP_ORIGIN_ADMIN | core.SHOP_ORIGIN_PLAYER
    base_ask: int                    # row buy_price (admin base price at region multiplier 1)
    base_bid: int = 0                # row sell_price (not used by the background trade, kept for the runner)
    stock: Optional[int] = None      # NULL -> 0 for a living merchant
    restock_target: int = 0


@dataclass(frozen=True)
class MerchantIn:
    npc_id: int
    cash: int                        # NPC currency_balance (locked by the runner)
    rows: Sequence[ShopRow] = ()


@dataclass(frozen=True)
class MarketGood:
    """The part of an ``econ_region_goods`` row the merchants see (``econ_sim.GoodState`` fits as well)."""

    stock: float
    norm_stock: float
    price_mult: float


@dataclass(frozen=True)
class RegionMarket:
    region_id: int
    tax_rate: float                  # econ_regions.tax_rate
    purse: int                       # population purse balance after the region_tick posting
    goods: Mapping[str, object]      # group code -> MarketGood / econ_sim.GoodState (stock, norm_stock, price_mult)
    group_base: Mapping[str, float]  # group code -> econ_goods_groups.base_price


# --------------------------------------------------------------------------------------------- outputs

@dataclass
class RowResult:
    row_id: int
    stock_before: int
    stock_after: int
    sold: int = 0
    restocked: int = 0
    ask: int = 0
    wholesale: int = 0

    @property
    def changed(self) -> bool:
        return self.stock_after != self.stock_before


@dataclass
class MerchantResult:
    npc_id: int
    cash_before: int
    cash_after: int
    cash_target: int
    sold_items: int = 0
    sold_value: int = 0              # purse -> NPC
    tax: int = 0                     # NPC -> region treasury (trade_tax)
    restock_items: int = 0
    restock_value: int = 0           # NPC -> purse
    upkeep: int = 0                  # NPC -> purse
    rows: List[RowResult] = field(default_factory=list)

    def summary(self) -> Dict[str, int]:
        return {"sold_items": self.sold_items, "sold_value": self.sold_value, "tax": self.tax,
                "restock_items": self.restock_items, "restock_value": self.restock_value, "upkeep": self.upkeep}


@dataclass
class MerchantStepResult:
    region_id: int
    purse_before: int
    purse_after: int
    purse_budget: int                # floor(purse x merchant_purse_share)
    merchants: List[MerchantResult]
    stock_delta: Dict[str, float]    # group code -> change of the region stock (+ sold to residents, - restocked)
    stock_after: Dict[str, float]    # group code -> new region stock (only groups the merchants touched)
    legs: List[core.Leg]

    @property
    def new_row_stock(self) -> Dict[int, int]:
        """row id -> new stock for every row of the processed merchants (all rows, so the runner also turns a
        living merchant's NULL stock into a number; it may skip rows whose stored value already matches)."""
        result: Dict[int, int] = {}
        for merchant in self.merchants:
            for row in merchant.rows:
                result[row.row_id] = row.stock_after
        return result

    @property
    def sold_value(self) -> int:
        return sum(m.sold_value for m in self.merchants)

    @property
    def tax(self) -> int:
        return sum(m.tax for m in self.merchants)

    def metadata(self) -> Dict[str, Dict[str, Dict[str, int]]]:
        """``merchant_trade`` operation metadata: ``{"merchants": {"<npc_id>": {sold_items, …, upkeep}}}``."""
        return {"merchants": {str(m.npc_id): m.summary() for m in self.merchants}}


# --------------------------------------------------------------------------------------------- helpers

def _row_stock(row: ShopRow) -> int:
    return max(0, int(row.stock or 0))


def _restockable(row: ShopRow) -> bool:
    """Rows that count for the cash target: the admin assortment priced by the region."""
    return row.origin == core.SHOP_ORIGIN_ADMIN and not row.off_market and row.group is not None


def cash_target(rows: Sequence[ShopRow], params: SimParams = DEFAULT_PARAMS) -> int:
    """Merchant cash target (Q1): ``cash_target_mult x Σ restock_target x wholesale(base_ask, mult 1)`` over the
    on-market admin rows. Also the top-up target of the admin «Пополнить кассы торговцев»."""
    full_restock = sum(
        max(0, int(r.restock_target)) * core.wholesale_price(r.base_ask, 1, params.merchant_wholesale_share)
        for r in rows if _restockable(r)
    )
    return int(math.floor(full_restock * max(0.0, float(params.merchant_cash_target_mult))))


def upkeep_amount(cash: int, target: int, params: SimParams = DEFAULT_PARAMS) -> int:
    """Q4: cash above ``cash_cap_mult x target`` releases ``cash_release`` of the excess per tick.

    A merchant without a restockable assortment (target 0) keeps his cash — he has nothing to spend it on but
    player buy-backs, and draining it would make him refuse every player sale.
    """
    if target <= 0:
        return 0
    cap = int(math.floor(target * max(1.0, float(params.merchant_cash_cap_mult))))
    excess = int(cash) - cap
    if excess <= 0:
        return 0
    release = min(1.0, max(0.0, float(params.merchant_cash_release)))
    return int(math.floor(excess * release))


def _resident_share(mult: Decimal, params: SimParams) -> Decimal:
    share = Decimal(str(params.merchant_resident_share)) * mult
    cap = Decimal(str(params.merchant_resident_share_max))
    return max(Decimal(0), min(share, cap))


def merchant_legs(region_id: int, merchants: Sequence[MerchantResult]) -> List[core.Leg]:
    """Legs of the region's ``merchant_trade`` operation, per merchant in the given (ascending npc id) order:
    purse -> NPC (resident purchases), NPC -> region (``trade_tax``), NPC -> purse (restock), NPC -> purse (upkeep).
    Zero legs are omitted. The ledger adds the region -> country share of the trade tax."""
    purse = core.AccountRef.purse(region_id)
    region = core.AccountRef.region(region_id)
    legs: List[core.Leg] = []
    for m in merchants:
        npc = core.AccountRef.character(m.npc_id)
        for src, dst, amount, leg_type in (
            (purse, npc, m.sold_value, core.LEG_MAIN),
            (npc, region, m.tax, core.LEG_TRADE_TAX),
            (npc, purse, m.restock_value, core.LEG_MAIN),
            (npc, purse, m.upkeep, core.LEG_MAIN),
        ):
            if amount > 0:
                legs.append(core.Leg(src, dst, int(amount), leg_type))
    return legs


# --------------------------------------------------------------------------------------------- the step

def merchant_step(
    market: RegionMarket,
    merchants: Sequence[MerchantIn],
    params: SimParams = DEFAULT_PARAMS,
) -> MerchantStepResult:
    """One background-trade step of all living merchants of one region (3.4). Inputs are not mutated."""
    region_id = int(market.region_id)
    purse_before = max(0, int(market.purse))
    purse_budget = int(math.floor(purse_before * min(1.0, max(0.0, float(params.merchant_purse_share)))))
    budget_left = purse_budget
    take_share = min(1.0, max(0.0, float(params.merchant_take_share)))

    mults = {code: getattr(g, "price_mult", 1.0) for code, g in market.goods.items()}
    region_stock: Dict[str, float] = {code: max(0.0, float(g.stock)) for code, g in market.goods.items()}
    norms: Dict[str, float] = {code: max(0.0, float(g.norm_stock)) for code, g in market.goods.items()}
    take_left: Dict[str, float] = {code: s * take_share for code, s in region_stock.items()}
    start_stock = dict(region_stock)
    touched = set()

    results: List[MerchantResult] = []
    for merchant in sorted(merchants, key=lambda m: int(m.npc_id)):
        cash = max(0, int(merchant.cash))
        rows = sorted(merchant.rows, key=lambda r: int(r.row_id))
        target = cash_target(rows, params)
        res = MerchantResult(npc_id=int(merchant.npc_id), cash_before=cash, cash_after=cash, cash_target=target)

        # Per row: (row, result, mult, units) — None for rows that cannot trade with the region.
        trading = []
        for row in rows:
            stock = _row_stock(row)
            row_res = RowResult(row_id=int(row.row_id), stock_before=stock, stock_after=stock)
            res.rows.append(row_res)
            if row.off_market or row.group is None or row.group not in region_stock:
                continue
            units = core.units_per_item(row.base_ask, market.group_base.get(row.group, 0))
            if units <= 0:
                continue
            mult = core.market_mult(True, row.group, False, mults)
            row_res.ask = core.market_ask(row.base_ask, mult)
            row_res.wholesale = core.wholesale_price(row.base_ask, mult, params.merchant_wholesale_share)
            trading.append((row, row_res, mult, units))

        # 1. residents buy
        for row, row_res, mult, units in trading:
            stock = row_res.stock_after
            # round half up (not floor): a small row (stock 3-5) still sells now and then (FEAT-183 B5 fix)
            n = int((Decimal(stock) * _resident_share(mult, params)).to_integral_value(rounding=ROUND_HALF_UP))
            n = min(n, stock, budget_left // row_res.ask)
            if n <= 0:
                continue
            value = n * row_res.ask
            budget_left -= value
            row_res.sold = n
            row_res.stock_after = stock - n
            region_stock[row.group] += n * units
            touched.add(row.group)
            res.sold_items += n
            res.sold_value += value

        # 2. trade tax on the takings
        res.tax = core.trade_tax(res.sold_value, market.tax_rate)
        cash_left = cash + res.sold_value - res.tax

        # 3. restock from the region
        for row, row_res, mult, units in trading:
            want = max(0, int(row.restock_target) - row_res.stock_after)
            if want <= 0:
                continue
            g = row.group
            norm = norms.get(g, 0.0)
            fill = 1.0 if norm <= 0 else min(1.0, max(0.0, region_stock[g] / norm))
            # ceil (not floor): a deficit of 1 is refilled while the group has any stock (FEAT-183 B5 fix)
            n = max(0, int(math.ceil(want * fill - _UNITS_EPS)))
            by_take = int(math.floor(take_left[g] / units + _UNITS_EPS))
            by_stock = int(math.floor(region_stock[g] / units + _UNITS_EPS))
            n = min(n, by_take, by_stock, cash_left // row_res.wholesale)
            if n <= 0:
                continue
            value = n * row_res.wholesale
            cash_left -= value
            taken = n * units
            take_left[g] = max(0.0, take_left[g] - taken)
            region_stock[g] = max(0.0, region_stock[g] - taken)
            touched.add(g)
            row_res.restocked = n
            row_res.stock_after += n
            res.restock_items += n
            res.restock_value += value

        # 4. upkeep (surplus cash to the residents)
        res.upkeep = upkeep_amount(cash_left, target, params)
        res.cash_after = cash_left - res.upkeep
        results.append(res)

    purse_after = purse_before + sum(m.restock_value + m.upkeep - m.sold_value for m in results)
    stock_after = {g: region_stock[g] for g in sorted(touched)}
    stock_delta = {g: region_stock[g] - start_stock[g] for g in sorted(touched)}
    return MerchantStepResult(
        region_id=region_id, purse_before=purse_before, purse_after=purse_after, purse_budget=purse_budget,
        merchants=results, stock_delta=stock_delta, stock_after=stock_after,
        legs=merchant_legs(region_id, results),
    )


def market_from_sim(region_id: int, tax_rate: float, purse: int, goods: Mapping[str, GoodState],
                    group_base: Mapping[str, float]) -> RegionMarket:
    """Convenience for the runner: a RegionMarket over the goods returned by ``econ_sim.simulate_region``."""
    return RegionMarket(region_id=int(region_id), tax_rate=float(tax_rate), purse=int(purse),
                        goods={code: MarketGood(float(g.stock), float(g.norm_stock), float(g.price_mult))
                               for code, g in goods.items()},
                        group_base=dict(group_base))
