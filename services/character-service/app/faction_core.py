"""FEAT-205 factions — pure rules (no I/O, no DB). features/FEAT-205 §3.4.

* entry conditions: typed blocks AND-ed; :func:`condition_met` decides on resolved :class:`Facts`, :func:`condition_text`
  builds the player text from resolved :class:`Refs` (fame / infamy are shown as TIER NAMES, never numbers; a secret
  faction is never named to a player);
* ranks: an ordered ladder; the lowest rank is the entry rank (no conditions); :func:`climb` walks upward from the
  current rank while the next rank's conditions hold — ranks never go down while a member;
* points: clamped at 0; the hostility penalty is a share of a quest GAIN; leaving / expulsion burns a share.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

# --------------------------------------------------------------------------------------------------- constants

STATUS_ACTIVE = "active"
STATUS_LEFT = "left"
STATUS_EXPELLED = "expelled"
MEMBER_STATUSES = (STATUS_ACTIVE, STATUS_LEFT, STATUS_EXPELLED)

APP_PENDING = "pending"
APP_APPROVED = "approved"
APP_REJECTED = "rejected"
APP_CANCELLED = "cancelled"
APP_STATUSES = (APP_PENDING, APP_APPROVED, APP_REJECTED, APP_CANCELLED)

COND_REGION = "region_reputation"
COND_FAME = "fame"
COND_INFAMY = "infamy"
COND_LEVEL = "level"
COND_CLASS = "class"
COND_SUBCLASS = "subclass"
COND_RACE = "race"
COND_QUEST = "quest"
COND_NOT_IN = "not_in_faction"
COND_TYPES = (COND_REGION, COND_FAME, COND_INFAMY, COND_LEVEL, COND_CLASS, COND_SUBCLASS, COND_RACE, COND_QUEST,
              COND_NOT_IN)

# rank requirement types (next-rank progress)
REQ_POINTS = "points"
REQ_LEVEL = "level"
REQ_QUEST = "quest"

EV_JOINED = "joined"
EV_LEFT = "left"
EV_EXPELLED = "expelled"
EV_RANK_UP = "rank_up"
EV_POINTS = "points"
EV_HOSTILE = "hostile_penalty"
EV_WARNING = "warning"
EV_WARNING_CLEARED = "warning_cleared"
EV_APPLIED = "applied"
EV_APP_APPROVED = "application_approved"
EV_APP_REJECTED = "application_rejected"
EV_ADMIN_POINTS = "admin_points"
EV_REWARD_FAILED = "reward_failed"
EV_DONATION = "donation"                            # FEAT-206: marks donated to the treasury (+ points)
PLAYER_HIDDEN_EVENTS = (EV_REWARD_FAILED,)          # admin-only journal rows

KIND_XP = "xp"
KIND_TITLE = "title"
KIND_ITEM = "item"
KIND_VOUCHER = "voucher"
VOUCHER_READY = "ready"                             # house_plots.kind
VOUCHER_EMPTY = "empty"

DLV_PENDING = "pending"
DLV_SENDING = "sending"
DLV_DONE = "done"
DLV_FAILED = "failed"
DLV_UNCERTAIN = "uncertain"                         # last_error of an ambiguous item delivery

# bounds (§3.2 / §3.10)
MAX_CONDITIONS = 20
MAX_LEADERS = 5
MAX_REWARD_ITEMS = 10
MAX_ITEM_QTY = 999
MAX_POINTS_VALUE = 10_000_000
MAX_LEVEL = 1000
MAX_RANK_XP = 10_000_000
MAX_MEMBER_LIMIT = 100_000
MAX_QUEST_POINTS = 10_000
MAX_QUEST_REWARDS = 5
MAX_ADMIN_DELTA = 100_000
MAX_CLASS_IDS = 20
MAX_SUBCLASS_KEYS = 30
MAX_RACE_IDS = 30
SUBCLASS_KEY_RE = r"^[a-z0-9_]{1,50}$"

SECRET_FACTION_TEXT = "Не состоит в некоторых тайных организациях"


@dataclass(frozen=True)
class FactionSettings:
    warning_days: int = 3
    rejoin_cooldown_days: int = 7
    leave_burn_pct: int = 50
    hostile_penalty_pct: int = 50
    reapply_cooldown_hours: int = 24


DEFAULT_SETTINGS = FactionSettings()

SETTINGS_BOUNDS = {
    "warning_days": (0, 60),
    "rejoin_cooldown_days": (0, 365),
    "leave_burn_pct": (0, 100),
    "hostile_penalty_pct": (0, 100),
    "reapply_cooldown_hours": (0, 720),
}


def settings_from_row(row) -> FactionSettings:
    if row is None:
        return DEFAULT_SETTINGS
    return FactionSettings(
        warning_days=int(row.warning_days), rejoin_cooldown_days=int(row.rejoin_cooldown_days),
        leave_burn_pct=int(row.leave_burn_pct), hostile_penalty_pct=int(row.hostile_penalty_pct),
        reapply_cooldown_hours=int(row.reapply_cooldown_hours))


# --------------------------------------------------------------------------------------------------- value objects

@dataclass
class Facts:
    """What the conditions of ONE character need (filled lazily by the caller; None = unknown / not loaded)."""
    level: int = 0
    class_id: Optional[int] = None
    race_id: Optional[int] = None
    subrace_id: Optional[int] = None
    subclass_key: Optional[str] = None
    fame_rank: Optional[int] = None                 # sort_order of the current fame tier
    infamy_rank: Optional[int] = None
    region_ranks: Dict[int, int] = field(default_factory=dict)     # region_id -> sort_order of the reputation tier
    completed_quests: Set[int] = field(default_factory=set)
    active_factions: Set[int] = field(default_factory=set)


@dataclass
class Refs:
    """Names for the player texts (resolved by the caller)."""
    rep_tiers: Dict[str, Tuple[int, str]] = field(default_factory=dict)       # code -> (sort_order, name)
    fame_tiers: Dict[str, Tuple[int, str]] = field(default_factory=dict)
    infamy_tiers: Dict[str, Tuple[int, str]] = field(default_factory=dict)
    regions: Dict[int, str] = field(default_factory=dict)
    classes: Dict[int, str] = field(default_factory=dict)
    races: Dict[int, str] = field(default_factory=dict)
    subraces: Dict[int, str] = field(default_factory=dict)
    quests: Dict[int, str] = field(default_factory=dict)
    factions: Dict[int, Tuple[str, bool]] = field(default_factory=dict)       # id -> (name, is_secret)
    subclasses: Dict[str, str] = field(default_factory=dict)                  # subclass_key -> name


@dataclass(frozen=True)
class RankDef:
    id: int
    sort_order: int
    name: str
    min_points: int = 0
    min_level: int = 0
    required_quest_id: Optional[int] = None


# --------------------------------------------------------------------------------------------------- conditions

def _rank_of(code: Optional[str], tiers: Dict[str, Tuple[int, str]]) -> Optional[int]:
    if not code or code not in tiers:
        return None
    return tiers[code][0]


def _tier_name(code: Optional[str], tiers: Dict[str, Tuple[int, str]]) -> str:
    if code and code in tiers:
        return tiers[code][1]
    return code or "—"


def _in_range(rank: Optional[int], lo: Optional[int], hi: Optional[int]) -> bool:
    value = rank if rank is not None else 1           # no row = the lowest tier
    if lo is not None and value < lo:
        return False
    if hi is not None and value > hi:
        return False
    return True


def condition_met(cond_type: str, params: dict, facts: Facts, refs: Refs) -> bool:
    p = params or {}
    if cond_type == COND_REGION:
        need = _rank_of(p.get("min_tier"), refs.rep_tiers)
        if need is None:
            return True
        have = facts.region_ranks.get(int(p.get("region_id") or 0))
        return have is not None and have >= need
    if cond_type == COND_FAME:
        return _in_range(facts.fame_rank, _rank_of(p.get("min_tier"), refs.fame_tiers),
                         _rank_of(p.get("max_tier"), refs.fame_tiers))
    if cond_type == COND_INFAMY:
        return _in_range(facts.infamy_rank, _rank_of(p.get("min_tier"), refs.infamy_tiers),
                         _rank_of(p.get("max_tier"), refs.infamy_tiers))
    if cond_type == COND_LEVEL:
        return int(facts.level or 0) >= int(p.get("min_level") or 0)
    if cond_type == COND_CLASS:
        return facts.class_id is not None and int(facts.class_id) in {int(x) for x in p.get("class_ids") or []}
    if cond_type == COND_SUBCLASS:
        return bool(facts.subclass_key) and facts.subclass_key in set(p.get("subclass_keys") or [])
    if cond_type == COND_RACE:
        if facts.race_id is None or int(facts.race_id) not in {int(x) for x in p.get("race_ids") or []}:
            return False
        subraces = p.get("subrace_ids") or []
        return not subraces or (facts.subrace_id is not None and int(facts.subrace_id) in {int(x) for x in subraces})
    if cond_type == COND_QUEST:
        return int(p.get("quest_id") or 0) in facts.completed_quests
    if cond_type == COND_NOT_IN:
        return int(p.get("faction_id") or 0) not in facts.active_factions
    return False                                        # unknown type never passes


def _names(ids, mapping: Dict[int, str]) -> str:
    return " или ".join(mapping.get(int(i), f"#{int(i)}") for i in ids or [])


def _range_text(label: str, params: dict, tiers: Dict[str, Tuple[int, str]]) -> str:
    lo, hi = params.get("min_tier"), params.get("max_tier")
    if lo and hi:
        return f"{label}: от «{_tier_name(lo, tiers)}» до «{_tier_name(hi, tiers)}»"
    if lo:
        return f"{label}: не ниже «{_tier_name(lo, tiers)}»"
    return f"{label}: не выше «{_tier_name(hi, tiers)}»"


def faction_ref_text(faction_id: int, refs: Refs, *, reveal_secret: bool = False) -> str:
    name, secret = refs.factions.get(int(faction_id), (None, False))
    if secret and not reveal_secret:
        return SECRET_FACTION_TEXT
    return f"Не состоит во фракции «{name or '#' + str(int(faction_id))}»"


def condition_text(cond_type: str, params: dict, refs: Refs, *, reveal_secret: bool = False) -> str:
    p = params or {}
    if cond_type == COND_REGION:
        region = refs.regions.get(int(p.get("region_id") or 0), f"#{p.get('region_id')}")
        return f"Репутация в крае «{region}»: не ниже «{_tier_name(p.get('min_tier'), refs.rep_tiers)}»"
    if cond_type == COND_FAME:
        return _range_text("Слава", p, refs.fame_tiers)
    if cond_type == COND_INFAMY:
        return _range_text("Слухи", p, refs.infamy_tiers)
    if cond_type == COND_LEVEL:
        return f"Уровень от {int(p.get('min_level') or 0)}"
    if cond_type == COND_CLASS:
        return f"Класс: {_names(p.get('class_ids'), refs.classes)}"
    if cond_type == COND_SUBCLASS:
        return "Подкласс: " + " или ".join(refs.subclasses.get(str(k)) or str(k) for k in p.get("subclass_keys") or [])
    if cond_type == COND_RACE:
        text = f"Раса: {_names(p.get('race_ids'), refs.races)}"
        if p.get("subrace_ids"):
            text += f" (подраса: {_names(p.get('subrace_ids'), refs.subraces)})"
        return text
    if cond_type == COND_QUEST:
        title = refs.quests.get(int(p.get("quest_id") or 0)) or f"#{p.get('quest_id')}"
        return f"Выполнено задание «{title}»"
    if cond_type == COND_NOT_IN:
        return faction_ref_text(int(p.get("faction_id") or 0), refs, reveal_secret=reveal_secret)
    return "Неизвестное условие"


def public_params(cond_type: str, params: dict, refs: Refs) -> Optional[dict]:
    """Params safe for a player (a secret faction id is never revealed)."""
    if cond_type == COND_NOT_IN:
        _name, secret = refs.factions.get(int((params or {}).get("faction_id") or 0), (None, False))
        if secret:
            return None
    return dict(params or {})


def evaluate(conditions: Sequence[Tuple[str, dict]], facts: Optional[Facts], refs: Refs) -> List[dict]:
    """``[{type, text, met, params}]``; ``met`` is None without a character."""
    out = []
    for cond_type, params in conditions:
        out.append({
            "type": cond_type,
            "text": condition_text(cond_type, params, refs),
            "met": None if facts is None else condition_met(cond_type, params, facts, refs),
            "params": public_params(cond_type, params, refs),
        })
    return out


def unmet_texts(evaluated: Sequence[dict]) -> List[str]:
    return [c["text"] for c in evaluated if c.get("met") is False]


def entry_conditions(faction_id: int, own: Sequence[Tuple[str, dict]],
                     irreconcilable_with: Sequence[int]) -> List[Tuple[str, dict]]:
    """The faction's own blocks + the implicit «not in <irreconcilable faction>» (deduplicated)."""
    out = list(own)
    already = {int((p or {}).get("faction_id") or 0) for t, p in own if t == COND_NOT_IN}
    for other in sorted({int(x) for x in irreconcilable_with}):
        if other != int(faction_id) and other not in already:
            out.append((COND_NOT_IN, {"faction_id": other}))
    return out


# --------------------------------------------------------------------------------------------------- ranks

def sorted_ladder(ranks: Sequence[RankDef]) -> List[RankDef]:
    return sorted(ranks, key=lambda r: (r.sort_order, r.id))


def rank_requirements_met(rank: RankDef, points: int, level: int, completed: Set[int]) -> bool:
    if int(points) < int(rank.min_points or 0):
        return False
    if int(level or 0) < int(rank.min_level or 0):
        return False
    if rank.required_quest_id and int(rank.required_quest_id) not in completed:
        return False
    return True


def climb(ladder: Sequence[RankDef], current_rank_id: Optional[int], points: int, level: int,
          completed: Set[int]) -> List[RankDef]:
    """Ranks reached by this walk, in order (the entry rank first when the walk starts from it).

    ``current_rank_id`` None (a (re)join, or the rank was deleted) -> the walk starts at the entry rank, which is
    reached unconditionally. Otherwise it starts right above the current rank. Stops at the first unmet rank.
    """
    ordered = sorted_ladder(ladder)
    if not ordered:
        return []
    reached: List[RankDef] = []
    start = 0
    if current_rank_id is None or all(r.id != current_rank_id for r in ordered):
        reached.append(ordered[0])
        start = 1
    else:
        start = next(i for i, r in enumerate(ordered) if r.id == current_rank_id) + 1
    for rank in ordered[start:]:
        if not rank_requirements_met(rank, points, level, completed):
            break
        reached.append(rank)
    return reached


def next_rank(ladder: Sequence[RankDef], current_rank_id: Optional[int]) -> Optional[RankDef]:
    ordered = sorted_ladder(ladder)
    if not ordered:
        return None
    if current_rank_id is None:
        return ordered[0]
    for i, rank in enumerate(ordered):
        if rank.id == current_rank_id:
            return ordered[i + 1] if i + 1 < len(ordered) else None
    return ordered[0]


def rank_requirements(rank: RankDef, points: int, level: int, completed: Set[int],
                      quest_titles: Dict[int, str]) -> List[dict]:
    out = []
    if rank.min_points:
        out.append({"type": REQ_POINTS, "text": f"Очки фракции: {int(points)} / {int(rank.min_points)}",
                    "met": int(points) >= int(rank.min_points)})
    if rank.min_level:
        out.append({"type": REQ_LEVEL, "text": f"Уровень от {int(rank.min_level)}",
                    "met": int(level or 0) >= int(rank.min_level)})
    if rank.required_quest_id:
        title = quest_titles.get(int(rank.required_quest_id)) or f"#{int(rank.required_quest_id)}"
        out.append({"type": REQ_QUEST, "text": f"Выполнено задание «{title}»",
                    "met": int(rank.required_quest_id) in completed})
    return out


# --------------------------------------------------------------------------------------------------- points

def apply_points(points: int, delta: int) -> int:
    return max(0, int(points) + int(delta))


def hostile_penalty(gain: int, pct: int) -> int:
    """The share of a quest GAIN taken from each hostile faction (0 for a loss / zero)."""
    if gain <= 0 or pct <= 0:
        return 0
    return (int(gain) * int(pct)) // 100


def burn(points: int, pct: int) -> int:
    """Points kept after leaving / expulsion."""
    return (int(points) * (100 - int(pct))) // 100


def rejoin_after(now: datetime, s: FactionSettings) -> datetime:
    return now + timedelta(days=int(s.rejoin_cooldown_days))


def warning_deadline(warning_at: datetime, s: FactionSettings) -> datetime:
    return warning_at + timedelta(days=int(s.warning_days))


def remaining_seconds(until: Optional[datetime], now: datetime) -> Optional[int]:
    if until is None:
        return None
    return max(0, int((until - now).total_seconds()))


def pair(a: int, b: int) -> Tuple[int, int]:
    a, b = int(a), int(b)
    return (a, b) if a < b else (b, a)


# =====================================================================================================================
# FEAT-207 — territory, rank passives, enemies / kill points, outlaw regions (features/FEAT-207 §3.3)
# =====================================================================================================================

EV_KILL = "kill"                                    # points for defeating the faction's enemies
EV_EJECTED = "ejected"                              # moved out of a closed territory

ACCESS_LOCATION = "location"
ACCESS_DUNGEON = "dungeon"
ACCESS_KINDS = (ACCESS_LOCATION, ACCESS_DUNGEON)

ENEMY_MOB = "mob"                                   # ref = mob_templates.id
ENEMY_NPC = "npc"                                   # ref = characters.id (is_npc = 1, npc_role != 'mob')
ENEMY_HOSTILE = "hostile"                           # ref = 0: open members of hostile factions (PvP)
# FEAT-212 3.10: caravan deeds as "дело фракции" — singletons like hostile (ref = 0), points per deed, the kill cap
ENEMY_ESCORT = "escort"                             # «Охрана караванов»: a caravan delivered under a member's escort
ENEMY_RAID = "raid"                                 # «Налёты на караваны»: a won raid of a member
ENEMY_KINDS = (ENEMY_MOB, ENEMY_NPC, ENEMY_HOSTILE, ENEMY_ESCORT, ENEMY_RAID)
ENEMY_SINGLETONS = (ENEMY_HOSTILE, ENEMY_ESCORT, ENEMY_RAID)
EV_CARAVAN_ESCORT = "caravan_escort"                # faction_log.event_type of an escort deed
EV_CARAVAN_RAID = "caravan_raid"                    # faction_log.event_type of a raid deed
PVP_KILL_BATTLE_TYPES = ("pvp_death", "pvp_attack")     # training duels never count (Q2)

MAX_ENEMIES = 50
MAX_ENEMY_POINTS = 10_000
MAX_KILL_CAP = 100_000
MAX_OUTLAW_REGIONS = 50

# passives (§3.0 #4): battle keys only
FACTION_PASSIVE_PRIMARIES = ("strength", "agility", "intelligence", "endurance", "luck")
FACTION_PASSIVE_KEYS = FACTION_PASSIVE_PRIMARIES + (
    "damage", "dodge", "res_effects",
    "res_physical", "res_catting", "res_crushing", "res_piercing",
    "res_magic", "res_fire", "res_ice", "res_watering",
    "res_electricity", "res_wind", "res_sainting", "res_damning",
    "critical_hit_chance", "critical_damage",
    "vul_effects", "vul_physical", "vul_catting", "vul_crushing", "vul_piercing",
    "vul_magic", "vul_fire", "vul_ice", "vul_watering",
    "vul_electricity", "vul_sainting", "vul_wind", "vul_damning",
)
MAX_PASSIVE_KEYS = 10
PASSIVE_VALUE_MIN = -100
PASSIVE_VALUE_MAX = 100
MAX_PASSIVE_NAME = 100
MAX_PASSIVE_DESCRIPTION = 500

MSG_PASSIVE_KEY = "Пассивка: неизвестный модификатор «{key}»"
MSG_PASSIVE_VALUE = "Пассивка: значение модификатора «{key}» — целое число от -100 до 100, не 0"
MSG_PASSIVE_MAX = "Пассивка: не больше 10 модификаторов"
MSG_PASSIVE_NAME = "Пассивка: укажите название (до 100 символов)"
MSG_PASSIVE_DESCRIPTION = "Пассивка: описание до 500 символов"


class PassiveError(ValueError):
    """Invalid rank passive (Russian message for the admin)."""


@dataclass(frozen=True)
class TerritorySettings:
    """The FEAT-207 part of ``faction_settings`` (row id=1); the item sale share lives in faction_econ.EconSettings."""
    kill_points_daily_cap: int = 50
    pvp_kill_repeat_hours: int = 24
    outlaw_check_cooldown_hours: int = 24


DEFAULT_TERRITORY_SETTINGS = TerritorySettings()

# name -> (lo, hi, Russian label)
TERRITORY_SETTINGS_BOUNDS = {
    "kill_points_daily_cap": (0, 100_000, "Очков за победы над врагами в день (0 — не даются)"),
    "pvp_kill_repeat_hours": (0, 720, "Часов до повторных очков за того же противника"),
    "outlaw_check_cooldown_hours": (1, 720, "Часов между правонарушениями «членство» в одном крае"),
}


def territory_settings_from_row(row) -> TerritorySettings:
    if row is None:
        return DEFAULT_TERRITORY_SETTINGS

    def get(name):
        value = getattr(row, name, None)
        return getattr(DEFAULT_TERRITORY_SETTINGS, name) if value is None else int(value)

    return TerritorySettings(kill_points_daily_cap=max(0, get("kill_points_daily_cap")),
                             pvp_kill_repeat_hours=max(0, get("pvp_kill_repeat_hours")),
                             outlaw_check_cooldown_hours=max(1, get("outlaw_check_cooldown_hours")))


# --------------------------------------------------------------------------------------------------- access

@dataclass(frozen=True)
class AccessFaction:
    id: int
    name: str
    is_secret: bool
    is_active: bool


@dataclass(frozen=True)
class AccessRank:
    id: int
    name: str
    sort_order: int


@dataclass(frozen=True)
class AccessDecision:
    allowed: Optional[bool]                         # None = viewer unknown (public map)
    label: Optional[str]                            # short mark for neighbours / map / dungeon list
    refusal: Optional[str] = None                   # move refusal text (only when allowed is False)
    rule: bool = True                               # an effective rule exists (False -> open, label None)


OPEN_DECISION = AccessDecision(allowed=True, label=None, refusal=None, rule=False)

LABEL_CLOSED = "Закрыто"
REFUSAL_SECRET = "Сюда вас не пускают"


def access_label_public(faction: AccessFaction) -> str:
    return LABEL_CLOSED if faction.is_secret else f"Закрыто: {faction.name}"


def access_decision(faction: Optional[AccessFaction], min_rank: Optional[AccessRank], *, viewer_known: bool,
                    is_member: bool = False, member_rank_order: Optional[int] = None) -> AccessDecision:
    """The single source of truth of a closed territory (§3.3 table).

    ``faction`` None (no rule / faction deleted) or hidden (``is_active`` false) -> open. ``viewer_known`` False ->
    the public label with ``allowed`` None. ``is_member`` = an ACTIVE membership of the rule's faction;
    ``member_rank_order`` = sort_order of the held rank (None = no rank).
    """
    if faction is None or not faction.is_active:
        return OPEN_DECISION
    if not viewer_known:
        return AccessDecision(allowed=None, label=access_label_public(faction))
    if is_member:
        if min_rank is None or (member_rank_order is not None and int(member_rank_order) >= int(min_rank.sort_order)):
            return AccessDecision(allowed=True, label=f"Территория фракции «{faction.name}»")
        return AccessDecision(
            allowed=False, label=f"Закрыто: нужно звание «{min_rank.name}» во фракции «{faction.name}»",
            refusal=f"Нужно звание «{min_rank.name}» во фракции «{faction.name}»")
    if faction.is_secret:
        return AccessDecision(allowed=False, label=LABEL_CLOSED, refusal=REFUSAL_SECRET)
    return AccessDecision(allowed=False, label=f"Закрыто: {faction.name}",
                          refusal=f"Вход только для членов фракции «{faction.name}»")


def dungeon_refusal(faction: AccessFaction, min_rank: Optional[AccessRank], failed_names: Sequence[str], *,
                    party: bool) -> str:
    """Refusal text of a dungeon entry (§3.4). A secret faction is never named (generic text)."""
    if faction.is_secret:
        return "Подземелье закрыто — войти могут не все участники отряда" if party else "Подземелье закрыто"
    if min_rank is not None:
        text = f"Нужно звание «{min_rank.name}» во фракции «{faction.name}»"
    else:
        text = f"Подземелье только для членов фракции «{faction.name}»"
    if party and failed_names:
        text += " — не проходят: " + ", ".join(failed_names)
    return text


# --------------------------------------------------------------------------------------------------- passives

def validate_passive(name: Optional[str], description: Optional[str], modifiers):
    """(name, description, modifiers) normalised; empty modifiers -> (None, None, None). Raises PassiveError."""
    if modifiers is None or modifiers == {}:
        return None, None, None
    if not isinstance(modifiers, dict) or len(modifiers) > MAX_PASSIVE_KEYS:
        raise PassiveError(MSG_PASSIVE_MAX)
    out: Dict[str, int] = {}
    for key, value in modifiers.items():
        key = str(key)
        if key not in FACTION_PASSIVE_KEYS:
            raise PassiveError(MSG_PASSIVE_KEY.format(key=key))
        if isinstance(value, bool) or not isinstance(value, int):
            raise PassiveError(MSG_PASSIVE_VALUE.format(key=key))
        if value == 0 or not PASSIVE_VALUE_MIN <= value <= PASSIVE_VALUE_MAX:
            raise PassiveError(MSG_PASSIVE_VALUE.format(key=key))
        out[key] = int(value)
    name = (name or "").strip()
    if not 1 <= len(name) <= MAX_PASSIVE_NAME:
        raise PassiveError(MSG_PASSIVE_NAME)
    description = (description or "").strip() or None
    if description and len(description) > MAX_PASSIVE_DESCRIPTION:
        raise PassiveError(MSG_PASSIVE_DESCRIPTION)
    return name, description, {k: out[k] for k in FACTION_PASSIVE_KEYS if k in out}


def clean_modifiers(modifiers) -> Dict[str, int]:
    """Stored modifiers, tolerant: unknown keys / non-int / zero values are dropped."""
    if not isinstance(modifiers, dict):
        return {}
    out = {}
    for key, value in modifiers.items():
        if str(key) in FACTION_PASSIVE_KEYS and isinstance(value, int) and not isinstance(value, bool) and value:
            out[str(key)] = int(value)
    return out


@dataclass(frozen=True)
class PassiveRank:
    id: int
    sort_order: int
    name: str
    passive_name: Optional[str]
    passive_description: Optional[str]
    modifiers: Dict[str, int]


def active_passives(ladder: Sequence[PassiveRank], held_rank_id: Optional[int]) -> List[PassiveRank]:
    """Cumulative: every rank up to and including the held one with non-empty modifiers (ladder order)."""
    if held_rank_id is None:
        return []
    held = next((r for r in ladder if int(r.id) == int(held_rank_id)), None)
    if held is None:
        return []
    return [r for r in sorted(ladder, key=lambda r: (r.sort_order, r.id))
            if (r.sort_order, r.id) <= (held.sort_order, held.id) and r.modifiers]


def sum_modifiers(groups: Sequence[Mapping]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for group in groups:
        for key, value in (group or {}).items():
            out[str(key)] = out.get(str(key), 0) + int(value)
    return {k: v for k, v in out.items() if v}


# --------------------------------------------------------------------------------------------------- kill points

def kill_gain(enemy_points: Sequence[int], cap: int, today_before: int) -> Tuple[int, int]:
    """(gain, today_after): raw = sum, gain = max(0, min(raw, cap - today_before))."""
    raw = sum(max(0, int(p)) for p in enemy_points)
    today_before = max(0, int(today_before))
    gain = max(0, min(raw, max(0, int(cap)) - today_before))
    return gain, today_before + gain


def kill_cap(faction_override: Optional[int], s: TerritorySettings) -> int:
    """The faction's override when set, else the global setting."""
    return max(0, int(faction_override)) if faction_override is not None else int(s.kill_points_daily_cap)
