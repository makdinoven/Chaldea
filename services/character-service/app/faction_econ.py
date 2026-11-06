"""FEAT-206 faction economy — pure rules (no I/O, no DB). features/FEAT-206 §3.4.

* params: a whitelist of keys with bounds; effective = code defaults <- template.params <- per-faction overrides;
* wealth 0..100 of the treasury against the norm (players see only words, staff see numbers);
* :func:`plan_faction_step` — one 6 h step of one faction (dues / profile in, wages out, FIFO debt payouts,
  quartermaster restock from the HQ market paying the residents' purse, NPC members dynamics); deterministic,
  inputs never mutated, every amount an int, no balance ever below 0;
* donation points (daily cap per UTC day) and the quartermaster price / rank gate.

Money never appears or disappears here: every amount moved is a leg between two named accounts (the caller posts them
as ONE ledger operation).
"""

import logging
import math
from dataclasses import dataclass, field, replace
from decimal import ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import econ_core as core

logger = logging.getLogger("character-service.faction_econ")

# --------------------------------------------------------------------------------------------------- params

PROFILE_NONE = "none"
PROFILE_MEMBERS_PURSE = "members_purse"     # profile_per_member x members, from the HQ purse
PROFILE_INCOME_SHARE = "income_share"       # profile_rate x econ_regions.last_income, from the HQ purse
PROFILE_TREASURY_SHARE = "treasury_share"   # profile_rate x positive HQ region treasury, from the region treasury
PROFILE_KINDS = (PROFILE_NONE, PROFILE_MEMBERS_PURSE, PROFILE_INCOME_SHARE, PROFILE_TREASURY_SHARE)

_INT = "int"
_DEC = "dec"
_KIND = "kind"

# key -> (type, lo, hi, Russian label)
PARAM_SPECS: Dict[str, Tuple[str, Optional[Decimal], Optional[Decimal], str]] = {
    "start_members": (_INT, Decimal(0), Decimal(100000), "Участников при заполнении"),
    "norm_per_member": (_INT, Decimal(1), Decimal(100000), "Норма казны на участника"),
    "start_treasury_per_member": (_INT, Decimal(0), Decimal(100000), "Стартовая казна на участника"),
    "dues_per_member": (_DEC, Decimal(0), Decimal(1000), "Взнос участника за пересчёт"),
    "wage_per_member": (_DEC, Decimal(0), Decimal(1000), "Жалованье участника за пересчёт"),
    "profile_kind": (_KIND, None, None, "Источник дохода по профилю"),
    "profile_per_member": (_DEC, Decimal(0), Decimal(1000), "Доход по профилю на участника"),
    "profile_rate": (_DEC, Decimal(0), Decimal("0.2"), "Доля дохода по профилю"),
    "qm_budget_share": (_DEC, Decimal(0), Decimal(1), "Доля бюджета закупок интенданта"),
}
PARAM_KEYS = tuple(PARAM_SPECS)
MAX_DECIMALS = 6

MSG_PARAM_UNKNOWN = "Неизвестный параметр шаблона: {key}"
MSG_PARAM_RANGE = "{label}: от {lo} до {hi}"
MSG_PARAM_INT = "{label}: нужно целое число от {lo} до {hi}"
MSG_PARAM_KIND = "Источник дохода по профилю: none, members_purse, income_share или treasury_share"


class ParamError(ValueError):
    """Invalid template params (Russian message for the admin)."""


@dataclass(frozen=True)
class FactionEconParams:
    start_members: int = 0
    norm_per_member: int = 30
    start_treasury_per_member: int = 0
    dues_per_member: Decimal = Decimal(0)
    wage_per_member: Decimal = Decimal(0)
    profile_kind: str = PROFILE_NONE
    profile_per_member: Decimal = Decimal(0)
    profile_rate: Decimal = Decimal(0)
    qm_budget_share: Decimal = Decimal(0)

    def as_dict(self) -> dict:
        """JSON-ready (decimals as strings, the stored form)."""
        out = {}
        for key in PARAM_KEYS:
            value = getattr(self, key)
            out[key] = _dec_str(value) if isinstance(value, Decimal) else value
        return out


DEFAULT_PARAMS = FactionEconParams()


def _dec_str(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text if text not in ("-0",) else "0"


def _fmt(value: Decimal) -> str:
    return _dec_str(value)


def _to_dec(value) -> Decimal:
    if isinstance(value, bool):
        raise InvalidOperation("bool")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, float, str)):
        result = Decimal(str(value).strip())
    else:
        raise InvalidOperation(type(value).__name__)
    if not result.is_finite():
        raise InvalidOperation("not finite")
    return result


def validate_value(key: str, value):
    """One param, normalised (int / Decimal / kind str). Raises ParamError (Russian)."""
    if key not in PARAM_SPECS:
        raise ParamError(MSG_PARAM_UNKNOWN.format(key=key))
    kind, lo, hi, label = PARAM_SPECS[key]
    if kind == _KIND:
        if not isinstance(value, str) or value not in PROFILE_KINDS:
            raise ParamError(MSG_PARAM_KIND)
        return value
    try:
        number = _to_dec(value)
    except (InvalidOperation, ValueError):
        if kind == _INT:
            raise ParamError(MSG_PARAM_INT.format(label=label, lo=_fmt(lo), hi=_fmt(hi)))
        raise ParamError(MSG_PARAM_RANGE.format(label=label, lo=_fmt(lo), hi=_fmt(hi)))
    if kind == _INT:
        if number != number.to_integral_value() or not lo <= number <= hi:
            raise ParamError(MSG_PARAM_INT.format(label=label, lo=_fmt(lo), hi=_fmt(hi)))
        return int(number)
    if not lo <= number <= hi:
        raise ParamError(MSG_PARAM_RANGE.format(label=label, lo=_fmt(lo), hi=_fmt(hi)))
    return number.quantize(Decimal(1).scaleb(-MAX_DECIMALS), rounding=ROUND_DOWN).normalize()


def validate_params(mapping: Optional[Mapping], *, partial: bool) -> dict:
    """Whitelist + bounds. ``partial`` = overrides (any subset); otherwise a template's full set (missing keys get the
    code defaults). Returns the stored JSON form (decimals as strings). Raises ParamError."""
    mapping = dict(mapping or {})
    out = {}
    for key, value in mapping.items():
        normalised = validate_value(str(key), value)
        out[str(key)] = _dec_str(normalised) if isinstance(normalised, Decimal) else normalised
    if not partial:
        defaults = DEFAULT_PARAMS.as_dict()
        for key in PARAM_KEYS:
            out.setdefault(key, defaults[key])
    return {key: out[key] for key in PARAM_KEYS if key in out}


def _tolerant(base: FactionEconParams, mapping: Optional[Mapping], what: str) -> FactionEconParams:
    if not isinstance(mapping, Mapping):
        if mapping is not None:
            logger.warning("faction econ: %s params are not an object, ignored", what)
        return base
    changes = {}
    for key, value in mapping.items():
        try:
            changes[str(key)] = validate_value(str(key), value)
        except ParamError:
            logger.warning("faction econ: %s param %r=%r ignored", what, key, value)
    return replace(base, **changes) if changes else base


def effective_params(template_params: Optional[Mapping], overrides: Optional[Mapping]) -> FactionEconParams:
    """code defaults <- template params <- overrides; broken stored values are ignored with a warning."""
    return _tolerant(_tolerant(DEFAULT_PARAMS, template_params, "template"), overrides, "override")


# --------------------------------------------------------------------------------------------------- settings

@dataclass(frozen=True)
class EconSettings:
    """The FEAT-206 part of ``faction_settings`` (row id=1)."""
    donation_marks_per_point: int = 10
    donation_points_daily_cap: int = 50
    econ_enabled: bool = True
    econ_purse_share_pct: int = 2
    econ_treasury_share_pct: int = 1
    members_leave_pct: int = 5
    members_grow_pct: int = 1
    qm_take_share_pct: int = 5
    econ_item_sale_share_pct: int = 2           # FEAT-207: HQ purse share per tick for donated item sales


DEFAULT_ECON_SETTINGS = EconSettings()

# name -> (lo, hi, Russian label); econ_enabled is a bool and handled separately
ECON_SETTINGS_BOUNDS = {
    "donation_marks_per_point": (1, 10000, "Марок за одно очко пожертвования"),
    "donation_points_daily_cap": (0, 100000, "Очков за пожертвования в день (0 — не даются)"),
    "econ_purse_share_pct": (0, 20, "Доля кошелька жителей края на все фракции за пересчёт, %"),
    "econ_treasury_share_pct": (0, 20, "Доля казны края на все фракции за пересчёт, %"),
    "members_leave_pct": (0, 50, "Уход участников без жалованья за пересчёт, %"),
    "members_grow_pct": (0, 10, "Приток участников при богатой казне за пересчёт, %"),
    "qm_take_share_pct": (0, 50, "Доля запаса группы товаров края на закупку интенданта, %"),
    "econ_item_sale_share_pct": (0, 20, "Доля кошелька жителей края на выкуп пожертвованных предметов за пересчёт, %"),
}


def econ_settings_from_row(row) -> EconSettings:
    if row is None:
        return DEFAULT_ECON_SETTINGS

    def get(name):
        value = getattr(row, name, None)
        return getattr(DEFAULT_ECON_SETTINGS, name) if value is None else value

    return EconSettings(
        donation_marks_per_point=max(1, int(get("donation_marks_per_point"))),
        donation_points_daily_cap=max(0, int(get("donation_points_daily_cap"))),
        econ_enabled=bool(get("econ_enabled")),
        econ_purse_share_pct=int(get("econ_purse_share_pct")),
        econ_treasury_share_pct=int(get("econ_treasury_share_pct")),
        members_leave_pct=int(get("members_leave_pct")),
        members_grow_pct=int(get("members_grow_pct")),
        qm_take_share_pct=int(get("qm_take_share_pct")),
        econ_item_sale_share_pct=int(get("econ_item_sale_share_pct")),
    )


# --------------------------------------------------------------------------------------------------- wealth

WEALTH_THRIVING = "thriving"
WEALTH_STABLE = "stable"
WEALTH_STRUGGLING = "struggling"
WEALTH_DESTITUTE = "destitute"
WEALTH_LABELS = {
    WEALTH_THRIVING: "Процветает",
    WEALTH_STABLE: "Держится",
    WEALTH_STRUGGLING: "В затруднении",
    WEALTH_DESTITUTE: "Бедствует",
}
WEALTH_NEUTRAL = 50          # balance == norm


def norm(members: int, params: FactionEconParams) -> int:
    return max(1, int(members) * int(params.norm_per_member))


def wealth(balance: int, norm_value: int) -> int:
    """clamp(0, 100, round(50 x balance / norm)); half rounds up."""
    norm_value = max(1, int(norm_value))
    raw = (Decimal(max(0, int(balance))) * WEALTH_NEUTRAL / Decimal(norm_value)).to_integral_value(
        rounding=ROUND_HALF_UP)
    return int(min(Decimal(100), max(Decimal(0), raw)))


def wealth_state(value: int) -> str:
    value = int(value)
    if value >= 75:
        return WEALTH_THRIVING
    if value >= 40:
        return WEALTH_STABLE
    if value >= 15:
        return WEALTH_STRUGGLING
    return WEALTH_DESTITUTE


def wealth_word(value: Optional[int]) -> Optional[dict]:
    if value is None:
        return None
    state = wealth_state(value)
    return {"state": state, "label": WEALTH_LABELS[state]}


# --------------------------------------------------------------------------------------------------- tick inputs

def _floor(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


@dataclass(frozen=True)
class Wants:
    """What a faction would take this tick before the caps."""
    dues: int = 0
    profile_purse: int = 0
    profile_treasury: int = 0

    @property
    def purse(self) -> int:
        return self.dues + self.profile_purse


def wants(members: int, params: FactionEconParams, *, region_treasury: int, last_income: int) -> Wants:
    members = max(0, int(members))
    dues = _floor(Decimal(members) * params.dues_per_member)
    profile_purse = profile_treasury = 0
    if params.profile_kind == PROFILE_MEMBERS_PURSE:
        profile_purse = _floor(Decimal(members) * params.profile_per_member)
    elif params.profile_kind == PROFILE_INCOME_SHARE:
        profile_purse = _floor(Decimal(max(0, int(last_income))) * params.profile_rate)
    elif params.profile_kind == PROFILE_TREASURY_SHARE:
        profile_treasury = _floor(Decimal(max(0, int(region_treasury))) * params.profile_rate)
    return Wants(dues=max(0, dues), profile_purse=max(0, profile_purse), profile_treasury=max(0, profile_treasury))


def regional_caps(purse: int, region_treasury: int, s: EconSettings) -> Tuple[int, int]:
    """(purse cap, treasury cap) for ALL ticking factions of one HQ region this tick."""
    purse_cap = (max(0, int(purse)) * int(s.econ_purse_share_pct)) // 100
    treasury_cap = (max(0, int(region_treasury)) * int(s.econ_treasury_share_pct)) // 100
    return purse_cap, treasury_cap


def split_cap(cap: int, wanted: Mapping[int, int]) -> Dict[int, int]:
    """Split ``cap`` between factions proportionally to their wants (floor; nobody gets more than wanted)."""
    cap = max(0, int(cap))
    total = sum(max(0, int(v)) for v in wanted.values())
    out: Dict[int, int] = {}
    for fid in sorted(wanted):
        want = max(0, int(wanted[fid]))
        if total <= cap:
            out[fid] = want
        else:
            out[fid] = min(want, (want * cap) // total) if total > 0 else 0
    return out


@dataclass(frozen=True)
class Budgets:
    purse: int = 0
    treasury: int = 0
    sales: int = 0             # FEAT-207: this faction's share of the HQ purse for donated item sales


@dataclass(frozen=True)
class SaleRowIn:
    """FEAT-207: donated items of one kind waiting in ``faction_item_stock``."""
    item_id: int
    group: str
    quantity: int
    item_price: int            # items.price (0 -> the group base)


@dataclass(frozen=True)
class DebtIn:
    debt_id: int
    character_id: int
    remaining: int


@dataclass(frozen=True)
class RestockRowIn:
    qm_item_id: int
    group: str
    stock: int
    target: int
    base_price: int            # item base (items.price, else the group base)


@dataclass(frozen=True)
class MarketGroupIn:
    stock: float               # HQ region stock (abstract units) at step start
    price_mult: Decimal
    group_base: int


@dataclass(frozen=True)
class FactionStateIn:
    faction_id: int
    hq_region_id: int
    members: int
    carry: Decimal = Decimal(0)
    members_min: int = 10
    members_max: int = 5000


@dataclass
class FactionStepPlan:
    dues: int = 0
    profile_purse: int = 0
    profile_treasury: int = 0
    wages_due: int = 0
    wages_paid: int = 0
    debts: Dict[int, int] = field(default_factory=dict)          # debt_id -> paid now
    payouts: Dict[int, int] = field(default_factory=dict)        # character_id -> paid now
    restock: Dict[int, int] = field(default_factory=dict)        # qm_item_id -> items bought
    restock_spent: int = 0
    restock_items: int = 0
    stock_delta: Dict[str, float] = field(default_factory=dict)  # group -> -units taken from the HQ region
    balance_before: int = 0
    balance_after: int = 0
    members_before: int = 0
    members_after: int = 0
    carry_after: Decimal = Decimal(0)
    wealth_after: int = 0
    legs: List[core.Leg] = field(default_factory=list)
    # FEAT-207: donated items sold to the HQ market (stock_delta gets +units for them)
    item_sales: int = 0
    items_sold: int = 0
    sale: Dict[int, int] = field(default_factory=dict)           # item_id -> items sold

    @property
    def profile(self) -> int:
        return self.profile_purse + self.profile_treasury

    @property
    def debts_paid(self) -> int:
        return sum(self.debts.values())

    @property
    def members_delta(self) -> int:
        return self.members_after - self.members_before


_UNITS_EPS = 1e-9


def plan_debts(available: int, debts: Sequence[DebtIn]) -> Tuple[Dict[int, int], Dict[int, int], int]:
    """FIFO (ascending debt id), partial allowed. Returns ({debt_id: paid}, {character_id: paid}, left)."""
    available = max(0, int(available))
    by_debt: Dict[int, int] = {}
    by_char: Dict[int, int] = {}
    for debt in sorted(debts, key=lambda d: int(d.debt_id)):
        if available <= 0:
            break
        pay = min(available, max(0, int(debt.remaining)))
        if pay <= 0:
            continue
        available -= pay
        by_debt[int(debt.debt_id)] = pay
        by_char[int(debt.character_id)] = by_char.get(int(debt.character_id), 0) + pay
    return by_debt, by_char, available


def plan_faction_step(state: FactionStateIn, params: FactionEconParams, s: EconSettings, budgets: Budgets, *,
                      purse: int, region_treasury: int, last_income: int, balance: int,
                      open_debts: Sequence[DebtIn] = (), restock_rows: Sequence[RestockRowIn] = (),
                      market: Optional[Mapping[str, MarketGroupIn]] = None,
                      wholesale_share=Decimal("0.5"), sale_rows: Sequence[SaleRowIn] = ()) -> FactionStepPlan:
    """One 6 h step of one faction (§3.4 #1-7; FEAT-207 §3.3: donated item sales with the income)."""
    fid, region_id = int(state.faction_id), int(state.hq_region_id)
    members = max(0, int(state.members))
    balance = max(0, int(balance))
    purse = max(0, int(purse))
    plan = FactionStepPlan(balance_before=balance, members_before=members)
    market = market or {}

    # 1. inflows, capped by this faction's share of the regional caps and by the balances
    want = wants(members, params, region_treasury=region_treasury, last_income=last_income)
    purse_cap = min(max(0, int(budgets.purse)), purse)
    if want.purse <= purse_cap:
        plan.dues, plan.profile_purse = want.dues, want.profile_purse
    elif want.purse > 0:
        plan.dues = (want.dues * purse_cap) // want.purse
        plan.profile_purse = (want.profile_purse * purse_cap) // want.purse
    plan.profile_treasury = min(want.profile_treasury, max(0, int(budgets.treasury)), max(0, int(region_treasury)))

    # 1b. FEAT-207: donated items sold to the HQ market (the residents' purse pays the wholesale price)
    purse_left = max(0, purse - plan.dues - plan.profile_purse)
    sale_left = max(0, int(budgets.sales))
    for row in sorted(sale_rows, key=lambda r: int(r.item_id)):
        good = market.get(row.group)
        quantity = max(0, int(row.quantity))
        if good is None or quantity <= 0:
            continue
        base = core.item_base_price(row.item_price, good.group_base)
        units = core.units_per_item(base, good.group_base)
        if units <= 0 or base <= 0:
            continue
        price = core.wholesale_price(base, good.price_mult, wholesale_share)
        if price <= 0:
            continue
        n = min(quantity, sale_left // price, purse_left // price)
        if n <= 0:
            continue
        income = n * price
        sale_left -= income
        purse_left -= income
        plan.sale[int(row.item_id)] = n
        plan.item_sales += income
        plan.items_sold += n
        plan.stock_delta[row.group] = plan.stock_delta.get(row.group, 0.0) + n * units

    # 2. available money
    available = balance + plan.dues + plan.profile + plan.item_sales

    # 3. wages
    plan.wages_due = _floor(Decimal(members) * params.wage_per_member)
    plan.wages_paid = min(plan.wages_due, available)
    available -= plan.wages_paid

    # 4. debts FIFO
    plan.debts, plan.payouts, available = plan_debts(available, open_debts)

    # 5. quartermaster restock from the HQ market (money -> the residents' purse)
    norm_before = norm(members, params)
    excess = max(Decimal(0), Decimal(available) - Decimal(norm_before) / 2)
    budget = max(0, min(available, _floor(excess * params.qm_budget_share)))
    take_left: Dict[str, float] = {}
    for code, good in market.items():
        take_left[code] = max(0.0, float(good.stock)) * int(s.qm_take_share_pct) / 100.0
    for row in sorted(restock_rows, key=lambda r: int(r.qm_item_id)):
        good = market.get(row.group)
        if good is None or budget <= 0:
            continue
        need = max(0, int(row.target) - max(0, int(row.stock)))
        if need <= 0:
            continue
        base = core.item_base_price(row.base_price, good.group_base)
        units = core.units_per_item(base, good.group_base)
        if units <= 0 or base <= 0:
            continue
        price = core.wholesale_price(base, good.price_mult, wholesale_share)
        by_take = int(math.floor(take_left.get(row.group, 0.0) / units + _UNITS_EPS))
        n = min(need, budget // price, by_take)
        if n <= 0:
            continue
        spent = n * price
        budget -= spent
        available -= spent
        take_left[row.group] = max(0.0, take_left.get(row.group, 0.0) - n * units)
        plan.restock[int(row.qm_item_id)] = n
        plan.restock_spent += spent
        plan.restock_items += n
        plan.stock_delta[row.group] = plan.stock_delta.get(row.group, 0.0) - n * units

    plan.balance_after = available

    # 6. members
    plan.wealth_after = wealth(plan.balance_after, norm_before)
    ratio = Decimal(1) if plan.wages_due <= 0 else Decimal(plan.wages_paid) / Decimal(plan.wages_due)
    if ratio < 1:
        delta = -Decimal(members) * Decimal(int(s.members_leave_pct)) / 100 * (1 - ratio)
    elif plan.wealth_after >= WEALTH_NEUTRAL:
        delta = (Decimal(members) * Decimal(int(s.members_grow_pct)) / 100
                 * Decimal(plan.wealth_after - WEALTH_NEUTRAL) / WEALTH_NEUTRAL)
    else:
        delta = Decimal(0)
    carry = Decimal(state.carry or 0) + delta
    whole = int(carry.to_integral_value(rounding=ROUND_DOWN))          # toward zero, sign preserved
    carry -= whole
    lo, hi = int(state.members_min), int(state.members_max)
    plan.members_after = min(max(members + whole, lo), hi) if lo <= hi else members + whole
    plan.members_after = max(0, plan.members_after)
    plan.carry_after = carry.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)

    # 7. legs (one faction_tick operation)
    faction, purse_ref, region_ref = core.AccountRef.faction(fid), core.AccountRef.purse(region_id), \
        core.AccountRef.region(region_id)
    legs: List[core.Leg] = []
    if plan.dues + plan.profile_purse > 0:
        legs.append(core.Leg(purse_ref, faction, plan.dues + plan.profile_purse))
    if plan.profile_treasury > 0:
        legs.append(core.Leg(region_ref, faction, plan.profile_treasury))
    if plan.item_sales > 0:
        legs.append(core.Leg(purse_ref, faction, plan.item_sales))
    if plan.wages_paid > 0:
        legs.append(core.Leg(faction, purse_ref, plan.wages_paid))
    if plan.restock_spent > 0:
        legs.append(core.Leg(faction, purse_ref, plan.restock_spent))
    for character_id in sorted(plan.payouts):
        legs.append(core.Leg(faction, core.AccountRef.character(character_id), plan.payouts[character_id]))
    plan.legs = legs
    return plan


# --------------------------------------------------------------------------------------------------- donations

def donation_points(marks_today_before: int, marks: int, per_point: int, cap: int,
                    points_today_before: int) -> Tuple[int, int]:
    """(points gained now, points today after). Fractions carry within the UTC day; above the cap nothing."""
    per_point = max(1, int(per_point))
    cap = max(0, int(cap))
    new_total = min(cap, (max(0, int(marks_today_before)) + max(0, int(marks))) // per_point)
    gain = max(0, new_total - max(0, int(points_today_before)))
    return gain, max(0, int(points_today_before)) + gain


# --------------------------------------------------------------------------------------------------- quartermaster

MAX_QM_DISCOUNT = 50


def qm_unit_price(price: int, discount_pct: int) -> int:
    pct = min(max(0, int(discount_pct or 0)), MAX_QM_DISCOUNT)
    return max(1, (int(price) * (100 - pct)) // 100)


def qm_total(price: int, discount_pct: int, quantity: int) -> int:
    return qm_unit_price(price, discount_pct) * max(0, int(quantity))


def rank_allows(member_rank_order: Optional[int], min_rank_order: Optional[int]) -> bool:
    """No min rank -> any member; otherwise the member's rank sort_order must reach it."""
    if min_rank_order is None:
        return True
    if member_rank_order is None:
        return False
    return int(member_rank_order) >= int(min_rank_order)
