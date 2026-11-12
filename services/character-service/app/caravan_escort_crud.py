"""FEAT-212 — player escorts of physical caravans (sync SQLAlchemy; features/FEAT-212 §3.7–3.10).

* **hiring** at a «Караванщик» NPC (role ``caravaneer``) standing at the seller's trade gate (C1 view, C2 hire):
  :func:`resolve_caravaneer` (steps 1–3; the API then asks the ``npc_dialogue`` gate and the NPC tier gate),
  :func:`caravaneer_view`, :func:`hire`. A caravan is *preparing* (hireable) while it is physical, in transit, not
  arrived, at ``route_index 0`` and was never raided. Strangers never learn how many escorts ride (PM decision 1:
  only «есть места» / «мест нет»);
* **the job** (C3 :func:`escort_job`, C4 :func:`leave`, the caravan channel C5 :func:`messages` / C6
  :func:`post_message`);
* **stepping** (:func:`move_escorts`, called by ``caravan_pass.step_caravan`` in the caravan's transaction);
* **delivery** (:func:`pay_plan` / :func:`finish_paid` / :func:`cancel_escorts`, called by
  ``economy_caravan_crud.deliver_physical`` inside the ``caravan_delivery`` / ``caravan_cancel`` op transaction);
* **pass steps** 6 :func:`escort_rewards` (reputation in both regions, defense reputation + fame, faction points) and
  7 :func:`escort_housekeeping` (crash safety, old channel messages);
* :func:`release` — a job ended from outside the caravan flow (admin / home teleport, housekeeping).

Lock order (§3.15): ``econ_regions → econ_region_goods → econ_region_events → econ_caravans (asc) →
econ_caravan_raids → econ_caravan_escorts (asc id) → econ_caravan_raid_shares → … → characters (asc id, ONE sorted lock
call per tx) → econ_accounts (asc) → character_attributes``. Reputation / fame / faction rows are written only in the
rewards step's own transactions. Channel messages are plain inserts, never locked. Notices are published by the
caller after the commit.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_FLOOR, Decimal
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

import activity_lock
import econ_caravan
import econ_core as core
import economy_caravan_crud as caravan_crud
import law_notify
import models
from economy_crud import EconomyApiError

logger = logging.getLogger("character-service.caravan_escorts")

SessionFactory = Callable[[], Session]

# econ_caravan_escorts.status
STATUS_ACTIVE = "active"
STATUS_LEFT = "left"            # «Сойти» — no pay, no rejoin
STATUS_FALLEN = "fallen"        # lost in the raid battle
STATUS_DELIVERED = "delivered"  # caravan arrived, paid
STATUS_CANCELLED = "cancelled"  # caravan cancelled, no pay
STATUS_RELEASED = "released"    # pulled out from outside (admin teleport, housekeeping, expired raid)
END_STATUSES = (STATUS_LEFT, STATUS_FALLEN, STATUS_DELIVERED, STATUS_CANCELLED, STATUS_RELEASED)

LOG_EVENT_TYPE = "caravan_escort"
WS_CARAVAN_ESCORT = "caravan_escort"

CARAVANEER_ROLE = "caravaneer"
NPC_DEAD = "dead"
NEUTRAL_TIER = "wanderer"                 # «Скиталец»: reputation must not be below neutral in the seller region
RAID_ACTIVE_STATUSES = ("starting", "fighting")
RAID_REPELLED = "repelled"

# C3 states
STATE_PREPARING = "preparing"
STATE_ON_ROAD = "on_road"
STATE_HELD = "held"
STATE_UNDER_ATTACK = "under_attack"
STATE_ARRIVED = "arrived"

MESSAGE_MAX_LEN = 500
MESSAGES_PAGE = 100
MESSAGE_THROTTLE = timedelta(seconds=3)
MESSAGES_KEEP = timedelta(days=7)         # channel messages are deleted 7 days after the caravan finished
BATCH_SIZE = 200
HOUSEKEEPING_DELETE_BATCH = 1000

MSG_RELEASED = "Вы сняты с охраны каравана"
MSG_CHARACTER_NOT_FOUND = "Персонаж не найден"
MSG_NOT_OWNER = "Вы можете управлять только своими персонажами"
MSG_NOT_PLAYER = "Охрану караванов нанимают только персонажи игроков"
MSG_CARAVANEER_NOT_FOUND = "Караванщик не найден"
MSG_NOT_AT_CARAVANEER = "Вы не у караванщика"
MSG_GATE_CLOSED = "Нужен пост-намерение «Диалог с НПС» с этим персонажем"
MSG_GATE_UNAVAILABLE = "Не удалось проверить обращение к караванщику, попробуйте позже"
MSG_CARAVAN_NOT_FOUND = "Караван не найден"
MSG_CARAVAN_GONE = "Караван уже ушёл"
MSG_WRONG_GATE = "Этот караван собирается не здесь"
MSG_RAIDED = "На этот караван уже напали"
MSG_HIRING_OFF = "Караванщик сейчас не нанимает охрану"
MSG_NO_SEATS = "Мест в охране больше нет"
MSG_ALREADY_ESCORT = "Вы уже в охране каравана"
MSG_NO_REJOIN = "В этот караван вас больше не возьмут"
MSG_IN_BATTLE = "Персонаж в бою"
MSG_GATHERING = "Сначала закончите сбор ресурсов"
MSG_WANTED = "Вас разыскивают в краю, откуда идёт караван — караванщик не возьмёт"
MSG_NOT_ESCORT = "Вы не в охране каравана"
MSG_LEAVE_IN_BATTLE = "Идёт бой — сойти с каравана нельзя"
MSG_TEXT_LENGTH = "Сообщение: от 1 до 500 символов"
MSG_TOO_OFTEN = "Слишком часто — подождите пару секунд"


def now_utc() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _i(value) -> int:
    return int(value or 0)


def _for_update(db: Session) -> bool:
    return core.supports_for_update(db.get_bind().dialect.name)


def _locked(q, db: Session):
    return (q.with_for_update() if _for_update(db) else q).populate_existing()


def _params(db: Session):
    import econ_tick                                    # late: econ_tick imports most of the service
    return econ_tick.load_params(db)


def _group_name(db: Session, code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    return db.execute(text("SELECT name FROM econ_goods_groups WHERE code = :c"), {"c": code}).scalar() or code


def _lock_characters(db: Session, ids: Sequence[int]) -> None:
    ids = sorted({int(i) for i in ids})
    if not ids:
        return
    ph, params = core.in_params("c", ids)
    db.execute(text(f"SELECT id FROM characters WHERE id IN ({ph}) ORDER BY id"
                    + (" FOR UPDATE" if _for_update(db) else "")), params).fetchall()


def _probe(db: Session, sql: str, params: dict) -> bool:
    """A read of another service's table that may be absent (SQLite fixtures): absent → False."""
    try:
        with db.begin_nested():
            return db.execute(text(sql), params).first() is not None
    except DBAPIError:
        return False


def _in_battle(db: Session, character_id: int) -> bool:
    return _probe(db, "SELECT 1 FROM battles b JOIN battle_participants bp ON b.id = bp.battle_id "
                      "WHERE bp.character_id = :c AND b.status IN ('pending', 'in_progress') "
                      "AND bp.dropped_out_at IS NULL LIMIT 1", {"c": int(character_id)})


def _gathering(db: Session, character_id: int) -> bool:
    return _probe(db, "SELECT 1 FROM gathering_sessions WHERE character_id = :c AND status = 'active' LIMIT 1",
                  {"c": int(character_id)})


def _ids(value) -> List[int]:
    out: List[int] = []
    for x in caravan_crud._json_list(value):
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _region_exists(db: Session, region_id: Optional[int]) -> bool:
    if not region_id:
        return False
    return db.execute(text("SELECT 1 FROM Regions WHERE id = :r"), {"r": int(region_id)}).first() is not None


def _notice(user_id, message: str, character_id: int, caravan_id: int, **data) -> law_notify.Notice:
    return law_notify.Notice(user_id, message, WS_CARAVAN_ESCORT, law_notify.CATEGORY_PROGRESS,
                             {"character_id": int(character_id), "caravan_id": int(caravan_id), **data})


def _log(db: Session, character_id: int, message: str, caravan_id: int, **meta) -> None:
    db.add(models.CharacterLog(character_id=int(character_id), event_type=LOG_EVENT_TYPE, description=message,
                               metadata_={"caravan_id": int(caravan_id), **meta}))


# =====================================================================================================================
# release (task 1) — a job ended from outside the caravan flow
# =====================================================================================================================

@dataclass
class ReleaseResult:
    released: bool
    caravan_id: Optional[int] = None
    notice: Optional[law_notify.Notice] = None


def release(db: Session, character_id: int, *, status: str = STATUS_RELEASED, now: Optional[datetime] = None,
            message: str = MSG_RELEASED) -> ReleaseResult:
    """End the character's active escort job without pay (no commit; the caller commits, then publishes
    ``result.notice``). The character stays where he is. Idempotent: no job → ``released=False``; a dangling column
    without an active row is cleared too."""
    if status not in END_STATUSES:
        raise ValueError(f"unknown escort end status: {status}")
    now = now or datetime.utcnow()
    peek = db.query(models.Character.escort_caravan_id).filter(models.Character.id == int(character_id)).first()
    caravan_id = int(peek[0]) if peek is not None and peek[0] else None
    if caravan_id is None:
        return ReleaseResult(False)
    # lock order: caravan → escort row → character
    _locked(db.query(models.EconCaravan).filter(models.EconCaravan.id == caravan_id), db).first()
    row = _locked(db.query(models.EconCaravanEscort).filter(
        models.EconCaravanEscort.caravan_id == caravan_id,
        models.EconCaravanEscort.character_id == int(character_id),
        models.EconCaravanEscort.status == STATUS_ACTIVE), db).first()
    character = _locked(db.query(models.Character).filter(models.Character.id == int(character_id)), db).first()
    if character is None:
        return ReleaseResult(False)
    if character.escort_caravan_id is None or int(character.escort_caravan_id) != caravan_id:
        return ReleaseResult(False)  # changed meanwhile (left / delivered by another tx)
    character.escort_caravan_id = None
    if row is not None:
        row.status = status
        row.ended_at = now
        db.add(models.CharacterLog(character_id=int(character_id), event_type=LOG_EVENT_TYPE, description=message,
                                   metadata_={"caravan_id": caravan_id, "status": status}))
    notice = law_notify.Notice(user_id=character.user_id, message=message, ws_type=WS_CARAVAN_ESCORT,
                               data={"character_id": int(character_id), "caravan_id": caravan_id})
    return ReleaseResult(True, caravan_id, notice)


# =====================================================================================================================
# pay maths (C1 / C3 estimates and the delivery split share one formula)
# =====================================================================================================================

def _floor_share(amount: int, share) -> int:
    return max(0, int((Decimal(max(0, int(amount))) * Decimal(str(share or 0)))
                      .to_integral_value(rounding=ROUND_FLOOR)))


def pools(seller_part: int, params, repelled: bool) -> Tuple[int, int]:
    """(fee_pool, bonus_pool) carved out of the seller's remaining proceeds; their sum never exceeds the part."""
    fee = _floor_share(seller_part, getattr(params, "caravan_escort_fee_share", 0))
    bonus = _floor_share(seller_part, getattr(params, "caravan_escort_bonus_share", 0)) if repelled else 0
    fee = min(fee, max(0, int(seller_part)))
    bonus = min(bonus, max(0, int(seller_part)) - fee)
    return fee, bonus


def _seller_part(caravan: "models.EconCaravan") -> int:
    seller, _duty = econ_caravan.remaining_payout(_i(caravan.value), _i(caravan.duty),
                                                  _i(caravan.paid_purse) + _i(caravan.paid_treasury),
                                                  _i(caravan.raid_paid))
    return seller


def _seats(params) -> int:
    return max(0, _i(getattr(params, "caravan_escort_seats", 0)))


# =====================================================================================================================
# hiring (C1 / C2, §3.7)
# =====================================================================================================================

@dataclass(frozen=True)
class CaravaneerContext:
    character_id: int
    user_id: int
    npc_id: int
    location_id: int


def _player(db: Session, character_id: int, user_id: int) -> "models.Character":
    character = db.query(models.Character).filter(models.Character.id == int(character_id)).first()
    if character is None:
        raise EconomyApiError(404, MSG_CHARACTER_NOT_FOUND)
    if character.user_id is None or int(character.user_id) != int(user_id):
        raise EconomyApiError(403, MSG_NOT_OWNER)
    if character.is_npc:
        raise EconomyApiError(403, MSG_NOT_PLAYER)
    return character


def require_owner(db: Session, character_id: int, user_id: int) -> "models.Character":
    """404 / 403 owner check of the player character (C3–C6)."""
    return _player(db, character_id, user_id)


def resolve_caravaneer(db: Session, npc_id: int, character_id: int, user_id: int) -> CaravaneerContext:
    """Steps 1–3: owner + player, the caravaneer exists / role / alive, same location. Raises EconomyApiError."""
    character = _player(db, character_id, user_id)
    npc = db.query(models.Character).filter(models.Character.id == int(npc_id)).first()
    if npc is None or not npc.is_npc or npc.npc_role != CARAVANEER_ROLE or npc.npc_status == NPC_DEAD \
            or npc.current_location_id is None:
        raise EconomyApiError(404, MSG_CARAVANEER_NOT_FOUND)
    if character.current_location_id is None or int(character.current_location_id) != int(npc.current_location_id):
        raise EconomyApiError(400, MSG_NOT_AT_CARAVANEER)
    return CaravaneerContext(int(character.id), int(user_id), int(npc.id), int(npc.current_location_id))


def require_npc_tier(db: Session, ctx: CaravaneerContext) -> None:
    """Step 5: the NPC's reputation tier gate (403 ReputationError)."""
    import reputation_crud
    reputation_crud.require_npc_tier(db, ctx.character_id, ctx.npc_id)


def _active_count(db: Session, caravan_id: int, *, lock: bool = False) -> int:
    q = db.query(models.EconCaravanEscort).filter(models.EconCaravanEscort.caravan_id == int(caravan_id),
                                                  models.EconCaravanEscort.status == STATUS_ACTIVE)
    if lock:
        return len(_locked(q.order_by(models.EconCaravanEscort.id), db).all())
    return q.count()


def _caravan_refusal(caravan, location_id: int, raid_status: Optional[str]) -> Optional[Tuple[int, str]]:
    if caravan is None or not caravan.is_physical or caravan.status != caravan_crud.STATUS_IN_TRANSIT:
        return 404, MSG_CARAVAN_NOT_FOUND
    if _i(caravan.route_index) > 0 or caravan.arrived_at is not None:
        return 409, MSG_CARAVAN_GONE
    if caravan.current_location_id is None or int(caravan.current_location_id) != int(location_id):
        return 400, MSG_WRONG_GATE
    if raid_status is not None:
        return 409, MSG_RAIDED
    return None


def _seat_refusal(params, taken: int) -> Optional[Tuple[int, str]]:
    seats = _seats(params)
    if seats == 0:
        return 409, MSG_HIRING_OFF
    if taken >= seats:
        return 409, MSG_NO_SEATS
    return None


def _character_refusal(db: Session, character: "models.Character", caravan: "models.EconCaravan",
                       now: datetime) -> Optional[Tuple[int, str]]:
    """The character side of §3.7 in the contract order (one job, no rejoin, lock, battle, gathering, law, rep)."""
    if character.escort_caravan_id is not None:
        return 409, MSG_ALREADY_ESCORT
    if db.query(models.EconCaravanEscort.id).filter(
            models.EconCaravanEscort.caravan_id == int(caravan.id),
            models.EconCaravanEscort.character_id == int(character.id)).first() is not None:
        return 409, MSG_NO_REJOIN
    message = activity_lock.lock_message(activity_lock.lock_for_character(character))
    if message:
        return 409, message
    if _in_battle(db, character.id):
        return 409, MSG_IN_BATTLE
    if _gathering(db, character.id):
        return 409, MSG_GATHERING
    seller_region = int(caravan.from_region_id) if caravan.from_region_id else None
    if _region_exists(db, seller_region):
        import law_crud
        import reputation_crud
        if law_crud.read_wanted(db, character.id, seller_region, law_crud.load_settings(db), now) > 0:
            return 403, MSG_WANTED
        failure = reputation_crud.gate_failure(db, character.id, seller_region, NEUTRAL_TIER)
        if failure:
            return 403, failure
    return None


def _preparing_here(db: Session, location_id: int) -> List["models.EconCaravan"]:
    rows = (db.query(models.EconCaravan)
            .filter(models.EconCaravan.is_physical.is_(True),
                    models.EconCaravan.status == caravan_crud.STATUS_IN_TRANSIT,
                    models.EconCaravan.arrived_at.is_(None),
                    models.EconCaravan.route_index == 0,
                    models.EconCaravan.current_location_id == int(location_id))
            .order_by(models.EconCaravan.id).all())
    return [r for r in rows if caravan_crud.active_raid_status(db, int(r.id)) is None]


def caravaneer_view(db: Session, ctx: CaravaneerContext, now: Optional[datetime] = None) -> dict:
    """C1: caravans preparing at the caravaneer's gate with per-caravan eligibility. Never from / to / route / value
    and never the number of seats or escorts (PM decision 1): only ``has_seats``. ``pay_estimate`` = the guaranteed
    pay per head when every seat is taken (independent of the current escorts)."""
    now = now or now_utc()
    params = _params(db)
    seats = _seats(params)
    character = db.get(models.Character, ctx.character_id)
    out = []
    for caravan in _preparing_here(db, ctx.location_id):
        taken = _active_count(db, caravan.id)
        refusal = _seat_refusal(params, taken) or _character_refusal(db, character, caravan, now)
        fee, _bonus = pools(_seller_part(caravan), params, False)
        departs = None
        if caravan.next_move_at is not None:
            departs = max(0, int((caravan.next_move_at - now).total_seconds()))
        out.append({"id": int(caravan.id), "group_code": caravan.group_code,
                    "group_name": _group_name(db, caravan.group_code), "departs_in_sec": departs,
                    "has_seats": seats > 0 and taken < seats, "pay_estimate": fee // seats if seats else 0,
                    "can_hire": refusal is None, "reason": refusal[1] if refusal else None})
    return {"npc_id": ctx.npc_id, "location_id": ctx.location_id,
            "my_escort_caravan_id": int(character.escort_caravan_id) if character.escort_caravan_id else None,
            "seats_enabled": seats > 0, "caravans": out}


@dataclass
class HireResult:
    caravan_id: int
    notice: law_notify.Notice


def hire(db: Session, ctx: CaravaneerContext, caravan_id: int, now: Optional[datetime] = None) -> HireResult:
    """C2 (no commit; the caller commits, maps IntegrityError → 409 «больше не возьмут», then publishes). Lock order:
    caravan → its active escort rows → the character. Raises EconomyApiError in the §3.7 order."""
    now = now or now_utc()
    params = _params(db)
    caravan = caravan_crud._lock_caravan(db, caravan_id)
    raid_status = caravan_crud.active_raid_status(db, int(caravan_id)) if caravan is not None else None
    refusal = _caravan_refusal(caravan, ctx.location_id, raid_status)
    if refusal is None:
        refusal = _seat_refusal(params, _active_count(db, caravan.id, lock=True))
    if refusal is not None:
        raise EconomyApiError(*refusal)
    character = _locked(db.query(models.Character).filter(models.Character.id == ctx.character_id), db).first()
    if character is None:
        raise EconomyApiError(404, MSG_CHARACTER_NOT_FOUND)
    refusal = _character_refusal(db, character, caravan, now)
    if refusal is not None:
        raise EconomyApiError(*refusal)
    db.add(models.EconCaravanEscort(caravan_id=int(caravan.id), character_id=int(character.id), status=STATUS_ACTIVE,
                                    hire_location_id=character.current_location_id, joined_at=now))
    character.escort_caravan_id = int(caravan.id)
    character.house_room_id = None
    group = _group_name(db, caravan.group_code)
    message = f"Нанялся в охрану каравана ({group})"
    _log(db, character.id, message, caravan.id, npc_id=ctx.npc_id)
    db.flush()
    return HireResult(int(caravan.id), _notice(character.user_id, f"Вы в охране каравана ({group})", character.id,
                                               caravan.id))


# =====================================================================================================================
# the job (C3), leaving (C4)
# =====================================================================================================================

def _active_row(db: Session, character_id: int) -> Optional["models.EconCaravanEscort"]:
    peek = db.query(models.Character.escort_caravan_id).filter(models.Character.id == int(character_id)).first()
    if peek is None or not peek[0]:
        return None
    return db.query(models.EconCaravanEscort).filter(
        models.EconCaravanEscort.caravan_id == int(peek[0]),
        models.EconCaravanEscort.character_id == int(character_id),
        models.EconCaravanEscort.status == STATUS_ACTIVE).first()


def _escorts_of(db: Session, caravan_id: int) -> List[dict]:
    rows = db.execute(text(
        "SELECT e.character_id, ch.name, ch.avatar FROM econ_caravan_escorts e "
        "LEFT JOIN characters ch ON ch.id = e.character_id WHERE e.caravan_id = :c AND e.status = :s "
        "ORDER BY e.id"), {"c": int(caravan_id), "s": STATUS_ACTIVE}).fetchall()
    return [{"character_id": int(r[0]), "name": r[1], "avatar": r[2]} for r in rows]


def escort_job(db: Session, character_id: int, now: Optional[datetime] = None) -> Optional[dict]:
    """C3: the character's own active job (full route — he is «свой»), or None."""
    now = now or now_utc()
    row = _active_row(db, character_id)
    if row is None:
        return None
    caravan = db.get(models.EconCaravan, int(row.caravan_id))
    if caravan is None:
        return None
    params = _params(db)
    route_ids = [int(x) for x in caravan_crud._json_list(caravan.route)]
    names = caravan_crud._location_names(db, route_ids + ([caravan.current_location_id]
                                                          if caravan.current_location_id else []))
    regions = caravan_crud._region_names(db, [caravan.from_region_id, caravan.to_region_id])
    raid = db.query(models.EconCaravanRaid).filter(models.EconCaravanRaid.caravan_id == int(caravan.id)).first()
    raid_status = raid.status if raid is not None else None
    if caravan.arrived_at is not None or caravan.status != caravan_crud.STATUS_IN_TRANSIT:
        state = STATE_ARRIVED
    elif raid_status in RAID_ACTIVE_STATUSES:
        state = STATE_UNDER_ATTACK
    elif caravan_crud.held_by(db, caravan, now, params, caravan_crud.gate_tables_available(db)) is not None:
        state = STATE_HELD
    elif _i(caravan.route_index) == 0 and raid is None:
        state = STATE_PREPARING
    else:
        state = STATE_ON_ROAD
    next_move = None
    if state in (STATE_PREPARING, STATE_ON_ROAD) and caravan.next_move_at is not None:
        next_move = max(0, int((caravan.next_move_at - now).total_seconds()))
    escorts = _escorts_of(db, caravan.id)
    fee, bonus = pools(_seller_part(caravan), params, raid_status == RAID_REPELLED)
    in_raid = bool(row.in_raid) or (raid is not None and int(character_id) in _ids(raid.escort_ids))
    battle_id = (int(raid.battle_id) if raid is not None and raid_status in RAID_ACTIVE_STATUSES and in_raid
                 and raid.battle_id is not None else None)
    return {
        "caravan_id": int(caravan.id), "group_code": caravan.group_code,
        "group_name": _group_name(db, caravan.group_code),
        "from_region_name": regions.get(int(caravan.from_region_id)) if caravan.from_region_id else None,
        "to_region_name": regions.get(int(caravan.to_region_id)) if caravan.to_region_id else None,
        "route": [{"index": i, "location_id": loc, "name": names.get(loc)} for i, loc in enumerate(route_ids)],
        "route_index": _i(caravan.route_index),
        "current_location_id": int(caravan.current_location_id) if caravan.current_location_id else None,
        "current_location_name": names.get(int(caravan.current_location_id)) if caravan.current_location_id else None,
        "state": state, "next_move_in_sec": next_move, "seats_total": _seats(params), "escorts": escorts,
        "pay_estimate": (fee + bonus) // max(1, len(escorts)), "raid_status": raid_status, "battle_id": battle_id,
        "joined_at": row.joined_at,
    }


@dataclass
class LeaveResult:
    location_id: Optional[int]
    notice: law_notify.Notice


def leave(db: Session, character_id: int, now: Optional[datetime] = None) -> LeaveResult:
    """C4 «Сойти» (no commit): the character stays where the caravan is, no pay, no rejoin (UNIQUE row). Refused
    while the caravan's raid is starting / fighting. Lock order: caravan → escort row → character."""
    now = now or now_utc()
    row = _active_row(db, character_id)
    if row is None:
        raise EconomyApiError(404, MSG_NOT_ESCORT)
    caravan_id = int(row.caravan_id)
    caravan = caravan_crud._lock_caravan(db, caravan_id)
    if caravan_crud.active_raid_status(db, caravan_id) in RAID_ACTIVE_STATUSES:
        raise EconomyApiError(409, MSG_LEAVE_IN_BATTLE)
    row = _locked(db.query(models.EconCaravanEscort).filter(
        models.EconCaravanEscort.caravan_id == caravan_id,
        models.EconCaravanEscort.character_id == int(character_id),
        models.EconCaravanEscort.status == STATUS_ACTIVE), db).first()
    character = _locked(db.query(models.Character).filter(models.Character.id == int(character_id)), db).first()
    if row is None or character is None or character.escort_caravan_id is None \
            or int(character.escort_caravan_id) != caravan_id:
        raise EconomyApiError(404, MSG_NOT_ESCORT)
    row.status = STATUS_LEFT
    row.ended_at = now
    character.escort_caravan_id = None
    group = _group_name(db, caravan.group_code) if caravan is not None else None
    _log(db, character.id, f"Сошёл с каравана ({group or 'товары'})", caravan_id, status=STATUS_LEFT)
    db.flush()
    return LeaveResult(character.current_location_id,
                       _notice(character.user_id, "Вы сошли с каравана — оплаты не будет", character.id, caravan_id))


# =====================================================================================================================
# the caravan channel (C5 / C6)
# =====================================================================================================================

def _member_caravan(db: Session, character_id: int) -> int:
    row = _active_row(db, character_id)
    if row is None:
        raise EconomyApiError(404, MSG_NOT_ESCORT)
    return int(row.caravan_id)


def _message_out(r) -> dict:
    return {"id": int(r[0]), "character_id": int(r[1]), "name": r[2], "avatar": r[3], "body": r[4],
            "created_at": r[5]}


SQL_MESSAGES = ("SELECT m.id, m.character_id, ch.name, ch.avatar, m.body, m.created_at FROM econ_caravan_messages m "
                "LEFT JOIN characters ch ON ch.id = m.character_id WHERE m.caravan_id = :c")


def messages(db: Session, character_id: int, after_id: int = 0) -> dict:
    """C5 (active escorts of that caravan only), oldest → newest, at most 100. ``after_id = 0`` → the latest 100;
    ``after_id > 0`` → the next 100 after it."""
    caravan_id = _member_caravan(db, character_id)
    if int(after_id or 0) > 0:
        rows = db.execute(text(SQL_MESSAGES + " AND m.id > :a ORDER BY m.id LIMIT :n"),
                          {"c": caravan_id, "a": int(after_id), "n": MESSAGES_PAGE}).fetchall()
    else:
        rows = list(reversed(db.execute(text(SQL_MESSAGES + " ORDER BY m.id DESC LIMIT :n"),
                                        {"c": caravan_id, "n": MESSAGES_PAGE}).fetchall()))
    return {"caravan_id": caravan_id, "messages": [_message_out(r) for r in rows]}


def post_message(db: Session, character_id: int, body: str, now: Optional[datetime] = None) -> dict:
    """C6 (no commit): active escort only; 1..500 characters after strip; one message per 3 s per character."""
    now = now or now_utc()
    caravan_id = _member_caravan(db, character_id)
    clean = (body or "").strip()
    if not 1 <= len(clean) <= MESSAGE_MAX_LEN:
        raise EconomyApiError(400, MSG_TEXT_LENGTH)
    last = db.execute(text("SELECT MAX(created_at) FROM econ_caravan_messages WHERE character_id = :c"),
                      {"c": int(character_id)}).scalar()
    if isinstance(last, str):
        last = datetime.fromisoformat(last)
    if last is not None and now - last < MESSAGE_THROTTLE:
        raise EconomyApiError(429, MSG_TOO_OFTEN)
    row = models.EconCaravanMessage(caravan_id=caravan_id, character_id=int(character_id), body=clean,
                                    created_at=now)
    db.add(row)
    db.flush()
    ch = db.execute(text("SELECT name, avatar FROM characters WHERE id = :c"), {"c": int(character_id)}).first()
    return {"id": int(row.id), "character_id": int(character_id), "name": ch[0] if ch else None,
            "avatar": ch[1] if ch else None, "body": clean, "created_at": now}


# =====================================================================================================================
# stepping (§3.8) — inside caravan_pass.step_caravan's transaction, after the caravan row moved
# =====================================================================================================================

def move_escorts(db: Session, caravan: "models.EconCaravan") -> int:
    """Move the caravan's active escorts to its current location (raw write: no law entry check, no faction
    territory refusal — they ride inside the wagon). Lock order: escort rows (asc id) → characters (asc id)."""
    rows = _locked(db.query(models.EconCaravanEscort).filter(
        models.EconCaravanEscort.caravan_id == int(caravan.id),
        models.EconCaravanEscort.status == STATUS_ACTIVE).order_by(models.EconCaravanEscort.id), db).all()
    if not rows or caravan.current_location_id is None:
        return 0
    ids = sorted({int(r.character_id) for r in rows})
    _lock_characters(db, ids)
    ph, params = core.in_params("c", ids)
    result = db.execute(text(
        f"UPDATE characters SET current_location_id = :loc, house_room_id = NULL WHERE id IN ({ph}) "
        "AND escort_caravan_id = :car"),
        {**params, "loc": int(caravan.current_location_id), "car": int(caravan.id)})
    return int(result.rowcount or 0)


# =====================================================================================================================
# delivery (§3.10 pay) — inside economy_caravan_crud.deliver_physical's transaction
# =====================================================================================================================

@dataclass
class PayPlan:
    rows: List["models.EconCaravanEscort"] = field(default_factory=list)
    fee_each: int = 0
    bonus_each: int = 0

    @property
    def total(self) -> int:
        return len(self.rows) * (self.fee_each + self.bonus_each)

    def legs(self, escrow_ref) -> List[core.Leg]:
        each = self.fee_each + self.bonus_each
        if each <= 0:
            return []
        return [core.Leg(escrow_ref, core.AccountRef.character(int(r.character_id)), each)
                for r in sorted(self.rows, key=lambda r: int(r.character_id))]

    def metadata(self) -> List[dict]:
        return [{"character_id": int(r.character_id), "fee": self.fee_each, "bonus": self.bonus_each}
                for r in self.rows]


def _active_rows_locked(db: Session, caravan_id: int) -> List["models.EconCaravanEscort"]:
    return _locked(db.query(models.EconCaravanEscort).filter(
        models.EconCaravanEscort.caravan_id == int(caravan_id),
        models.EconCaravanEscort.status == STATUS_ACTIVE).order_by(models.EconCaravanEscort.id), db).all()


def pay_plan(db: Session, caravan: "models.EconCaravan", seller_part: int) -> PayPlan:
    """Lock the active escorts (asc id) and their characters (asc id, before any account) and split the pools
    ``floor(pool / n)`` per head (remainders stay with the seller). No escorts → an empty plan (old behaviour)."""
    rows = _active_rows_locked(db, caravan.id)
    if not rows:
        return PayPlan()
    _lock_characters(db, [r.character_id for r in rows])
    params = _params(db)
    repelled = caravan_crud.active_raid_status(db, int(caravan.id)) == RAID_REPELLED
    fee, bonus = pools(seller_part, params, repelled)
    n = len(rows)
    return PayPlan(rows, fee // n, bonus // n)


def _clear_columns(db: Session, caravan_id: int, character_ids: Sequence[int]) -> None:
    ids = sorted({int(c) for c in character_ids})
    if not ids:
        return
    ph, params = core.in_params("c", ids)
    db.execute(text(f"UPDATE characters SET escort_caravan_id = NULL WHERE id IN ({ph}) AND escort_caravan_id = :car"),
               {**params, "car": int(caravan_id)})


def finish_paid(db: Session, caravan: "models.EconCaravan", plan: PayPlan, op_id: Optional[int],
                now: datetime) -> List[law_notify.Notice]:
    """After the delivery op: rows → delivered (fee, bonus, op), columns cleared (the escort stays at the destination
    gate), CharacterLog + notices."""
    if not plan.rows:
        return []
    import law_crud
    group = _group_name(db, caravan.group_code) or "товары"
    users = law_crud.character_user_ids(db, [r.character_id for r in plan.rows])
    notices = []
    for row in plan.rows:
        row.status = STATUS_DELIVERED
        row.fee = plan.fee_each
        row.bonus = plan.bonus_each
        row.payout_op_id = op_id
        row.ended_at = now
        extra = f" (+{plan.bonus_each} за отбитый налёт)" if plan.bonus_each > 0 else ""
        message = f"Охрана каравана ({group}): плата {plan.fee_each} марок{extra}"
        _log(db, row.character_id, message, caravan.id, status=STATUS_DELIVERED, fee=plan.fee_each,
             bonus=plan.bonus_each, operation_id=op_id)
        notices.append(_notice(users.get(int(row.character_id)), f"Караван дошёл! {message}", row.character_id,
                               caravan.id, fee=plan.fee_each, bonus=plan.bonus_each))
    _clear_columns(db, caravan.id, [r.character_id for r in plan.rows])
    return notices


def cancel_escorts(db: Session, caravan: "models.EconCaravan", now: datetime) -> List[law_notify.Notice]:
    """Cancel branch: escorts → cancelled, no pay, columns cleared, notice; no rewards."""
    rows = _active_rows_locked(db, caravan.id)
    if not rows:
        return []
    import law_crud
    ids = [int(r.character_id) for r in rows]
    _lock_characters(db, ids)
    users = law_crud.character_user_ids(db, ids)
    message = "Караван отменён — оплаты не будет"
    notices = []
    for row in rows:
        row.status = STATUS_CANCELLED
        row.ended_at = now
        _log(db, row.character_id, message, caravan.id, status=STATUS_CANCELLED)
        notices.append(_notice(users.get(int(row.character_id)), message, row.character_id, caravan.id))
    _clear_columns(db, caravan.id, ids)
    return notices


# =====================================================================================================================
# pass step 6: rewards of delivered escorts (own transaction per escort, never with economy locks)
# =====================================================================================================================

def escort_rep_key(action: str, caravan_id: int, character_id: int, region_id: int) -> str:
    return f"{action}:{int(caravan_id)}:{int(character_id)}:r{int(region_id)}"


def escort_faction_key(caravan_id: int, character_id: int) -> str:
    return f"faction:caravan_escort:c{int(caravan_id)}:{int(character_id)}"


def defense_fame_key(caravan_id: int, character_id: int) -> str:
    return f"caravan_defense:{int(caravan_id)}:{int(character_id)}"


def _select_ids(factory: SessionFactory, sql: str, params: dict) -> List[int]:
    db = factory()
    try:
        return [int(r[0]) for r in db.execute(text(sql), params).fetchall()]
    finally:
        db.rollback()
        db.close()


def reward_one(db: Session, escort_id: int, now: datetime, params) -> bool:
    """Rewards of one delivered escort. Faction points first (own commits, idempotent per event key), then ONE
    transaction: the ``rewards_done`` claim + reputation (seller + buyer region, ``echo=False``) + for a repelled raid
    fought by him the defense reputation and fame. Publishes after the commit. False = nothing to do / claimed."""
    import faction_core as fc
    import faction_kills
    import faction_notify
    import renown_crud
    import reputation_core as rc
    import reputation_crud
    import reputation_notify
    import shadow_core as sc

    info = db.execute(text(
        "SELECT e.character_id, e.caravan_id, e.in_raid, c.from_region_id, c.to_region_id, c.group_code "
        "FROM econ_caravan_escorts e JOIN econ_caravans c ON c.id = e.caravan_id "
        "WHERE e.id = :id AND e.status = :s AND e.rewards_done = 0"),
        {"id": int(escort_id), "s": STATUS_DELIVERED}).first()
    db.rollback()
    if info is None:
        return False
    cid, caravan_id, in_raid = int(info[0]), int(info[1]), bool(info[2])
    faction = faction_kills.apply_caravan_deed(db, cid, fc.ENEMY_ESCORT, escort_faction_key(caravan_id, cid), now)
    try:
        claimed = db.execute(text(
            "UPDATE econ_caravan_escorts SET rewards_done = 1 WHERE id = :id AND rewards_done = 0"),
            {"id": int(escort_id)})
        if (claimed.rowcount or 0) != 1:
            db.rollback()
            faction_notify.publish(faction.notices)
            return False
        regions = [r for r in dict.fromkeys([int(info[3]) if info[3] else None, int(info[4]) if info[4] else None])
                   if r and _region_exists(db, r)]
        defended = in_raid and caravan_crud.active_raid_status(db, caravan_id) == RAID_REPELLED
        group = _group_name(db, info[5]) or "товары"
        results = []
        fame_changes = []
        for region_id in regions:
            results.append(reputation_crud.apply_reputation(
                db, character_id=cid, region_id=region_id, action=rc.ACTION_CARAVAN_ESCORT,
                idem_key=escort_rep_key(rc.ACTION_CARAVAN_ESCORT, caravan_id, cid, region_id),
                reason=f"Охрана каравана ({group}) #{caravan_id}", echo=False, now=now))
            if defended:
                results.append(reputation_crud.apply_reputation(
                    db, character_id=cid, region_id=region_id, action=rc.ACTION_CARAVAN_DEFENSE,
                    idem_key=escort_rep_key(rc.ACTION_CARAVAN_DEFENSE, caravan_id, cid, region_id),
                    reason=f"Отбит налёт на караван ({group}) #{caravan_id}", echo=False, now=now))
        fame = _i(getattr(params, "caravan_escort_defense_fame", 0))
        if defended and fame > 0:
            outcome = renown_crud.add_fame(db, character_id=cid, points=fame, source=sc.SOURCE_CARAVAN_DEFENSE,
                                           event_key=defense_fame_key(caravan_id, cid), ref_id=caravan_id,
                                           reason=f"Отбит налёт на караван ({group})", now=now)
            if outcome.change is not None:
                fame_changes.append(outcome.change)
        db.commit()
    except Exception:
        db.rollback()
        raise
    reputation_notify.publish_tier_changes(reputation_crud.tier_changes_of(results))
    renown_crud.publish_fame_changes(reputation_crud.fame_changes_of(results) + fame_changes)
    faction_notify.publish(faction.notices)
    return True


def escort_rewards(factory: SessionFactory, now: datetime, params) -> int:
    """Pass step 6: delivered escorts without rewards (best effort, retried next pass on failure)."""
    done = 0
    for escort_id in _select_ids(factory, "SELECT id FROM econ_caravan_escorts WHERE status = :s AND rewards_done = 0 "
                                          "ORDER BY id LIMIT :n", {"s": STATUS_DELIVERED, "n": BATCH_SIZE}):
        db = factory()
        try:
            if reward_one(db, escort_id, now, params):
                done += 1
        except Exception:
            db.rollback()
            logger.exception("caravan pass: rewards of escort row %s failed, retried next pass", escort_id)
        finally:
            db.close()
    return done


# =====================================================================================================================
# pass step 7: housekeeping (crash safety, old channel messages)
# =====================================================================================================================

def _release_stale_row(db: Session, escort_id: int, now: datetime) -> Optional[law_notify.Notice]:
    """An ``active`` row whose caravan is gone / no longer in transit → ``released`` (+ its column). Commits."""
    try:
        probe = db.execute(text("SELECT caravan_id FROM econ_caravan_escorts WHERE id = :id"),
                           {"id": int(escort_id)}).first()
        if probe is None:
            db.rollback()
            return None
        caravan = caravan_crud._lock_caravan(db, int(probe[0]))
        row = _locked(db.query(models.EconCaravanEscort).filter(models.EconCaravanEscort.id == int(escort_id)),
                      db).first()
        if row is None or row.status != STATUS_ACTIVE or (
                caravan is not None and caravan.status == caravan_crud.STATUS_IN_TRANSIT):
            db.rollback()
            return None
        _lock_characters(db, [row.character_id])
        row.status = STATUS_RELEASED
        row.ended_at = now
        _clear_columns(db, row.caravan_id, [row.character_id])
        _log(db, row.character_id, MSG_RELEASED, row.caravan_id, status=STATUS_RELEASED)
        user = db.execute(text("SELECT user_id FROM characters WHERE id = :c"), {"c": int(row.character_id)}).scalar()
        notice = _notice(user, MSG_RELEASED, row.character_id, row.caravan_id)
        db.commit()
        return notice
    except Exception:
        db.rollback()
        raise


def escort_housekeeping(factory: SessionFactory, now: datetime) -> int:
    """Pass step 7 (cheap, best effort): (a) active rows of finished / missing caravans → released; (b) dangling
    ``characters.escort_caravan_id`` without an active row → cleared; (c) channel messages of caravans finished more
    than 7 days ago → deleted (1000 per pass)."""
    done = 0
    notices = []
    for escort_id in _select_ids(factory, (
            "SELECT e.id FROM econ_caravan_escorts e LEFT JOIN econ_caravans c ON c.id = e.caravan_id "
            "WHERE e.status = :s AND (c.id IS NULL OR c.status <> :t) ORDER BY e.id LIMIT :n"),
            {"s": STATUS_ACTIVE, "t": caravan_crud.STATUS_IN_TRANSIT, "n": BATCH_SIZE}):
        db = factory()
        try:
            notice = _release_stale_row(db, escort_id, now)
            if notice is not None:
                notices.append(notice)
                done += 1
        except Exception:
            logger.exception("caravan pass: stale escort row %s not released", escort_id)
        finally:
            db.close()
    db = factory()
    try:
        dangling = db.execute(text(
            "SELECT ch.id, ch.escort_caravan_id FROM characters ch WHERE ch.escort_caravan_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM econ_caravan_escorts e WHERE e.character_id = ch.id "
            "AND e.caravan_id = ch.escort_caravan_id AND e.status = :s) ORDER BY ch.id LIMIT :n"),
            {"s": STATUS_ACTIVE, "n": BATCH_SIZE}).fetchall()
        db.rollback()
        for cid, caravan_id in dangling:
            db.execute(text("UPDATE characters SET escort_caravan_id = NULL WHERE id = :c AND escort_caravan_id = :car"),
                       {"c": int(cid), "car": int(caravan_id)})
            db.commit()
            logger.warning("caravan pass: dangling escort column of character %s (caravan %s) cleared", cid,
                           caravan_id)
            done += 1
        ids = [int(r[0]) for r in db.execute(text(
            "SELECT m.id FROM econ_caravan_messages m JOIN econ_caravans c ON c.id = m.caravan_id "
            "WHERE c.status <> :t AND c.finished_at IS NOT NULL AND c.finished_at < :cut ORDER BY m.id LIMIT :n"),
            {"t": caravan_crud.STATUS_IN_TRANSIT, "cut": now - MESSAGES_KEEP,
             "n": HOUSEKEEPING_DELETE_BATCH}).fetchall()]
        if ids:
            ph, params = core.in_params("m", ids)
            db.execute(text(f"DELETE FROM econ_caravan_messages WHERE id IN ({ph})"), params)
            done += len(ids)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("caravan pass: escort housekeeping failed")
    finally:
        db.close()
    if notices:
        law_notify.publish(notices)
    return done
