"""FEAT-199 the shadow (reputation stage 2b) — pure maths (no I/O; character-service only, no copies).

* witnesses (FEAT-201, multiplicative): per member ``base(Locations.marker_type) × (1 − stealth reduction) ×
  (1 + fame%)`` (fame = recognisability; ignored for a masked member — the mask is anonymity only). The stealth
  reduction is ``min(max, effective stealth × per point)``, where effective = the FEAT-195 cap of (stored stealth +
  subclass stealth points). The GROUP chance is the highest member chance (least stealthy) × (1 + per-extra% ×
  (n − 1)), clamped (:func:`member_chance`, :func:`group_chance`);
* reveal: the daily chance of an unresolved crime grows with the region's suspicion, a masked crime × factor, and
  × (1 − the attacker's stealth reduction snapshotted on the crime row) (:func:`reveal_chance`);
* region suspicion: a value with lazy linear decay (``law_core.materialise`` / ``effective_wanted`` maths), public
  only as a text state (:func:`suspicion_state`);
* renown: fame (public tier) and infamy (hidden) with 5 fixed-code tiers per scale (:func:`renown_tier_for`).
"""

from dataclasses import dataclass, fields
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import Iterable, List, Optional, Sequence, Tuple

import stat_caps

# --------------------------------------------------------------------------------------------------- constants

# skills-service subclass keys (stable, never renamed — skills-service/app/subclasses.py)
SUBCLASS_AGENT = "warrior_agent"
SUBCLASS_ASSASSIN = "rogue_assassin"
SUBCLASS_TRICKSTER = "rogue_trickster"
SUBCLASS_LABELS = {SUBCLASS_ASSASSIN: "Ассасин", SUBCLASS_TRICKSTER: "Фокусник", SUBCLASS_AGENT: "Агент"}

# locations-service Locations.marker_type
MARKER_SAFE = "safe"
MARKER_FARM = "farm"
MARKER_DANGEROUS = "dangerous"
MARKER_DUNGEON = "dungeon"

SCALE_FAME = "fame"
SCALE_INFAMY = "infamy"
SCALES = (SCALE_FAME, SCALE_INFAMY)

FAME_CODES = ("nameless", "familiar", "known", "famous", "legend")
INFAMY_CODES = ("none", "whispers", "rumored", "notorious", "dreaded")
TIER_CODES = {SCALE_FAME: FAME_CODES, SCALE_INFAMY: INFAMY_CODES}

# renown_log.source
SOURCE_QUEST = "quest"
SOURCE_REPUTATION = "reputation"
SOURCE_CRIME = "crime"
SOURCE_STAFF = "staff"
SOURCE_CARAVAN_DEFENSE = "caravan_defense"   # FEAT-212: a repelled raid on a caravan the player escorted

# region suspicion states (calm is never shown)
SUSPICION_CALM = "calm"
SUSPICION_UNEASY = "uneasy"
SUSPICION_ALARMED = "alarmed"
SUSPICION_FEAR = "fear"
SUSPICION_LABELS = {
    SUSPICION_CALM: "В крае спокойно",
    SUSPICION_UNEASY: "В крае неспокойно",
    SUSPICION_ALARMED: "Край встревожен",
    SUSPICION_FEAR: "Край охвачен страхом",
}

# reputation action codes (reputation_core.ACTION_QUEST / ACTION_GUILD; repeated here to keep this module pure)
ACTION_QUEST = "quest_complete"
ACTION_GUILD = "guild_delivery"

# bounds (§3.1)
MAX_PER_POINT = Decimal(10)
MAX_RATIO = Decimal(10)
MAX_REVEAL_DAYS = 30
MAX_SUSPICION = 10_000
MAX_FAME_QUEST = 1000
MAX_INFAMY_MIN_GAIN = 1000
MAX_TIER_WITNESS_PCT = Decimal(50)
MAX_TIER_VALUE = 10_000_000
MAX_DECAY_PER_DAY = Decimal(100_000)
MAX_SUBCLASS_STEALTH = 500

_CENT = Decimal("0.01")
_HUNDRED = Decimal(100)


# --------------------------------------------------------------------------------------------------- value objects

@dataclass(frozen=True)
class ShadowSettings:
    witness_enabled: bool = True
    witness_base_safe_pct: Decimal = Decimal(100)
    witness_base_farm_pct: Decimal = Decimal(70)
    witness_base_dangerous_pct: Decimal = Decimal(40)
    witness_base_dungeon_pct: Decimal = Decimal(25)
    witness_base_default_pct: Decimal = Decimal(50)
    stealth_pct_per_point: Decimal = Decimal("0.5")
    stealth_max_reduction_pct: Decimal = Decimal(90)
    stealth_assassin_points: int = 30
    stealth_trickster_points: int = 30
    stealth_agent_points: int = 20
    witness_group_per_extra_pct: Decimal = Decimal(10)
    witness_min_pct: Decimal = Decimal(5)
    witness_max_pct: Decimal = Decimal(100)
    reveal_days: int = 3
    reveal_base_pct: Decimal = Decimal(15)
    reveal_per_suspicion_pct: Decimal = Decimal("0.4")
    reveal_mask_factor_pct: Decimal = Decimal(50)
    reveal_min_pct: Decimal = Decimal(1)
    reveal_max_pct: Decimal = Decimal(90)
    suspicion_max: int = 100
    suspicion_unwitnessed: int = 10
    suspicion_masked: int = 20
    suspicion_decay_per_day: Decimal = Decimal(5)
    suspicion_uneasy_at: int = 20
    suspicion_alarmed_at: int = 50
    suspicion_fear_at: int = 80
    infamy_ratio: Decimal = Decimal(1)
    infamy_min_gain: int = 10
    fame_quest_default: int = 5
    fame_rep_ratio: Decimal = Decimal("0.5")
    fame_guild_ratio: Decimal = Decimal(0)


DEFAULT_SETTINGS = ShadowSettings()

SETTINGS_FIELDS = tuple(f.name for f in fields(ShadowSettings))
BOOL_FIELDS = frozenset({"witness_enabled"})
INT_FIELDS = frozenset({"reveal_days", "suspicion_max", "suspicion_unwitnessed", "suspicion_masked",
                        "suspicion_uneasy_at", "suspicion_alarmed_at", "suspicion_fear_at", "infamy_min_gain",
                        "fame_quest_default", "stealth_assassin_points", "stealth_trickster_points",
                        "stealth_agent_points"})
DECIMAL_FIELDS = frozenset(n for n in SETTINGS_FIELDS if n not in BOOL_FIELDS and n not in INT_FIELDS)

SQL_SELECT_SETTINGS = "SELECT " + ", ".join(SETTINGS_FIELDS) + " FROM shadow_settings WHERE id = 1"
SQL_SELECT_TIERS = ("SELECT scale, code, sort_order, name, min_value, witness_pct FROM renown_tiers "
                    "ORDER BY scale, sort_order")


@dataclass(frozen=True)
class RenownTier:
    scale: str
    code: str
    sort_order: int
    name: str
    min_value: int
    witness_pct: Decimal = Decimal(0)


DEFAULT_TIERS: Tuple[RenownTier, ...] = (
    RenownTier(SCALE_FAME, "nameless", 1, "Безвестный", 0, Decimal(0)),
    RenownTier(SCALE_FAME, "familiar", 2, "Знакомое имя", 50, Decimal(2)),
    RenownTier(SCALE_FAME, "known", 3, "Известный", 200, Decimal(5)),
    RenownTier(SCALE_FAME, "famous", 4, "Знаменитый", 600, Decimal(10)),
    RenownTier(SCALE_FAME, "legend", 5, "Легенда", 1500, Decimal(15)),
    RenownTier(SCALE_INFAMY, "none", 1, "О вас не говорят", 0, Decimal(0)),
    RenownTier(SCALE_INFAMY, "whispers", 2, "Шёпот в тавернах", 100, Decimal(0)),
    RenownTier(SCALE_INFAMY, "rumored", 3, "О вас ходят слухи", 400, Decimal(0)),
    RenownTier(SCALE_INFAMY, "notorious", 4, "Дурная слава", 1000, Decimal(0)),
    RenownTier(SCALE_INFAMY, "dreaded", 5, "Имя, которое произносят шёпотом", 2500, Decimal(0)),
)


# --------------------------------------------------------------------------------------------------- helpers

def _dec(value) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _q(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lo, hi) -> Decimal:
    return max(_dec(lo), min(_dec(hi), value))


def settings_from_row(row) -> ShadowSettings:
    """A ``SQL_SELECT_SETTINGS`` row (or None = defaults: tests / a fresh DB)."""
    if row is None:
        return DEFAULT_SETTINGS
    values = {}
    for index, name in enumerate(SETTINGS_FIELDS):
        raw = row[index]
        if name in BOOL_FIELDS:
            values[name] = bool(raw)
        elif name in INT_FIELDS:
            values[name] = int(raw)
        else:
            values[name] = _dec(raw)
    return ShadowSettings(**values)


def tiers_from_rows(rows) -> List[RenownTier]:
    """``SQL_SELECT_TIERS`` rows; a scale without rows (fresh test DB) gets the defaults."""
    tiers = [RenownTier(str(r[0]), str(r[1]), int(r[2]), str(r[3]), int(r[4]), _dec(r[5])) for r in rows or ()]
    out: List[RenownTier] = []
    for scale in SCALES:
        mine = sorted((t for t in tiers if t.scale == scale), key=lambda t: t.sort_order)
        out.extend(mine or [t for t in DEFAULT_TIERS if t.scale == scale])
    return out


def scale_tiers(tiers: Iterable[RenownTier], scale: str) -> List[RenownTier]:
    return sorted((t for t in tiers if t.scale == scale), key=lambda t: t.sort_order)


# --------------------------------------------------------------------------------------------------- witnesses

def base_pct(marker_type: Optional[str], s: ShadowSettings) -> Decimal:
    """The witness base of a location by ``Locations.marker_type`` (unknown / no location = default)."""
    return {
        MARKER_SAFE: s.witness_base_safe_pct,
        MARKER_FARM: s.witness_base_farm_pct,
        MARKER_DANGEROUS: s.witness_base_dangerous_pct,
        MARKER_DUNGEON: s.witness_base_dungeon_pct,
    }.get(marker_type or "", s.witness_base_default_pct)


def subclass_stealth_points(subclass_key: Optional[str], s: ShadowSettings) -> int:
    """FEAT-201: out-of-battle stealth points of a subclass (0 for none / any other subclass)."""
    return int({
        SUBCLASS_AGENT: s.stealth_agent_points,
        SUBCLASS_ASSASSIN: s.stealth_assassin_points,
        SUBCLASS_TRICKSTER: s.stealth_trickster_points,
    }.get(subclass_key or "", 0))


def effective_stealth(raw_stealth, subclass_points) -> Decimal:
    """The FEAT-195 cap of (stored stealth + subclass points); the bonus is added BEFORE the cap. 2 decimals."""
    total = max(0, int(raw_stealth or 0)) + max(0, int(subclass_points or 0))
    return _q(_dec(stat_caps.effective_stat(total)))


def stealth_reduction_pct(eff_stealth, s: ShadowSettings) -> Decimal:
    """``min(max_reduction, max(0, eff) × pct_per_point)`` — the % of the chance stealth removes. 2 decimals."""
    raw = max(Decimal(0), _dec(eff_stealth)) * _dec(s.stealth_pct_per_point)
    return _q(min(_dec(s.stealth_max_reduction_pct), raw))


def member_chance(base, reduction_pct, masked: bool, fame_witness_pct) -> Decimal:
    """One attacker's (unclamped) chance to be seen: ``base × (1 − reduction / 100) × (1 + fame / 100)``.
    A masked member is anonymous: their fame does not count (the mask gives no other bonus)."""
    reduction = max(Decimal(0), min(_HUNDRED, _dec(reduction_pct)))
    value = _dec(base) * (_HUNDRED - reduction) / _HUNDRED
    if not masked:
        value = value * (_HUNDRED + max(Decimal(0), _dec(fame_witness_pct))) / _HUNDRED
    return value


def group_chance(member_chances: Sequence, n_players: int, s: ShadowSettings) -> Decimal:
    """``clamp(max(member chances) × (1 + per_extra / 100 × (n − 1)), min, max)``, 2 decimals."""
    if not member_chances:
        return _q(_clamp(_dec(s.witness_base_default_pct), s.witness_min_pct, s.witness_max_pct))
    factor = _HUNDRED + _dec(s.witness_group_per_extra_pct) * max(0, int(n_players) - 1)
    raw = max(_dec(c) for c in member_chances) * factor / _HUNDRED
    return _q(_clamp(raw, s.witness_min_pct, s.witness_max_pct))


# --------------------------------------------------------------------------------------------------- reveal

def reveal_chance(effective_suspicion, masked: bool, s: ShadowSettings, stealth_reduction_pct=0) -> Decimal:
    """``clamp((base + suspicion × per_point) × (masked ? factor / 100 : 1) × (1 − snapshot / 100), min, max)``,
    2 decimals. ``stealth_reduction_pct`` is the attacker's reduction stored on the crime (None / old rows = 0)."""
    raw = _dec(s.reveal_base_pct) + Decimal(max(0, int(effective_suspicion or 0))) * _dec(s.reveal_per_suspicion_pct)
    if masked:
        raw = raw * _dec(s.reveal_mask_factor_pct) / _HUNDRED
    snapshot = max(Decimal(0), min(_HUNDRED, _dec(stealth_reduction_pct)))
    raw = raw * (_HUNDRED - snapshot) / _HUNDRED
    return _q(_clamp(raw, s.reveal_min_pct, s.reveal_max_pct))


# --------------------------------------------------------------------------------------------------- suspicion

def add_suspicion(effective: int, gain: int, s: ShadowSettings) -> int:
    return max(0, min(int(s.suspicion_max), int(effective) + int(gain)))


def suspicion_code(value: int, s: ShadowSettings) -> str:
    value = int(value or 0)
    if value >= int(s.suspicion_fear_at):
        return SUSPICION_FEAR
    if value >= int(s.suspicion_alarmed_at):
        return SUSPICION_ALARMED
    if value >= int(s.suspicion_uneasy_at):
        return SUSPICION_UNEASY
    return SUSPICION_CALM


def suspicion_state(value: int, s: ShadowSettings) -> Optional[Tuple[str, str]]:
    """``(code, label)`` of a region's suspicion; None when calm (nothing is shown)."""
    code = suspicion_code(value, s)
    if code == SUSPICION_CALM:
        return None
    return code, SUSPICION_LABELS[code]


# --------------------------------------------------------------------------------------------------- renown

def renown_tier_for(value: int, tiers: Sequence[RenownTier]) -> RenownTier:
    """The highest tier (of ONE scale) whose ``min_value <= value``; the first tier for 0."""
    ordered = sorted(tiers, key=lambda t: t.sort_order)
    found = ordered[0]
    for tier in ordered:
        if int(value or 0) >= tier.min_value:
            found = tier
    return found


def next_tier(tier: RenownTier, tiers: Sequence[RenownTier]) -> Optional[RenownTier]:
    ordered = sorted(tiers, key=lambda t: t.sort_order)
    for candidate in ordered:
        if candidate.sort_order > tier.sort_order:
            return candidate
    return None


def renown_progress(value: int, tier: RenownTier, tiers: Sequence[RenownTier]) -> float:
    """Progress 0..1 inside ``tier`` towards the next one (top tier = 1.0)."""
    nxt = next_tier(tier, tiers)
    if nxt is None:
        return 1.0
    span = nxt.min_value - tier.min_value
    if span <= 0:
        return 1.0
    return round(max(0.0, min(1.0, (int(value or 0) - tier.min_value) / span)), 4)


def infamy_gain(wanted_points: int, s: ShadowSettings) -> int:
    """``max(infamy_min_gain, floor(wanted_points × infamy_ratio))``."""
    scaled = int((Decimal(max(0, int(wanted_points or 0))) * _dec(s.infamy_ratio))
                 .to_integral_value(rounding=ROUND_FLOOR))
    return max(int(s.infamy_min_gain), scaled)


def fame_from_reputation(action: str, applied_delta: int, s: ShadowSettings) -> int:
    """Fame of an automatic positive reputation change (quests have their own fame source)."""
    applied_delta = int(applied_delta or 0)
    if applied_delta <= 0 or action == ACTION_QUEST:
        return 0
    ratio = s.fame_guild_ratio if action == ACTION_GUILD else s.fame_rep_ratio
    return max(0, int((Decimal(applied_delta) * _dec(ratio)).to_integral_value(rounding=ROUND_FLOOR)))


# --------------------------------------------------------------------------------------------------- validation

def _pct_ok(value) -> bool:
    return Decimal(0) <= _dec(value) <= _HUNDRED


def validate(s: ShadowSettings, tiers: Sequence[RenownTier]) -> Optional[str]:
    """Russian error text for invalid settings / tiers, else None (§3.1)."""
    pct_fields = (
        ("witness_base_safe_pct", "База свидетелей (поселение)"),
        ("witness_base_farm_pct", "База свидетелей (угодья)"),
        ("witness_base_dangerous_pct", "База свидетелей (дикие места)"),
        ("witness_base_dungeon_pct", "База свидетелей (подземелье)"),
        ("witness_base_default_pct", "База свидетелей (по умолчанию)"),
        ("stealth_max_reduction_pct", "Предел снижения скрытностью"),
        ("witness_group_per_extra_pct", "Прибавка за участника группы"),
        ("witness_min_pct", "Минимальный шанс свидетелей"),
        ("witness_max_pct", "Максимальный шанс свидетелей"),
        ("reveal_base_pct", "База шанса раскрытия"),
        ("reveal_mask_factor_pct", "Множитель раскрытия для маски"),
        ("reveal_min_pct", "Минимальный шанс раскрытия"),
        ("reveal_max_pct", "Максимальный шанс раскрытия"),
    )
    for name, label in pct_fields:
        if not _pct_ok(getattr(s, name)):
            return f"{label}: от 0 до 100 %"
    if _dec(s.witness_min_pct) > _dec(s.witness_max_pct):
        return "Шанс свидетелей: минимум не может быть больше максимума"
    if _dec(s.reveal_min_pct) > _dec(s.reveal_max_pct):
        return "Шанс раскрытия: минимум не может быть больше максимума"
    for name, label in (("stealth_pct_per_point", "Снижение за очко скрытности"),
                        ("reveal_per_suspicion_pct", "Прибавка к раскрытию за очко подозрения")):
        if not (Decimal(0) <= _dec(getattr(s, name)) <= MAX_PER_POINT):
            return f"{label}: от 0 до {MAX_PER_POINT}"
    for name, key in (("stealth_assassin_points", SUBCLASS_ASSASSIN), ("stealth_trickster_points", SUBCLASS_TRICKSTER),
                      ("stealth_agent_points", SUBCLASS_AGENT)):
        if not (0 <= int(getattr(s, name)) <= MAX_SUBCLASS_STEALTH):
            return f"Скрытность подкласса «{SUBCLASS_LABELS[key]}»: от 0 до {MAX_SUBCLASS_STEALTH}"
    if not (1 <= int(s.reveal_days) <= MAX_REVEAL_DAYS):
        return f"Срок раскрытия: от 1 до {MAX_REVEAL_DAYS} дней"
    if not (1 <= int(s.suspicion_max) <= MAX_SUSPICION):
        return f"Максимальное подозрение: от 1 до {MAX_SUSPICION}"
    for name, label in (("suspicion_unwitnessed", "Подозрение за незамеченное преступление"),
                        ("suspicion_masked", "Подозрение за преступление в маске")):
        if not (0 <= int(getattr(s, name)) <= int(s.suspicion_max)):
            return f"{label}: от 0 до максимального подозрения"
    if not (Decimal(0) <= _dec(s.suspicion_decay_per_day) <= MAX_DECAY_PER_DAY):
        return "Спад подозрения в день должен быть не меньше 0"
    if not (1 <= int(s.suspicion_uneasy_at) < int(s.suspicion_alarmed_at) < int(s.suspicion_fear_at)
            <= int(s.suspicion_max)):
        return "Пороги подозрения должны строго возрастать: от 1 до максимального подозрения"
    for name, label in (("infamy_ratio", "Множитель дурной славы"), ("fame_rep_ratio", "Доля славы от репутации"),
                        ("fame_guild_ratio", "Доля славы от заказов гильдии")):
        if not (Decimal(0) <= _dec(getattr(s, name)) <= MAX_RATIO):
            return f"{label}: от 0 до {MAX_RATIO}"
    if not (0 <= int(s.fame_quest_default) <= MAX_FAME_QUEST):
        return f"Слава за задание: от 0 до {MAX_FAME_QUEST}"
    if not (0 <= int(s.infamy_min_gain) <= MAX_INFAMY_MIN_GAIN):
        return f"Минимальная дурная слава за преступление: от 0 до {MAX_INFAMY_MIN_GAIN}"

    for scale, label in ((SCALE_FAME, "славы"), (SCALE_INFAMY, "дурной славы")):
        mine = [t for t in tiers if t.scale == scale]
        codes = TIER_CODES[scale]
        if sorted(t.code for t in mine) != sorted(codes) or len(mine) != len(codes):
            return f"Нужны ровно 5 ступеней {label}"
        previous = None
        for tier in sorted(mine, key=lambda t: codes.index(t.code)):
            if not tier.name or not tier.name.strip() or len(tier.name.strip()) > 60:
                return f"Название ступени {label}: от 1 до 60 символов"
            if previous is None:
                if int(tier.min_value) != 0:
                    return f"Первая ступень {label} должна начинаться с 0"
            elif int(tier.min_value) <= previous:
                return f"Пороги ступеней {label} должны строго возрастать"
            if int(tier.min_value) > MAX_TIER_VALUE:
                return f"Порог ступени {label} слишком большой"
            if scale == SCALE_FAME and not (Decimal(0) <= _dec(tier.witness_pct) <= MAX_TIER_WITNESS_PCT):
                return f"Узнаваемость ступени славы (множитель): от 0 до {MAX_TIER_WITNESS_PCT} %"
            previous = int(tier.min_value)
    return None
