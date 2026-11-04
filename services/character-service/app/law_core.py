"""FEAT-198 law (reputation stage 2a) — pure maths (no I/O, no project imports).

Only character-service computes wanted levels; other services see the law through the activity lock
(``characters.jailed_until`` / ``characters.law_encounter_id``).

Model (features/FEAT-198 §3.1-3.2, §3.14-ANSWERED):

* wanted = a positive value per (character, region) in ``[0, max_wanted]``; no row = 0;
* it decays linearly toward 0, ``decay_per_day`` points per day counted from ``decay_at``; readers use
  :func:`effective_wanted`, writers :func:`materialise` (the anchor advances by exactly the time the consumed points
  took, so frequent writes never lose fractions — the same rule as ``reputation_core.materialise_decay``);
* 5 severity levels with FIXED codes (:data:`LEVEL_CODES`), editable name / threshold / fine / jail term;
* the guard encounter offers :func:`options`; flee / escape chances come from agility + luck (:func:`chance`;
  FEAT-199: the EFFECTIVE values after the FEAT-195 caps).
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------------------------------- constants

LEVEL_CODES = ("suspect", "offender", "criminal", "villain", "enemy")

SECONDS_PER_DAY = 86400

GUARD_ROLE = "guard"
BANKER_ROLE = "banker"

# crime types (law_crimes.crime_type)
CRIME_NPC_KILL = "npc_kill"
CRIME_GUARD_DEFEAT = "guard_defeat"
CRIME_JAIL_ESCAPE = "jail_escape"
# reserved for future sources (no source in 2a)
CRIME_CARAVAN_ATTACK = "caravan_attack"
CRIME_PVP_ATTACK = "pvp_attack"
CRIME_THEFT = "theft"

# crime statuses: 2a applies every crime at once; 2b (FEAT-199) defers unwitnessed / masked crimes
CRIME_REPORTED = "reported"
CRIME_UNWITNESSED = "unwitnessed"
CRIME_MASKED = "masked"
CRIME_CLOSED = "closed"
CRIME_OPEN = (CRIME_UNWITNESSED, CRIME_MASKED)
CRIME_STATUSES = (CRIME_REPORTED, CRIME_UNWITNESSED, CRIME_MASKED, CRIME_CLOSED)

# encounter choices (the order of options())
CHOICE_FINE = "fine"
CHOICE_SURRENDER = "surrender"
CHOICE_FLEE = "flee"
CHOICE_FIGHT = "fight"
CHOICES = (CHOICE_FINE, CHOICE_SURRENDER, CHOICE_FLEE, CHOICE_FIGHT)

# encounter statuses
ENC_PENDING = "pending"
ENC_FIGHTING = "fighting"
ENC_FINED = "fined"
ENC_JAILED = "jailed"
ENC_FLED = "fled"
ENC_WON = "won"
ENC_AUTO_FINED = "auto_fined"
ENC_CANCELLED = "cancelled"
ENC_GUARD_GONE = "guard_gone"
ENC_OPEN = (ENC_PENDING, ENC_FIGHTING)

# encounter sources
SOURCE_MOVE = "move"
SOURCE_QUICK_MOVE = "quick_move"
SOURCE_TELEPORT = "teleport"
MOVE_SOURCES = (SOURCE_MOVE, SOURCE_QUICK_MOVE)

# jail term statuses
JAIL_SERVING = "serving"
JAIL_SERVED = "served"
JAIL_BAILED = "bailed"
JAIL_ESCAPED = "escaped"
JAIL_RELEASED = "released"

# law_log actions
LOG_CRIME = "crime"
LOG_ENCOUNTER = "encounter"
LOG_FINE = "fine"
LOG_SURRENDER = "surrender"
LOG_JAIL = "jail"
LOG_FLEE_OK = "flee_ok"
LOG_FLEE_FAIL = "flee_fail"
LOG_FIGHT = "fight"
LOG_FIGHT_WON = "fight_won"
LOG_FIGHT_LOST = "fight_lost"
LOG_FIGHT_ABORTED = "fight_aborted"
LOG_ESCAPE_OK = "escape_ok"
LOG_ESCAPE_FAIL = "escape_fail"
LOG_BAIL = "bail"
LOG_SERVED = "served"
LOG_AUTO_SURRENDER = "auto_surrender"
LOG_AUTO_FINE = "auto_fine"
LOG_STAFF_RELEASE = "staff_release"
LOG_STAFF_CLEAR = "staff_clear"
LOG_STAFF_CANCEL = "staff_cancel"
LOG_GUARD_KO = "guard_ko"
LOG_GUARD_GONE = "guard_gone"
LOG_CHOICE = "choice"
# FEAT-199: deferred crimes
LOG_REVEAL = "reveal"
LOG_REVEAL_FAIL = "reveal_fail"
LOG_CRIME_CLOSED = "crime_closed"
LOG_STAFF_REVEAL = "staff_reveal"
LOG_STAFF_CLOSE = "staff_close"

# §3.14-ANSWERED A7: after a successful flee the guards of that location leave the character alone this long
FLEE_GUARD_COOLDOWN = timedelta(hours=1)

# settings bounds (§3.1, §3.14-ANSWERED A1)
MAX_JAIL_HOURS = 168
MAX_FINE = 1_000_000
MAX_WANTED_LIMIT = 100_000
MAX_DECAY_PER_DAY = Decimal(100_000)
MAX_HOURS = 168
MIN_BAIL_MULTIPLIER = Decimal(1)
MAX_BAIL_MULTIPLIER = Decimal(10)
MAX_PER_POINT_PCT = Decimal(100)

_CENT = Decimal("0.01")


# --------------------------------------------------------------------------------------------------- value objects

@dataclass(frozen=True)
class Level:
    code: str
    sort_order: int
    name: str
    min_value: int              # inclusive lower bound of wanted; level 1 >= 1
    fine: int
    jail_hours: int


@dataclass(frozen=True)
class LawSettings:
    max_wanted: int = 1000
    decay_per_day: Decimal = Decimal(50)
    heavy_wanted: int = 600
    outlaw_min_level: str = "criminal"
    encounter_timeout_hours: int = 24
    guard_ko_hours: int = 6
    flee_base_pct: Decimal = Decimal(20)
    flee_per_point_pct: Decimal = Decimal("0.25")
    flee_min_pct: Decimal = Decimal(5)
    flee_max_pct: Decimal = Decimal(85)
    escape_base_pct: Decimal = Decimal(5)
    escape_per_point_pct: Decimal = Decimal("0.15")
    escape_min_pct: Decimal = Decimal(2)
    escape_max_pct: Decimal = Decimal(50)
    escape_cooldown_hours: int = 6
    escape_fail_extend_pct: Decimal = Decimal(50)
    max_remaining_jail_hours: int = 168
    bail_multiplier: Decimal = Decimal(2)


DEFAULT_SETTINGS = LawSettings()

DEFAULT_LEVELS: Tuple[Level, ...] = (
    Level("suspect", 1, "Подозреваемый", 1, 50, 2),
    Level("offender", 2, "Нарушитель", 100, 150, 12),
    Level("criminal", 3, "Преступник", 300, 400, 24),
    Level("villain", 4, "Злодей", 600, 1000, 72),
    Level("enemy", 5, "Враг края", 900, 2500, 168),
)

SETTINGS_FIELDS = (
    "max_wanted", "decay_per_day", "heavy_wanted", "outlaw_min_level", "encounter_timeout_hours", "guard_ko_hours",
    "flee_base_pct", "flee_per_point_pct", "flee_min_pct", "flee_max_pct", "escape_base_pct", "escape_per_point_pct",
    "escape_min_pct", "escape_max_pct", "escape_cooldown_hours", "escape_fail_extend_pct", "max_remaining_jail_hours",
    "bail_multiplier",
)
_DECIMAL_FIELDS = frozenset({
    "decay_per_day", "flee_base_pct", "flee_per_point_pct", "flee_min_pct", "flee_max_pct", "escape_base_pct",
    "escape_per_point_pct", "escape_min_pct", "escape_max_pct", "escape_fail_extend_pct", "bail_multiplier",
})


# --------------------------------------------------------------------------------------------------- SQL (shared)

SQL_SELECT_SETTINGS = "SELECT " + ", ".join(SETTINGS_FIELDS) + " FROM law_settings WHERE id = 1"
SQL_SELECT_LEVELS = "SELECT code, sort_order, name, min_value, fine, jail_hours FROM law_levels ORDER BY sort_order"


# --------------------------------------------------------------------------------------------------- helpers

def _dec(value) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def settings_from_row(row) -> LawSettings:
    """A ``SQL_SELECT_SETTINGS`` row (or None = defaults)."""
    if row is None:
        return DEFAULT_SETTINGS
    values = {}
    for index, name in enumerate(SETTINGS_FIELDS):
        raw = row[index]
        if name in _DECIMAL_FIELDS:
            values[name] = _dec(raw)
        elif name == "outlaw_min_level":
            values[name] = str(raw)
        else:
            values[name] = int(raw)
    return LawSettings(**values)


def levels_from_rows(rows) -> List[Level]:
    """``SQL_SELECT_LEVELS`` rows; an empty table (fresh test DB) = the defaults."""
    levels = [Level(str(r[0]), int(r[1]), str(r[2]), int(r[3]), int(r[4]), int(r[5])) for r in rows or ()]
    return sorted(levels, key=lambda lv: lv.sort_order) if levels else list(DEFAULT_LEVELS)


def _as_datetime(value) -> Optional[datetime]:
    if isinstance(value, str):              # raw SQL on drivers without DATETIME conversion (SQLite)
        return datetime.fromisoformat(value)
    return value


# --------------------------------------------------------------------------------------------------- wanted

def materialise(value: int, decay_at, now: datetime, per_day) -> Tuple[int, Optional[datetime]]:
    """Decay up to ``now``: ``(new_value, new_decay_at)``. The anchor advances by exactly the time the consumed points
    took (whole seconds, rounded down — never in the player's disfavour); ``None`` at 0. A zero rate / no anchor /
    a value of 0 are returned unchanged (anchor None at 0)."""
    value = max(0, int(value or 0))
    decay_at = _as_datetime(decay_at)
    per_day = _dec(per_day)
    if value == 0:
        return 0, None
    if decay_at is None or per_day <= 0 or now <= decay_at:
        return value, decay_at
    elapsed = Decimal((now - decay_at).total_seconds())
    points = int((per_day * elapsed / SECONDS_PER_DAY).to_integral_value(rounding=ROUND_FLOOR))
    points = max(0, min(points, value))
    if points == 0:
        return value, decay_at
    new_value = value - points
    if new_value <= 0:
        return 0, None
    took = int((Decimal(points) * SECONDS_PER_DAY / per_day).to_integral_value(rounding=ROUND_FLOOR))
    return new_value, decay_at + timedelta(seconds=took)


def effective_wanted(value: int, decay_at, now: datetime, per_day) -> int:
    """The value readers must use."""
    return materialise(value, decay_at, now, per_day)[0]


def add_wanted(effective: int, gain: int, settings: LawSettings, floor: Optional[int] = None) -> int:
    """``min(max_wanted, max(effective + gain, floor or 0))``."""
    return min(int(settings.max_wanted), max(int(effective) + int(gain), int(floor or 0), 0))


def next_decay_at(old_value: int, new_value: int, decay_at, now: datetime) -> Optional[datetime]:
    """Anchor after a change ``old_value -> new_value`` (``old_value`` already materialised)."""
    if new_value <= 0:
        return None
    if old_value <= 0 or decay_at is None:
        return now
    return _as_datetime(decay_at)


def crime_weight(kill_points: int) -> int:
    """Wanted points of a kill = ``-kill_points`` of the reputation weight; only negative weights are crimes
    (a bandit, +20, is not)."""
    kill_points = int(kill_points or 0)
    return -kill_points if kill_points < 0 else 0


# --------------------------------------------------------------------------------------------------- levels

def sorted_levels(levels: Sequence[Level]) -> List[Level]:
    return sorted(levels, key=lambda lv: lv.sort_order)


def level_by_code(code: Optional[str], levels: Sequence[Level]) -> Optional[Level]:
    for lv in levels:
        if lv.code == code:
            return lv
    return None


def level_for(value: int, levels: Sequence[Level]) -> Optional[Level]:
    """The highest level whose ``min_value <= value``; None for 0 (not wanted)."""
    value = int(value or 0)
    if value <= 0:
        return None
    found = None
    for lv in sorted_levels(levels):
        if value >= lv.min_value:
            found = lv
    return found or sorted_levels(levels)[0]


def level_at_least(level: Optional[Level], code: Optional[str], levels: Sequence[Level]) -> Optional[Level]:
    """``level`` raised to at least the level ``code`` (an unknown code leaves it unchanged)."""
    floor = level_by_code(code, levels)
    if floor is None:
        return level
    if level is None or level.sort_order < floor.sort_order:
        return floor
    return level


# --------------------------------------------------------------------------------------------------- encounter

def options(is_outlaw: bool, has_jail: bool, flee_used: bool) -> List[str]:
    """Ordered choices of a guard encounter (§3.2, user decisions 1-2)."""
    out: List[str] = []
    if not is_outlaw:
        out.append(CHOICE_FINE)
    if has_jail:
        out.append(CHOICE_SURRENDER)
    if not is_outlaw and not flee_used:
        out.append(CHOICE_FLEE)
    out.append(CHOICE_FIGHT)
    return out


def chance(base, per_point, lo, hi, agility, luck) -> Decimal:
    """``clamp(base + (agility + luck) * per_point, lo, hi)`` percent, 2 decimals. Agility / luck may be Decimal
    (FEAT-199: the effective values after the FEAT-195 caps); integers give the same result as before."""
    points = max(Decimal(0), _dec(agility)) + max(Decimal(0), _dec(luck))
    raw = _dec(base) + points * _dec(per_point)
    raw = max(_dec(lo), min(_dec(hi), raw))
    return raw.quantize(_CENT, rounding=ROUND_HALF_UP)


def roll_succeeds(chance_pct, rng) -> Tuple[bool, Decimal]:
    """A server-side roll in [0, 100) (2 decimals); success when ``roll < chance``. ``rng`` has ``random()``."""
    roll = (Decimal(str(rng.random())) * 100).quantize(_CENT, rounding=ROUND_FLOOR)
    if roll >= 100:
        roll = Decimal("99.99")
    return roll < _dec(chance_pct), roll


# --------------------------------------------------------------------------------------------------- jail

def extended_until(now: datetime, until: datetime, pct, cap_hours: int) -> datetime:
    """A failed escape: ``max(until, now + min(remaining * (1 + pct / 100), cap))`` (§3.14-ANSWERED A4).

    The cap only limits the growth: a cap below the remaining term never shortens it (failing must not pay off)."""
    until = _as_datetime(until)
    remaining = max(0.0, (until - now).total_seconds())
    extended = Decimal(str(remaining)) * (Decimal(1) + _dec(pct) / Decimal(100))
    cap = Decimal(int(cap_hours) * 3600)
    seconds = int(min(extended, cap).to_integral_value(rounding=ROUND_FLOOR))
    return max(until, now + timedelta(seconds=seconds))


def bail_price(fine_base: int, multiplier) -> int:
    """``max(1, ceil(fine_base * multiplier))``."""
    return max(1, int(math.ceil(Decimal(int(fine_base or 0)) * _dec(multiplier))))


# --------------------------------------------------------------------------------------------------- validation

def _pct_ok(value) -> bool:
    return Decimal(0) <= _dec(value) <= Decimal(100)


def validate(settings: LawSettings, levels: Sequence[Level]) -> Optional[str]:
    """Russian error text for invalid settings / levels, else None (§3.1)."""
    if not (1 <= int(settings.max_wanted) <= MAX_WANTED_LIMIT):
        return f"Максимальный розыск должен быть от 1 до {MAX_WANTED_LIMIT}"
    if not (Decimal(0) <= _dec(settings.decay_per_day) <= MAX_DECAY_PER_DAY):
        return "Спад розыска в день должен быть не меньше 0"
    if not (1 <= int(settings.heavy_wanted) <= int(settings.max_wanted)):
        return "Порог тяжёлого розыска должен быть от 1 до максимального розыска"
    if settings.outlaw_min_level not in LEVEL_CODES:
        return "Неизвестная ступень розыска для «Вне закона»"
    for name, label in (("encounter_timeout_hours", "Время на ответ страже"),
                        ("guard_ko_hours", "Время восстановления стражника"),
                        ("escape_cooldown_hours", "Перерыв между побегами"),
                        ("max_remaining_jail_hours", "Предел срока после неудачного побега")):
        if not (1 <= int(getattr(settings, name)) <= MAX_HOURS):
            return f"{label}: от 1 до {MAX_HOURS} часов"
    for prefix, label in (("flee", "Шанс бегства"), ("escape", "Шанс побега")):
        base, lo, hi = (getattr(settings, f"{prefix}_{k}_pct") for k in ("base", "min", "max"))
        per_point = getattr(settings, f"{prefix}_per_point_pct")
        if not (_pct_ok(base) and _pct_ok(lo) and _pct_ok(hi)):
            return f"{label}: проценты должны быть от 0 до 100"
        if _dec(lo) > _dec(hi):
            return f"{label}: минимум не может быть больше максимума"
        if not (Decimal(0) <= _dec(per_point) <= MAX_PER_POINT_PCT):
            return f"{label}: прибавка за очко должна быть от 0 до 100"
    if not (Decimal(0) <= _dec(settings.escape_fail_extend_pct) <= Decimal(1000)):
        return "Продление срока после неудачного побега: от 0 до 1000 %"
    if not (MIN_BAIL_MULTIPLIER <= _dec(settings.bail_multiplier) <= MAX_BAIL_MULTIPLIER):
        return "Множитель залога должен быть от 1 до 10"

    codes = [lv.code for lv in levels]
    if sorted(codes) != sorted(LEVEL_CODES) or len(codes) != len(LEVEL_CODES):
        return "Нужны ровно 5 ступеней розыска"
    previous = 0
    for lv in sorted(levels, key=lambda x: LEVEL_CODES.index(x.code)):
        if not lv.name or not lv.name.strip() or len(lv.name.strip()) > 60:
            return "Название ступени розыска: от 1 до 60 символов"
        if int(lv.min_value) <= previous:
            return "Пороги ступеней розыска должны строго возрастать и начинаться с 1"
        if int(lv.min_value) > int(settings.max_wanted):
            return "Порог ступени розыска не может превышать максимальный розыск"
        if not (0 <= int(lv.fine) <= MAX_FINE):
            return f"Штраф должен быть от 0 до {MAX_FINE}"
        if not (1 <= int(lv.jail_hours) <= MAX_JAIL_HOURS):
            return f"Срок заключения должен быть от 1 до {MAX_JAIL_HOURS} часов"
        previous = int(lv.min_value)
    return None
