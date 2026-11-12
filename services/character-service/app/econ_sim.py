"""Living-regions simulation math (FEAT-182, section 3.4) — pure functions, no DB.

The tick runner (``econ_tick.py``) loads rows, converts them into the dataclasses below, calls
:func:`simulate_region` once per region and stores the result / posts the money legs. Everything here is
deterministic and side-effect free so it can be unit-tested without SQL.

Units: goods are "units", production / norms are given per 1000 inhabitants per day, one tick advances
``params.dt`` days (0.25 = 6 h). Money is integer gold (floored).

Population (FEAT-186): ``econ_regions.population`` / ``RegionState.population`` is the lore number (up to millions).
The math runs on the *simulated* population = lore / ``params.population_scale`` (:func:`sim_population`, default
scale 100). :func:`simulate_region` scales ``region.population`` itself; every other function that takes a
``population`` argument (``norm_stock``, ``demand_tick``, ``needs_cost_day``, ``starting_purse``, ``starting_goods``,
``household_demand_day``) expects the already scaled simulated population. :func:`country_grants` splits by the lore
numbers — proportions do not depend on the scale.

Card helpers (``food_state`` … ``region_card``) turn the stored state into the qualitative player card of
3.7 — no balances or raw numbers leave this module through them.
"""

import math
from dataclasses import dataclass, field, fields, replace
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import econ_classes
from econ_classes import ClassMix

FOOD_CODE = "food"

# Processing order of the default chains (3.4 step 3). Groups with inputs that are not listed here are
# processed after these, in the order they are given to the simulation.
PROCESSED_ORDER = ("weapons", "armor", "jewelry", "potions", "tools", "household")

# Card thresholds (3.7).
FOOD_TIGHT_HUNGER = 0.03
FOOD_HUNGER_HUNGER = 0.15
TREASURY_FULL_SHARE = 1.0
TREASURY_OK_SHARE = 0.4
STABILITY_CALM = 70.0
STABILITY_UNEASY = 45.0
STABILITY_UNREST = 25.0
PROSPERITY_RICH = 75.0
PROSPERITY_WEALTHY = 50.0
PROSPERITY_MODEST = 25.0
PRICE_LEVEL_LOW = 0.85
PRICE_LEVEL_NORMAL = 1.2
PRICE_LEVEL_HIGH = 1.8
GROUP_VERY_LOW = 0.6
GROUP_LOW = 0.85
GROUP_HIGH = 1.2
GROUP_VERY_HIGH = 1.8
SHORTAGE_MULT = 1.6
SURPLUS_MULT = 0.7
TREND_EPS = 0.03

PROSPERITY_FACTOR_FLOOR = 0.1
MIN_STOCK_RATIO = 0.01


# --------------------------------------------------------------------------------------------- params

@dataclass(frozen=True)
class SimParams:
    """Global simulation parameters (``econ_sim_settings.params``); defaults = 3.4."""

    dt: float = 0.25
    price_min: float = 0.5
    price_max: float = 3.0
    price_exponent: float = 0.631
    stock_cap_mult: float = 3.0
    prod_price_elasticity: float = 0.15
    prod_price_min: float = 0.85
    prod_price_max: float = 1.30
    full_stability: float = 60.0
    hunger_prod_penalty: float = 0.5
    afford_days: float = 1.0
    treasury_reserve_days: float = 7.0
    treasury_release_ticks: int = 8
    country_grant_share: float = 0.25
    purse_start_days: float = 7.0
    stab_base: float = 85.0
    stab_hunger_w: float = 100.0
    stab_goods_w: float = 15.0
    stab_free_tax: float = 0.12
    stab_tax_w: float = 200.0
    stab_debt_penalty: float = 10.0
    stab_rate_up: float = 0.08
    stab_rate_down: float = 0.25
    prosp_rate: float = 0.05
    # prosperity target weights (changed by B4: the 3.4 weights 0.45/0.25/0.15 with liq over 7 days put a balanced
    # region at ~80, so every region read as «богатый» and luxury demand ran ~1.5x the template norm)
    prosp_w_sat: float = 0.30
    prosp_w_liq: float = 0.40
    prosp_w_stab: float = 0.15
    prosp_hunger_w: float = 60.0
    prosp_liq_days: float = 14.0
    history_retention_days: int = 60
    # FEAT-183 NPC merchants (3.2): background trade step of econ_merchant. Not in the 028 migration seed —
    # missing keys of a stored params JSON fall back to these defaults.
    merchant_bid_share: float = 0.5           # = econ_core.DEFAULT_MERCHANT_BID_SHARE (locations reads it via econ_core)
    merchant_wholesale_share: float = 0.5     # restock price = market ask x share
    merchant_resident_share: float = 0.2      # residents buy share x price_mult of a row's stock per tick ...
    merchant_resident_share_max: float = 0.6  # ... capped at this share
    merchant_purse_share: float = 0.05        # at most this share of the purse is spent at merchants per tick
    merchant_take_share: float = 0.25         # merchants together take at most this share of a group's region stock
    merchant_cash_target_mult: float = 2.0    # cash target = mult x wholesale value of a full restock at x1 prices
    merchant_cash_cap_mult: float = 3.0       # upkeep starts above cap_mult x cash target ...
    merchant_cash_release: float = 0.25       # ... and releases this share of the excess per tick to the purse
    # FEAT-184 banks (3.5): rates per day, loan caps, fees, residents. Not in any migration seed either.
    bank_demand_rate_day: float = 0.001       # base demand-deposit rate (x the bank's deposit_rate_factor)
    bank_term_rate_day_7: float = 0.002       # base term rates (x factor, fixed at opening)
    bank_term_rate_day_14: float = 0.0025
    bank_term_rate_day_28: float = 0.003
    bank_loan_rate_day: float = 0.005         # loans of players and residents, fixed at issue
    bank_penalty_rate_day: float = 0.01       # added to the loan rate after due_at
    bank_debt_cap_mult: float = 2.0           # interest + penalties stop at principal x mult
    bank_loan_cap_base: int = 500             # loan cap = base + per_level x level
    bank_loan_cap_per_level: int = 250
    bank_min_amount: int = 10                 # minimum deposit / withdrawal / transfer / loan / repay
    bank_transfer_fee_rate: float = 0.02      # commission share (ceil) ...
    bank_transfer_fee_min: int = 1            # ... but at least this
    bank_start_capital: int = 20000           # taken from the region treasury at the first switch-on
    bank_reserve_ratio: float = 0.2           # share of residents' deposits never lent / never used for interest
    bank_rate_cover: float = 1.25             # the bank wants loan income >= cover x deposit cost
    bank_rate_factor_min: float = 0.2         # lowest deposit-rate factor
    bank_rate_smoothing: float = 0.25         # the factor moves this share toward its target per pass
    bank_resident_deposit_share: float = 0.2  # residents keep this share of their savings in the bank
    bank_resident_loan_share: float = 0.1     # residents' loan target as a share of the purse
    bank_resident_adjust: float = 0.25        # per 6 h residents move this share of the gap to their targets
    bank_profit_to_treasury_share: float = 1.0  # share of the bank's realized net interest income sent to the treasury
    # FEAT-186: the sim runs on lore population / scale (4 000 000 inhabitants -> 40 000 at 100). Not in a seed.
    population_scale: int = 100
    # FEAT-187 region events (3.5): frequency, stacking caps, spreading, riot clock. Not in a seed either.
    events_enabled: int = 1                   # 0 = no automatic starts (random / spread / chain / riot)
    event_rate_per_season: float = 1.0        # average random events per region per «season»
    event_season_days: float = 49.0           # real days of one «season» (calendar: season 39 + festival 10)
    event_max_active: int = 3                 # automatic starts skip a region with this many active events
    event_mult_min: float = 0.1               # clamp of a stacked multiplier ...
    event_mult_max: float = 3.0               # ... from both sides
    event_delta_max: float = 10.0             # cap of the summed stability / prosperity change per recount
    event_spread_max_depth: int = 2           # hops a spreading event may make (0 = no spreading)
    event_riot_stability: float = 25.0        # the riot clock runs while stability is below this
    event_riot_after_days: float = 3.0        # days of continuous low stability before a riot starts
    # FEAT-191 mint and season quota (3.5). Not in a seed; 0 = dormant until the admin sets the amounts.
    quota_season_amount: int = 0              # marks issued once per game season into participating region treasuries
    mint_season_limit: int = 0                # default per-country season limit (court + players); 0 = mint closed
    mint_court_marks_per_unit: float = 8.0    # marks per region unit of ore_metal taken by the court
    mint_court_threshold_pct: float = 100.0   # the court takes ore only above this % of the capital's norm_stock
    # FEAT-192 NPC caravans (3.10). Not in a seed either.
    caravans_enabled: int = 1                 # 0 = no new caravans (those on the road still arrive)
    caravan_surplus_share: float = 0.25       # share of a seller's surplus above norm that may leave per recount
    caravan_purse_share: float = 0.25         # share of a buyer's purse caravans may spend per recount (all goods)
    caravan_treasury_food_share: float = 0.5  # share of a buyer's positive treasury that may top up food per recount
    caravan_travel_domestic: int = 1          # recounts on the road inside a country
    caravan_travel_foreign: int = 2           # recounts on the road between countries
    caravan_min_value: int = 10               # smaller deals are not sent
    caravan_max_per_run: int = 200            # hard cap of dispatches per recount
    # FEAT-211 physical caravans and raids (3.14). Not in a seed either.
    caravan_physical_enabled: int = 1         # 0 = new caravans stay abstract (those on the road keep moving)
    caravan_physical_min_value: int = 1000    # «крупный» caravan: value (marks) from which it always goes by road
    caravan_physical_small_chance: float = 0.1  # chance that a smaller domestic caravan goes by road too
    caravan_physical_max_active: int = 30     # cap of physical caravans on the road at once
    caravan_step_minutes: int = 18            # minutes per location (±25 % jitter)
    caravan_route_max_steps: int = 40         # a longer shortest path = «no road»
    caravan_post_hold_max_min: int = 120      # max wait for a raid post (one window per caravan)
    caravan_raid_battle_max_hours: int = 48   # a raid battle running longer is ignored (no loot)
    caravan_raid_marks_share: float = 0.2     # share of the escrow money of a caravan taken by a won raid
    caravan_raid_goods_share: float = 0.3     # share of the units taken by a won raid (-> bales)
    caravan_guard_count_base: int = 2         # guards of a cheap caravan
    caravan_guard_value_per_extra: int = 1000  # +1 guard per this value
    caravan_guard_count_max: int = 5          # guard cap (battle team size)
    caravan_guard_mult_per_1000: float = 0.1  # guard stat multiplier growth per 1000 marks of value
    caravan_guard_mult_max: float = 2.0       # cap of the value part of the multiplier
    caravan_guard_mult_dangerous: float = 1.25  # extra factor on `dangerous` locations
    caravan_rep_trade_share: float = 0.5      # seller / buyer region reputation loss vs the raid region
    fence_purse_share: float = 0.1            # share of a region purse its fences may refill from per recount
    # FEAT-212 player escorts (3.4). Not in a seed either.
    caravan_departure_minutes: int = 45       # a new physical caravan stands at the seller gate this long (hire window)
    caravan_escort_seats: int = 3             # player escort seats per caravan; 0 = hiring off (<= 4 keeps >= 1 mob)
    caravan_escort_fee_share: float = 0.05    # escort pay pool = share of the seller's remaining proceeds
    caravan_escort_bonus_share: float = 0.03  # extra pool when the caravan's raid was repelled (same source)
    caravan_escort_defense_fame: int = 5      # fame per escort for a repelled raid (paid on delivery)
    # FEAT-193 guild orders (3.4). Not in a seed either.
    guild_enabled: int = 1                    # 0 = no orders (open ones close on the next recount)
    guild_markup_pct: float = 20.0            # markup over the local price
    guild_open_threshold_pct: float = 80.0    # an order exists only while stock (+ caravans on the road) < this % of norm
    guild_min_order_value: int = 50           # smaller shortages (marks at the local price) open no order
    guild_purse_share: float = 0.25           # share of the residents' purse the guild may spend per recount
    guild_treasury_food_share: float = 0.25   # share of the positive treasury that may top up food orders per recount
    guild_xp_per_mark: float = 0.1            # XP per mark paid for an item no merchant of the region sells
    guild_xp_per_mark_merchant_items: float = 0.05  # XP per mark paid for an item a merchant of the region sells
    guild_xp_daily_cap: int = 200             # max base guild XP per character per UTC day; 0 = guild XP off
    # FEAT-194 social classes and the wealth norm (3.14). Not in a seed either.
    classes_enabled: int = 1                  # 0 = the whole class layer off (pre-FEAT-194 math, norm = purse_start_days)
    class_norm_days_poor: float = 3.0         # wealth norm of a resident: days of his class's needs at base prices
    class_norm_days_middling: float = 7.0
    class_norm_days_rich: float = 21.0
    wealth_tax_rate: float = 0.02             # share of the purse excess above the norm taxed into the treasury
    class_tax_w_poor: float = 0.3             # income-tax weights (normalised to the template mix)
    class_tax_w_middling: float = 1.0
    class_tax_w_rich: float = 2.0
    class_stab_poor_threshold: float = 0.6    # poor share above which unrest starts
    class_stab_poor_w: float = 40.0           # stability points per 1.0 of poor share above the threshold
    class_stab_poor_hunger_w: float = 50.0    # extra stability loss per (poor share x poor hunger)
    class_stab_rich_free_tax: float = 0.12    # tax rate the rich accept
    class_stab_rich_tax_w: float = 100.0      # stability loss per (rich share x tax above that)
    mob_rate_up: float = 0.001                # max share of a class moving up per recount
    mob_rate_down: float = 0.0015             # max share moving down per recount
    mob_rich_factor: float = 0.5              # middling -> rich at this fraction of the poor -> middling rate
    mob_dead_zone: float = 0.1                # weaker mobility signals move nobody
    mob_w_prosperity: float = 0.4             # weights of the mobility signal
    mob_w_money: float = 0.4
    mob_w_stability: float = 0.2
    mob_w_hunger: float = 1.0
    class_share_min: float = 0.02             # mobility / events never push a share outside these bounds
    class_share_max: float = 0.90
    grant_deficit_share: float = 0.25         # share of the country grant pool split by the deficit below the norm

    @classmethod
    def from_mapping(cls, data: Optional[Mapping]) -> "SimParams":
        """Build from a (possibly partial) JSON dict; unknown keys are ignored, missing keys use defaults."""
        if not data:
            return cls()
        known = {f.name: f for f in fields(cls)}
        kwargs = {}
        for key, value in data.items():
            if key in known and value is not None:
                kwargs[key] = int(value) if known[key].type in (int, "int") else float(value)
        return cls(**kwargs)

    def to_dict(self) -> Dict[str, float]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


DEFAULT_PARAMS = SimParams()


# --------------------------------------------------------------------------------------------- inputs

@dataclass(frozen=True)
class GroupDef:
    """One goods group (``econ_goods_groups`` + its ``econ_group_inputs``)."""

    code: str
    name: str
    base_price: float
    norm_per_1000: float
    norm_days: float
    prosperity_elasticity: float = 0.0
    price_elasticity: float = 0.0
    is_food: bool = False
    inputs: Mapping[str, float] = field(default_factory=dict)  # input_code -> units of input per unit
    # FEAT-194: per-capita demand weights of the poor / middling / rich (normalised to the template mix)
    class_demand: Tuple[float, float, float] = (1.0, 1.0, 1.0)


@dataclass
class GoodState:
    """One ``econ_region_goods`` row."""

    group_code: str
    production_per_1000: float = 0.0
    consumption_mult: float = 1.0
    stock: float = 0.0
    norm_stock: float = 0.0
    price_mult: float = 1.0
    prev_price_mult: float = 1.0
    last_produced: float = 0.0
    last_consumed: float = 0.0
    last_demand: float = 0.0
    last_spoiled: float = 0.0


@dataclass
class RegionState:
    """The simulated part of one ``econ_regions`` row."""

    population: int     # lore number; the math uses sim_population(population, params)
    tax_rate: float
    stability: float = 70.0
    prosperity: float = 50.0
    hunger: float = 0.0
    satisfaction: float = 1.0
    treasury_target: int = 0
    # FEAT-194: live class mix (None = no classes) and the template default mix every factor is normalised to
    classes: Optional[ClassMix] = None
    class_base: Optional[ClassMix] = None


@dataclass(frozen=True)
class RegionModifiers:
    """Per-step levers of the active region events (FEAT-187 3.4), built by ``econ_events.aggregate``.

    Maps hold only the groups an event touches (missing group -> 1.0); ``production`` already includes the
    ``labor`` multiplier. All fields at their defaults = identity.
    """

    production: Mapping[str, float] = field(default_factory=dict)
    consumption: Mapping[str, float] = field(default_factory=dict)
    price: Mapping[str, float] = field(default_factory=dict)
    tax_income_mult: float = 1.0
    stability_delta: float = 0.0
    prosperity_delta: float = 0.0


@dataclass
class SimResult:
    region: RegionState
    goods: Dict[str, GoodState]
    income: int
    tax: int            # purse -> region treasury (the ledger adds the country leg on top of it)
    country_tax: int    # part of ``tax`` the ledger forwards region -> country
    grant: int          # country -> region treasury
    wages: int          # region treasury -> purse
    purse_after: int
    treasury_after: int
    needs_cost_day: float
    affordability: float
    # FEAT-194 (defaults keep every caller valid). ``tax`` stays the income tax.
    wealth_tax: int = 0                                     # purse -> treasury on top of ``tax`` (same ledger leg)
    wealth_norm: int = 0                                    # purse norm (no classes: starting_purse)
    class_hunger: Optional[Tuple[float, float, float]] = None
    class_afford: Optional[Tuple[float, float, float]] = None
    class_delta: Tuple[float, float] = (0.0, 0.0)           # (dpoor, drich) of this recount


# --------------------------------------------------------------------------------------------- helpers

def _clamp(value: float, lo: float, hi: float) -> float:
    if value != value:  # NaN guard
        return lo
    return max(lo, min(hi, value))


def _ordered_codes(groups: Mapping[str, GroupDef], goods: Mapping[str, GoodState]) -> List[str]:
    """Raw groups (no inputs) first, then processed ones in ``PROCESSED_ORDER``, then any other processed."""
    codes = [c for c in groups if c in goods]
    raw = [c for c in codes if not groups[c].inputs]
    processed = [c for c in PROCESSED_ORDER if c in codes and groups[c].inputs]
    processed += [c for c in codes if groups[c].inputs and c not in processed]
    return raw + processed


def price_mult(stock: float, norm: float, params: SimParams = DEFAULT_PARAMS) -> float:
    """Price multiplier from the stock / norm ratio (3.4 step 7). Norm 0 -> 1.0."""
    stock = float(stock)
    norm = float(norm)
    if norm <= 0:
        return 1.0
    ratio = max(stock / norm, MIN_STOCK_RATIO)
    return _clamp(ratio ** (-params.price_exponent), params.price_min, params.price_max)


def sim_population(population, params: SimParams = DEFAULT_PARAMS) -> float:
    """Simulated population of a region: lore ``population`` / ``params.population_scale`` (FEAT-186).

    Negative / missing population -> 0; the scale is floored at 1 (no division by zero). The result may be fractional
    (lore 50 at scale 100 -> 0.5: a tiny region, all formulas are linear in it). A lore population that is a multiple
    of the scale gives the exact float of the quotient, so a world migrated x100 at scale 100 computes bit-identically.
    """
    pop = max(0, int(population or 0))
    scale = max(1, int(params.population_scale))
    return pop / scale


def household_demand_day(group: GroupDef, consumption_mult: float, population: float) -> float:
    """Household consumption per day at prosperity 50 and price x1."""
    return float(group.norm_per_1000) * float(consumption_mult) * population / 1000.0


def norm_stock(
    code: str,
    groups: Mapping[str, GroupDef],
    goods: Mapping[str, GoodState],
    population: float,
    factors: Optional[Mapping[str, float]] = None,
) -> float:
    """Norm stock of ``code`` (3.4 step 6): norm_days x (household demand/day + input use of processing/day).

    ``factors`` (FEAT-194): class demand factor per group, multiplies the household part only (None = no classes)."""
    group = groups[code]
    good = goods.get(code)
    cmult = good.consumption_mult if good is not None else 1.0
    per_day = household_demand_day(group, cmult, population)
    if factors is not None:
        per_day *= float(factors.get(code, 1.0))
    pop_k = population / 1000.0
    for other_code, other in groups.items():
        ratio = other.inputs.get(code) if other.inputs else None
        if not ratio:
            continue
        other_good = goods.get(other_code)
        if other_good is None:
            continue
        per_day += float(other_good.production_per_1000) * pop_k * float(ratio)
    return float(group.norm_days) * per_day


def demand_tick(
    group: GroupDef,
    good: GoodState,
    population: float,
    prosperity: float,
    params: SimParams = DEFAULT_PARAMS,
    factor: Optional[float] = None,
) -> float:
    """Household demand of one group for one tick (3.4 step 4), at the current price.

    ``factor`` (FEAT-194): class demand factor of the group (None = no classes, the statement below unchanged)."""
    pop_k = population / 1000.0
    prosp_factor = max(PROSPERITY_FACTOR_FLOOR,
                       1.0 + float(group.prosperity_elasticity) * (float(prosperity) - 50.0) / 50.0)
    price_factor = max(float(good.price_mult), MIN_STOCK_RATIO) ** (-float(group.price_elasticity))
    demand = float(group.norm_per_1000) * float(good.consumption_mult) * pop_k * prosp_factor * price_factor * params.dt
    if factor is not None:
        demand *= float(factor)
    return demand


def needs_cost_day(
    groups: Mapping[str, GroupDef],
    goods: Mapping[str, GoodState],
    population: float,
    prosperity: float = 50.0,
    params: SimParams = DEFAULT_PARAMS,
    base_prices: bool = False,
    factors: Optional[Mapping[str, float]] = None,
) -> float:
    """Cost of one day of household demand. ``base_prices=True`` -> prices x1 (used by «Заполнить»).

    ``factors`` (FEAT-194): class demand factor per group (None = no classes)."""
    total = 0.0
    for code, good in goods.items():
        group = groups.get(code)
        if group is None:
            continue
        factor = factors.get(code, 1.0) if factors is not None else None
        if base_prices:
            probe = replace(good, price_mult=1.0)
            demand = demand_tick(group, probe, population, 50.0, params, factor) / params.dt
            total += demand * float(group.base_price)
        else:
            demand = demand_tick(group, good, population, prosperity, params, factor) / params.dt
            total += demand * float(group.base_price) * float(good.price_mult)
    return total


def starting_purse(
    groups: Mapping[str, GroupDef],
    goods: Mapping[str, GoodState],
    population: float,
    params: SimParams = DEFAULT_PARAMS,
    classes: Optional[ClassMix] = None,
    class_base: Optional[ClassMix] = None,
) -> int:
    """Purse target for «Заполнить регионы по шаблонам»: ``purse_start_days`` of needs at base prices.

    FEAT-194: with ``classes`` (and ``params.classes_enabled``) the target is the class wealth norm
    (:func:`econ_classes.wealth_norm`, normalised to ``class_base`` = the template mix; None -> ``classes``)."""
    if classes is not None and params.classes_enabled:
        return econ_classes.wealth_norm(groups, goods, population, classes, class_base or classes, params)[0]
    return int(math.floor(params.purse_start_days * needs_cost_day(groups, goods, population, params=params,
                                                                   base_prices=True)))


def class_factors(groups: Mapping[str, GroupDef], region: RegionState,
                  params: SimParams = DEFAULT_PARAMS) -> Optional[Dict[str, float]]:
    """FEAT-194: demand factor per group of a region with classes (None = classes off / no shares)."""
    if not params.classes_enabled or region.classes is None:
        return None
    return econ_classes.demand_factors(groups, region.classes, region.class_base or region.classes)


def region_wealth_norm(groups: Mapping[str, GroupDef], goods: Mapping[str, GoodState], region: RegionState,
                       params: SimParams = DEFAULT_PARAMS) -> int:
    """FEAT-194 (3.4): the purse norm of a region — class wealth norm, or ``starting_purse`` without classes."""
    pop = sim_population(region.population, params)
    if params.classes_enabled and region.classes is not None:
        return starting_purse(groups, goods, pop, params, region.classes, region.class_base)
    return starting_purse(groups, goods, pop, params)


def starting_goods(
    groups: Mapping[str, GroupDef],
    template_goods: Mapping[str, Tuple[float, float]],
    population: float,
    factors: Optional[Mapping[str, float]] = None,
) -> Dict[str, GoodState]:
    """Goods rows of a freshly applied template: stock = norm, prices x1.

    ``template_goods`` maps group code -> (production_per_1000, consumption_mult); ``factors`` (FEAT-194) = class
    demand factors of the region (None = no classes).
    """
    goods = {
        code: GoodState(group_code=code,
                        production_per_1000=float(template_goods.get(code, (0.0, 1.0))[0]),
                        consumption_mult=float(template_goods.get(code, (0.0, 1.0))[1]))
        for code in groups
    }
    for code, good in goods.items():
        good.norm_stock = norm_stock(code, groups, goods, population, factors)
        good.stock = good.norm_stock
    return goods


def template_production_per_1000(
    groups: Mapping[str, GroupDef],
    ratios: Mapping[str, float],
    cmults: Mapping[str, float],
) -> Dict[str, float]:
    """Seed rule of 3.4: production_per_1000 = ratio x need_per_1000 (rounded to 3 decimals).

    Finished groups: need = norm x cmult. Raw groups: need = norm x cmult + sum(finished production x input ratio).
    """
    result: Dict[str, float] = {}
    for code, group in groups.items():
        if group.inputs:
            need = float(group.norm_per_1000) * float(cmults.get(code, 1.0))
            result[code] = round(float(ratios.get(code, 1.0)) * need, 3)
    for code, group in groups.items():
        if group.inputs:
            continue
        need = float(group.norm_per_1000) * float(cmults.get(code, 1.0))
        for other_code, other in groups.items():
            ratio = other.inputs.get(code) if other.inputs else None
            if ratio:
                need += result.get(other_code, 0.0) * float(ratio)
        result[code] = round(float(ratios.get(code, 1.0)) * need, 3)
    return result


def wage_amount(net_tax: int, grant: int, treasury_before: int, treasury_target: int,
                params: SimParams = DEFAULT_PARAMS) -> int:
    """Wages rule (3.4 step 8). Never pushes a non-negative treasury below 0."""
    release_ticks = max(1, int(params.treasury_release_ticks))
    release = (int(treasury_before) - int(treasury_target)) // release_ticks
    return max(0, int(net_tax) + int(grant) + release)


def country_grants(country_balance: int, region_populations: Mapping[int, int],
                   params: SimParams = DEFAULT_PARAMS,
                   deficits: Optional[Mapping[int, int]] = None) -> Dict[int, int]:
    """Split ``country_grant_share`` of a country's positive balance between its simulated regions by population.

    Integer floor per region, so the sum never exceeds the granted pool.

    FEAT-194 (3.10): with ``deficits`` (money below the region norm) ``grant_deficit_share`` of the pool goes to the
    regions with a positive deficit ∝ deficit (each floored and capped at its deficit), the rest by population.
    Nobody below the norm -> the whole pool by population. ``deficits=None`` -> the statement above, unchanged.
    """
    pool = int(math.floor(max(0, int(country_balance)) * params.country_grant_share))
    total_pop = sum(max(0, int(p)) for p in region_populations.values())
    if pool <= 0 or total_pop <= 0:
        return {rid: 0 for rid in region_populations}
    if deficits is None:
        return {rid: pool * max(0, int(p)) // total_pop for rid, p in region_populations.items()}
    grants = {rid: 0 for rid in region_populations}
    below = {rid: int(deficits.get(rid) or 0) for rid in region_populations if int(deficits.get(rid) or 0) > 0}
    if below:
        total_deficit = sum(below.values())
        tilt = int(math.floor(pool * _clamp(float(params.grant_deficit_share), 0.0, 1.0)))
        for rid, d in below.items():
            grants[rid] = min(d, tilt * d // total_deficit)
    rest = pool - sum(grants.values())
    for rid, p in region_populations.items():
        grants[rid] += rest * max(0, int(p)) // total_pop
    return grants


def class_report(region: RegionState, goods: Mapping[str, GoodState], groups: Mapping[str, GroupDef], *,
                 purse: int, treasury: int, params: SimParams = DEFAULT_PARAMS) -> Optional[Dict]:
    """FEAT-194 (3.13): admin class report of a region with classes (None when classes are off / no shares).

    Needs at the current prices / prosperity use the stored goods state (prices of the last recount)."""
    if not params.classes_enabled or region.classes is None:
        return None
    mix = region.classes
    base = region.class_base or region.classes
    pop = sim_population(region.population, params)
    goods = {c: g for c, g in goods.items() if c in groups}
    _norm, norm_parts = econ_classes.wealth_norm(groups, goods, pop, mix, base, params)
    cost = [0.0, 0.0, 0.0]
    for code, good in goods.items():
        weights, factor = econ_classes.demand_weights(groups[code], mix, base)
        day = demand_tick(groups[code], good, pop, region.prosperity, params, factor) / params.dt
        unit = float(groups[code].base_price) * float(good.price_mult)
        for k, part in enumerate(econ_classes.class_parts(day, weights, factor)):
            cost[k] += part * unit
    return econ_classes.class_report(mix=mix, base=base, population=pop, norm_parts=norm_parts,
                                     cost_parts_day=cost, purse=purse, treasury=treasury,
                                     treasury_target=region.treasury_target, params=params)


# --------------------------------------------------------------------------------------------- the tick

def simulate_region(
    region: RegionState,
    goods: Mapping[str, GoodState],
    groups: Mapping[str, GroupDef],
    *,
    purse: int,
    treasury: int,
    grant: int = 0,
    country_tax_rate: float = 0.1,
    params: SimParams = DEFAULT_PARAMS,
    mods: Optional[RegionModifiers] = None,
) -> SimResult:
    """One tick of one region (3.4 steps 1-10). Inputs are not mutated.

    ``purse`` / ``treasury`` are the ledger balances before the tick, ``grant`` the country grant planned for this
    region, ``country_tax_rate`` the rate the ledger applies on purse -> region inflows.

    ``mods`` (FEAT-187) are the aggregated levers of the region's active events: production / consumption multiply
    the working copies (never persisted), prices are multiplied after step 7, the tax after step 8 inputs, stability /
    prosperity deltas after steps 9 / 10. ``None`` executes none of these statements (results unchanged).

    Social classes (FEAT-194, 3.2): when ``params.classes_enabled`` and ``region.classes`` is set, demand / norms are
    scaled by the class demand factors (exactly 1.0 at the template mix ``region.class_base``), affordability and
    consumption run per class (shortages served rich -> middling -> poor), the income tax is class-weighted, a wealth
    tax takes ``wealth_tax_rate`` of the purse above the wealth norm into the treasury (not paid back as wages in the
    same tick), stability gets the class terms and the mix drifts (mobility). Without classes none of these
    statements run (results unchanged; ``wealth_norm`` = :func:`starting_purse`).
    """
    dt = params.dt
    pop = sim_population(region.population, params)
    pop_k = pop / 1000.0
    purse = max(0, int(purse))
    treasury = int(treasury)
    grant = max(0, int(grant))
    has_classes = bool(params.classes_enabled) and region.classes is not None
    mix: Optional[ClassMix] = region.classes if has_classes else None
    base: Optional[ClassMix] = (region.class_base or region.classes) if has_classes else None
    factors: Optional[Dict[str, float]] = None
    class_w: Dict[str, Tuple[float, float, float]] = {}
    norm_total = 0
    norm_parts: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    if has_classes:
        # 0. class demand factors and the wealth norm (from the input goods: event mods never move the norm)
        factors = {}
        for code, group in groups.items():
            class_w[code], factors[code] = econ_classes.demand_weights(group, mix, base)
        norm_total, norm_parts = econ_classes.wealth_norm(groups, {c: g for c, g in goods.items() if c in groups},
                                                          pop, mix, base, params)
    new = {code: replace(good) for code, good in goods.items() if code in groups}
    for good in new.values():
        good.prev_price_mult = good.price_mult
        good.last_produced = good.last_consumed = good.last_demand = good.last_spoiled = 0.0
    if mods is not None:
        for code, good in new.items():
            good.production_per_1000 = float(good.production_per_1000) * float(mods.production.get(code, 1.0))
            good.consumption_mult = float(good.consumption_mult) * float(mods.consumption.get(code, 1.0))

    # 1. multipliers
    stab_factor = 0.5 + 0.5 * min(1.0, max(0.0, float(region.stability)) / max(params.full_stability, 1e-9))
    hunger_factor = 1.0 - params.hunger_prod_penalty * _clamp(float(region.hunger), 0.0, 1.0)
    m = stab_factor * max(0.0, hunger_factor)

    # 2-3. production (raw first, then processed limited by inputs)
    for code in _ordered_codes(groups, new):
        group, good = groups[code], new[code]
        e_g = _clamp(1.0 + params.prod_price_elasticity * (good.price_mult - 1.0),
                     params.prod_price_min, params.prod_price_max)
        potential = max(0.0, float(good.production_per_1000)) * pop_k * m * e_g * dt
        produced = potential
        inputs = {ic: float(r) for ic, r in group.inputs.items() if r and r > 0 and ic in new}
        if inputs and potential > 0:
            limit = min(max(0.0, new[ic].stock) / r for ic, r in inputs.items())
            produced = min(potential, limit)
            for ic, r in inputs.items():
                new[ic].stock = max(0.0, new[ic].stock - produced * r)
        good.stock += produced
        good.last_produced = produced

    # 4. demand
    for code, good in new.items():
        if factors is None:
            good.last_demand = demand_tick(groups[code], good, pop, region.prosperity, params)
        else:
            good.last_demand = demand_tick(groups[code], good, pop, region.prosperity, params, factors[code])

    # 5. affordability & consumption
    cost_day = sum(g.last_demand / dt * float(groups[c].base_price) * g.price_mult for c, g in new.items())
    class_hunger: Optional[Tuple[float, float, float]] = None
    class_afford: Optional[Tuple[float, float, float]] = None
    food_group = next((g for g in groups.values() if g.is_food), None)
    if not has_classes:
        afford = 1.0 if cost_day <= 0 else _clamp(purse / (cost_day * params.afford_days), 0.0, 1.0)
        for good in new.values():
            consumed = min(max(0.0, good.stock), good.last_demand * afford)
            good.stock -= consumed
            good.last_consumed = consumed
    else:
        # per class: the purse split ∝ the class norm parts, afford_k against the class's cost at current prices;
        # each group's class parts are served from the stock rich -> middling -> poor
        parts = {c: econ_classes.class_parts(g.last_demand, class_w[c], factors[c]) for c, g in new.items()}
        cost_k = [0.0, 0.0, 0.0]
        for c, g in new.items():
            unit = float(groups[c].base_price) * g.price_mult / dt
            for k in range(3):
                cost_k[k] += parts[c][k] * unit
        money = econ_classes.split_money(purse, norm_parts if sum(norm_parts) > 0 else cost_k)
        class_afford = tuple(econ_classes.class_afford(money[k], cost_k[k], params.afford_days)
                             for k in range(3))  # type: ignore[assignment]
        afford = (sum(cost_k[k] * class_afford[k] for k in range(3)) / cost_day) if cost_day > 0 else 1.0
        food_got = (0.0, 0.0, 0.0)
        for c, good in new.items():
            got_k = econ_classes.allocate(good.stock, parts[c], class_afford)
            consumed = min(max(0.0, good.stock), got_k[0] + got_k[1] + got_k[2])
            good.stock -= consumed
            good.last_consumed = consumed
            if food_group is not None and c == food_group.code:
                food_got = got_k

    hunger = 0.0
    if food_group is not None and food_group.code in new:
        food = new[food_group.code]
        need = float(food_group.norm_per_1000) * float(food.consumption_mult) * pop_k * dt
        if not has_classes:
            hunger = _clamp(1.0 - food.last_consumed / need, 0.0, 1.0) if need > 0 else 0.0
        else:
            # class need = today's need x the class's per-capita weight (sums to need x F_food)
            need_k = [need * w for w in class_w[food_group.code]]
            class_hunger = tuple(_clamp(1.0 - food_got[k] / need_k[k], 0.0, 1.0) if need_k[k] > 0 else 0.0
                                 for k in range(3))  # type: ignore[assignment]
            need_total = sum(need_k)
            hunger = _clamp(1.0 - sum(food_got) / need_total, 0.0, 1.0) if need_total > 0 else 0.0
    elif has_classes:
        class_hunger = (0.0, 0.0, 0.0)
    want = sum(g.last_demand * float(groups[c].base_price) for c, g in new.items() if not groups[c].is_food)
    got = sum(g.last_consumed * float(groups[c].base_price) for c, g in new.items() if not groups[c].is_food)
    satisfaction = _clamp(got / want, 0.0, 1.0) if want > 0 else 1.0

    # 6. norm & cap, 7. prices
    for code, good in new.items():
        if factors is None:
            good.norm_stock = norm_stock(code, groups, new, pop)
        else:
            good.norm_stock = norm_stock(code, groups, new, pop, factors)
        cap = params.stock_cap_mult * good.norm_stock
        if good.stock > cap:
            good.last_spoiled = good.stock - cap
            good.stock = cap
        good.price_mult = price_mult(good.stock, good.norm_stock, params)
    if mods is not None:
        for code, mult in mods.price.items():
            if code in new:
                new[code].price_mult = _clamp(new[code].price_mult * float(mult), params.price_min, params.price_max)

    # 8. money
    income_f = sum(g.last_produced * float(groups[c].base_price) * g.price_mult for c, g in new.items())
    income = int(math.floor(max(0.0, income_f)))
    wealth_tax = 0
    if not has_classes:
        if mods is None:
            tax = min(purse, int(math.floor(income * max(0.0, float(region.tax_rate)))))
        else:
            tax = min(purse, int(math.floor(income * max(0.0, float(region.tax_rate))
                                            * max(0.0, float(mods.tax_income_mult)))))
        country_tax = int(math.floor(tax * max(0.0, float(country_tax_rate))))
        net_tax = tax - country_tax
        treasury_target = int(math.floor(tax * (1.0 / dt) * params.treasury_reserve_days))
        wages = wage_amount(net_tax, grant, treasury, treasury_target, params)
        purse_after = purse - tax + wages
        treasury_after = treasury + net_tax + grant - wages
    else:
        # class-weighted income tax (x1.0 at the template mix) + wealth tax on the purse above the norm. Both go
        # purse -> treasury in one ledger leg, the ledger forwards country_tax_rate of the sum to the country.
        # treasury_target and wages come from the income tax only: the wealth tax is not paid back the same tick.
        t_factor = econ_classes.tax_factor(mix, base, params)
        if mods is None:
            tax = min(purse, int(math.floor(income * max(0.0, float(region.tax_rate)) * t_factor)))
        else:
            tax = min(purse, int(math.floor(income * max(0.0, float(region.tax_rate))
                                            * max(0.0, float(mods.tax_income_mult)) * t_factor)))
        wealth_tax = econ_classes.wealth_tax(purse - tax, norm_total, params)
        rate = max(0.0, float(country_tax_rate))
        country_tax = int(math.floor((tax + wealth_tax) * rate))
        net_tax = tax - int(math.floor(tax * rate))
        treasury_target = int(math.floor(tax * (1.0 / dt) * params.treasury_reserve_days))
        wages = wage_amount(net_tax, grant, treasury, treasury_target, params)
        purse_after = purse - tax - wealth_tax + wages
        treasury_after = treasury + tax + wealth_tax - country_tax + grant - wages

    # 9. stability
    stab_target = (params.stab_base
                   - params.stab_hunger_w * hunger
                   - params.stab_goods_w * (1.0 - satisfaction)
                   - params.stab_tax_w * max(0.0, float(region.tax_rate) - params.stab_free_tax)
                   - (params.stab_debt_penalty if treasury_after < 0 else 0.0))
    if has_classes:
        stab_target -= econ_classes.stability_terms(mix, class_hunger[0] if class_hunger else 0.0,
                                                    float(region.tax_rate), params)
    stab_target = _clamp(stab_target, 0.0, 100.0)
    stability = float(region.stability)
    rate = params.stab_rate_up if stab_target > stability else params.stab_rate_down
    stability = _clamp(stability + rate * (stab_target - stability), 0.0, 100.0)
    if mods is not None:
        stability = _clamp(stability + float(mods.stability_delta), 0.0, 100.0)

    # 10. prosperity
    liq_base = cost_day * params.prosp_liq_days
    liq = min(1.0, purse_after / liq_base) if liq_base > 0 else 1.0
    prosp_target = _clamp(100.0 * (params.prosp_w_sat * satisfaction + params.prosp_w_liq * liq
                                   + params.prosp_w_stab * stability / 100.0) - params.prosp_hunger_w * hunger,
                          0.0, 100.0)
    prosperity = float(region.prosperity)
    prosperity = _clamp(prosperity + params.prosp_rate * (prosp_target - prosperity), 0.0, 100.0)
    if mods is not None:
        prosperity = _clamp(prosperity + float(mods.prosperity_delta), 0.0, 100.0)

    if not has_classes:
        new_region = replace(region, stability=stability, prosperity=prosperity, hunger=hunger,
                             satisfaction=satisfaction, treasury_target=treasury_target)
        return SimResult(region=new_region, goods=new, income=income, tax=tax, country_tax=country_tax, grant=grant,
                         wages=wages, purse_after=purse_after, treasury_after=treasury_after,
                         needs_cost_day=cost_day, affordability=afford,
                         wealth_norm=starting_purse(groups, {c: g for c, g in goods.items() if c in groups}, pop,
                                                    params))

    # 11. mobility (slow drift of the mix; dead zone, share bounds)
    r = purse_after / norm_total if norm_total > 0 else 0.0
    new_mix, d_poor, d_rich = econ_classes.mobility(mix, stability, prosperity, hunger, r, params)
    new_region = replace(region, stability=stability, prosperity=prosperity, hunger=hunger,
                         satisfaction=satisfaction, treasury_target=treasury_target, classes=new_mix)
    return SimResult(region=new_region, goods=new, income=income, tax=tax, country_tax=country_tax, grant=grant,
                     wages=wages, purse_after=purse_after, treasury_after=treasury_after,
                     needs_cost_day=cost_day, affordability=afford, wealth_tax=wealth_tax, wealth_norm=norm_total,
                     class_hunger=class_hunger, class_afford=class_afford, class_delta=(d_poor, d_rich))


# --------------------------------------------------------------------------------------------- card

_GENDER_ENDINGS = {
    # food state -> (m, f, n)
    "fed": ("сыт", "сыта", "сыто"),
    "tight": ("недоедает", "недоедает", "недоедает"),
    "hunger": ("голодает", "голодает", "голодает"),
}
_PROSPERITY_ADJ = {
    "rich": ("Богатый", "Богатая", "Богатое"),
    "wealthy": ("Зажиточный", "Зажиточная", "Зажиточное"),
    "modest": ("Скромный", "Скромная", "Скромное"),
    "poor": ("Бедный", "Бедная", "Бедное"),
}
TREASURY_LABELS = {"full": "Казна полна", "ok": "Казна в порядке", "low": "Казна почти пуста",
                   "debt": "Казна в долгах"}
STABILITY_LABELS = {"calm": "Спокойно", "uneasy": "Неспокойно", "unrest": "Волнения", "riot": "Бунт"}
PRICE_LEVEL_LABELS = {"low": "Цены низкие", "normal": "Цены обычные", "high": "Цены высокие",
                      "very_high": "Цены очень высокие"}


def _gender_index(gender: Optional[str]) -> int:
    return {"m": 0, "f": 1, "n": 2}.get((gender or "m").lower(), 0)


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def food_state(hunger: float) -> str:
    hunger = float(hunger)
    if hunger < FOOD_TIGHT_HUNGER:
        return "fed"
    if hunger < FOOD_HUNGER_HUNGER:
        return "tight"
    return "hunger"


def food_label(state: str, noun: str = "Регион", gender: str = "m") -> str:
    """«Регион сыт», «Крепость сыта», «Округа голодает»."""
    return f"{noun} {_GENDER_ENDINGS[state][_gender_index(gender)]}"


def treasury_state(treasury: int, target: int) -> str:
    treasury, target = int(treasury), int(target)
    if treasury < 0:
        return "debt"
    if target <= 0:
        return "ok"
    if treasury >= TREASURY_FULL_SHARE * target:
        return "full"
    if treasury >= TREASURY_OK_SHARE * target:
        return "ok"
    return "low"


def stability_state(stability: float) -> str:
    stability = float(stability)
    if stability >= STABILITY_CALM:
        return "calm"
    if stability >= STABILITY_UNEASY:
        return "uneasy"
    if stability >= STABILITY_UNREST:
        return "unrest"
    return "riot"


def prosperity_state(prosperity: float) -> str:
    prosperity = float(prosperity)
    if prosperity >= PROSPERITY_RICH:
        return "rich"
    if prosperity >= PROSPERITY_WEALTHY:
        return "wealthy"
    if prosperity >= PROSPERITY_MODEST:
        return "modest"
    return "poor"


def prosperity_label(state: str, noun: str = "Регион", gender: str = "m") -> str:
    """«Зажиточный регион», «Бедная крепость»."""
    return f"{_PROSPERITY_ADJ[state][_gender_index(gender)]} {_lower_first(noun)}"


PROSPERITY_PHRASES = {"rich": "процветает", "wealthy": "живёт в достатке", "modest": "живёт скромно",
                      "poor": "в упадке"}


def prosperity_phrase(state: str, noun: str = "Регион") -> str:
    """FEAT-194: «Город процветает», «Округа в упадке» — the prosperity state without the class-like adjective."""
    return f"{noun} {PROSPERITY_PHRASES[state]}"


def price_level_value(goods: Iterable[GoodState], groups: Mapping[str, GroupDef]) -> float:
    """Demand-value-weighted mean price multiplier (weights = last_demand x base_price); no demand -> 1.0."""
    weight = total = 0.0
    for good in goods:
        group = groups.get(good.group_code)
        if group is None:
            continue
        w = max(0.0, float(good.last_demand)) * float(group.base_price)
        weight += w
        total += w * float(good.price_mult)
    return total / weight if weight > 0 else 1.0


def price_level_state(value: float) -> str:
    if value < PRICE_LEVEL_LOW:
        return "low"
    if value < PRICE_LEVEL_NORMAL:
        return "normal"
    if value < PRICE_LEVEL_HIGH:
        return "high"
    return "very_high"


def group_level(mult: float) -> str:
    mult = float(mult)
    if mult <= GROUP_VERY_LOW:
        return "very_low"
    if mult <= GROUP_LOW:
        return "low"
    if mult >= GROUP_VERY_HIGH:
        return "very_high"
    if mult >= GROUP_HIGH:
        return "high"
    return "normal"


def price_trend(mult: float, prev_mult: float) -> str:
    mult, prev_mult = float(mult), float(prev_mult)
    if prev_mult <= 0:
        return "flat"
    if mult > prev_mult * (1.0 + TREND_EPS):
        return "up"
    if mult < prev_mult * (1.0 - TREND_EPS):
        return "down"
    return "flat"


def region_card(
    region: RegionState,
    goods: Mapping[str, GoodState],
    groups: Mapping[str, GroupDef],
    *,
    treasury: int,
    noun: str = "Регион",
    gender: str = "m",
    group_order: Optional[Sequence[str]] = None,
    classes: Optional[ClassMix] = None,
) -> Dict:
    """Qualitative player card body of 3.7 (without region_id / participating / updated_at). No numbers.

    FEAT-194 (3.11): with ``classes`` the card gains ``classes`` {state, label, bar words}; ``phrases[0]`` becomes the
    class label and the prosperity label loses its adjective («Город процветает» / «… в упадке» — only rich / poor
    are added to the phrases, after the food phrase). ``classes=None`` -> the card is unchanged."""
    order = [c for c in (group_order or list(groups)) if c in goods and c in groups]
    food = food_state(region.hunger)
    treas = treasury_state(treasury, region.treasury_target)
    stab = stability_state(region.stability)
    prosp = prosperity_state(region.prosperity)
    level = price_level_state(price_level_value((goods[c] for c in order), groups))

    shortages = [groups[c].name for c in order if goods[c].price_mult >= SHORTAGE_MULT]
    surpluses = [groups[c].name for c in order if goods[c].price_mult <= SURPLUS_MULT]

    card = {
        "food": {"state": food, "label": food_label(food, noun, gender)},
        "treasury": {"state": treas, "label": TREASURY_LABELS[treas]},
        "stability": {"state": stab, "label": STABILITY_LABELS[stab]},
        "prosperity": {"state": prosp, "label": prosperity_label(prosp, noun, gender)},
        "price_level": {"state": level, "label": PRICE_LEVEL_LABELS[level]},
        "shortages": shortages,
        "surpluses": surpluses,
    }
    if classes is None:
        phrases = [card["prosperity"]["label"], card["food"]["label"]]
    else:
        card["classes"] = econ_classes.class_card(classes, noun, gender)
        card["prosperity"]["label"] = prosperity_phrase(prosp, noun)
        phrases = [card["classes"]["label"], card["food"]["label"]]
        if prosp in ("rich", "poor"):
            phrases.append(card["prosperity"]["label"])
    if stab != "calm":
        phrases.append(card["stability"]["label"])
    if treas in ("full", "low", "debt"):
        phrases.append(card["treasury"]["label"])
    if shortages:
        phrases.append("Нехватка: " + ", ".join(_lower_first(n) for n in shortages))
    if surpluses:
        phrases.append("Избыток: " + ", ".join(_lower_first(n) for n in surpluses))
    phrases.append(card["price_level"]["label"])
    card["phrases"] = phrases
    card["groups"] = [
        {"code": c, "name": groups[c].name, "level": group_level(goods[c].price_mult),
         "trend": price_trend(goods[c].price_mult, goods[c].prev_price_mult)}
        for c in order
    ]
    return card
