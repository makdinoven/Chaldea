"""FEAT-197 region reputation — pure maths (no I/O, no project imports).

Canonical copy: ``services/character-service/app/reputation_core.py``. A byte-identical copy lives in
locations-service (guarded by ``scripts/check_econ_copies.sh``) so both services compute tiers, decay and
progress the same way. Keep this module free of imports from either service.

Model (features/FEAT-197 §3.1-3.2):

* a value per (character, region) in ``[Settings.min_value, Settings.max_value]``; no row = 0;
* 8 tiers with FIXED codes (:data:`TIER_CODES`); the admin edits names / thresholds / price modifiers only;
* only a negative value decays toward 0, ``decay_per_day`` points per day counted from ``decay_at``;
  readers use :func:`effective_value`, writers materialise with :func:`materialise_decay` (the anchor moves by
  exactly the time the materialised points took, so frequent runs never lose fractions);
* an echo of an automatic change goes to the other regions of the same country (:func:`echo_delta`).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_FLOOR
from typing import Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------------------------------- constants

TIER_CODES = ("outlaw", "outcast", "watched", "wanderer", "familiar", "trusted", "defender", "legend")
START_TIER = "wanderer"                 # the band that must contain 0 (a character without a row)
OUTLAW_TIER = "outlaw"

SECONDS_PER_DAY = 86400

MAX_DISCOUNT_PCT = Decimal(50)          # price_pct upper bound (the econ_core 50 % discount cap)
MAX_MARKUP_PCT = Decimal(100)           # price_pct lower bound is -100 (markup)
MIN_SELL_PCT = Decimal(-100)            # sell_pct in [-100, 0]: low tiers get less from merchants, never more
MAX_ECHO_PCT = Decimal(100)
MAX_DECAY_PER_DAY = Decimal(1000)
VALUE_LIMIT = 100000                    # |min_value| / |max_value| sanity bound for settings

# action codes referenced from code (reputation_actions.is_builtin = 1)
ACTION_QUEST = "quest_complete"
ACTION_GUILD = "guild_delivery"
ACTION_NPC_KILL = "npc_kill"
ACTION_REGION_EVENT = "region_event_help"
ACTION_CARAVAN = "caravan_attack"
ACTION_CRIME = "crime"
ACTION_ADMIN = "admin_manual"
ACTION_DECAY = "decay"                  # journal-only pseudo action (never a row of reputation_actions)
DECAY_ACTION_NAME = "Забвение"

ROLE_FALLBACK = "*"                     # reputation_npc_role_weights: any other / NULL role

DIRECTION_UP = "up"
DIRECTION_DOWN = "down"
DIRECTION_DECAY = "decay"

ACTION_CODE_RE = r"^[a-z][a-z0-9_]{2,39}$"
ROLE_RE = r"^(\*|[a-z][a-z0-9_]{0,49})$"


# --------------------------------------------------------------------------------------------------- value objects

@dataclass(frozen=True)
class Tier:
    code: str
    sort_order: int
    name: str
    min_value: Optional[int]            # inclusive lower bound; None only for the lowest tier
    price_pct: Decimal = Decimal(0)     # > 0 discount, < 0 markup (merchant asks)
    sell_pct: Decimal = Decimal(0)      # <= 0: what merchants pay the player is lowered by this percent
    trade_refused: bool = False         # merchants (and the guild) refuse to deal


@dataclass(frozen=True)
class Settings:
    min_value: int = -1000
    max_value: int = 1000
    echo_pct: Decimal = Decimal(20)
    decay_per_day: Decimal = Decimal(10)


DEFAULT_SETTINGS = Settings()

DEFAULT_TIERS: Tuple[Tier, ...] = (
    Tier("outlaw", 1, "Вне закона", None, Decimal(0), Decimal(0), True),
    Tier("outcast", 2, "Изгой", -599, Decimal(-25), Decimal(-25), False),
    Tier("watched", 3, "На заметке", -299, Decimal(-10), Decimal(-10), False),
    Tier("wanderer", 4, "Скиталец", -99, Decimal(0), Decimal(0), False),
    Tier("familiar", 5, "Знакомое лицо", 100, Decimal(0), Decimal(0), False),
    Tier("trusted", 6, "Свой человек", 300, Decimal(5), Decimal(0), False),
    Tier("defender", 7, "Заступник", 600, Decimal(10), Decimal(0), False),
    Tier("legend", 8, "Легенда края", 900, Decimal(15), Decimal(0), False),
)

# (code, name, points, daily_cap, has_source, sort_order) — all builtin
DEFAULT_ACTIONS: Tuple[Tuple[str, str, int, Optional[int], bool, int], ...] = (
    (ACTION_QUEST, "Выполнено задание", 10, None, True, 10),
    (ACTION_GUILD, "Поставка по заказу гильдии", 2, 20, True, 20),
    (ACTION_NPC_KILL, "Убийство жителя", 0, None, True, 30),
    (ACTION_REGION_EVENT, "Помощь краю", 5, None, False, 40),
    (ACTION_CARAVAN, "Нападение на караван", -100, None, True, 50),
    (ACTION_CRIME, "Преступление", -50, None, False, 60),
    (ACTION_ADMIN, "Решение властей", 0, None, False, 70),
)
BUILTIN_ACTION_CODES = tuple(a[0] for a in DEFAULT_ACTIONS)

_PEACEFUL_ROLES = ("merchant", "blacksmith", "alchemist", "bard", "sage", "priest", "healer", "hunter", "wanderer",
                   "auctioneer", "banker", "minter", "guild", "teleport_master", "hero")
DEFAULT_NPC_ROLE_WEIGHTS: Dict[str, int] = {
    "bandit": 20,
    "mercenary": -30,
    "guard": -300,
    "ruler": -1000,
    "king": -1000,
    **{role: -150 for role in _PEACEFUL_ROLES},
    ROLE_FALLBACK: -150,
}


# --------------------------------------------------------------------------------------------------- SQL (shared)

SQL_SELECT_SETTINGS = (
    "SELECT min_value, max_value, echo_pct, decay_per_day FROM reputation_settings WHERE id = 1"
)
SQL_SELECT_TIERS = (
    "SELECT code, sort_order, name, min_value, price_pct, sell_pct, trade_refused FROM reputation_tiers "
    "ORDER BY sort_order"
)
SQL_SELECT_VALUE = (
    "SELECT value, decay_at FROM character_reputation WHERE character_id = :character_id AND region_id = :region_id"
)


# --------------------------------------------------------------------------------------------------- helpers

def _dec(value) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def settings_from_row(row) -> Settings:
    """Row of :data:`SQL_SELECT_SETTINGS` (None -> defaults)."""
    if row is None:
        return DEFAULT_SETTINGS
    return Settings(min_value=int(row[0]), max_value=int(row[1]), echo_pct=_dec(row[2]), decay_per_day=_dec(row[3]))


def tiers_from_rows(rows) -> List[Tier]:
    """Rows of :data:`SQL_SELECT_TIERS`; the defaults unless all 8 fixed codes are present."""
    tiers = [Tier(code=str(r[0]), sort_order=int(r[1]), name=str(r[2]),
                  min_value=int(r[3]) if r[3] is not None else None,
                  price_pct=_dec(r[4]), sell_pct=_dec(r[5]), trade_refused=bool(r[6])) for r in rows or ()]
    if sorted(t.code for t in tiers) != sorted(TIER_CODES):
        return list(DEFAULT_TIERS)
    return sorted(tiers, key=lambda t: t.sort_order)


def clamp(value: int, settings: Settings) -> int:
    return max(int(settings.min_value), min(int(settings.max_value), int(value)))


# --------------------------------------------------------------------------------------------------- decay

def materialise_decay(value: int, decay_at: Optional[datetime], now: datetime,
                      decay_per_day) -> Tuple[int, Optional[datetime], int]:
    """Negative decay up to ``now``: ``(new_value, new_decay_at, points)``.

    ``points = floor(per_day * elapsed / day)`` capped at ``-value``. The anchor advances by exactly the time those
    points took (whole seconds, rounded down — never in the player's disfavour), so the remainder carries over to
    the next call. ``new_decay_at`` is None once the value reaches 0. Non-negative values / no anchor / a zero rate
    are returned unchanged."""
    value = int(value)
    per_day = _dec(decay_per_day)
    if isinstance(decay_at, str):           # raw SQL on drivers without DATETIME conversion (SQLite)
        decay_at = datetime.fromisoformat(decay_at)
    if value >= 0:
        return value, None, 0
    if decay_at is None or per_day <= 0 or now <= decay_at:
        return value, decay_at, 0
    elapsed = Decimal((now - decay_at).total_seconds())
    points = int((per_day * elapsed / SECONDS_PER_DAY).to_integral_value(rounding=ROUND_FLOOR))
    points = max(0, min(points, -value))
    if points == 0:
        return value, decay_at, 0
    new_value = value + points
    if new_value >= 0:
        return 0, None, points
    took = int((Decimal(points) * SECONDS_PER_DAY / per_day).to_integral_value(rounding=ROUND_FLOOR))
    return new_value, decay_at + timedelta(seconds=took), points


def effective_value(value: int, decay_at: Optional[datetime], now: datetime, decay_per_day) -> int:
    """The value readers must use (stored value with the negative decay applied up to ``now``)."""
    return materialise_decay(value, decay_at, now, decay_per_day)[0]


def next_decay_at(old_value: int, new_value: int, decay_at: Optional[datetime], now: datetime) -> Optional[datetime]:
    """Anchor after a change ``old_value -> new_value`` (``old_value`` already materialised)."""
    if new_value >= 0:
        return None
    if old_value >= 0 or decay_at is None:
        return now
    return decay_at


# --------------------------------------------------------------------------------------------------- tiers

def sorted_tiers(tiers: Sequence[Tier]) -> List[Tier]:
    return sorted(tiers, key=lambda t: t.sort_order)


def tier_for(value: int, tiers: Sequence[Tier]) -> Tier:
    """The highest tier whose lower bound is <= value (the lowest tier when none)."""
    ordered = sorted_tiers(tiers)
    current = ordered[0]
    for tier in ordered[1:]:
        if tier.min_value is not None and int(value) >= tier.min_value:
            current = tier
    return current


def tier_by_code(code: Optional[str], tiers: Sequence[Tier]) -> Optional[Tier]:
    for tier in tiers:
        if tier.code == code:
            return tier
    return None


def tier_rank(code: Optional[str], tiers: Sequence[Tier]) -> Optional[int]:
    tier = tier_by_code(code, tiers)
    return tier.sort_order if tier is not None else None


def meets(value: int, min_code: Optional[str], tiers: Sequence[Tier]) -> bool:
    """Does ``value`` reach the tier ``min_code``? Unknown / empty code = no gate."""
    need = tier_rank(min_code, tiers) if min_code else None
    if need is None:
        return True
    return tier_for(value, tiers).sort_order >= need


def gate_message(min_code: Optional[str], tiers: Sequence[Tier]) -> str:
    tier = tier_by_code(min_code, tiers)
    return f"Нужна репутация: {tier.name if tier is not None else min_code}"


def band(tier: Tier, tiers: Sequence[Tier], settings: Settings) -> Tuple[int, int]:
    """``[lo, hi)`` of the tier; the outer tiers use the settings range as the open bound."""
    ordered = sorted_tiers(tiers)
    lo = tier.min_value if tier.min_value is not None else int(settings.min_value)
    hi = int(settings.max_value)
    for other in ordered:
        if other.sort_order > tier.sort_order and other.min_value is not None:
            hi = other.min_value
            break
    return lo, hi


def progress(value: int, tiers: Sequence[Tier], settings: Settings) -> float:
    """Position of ``value`` inside its tier band, 0..1 (3 decimals); the top tier is full at ``max_value``."""
    tier = tier_for(value, tiers)
    lo, hi = band(tier, tiers, settings)
    if hi <= lo:
        return 1.0
    frac = (int(value) - lo) / float(hi - lo)
    return round(max(0.0, min(1.0, frac)), 3)


def tier_price_pct(value: int, tiers: Sequence[Tier]) -> Decimal:
    """Signed ask modifier of the tier: > 0 discount, < 0 markup."""
    return _dec(tier_for(value, tiers).price_pct)


def tier_sell_pct(value: int, tiers: Sequence[Tier]) -> Decimal:
    """Bid modifier of the tier, always <= 0."""
    return min(Decimal(0), _dec(tier_for(value, tiers).sell_pct))


def trade_refused(value: int, tiers: Sequence[Tier]) -> bool:
    return bool(tier_for(value, tiers).trade_refused)


# --------------------------------------------------------------------------------------------------- deltas

def echo_delta(delta: int, echo_pct) -> int:
    """``delta * pct / 100`` truncated toward zero."""
    raw = Decimal(int(delta)) * _dec(echo_pct) / Decimal(100)
    return int(raw)                      # int() of a Decimal truncates toward zero


def kill_points(override: Optional[int], role: Optional[str], weights: Dict[str, int]) -> int:
    """Kill weight of an NPC: the per-NPC override, else its role weight, else the ``*`` weight."""
    if override is not None:
        return int(override)
    if role and role in weights:
        return int(weights[role])
    if ROLE_FALLBACK in weights:
        return int(weights[ROLE_FALLBACK])
    return int(DEFAULT_NPC_ROLE_WEIGHTS[ROLE_FALLBACK])


def direction(delta: int) -> str:
    return DIRECTION_UP if int(delta) > 0 else DIRECTION_DOWN


# --------------------------------------------------------------------------------------------------- validation

def validate(settings: Settings, tiers: Sequence[Tier]) -> Optional[str]:
    """Russian error text for an invalid settings / tiers set, else None."""
    if not (-VALUE_LIMIT <= settings.min_value < 0 < settings.max_value <= VALUE_LIMIT):
        return "Диапазон репутации должен включать 0 (минимум < 0 < максимум)"
    if not (Decimal(0) <= _dec(settings.echo_pct) <= MAX_ECHO_PCT):
        return "Отголосок — от 0 до 100 %"
    if not (Decimal(0) <= _dec(settings.decay_per_day) <= MAX_DECAY_PER_DAY):
        return "Скорость забывания — от 0 до 1000 очков в день"
    codes = [t.code for t in tiers]
    if sorted(codes) != sorted(TIER_CODES) or len(set(codes)) != len(TIER_CODES):
        return "Нужны ровно 8 ступеней с фиксированными кодами"
    ordered = sorted_tiers(tiers)
    if [t.sort_order for t in ordered] != list(range(1, len(TIER_CODES) + 1)) or \
            [t.code for t in ordered] != list(TIER_CODES):
        return "Порядок ступеней менять нельзя"
    previous = settings.min_value
    for i, tier in enumerate(ordered):
        name = (tier.name or "").strip()
        if not name or len(name) > 60:
            return "Название ступени — от 1 до 60 символов"
        if i == 0:
            if tier.min_value is not None:
                return f"У нижней ступени «{name}» нет нижнего порога"
        else:
            if tier.min_value is None:
                return f"У ступени «{name}» должен быть нижний порог"
            if not (previous < tier.min_value <= settings.max_value):
                return f"Пороги ступеней должны строго возрастать в пределах диапазона («{name}»)"
            previous = tier.min_value
        if not (-MAX_MARKUP_PCT <= _dec(tier.price_pct) <= MAX_DISCOUNT_PCT):
            return f"Цена у торговцев для «{name}» — от −100 до +50 %"
        if not (MIN_SELL_PCT <= _dec(tier.sell_pct) <= Decimal(0)):
            return f"Скупка у «{name}» — от −100 до 0 %"
    if tier_for(0, ordered).code != START_TIER:
        return "Стартовая ступень «Скиталец» должна включать 0"
    return None
