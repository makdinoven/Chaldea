"""Region events (FEAT-187, section 3.4) — pure functions, no DB.

An event instance carries a list of effects (JSON snapshot of its template). The tick runner (``econ_tick.py``)
parses the effects of every active instance of a region, aggregates them into the per-step levers
(:class:`econ_sim.RegionModifiers` + merchant / bank flags) and applies the one-shot effects once per instance.
Random rolls are deterministic per (slot, region, purpose) — :func:`rng_for` — so a resumed run repeats them exactly.

Effect JSON: ``{"type": ..., "groups": [codes] | ["*"], "mult": x, "share": s, "delta": d, "pct": p}`` — only the
fields of its type (:data:`EFFECT_FIELDS`). Strict validation lives in ``schemas``; :func:`parse_effects` is lenient
(stored JSON): unknown types / malformed entries are skipped with a warning, numbers are clamped to the type bounds.
"""

import json
import logging
import math
import random
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from econ_sim import RegionModifiers, SimParams

logger = logging.getLogger(__name__)

DAY = 86400
TICK_SECONDS = 21600          # one scheduled run per 6 h slot

KINDS = ("good", "bad")
TRIGGERS = ("random", "low_stability", "manual")
SCOPES = ("region", "neighbours", "country", "world")
ORIGINS = ("random", "manual", "spread", "chain", "riot")
STATUSES = ("active", "ended", "cancelled")
# Calendar segments of locations-service (GET /locations/game-time -> computed.segment_name). Vocabulary only:
# the calendar itself (lengths, epoch) is never re-implemented here.
GAME_SEGMENTS = ("spring", "beltane", "summer", "lughnasad", "autumn", "samhain", "winter", "imbolc")
# Icon names (mirrored by the frontend icon map).
EVENT_ICONS = ("sun", "cloud-rain", "waves", "skull", "biohazard", "zap", "sparkles", "pickaxe", "gem", "beef",
               "swords", "flame", "wheat", "fish", "store", "party-popper", "snowflake", "bug", "coins",
               "heart-pulse", "shield-alert", "alert")
ALL_GROUPS = "*"

PER_STEP_TYPES = ("production", "consumption", "labor", "price", "tax_income", "stability", "prosperity",
                  "merchants_halt", "bank_panic", "loan_boom")
ONE_SHOT_TYPES = ("stock_loss", "treasury_expense", "population")
EFFECT_TYPES = PER_STEP_TYPES + ONE_SHOT_TYPES
GROUP_TYPES = ("production", "consumption", "price", "stock_loss")

# type -> fields it carries (besides "type")
EFFECT_FIELDS: Dict[str, Tuple[str, ...]] = {
    "production": ("groups", "mult"),
    "consumption": ("groups", "mult"),
    "labor": ("mult",),
    "price": ("groups", "mult"),
    "tax_income": ("mult",),
    "stability": ("delta",),
    "prosperity": ("delta",),
    "merchants_halt": (),
    "bank_panic": (),
    "loan_boom": ("mult",),
    "stock_loss": ("groups", "share"),
    "treasury_expense": ("share",),
    "population": ("pct",),
}
# type -> (numeric field, lo, hi)
EFFECT_BOUNDS: Dict[str, Tuple[str, float, float]] = {
    "production": ("mult", 0.0, 5.0),
    "consumption": ("mult", 0.0, 5.0),
    "labor": ("mult", 0.0, 1.5),
    "price": ("mult", 0.2, 5.0),
    "tax_income": ("mult", 0.0, 5.0),
    "stability": ("delta", -10.0, 10.0),
    "prosperity": ("delta", -10.0, 10.0),
    "loan_boom": ("mult", 1.0, 5.0),
    "stock_loss": ("share", 0.0, 0.9),
    "treasury_expense": ("share", 0.0, 0.9),
    "population": ("pct", -0.5, 0.5),
}
MAX_EFFECTS = 12
MAX_ONE_SHOT_SHARE = 0.9      # cap of combined stock-loss / treasury-expense shares of one instance
POPULATION_PCT_LIMIT = 0.5    # combined population change of one instance: +-50 %
POPULATION_MAX = 2_000_000_000  # econ_regions.population is INT
BANK_LOAN_SHARE_MAX = 0.9


def _clamp(value: float, lo: float, hi: float) -> float:
    if value != value:  # NaN guard
        return lo
    return max(lo, min(hi, value))


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Attribute of an ORM row / dataclass or key of a mapping."""
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


# --------------------------------------------------------------------------------------------- effects

@dataclass(frozen=True)
class Effect:
    type: str
    groups: Tuple[str, ...] = ()
    mult: float = 1.0
    share: float = 0.0
    delta: float = 0.0
    pct: float = 0.0


def parse_effects(raw: Any) -> List[Effect]:
    """Lenient parse of a stored effects JSON (list of dicts, or its JSON string). Bad entries are skipped."""
    if raw is None:
        return []
    if isinstance(raw, (str, bytes)):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("region events: effects are not valid JSON — ignored")
            return []
    if not isinstance(raw, (list, tuple)):
        logger.warning("region events: effects are not a list — ignored")
        return []
    result: List[Effect] = []
    for item in raw:
        if not isinstance(item, Mapping):
            logger.warning("region events: effect is not an object — skipped")
            continue
        etype = item.get("type")
        if etype not in EFFECT_FIELDS:
            logger.warning("region events: unknown effect type %r — skipped", etype)
            continue
        kwargs: Dict[str, Any] = {}
        if "groups" in EFFECT_FIELDS[etype]:
            groups = item.get("groups")
            if not isinstance(groups, (list, tuple)):
                logger.warning("region events: effect %s without groups — skipped", etype)
                continue
            codes = tuple(dict.fromkeys(str(g) for g in groups if isinstance(g, str) and g))
            if not codes:
                logger.warning("region events: effect %s without groups — skipped", etype)
                continue
            kwargs["groups"] = codes
        bound = EFFECT_BOUNDS.get(etype)
        if bound is not None:
            name, lo, hi = bound
            value = item.get(name)
            if isinstance(value, bool):
                value = None
            try:
                number = float(value)
            except (TypeError, ValueError):
                logger.warning("region events: effect %s without a numeric %s — skipped", etype, name)
                continue
            if math.isinf(number) or number != number:
                logger.warning("region events: effect %s with a non-finite %s — skipped", etype, name)
                continue
            kwargs[name] = _clamp(number, lo, hi)
        result.append(Effect(type=etype, **kwargs))
    return result


def _expand(groups: Sequence[str], group_codes: Sequence[str]) -> List[str]:
    if ALL_GROUPS in groups:
        return list(group_codes)
    return list(groups)


@dataclass(frozen=True)
class EventEffects:
    """Aggregated per-step effect of all active events of one region."""

    mods: RegionModifiers = field(default_factory=RegionModifiers)
    merchants_halt: bool = False
    bank_panic: bool = False
    loan_boom_mult: float = 1.0


def aggregate(effect_lists: Sequence[Sequence[Effect]], group_codes: Sequence[str],
              params: SimParams) -> EventEffects:
    """Stack the per-step effects of several instances (3.4).

    Per group: product of production mults x product of labor mults (labor hits every group), product of consumption /
    price mults — each product clamped to [event_mult_min, event_mult_max]; only touched groups appear in the maps.
    Tax income: product, same clamp. Stability / prosperity: sum, clamped to +-event_delta_max. Loan boom: product,
    clamped to [1, event_mult_max]. One-shot types are ignored here. Empty input -> identity.
    """
    lo = float(params.event_mult_min)
    hi = max(lo, float(params.event_mult_max))
    delta_max = max(0.0, float(params.event_delta_max))
    group_codes = list(group_codes)

    production: Dict[str, float] = {}
    consumption: Dict[str, float] = {}
    price: Dict[str, float] = {}
    labor = 1.0
    has_labor = has_tax = False
    tax = 1.0
    stability = prosperity = 0.0
    merchants_halt = bank_panic = False
    loan_boom = 1.0

    for effects in effect_lists:
        for eff in effects:
            if eff.type == "production":
                for code in _expand(eff.groups, group_codes):
                    production[code] = production.get(code, 1.0) * eff.mult
            elif eff.type == "consumption":
                for code in _expand(eff.groups, group_codes):
                    consumption[code] = consumption.get(code, 1.0) * eff.mult
            elif eff.type == "price":
                for code in _expand(eff.groups, group_codes):
                    price[code] = price.get(code, 1.0) * eff.mult
            elif eff.type == "labor":
                labor *= eff.mult
                has_labor = True
            elif eff.type == "tax_income":
                tax *= eff.mult
                has_tax = True
            elif eff.type == "stability":
                stability += eff.delta
            elif eff.type == "prosperity":
                prosperity += eff.delta
            elif eff.type == "merchants_halt":
                merchants_halt = True
            elif eff.type == "bank_panic":
                bank_panic = True
            elif eff.type == "loan_boom":
                loan_boom *= eff.mult

    if has_labor:
        for code in group_codes:
            production[code] = production.get(code, 1.0) * labor

    mods = RegionModifiers(
        production={c: _clamp(v, lo, hi) for c, v in production.items()},
        consumption={c: _clamp(v, lo, hi) for c, v in consumption.items()},
        price={c: _clamp(v, lo, hi) for c, v in price.items()},
        tax_income_mult=_clamp(tax, lo, hi) if has_tax else 1.0,
        stability_delta=_clamp(stability, -delta_max, delta_max),
        prosperity_delta=_clamp(prosperity, -delta_max, delta_max),
    )
    return EventEffects(mods=mods, merchants_halt=merchants_halt, bank_panic=bank_panic,
                        loan_boom_mult=_clamp(loan_boom, 1.0, max(1.0, hi)))


def merchant_params(params: SimParams, ev: Optional[EventEffects]) -> SimParams:
    """Params of the region's merchant step: no restock while merchants halt (residents still buy)."""
    if ev is None or not ev.merchants_halt:
        return params
    return replace(params, merchant_take_share=0.0)


def bank_params(params: SimParams, ev: Optional[EventEffects]) -> SimParams:
    """Params of the region's bank pass: panic -> residents keep nothing in the bank; boom -> larger loan target."""
    if ev is None:
        return params
    changes: Dict[str, float] = {}
    if ev.bank_panic:
        changes["bank_resident_deposit_share"] = 0.0
    if ev.loan_boom_mult != 1.0:
        changes["bank_resident_loan_share"] = min(BANK_LOAN_SHARE_MAX,
                                                  float(params.bank_resident_loan_share) * ev.loan_boom_mult)
    return replace(params, **changes) if changes else params


# --------------------------------------------------------------------------------------------- one-shots

@dataclass(frozen=True)
class OneShots:
    stock_loss: Dict[str, float] = field(default_factory=dict)   # group -> share of the stock lost
    treasury_share: float = 0.0
    population_pct: float = 0.0

    @property
    def empty(self) -> bool:
        return not self.stock_loss and self.treasury_share <= 0 and self.population_pct == 0


def one_shots(effects: Iterable[Effect], group_codes: Sequence[str] = ()) -> OneShots:
    """Combine the one-shot effects of ONE instance.

    Stock shares on one group combine as 1 - prod(1 - s) (capped at 0.9); treasury shares sum (cap 0.9); population
    pcts sum, clamped to +-50 %. ``"*"`` in stock-loss groups expands to ``group_codes``.
    """
    keep: Dict[str, float] = {}
    treasury = 0.0
    population = 0.0
    for eff in effects:
        if eff.type == "stock_loss":
            for code in _expand(eff.groups, list(group_codes)):
                keep[code] = keep.get(code, 1.0) * (1.0 - _clamp(eff.share, 0.0, MAX_ONE_SHOT_SHARE))
        elif eff.type == "treasury_expense":
            treasury += _clamp(eff.share, 0.0, MAX_ONE_SHOT_SHARE)
        elif eff.type == "population":
            population += eff.pct
    stock_loss = {c: _clamp(1.0 - k, 0.0, MAX_ONE_SHOT_SHARE) for c, k in keep.items()}
    return OneShots(stock_loss={c: s for c, s in stock_loss.items() if s > 0},
                    treasury_share=_clamp(treasury, 0.0, MAX_ONE_SHOT_SHARE),
                    population_pct=_clamp(population, -POPULATION_PCT_LIMIT, POPULATION_PCT_LIMIT))


def stock_after_loss(stock: float, share: float) -> Tuple[float, float]:
    """-> (new stock, units lost). Negative stock is treated as 0."""
    stock = max(0.0, float(stock))
    lost = stock * _clamp(float(share), 0.0, MAX_ONE_SHOT_SHARE)
    return stock - lost, lost


def treasury_expense(treasury_after: int, share: float) -> int:
    """Gold spent on recovery: a share of the POSITIVE treasury (empty / in debt -> 0, never a new debt)."""
    return int(math.floor(max(0, int(treasury_after)) * _clamp(float(share), 0.0, MAX_ONE_SHOT_SHARE)))


def population_after(population: int, pct: float, scale: int) -> int:
    """Lore population after a permanent +-pct change.

    Never drops below max(1, scale) (sim population >= 1, the region stays participating) — and a negative change
    never raises a population that is already below that floor. 0 % or a non-positive population -> unchanged.
    """
    population = int(population)
    pct = _clamp(float(pct), -POPULATION_PCT_LIMIT, POPULATION_PCT_LIMIT)
    if pct == 0 or population <= 0:
        return population
    new = int(round(population * (1.0 + pct)))
    if pct < 0:
        floor = min(population, max(1, int(scale)))
        return max(floor, new)
    return min(POPULATION_MAX, max(population, new))


# --------------------------------------------------------------------------------------------- rolls

def tick_chance(params: SimParams) -> float:
    """Chance of a random event per region per scheduled 6 h slot: rate per «season» spread over its slots."""
    days = float(params.event_season_days)
    if days <= 0:
        return 0.0
    return _clamp(float(params.event_rate_per_season) * TICK_SECONDS / (days * DAY), 0.0, 1.0)


def per_tick_chance(lifetime_chance: float, duration_seconds: float) -> float:
    """Per-slot chance so that the chance over the whole ``duration`` equals ``lifetime_chance``."""
    c = _clamp(float(lifetime_chance), 0.0, 1.0)
    if c <= 0:
        return 0.0
    if c >= 1:
        return 1.0
    duration = max(float(duration_seconds), float(TICK_SECONDS))
    return 1.0 - (1.0 - c) ** (TICK_SECONDS / duration)


def _codes(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, (str, bytes)):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    if not isinstance(value, (list, tuple)):
        return []
    return [str(v) for v in value]


def eligible(templates: Iterable[Any], *, region_template: Optional[str], segment: Optional[str],
             active_codes: Iterable[str]) -> list:
    """Templates a random roll may pick for a region (input order kept).

    Enabled, trigger ``random``, weight > 0, region template allowed (empty list = any), season allowed (empty list =
    any; a seasonal template needs a known ``segment``), not already active in the region.
    """
    active = set(active_codes)
    result = []
    for t in templates:
        if not _get(t, "is_enabled", True) or _get(t, "trigger_kind", "random") != "random":
            continue
        try:
            if float(_get(t, "weight", 0) or 0) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        if _get(t, "code") in active:
            continue
        allowed = _codes(_get(t, "region_templates"))
        if allowed and region_template not in allowed:
            continue
        seasons = _codes(_get(t, "seasons"))
        if seasons and (segment is None or segment not in seasons):
            continue
        result.append(t)
    return result


def pick_weighted(rng: random.Random, items: Sequence[Any]) -> Optional[Any]:
    """One item by its ``weight`` (attribute or key); None when nothing has a positive weight."""
    weighted = []
    for item in items:
        try:
            w = float(_get(item, "weight", 0) or 0)
        except (TypeError, ValueError):
            continue
        if w > 0 and not math.isinf(w):
            weighted.append((item, w))
    if not weighted:
        return None
    total = sum(w for _, w in weighted)
    point = rng.random() * total
    acc = 0.0
    for item, w in weighted:
        acc += w
        if point < acc:
            return item
    return weighted[-1][0]


def roll_duration_seconds(rng: random.Random, min_days: float, max_days: float) -> int:
    """Uniform duration in [min, max] days, rounded to whole minutes (at least one minute)."""
    lo = max(0.0, float(min_days)) * DAY
    hi = max(lo, float(max_days) * DAY)
    seconds = rng.uniform(lo, hi)
    return max(60, int(round(seconds / 60.0)) * 60)


def riot_due(low_since: Optional[datetime], last_riot_end: Optional[datetime], riot_active: bool,
             now: datetime, after_days: float) -> bool:
    """A riot starts after ``after_days`` of continuous low stability, counted from the later of the low-stability
    start and the end of the previous riot; never while a riot is active."""
    if riot_active or low_since is None:
        return False
    start = low_since if last_riot_end is None else max(low_since, last_riot_end)
    return (now - start).total_seconds() >= float(after_days) * DAY


def rng_for(slot: int, region_id: int, purpose: str) -> random.Random:
    """Deterministic RNG per scheduled slot / region / purpose (str seeds are hashed with SHA-512 — stable across
    processes, independent of PYTHONHASHSEED)."""
    return random.Random(f"{slot}:{region_id}:{purpose}")
