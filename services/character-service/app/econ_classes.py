"""Social classes of the residents and the wealth norm (FEAT-194, section 3) — pure functions, no DB.

A participating region holds the shares of three classes — poor / middling / rich, sum 1 (:class:`ClassMix`). Every
class factor is normalised against the region's **template default mix** (``base``), so a region sitting at its
template mix computes factor exactly ``1.0`` (``x / x`` with the numerator and the denominator summed in the same
order) — the rollout does not move demand, norms, prices or the income tax.

This module imports nothing from ``econ_sim`` (``econ_sim`` imports it): goods groups and params are passed
duck-typed (``group.class_demand`` = (poor, middling, rich) per-capita weights; ``params`` = ``econ_sim.SimParams``).

* demand (3.3): ``w_kg = s_k c_kg / Σ_j base_j c_jg``, ``F_g = Σ_k s_k c_kg / Σ_j base_j c_jg``;
* wealth norm (3.4): ``Σ_k norm_days_k × (class k's household needs per day at base prices)``;
* purchasing power (3.5): the purse is split ∝ the class norm parts, ``afford_k = money_k / (cost_k × afford_days)``;
  shortages are served rich → middling → poor;
* taxes (3.6): class-weighted income tax factor, wealth tax on the purse above the norm;
* stability (3.7), mobility (3.8, with a dead zone and share bounds), deficit (3.9);
* player card words (3.11) — no numbers; admin class report (3.13).
"""

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Mapping, Optional, Sequence, Tuple

CLASSES = ("poor", "middling", "rich")

# Card thresholds (3.11): index = middling x 0.5 + rich.
CLASS_INDEX_MODEST = 0.25
CLASS_INDEX_WEALTHY = 0.32
CLASS_INDEX_RICH = 0.40
CLASS_TAIL_POOR = 0.5          # «, много бедняков» from this poor share
CLASS_TAIL_RICH = 0.18         # «, много богачей» from this rich share
# Bar words: poor / middling «few < 0.30 <= some < 0.50 <= many»; rich «few < 0.08 <= some < 0.18 <= many».
BAR_SOME = {"poor": 0.30, "middling": 0.30, "rich": 0.08}
BAR_MANY = {"poor": 0.50, "middling": 0.50, "rich": 0.18}
# Mobility: hunger at this level is a full «голодает» signal (= econ_sim.FOOD_HUNGER_HUNGER).
MOB_HUNGER_FULL = 0.15
SHARE_DECIMALS = 6
_SHARE_QUANT = Decimal(1).scaleb(-SHARE_DECIMALS)

CLASS_ADJ = {
    "rich": ("Богатый", "Богатая", "Богатое"),
    "wealthy": ("Зажиточный", "Зажиточная", "Зажиточное"),
    "modest": ("Скромный", "Скромная", "Скромное"),
    "poor": ("Бедный", "Бедная", "Бедное"),
}
TAIL_POOR = ", много бедняков"
TAIL_RICH = ", много богачей"


def _clamp(value: float, lo: float, hi: float) -> float:
    if value != value:  # NaN guard
        return lo
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class ClassMix:
    poor: float
    middling: float
    rich: float

    def as_tuple(self) -> Tuple[float, float, float]:
        return (float(self.poor), float(self.middling), float(self.rich))

    @classmethod
    def of(cls, poor, middling, rich) -> Optional["ClassMix"]:
        """From DB values; None when any share is missing."""
        if poor is None or middling is None or rich is None:
            return None
        return cls(float(poor), float(middling), float(rich))


# --------------------------------------------------------------------------------------------- demand (3.3)

def _class_demand(group) -> Tuple[float, float, float]:
    c = getattr(group, "class_demand", None) or (1.0, 1.0, 1.0)
    return (float(c[0]), float(c[1]), float(c[2]))


def demand_weights(group, mix: ClassMix, base: ClassMix) -> Tuple[Tuple[float, float, float], float]:
    """-> ((w_poor, w_middling, w_rich), F) of one group.

    ``w_k = s_k c_k / Σ_j base_j c_j``; ``F = Σ_k s_k c_k / Σ_j base_j c_j`` (exactly 1.0 when ``mix == base``).
    Guard: ``Σ_j base_j c_j == 0`` -> F = 1 and the weights split by the shares.
    """
    c = _class_demand(group)
    s = mix.as_tuple()
    b = base.as_tuple()
    denom = b[0] * c[0] + b[1] * c[1] + b[2] * c[2]
    if denom <= 0:
        total = s[0] + s[1] + s[2]
        if total <= 0:
            return (1.0 / 3, 1.0 / 3, 1.0 / 3), 1.0
        return (s[0] / total, s[1] / total, s[2] / total), 1.0
    numer = s[0] * c[0] + s[1] * c[1] + s[2] * c[2]
    return (s[0] * c[0] / denom, s[1] * c[1] / denom, s[2] * c[2] / denom), numer / denom


def demand_factors(groups: Mapping[str, object], mix: ClassMix, base: ClassMix) -> Dict[str, float]:
    """{group code: F_g}."""
    return {code: demand_weights(group, mix, base)[1] for code, group in groups.items()}


def class_parts(total: float, weights: Sequence[float], factor: float) -> Tuple[float, float, float]:
    """Class parts of a group's total demand: ``D × w_k / F`` (F = 0 -> zeros)."""
    if factor <= 0:
        return (0.0, 0.0, 0.0)
    return tuple(float(total) * float(w) / factor for w in weights)  # type: ignore[return-value]


# --------------------------------------------------------------------------------------------- wealth norm (3.4)

def norm_days(params) -> Tuple[float, float, float]:
    return (max(0.0, float(params.class_norm_days_poor)), max(0.0, float(params.class_norm_days_middling)),
            max(0.0, float(params.class_norm_days_rich)))


def base_cost_parts(groups: Mapping[str, object], goods: Mapping[str, object], population: float,
                    mix: ClassMix, base: ClassMix) -> Tuple[float, float, float]:
    """Per class: marks per day of its household needs at base prices (prosperity 50, price x1), whole region.

    The household demand per group is ``econ_sim.household_demand_day`` (norm x consumption_mult x pop / 1000).
    """
    parts = [0.0, 0.0, 0.0]
    for code, good in goods.items():
        group = groups.get(code)
        if group is None:
            continue
        day = float(group.norm_per_1000) * float(good.consumption_mult) * population / 1000.0
        weights, _f = demand_weights(group, mix, base)
        price = float(group.base_price)
        for k in range(3):
            parts[k] += day * weights[k] * price
    return (parts[0], parts[1], parts[2])


def wealth_norm_parts(groups, goods, population: float, mix: ClassMix, base: ClassMix,
                      params) -> Tuple[float, float, float]:
    days = norm_days(params)
    cost = base_cost_parts(groups, goods, population, mix, base)
    return (days[0] * cost[0], days[1] * cost[1], days[2] * cost[2])


def wealth_norm(groups, goods, population: float, mix: ClassMix, base: ClassMix,
                params) -> Tuple[int, Tuple[float, float, float]]:
    """-> (purse norm of the region, per-class norm parts)."""
    parts = wealth_norm_parts(groups, goods, population, mix, base, params)
    return int(math.floor(max(0.0, parts[0] + parts[1] + parts[2]))), parts


# --------------------------------------------------------------------------------------------- purchasing power (3.5)

def split_money(purse: float, weights: Sequence[float]) -> Tuple[float, float, float]:
    """The purse split between the classes ∝ ``weights`` (their norm parts); all-zero weights -> thirds."""
    purse = max(0.0, float(purse))
    total = sum(max(0.0, float(w)) for w in weights)
    if total <= 0:
        return (purse / 3, purse / 3, purse / 3)
    return tuple(purse * max(0.0, float(w)) / total for w in weights)  # type: ignore[return-value]


def class_afford(money: float, cost_day: float, afford_days: float) -> float:
    """``clamp(money / (cost_day × afford_days), 0, 1)``; nothing to buy -> 1."""
    need = float(cost_day) * float(afford_days)
    if need <= 0:
        return 1.0
    return _clamp(float(money) / need, 0.0, 1.0)


def allocate(stock: float, parts: Sequence[float], affords: Sequence[float]) -> Tuple[float, float, float]:
    """Serve the class parts of one group from ``stock``, rich -> middling -> poor, each up to part × afford."""
    left = max(0.0, float(stock))
    got = [0.0, 0.0, 0.0]
    for k in (2, 1, 0):
        want = max(0.0, float(parts[k])) * float(affords[k])
        take = min(left, want)
        got[k] = take
        left -= take
    return (got[0], got[1], got[2])


# --------------------------------------------------------------------------------------------- taxes (3.6)

def tax_weights(params) -> Tuple[float, float, float]:
    return (max(0.0, float(params.class_tax_w_poor)), max(0.0, float(params.class_tax_w_middling)),
            max(0.0, float(params.class_tax_w_rich)))


def tax_factor(mix: ClassMix, base: ClassMix, params) -> float:
    """``Σ s_k t_k / Σ base_k t_k`` — exactly 1.0 at the template mix; zero denominator -> 1.0."""
    t = tax_weights(params)
    s, b = mix.as_tuple(), base.as_tuple()
    denom = b[0] * t[0] + b[1] * t[1] + b[2] * t[2]
    if denom <= 0:
        return 1.0
    return (s[0] * t[0] + s[1] * t[1] + s[2] * t[2]) / denom


def wealth_tax(purse_left: int, norm: int, params) -> int:
    """``floor(rate × max(0, purse_left − norm))``, never more than ``purse_left``."""
    purse_left = max(0, int(purse_left))
    excess = max(0, purse_left - max(0, int(norm)))
    rate = _clamp(float(params.wealth_tax_rate), 0.0, 1.0)
    return min(purse_left, int(math.floor(excess * rate)))


# --------------------------------------------------------------------------------------------- stability (3.7)

def stability_terms(mix: ClassMix, hunger_poor: float, tax_rate: float, params) -> float:
    """Extra stability loss (>= 0) subtracted from the stability target."""
    poor, rich = float(mix.poor), float(mix.rich)
    loss = float(params.class_stab_poor_w) * max(0.0, poor - float(params.class_stab_poor_threshold))
    loss += float(params.class_stab_poor_hunger_w) * poor * max(0.0, float(hunger_poor))
    loss += float(params.class_stab_rich_tax_w) * rich * max(0.0, float(tax_rate)
                                                             - float(params.class_stab_rich_free_tax))
    return max(0.0, loss)


# --------------------------------------------------------------------------------------------- mobility (3.8)

def mobility_score(stability: float, prosperity: float, hunger: float, r: float, params) -> float:
    score = (float(params.mob_w_prosperity) * (float(prosperity) - 50.0) / 50.0
             + float(params.mob_w_money) * _clamp(float(r) - 1.0, -1.0, 1.0)
             + float(params.mob_w_stability) * _clamp((float(stability) - 50.0) / 50.0, -1.0, 1.0)
             - float(params.mob_w_hunger) * _clamp(float(hunger) / MOB_HUNGER_FULL, 0.0, 1.0))
    return _clamp(score, -1.0, 1.0)


def _q(value: float) -> Decimal:
    return Decimal(repr(float(value))).quantize(_SHARE_QUANT, rounding=ROUND_HALF_UP)


def decimals(mix: ClassMix) -> Tuple[Decimal, Decimal, Decimal]:
    """Storage form: poor / rich at 6 decimals, middling = 1 − poor − rich (the sum is exactly 1)."""
    poor, rich = _q(mix.poor), _q(mix.rich)
    return poor, Decimal(1) - poor - rich, rich


def shift(mix: ClassMix, up: float, down: float, rich_factor: float, smin: float,
          smax: float) -> Tuple[ClassMix, float, float]:
    """Move shares between the classes; -> (new mix, dpoor, drich).

    Up: ``up × poor`` poor -> middling and ``up × rich_factor × middling`` middling -> rich. Down: ``down × rich``
    rich -> middling and ``down × middling`` middling -> poor. Flows come from the old shares and are capped so that no
    share is pushed below ``smin`` or above ``smax`` (a share already outside the bounds is never pushed further out).
    The result is rounded (poor / rich to 6 decimals, middling = 1 − poor − rich); no flow -> the mix unchanged.
    """
    up = max(0.0, float(up))
    down = max(0.0, float(down))
    if up <= 0 and down <= 0:
        return mix, 0.0, 0.0
    poor, mid, rich = mix.as_tuple()
    smin, smax = float(smin), float(smax)
    p2m = m2r = r2m = m2p = 0.0
    if up > 0:
        p2m = min(up * poor, max(0.0, poor - smin))
        m2r = min(up * max(0.0, float(rich_factor)) * mid, max(0.0, smax - rich), max(0.0, mid - smin))
        new_mid = mid + p2m - m2r
        if new_mid > max(mid, smax):
            p2m = max(0.0, p2m - (new_mid - max(mid, smax)))
        new_mid = mid + p2m - m2r
        if new_mid < min(mid, smin):
            m2r = max(0.0, m2r - (min(mid, smin) - new_mid))
    if down > 0:
        r2m = min(down * rich, max(0.0, rich - smin))
        m2p = min(down * mid, max(0.0, smax - poor), max(0.0, mid - smin))
        new_mid = mid + r2m - m2p
        if new_mid > max(mid, smax):
            r2m = max(0.0, r2m - (new_mid - max(mid, smax)))
        new_mid = mid + r2m - m2p
        if new_mid < min(mid, smin):
            m2p = max(0.0, m2p - (min(mid, smin) - new_mid))
    new_poor = poor - p2m + m2p
    new_rich = rich + m2r - r2m
    if new_poor == poor and new_rich == rich:
        return mix, 0.0, 0.0
    d_poor, d_mid, d_rich = decimals(ClassMix(new_poor, 1.0 - new_poor - new_rich, new_rich))
    new = ClassMix(float(d_poor), float(d_mid), float(d_rich))
    old_poor, _m, old_rich = decimals(mix)
    return new, float(d_poor - old_poor), float(d_rich - old_rich)


def mobility(mix: ClassMix, stability: float, prosperity: float, hunger: float, r: float,
             params) -> Tuple[ClassMix, float, float]:
    """One recount of slow drift: -> (new mix, dpoor, drich). A signal inside the dead zone moves nobody."""
    score = mobility_score(stability, prosperity, hunger, r, params)
    dz = _clamp(float(params.mob_dead_zone), 0.0, 0.99)
    if score > dz:
        up = float(params.mob_rate_up) * (score - dz) / (1.0 - dz)
        return shift(mix, up, 0.0, params.mob_rich_factor, params.class_share_min, params.class_share_max)
    if score < -dz:
        down = float(params.mob_rate_down) * (-score - dz) / (1.0 - dz)
        return shift(mix, 0.0, down, params.mob_rich_factor, params.class_share_min, params.class_share_max)
    return mix, 0.0, 0.0


def event_shift(mix: ClassMix, delta: float, params) -> Tuple[ClassMix, float, float]:
    """One-shot ``class_shift`` of an event (3.15): delta > 0 up, delta < 0 down, same bounds as mobility."""
    delta = float(delta)
    if delta > 0:
        return shift(mix, delta, 0.0, params.mob_rich_factor, params.class_share_min, params.class_share_max)
    if delta < 0:
        return shift(mix, 0.0, -delta, params.mob_rich_factor, params.class_share_min, params.class_share_max)
    return mix, 0.0, 0.0


# --------------------------------------------------------------------------------------------- deficit (3.9)

def deficit(wealth_norm_value: int, treasury_target: int, purse: int, treasury: int) -> int:
    """Money below the region's norm: ``max(0, norm + max(0, target) − max(0, purse) − treasury)``."""
    return max(0, int(wealth_norm_value) + max(0, int(treasury_target)) - max(0, int(purse)) - int(treasury))


# --------------------------------------------------------------------------------------------- card (3.11)

def _gender_index(gender: Optional[str]) -> int:
    return {"m": 0, "f": 1, "n": 2}.get((gender or "m").lower(), 0)


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def class_index(mix: ClassMix) -> float:
    return float(mix.middling) * 0.5 + float(mix.rich)


def class_state(mix: ClassMix) -> str:
    index = class_index(mix)
    if index < CLASS_INDEX_MODEST:
        return "poor"
    if index < CLASS_INDEX_WEALTHY:
        return "modest"
    if index < CLASS_INDEX_RICH:
        return "wealthy"
    return "rich"


def class_bar(mix: ClassMix) -> Dict[str, str]:
    """{class: few|some|many} — words only, the page draws the widths."""
    bar = {}
    for name, share in zip(CLASSES, mix.as_tuple()):
        if share < BAR_SOME[name]:
            bar[name] = "few"
        elif share < BAR_MANY[name]:
            bar[name] = "some"
        else:
            bar[name] = "many"
    return bar


def class_phrase(mix: ClassMix, noun: str = "Регион", gender: str = "m") -> str:
    """«Зажиточный город, много бедняков», «Бедная округа», «Богатый город»."""
    state = class_state(mix)
    label = f"{CLASS_ADJ[state][_gender_index(gender)]} {_lower_first(noun)}"
    if float(mix.poor) >= CLASS_TAIL_POOR and state != "poor":
        label += TAIL_POOR
    elif float(mix.rich) >= CLASS_TAIL_RICH and state != "rich":
        label += TAIL_RICH
    return label


def class_card(mix: ClassMix, noun: str = "Регион", gender: str = "m") -> Dict:
    return {"state": class_state(mix), "label": class_phrase(mix, noun, gender), "bar": class_bar(mix)}


# --------------------------------------------------------------------------------------------- admin report (3.13)

def class_report(*, mix: ClassMix, base: ClassMix, population: float, norm_parts: Sequence[float],
                 cost_parts_day: Sequence[float], purse: int, treasury: int, treasury_target: int,
                 params) -> Dict:
    """Admin view of one region: per class share / norm / money / needs / afford (per simulated resident).

    ``cost_parts_day`` = the class parts of one day of household demand at the current prices.
    """
    norm_total = int(math.floor(max(0.0, sum(norm_parts))))
    money = split_money(purse, norm_parts if sum(norm_parts) > 0 else cost_parts_day)
    days = norm_days(params)
    classes = {}
    for k, name in enumerate(CLASSES):
        share = mix.as_tuple()[k]
        residents = float(population) * share
        per = (lambda v: round(v / residents, 4) if residents > 0 else 0.0)
        classes[name] = {
            "share": round(share, 6),
            "base_share": round(base.as_tuple()[k], 6),
            "norm_days": days[k],
            "norm_per_resident": per(norm_parts[k]),
            "money_per_resident": per(money[k]),
            "needs_per_resident_day": per(cost_parts_day[k]),
            "afford": round(class_afford(money[k], cost_parts_day[k], params.afford_days), 4),
        }
    target = max(0, int(treasury_target))
    return {
        "classes": classes,
        "wealth_norm": norm_total,
        "money_norm": norm_total + target,
        "deficit": deficit(norm_total, target, purse, treasury),
        "r": round(max(0, int(purse)) / norm_total, 4) if norm_total > 0 else None,
    }
