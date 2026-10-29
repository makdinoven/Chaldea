"""Living-regions simulation math (FEAT-182, section 3.4) — pure functions, no DB.

The tick runner (``econ_tick.py``) loads rows, converts them into the dataclasses below, calls
:func:`simulate_region` once per region and stores the result / posts the money legs. Everything here is
deterministic and side-effect free so it can be unit-tested without SQL.

Units: goods are "units", production / norms are given per 1000 inhabitants per day, one tick advances
``params.dt`` days (0.25 = 6 h). Money is integer gold (floored).

Card helpers (``food_state`` … ``region_card``) turn the stored state into the qualitative player card of
3.7 — no balances or raw numbers leave this module through them.
"""

import math
from dataclasses import dataclass, field, fields, replace
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

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

    population: int
    tax_rate: float
    stability: float = 70.0
    prosperity: float = 50.0
    hunger: float = 0.0
    satisfaction: float = 1.0
    treasury_target: int = 0


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


def household_demand_day(group: GroupDef, consumption_mult: float, population: int) -> float:
    """Household consumption per day at prosperity 50 and price x1."""
    return float(group.norm_per_1000) * float(consumption_mult) * population / 1000.0


def norm_stock(
    code: str,
    groups: Mapping[str, GroupDef],
    goods: Mapping[str, GoodState],
    population: int,
) -> float:
    """Norm stock of ``code`` (3.4 step 6): norm_days x (household demand/day + input use of processing/day)."""
    group = groups[code]
    good = goods.get(code)
    cmult = good.consumption_mult if good is not None else 1.0
    per_day = household_demand_day(group, cmult, population)
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
    population: int,
    prosperity: float,
    params: SimParams = DEFAULT_PARAMS,
) -> float:
    """Household demand of one group for one tick (3.4 step 4), at the current price."""
    pop_k = population / 1000.0
    prosp_factor = max(PROSPERITY_FACTOR_FLOOR,
                       1.0 + float(group.prosperity_elasticity) * (float(prosperity) - 50.0) / 50.0)
    price_factor = max(float(good.price_mult), MIN_STOCK_RATIO) ** (-float(group.price_elasticity))
    return float(group.norm_per_1000) * float(good.consumption_mult) * pop_k * prosp_factor * price_factor * params.dt


def needs_cost_day(
    groups: Mapping[str, GroupDef],
    goods: Mapping[str, GoodState],
    population: int,
    prosperity: float = 50.0,
    params: SimParams = DEFAULT_PARAMS,
    base_prices: bool = False,
) -> float:
    """Cost of one day of household demand. ``base_prices=True`` -> prices x1 (used by «Заполнить»)."""
    total = 0.0
    for code, good in goods.items():
        group = groups.get(code)
        if group is None:
            continue
        if base_prices:
            probe = replace(good, price_mult=1.0)
            demand = demand_tick(group, probe, population, 50.0, params) / params.dt
            total += demand * float(group.base_price)
        else:
            demand = demand_tick(group, good, population, prosperity, params) / params.dt
            total += demand * float(group.base_price) * float(good.price_mult)
    return total


def starting_purse(
    groups: Mapping[str, GroupDef],
    goods: Mapping[str, GoodState],
    population: int,
    params: SimParams = DEFAULT_PARAMS,
) -> int:
    """Purse target for «Заполнить регионы по шаблонам»: ``purse_start_days`` of needs at base prices."""
    return int(math.floor(params.purse_start_days * needs_cost_day(groups, goods, population, params=params,
                                                                   base_prices=True)))


def starting_goods(
    groups: Mapping[str, GroupDef],
    template_goods: Mapping[str, Tuple[float, float]],
    population: int,
) -> Dict[str, GoodState]:
    """Goods rows of a freshly applied template: stock = norm, prices x1.

    ``template_goods`` maps group code -> (production_per_1000, consumption_mult).
    """
    goods = {
        code: GoodState(group_code=code,
                        production_per_1000=float(template_goods.get(code, (0.0, 1.0))[0]),
                        consumption_mult=float(template_goods.get(code, (0.0, 1.0))[1]))
        for code in groups
    }
    for code, good in goods.items():
        good.norm_stock = norm_stock(code, groups, goods, population)
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
                   params: SimParams = DEFAULT_PARAMS) -> Dict[int, int]:
    """Split ``country_grant_share`` of a country's positive balance between its simulated regions by population.

    Integer floor per region, so the sum never exceeds the granted pool.
    """
    pool = int(math.floor(max(0, int(country_balance)) * params.country_grant_share))
    total_pop = sum(max(0, int(p)) for p in region_populations.values())
    if pool <= 0 or total_pop <= 0:
        return {rid: 0 for rid in region_populations}
    return {rid: pool * max(0, int(p)) // total_pop for rid, p in region_populations.items()}


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
) -> SimResult:
    """One tick of one region (3.4 steps 1-10). Inputs are not mutated.

    ``purse`` / ``treasury`` are the ledger balances before the tick, ``grant`` the country grant planned for this
    region, ``country_tax_rate`` the rate the ledger applies on purse -> region inflows.
    """
    dt = params.dt
    pop = max(0, int(region.population))
    pop_k = pop / 1000.0
    purse = max(0, int(purse))
    treasury = int(treasury)
    grant = max(0, int(grant))
    new = {code: replace(good) for code, good in goods.items() if code in groups}
    for good in new.values():
        good.prev_price_mult = good.price_mult
        good.last_produced = good.last_consumed = good.last_demand = good.last_spoiled = 0.0

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
        good.last_demand = demand_tick(groups[code], good, pop, region.prosperity, params)

    # 5. affordability & consumption
    cost_day = sum(g.last_demand / dt * float(groups[c].base_price) * g.price_mult for c, g in new.items())
    afford = 1.0 if cost_day <= 0 else _clamp(purse / (cost_day * params.afford_days), 0.0, 1.0)
    for good in new.values():
        consumed = min(max(0.0, good.stock), good.last_demand * afford)
        good.stock -= consumed
        good.last_consumed = consumed

    hunger = 0.0
    food_group = next((g for g in groups.values() if g.is_food), None)
    if food_group is not None and food_group.code in new:
        food = new[food_group.code]
        need = float(food_group.norm_per_1000) * float(food.consumption_mult) * pop_k * dt
        hunger = _clamp(1.0 - food.last_consumed / need, 0.0, 1.0) if need > 0 else 0.0
    want = sum(g.last_demand * float(groups[c].base_price) for c, g in new.items() if not groups[c].is_food)
    got = sum(g.last_consumed * float(groups[c].base_price) for c, g in new.items() if not groups[c].is_food)
    satisfaction = _clamp(got / want, 0.0, 1.0) if want > 0 else 1.0

    # 6. norm & cap, 7. prices
    for code, good in new.items():
        good.norm_stock = norm_stock(code, groups, new, pop)
        cap = params.stock_cap_mult * good.norm_stock
        if good.stock > cap:
            good.last_spoiled = good.stock - cap
            good.stock = cap
        good.price_mult = price_mult(good.stock, good.norm_stock, params)

    # 8. money
    income_f = sum(g.last_produced * float(groups[c].base_price) * g.price_mult for c, g in new.items())
    income = int(math.floor(max(0.0, income_f)))
    tax = min(purse, int(math.floor(income * max(0.0, float(region.tax_rate)))))
    country_tax = int(math.floor(tax * max(0.0, float(country_tax_rate))))
    net_tax = tax - country_tax
    treasury_target = int(math.floor(tax * (1.0 / dt) * params.treasury_reserve_days))
    wages = wage_amount(net_tax, grant, treasury, treasury_target, params)
    purse_after = purse - tax + wages
    treasury_after = treasury + net_tax + grant - wages

    # 9. stability
    stab_target = (params.stab_base
                   - params.stab_hunger_w * hunger
                   - params.stab_goods_w * (1.0 - satisfaction)
                   - params.stab_tax_w * max(0.0, float(region.tax_rate) - params.stab_free_tax)
                   - (params.stab_debt_penalty if treasury_after < 0 else 0.0))
    stab_target = _clamp(stab_target, 0.0, 100.0)
    stability = float(region.stability)
    rate = params.stab_rate_up if stab_target > stability else params.stab_rate_down
    stability = _clamp(stability + rate * (stab_target - stability), 0.0, 100.0)

    # 10. prosperity
    liq_base = cost_day * params.prosp_liq_days
    liq = min(1.0, purse_after / liq_base) if liq_base > 0 else 1.0
    prosp_target = _clamp(100.0 * (params.prosp_w_sat * satisfaction + params.prosp_w_liq * liq
                                   + params.prosp_w_stab * stability / 100.0) - params.prosp_hunger_w * hunger,
                          0.0, 100.0)
    prosperity = float(region.prosperity)
    prosperity = _clamp(prosperity + params.prosp_rate * (prosp_target - prosperity), 0.0, 100.0)

    new_region = replace(region, stability=stability, prosperity=prosperity, hunger=hunger,
                         satisfaction=satisfaction, treasury_target=treasury_target)
    return SimResult(region=new_region, goods=new, income=income, tax=tax, country_tax=country_tax, grant=grant,
                     wages=wages, purse_after=purse_after, treasury_after=treasury_after,
                     needs_cost_day=cost_day, affordability=afford)


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


def food_label(state: str, noun: str = "Город", gender: str = "m") -> str:
    """«Город сыт», «Крепость сыта», «Округа голодает»."""
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


def prosperity_label(state: str, noun: str = "Город", gender: str = "m") -> str:
    """«Зажиточный край», «Бедная крепость»."""
    return f"{_PROSPERITY_ADJ[state][_gender_index(gender)]} {_lower_first(noun)}"


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
    noun: str = "Город",
    gender: str = "m",
    group_order: Optional[Sequence[str]] = None,
) -> Dict:
    """Qualitative player card body of 3.7 (without region_id / participating / updated_at). No numbers."""
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
    phrases = [card["prosperity"]["label"], card["food"]["label"]]
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
