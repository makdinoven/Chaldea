"""FEAT-197 region reputation — DB layer (sync SQLAlchemy). Pure maths: ``reputation_core``.

* :func:`apply_reputation` — THE single write path (sources, staff edits); runs in the caller's transaction, never
  commits; the caller publishes ``ApplyResult.tier_changes`` (``reputation_notify``) after its commit;
* reads: effective value / tier per (character, region), gates (:func:`gate_failure`, :func:`npc_gate_failure`,
  :func:`require_tier`, :func:`require_npc_tier`), the trade refusal of a tier;
* player / admin read models and the admin settings writes (routers in ``reputation_api``).

Lock order: ``character_reputation`` rows of ONE character, ascending ``region_id`` (the decay pass walks
``(character_id, region_id)`` ascending). Reputation rows are always the LAST rows a transaction locks (guild hand-in
locks them after the ledger posting), so no cycle with the economy lock order is possible.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import econ_core
import econ_ledger
import law_core
import models
import renown_crud
import reputation_core as rc
import shadow_core as sc
from economy_crud import EconomyApiError

logger = logging.getLogger("character-service.reputation")

MAX_EVENT_KEY = 191
MAX_REASON = 500

MSG_CHARACTER_NOT_FOUND = "Персонаж не найден"
MSG_REGION_NOT_FOUND = "Регион не найден"
MSG_ACTION_NOT_FOUND = "Действие репутации не найдено"
MSG_NPC_TARGET = "У NPC нет репутации"
MSG_KEY_TOO_LONG = "Слишком длинный ключ события"
MSG_ACTION_EXISTS = "Действие с таким кодом уже есть"
MSG_ACTION_BUILTIN = "Встроенное действие удалить нельзя"
MSG_ACTION_NO_POINTS = "У этого действия нет очков — укажите изменение числом"
MSG_ROLES_FALLBACK = "Вес «*» (все остальные роли) обязателен"
MSG_ROLES_DUPLICATE = "Роль указана дважды: {role}"
MSG_GUILD_REFUSED = "Гильдия не работает с теми, кто вне закона (репутация: {tier})"
MSG_TRADE_REFUSED = "Торговцы этого края отказываются иметь с вами дело (репутация: {tier})"

SKIP_NPC = "npc"
SKIP_ZERO = "zero"
SKIP_CAP = "cap"

# The decay pass materialises a decaying row only when the tier changes, the value reaches 0 or at least this many
# points accrued — readers use reputation_core.effective_value anyway, so the stored value may lag (no journal spam).
DECAY_MIN_POINTS = 50


class ReputationError(EconomyApiError):
    """Business error of the reputation layer (HTTP status + Russian text); a subclass of the economy error, so the
    economy routers map it without changes."""


# =====================================================================================================================
# helpers / loaders
# =====================================================================================================================

def now_utc() -> datetime:
    """Naive UTC without microseconds."""
    return datetime.utcnow().replace(microsecond=0)


def _is_mysql(db: Session) -> bool:
    return db.get_bind().dialect.name == "mysql"


def _for_update(db: Session) -> bool:
    return db.get_bind().dialect.name != "sqlite"


def _in(prefix: str, values: Sequence) -> Tuple[str, Dict[str, object]]:
    names = [f"{prefix}{i}" for i in range(len(values))]
    return ", ".join(f":{n}" for n in names), dict(zip(names, values))


def load_settings(db: Session) -> rc.Settings:
    return rc.settings_from_row(db.execute(text(rc.SQL_SELECT_SETTINGS)).first())


def load_tiers(db: Session) -> List[rc.Tier]:
    return rc.tiers_from_rows(db.execute(text(rc.SQL_SELECT_TIERS)).fetchall())


@dataclass(frozen=True)
class Action:
    code: str
    name: str
    points: int
    daily_cap: Optional[int]
    is_builtin: bool
    has_source: bool
    sort_order: int


def _default_actions() -> Dict[str, Action]:
    return {code: Action(code, name, points, cap, True, bool(src), order)
            for code, name, points, cap, src, order in rc.DEFAULT_ACTIONS}


def _action_from_row(row: "models.ReputationAction") -> Action:
    return Action(row.code, row.name, int(row.points or 0), int(row.daily_cap) if row.daily_cap is not None else None,
                  bool(row.is_builtin), bool(row.has_source), int(row.sort_order or 0))


def list_actions(db: Session) -> List[Action]:
    """Table rows plus the builtin defaults missing from the table (a fresh test DB has no seeds)."""
    actions = _default_actions()
    for row in db.query(models.ReputationAction).all():
        actions[row.code] = _action_from_row(row)
    return sorted(actions.values(), key=lambda a: (a.sort_order, a.code))


def load_action(db: Session, code: str) -> Optional[Action]:
    row = db.get(models.ReputationAction, code)
    if row is not None:
        return _action_from_row(row)
    return _default_actions().get(code)


def action_names(db: Session) -> Dict[str, str]:
    names = {a.code: a.name for a in list_actions(db)}
    names[rc.ACTION_DECAY] = rc.DECAY_ACTION_NAME
    return names


def load_role_weights(db: Session) -> Dict[str, int]:
    rows = db.query(models.ReputationNpcRoleWeight).all()
    if not rows:
        return dict(rc.DEFAULT_NPC_ROLE_WEIGHTS)
    return {r.role: int(r.points) for r in rows}


@dataclass(frozen=True)
class RegionInfo:
    region_id: int
    name: Optional[str]
    country_id: Optional[int]
    country_name: Optional[str]


def region_infos(db: Session, region_ids: Iterable[int]) -> Dict[int, RegionInfo]:
    ids = sorted({int(r) for r in region_ids if r})
    if not ids:
        return {}
    ph, params = _in("r", ids)
    rows = db.execute(text(
        "SELECT r.id, r.name, r.country_id, c.name FROM Regions r LEFT JOIN Countries c ON c.id = r.country_id "
        f"WHERE r.id IN ({ph})"), params).fetchall()
    return {int(r[0]): RegionInfo(int(r[0]), r[1], int(r[2]) if r[2] is not None else None, r[3]) for r in rows}


def country_region_ids(db: Session, country_id: Optional[int]) -> List[int]:
    if country_id is None:
        return []
    rows = db.execute(text("SELECT id FROM Regions WHERE country_id = :c ORDER BY id"), {"c": int(country_id)})
    return [int(r[0]) for r in rows.fetchall()]


# FEAT-209: top-down mirror of econ_core.SQL_RESOLVE_LOCATION — locations whose own COALESCE(district region,
# location region) is in the set, plus descendants via parent_id that have no own region (nearest-ancestor rule).
# Nested districts need no recursion: every Districts row carries its own region_id.
SQL_REGION_LOCATION_IDS = """
WITH RECURSIVE scope (id, depth) AS (
  SELECT l.id, 0 FROM Locations l LEFT JOIN Districts d ON d.id = l.district_id
  WHERE COALESCE(d.region_id, l.region_id) IN :region_ids
  UNION ALL
  SELECT l.id, s.depth + 1 FROM Locations l JOIN scope s ON l.parent_id = s.id
  LEFT JOIN Districts d ON d.id = l.district_id
  WHERE COALESCE(d.region_id, l.region_id) IS NULL AND s.depth < :max_depth
)
SELECT DISTINCT id FROM scope
"""


def region_location_ids(db: Session, region_ids: Sequence[int]) -> List[int]:
    """Ids of all locations that resolve (like `location_region`) to any of `region_ids`."""
    ids = sorted({int(r) for r in region_ids})
    if not ids:
        return []
    rows = db.execute(
        text(SQL_REGION_LOCATION_IDS).bindparams(bindparam("region_ids", expanding=True)),
        {"region_ids": ids, "max_depth": econ_core.LOCATION_PARENT_DEPTH},
    ).fetchall()
    return sorted(int(r[0]) for r in rows)


def admin_geo_location_ids(db: Session, country_id: Optional[int], region_id: Optional[int]) -> Optional[List[int]]:
    """FEAT-209 §3.2 / FEAT-210 §3.4: location scope of the admin country/region list filter.

    ``None`` when neither is given (no geo filter). Otherwise the region (checked against the country when both are
    given — a foreign region yields an empty scope) or all regions of the country, expanded via
    ``region_location_ids``; ``[]`` for an empty scope.
    """
    if country_id is None and region_id is None:
        return None
    if region_id is not None:
        if country_id is not None:
            owner = db.execute(text("SELECT country_id FROM Regions WHERE id = :r"), {"r": int(region_id)}).scalar()
            region_ids = [int(region_id)] if owner is not None and int(owner) == int(country_id) else []
        else:
            region_ids = [int(region_id)]
    else:
        region_ids = country_region_ids(db, country_id)
    return region_location_ids(db, region_ids) if region_ids else []


def location_region(db: Session, location_id: Optional[int]) -> Optional[int]:
    region_id, _country = econ_ledger.resolve_location(db, location_id)
    return int(region_id) if region_id else None


# =====================================================================================================================
# reads + gates
# =====================================================================================================================

def effective(db: Session, character_id: int, region_id: Optional[int], *, settings: Optional[rc.Settings] = None,
              now: Optional[datetime] = None) -> int:
    """Effective value (0 without a row / region)."""
    if not region_id:
        return 0
    row = db.execute(text(rc.SQL_SELECT_VALUE), {"character_id": int(character_id),
                                                 "region_id": int(region_id)}).first()
    if row is None:
        return 0
    settings = settings or load_settings(db)
    return rc.effective_value(int(row[0]), row[1], now or now_utc(), settings.decay_per_day)


def tier_of(db: Session, character_id: int, region_id: Optional[int], *,
            tiers: Optional[Sequence[rc.Tier]] = None) -> rc.Tier:
    tiers = tiers or load_tiers(db)
    return rc.tier_for(effective(db, character_id, region_id), tiers)


def gate_failure(db: Session, character_id: int, region_id: Optional[int], min_code: Optional[str], *,
                 tiers: Optional[Sequence[rc.Tier]] = None) -> Optional[str]:
    """«Нужна репутация: X» when the character misses the tier ``min_code`` in the region, else None.
    No gate code / no region = open."""
    if not min_code or not region_id:
        return None
    tiers = tiers or load_tiers(db)
    if rc.tier_by_code(min_code, tiers) is None:
        return None
    if rc.meets(effective(db, character_id, region_id), min_code, tiers):
        return None
    return rc.gate_message(min_code, tiers)


def require_tier(db: Session, character_id: int, region_id: Optional[int], min_code: Optional[str]) -> None:
    message = gate_failure(db, character_id, region_id, min_code)
    if message:
        raise ReputationError(403, message)


def _npc_gate_row(db: Session, npc_id: int):
    return db.execute(text("SELECT reputation_min_tier, current_location_id FROM characters WHERE id = :id"),
                      {"id": int(npc_id)}).first()


def npc_gate_failure(db: Session, character_id: int, npc_id: int, region_id: Optional[int] = None) -> Optional[str]:
    """The NPC-level gate (``characters.reputation_min_tier``) in the NPC's region (``region_id`` when the caller has
    already resolved it)."""
    row = _npc_gate_row(db, npc_id)
    if row is None or not row[0]:
        return None
    if region_id is None:
        region_id = location_region(db, row[1])
    return gate_failure(db, character_id, region_id, row[0])


def require_npc_tier(db: Session, character_id: int, npc_id: int, region_id: Optional[int] = None) -> None:
    message = npc_gate_failure(db, character_id, npc_id, region_id)
    if message:
        raise ReputationError(403, message)


def refused_tier(db: Session, character_id: int, region_id: Optional[int]) -> Optional[rc.Tier]:
    """The character's tier in the region when that tier refuses trade (Вне закона), else None."""
    if not region_id:
        return None
    tier = tier_of(db, character_id, region_id)
    return tier if tier.trade_refused else None


def guild_lock_reason(db: Session, character_id: int, npc_id: int, region_id: Optional[int]) -> Optional[str]:
    """Merchant guild (§3.14 A4): the NPC gate, then the trade refusal of the tier."""
    message = npc_gate_failure(db, character_id, npc_id, region_id)
    if message:
        return message
    tier = refused_tier(db, character_id, region_id)
    if tier is not None:
        return MSG_GUILD_REFUSED.format(tier=tier.name)
    return None


# =====================================================================================================================
# the write path
# =====================================================================================================================

@dataclass(frozen=True)
class RegionChange:
    region_id: int
    is_echo: bool
    value_before: int           # effective value before the change (decay materialised)
    value_after: int
    applied_delta: int
    tier_before: str
    tier_after: str


@dataclass(frozen=True)
class TierChange:
    character_id: int
    user_id: Optional[int]
    region_id: int
    region_name: Optional[str]
    tier_before: str
    tier_before_name: str
    tier_after: str
    tier_after_name: str
    direction: str              # up | down | decay


@dataclass
class ApplyResult:
    duplicate: bool = False
    skipped: Optional[str] = None
    changes: List[RegionChange] = field(default_factory=list)
    tier_changes: List[TierChange] = field(default_factory=list)
    fame_changes: list = field(default_factory=list)            # FEAT-199: renown_crud.RenownChange

    @property
    def applied(self) -> bool:
        return not self.duplicate and self.skipped is None and bool(self.changes)


def _decay_key(character_id: int, region_id: int, anchor: datetime) -> str:
    return f"decay:{character_id}:{region_id}:{anchor.isoformat()}"


def _ensure_rows(db: Session, character_id: int, region_ids: Sequence[int], now: datetime) -> None:
    ph, params = _in("r", list(region_ids))
    params["c"] = int(character_id)
    have = {int(r[0]) for r in db.execute(text(
        f"SELECT region_id FROM character_reputation WHERE character_id = :c AND region_id IN ({ph})"),
        params).fetchall()}
    missing = [r for r in region_ids if r not in have]
    if not missing:
        return
    if _is_mysql(db):
        sql = ("INSERT INTO character_reputation (character_id, region_id, value, decay_at, updated_at) "
               "VALUES (:c, :r, 0, NULL, :now) ON DUPLICATE KEY UPDATE id = id")
    else:
        sql = ("INSERT OR IGNORE INTO character_reputation (character_id, region_id, value, decay_at, updated_at) "
               "VALUES (:c, :r, 0, NULL, :now)")
    for region_id in sorted(missing):
        db.execute(text(sql), {"c": int(character_id), "r": int(region_id), "now": now})


def lock_rows(db: Session, character_id: int, region_ids: Sequence[int]) -> List["models.CharacterReputation"]:
    query = (db.query(models.CharacterReputation)
             .filter(models.CharacterReputation.character_id == int(character_id),
                     models.CharacterReputation.region_id.in_([int(r) for r in region_ids]))
             .order_by(models.CharacterReputation.region_id))
    if _for_update(db):
        query = query.with_for_update()
    return query.populate_existing().all()


def _log(db: Session, *, character_id: int, region_id: int, action: str, key: str, is_echo: bool,
         origin_region_id: Optional[int], requested: int, applied: int, value_after: int, tier_before: str,
         tier_after: str, reason: Optional[str], actor_user_id: Optional[int], now: datetime) -> None:
    db.add(models.ReputationLog(
        character_id=int(character_id), region_id=int(region_id), action=action, event_key=key, is_echo=bool(is_echo),
        origin_region_id=origin_region_id, requested_delta=int(requested), applied_delta=int(applied),
        value_after=int(value_after), tier_before=tier_before, tier_after=tier_after,
        reason=(reason[:MAX_REASON] if reason else None), actor_user_id=actor_user_id, created_at=now))


def materialise_row(db: Session, row: "models.CharacterReputation", *, settings: rc.Settings,
                    tiers: Sequence[rc.Tier], now: datetime, force: bool = True) -> Optional[TierChange]:
    """Materialise the negative decay of a LOCKED row (journal row ``decay`` when points > 0). With ``force=False``
    (the decay pass) only when the tier changes, the value reaches 0 or :data:`DECAY_MIN_POINTS` accrued.
    Returns the tier change (direction ``decay``) without user / region names (the caller fills them)."""
    value = int(row.value or 0)
    new_value, new_anchor, points = rc.materialise_decay(value, row.decay_at, now, settings.decay_per_day)
    if points <= 0:
        return None
    before, after = rc.tier_for(value, tiers), rc.tier_for(new_value, tiers)
    if not force and before.code == after.code and new_value < 0 and points < DECAY_MIN_POINTS:
        return None
    _log(db, character_id=row.character_id, region_id=row.region_id, action=rc.ACTION_DECAY,
         key=_decay_key(row.character_id, row.region_id, row.decay_at), is_echo=False, origin_region_id=None,
         requested=points, applied=points, value_after=new_value, tier_before=before.code, tier_after=after.code,
         reason=None, actor_user_id=None, now=now)
    row.value = new_value
    row.decay_at = new_anchor
    row.updated_at = now
    if before.code == after.code:
        return None
    return TierChange(int(row.character_id), None, int(row.region_id), None, before.code, before.name, after.code,
                      after.name, rc.DIRECTION_DECAY)


def apply_reputation(db: Session, *, character_id: int, region_id: int, action: str, idem_key: str,
                     delta: Optional[int] = None, reason: Optional[str] = None, actor_user_id: Optional[int] = None,
                     echo: bool = True, now: Optional[datetime] = None) -> ApplyResult:
    """Apply one reputation event (origin region + echo to the other regions of its country) in the caller's
    transaction. Idempotent per ``(idem_key, origin region)``: a repeat is a silent ``duplicate=True``.
    Raises :class:`ReputationError` (404 character / region / action, 400 key too long)."""
    now = now or now_utc()
    character_id, region_id = int(character_id), int(region_id)
    if len(idem_key or "") > MAX_EVENT_KEY or not idem_key:
        raise ReputationError(400, MSG_KEY_TOO_LONG)

    # 1. player only
    char = db.execute(text("SELECT id, is_npc, user_id FROM characters WHERE id = :id"), {"id": character_id}).first()
    if char is None:
        raise ReputationError(404, MSG_CHARACTER_NOT_FOUND)
    if bool(char[1]):
        return ApplyResult(skipped=SKIP_NPC)
    user_id = int(char[2]) if char[2] is not None else None

    # 2. action + delta
    act = load_action(db, action)
    if act is None:
        raise ReputationError(404, MSG_ACTION_NOT_FOUND)
    delta = int(delta) if delta is not None else int(act.points)
    if delta == 0:
        return ApplyResult(skipped=SKIP_ZERO)

    infos = region_infos(db, [region_id])
    origin = infos.get(region_id)
    if origin is None:
        raise ReputationError(404, MSG_REGION_NOT_FOUND)

    # 3. duplicate pre-check (UNIQUE(event_key, region_id) is the hard guarantee)
    if db.execute(text("SELECT 1 FROM reputation_log WHERE event_key = :k AND region_id = :r"),
                  {"k": idem_key, "r": region_id}).first() is not None:
        return ApplyResult(duplicate=True)

    # 4. daily cap (automatic positive deltas only)
    if actor_user_id is None and delta > 0 and act.daily_cap:
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        used = int(db.execute(text(
            "SELECT COALESCE(SUM(applied_delta), 0) FROM reputation_log WHERE character_id = :c AND region_id = :r "
            "AND action = :a AND is_echo = 0 AND applied_delta > 0 AND created_at >= :d"),
            {"c": character_id, "r": region_id, "a": act.code, "d": day_start}).scalar() or 0)
        delta = min(delta, int(act.daily_cap) - used)
        if delta <= 0:
            return ApplyResult(skipped=SKIP_CAP)

    # 5. targets
    settings, tiers = load_settings(db), load_tiers(db)
    echo_d = rc.echo_delta(delta, settings.echo_pct) if echo else 0
    targets = {region_id: delta}
    if echo_d != 0:
        for other in country_region_ids(db, origin.country_id):
            if other != region_id:
                targets[other] = echo_d
    if len(targets) > 1:
        infos = region_infos(db, targets)

    # 6. rows (create missing, lock all by region_id)
    _ensure_rows(db, character_id, sorted(targets), now)
    rows = lock_rows(db, character_id, sorted(targets))

    # 7. apply
    result = ApplyResult()
    for row in rows:
        rid = int(row.region_id)
        materialise_row(db, row, settings=settings, tiers=tiers, now=now)
        old = int(row.value or 0)
        requested = targets[rid]
        new = rc.clamp(old + requested, settings)
        before, after = rc.tier_for(old, tiers), rc.tier_for(new, tiers)
        is_echo = rid != region_id
        _log(db, character_id=character_id, region_id=rid, action=act.code, key=idem_key, is_echo=is_echo,
             origin_region_id=region_id if is_echo else None, requested=requested, applied=new - old,
             value_after=new, tier_before=before.code, tier_after=after.code, reason=reason,
             actor_user_id=actor_user_id, now=now)
        row.decay_at = rc.next_decay_at(old, new, row.decay_at, now)
        row.value = new
        row.updated_at = now
        result.changes.append(RegionChange(rid, is_echo, old, new, new - old, before.code, after.code))
        if before.code != after.code:
            info = infos.get(rid)
            result.tier_changes.append(TierChange(
                character_id, user_id, rid, info.name if info else None, before.code, before.name, after.code,
                after.name, rc.DIRECTION_UP if after.sort_order > before.sort_order else rc.DIRECTION_DOWN))
    db.flush()

    # 8. FEAT-199 fame hook: an automatic (not staff) positive change of the ORIGIN region feeds fame
    origin_applied = sum(c.applied_delta for c in result.changes if not c.is_echo)
    if actor_user_id is None and origin_applied > 0:
        gain = sc.fame_from_reputation(act.code, origin_applied, renown_crud.load_shadow_settings(db))
        if gain > 0:
            fame = renown_crud.add_fame(db, character_id=character_id, points=gain, source=sc.SOURCE_REPUTATION,
                                        event_key=fame_rep_key(idem_key), now=now)
            if fame.change is not None:
                result.fame_changes.append(fame.change)
    return result


FAME_REP_PREFIX = "fame:rep:"


def fame_rep_key(idem_key: str) -> str:
    """FEAT-200 (fix 8): fame event key of a reputation change. A plain prefix while it fits the column; a
    longer one is hashed (sha1 of the whole reputation key) instead of truncated, so two distinct long keys
    with a common head never collapse into one fame event."""
    key = f"{FAME_REP_PREFIX}{idem_key}"
    if len(key) <= MAX_EVENT_KEY:
        return key
    return f"{FAME_REP_PREFIX}sha1:{hashlib.sha1(idem_key.encode('utf-8')).hexdigest()}"


def npc_kill_points(db: Session, npc: "models.Character") -> int:
    """Kill weight of an NPC exactly as the kill reputation resolves it (override ?? role weight ?? '*').
    FEAT-198 derives the crime weight from it (law_core.crime_weight)."""
    return rc.kill_points(npc.reputation_kill_points, npc.npc_role, load_role_weights(db))


def apply_npc_kill(db: Session, npc: "models.Character", *, battle_id: Optional[int],
                   killer_ids: Iterable[int], now: Optional[datetime] = None) -> List[ApplyResult]:
    """Kill reputation for every PLAYER on the winning side (full weight each, §3.14 A5), in the caller's
    transaction. The region is the NPC's location at death; no region / zero weight = nothing."""
    now = now or now_utc()
    ids = sorted({int(k) for k in killer_ids or () if k and int(k) != int(npc.id)})
    if not ids:
        return []
    region_id = location_region(db, npc.current_location_id)
    if not region_id:
        return []
    points = npc_kill_points(db, npc)
    if points == 0:
        return []
    ph, params = _in("k", ids)
    players = [int(r[0]) for r in db.execute(text(
        f"SELECT id FROM characters WHERE id IN ({ph}) AND is_npc = 0 ORDER BY id"), params).fetchall()]
    stamp = kill_stamp(battle_id, now)
    return [apply_npc_kill_for(db, npc, killer_id, region_id, points, stamp, battle_id=battle_id, now=now)
            for killer_id in players]


def kill_stamp(battle_id: Optional[int], now: datetime) -> str:
    """The event stamp of a kill: the battle id, or the time when there is no battle."""
    return str(int(battle_id)) if battle_id else f"t{now.strftime('%Y%m%d%H%M%S')}"


def npc_kill_key(npc_id: int, stamp: str, killer_id: int) -> str:
    return f"npc_kill:{int(npc_id)}:{stamp}:{int(killer_id)}"


def npc_kill_reason(npc: "models.Character", battle_id: Optional[int]) -> str:
    # FEAT-200 (fix 4): a guard is knocked out, never killed (FEAT-198) — the journal says so
    if (getattr(npc, "npc_role", None) or "") == law_core.GUARD_ROLE:
        head = f"Повержен стражник «{npc.name}» (#{npc.id})"
    else:
        head = f"Убит NPC «{npc.name}» (#{npc.id})"
    return head + (f" в бою #{battle_id}" if battle_id else "")


def apply_npc_kill_for(db: Session, npc: "models.Character", killer_id: int, region_id: int, points: int,
                       stamp: str, *, battle_id: Optional[int], now: datetime) -> ApplyResult:
    """The kill reputation of ONE player (FEAT-199: also used by the witnessed path of ``shadow_crud``)."""
    return apply_reputation(db, character_id=killer_id, region_id=region_id, action=rc.ACTION_NPC_KILL,
                            idem_key=npc_kill_key(npc.id, stamp, killer_id), delta=points,
                            reason=npc_kill_reason(npc, battle_id), now=now)


def tier_changes_of(results: Iterable[ApplyResult]) -> List[TierChange]:
    out: List[TierChange] = []
    for r in results:
        out.extend(r.tier_changes)
    return out


def fame_changes_of(results: Iterable[ApplyResult]) -> list:
    """FEAT-199: the fame tier changes of the results (publish with ``renown_crud.publish_fame_changes``)."""
    out: list = []
    for r in results:
        out.extend(getattr(r, "fame_changes", None) or ())
    return out


# =====================================================================================================================
# player read models (no numbers)
# =====================================================================================================================

def _tiers_out(tiers: Sequence[rc.Tier]) -> List[dict]:
    return [{"code": t.code, "name": t.name, "sort_order": t.sort_order} for t in rc.sorted_tiers(tiers)]


def _player_entry(info: RegionInfo, value: int, tiers, settings) -> dict:
    tier = rc.tier_for(value, tiers)
    return {
        "region_id": info.region_id,
        "region_name": info.name,
        "country_id": info.country_id,
        "country_name": info.country_name,
        "tier_code": tier.code,
        "tier_name": tier.name,
        "progress": rc.progress(value, tiers, settings),
        "trade_refused": bool(tier.trade_refused),
    }


def _is_npc(db: Session, character_id: int) -> bool:
    row = db.execute(text("SELECT is_npc FROM characters WHERE id = :id"), {"id": int(character_id)}).first()
    if row is None:
        raise ReputationError(404, MSG_CHARACTER_NOT_FOUND)
    return bool(row[0])


def _values(db: Session, character_id: int, settings: rc.Settings, now: datetime,
            region_id: Optional[int] = None) -> Dict[int, Tuple[int, "models.CharacterReputation"]]:
    query = db.query(models.CharacterReputation).filter(models.CharacterReputation.character_id == int(character_id))
    if region_id is not None:
        query = query.filter(models.CharacterReputation.region_id == int(region_id))
    return {int(r.region_id): (rc.effective_value(int(r.value or 0), r.decay_at, now, settings.decay_per_day), r)
            for r in query.all()}


def _sort_key(entry: dict):
    return (entry.get("country_name") or "", entry.get("region_name") or "", entry["region_id"])


def player_view(db: Session, character_id: int, region_id: Optional[int] = None) -> dict:
    """``GET /characters/{id}/reputation``: tier + progress per visited region (one region with ``region_id``)."""
    settings, tiers, now = load_settings(db), load_tiers(db), now_utc()
    out = {"regions": [], "tiers": _tiers_out(tiers)}
    if region_id is not None:
        info = region_infos(db, [region_id]).get(int(region_id))
        if info is None:
            raise ReputationError(404, MSG_REGION_NOT_FOUND)
        if _is_npc(db, character_id):
            return out
        values = _values(db, character_id, settings, now, region_id)
        out["regions"].append(_player_entry(info, values.get(int(region_id), (0, None))[0], tiers, settings))
        return out
    if _is_npc(db, character_id):
        return out
    values = _values(db, character_id, settings, now)
    infos = region_infos(db, values)
    out["regions"] = sorted((_player_entry(infos[rid], value, tiers, settings)
                             for rid, (value, _row) in values.items() if rid in infos), key=_sort_key)
    return out


def _history_text(row: "models.ReputationLog", region_name: Optional[str]) -> str:
    region = f"«{region_name}»" if region_name else "этого края"
    if row.action == rc.ACTION_DECAY:
        return f"Жители края {region} понемногу забывают ваши проступки"
    better = "лучше" if int(row.applied_delta) > 0 else "хуже"
    if row.is_echo:
        return f"До жителей края {region} дошли слухи о вас — к вам стали относиться {better}"
    return f"Жители края {region} стали относиться к вам {better}"


def _history_query(db: Session, character_id: int, region_id: Optional[int], *, nonzero: bool):
    query = db.query(models.ReputationLog).filter(models.ReputationLog.character_id == int(character_id))
    if region_id is not None:
        query = query.filter(models.ReputationLog.region_id == int(region_id))
    if nonzero:
        query = query.filter(models.ReputationLog.applied_delta != 0)
    return query


def player_history(db: Session, character_id: int, region_id: Optional[int], page: int, page_size: int) -> dict:
    """Journal phrases only: no deltas, values or staff reasons."""
    _is_npc(db, character_id)
    query = _history_query(db, character_id, region_id, nonzero=True)
    total = query.count()
    rows = (query.order_by(models.ReputationLog.created_at.desc(), models.ReputationLog.id.desc())
            .offset((page - 1) * page_size).limit(page_size).all())
    infos = region_infos(db, {int(r.region_id) for r in rows})
    names = action_names(db)
    tiers = {t.code: t for t in load_tiers(db)}
    items = []
    for row in rows:
        info = infos.get(int(row.region_id))
        region_name = info.name if info else None
        after = tiers.get(row.tier_after)
        items.append({
            "created_at": row.created_at,
            "region_id": int(row.region_id),
            "region_name": region_name,
            "direction": rc.direction(int(row.applied_delta)),
            "action_name": names.get(row.action, row.action),
            "text": _history_text(row, region_name),
            "tier_after_name": after.name if after else row.tier_after,
            "tier_changed": row.tier_before != row.tier_after,
        })
    return {"items": items, "total": int(total)}


# =====================================================================================================================
# admin read models (numbers)
# =====================================================================================================================

def admin_character(db: Session, character_id: int) -> List[dict]:
    _is_npc(db, character_id)
    settings, tiers, now = load_settings(db), load_tiers(db), now_utc()
    values = _values(db, character_id, settings, now)
    infos = region_infos(db, values)
    out = []
    for rid, (value, row) in values.items():
        info = infos.get(rid)
        tier = rc.tier_for(value, tiers)
        out.append({
            "region_id": rid,
            "region_name": info.name if info else None,
            "country_id": info.country_id if info else None,
            "country_name": info.country_name if info else None,
            "value": value,
            "tier_code": tier.code,
            "tier_name": tier.name,
            "decaying": value < 0 and row.decay_at is not None and settings.decay_per_day > 0,
            "updated_at": row.updated_at,
        })
    return sorted(out, key=_sort_key)


def _usernames(db: Session, user_ids: Iterable[int]) -> Dict[int, str]:
    ids = sorted({int(u) for u in user_ids if u})
    if not ids:
        return {}
    ph, params = _in("u", ids)
    try:
        rows = db.execute(text(f"SELECT id, username FROM users WHERE id IN ({ph})"), params).fetchall()
    except SQLAlchemyError:          # users is owned by user-service (absent in unit-test databases)
        logger.warning("reputation history: usernames unavailable")
        return {}
    return {int(r[0]): r[1] for r in rows}


def admin_history(db: Session, character_id: int, region_id: Optional[int], page: int, page_size: int) -> dict:
    _is_npc(db, character_id)
    query = _history_query(db, character_id, region_id, nonzero=False)
    total = query.count()
    rows = (query.order_by(models.ReputationLog.created_at.desc(), models.ReputationLog.id.desc())
            .offset((page - 1) * page_size).limit(page_size).all())
    infos = region_infos(db, {int(r.region_id) for r in rows} | {int(r.origin_region_id) for r in rows
                                                                    if r.origin_region_id})
    names = action_names(db)
    tiers = {t.code: t for t in load_tiers(db)}
    users = _usernames(db, [r.actor_user_id for r in rows])
    items = []
    for row in rows:
        info = infos.get(int(row.region_id))
        origin = infos.get(int(row.origin_region_id)) if row.origin_region_id else None
        items.append({
            "id": int(row.id),
            "created_at": row.created_at,
            "region_id": int(row.region_id),
            "region_name": info.name if info else None,
            "action": row.action,
            "action_name": names.get(row.action, row.action),
            "event_key": row.event_key,
            "is_echo": bool(row.is_echo),
            "origin_region_id": int(row.origin_region_id) if row.origin_region_id else None,
            "origin_region_name": origin.name if origin else None,
            "requested_delta": int(row.requested_delta),
            "applied_delta": int(row.applied_delta),
            "value_after": int(row.value_after),
            "tier_before": row.tier_before,
            "tier_before_name": tiers[row.tier_before].name if row.tier_before in tiers else row.tier_before,
            "tier_after": row.tier_after,
            "tier_after_name": tiers[row.tier_after].name if row.tier_after in tiers else row.tier_after,
            "reason": row.reason,
            "actor_user_id": row.actor_user_id,
            "actor_username": users.get(int(row.actor_user_id)) if row.actor_user_id else None,
        })
    return {"items": items, "total": int(total)}


def admin_adjust(db: Session, character_id: int, *, region_id: int, delta: Optional[int], action_code: Optional[str],
                 reason: str, echo: bool, request_id: str, actor_user_id: int) -> Tuple[dict, ApplyResult]:
    """Staff edit (``reputation:manage``): one of ``delta`` (action ``admin_manual``) / ``action_code`` (its points).
    Idempotent per ``admin:{user}:{request_id}``. Returns the response body and the result (tier changes)."""
    if _is_npc(db, character_id):
        raise ReputationError(400, MSG_NPC_TARGET)
    if action_code:
        act = load_action(db, action_code)
        if act is None:
            raise ReputationError(404, MSG_ACTION_NOT_FOUND)
        if int(act.points) == 0:
            raise ReputationError(400, MSG_ACTION_NO_POINTS)
        code, value = act.code, int(act.points)
    else:
        code, value = rc.ACTION_ADMIN, int(delta or 0)
    result = apply_reputation(db, character_id=character_id, region_id=region_id, action=code,
                              idem_key=f"admin:{actor_user_id}:{request_id}", delta=value, reason=reason,
                              actor_user_id=actor_user_id, echo=echo)
    body = {
        "duplicate": result.duplicate,
        "changes": [{"region_id": c.region_id, "is_echo": c.is_echo, "value_before": c.value_before,
                     "value_after": c.value_after, "tier_before": c.tier_before, "tier_after": c.tier_after}
                    for c in result.changes],
    }
    return body, result


# =====================================================================================================================
# admin settings
# =====================================================================================================================

def _tier_out(t: rc.Tier) -> dict:
    return {"code": t.code, "sort_order": t.sort_order, "name": t.name, "min_value": t.min_value,
            "price_pct": float(t.price_pct), "sell_pct": float(t.sell_pct), "trade_refused": bool(t.trade_refused)}


def settings_out(db: Session) -> dict:
    s = load_settings(db)
    return {
        "settings": {"min_value": int(s.min_value), "max_value": int(s.max_value), "echo_pct": float(s.echo_pct),
                     "decay_per_day": float(s.decay_per_day)},
        "tiers": [_tier_out(t) for t in load_tiers(db)],
    }


def _lock_decaying(db: Session) -> List["models.CharacterReputation"]:
    query = (db.query(models.CharacterReputation)
             .filter(models.CharacterReputation.value < 0, models.CharacterReputation.decay_at.isnot(None))
             .order_by(models.CharacterReputation.character_id, models.CharacterReputation.region_id))
    if _for_update(db):
        query = query.with_for_update()
    return query.populate_existing().all()


def update_settings(db: Session, body) -> dict:
    """Validate and store the settings + all 8 tiers (``reputation:settings``). A changed decay rate first
    materialises every decaying row with the OLD rate (same transaction), so the change is not retroactive."""
    old = load_settings(db)
    new = rc.Settings(min_value=int(body.settings.min_value), max_value=int(body.settings.max_value),
                      echo_pct=Decimal(str(body.settings.echo_pct)),
                      decay_per_day=Decimal(str(body.settings.decay_per_day)))
    tiers = [rc.Tier(code=t.code, sort_order=rc.TIER_CODES.index(t.code) + 1 if t.code in rc.TIER_CODES else 0,
                     name=(t.name or "").strip(), min_value=t.min_value, price_pct=Decimal(str(t.price_pct)),
                     sell_pct=Decimal(str(t.sell_pct)), trade_refused=bool(t.trade_refused)) for t in body.tiers]
    error = rc.validate(new, tiers)
    if error:
        raise ReputationError(400, error)
    now = now_utc()
    if Decimal(str(new.decay_per_day)) != Decimal(str(old.decay_per_day)):
        old_tiers = load_tiers(db)
        for row in _lock_decaying(db):
            materialise_row(db, row, settings=old, tiers=old_tiers, now=now)
            if old.decay_per_day <= 0 and int(row.value or 0) < 0:
                row.decay_at = now          # decay was off: the new rate counts from now, not from the old anchor
    row = db.get(models.ReputationSettings, 1)
    if row is None:
        row = models.ReputationSettings(id=1, updated_at=now)
        db.add(row)
    row.min_value, row.max_value = new.min_value, new.max_value
    row.echo_pct, row.decay_per_day = new.echo_pct, new.decay_per_day
    row.updated_at = now
    existing = {t.code: t for t in db.query(models.ReputationTier).all()}
    # sort_order is UNIQUE and fixed per code: rows never swap orders, so in-place updates are safe
    for tier in tiers:
        target = existing.get(tier.code)
        if target is None:
            target = models.ReputationTier(code=tier.code, sort_order=tier.sort_order)
            db.add(target)
        target.sort_order = tier.sort_order
        target.name = tier.name
        target.min_value = tier.min_value
        target.price_pct = tier.price_pct
        target.sell_pct = tier.sell_pct
        target.trade_refused = tier.trade_refused
    db.flush()
    return settings_out(db)


def _action_out(a: Action) -> dict:
    return {"code": a.code, "name": a.name, "points": a.points, "daily_cap": a.daily_cap, "is_builtin": a.is_builtin,
            "has_source": a.has_source, "sort_order": a.sort_order}


def actions_out(db: Session) -> List[dict]:
    return [_action_out(a) for a in list_actions(db)]


def _materialise_builtin(db: Session, code: str) -> Optional["models.ReputationAction"]:
    """The table row of an action; a builtin missing from the table (fresh DB) is created from its default."""
    row = db.get(models.ReputationAction, code)
    if row is None and code in rc.BUILTIN_ACTION_CODES:
        a = _default_actions()[code]
        row = models.ReputationAction(code=a.code, name=a.name, points=a.points, daily_cap=a.daily_cap,
                                      is_builtin=True, has_source=a.has_source, sort_order=a.sort_order)
        db.add(row)
    return row


def create_action(db: Session, body) -> dict:
    if load_action(db, body.code) is not None:
        raise ReputationError(409, MSG_ACTION_EXISTS)
    max_order = max((a.sort_order for a in list_actions(db)), default=0)
    row = models.ReputationAction(code=body.code, name=body.name.strip(), points=int(body.points),
                                  daily_cap=body.daily_cap, is_builtin=False, has_source=False,
                                  sort_order=int(body.sort_order) if body.sort_order is not None else max_order + 10)
    db.add(row)
    db.flush()
    return _action_out(_action_from_row(row))


def update_action(db: Session, code: str, body) -> dict:
    row = _materialise_builtin(db, code)
    if row is None:
        raise ReputationError(404, MSG_ACTION_NOT_FOUND)
    row.name = body.name.strip()
    row.points = int(body.points)
    row.daily_cap = body.daily_cap
    if body.sort_order is not None:
        row.sort_order = int(body.sort_order)
    db.flush()
    return _action_out(_action_from_row(row))


def delete_action(db: Session, code: str) -> None:
    if code in rc.BUILTIN_ACTION_CODES:
        raise ReputationError(409, MSG_ACTION_BUILTIN)
    row = db.get(models.ReputationAction, code)
    if row is None:
        raise ReputationError(404, MSG_ACTION_NOT_FOUND)
    if row.is_builtin:
        raise ReputationError(409, MSG_ACTION_BUILTIN)
    db.delete(row)
    db.flush()


def roles_out(db: Session) -> List[dict]:
    weights = load_role_weights(db)
    return [{"role": role, "points": points}
            for role, points in sorted(weights.items(), key=lambda kv: (kv[0] == rc.ROLE_FALLBACK, kv[0]))]


def replace_roles(db: Session, items) -> List[dict]:
    seen = set()
    for item in items:
        if item.role in seen:
            raise ReputationError(400, MSG_ROLES_DUPLICATE.format(role=item.role))
        seen.add(item.role)
    if rc.ROLE_FALLBACK not in seen:
        raise ReputationError(400, MSG_ROLES_FALLBACK)
    db.query(models.ReputationNpcRoleWeight).delete(synchronize_session=False)
    for item in items:
        db.add(models.ReputationNpcRoleWeight(role=item.role, points=int(item.points)))
    db.flush()
    return roles_out(db)


def validate_tier_code(code: Optional[str]) -> Optional[str]:
    """Normalise a gate field: '' / None -> None; a known code -> itself; else ValueError (schema validators)."""
    if code is None:
        return None
    code = str(code).strip()
    if not code:
        return None
    if code not in rc.TIER_CODES:
        raise ValueError("Неизвестная ступень репутации")
    return code
