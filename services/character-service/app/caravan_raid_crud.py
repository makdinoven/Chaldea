"""FEAT-211 stage 2 — raids on physical caravans (sync SQLAlchemy; contract 3.6 / 3.8 / 3.13 A1–A3).

* **visibility** (A1) — :func:`caravans_here`: the physical caravans standing in the character's own location
  (group, guards, state, time to departure) — never the origin, destination, route or value;
* **start** (A2, 3.6) — :func:`begin_raid` (Tx A: the raid row, UNIQUE caravan = one raid per caravan),
  :func:`spawn_guards` (hidden ``spawn_type='dungeon'`` mobs from the admin guard pool), then the API asks
  battle-service for the fight (``battle_client.create_caravan_raid_battle``) and calls :func:`mark_fighting`
  (Tx B) or :func:`abandon_start` (any failure: guards despawned, raid row deleted — no leftovers);
* **settlement** (A3 / the poll, 3.8) — :func:`settle_raid` (Tx 1, economy): a won raid takes
  ``caravan_raid_goods_share`` of the remaining units (→ stolen bales) and ``caravan_raid_marks_share`` of the paid
  escrow (ledger op ``caravan_raid``: escrow → raiders, untaxed); every outcome releases the caravan (it moves on with
  the rest). Then :func:`law_step` (Tx 2: ``shadow_crud.caravan_raid_consequences``), :func:`deliver_bales`
  (inventory-service) and :func:`despawn_guards`;
* **caravan pass hooks** (3.3 steps 1–3, called by ``caravan_pass``): :func:`expire_stale_raids`,
  :func:`poll_raid_battles`, :func:`raid_followups` — ``fn(factory, now, params) -> int``.
* **player escorts** (FEAT-212 §3.9): an activity-locked leader (an escort included) is refused before any spawn;
  :func:`spawn_guards` spawns ``max(1, min(guards, 5 − escorts))`` mobs and puts the caravan's active escorts on
  :class:`RaidStart`; battle-service places them on the guard team and answers which ones it placed —
  :func:`mark_fighting` stores them (``escort_ids``) and flags their rows ``in_raid``. :func:`settle_raid`: ``won`` →
  every placed escort falls out, ``repelled`` → only the fallen ones (``fallen_character_ids`` of the callback / the
  poll), ``aborted`` → they stay, ``expired`` → they are released. Faction points of a won raid
  (:func:`raid_faction_points`, claimed by ``faction_done``) run next to the law step.

Lock order (FEAT-211 3.16 + FEAT-212 §3.15): ``econ_caravans(row) → econ_caravan_raids(row) → econ_caravan_escorts
(asc id) → econ_caravan_raid_shares (insert) → characters (asc id, ONE sorted lock call for raiders ∪ escorts) →
econ_accounts (asc id)``. Law / reputation rows are written only in the separate law transaction, which first claims
the raid row by a conditional ``law_done`` UPDATE; faction rows only in ``faction_kills.apply_caravan_deed``'s own
transactions (nothing else open). Notices are published after the commit. Raider team = 0, guard team = 1.
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_FLOOR, Decimal
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import httpx
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

import activity_lock
import caravan_escort_crud as escort_crud
import econ_caravan
import econ_core as core
import econ_ledger
import economy_caravan_crud as caravan_crud
import law_crud
import law_notify
import models
from config import settings
from economy_crud import EconomyApiError

logger = logging.getLogger("character-service.caravan_raids")

SessionFactory = Callable[[], Session]

RAIDER_TEAM = 0
GUARD_TEAM = 1

STATUS_STARTING = "starting"
STATUS_FIGHTING = "fighting"
STATUS_WON = "won"
STATUS_REPELLED = "repelled"
STATUS_ABORTED = "aborted"
STATUS_EXPIRED = "expired"
ACTIVE_STATUSES = (STATUS_STARTING, STATUS_FIGHTING)
FINAL_STATUSES = (STATUS_WON, STATUS_REPELLED, STATUS_ABORTED, STATUS_EXPIRED)
RESULT_ALREADY = "already"
RESULT_UNKNOWN = "unknown"

STATE_ON_ROAD = "on_road"
STATE_HELD = "held"
STATE_UNDER_ATTACK = "under_attack"
STATE_RAIDED = "raided"

KEY_RAID = "raid"
SPAWN_TYPE = "dungeon"                    # hidden from the location lists; despawned by crud.despawn_dungeon_mobs
MAX_GUARDS = 5                            # battle team size
STALE_STARTING_AFTER = timedelta(minutes=10)
POLL_AFTER = timedelta(minutes=2)
BALE_RETRY_AFTER = timedelta(minutes=1)   # the pass leaves fresh shares to the callback path
FINISHED_BATTLE_STATUSES = ("finished", "forfeit")
BATCH_SIZE = 200
HTTP_TIMEOUT_SECONDS = 10.0
LOG_EVENT_TYPE = "caravan_raid"
WS_CARAVAN_RAID = "caravan_raid"

MSG_CARAVAN_NOT_FOUND = "Караван не найден"
MSG_NOT_HERE = "Каравана нет в вашей локации"
MSG_ALREADY_RAIDED = "Этот караван уже ограблен или на него уже напали"
MSG_ARRIVED = "Караван уже прибыл"
MSG_NO_GUARDS = "Охрана караванов не настроена — налёт невозможен"
MSG_GATE_REQUIRED = "Нужен боевой пост с этим караваном, чтобы напасть"      # same text as battle-service B1
MSG_GUARD_SPAWN_FAILED = "Не удалось собрать охрану каравана"
MSG_UNDER_ATTACK = "На караван уже напали"
MSG_CHARACTER_NOT_FOUND = "Персонаж не найден"
MSG_NPC = "НПС не может нападать на караваны"
MSG_REPELLED = "Охрана каравана отбилась"
MSG_ESCORT_FALLEN = "Охрана каравана разбита — вы выбыли из каравана"
MSG_ESCORT_FALLEN_REPELLED = "Вы пали в бою за караван — вы выбыли из каравана, оплаты не будет"
MSG_ESCORT_REPELLED = "Налёт отбит! Надбавка будет выплачена по прибытии"
MSG_ESCORT_EXPIRED = "Бой за караван затянулся — караван ушёл дальше без вас"


def now_utc() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _i(value) -> int:
    return int(value or 0)


def _for_update(db: Session) -> bool:
    return core.supports_for_update(db.get_bind().dialect.name)


def _ids(value) -> List[int]:
    out: List[int] = []
    for x in caravan_crud._json_list(value):
        try:
            cid = int(x)
        except (TypeError, ValueError):
            continue
        if cid not in out:
            out.append(cid)
    return out


def _params(db: Session):
    import econ_tick                                    # late: econ_tick imports most of the service
    return econ_tick.load_params(db)


def _lock_raid(db: Session, raid_id: int) -> Optional["models.EconCaravanRaid"]:
    q = db.query(models.EconCaravanRaid).filter(models.EconCaravanRaid.id == int(raid_id))
    return (q.with_for_update() if _for_update(db) else q).populate_existing().first()


def _group_name(db: Session, code: str) -> Optional[str]:
    return db.execute(text("SELECT name FROM econ_goods_groups WHERE code = :c"), {"c": code}).scalar()


def guard_pool_ids(db: Session) -> List[Tuple[int, int]]:
    """``[(mob_template_id, level)]`` of the admin guard pool."""
    return [(int(r[0]), _i(r[1])) for r in db.execute(text(
        "SELECT t.id, t.level FROM econ_caravan_guard_templates g JOIN mob_templates t ON t.id = g.mob_template_id "
        "ORDER BY t.id")).fetchall()]


def pick_guard_template(pool: Sequence[Tuple[int, int]], recommended_level: Optional[int]) -> Optional[int]:
    """The template whose level is closest to the location's recommended level (ties → lower id)."""
    if not pool:
        return None
    target = _i(recommended_level)
    return min(pool, key=lambda p: (abs(int(p[1]) - target), int(p[0])))[0]


# =====================================================================================================================
# A1: caravans in the character's location
# =====================================================================================================================

def _character(db: Session, character_id: int):
    return db.execute(text("SELECT id, is_npc, current_location_id FROM characters WHERE id = :c"),
                      {"c": int(character_id)}).first()


def caravans_here(db: Session, character_id: int, now: Optional[datetime] = None) -> dict:
    """A1. The location is the character's own (no location parameter → no remote scanning). Only physical caravans
    on the road that have not arrived; never from / to / route / value."""
    now = now or now_utc()
    char = _character(db, character_id)
    if char is None:
        raise EconomyApiError(404, MSG_CHARACTER_NOT_FOUND)
    location_id = int(char[2]) if char[2] is not None else None
    if location_id is None or not caravan_crud.caravans_available(db):
        return {"location_id": location_id, "caravans": []}
    rows = (db.query(models.EconCaravan)
            .filter(models.EconCaravan.is_physical.is_(True),
                    models.EconCaravan.status == caravan_crud.STATUS_IN_TRANSIT,
                    models.EconCaravan.arrived_at.is_(None),
                    models.EconCaravan.current_location_id == location_id)
            .order_by(models.EconCaravan.id).all())
    if not rows:
        return {"location_id": location_id, "caravans": []}
    params = _params(db)
    gates_available = caravan_crud.gate_tables_available(db)
    has_pool = bool(guard_pool_ids(db))
    names: Dict[str, Optional[str]] = {}
    out = []
    for row in rows:
        raid = caravan_crud.active_raid_status(db, int(row.id))
        departs = None
        if raid in ACTIVE_STATUSES:
            state, can_attack, reason = STATE_UNDER_ATTACK, False, MSG_UNDER_ATTACK
        elif raid is not None:
            state, can_attack, reason = STATE_RAIDED, False, MSG_ALREADY_RAIDED
        else:
            held = caravan_crud.held_by(db, row, now, params, gates_available)
            state = STATE_HELD if held else STATE_ON_ROAD
            if state == STATE_ON_ROAD and row.next_move_at is not None:
                departs = max(0, int((row.next_move_at - now).total_seconds()))
            can_attack, reason = (True, None) if has_pool else (False, MSG_NO_GUARDS)
        if row.group_code not in names:
            names[row.group_code] = _group_name(db, row.group_code)
        out.append({"id": int(row.id), "group_code": row.group_code,
                    "group_name": names[row.group_code] or row.group_code, "guard_count": _i(row.guard_count),
                    "state": state, "departs_in_sec": departs, "can_attack": can_attack, "reason": reason})
    return {"location_id": location_id, "caravans": out}


# =====================================================================================================================
# A2: raid start (3.6)
# =====================================================================================================================

def has_open_gate(db: Session, character_id: int, location_id: int, caravan_id: int) -> bool:
    """Pre-check of the leader's open ``caravan`` post gate naming this caravan here (battle-service consumes it —
    this only spares a guard spawn when it is missing). True when the locations-service tables are absent."""
    if not caravan_crud.gate_tables_available(db):
        return True
    return db.execute(text(
        "SELECT 1 FROM action_gates WHERE character_id = :c AND location_id = :l AND action_type = :a "
        "AND target_ref = :t AND status = 'open' LIMIT 1"),
        {"c": int(character_id), "l": int(location_id), "a": caravan_crud.GATE_ACTION_CARAVAN,
         "t": int(caravan_id)}).first() is not None


@dataclass(frozen=True)
class RaidStart:
    raid_id: int
    caravan_id: int
    location_id: int
    guard_ids: Tuple[int, ...] = ()
    escort_ids: Tuple[int, ...] = ()                  # FEAT-212: the caravan's active player escorts (asc id)


def begin_raid(db: Session, caravan_id: int, character_id: int, group: bool,
               now: Optional[datetime] = None) -> RaidStart:
    """Tx A (commits): lock the caravan, check, insert the ``starting`` raid row. Raises :class:`EconomyApiError`."""
    now = now or now_utc()
    char = _character(db, character_id)
    if char is None:
        raise EconomyApiError(404, MSG_CHARACTER_NOT_FOUND)
    if bool(char[1]):
        raise EconomyApiError(400, MSG_NPC)
    leader = db.query(models.Character).filter(models.Character.id == int(character_id)).first()
    message = activity_lock.lock_message(activity_lock.lock_for_character(leader)) if leader is not None else None
    if message:                                     # an escort (neutral text) / jailed / unconscious … — spares a spawn
        db.rollback()
        raise EconomyApiError(409, message)
    row = caravan_crud._lock_caravan(db, caravan_id)
    try:
        if row is None or not row.is_physical or row.status != caravan_crud.STATUS_IN_TRANSIT:
            raise EconomyApiError(404, MSG_CARAVAN_NOT_FOUND)
        if char[2] is None or row.current_location_id is None or int(row.current_location_id) != int(char[2]):
            raise EconomyApiError(400, MSG_NOT_HERE)
        if caravan_crud.active_raid_status(db, int(row.id)) is not None:
            raise EconomyApiError(409, MSG_ALREADY_RAIDED)
        if row.arrived_at is not None:
            raise EconomyApiError(409, MSG_ARRIVED)
        if not guard_pool_ids(db):
            raise EconomyApiError(409, MSG_NO_GUARDS)
        location_id = int(row.current_location_id)
        if not has_open_gate(db, character_id, location_id, int(row.id)):
            raise EconomyApiError(403, MSG_GATE_REQUIRED)
        region_id, _country = econ_ledger.resolve_location(db, location_id)
        raid = models.EconCaravanRaid(
            caravan_id=int(row.id), leader_character_id=int(character_id), is_group=bool(group),
            location_id=location_id, region_id=int(region_id) if region_id else None, status=STATUS_STARTING,
            created_at=now)
        db.add(raid)
        db.flush()
        db.commit()
    except IntegrityError:
        db.rollback()
        raise EconomyApiError(409, MSG_ALREADY_RAIDED)
    except Exception:
        db.rollback()
        raise
    return RaidStart(int(raid.id), int(caravan_id), location_id)


def spawn_guards(db: Session, raid_id: int, params=None) -> RaidStart:
    """Spawn the guards of a ``starting`` raid (``crud.spawn_mob_from_template`` commits per mob) and store them on
    the raid. On any failure the spawned guards are removed, the raid row deleted and a 500 raised."""
    import crud                                          # late: crud imports half of the service
    raid = db.get(models.EconCaravanRaid, int(raid_id))
    if raid is None:
        raise EconomyApiError(500, MSG_GUARD_SPAWN_FAILED)
    caravan = db.get(models.EconCaravan, int(raid.caravan_id))
    params = params or _params(db)
    loc = db.execute(text("SELECT recommended_level, marker_type FROM Locations WHERE id = :l"),
                     {"l": int(raid.location_id)}).first()
    recommended, marker = (loc[0], loc[1]) if loc is not None else (None, None)
    template_id = pick_guard_template(guard_pool_ids(db), recommended)
    value = _i(caravan.value) if caravan is not None else 0
    count = _i(caravan.guard_count) if caravan is not None else 0
    if count <= 0:
        count = econ_caravan.guard_count(value, params)
    escorts = active_escort_ids(db, int(raid.caravan_id))[:MAX_GUARDS - 1]
    count = max(1, min(count, MAX_GUARDS - len(escorts)))
    mult = econ_caravan.guard_multiplier(value, marker, params)
    location_id, caravan_id = int(raid.location_id), int(raid.caravan_id)
    db.rollback()
    spawned: List[int] = []
    try:
        if template_id is None:
            raise EconomyApiError(409, MSG_NO_GUARDS)
        for _ in range(count):
            _mob, character = crud.spawn_mob_from_template(db, template_id, location_id, SPAWN_TYPE,
                                                           stat_multiplier=mult)
            spawned.append(int(character.id))
        db.execute(text(
            "UPDATE econ_caravan_raids SET guard_ids = :g, guard_template_id = :t, guard_mult = :m WHERE id = :id"),
            {"g": _json(spawned), "t": int(template_id), "m": Decimal(str(mult)), "id": int(raid_id)})
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("caravan raid %s: guard spawn failed (%s)", raid_id, type(exc).__name__, exc_info=True)
        _cleanup(db, raid_id, spawned)
        if isinstance(exc, EconomyApiError):
            raise
        raise EconomyApiError(500, MSG_GUARD_SPAWN_FAILED)
    return RaidStart(int(raid_id), caravan_id, location_id, tuple(spawned), tuple(escorts))


def active_escort_ids(db: Session, caravan_id: int) -> List[int]:
    """Character ids of the caravan's active player escorts, ascending (FEAT-212 §3.9)."""
    return [int(r[0]) for r in db.execute(text(
        "SELECT character_id FROM econ_caravan_escorts WHERE caravan_id = :c AND status = :s ORDER BY character_id"),
        {"c": int(caravan_id), "s": escort_crud.STATUS_ACTIVE}).fetchall()]


def _json(ids: Sequence[int]) -> str:
    import json
    return json.dumps([int(i) for i in ids])


def _cleanup(db: Session, raid_id: int, guard_ids: Sequence[int]) -> None:
    """Remove the guards and the ``starting`` raid row (best effort, own commits)."""
    import crud
    try:
        if guard_ids:
            crud.despawn_dungeon_mobs(db, list(guard_ids))
    except Exception:
        db.rollback()
        logger.exception("caravan raid %s: guards %s not despawned", raid_id, list(guard_ids))
    try:
        db.execute(text("DELETE FROM econ_caravan_raids WHERE id = :id AND status = :s"),
                   {"id": int(raid_id), "s": STATUS_STARTING})
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("caravan raid %s: raid row not deleted (the pass removes it)", raid_id)


def abandon_start(db: Session, start: RaidStart) -> None:
    """The battle could not be created: no leftovers (guards despawned, raid row deleted)."""
    _cleanup(db, start.raid_id, start.guard_ids)


def mark_fighting(db: Session, raid_id: int, battle_id: int, attacker_ids: Sequence[int],
                  now: Optional[datetime] = None, *, escort_ids: Sequence[int] = ()) -> bool:
    """Tx B (commits): ``starting`` → ``fighting`` with the battle, the attackers and the escorts battle-service placed
    on the guard team (``escort_ids`` + ``in_raid = 1`` on their active rows). False when the row already moved on (a
    very fast callback settled it — the settlement then read the escorts from the battle's guard team)."""
    now = now or now_utc()
    escorts = sorted({int(e) for e in escort_ids or ()})
    result = db.execute(text(
        "UPDATE econ_caravan_raids SET status = :f, battle_id = :b, attacker_ids = :a, escort_ids = :e, "
        "started_at = :now WHERE id = :id AND status = :s"),
        {"f": STATUS_FIGHTING, "b": int(battle_id), "a": _json(attacker_ids), "e": _json(escorts), "now": now,
         "id": int(raid_id), "s": STATUS_STARTING})
    if (result.rowcount or 0) != 1:
        db.execute(text("UPDATE econ_caravan_raids SET attacker_ids = :a WHERE id = :id AND attacker_ids IS NULL"),
                   {"a": _json(attacker_ids), "id": int(raid_id)})
        db.execute(text("UPDATE econ_caravan_raids SET escort_ids = :e WHERE id = :id AND escort_ids IS NULL"),
                   {"e": _json(escorts), "id": int(raid_id)})
        db.commit()
        return False
    if escorts:
        caravan_id = db.execute(text("SELECT caravan_id FROM econ_caravan_raids WHERE id = :id"),
                                {"id": int(raid_id)}).scalar()
        ph, params = core.in_params("c", escorts)
        db.execute(text(f"UPDATE econ_caravan_escorts SET in_raid = 1 WHERE caravan_id = :car AND status = :s "
                        f"AND character_id IN ({ph})"),
                   {**params, "car": int(caravan_id), "s": escort_crud.STATUS_ACTIVE})
    db.commit()
    return True


# =====================================================================================================================
# A3 / poll: settlement (3.8)
# =====================================================================================================================

@dataclass
class SettleResult:
    status: str                                       # won | repelled | aborted | expired | already | unknown
    raid_id: Optional[int] = None
    notices: List[law_notify.Notice] = field(default_factory=list)


def _attackers(db: Session, raid: "models.EconCaravanRaid") -> List[int]:
    """The raid's attackers: stored by Tx B, else the battle's team 0, else the leader."""
    ids = _ids(raid.attacker_ids)
    if not ids and raid.battle_id:
        try:
            with db.begin_nested():
                ids = [int(r[0]) for r in db.execute(text(
                    "SELECT character_id FROM battle_participants WHERE battle_id = :b AND team = :t ORDER BY id"),
                    {"b": int(raid.battle_id), "t": RAIDER_TEAM}).fetchall()]
        except DBAPIError:
            logger.warning("caravan raid %s: battle participants unreadable — the leader takes it all", raid.id)
            ids = []
    return ids or [int(raid.leader_character_id)]


def _tagged_battle(db: Session, raid_id: int) -> Optional[int]:
    """The battle-service battle tagged with this raid (shared DB), None when there is none / no column yet."""
    try:
        with db.begin_nested():
            value = db.execute(text("SELECT id FROM battles WHERE caravan_raid_id = :r ORDER BY id LIMIT 1"),
                               {"r": int(raid_id)}).scalar()
    except DBAPIError:
        return None
    return int(value) if value is not None else None


def _players(db: Session, ids: Sequence[int]) -> List[int]:
    ids = sorted({int(i) for i in ids})
    if not ids:
        return []
    ph, params = core.in_params("c", ids)
    return [int(r[0]) for r in db.execute(text(
        f"SELECT id FROM characters WHERE id IN ({ph}) AND is_npc = 0 ORDER BY id"), params).fetchall()]


def _missing_bale_columns(exc: Exception) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return ("is_stolen" in message or "bale_group" in message) and (
        "unknown column" in message or "no such column" in message)


def bale_item(db: Session, group_code: str) -> Optional[Tuple[int, str, Decimal]]:
    """``(item_id, name, price)`` of the stolen bale of a goods group (inventory-service 037); None when missing."""
    try:
        with db.begin_nested():
            row = db.execute(text(
                "SELECT id, name, price FROM items WHERE is_stolen = 1 AND bale_group = :g ORDER BY id LIMIT 1"),
                {"g": group_code}).first()
    except DBAPIError as exc:
        if _missing_bale_columns(exc):
            logger.warning("items.is_stolen / bale_group missing (inventory migration 037 not applied?) — no bales")
            return None
        raise
    if row is None:
        return None
    return int(row[0]), row[1], Decimal(str(row[2] or 0))


def _lock_characters(db: Session, ids: Sequence[int]) -> None:
    ids = sorted({int(i) for i in ids})
    if not ids:
        return
    ph, params = core.in_params("c", ids)
    db.execute(text(f"SELECT id FROM characters WHERE id IN ({ph}) ORDER BY id"
                    + (" FOR UPDATE" if _for_update(db) else "")), params).fetchall()


def _raid_message(group_name: Optional[str], marks: int, bales: int, bale_name: Optional[str]) -> str:
    loot = f"{marks} марок"
    if bales > 0:
        loot += f" и {bales} тюков «{bale_name}»" if bale_name else f" и {bales} тюков"
    return f"Налёт на караван ({group_name or 'товары'}): добыча {loot}"


def _raid_escorts(db: Session, raid: "models.EconCaravanRaid") -> List[int]:
    """The escorts placed in the raid battle: stored by Tx B, else (a callback faster than Tx B / a raid re-attached
    by the pass) the battle's guard-team players that still escort this caravan; ``[]`` when unreadable."""
    if raid.escort_ids is not None:
        return _ids(raid.escort_ids)
    if not raid.battle_id:
        return []
    try:
        with db.begin_nested():
            return [int(r[0]) for r in db.execute(text(
                "SELECT DISTINCT bp.character_id FROM battle_participants bp JOIN econ_caravan_escorts e "
                "ON e.character_id = bp.character_id WHERE bp.battle_id = :b AND bp.team = :t "
                "AND e.caravan_id = :c AND e.status = :s ORDER BY bp.character_id"),
                {"b": int(raid.battle_id), "t": GUARD_TEAM, "c": int(raid.caravan_id),
                 "s": escort_crud.STATUS_ACTIVE}).fetchall()]
    except DBAPIError:
        logger.warning("caravan raid %s: battle participants unreadable — escorts left in the caravan", raid.id)
        return []


@dataclass
class EscortPlan:
    """What the settlement does with the raid's escorts (FEAT-212 §3.9)."""
    out_rows: List["models.EconCaravanEscort"] = field(default_factory=list)   # fall out / released
    out_status: Optional[str] = None
    out_message: Optional[str] = None
    survivors: List["models.EconCaravanEscort"] = field(default_factory=list)  # repelled: stay, bonus on arrival

    @property
    def out_ids(self) -> List[int]:
        return [int(r.character_id) for r in self.out_rows]


def _escort_plan(db: Session, raid: "models.EconCaravanRaid", caravan: Optional["models.EconCaravan"], status: str,
                 fallen_character_ids: Optional[Sequence[int]]) -> EscortPlan:
    """Lock the active escort rows (asc id; after the raid row) of the escorts placed in the battle and decide:
    ``won`` → all fall out; ``repelled`` → those in ``fallen_character_ids`` fall out (missing field → none), the
    rest stay; ``expired`` → all released; ``aborted`` → all stay."""
    if caravan is None or status == STATUS_ABORTED:
        return EscortPlan()
    placed = set(_raid_escorts(db, raid))
    if not placed:
        return EscortPlan()
    if raid.escort_ids is None:
        raid.escort_ids = sorted(placed)
    rows = [r for r in escort_crud._active_rows_locked(db, int(caravan.id)) if int(r.character_id) in placed]
    for row in rows:
        row.in_raid = True                       # Tx B may have been lost; the rewards step reads it
    if status == STATUS_WON:
        return EscortPlan(rows, escort_crud.STATUS_FALLEN, MSG_ESCORT_FALLEN)
    if status == STATUS_EXPIRED:
        return EscortPlan(rows, escort_crud.STATUS_RELEASED, MSG_ESCORT_EXPIRED)
    fallen = {int(c) for c in fallen_character_ids or ()}
    return EscortPlan([r for r in rows if int(r.character_id) in fallen], escort_crud.STATUS_FALLEN,
                      MSG_ESCORT_FALLEN_REPELLED, [r for r in rows if int(r.character_id) not in fallen])


def _apply_escort_plan(db: Session, caravan: "models.EconCaravan", plan: EscortPlan,
                       now: datetime) -> List[law_notify.Notice]:
    """Rows → fallen / released, columns cleared (the character stays at the raid location; no knockout, no pay),
    CharacterLog; notices for them and for the repelled survivors. The characters are already locked."""
    ids = plan.out_ids + [int(r.character_id) for r in plan.survivors]
    if not ids:
        return []
    users = law_crud.character_user_ids(db, ids)
    notices = []
    for row in plan.out_rows:
        row.status = plan.out_status
        row.ended_at = now
        escort_crud._log(db, row.character_id, plan.out_message, caravan.id, status=plan.out_status)
        notices.append(escort_crud._notice(users.get(int(row.character_id)), plan.out_message, row.character_id,
                                           caravan.id, status=plan.out_status))
    escort_crud._clear_columns(db, caravan.id, plan.out_ids)
    for row in plan.survivors:
        notices.append(escort_crud._notice(users.get(int(row.character_id)), MSG_ESCORT_REPELLED, row.character_id,
                                           caravan.id, status=STATUS_REPELLED))
    return notices


def settle_raid(db: Session, raid_id: int, *, battle_id: Optional[int], winner_team: Optional[int], aborted: bool,
                now: Optional[datetime] = None, expire: bool = False, params=None,
                rng: Callable[[], float] = random.random,
                fallen_character_ids: Optional[Sequence[int]] = None) -> SettleResult:
    """Tx 1 (economy; commits). Idempotent: a raid that is no longer ``starting`` / ``fighting`` → ``already``.
    ``expire`` = the battle ran longer than ``caravan_raid_battle_max_hours`` (no loot). ``fallen_character_ids`` =
    the battle's knocked-out / dropped participants (FEAT-212; an old battle-service sends none → on a repelled raid
    every escort stays). Notices are returned (publish after this call)."""
    now = now or now_utc()
    probe = db.execute(text("SELECT caravan_id FROM econ_caravan_raids WHERE id = :id"), {"id": int(raid_id)}).first()
    if probe is None:
        db.rollback()
        return SettleResult(RESULT_UNKNOWN)
    params = params or _params(db)
    try:
        caravan = caravan_crud._lock_caravan(db, int(probe[0]))
        raid = _lock_raid(db, raid_id)
        if raid is None:
            db.rollback()
            return SettleResult(RESULT_UNKNOWN)
        if raid.status not in ACTIVE_STATUSES:
            db.rollback()
            return SettleResult(RESULT_ALREADY, int(raid.id))
        if battle_id is not None and raid.battle_id is not None and int(raid.battle_id) != int(battle_id):
            logger.warning("caravan raid %s: result of battle %s ignored (raid battle %s)", raid_id, battle_id,
                           raid.battle_id)
            db.rollback()
            return SettleResult(RESULT_ALREADY, int(raid.id))
        if raid.battle_id is None and battle_id is not None:
            raid.battle_id = int(battle_id)

        if expire:
            status = STATUS_EXPIRED
        elif aborted:
            status = STATUS_ABORTED
        elif winner_team is not None and int(winner_team) == RAIDER_TEAM:
            status = STATUS_WON
        else:
            status = STATUS_REPELLED

        attackers = _attackers(db, raid)
        players = _players(db, attackers)
        escorts = _escort_plan(db, raid, caravan, status, fallen_character_ids)    # escort rows locked here
        notices: List[law_notify.Notice] = []
        group_name = _group_name(db, caravan.group_code) if caravan is not None else None
        if status == STATUS_WON and caravan is not None and players:
            notices = _pay_out(db, raid, caravan, attackers, players, group_name, params, now,
                               lock_also=escorts.out_ids)
        else:
            _lock_characters(db, escorts.out_ids)                                 # the one character lock of Tx 1
            if status == STATUS_REPELLED:
                user_ids = law_crud.character_user_ids(db, players)
                notices = [law_notify.Notice(user_ids.get(cid), MSG_REPELLED, WS_CARAVAN_RAID,
                                             law_notify.CATEGORY_PROGRESS,
                                             {"character_id": cid, "raid_id": int(raid.id)})
                           for cid in players]
        if caravan is not None:
            notices = notices + _apply_escort_plan(db, caravan, escorts, now)
        if raid.attacker_ids is None:
            raid.attacker_ids = attackers
        raid.status = status
        raid.finished_at = now
        if (caravan is not None and caravan.status == caravan_crud.STATUS_IN_TRANSIT
                and caravan.arrived_at is None):
            caravan.next_move_at = now + caravan_crud.step_delay(params, rng())
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise
    logger.info("caravan raid %s settled: %s (battle %s, attackers %s, escorts out %s, stay %s)", raid_id, status,
                battle_id, attackers, escorts.out_ids, [int(r.character_id) for r in escorts.survivors])
    return SettleResult(status, int(raid_id), notices)


def _pay_out(db: Session, raid: "models.EconCaravanRaid", caravan: "models.EconCaravan", attackers: Sequence[int],
             players: Sequence[int], group_name: Optional[str], params, now: datetime,
             lock_also: Sequence[int] = ()) -> List[law_notify.Notice]:
    """The loot of a won raid (inside Tx 1): stolen units / bales, escrow marks via the ledger, shares, logs.
    ``lock_also`` = the escorts falling out — locked in the same single sorted character lock as the raiders."""
    left = max(Decimal(0), caravan_crud._dec3(caravan.units) - caravan_crud._dec3(caravan.stolen_units))
    stolen_units, stolen_value = econ_caravan.stolen(left, caravan.unit_price, params.caravan_raid_goods_share)
    paid_total = _i(caravan.paid_purse) + _i(caravan.paid_treasury)
    marks = int((Decimal(paid_total) * Decimal(str(params.caravan_raid_marks_share or 0)))
                .to_integral_value(rounding=ROUND_FLOOR))
    marks = max(0, min(marks, paid_total - _i(caravan.raid_paid)))
    bale = bale_item(db, caravan.group_code)
    bales = econ_caravan.bale_count(stolen_value, bale[2]) if bale is not None else 0
    split = econ_caravan.split_loot(marks, bales, [a for a in attackers if a in players] or players,
                                    raid.leader_character_id)

    _lock_characters(db, list(players) + list(lock_also))
    escrow_ref = core.AccountRef.caravan_escrow()
    caravan_crud._lock_balances(db, [escrow_ref])
    legs = [core.Leg(escrow_ref, core.AccountRef.character(cid), m) for cid, (m, _b) in split.items() if m > 0]
    op_id = None
    if legs:
        posted = econ_ledger.post_operation(
            db, op_type=core.OP_CARAVAN_RAID, legs=legs, source_service=caravan_crud.SOURCE_SERVICE,
            region_id=int(raid.region_id) if raid.region_id else None, apply_tax=False,
            idempotency_key=caravan_crud.caravan_key(caravan.id, KEY_RAID),
            metadata={"caravan_id": int(caravan.id), "raid_id": int(raid.id),
                      "battle_id": int(raid.battle_id) if raid.battle_id else None,
                      "group_code": caravan.group_code, "stolen_units": str(stolen_units),
                      "stolen_value": int(stolen_value), "bales": int(bales)})
        op_id = posted.operation_id

    caravan.stolen_units = caravan_crud._dec3(caravan_crud._dec3(caravan.stolen_units) + Decimal(str(stolen_units)))
    caravan.raid_paid = _i(caravan.raid_paid) + marks
    raid.marks = marks
    raid.stolen_units = Decimal(str(stolen_units))
    raid.stolen_value = int(stolen_value)
    raid.bales = int(bales)
    raid.payout_op_id = op_id

    bale_id, bale_name = (bale[0], bale[1]) if bale is not None else (None, None)
    user_ids = law_crud.character_user_ids(db, list(split))
    notices = []
    for cid, (m, b) in split.items():
        db.add(models.EconCaravanRaidShare(raid_id=int(raid.id), character_id=int(cid), marks=int(m), bales=int(b),
                                           bale_item_id=bale_id if b > 0 else None))
        message = _raid_message(group_name, m, b, bale_name)
        db.add(models.CharacterLog(character_id=int(cid), event_type=LOG_EVENT_TYPE, description=message,
                                   metadata_={"raid_id": int(raid.id), "caravan_id": int(caravan.id),
                                              "marks": int(m), "bales": int(b), "bale_item_id": bale_id}))
        loot = f"{m} марок" + (f" и {b} тюков «{bale_name}»" if b > 0 and bale_name else "")
        notices.append(law_notify.Notice(user_ids.get(cid), f"Налёт удался: {loot}", WS_CARAVAN_RAID,
                                         law_notify.CATEGORY_PROGRESS,
                                         {"character_id": int(cid), "raid_id": int(raid.id)}))
    return notices


# =====================================================================================================================
# Player: own share of a raid by its battle (the battle victory window)
# =====================================================================================================================

SHARE_PENDING = "pending"           # the fight ended but the settlement has not run yet (the client asks again)


def raid_share_by_battle(db: Session, battle_id: int, character_id: int) -> dict:
    """The character's loot of the raid fought in ``battle_id``. ``raid = False`` for any battle that is not a raid
    or where the character was not a raider (so the window shows the ordinary PvE rewards only)."""
    none = {"raid": False, "status": None, "marks": 0, "bales": 0, "bale_name": None}
    row = db.execute(text(
        "SELECT id, status, attacker_ids FROM econ_caravan_raids WHERE battle_id = :b ORDER BY id DESC LIMIT 1"),
        {"b": int(battle_id)}).first()
    if row is None or int(character_id) not in _ids(row[2]):
        return none
    status = row[1]
    if status in ACTIVE_STATUSES:
        return {**none, "raid": True, "status": SHARE_PENDING}
    out = {**none, "raid": True, "status": status}
    if status != STATUS_WON:
        return out
    share = db.execute(text(
        "SELECT s.marks, s.bales, i.name FROM econ_caravan_raid_shares s LEFT JOIN items i ON i.id = s.bale_item_id "
        "WHERE s.raid_id = :r AND s.character_id = :c"), {"r": int(row[0]), "c": int(character_id)}).first()
    if share is not None:
        out.update(marks=int(share[0] or 0), bales=int(share[1] or 0), bale_name=share[2])
    return out


# =====================================================================================================================
# After the settlement: law (Tx 2), bales, guards
# =====================================================================================================================

def law_step(db: Session, raid_id: int, now: Optional[datetime] = None, params=None):
    """Tx 2 for a ``won`` raid (commits). Claims ``law_done`` first (a concurrent second run finds it set). Returns
    the ``shadow_crud.KillOutcome`` to publish, or None when there was nothing to do."""
    import shadow_crud
    now = now or now_utc()
    try:
        claimed = db.execute(text(
            "UPDATE econ_caravan_raids SET law_done = 1 WHERE id = :id AND status = :s AND law_done = 0"),
            {"id": int(raid_id), "s": STATUS_WON})
        if (claimed.rowcount or 0) != 1:
            db.rollback()
            return None
        raid = db.get(models.EconCaravanRaid, int(raid_id))
        caravan = db.get(models.EconCaravan, int(raid.caravan_id))
        if caravan is None:
            db.commit()
            return None
        params = params or _params(db)
        players = [int(r[0]) for r in db.execute(text(
            "SELECT character_id FROM econ_caravan_raid_shares WHERE raid_id = :r ORDER BY character_id"),
            {"r": int(raid_id)}).fetchall()]
        outcome = shadow_crud.caravan_raid_consequences(
            db, raid, caravan, players, trade_share=params.caravan_rep_trade_share, now=now)
        db.commit()
        return outcome
    except Exception:
        db.rollback()
        raise


def raid_faction_key(raid_id: int, character_id: int) -> str:
    return f"faction:caravan_raid:r{int(raid_id)}:{int(character_id)}"


def raid_faction_points(db: Session, raid_id: int, now: Optional[datetime] = None) -> int:
    """FEAT-212 §3.10: faction points «Налёты на караваны» for the players of a ``won`` raid's shares, once per raid
    (``faction_done``). ``faction_kills.apply_caravan_deed`` runs its own transactions (nothing may be open) and is
    idempotent per faction (event key), so the claim is set after the deeds — a crash in between only repeats no-ops.
    Publishes the notices. Returns the number of faction deeds applied."""
    import faction_core as fc
    import faction_kills
    import faction_notify
    now = now or now_utc()
    row = db.execute(text("SELECT status, faction_done FROM econ_caravan_raids WHERE id = :id"),
                     {"id": int(raid_id)}).first()
    players = [int(r[0]) for r in db.execute(text(
        "SELECT character_id FROM econ_caravan_raid_shares WHERE raid_id = :r ORDER BY character_id"),
        {"r": int(raid_id)}).fetchall()]
    db.rollback()
    if row is None or row[0] != STATUS_WON or bool(row[1]):
        return 0
    applied = 0
    notices = []
    for cid in players:
        result = faction_kills.apply_caravan_deed(db, cid, fc.ENEMY_RAID, raid_faction_key(raid_id, cid), now)
        notices.extend(result.notices)
        applied += len(result.data.get("applied") or [])
    try:
        db.execute(text("UPDATE econ_caravan_raids SET faction_done = 1 WHERE id = :id AND status = :s "
                        "AND faction_done = 0"), {"id": int(raid_id), "s": STATUS_WON})
        db.commit()
    except Exception:
        db.rollback()
        raise
    faction_notify.publish(notices)
    return applied


def _inventory_url(character_id: int) -> str:
    return f"{settings.INVENTORY_SERVICE_URL.rstrip('/')}/internal/characters/{int(character_id)}/items"


def http_post(url: str, payload: dict) -> httpx.Response:
    """THE network seam of the bale delivery (tests replace it)."""
    import crud
    return httpx.post(url, json=payload, headers=crud._internal_token_headers(), timeout=HTTP_TIMEOUT_SECONDS)


def deliver_bales(db: Session, raid_id: int, now: Optional[datetime] = None) -> int:
    """Bales of a won raid's shares via inventory-service, each marked after success (commits per share). A transport
    error / 5xx is retried by the pass; a 4xx (bale item or character gone) is logged and marked to stop retrying.
    A crash between the inventory success and the mark can deliver once more (accepted, logged)."""
    now = now or now_utc()
    rows = db.execute(text(
        "SELECT s.id, s.character_id, s.bales, s.bale_item_id FROM econ_caravan_raid_shares s "
        "JOIN econ_caravan_raids r ON r.id = s.raid_id WHERE s.raid_id = :r AND r.status = :won AND s.bales > 0 "
        "AND s.bale_item_id IS NOT NULL AND s.bales_delivered_at IS NULL ORDER BY s.id"),
        {"r": int(raid_id), "won": STATUS_WON}).fetchall()
    db.rollback()                                         # nothing open while the HTTP calls run
    delivered = 0
    for share_id, character_id, bales, item_id in rows:
        try:
            response = http_post(_inventory_url(character_id), {"item_id": int(item_id), "quantity": int(bales)})
        except httpx.HTTPError as exc:
            logger.warning("caravan raid %s: bales of share %s not delivered (%s), retried", raid_id, share_id,
                           type(exc).__name__)
            continue
        if response.status_code >= 500:
            logger.warning("caravan raid %s: bales of share %s refused (%s), retried", raid_id, share_id,
                           response.status_code)
            continue
        if response.status_code >= 400:
            logger.error("caravan raid %s: bales of share %s (character %s, item %s x%s) refused for good: %s %s",
                         raid_id, share_id, character_id, item_id, bales, response.status_code, response.text[:200])
        try:
            db.execute(text("UPDATE econ_caravan_raid_shares SET bales_delivered_at = :now WHERE id = :id "
                            "AND bales_delivered_at IS NULL"), {"now": now, "id": int(share_id)})
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("caravan raid %s: share %s delivered but not marked — may be delivered again",
                             raid_id, share_id)
            continue
        if response.status_code < 400:
            delivered += 1
    return delivered


def despawn_guards(db: Session, raid_id: int) -> bool:
    """Remove the guards of a finished raid (idempotent; commits). True when the raid is now marked despawned."""
    import crud
    raid = db.get(models.EconCaravanRaid, int(raid_id))
    if raid is None or raid.status not in FINAL_STATUSES or raid.guards_despawned:
        db.rollback()
        return False
    guard_ids = _ids(raid.guard_ids)
    db.rollback()
    if guard_ids:
        crud.despawn_dungeon_mobs(db, guard_ids)
    db.execute(text("UPDATE econ_caravan_raids SET guards_despawned = 1 WHERE id = :id"), {"id": int(raid_id)})
    db.commit()
    return True


def publish(notices) -> None:
    if notices:
        law_notify.publish(notices)


def finish_raid(db: Session, raid_id: int, now: Optional[datetime] = None, params=None) -> None:
    """Everything after the settlement for one raid (each step best effort): law + publish, bales, guards."""
    now = now or now_utc()
    try:
        outcome = law_step(db, raid_id, now, params)
        if outcome is not None:
            outcome.publish()
    except Exception:
        db.rollback()
        logger.exception("caravan raid %s: law step failed, retried by the caravan pass", raid_id)
    try:
        raid_faction_points(db, raid_id, now)
    except Exception:
        db.rollback()
        logger.exception("caravan raid %s: faction points failed, retried by the caravan pass", raid_id)
    try:
        deliver_bales(db, raid_id, now)
    except Exception:
        db.rollback()
        logger.exception("caravan raid %s: bale delivery failed, retried by the caravan pass", raid_id)
    try:
        despawn_guards(db, raid_id)
    except Exception:
        db.rollback()
        logger.exception("caravan raid %s: guards not despawned, retried by the caravan pass", raid_id)


def battle_result(db: Session, *, battle_id: int, raid_id: int, winner_team: Optional[int], aborted: bool,
                  now: Optional[datetime] = None, fallen_character_ids: Optional[Sequence[int]] = None) -> str:
    """A3 (battle-service callback): settle, publish, then law / faction points / bales / guards. Returns the A3
    status."""
    now = now or now_utc()
    result = settle_raid(db, raid_id, battle_id=battle_id, winner_team=winner_team, aborted=aborted, now=now,
                         fallen_character_ids=fallen_character_ids)
    publish(result.notices)
    if result.status in FINAL_STATUSES or result.status == RESULT_ALREADY:
        finish_raid(db, raid_id, now)          # a late callback of an expired raid only despawns the guards
    return result.status


# =====================================================================================================================
# caravan pass hooks (3.3 steps 1–3): fn(factory, now, params) -> int
# =====================================================================================================================

def _select_ids(factory: SessionFactory, sql: str, params: dict) -> List[int]:
    db = factory()
    try:
        return [int(r[0]) for r in db.execute(text(sql), {**params, "n": BATCH_SIZE}).fetchall()]
    finally:
        db.rollback()
        db.close()


def expire_stale_raids(factory: SessionFactory, now: datetime, params) -> int:
    """Step 1: ``starting`` raids older than 10 min with no battle → guards despawned, raid row deleted (the caravan
    may be raided again; a late callback for the deleted raid answers ``unknown``)."""
    ids = _select_ids(factory, "SELECT id FROM econ_caravan_raids WHERE status = :s AND battle_id IS NULL "
                               "AND created_at <= :cut ORDER BY id LIMIT :n",
                      {"s": STATUS_STARTING, "cut": now - STALE_STARTING_AFTER})
    done = 0
    for raid_id in ids:
        db = factory()
        try:
            raid = _lock_raid(db, raid_id)
            if raid is None or raid.status != STATUS_STARTING or raid.battle_id is not None:
                db.rollback()
                continue
            battle_id = _tagged_battle(db, raid_id)
            if battle_id is not None:                     # the fight exists, only Tx B was lost: keep the raid
                raid.status, raid.battle_id, raid.started_at = STATUS_FIGHTING, battle_id, raid.created_at
                db.commit()
                logger.warning("caravan raid %s: Tx B was lost — attached to battle %s", raid_id, battle_id)
                continue
            guard_ids = _ids(raid.guard_ids)
            db.execute(text("DELETE FROM econ_caravan_raids WHERE id = :id AND status = :s AND battle_id IS NULL"),
                       {"id": int(raid_id), "s": STATUS_STARTING})
            db.commit()
            if guard_ids:
                import crud
                crud.despawn_dungeon_mobs(db, guard_ids)
            done += 1
            logger.warning("caravan raid %s: stuck in starting — removed (guards %s)", raid_id, guard_ids)
        except Exception:
            db.rollback()
            logger.exception("caravan pass: stale raid %s not removed", raid_id)
        finally:
            db.close()
    return done


def _fallen(value) -> Optional[List[int]]:
    """``fallen_character_ids`` of a battle-service answer; None when an old battle-service sent no such field."""
    if value is None:
        return None
    out = []
    for x in value if isinstance(value, (list, tuple)) else ():
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def poll_raid_battles(factory: SessionFactory, now: datetime, params) -> int:
    """Step 2: ``fighting`` raids started > 2 min ago — poll battle-service (lost callbacks); a 404 battle = aborted;
    still running past ``caravan_raid_battle_max_hours`` → ``expired`` (no loot, caravan released)."""
    import battle_client
    ids = _select_ids(factory, "SELECT id FROM econ_caravan_raids WHERE status = :s AND started_at <= :cut "
                               "ORDER BY id LIMIT :n", {"s": STATUS_FIGHTING, "cut": now - POLL_AFTER})
    max_age = timedelta(hours=int(params.caravan_raid_battle_max_hours))
    done = 0
    for raid_id in ids:
        db = factory()
        try:
            raid = db.get(models.EconCaravanRaid, int(raid_id))
            if raid is None or raid.status != STATUS_FIGHTING:
                continue
            battle_id, started_at = raid.battle_id, raid.started_at
            db.rollback()
            kwargs = None
            if not battle_id:
                kwargs = dict(battle_id=None, winner_team=None, aborted=True)
            else:
                try:
                    result = battle_client.get_battle_result(int(battle_id))
                except battle_client.BattleServiceError as exc:
                    logger.warning("caravan pass: battle %s of raid %s not polled: %s", battle_id, raid_id, exc)
                    result = None
                if result == battle_client.BATTLE_NOT_FOUND:
                    kwargs = dict(battle_id=int(battle_id), winner_team=None, aborted=True)
                elif isinstance(result, dict) and result.get("status") in FINISHED_BATTLE_STATUSES:
                    kwargs = dict(battle_id=int(battle_id), winner_team=result.get("winner_team"),
                                  aborted=bool(result.get("aborted")),
                                  fallen_character_ids=_fallen(result.get("fallen_character_ids")))
            if kwargs is None and started_at is not None and started_at + max_age <= now:
                kwargs = dict(battle_id=int(battle_id) if battle_id else None, winner_team=None, aborted=False,
                              expire=True)
            if kwargs is None:
                continue
            outcome = settle_raid(db, raid_id, now=now, params=params, **kwargs)
            publish(outcome.notices)
            if outcome.status in FINAL_STATUSES:
                done += 1
        except Exception:
            db.rollback()
            logger.exception("caravan pass: raid %s not polled", raid_id)
        finally:
            db.close()
    return done


def raid_followups(factory: SessionFactory, now: datetime, params) -> int:
    """Step 3: won raids without the law step / without the faction points (FEAT-212), undelivered bales (of raids
    finished > 1 min ago — fresh ones are the callback's), finished raids with guards still spawned."""
    done = 0
    for raid_id in _select_ids(factory, "SELECT id FROM econ_caravan_raids WHERE status = :s AND law_done = 0 "
                                        "ORDER BY id LIMIT :n", {"s": STATUS_WON}):
        db = factory()
        try:
            outcome = law_step(db, raid_id, now, params)
            if outcome is not None:
                outcome.publish()
                done += 1
        except Exception:
            db.rollback()
            logger.exception("caravan pass: law step of raid %s failed", raid_id)
        finally:
            db.close()
    for raid_id in _select_ids(factory, "SELECT id FROM econ_caravan_raids WHERE status = :s AND faction_done = 0 "
                                        "ORDER BY id LIMIT :n", {"s": STATUS_WON}):
        db = factory()
        try:
            done += raid_faction_points(db, raid_id, now)
        except Exception:
            db.rollback()
            logger.exception("caravan pass: faction points of raid %s failed", raid_id)
        finally:
            db.close()
    for raid_id in _select_ids(factory, "SELECT DISTINCT r.id FROM econ_caravan_raids r JOIN econ_caravan_raid_shares s "
                                        "ON s.raid_id = r.id WHERE r.status = :s AND r.finished_at <= :cut "
                                        "AND s.bales > 0 AND s.bale_item_id IS NOT NULL "
                                        "AND s.bales_delivered_at IS NULL ORDER BY r.id LIMIT :n",
                               {"s": STATUS_WON, "cut": now - BALE_RETRY_AFTER}):
        db = factory()
        try:
            done += deliver_bales(db, raid_id, now)
        except Exception:
            db.rollback()
            logger.exception("caravan pass: bales of raid %s failed", raid_id)
        finally:
            db.close()
    final = ", ".join(f":f{i}" for i in range(len(FINAL_STATUSES)))
    for raid_id in _select_ids(factory, f"SELECT id FROM econ_caravan_raids WHERE guards_despawned = 0 "
                                        f"AND status IN ({final}) ORDER BY id LIMIT :n",
                               {f"f{i}": s for i, s in enumerate(FINAL_STATUSES)}):
        db = factory()
        try:
            if despawn_guards(db, raid_id):
                done += 1
        except Exception:
            db.rollback()
            logger.exception("caravan pass: guards of raid %s not despawned", raid_id)
        finally:
            db.close()
    return done
