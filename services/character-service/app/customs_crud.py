"""FEAT-216 customs & smuggling — DB layer (sync SQLAlchemy; features/FEAT-216 §3.3, §3.6, §3.7).

Sections:

* **officer job** (task 5; C1–C4): :func:`resolve_officer_npc` (gate steps 1–3; the API then asks the FEAT-145
  ``npc_dialogue`` gate over HTTP and the NPC tier gate), :func:`officer_view`, :func:`enlist`, :func:`resign`,
  :func:`job`. No activity lock — a plain ``econ_customs_officers`` row (§3.0 A9).
* **admin bans** (task 5; A1, A2): :func:`customs_admin`, :func:`replace_bans`.
* **inspection at the post** (task 4): :func:`start_inspection` / :func:`charge_duty` / :func:`clear_inspection`.
* **detection, fights, seizure** (task 7) — appended below.

Lock order (§3.3): ``… econ_caravans (asc) → econ_caravan_raids → econ_caravan_escorts (asc) →
econ_customs_officers (asc character_id) → … → characters (asc, ONE sorted call) → econ_accounts``. Enlist / resign:
``econ_customs_officers(row) → characters(row)``. ``econ_country_bans`` is never locked (admin replace = DELETE +
INSERT in one tx). Locations-service tables are plain reads (``is_customs`` read with a deploy-skew fallback).
Functions never commit; the API commits and maps :class:`EconomyApiError`.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

import activity_lock
import customs_core
import econ_core as core
import econ_ledger
import models
from economy_crud import EconomyApiError

logger = logging.getLogger("character-service.customs")

LOG_EVENT_TYPE = "customs"
NPC_DEAD = "dead"
NEUTRAL_TIER = "wanderer"           # «Скиталец»: reputation must not be below neutral in the NPC's region

MSG_CHARACTER_NOT_FOUND = "Персонаж не найден"
MSG_NOT_OWNER = "Вы можете управлять только своими персонажами"
MSG_NOT_PLAYER = "На таможню нанимаются только персонажи игроков"
MSG_NPC_NOT_FOUND = "Таможенник не найден"
MSG_NPC_NO_COUNTRY = "Этот таможенник не служит ни одной стране"
MSG_NOT_AT_NPC = "Вы не у таможенника"
MSG_GATE_CLOSED = "Нужен пост-намерение «Диалог с НПС» с этим персонажем"
MSG_GATE_UNAVAILABLE = "Не удалось проверить обращение к таможеннику, попробуйте позже"
MSG_ALREADY_OFFICER = "Вы уже служите на таможне"
MSG_NOT_OFFICER = "Вы не служите на таможне"
MSG_IN_BATTLE = "Персонаж в бою"
MSG_WANTED = "Вас разыскивают в этом краю — на таможню не возьмут"
MSG_COUNTRY_NOT_FOUND = "Страна не найдена"
MSG_UNKNOWN_GROUP = "Неизвестная группа товаров: {code}"
MSG_TOO_MANY_GROUPS = "Слишком много запрещённых групп (не больше {n})"


def now_utc() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _for_update(db: Session) -> bool:
    return core.supports_for_update(db.get_bind().dialect.name)


def _locked(q, db: Session):
    return (q.with_for_update() if _for_update(db) else q).populate_existing()


def _params(db: Session):
    import econ_tick                                    # late: econ_tick imports most of the service
    return econ_tick.load_params(db)


def _rows(db: Session, sql: str, params: Optional[dict] = None):
    """Rows of a read of another service's column that may be absent (deploy skew, SQLite fixtures): None."""
    try:
        with db.begin_nested():
            return db.execute(text(sql), params or {}).fetchall()
    except DBAPIError:
        return None


def _probe(db: Session, sql: str, params: dict) -> bool:
    rows = _rows(db, sql + " LIMIT 1", params)
    return bool(rows)


def _in_battle(db: Session, character_id: int) -> bool:
    return _probe(db, "SELECT 1 FROM battles b JOIN battle_participants bp ON b.id = bp.battle_id "
                      "WHERE bp.character_id = :c AND b.status IN ('pending', 'in_progress') "
                      "AND bp.dropped_out_at IS NULL", {"c": int(character_id)})


def _country_name(db: Session, country_id: Optional[int]) -> Optional[str]:
    if not country_id:
        return None
    return db.execute(text("SELECT name FROM Countries WHERE id = :c"), {"c": int(country_id)}).scalar()


def _log(db: Session, character_id: int, message: str, **meta) -> None:
    db.add(models.CharacterLog(character_id=int(character_id), event_type=LOG_EVENT_TYPE, description=message,
                               metadata_=meta or None))


# =====================================================================================================================
# officer job (C1–C4)
# =====================================================================================================================

@dataclass(frozen=True)
class OfficerNpcContext:
    character_id: int
    user_id: int
    npc_id: int
    location_id: int
    region_id: int
    country_id: int


def require_player(db: Session, character_id: int, user_id: int) -> "models.Character":
    """404 / 403: the character exists, belongs to the user and is a player character."""
    character = db.query(models.Character).filter(models.Character.id == int(character_id)).first()
    if character is None:
        raise EconomyApiError(404, MSG_CHARACTER_NOT_FOUND)
    if character.user_id is None or int(character.user_id) != int(user_id):
        raise EconomyApiError(403, MSG_NOT_OWNER)
    if character.is_npc:
        raise EconomyApiError(403, MSG_NOT_PLAYER)
    return character


def resolve_officer_npc(db: Session, npc_id: int, character_id: int, user_id: int) -> OfficerNpcContext:
    """Gate steps 1–3 (§3.6): owner + player → the «Таможенник» NPC exists / role / alive → same location → the
    NPC's location belongs to a region with a country. Raises EconomyApiError."""
    character = require_player(db, character_id, user_id)
    npc = db.query(models.Character).filter(models.Character.id == int(npc_id)).first()
    if npc is None or not npc.is_npc or npc.npc_role != customs_core.CUSTOMS_ROLE or npc.npc_status == NPC_DEAD \
            or npc.current_location_id is None:
        raise EconomyApiError(404, MSG_NPC_NOT_FOUND)
    if character.current_location_id is None or int(character.current_location_id) != int(npc.current_location_id):
        raise EconomyApiError(400, MSG_NOT_AT_NPC)
    region_id, country_id = econ_ledger.resolve_location(db, int(npc.current_location_id))
    if not region_id or not country_id:
        raise EconomyApiError(404, MSG_NPC_NO_COUNTRY)
    return OfficerNpcContext(int(character.id), int(user_id), int(npc.id), int(npc.current_location_id),
                             int(region_id), int(country_id))


def require_npc_tier(db: Session, ctx: OfficerNpcContext) -> None:
    """Gate step 5: the NPC's reputation tier gate (403 ReputationError)."""
    import reputation_crud
    reputation_crud.require_npc_tier(db, ctx.character_id, ctx.npc_id)


def _officer_row(db: Session, character_id: int, *, lock: bool = False) -> Optional["models.EconCustomsOfficer"]:
    q = db.query(models.EconCustomsOfficer).filter(models.EconCustomsOfficer.character_id == int(character_id))
    return (_locked(q, db) if lock else q).first()


def is_active_officer(db: Session, character_id: int) -> bool:
    """Is the character an enlisted (active) customs officer of any country? (Used by the fence hire refusal.)"""
    row = _officer_row(db, character_id)
    return row is not None and row.status == customs_core.OFFICER_ACTIVE


def _job_out(db: Session, row: Optional["models.EconCustomsOfficer"]) -> Optional[dict]:
    if row is None or row.status != customs_core.OFFICER_ACTIVE:
        return None
    return {"country_id": int(row.country_id), "country_name": _country_name(db, row.country_id),
            "status": row.status, "enlisted_at": row.enlisted_at, "seizures": int(row.seizures or 0),
            "earned": int(row.earned or 0)}


def job(db: Session, character_id: int) -> Optional[dict]:
    """C4: the character's active customs job, or None."""
    return _job_out(db, _officer_row(db, character_id))


def _enlist_refusal(db: Session, character: "models.Character", row: Optional["models.EconCustomsOfficer"],
                    ctx: OfficerNpcContext, now: datetime) -> Optional[Tuple[int, str]]:
    """The character side of the enlist checks in the §3.6 order: not already an active officer → not
    activity-locked / not in battle → not wanted in the NPC's region → reputation ≥ «Скиталец» there."""
    if row is not None and row.status == customs_core.OFFICER_ACTIVE:
        return 409, MSG_ALREADY_OFFICER
    message = activity_lock.lock_message(activity_lock.lock_for_character(character))
    if message:
        return 409, message
    if _in_battle(db, character.id):
        return 409, MSG_IN_BATTLE
    import law_crud
    import reputation_crud
    if law_crud.read_wanted(db, character.id, ctx.region_id, law_crud.load_settings(db), now) > 0:
        return 403, MSG_WANTED
    failure = reputation_crud.gate_failure(db, character.id, ctx.region_id, NEUTRAL_TIER)
    if failure:
        return 403, failure
    return None


def officer_view(db: Session, ctx: OfficerNpcContext, now: Optional[datetime] = None) -> dict:
    """C1: the «Таможенник» window — the NPC's country, the character's own job and whether he can enlist here."""
    now = now or now_utc()
    params = _params(db)
    character = db.get(models.Character, ctx.character_id)
    row = _officer_row(db, ctx.character_id)
    refusal = _enlist_refusal(db, character, row, ctx, now)
    return {"npc_id": ctx.npc_id, "country_id": ctx.country_id, "country_name": _country_name(db, ctx.country_id),
            "location_id": ctx.location_id, "job": _job_out(db, row),
            "can_enlist": refusal is None, "reason": refusal[1] if refusal else None,
            "params": {"officer_share": float(getattr(params, "customs_officer_share", 0) or 0),
                       "alert_minutes": int(getattr(params, "customs_alert_minutes", 0) or 0)}}


def enlist(db: Session, ctx: OfficerNpcContext, now: Optional[datetime] = None) -> dict:
    """C2 (no commit; the caller commits and maps IntegrityError → 409 «уже служите»). Lock order:
    ``econ_customs_officers(row) → characters(row)``. A resigned row is reactivated for the NPC's country (career
    counters ``seizures`` / ``earned`` are kept). Returns the job dict."""
    now = now or now_utc()
    row = _officer_row(db, ctx.character_id, lock=True)
    character = _locked(db.query(models.Character).filter(models.Character.id == ctx.character_id), db).first()
    if character is None:
        raise EconomyApiError(404, MSG_CHARACTER_NOT_FOUND)
    refusal = _enlist_refusal(db, character, row, ctx, now)
    if refusal is not None:
        raise EconomyApiError(*refusal)
    if row is None:
        row = models.EconCustomsOfficer(character_id=ctx.character_id, country_id=ctx.country_id, npc_id=ctx.npc_id,
                                        location_id=ctx.location_id, status=customs_core.OFFICER_ACTIVE,
                                        enlisted_at=now, ended_at=None, seizures=0, earned=0)
        db.add(row)
    else:
        row.country_id = ctx.country_id
        row.npc_id = ctx.npc_id
        row.location_id = ctx.location_id
        row.status = customs_core.OFFICER_ACTIVE
        row.enlisted_at = now
        row.ended_at = None
    country = _country_name(db, ctx.country_id)
    _log(db, ctx.character_id, f"Поступил на службу в таможню ({country or 'страна'})",
         country_id=ctx.country_id, npc_id=ctx.npc_id)
    db.flush()
    return _job_out(db, row)


def resign(db: Session, character_id: int, now: Optional[datetime] = None) -> None:
    """C3: leave the customs service, anytime and anywhere (no commit). 409 when not an active officer.
    Lock order: ``econ_customs_officers(row)`` (the character row is not written)."""
    now = now or now_utc()
    row = _officer_row(db, character_id, lock=True)
    if row is None or row.status != customs_core.OFFICER_ACTIVE:
        raise EconomyApiError(409, MSG_NOT_OFFICER)
    row.status = customs_core.OFFICER_RESIGNED
    row.ended_at = now
    _log(db, character_id, "Ушёл со службы на таможне", country_id=int(row.country_id))
    db.flush()


# =====================================================================================================================
# admin: posts + banned groups (A1, A2)
# =====================================================================================================================

def _groups(db: Session) -> List[dict]:
    rows = db.execute(text("SELECT code, name FROM econ_goods_groups ORDER BY sort_order, code")).fetchall()
    return [{"code": r[0], "name": r[1]} for r in rows]


def load_bans(db: Session) -> Dict[int, List[str]]:
    """``{country_id: [codes]}`` of every banned group (table missing → ``{}``)."""
    rows = _rows(db, "SELECT country_id, group_code FROM econ_country_bans ORDER BY country_id, group_code")
    out: Dict[int, List[str]] = {}
    for r in rows or ():
        out.setdefault(int(r[0]), []).append(r[1])
    return out


def posts_by_country(db: Session) -> Dict[int, List[dict]]:
    """``{country_id: [{location_id, name, is_port}]}`` of the customs posts (``Locations.is_customs``); the column
    missing (deploy skew) → ``{}``. Posts outside any country are skipped."""
    rows = _rows(db, "SELECT id, name, is_port FROM Locations WHERE is_customs = 1 ORDER BY id")
    if rows is None:
        rows = _rows(db, "SELECT id, name FROM Locations WHERE is_customs = 1 ORDER BY id") or []
    out: Dict[int, List[dict]] = {}
    for r in rows:
        _region, country_id = econ_ledger.resolve_location(db, int(r[0]))
        if not country_id:
            continue
        out.setdefault(int(country_id), []).append(
            {"location_id": int(r[0]), "name": r[1], "is_port": bool(r[2]) if len(r) > 2 else False})
    return out


def _country_out(country_id: int, name: Optional[str], bans: List[str], posts: List[dict],
                 group_order: Dict[str, int]) -> dict:
    return {"country_id": int(country_id), "name": name,
            "banned_groups": sorted(bans, key=lambda c: (group_order.get(c, len(group_order)), c)),
            "posts": posts}


def customs_admin(db: Session) -> dict:
    """A1: every country with its banned groups and its customs posts, plus the goods groups catalogue."""
    groups = _groups(db)
    order = {g["code"]: i for i, g in enumerate(groups)}
    bans = load_bans(db)
    posts = posts_by_country(db)
    countries = db.execute(text("SELECT id, name FROM Countries ORDER BY name, id")).fetchall()
    return {"countries": [_country_out(int(c[0]), c[1], bans.get(int(c[0]), []), posts.get(int(c[0]), []), order)
                          for c in countries],
            "groups": groups}


def replace_bans(db: Session, country_id: int, codes: Optional[List[str]], now: Optional[datetime] = None) -> dict:
    """A2 (no commit): replace one country's banned groups (DELETE + INSERT, never locked). 404 unknown country,
    400 unknown code / too many. Returns the A1 country item."""
    now = now or now_utc()
    name_row = db.execute(text("SELECT id, name FROM Countries WHERE id = :c"), {"c": int(country_id)}).first()
    if name_row is None:
        raise EconomyApiError(404, MSG_COUNTRY_NOT_FOUND)
    groups = _groups(db)
    try:
        wanted = customs_core.normalize_ban_codes(codes, [g["code"] for g in groups])
    except ValueError as exc:
        code = str(exc)
        if code == "too_many":
            raise EconomyApiError(400, MSG_TOO_MANY_GROUPS.format(n=customs_core.MAX_BANNED_GROUPS))
        raise EconomyApiError(400, MSG_UNKNOWN_GROUP.format(code=code[:32]))
    db.query(models.EconCountryBan).filter(models.EconCountryBan.country_id == int(country_id)) \
        .delete(synchronize_session=False)
    for code in wanted:
        db.add(models.EconCountryBan(country_id=int(country_id), group_code=code, created_at=now))
    db.flush()
    order = {g["code"]: i for i, g in enumerate(groups)}
    return _country_out(int(country_id), name_row[1], wanted, posts_by_country(db).get(int(country_id), []), order)


# =====================================================================================================================
# inspection at the post (task 4) — start_inspection / charge_duty
# =====================================================================================================================
# A legal foreign physical caravan routed via a post (``customs_state = pending``) stops at ``route[customs_index]``:
# the step (``caravan_pass.step_caravan``) or the unloading at a customs landing port (``sea_cargo._settle_hold``)
# calls :func:`start_inspection`, which charges the duty (escrow → destination country) and holds the caravan until
# ``customs_until``; the next due step clears it (:func:`clear_inspection`) and only then arrives / moves on. Lock
# order: the caller already holds ``econ_caravans(row)`` (+ escorts / characters); the duty op locks the accounts last.

KEY_DUTY = "duty"                       # idempotency key ``caravan:c<id>:duty``


def inspection_minutes(params) -> int:
    """``customs_inspection_minutes`` (0 = the duty is charged without a stop)."""
    return max(0, int(getattr(params, "customs_inspection_minutes", 0) or 0))


def at_post(row, index: Optional[int] = None) -> bool:
    """The caravan stands at its customs post (``index`` defaults to ``route_index``) and was not inspected yet."""
    if row.customs_state != customs_core.STATE_PENDING or row.customs_index is None:
        return False
    here = int(row.route_index or 0) if index is None else int(index)
    return here == int(row.customs_index)


def inspecting_here(row) -> bool:
    """A due step of a caravan under inspection at its post (it clears there before moving on / arriving)."""
    return (row.customs_state == customs_core.STATE_INSPECTING and row.customs_index is not None
            and int(row.route_index or 0) == int(row.customs_index))


def charge_duty(db: Session, row: "models.EconCaravan", now: datetime) -> Optional[int]:
    """§3.2: the duty leaves the escrow at the post (no commit; caravan row locked by the caller). The amount is the
    not-yet-settled duty part ``remaining_payout(..., duty_paid=None)`` — pro-rated when the caravan was raided before
    the post. Op ``caravan_duty`` escrow → the destination country (world when gone), untaxed, idempotent
    (``caravan:c<id>:duty``); duty 0 → no op. Sets ``duty_paid`` / ``duty_op_id`` and ``customs_state =
    inspecting`` in the same transaction. Already settled → nothing (returns the stored op id)."""
    import economy_caravan_crud as caravan_crud         # late: keeps this module import-light
    import econ_caravan
    if row.customs_state in customs_core.DUTY_SETTLED_STATES:
        return int(row.duty_op_id) if row.duty_op_id is not None else None
    paid_total = int(row.paid_purse or 0) + int(row.paid_treasury or 0)
    _seller, duty_now = econ_caravan.remaining_payout(int(row.value or 0), int(row.duty or 0), paid_total,
                                                      int(row.raid_paid or 0), freight=int(row.freight or 0),
                                                      duty_paid=None)
    duty_now = max(0, int(duty_now))
    op_id = None
    if duty_now > 0:
        post = int(row.customs_location_id) if row.customs_location_id else None
        region_id, _country = econ_ledger.resolve_location(db, post)
        legs = [core.Leg(core.AccountRef.caravan_escrow(), caravan_crud._country_or_world(db, row.to_country_id),
                         duty_now)]
        try:
            posted = econ_ledger.post_operation(
                db, op_type=core.OP_CARAVAN_DUTY, legs=legs, source_service=caravan_crud.SOURCE_SERVICE,
                location_id=post, region_id=region_id, apply_tax=False,
                idempotency_key=caravan_crud.caravan_key(row.id, KEY_DUTY),
                metadata={"caravan_id": int(row.id), "customs_location_id": post,
                          "to_country_id": int(row.to_country_id) if row.to_country_id else None,
                          "group_code": row.group_code, "duty": int(row.duty or 0), "duty_paid": duty_now,
                          "raid_paid": int(row.raid_paid or 0)})
            op_id = posted.operation_id
        except core.DuplicateOperation as exc:
            op_id = exc.operation_id
    row.duty_paid = duty_now
    row.duty_op_id = op_id
    row.customs_state = customs_core.STATE_INSPECTING
    return op_id


def start_inspection(db: Session, row: "models.EconCaravan", now: datetime, params) -> bool:
    """§3.0 A6: the caravan reached its post — duty charged (:func:`charge_duty`) and the caravan stops until
    ``customs_until = now + customs_inspection_minutes`` (``next_move_at = customs_until``; raidable there like at a
    gate). ``customs_inspection_minutes = 0`` → duty only, the caravan is cleared at once and the caller continues its
    normal arrive / move logic. Returns True when the caravan stops (no commit)."""
    charge_duty(db, row, now)
    minutes = inspection_minutes(params)
    if minutes <= 0:
        clear_inspection(row, now)
        return False
    row.customs_until = now + timedelta(minutes=minutes)
    row.next_move_at = row.customs_until
    row.arrived_at = None
    return True


def clear_inspection(row: "models.EconCaravan", now: datetime) -> None:
    """The inspection is over (``customs_state = cleared``); ``customs_until`` stays as the admin's record."""
    row.customs_state = customs_core.STATE_CLEARED
    if row.customs_until is None or row.customs_until > now:
        row.customs_until = now


def inspection_left_sec(row, now: datetime) -> Optional[int]:
    """Seconds until the inspection ends (None when the caravan is not under inspection)."""
    if row.customs_state != customs_core.STATE_INSPECTING or row.customs_until is None:
        return None
    return max(0, int((row.customs_until - now).total_seconds()))


# =====================================================================================================================
# detection, fights, seizure (task 7)
# =====================================================================================================================
# A contraband caravan that moved into a non-final location of a country where it is illegal (§3.0 A12) is checked
# right after the step loop of the caravan pass (``caravan_pass._customs_checks``): first the customs officers on watch
# there (one roll each, ascending id) → the first success raises an ALERT (``customs_alert_officer_id`` /
# ``customs_alert_until``; ``held_by`` = "customs") and a notice to that officer only; otherwise ONE roll of the law
# guards standing there → no active escorts: confiscation without a fight; escorts: an automatic patrol fight
# (battle-service ``/battles/internal/customs-fight``, enforcer NPC mode), BS 409 «Защитников каравана нет» →
# confiscation without a fight. The officer starts his fight himself (C5 ``POST /characters/caravans/{id}/inspect``:
# :func:`begin_inspection` + ``caravan_raid_crud.spawn_guards``). A won customs / patrol fight freezes the caravan
# (``caravan_raid_crud.settle_raid``), then :func:`confiscate_raid` (claimed by ``seized_done``) and
# :func:`consequences` (``law_done``) run as the raid follow-ups. Nothing here ever tells a non-escort player that a
# caravan carries contraband: every refusal of the inspect endpoint that depends on the caravan is the same 404.

MSG_NOTHING_TO_INSPECT = "Здесь нечего досматривать"
MSG_INSPECT_UNAVAILABLE = "Досмотр сейчас невозможен"
MSG_ALERT = "Вы заметили подозрительный караван ({group}). Досмотрите его в течение {minutes} мин"
MSG_SEIZED = "Контрабанда задержана"
MSG_REPELLED = "Контрабандисты отбились"
MSG_ESCORT_REPELLED = "Досмотр отбит! Надбавка будет выплачена по прибытии"
MSG_OFFICER_SHARE = "Конфискация контрабанды ({group}): ваша доля — {marks} марок"
MSG_OFFICER_NO_SHARE = "Конфискация контрабанды ({group}) завершена"
MSG_ESCORT_SEIZED = "Караван конфискован — оплаты не будет"
# battle-service B1 409 text (enforcer mode, no escort could be placed) → confiscation without a fight
BS_NO_DEFENDERS = "Защитников каравана нет"

WS_CUSTOMS_ALERT = "customs_alert"
WS_CUSTOMS = "customs"
KEY_SEIZE = "seize"                     # idempotency key ``caravan:c<id>:seize``
MAX_ENFORCERS = 5                       # patrol fight: guards on team 0

CHECK_ALERT = "alert"
CHECK_SEIZED = "seized"
CHECK_FIGHT = "patrol_fight"
SEIZE_CLOSED = "closed"                 # a won fight whose caravan is gone: the claim is set, nothing moved
WON = "won"                             # caravan_raid_crud.STATUS_WON (no import cycle at module load)


def rng():
    """THE seam of the detection rolls (tests patch it): an object with ``random()``."""
    import law_crud
    return law_crud.rng()


def enabled(params) -> bool:
    return int(getattr(params, "customs_enabled", 0) or 0) == 1


def fame_key(raid_id: int, character_id: int) -> str:
    return f"fame:customs:r{int(raid_id)}:{int(character_id)}"


def reputation_key(raid_id: int, character_id: int) -> str:
    return f"customs_seizure:r{int(raid_id)}:{int(character_id)}"


def crime_key(raid_id: int, character_id: int) -> str:
    return f"law:smuggling:r{int(raid_id)}:{int(character_id)}"


def _group_name(db: Session, code: Optional[str]) -> str:
    if not code:
        return "товары"
    name = db.execute(text("SELECT name FROM econ_goods_groups WHERE code = :c"), {"c": code}).scalar()
    return name or code


def checkable(db: Session, row, now: datetime) -> bool:
    """A contraband caravan on the road, between two steps, not at its final node, never fought, no open alert."""
    import economy_caravan_crud as caravan_crud
    if row is None or not row.is_physical or not bool(getattr(row, "is_contraband", False)):
        return False
    if row.status != caravan_crud.STATUS_IN_TRANSIT or row.arrived_at is not None or row.next_move_at is None:
        return False
    route_len = len(caravan_crud._json_list(row.route))
    if row.current_location_id is None or int(row.route_index or 0) >= route_len - 1:
        return False
    if caravan_crud.customs_alert_open(row, now):
        return False
    return caravan_crud.active_raid_status(db, int(row.id)) is None


def _escort_reduction(db: Session, escort_ids, params, shadow_settings):
    """The caravan's stealth (§3.0 A13): base param + best effective stealth of the active escorts, through
    ``stealth_reduction_pct``. Returns ``(reduction_pct, stealth)``."""
    import law_crud
    import shadow_core
    stealths = [law_crud.stealth_info(db, cid, shadow_settings).effective for cid in escort_ids]
    stealth = customs_core.caravan_stealth(getattr(params, "customs_caravan_stealth", 0), stealths)
    return shadow_core.stealth_reduction_pct(stealth, shadow_settings), stealth


def officer_attention(db: Session, character_id: int, shadow_settings):
    """The officer's «внимательность» (§3.0 A13): his own effective stealth through ``stealth_reduction_pct``."""
    import law_crud
    import shadow_core
    return shadow_core.stealth_reduction_pct(law_crud.stealth_info(db, character_id, shadow_settings).effective,
                                             shadow_settings)


def watching_officers(db: Session, country_id: int, location_id: int, region_id: Optional[int], now: datetime,
                      exclude=()) -> List[int]:
    """Active officers of ``country_id`` standing at ``location_id`` who are on watch: player, not activity-locked
    (jail / unconscious / escort …), not in battle, not wanted in the location's region (§3.0 A9, §3.12 Q4)."""
    import law_crud
    rows = db.execute(text(
        "SELECT o.character_id FROM econ_customs_officers o JOIN characters c ON c.id = o.character_id "
        "WHERE o.status = :s AND o.country_id = :country AND c.current_location_id = :loc AND c.is_npc = 0 "
        "ORDER BY o.character_id"),
        {"s": customs_core.OFFICER_ACTIVE, "country": int(country_id), "loc": int(location_id)}).fetchall()
    skip = {int(x) for x in exclude or ()}
    law_settings = None
    out = []
    for (cid,) in rows:
        cid = int(cid)
        if cid in skip:
            continue
        character = db.get(models.Character, cid)
        if character is None or activity_lock.lock_message(activity_lock.lock_for_character(character)):
            continue
        if _in_battle(db, cid):
            continue
        if region_id:
            law_settings = law_settings or law_crud.load_settings(db)
            if law_crud.read_wanted(db, cid, region_id, law_settings, now) > 0:
                continue
        out.append(cid)
    return out


def free_guards(db: Session, location_id: int, now: datetime) -> List[int]:
    """Law guards at the location that are not fighting already (at most :data:`MAX_ENFORCERS`)."""
    import law_crud
    return [g for g in law_crud.guards_at(db, location_id, now) if not _in_battle(db, g)][:MAX_ENFORCERS]


def check_caravan(factory, caravan_id: int, now: datetime, params, bans, roller=None) -> Optional[str]:
    """One contraband caravan after its step (best effort, own transactions; the caller skips the whole step while an
    economy run is running). Returns :data:`CHECK_ALERT` | :data:`CHECK_SEIZED` | :data:`CHECK_FIGHT` | None.
    Publishes its notices."""
    import caravan_raid_crud as raid_crud
    import law_core
    import law_notify
    import renown_crud
    roller = roller or rng()
    db = factory()
    try:
        row = db.get(models.EconCaravan, int(caravan_id))
        if not checkable(db, row, now):
            return None
        location_id = int(row.current_location_id)
        region_id, country_id = econ_ledger.resolve_location(db, location_id)
        if not customs_core.illegal_in(country_id, row.to_country_id, row.group_code, bans):
            return None
        escorts = raid_crud.active_escort_ids(db, int(row.id))
        shadow_settings = renown_crud.load_shadow_settings(db)
        reduction, stealth = _escort_reduction(db, escorts, params, shadow_settings)
        for officer_id in watching_officers(db, int(country_id), location_id, region_id, now, exclude=escorts):
            attention = officer_attention(db, officer_id, shadow_settings)
            chance = customs_core.detection_chance(params.customs_detect_base_pct, attention, reduction,
                                                   params.customs_detect_min_pct, params.customs_detect_max_pct)
            hit, roll = law_core.roll_succeeds(chance, roller)
            logger.info("customs check: caravan=%s officer=%s stealth=%s chance=%s roll=%s hit=%s", caravan_id,
                        officer_id, stealth, chance, roll, hit)
            if hit:
                db.rollback()
                notice = raise_alert(db, int(caravan_id), officer_id, location_id, now, params)
                if notice is None:
                    return None
                law_notify.publish([notice])
                return CHECK_ALERT
        guards = free_guards(db, location_id, now)
        if not guards:
            return None
        chance = customs_core.patrol_chance(params.customs_patrol_detect_pct, reduction,
                                            params.customs_detect_max_pct)
        hit, roll = law_core.roll_succeeds(chance, roller)
        logger.info("customs patrol check: caravan=%s guards=%s chance=%s roll=%s hit=%s", caravan_id, guards,
                    chance, roll, hit)
        if not hit:
            return None
    finally:
        db.rollback()
        db.close()
    if not escorts:
        result = confiscate_tx(factory, int(caravan_id), kind=customs_core.KIND_PATROL, location_id=location_id,
                               now=now, params=params)
        return CHECK_SEIZED if result.status == CHECK_SEIZED else None
    return start_patrol_fight(factory, int(caravan_id), guards, location_id, now, params)


def raise_alert(db: Session, caravan_id: int, officer_id: int, location_id: int, now: datetime, params):
    """Alert tx (commits; locks only ``econ_caravans(row)``): re-check, set the alert columns, CharacterLog of the
    officer. Returns the officer's notice (publish after this call) or None when the caravan moved on meanwhile."""
    import economy_caravan_crud as caravan_crud
    import law_crud
    import law_notify
    minutes = max(1, int(getattr(params, "customs_alert_minutes", 0) or 1))
    try:
        row = caravan_crud._lock_caravan(db, caravan_id)
        if not checkable(db, row, now) or int(row.current_location_id) != int(location_id):
            db.rollback()
            return None
        row.customs_alert_officer_id = int(officer_id)
        row.customs_alert_until = now + timedelta(minutes=minutes)
        message = MSG_ALERT.format(group=_group_name(db, row.group_code), minutes=minutes)
        _log(db, officer_id, message, caravan_id=int(caravan_id), location_id=int(location_id))
        user_id = law_crud.character_user_ids(db, [officer_id]).get(int(officer_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    logger.info("customs alert: caravan=%s officer=%s location=%s minutes=%s", caravan_id, officer_id, location_id,
                minutes)
    return law_notify.Notice(user_id, message, WS_CUSTOMS_ALERT, law_notify.CATEGORY_SYSTEM,
                             {"character_id": int(officer_id), "caravan_id": int(caravan_id),
                              "location_id": int(location_id), "inspect_in_sec": minutes * 60})


# --------------------------------------------------------------------------------------------- fight start

def _insert_check(db: Session, row, *, kind: str, leader_id: int, group: bool, now: datetime) -> int:
    """The ``starting`` raid row of a customs / patrol fight (caravan row locked by the caller); clears the alert."""
    import caravan_raid_crud as raid_crud
    location_id = int(row.current_location_id)
    region_id, _country = econ_ledger.resolve_location(db, raid_crud.crime_location(db, row, location_id))
    raid = models.EconCaravanRaid(
        caravan_id=int(row.id), leader_character_id=int(leader_id), is_group=bool(group), location_id=location_id,
        region_id=int(region_id) if region_id else None, status=raid_crud.STATUS_STARTING, created_at=now, kind=kind)
    db.add(raid)
    row.customs_alert_officer_id = None
    row.customs_alert_until = None
    db.flush()
    return int(raid.id)


def begin_inspection(db: Session, caravan_id: int, character_id: int, group: bool,
                     now: Optional[datetime] = None):
    """C5 Tx A (commits): the officer's «Досмотреть». Every check that could reveal the caravan is contraband answers
    the same 404 «Здесь нечего досматривать»; activity lock / battle → 409 with their own text. Clears the alert (it
    is not restored on a later failure — the caravan moves on). Returns ``caravan_raid_crud.RaidStart``."""
    import caravan_raid_crud as raid_crud
    import economy_caravan_crud as caravan_crud
    from sqlalchemy.exc import IntegrityError
    now = now or now_utc()
    nothing = EconomyApiError(404, MSG_NOTHING_TO_INSPECT)
    character = db.query(models.Character).filter(models.Character.id == int(character_id)).first()
    officer = _officer_row(db, character_id)
    if character is None or character.is_npc or officer is None or officer.status != customs_core.OFFICER_ACTIVE:
        db.rollback()
        raise nothing
    message = activity_lock.lock_message(activity_lock.lock_for_character(character))
    if message:
        db.rollback()
        raise EconomyApiError(409, message)
    if _in_battle(db, character_id):
        db.rollback()
        raise EconomyApiError(409, MSG_IN_BATTLE)
    here = int(character.current_location_id) if character.current_location_id is not None else None
    try:
        row = caravan_crud._lock_caravan(db, caravan_id)
        if (row is None or not row.is_physical or not row.is_contraband
                or row.status != caravan_crud.STATUS_IN_TRANSIT or row.arrived_at is not None
                or row.customs_alert_officer_id is None or int(row.customs_alert_officer_id) != int(character_id)
                or not caravan_crud.customs_alert_open(row, now)
                or here is None or row.current_location_id is None or int(row.current_location_id) != here
                or caravan_crud.active_raid_status(db, int(row.id)) is not None):
            raise nothing
        raid_id = _insert_check(db, row, kind=customs_core.KIND_CUSTOMS, leader_id=character_id, group=group, now=now)
        location_id = int(row.current_location_id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise nothing
    except Exception:
        db.rollback()
        raise
    return raid_crud.RaidStart(raid_id, int(caravan_id), location_id)


def begin_patrol(db: Session, caravan_id: int, guard_id: int, location_id: int, now: datetime):
    """Patrol Tx A (commits): the ``starting`` raid row ``kind = patrol`` (leader = the first guard). None when the
    caravan is no longer checkable at that location."""
    import caravan_raid_crud as raid_crud
    import economy_caravan_crud as caravan_crud
    from sqlalchemy.exc import IntegrityError
    try:
        row = caravan_crud._lock_caravan(db, caravan_id)
        if not checkable(db, row, now) or int(row.current_location_id) != int(location_id):
            db.rollback()
            return None
        raid_id = _insert_check(db, row, kind=customs_core.KIND_PATROL, leader_id=guard_id, group=False, now=now)
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    except Exception:
        db.rollback()
        raise
    return raid_crud.RaidStart(raid_id, int(caravan_id), int(location_id))


def start_patrol_fight(factory, caravan_id: int, guard_ids: List[int], location_id: int, now: datetime,
                       params) -> Optional[str]:
    """§3.0 A11: guards (team 0, enforcer NPC mode) vs the caravan's player escorts (team 1, no caravan mobs), started
    from the scheduler thread (FEAT-214 ``sea_raid_crud.start_raid`` pattern, ``asyncio.run``). BS 409 «Защитников
    каравана нет» → the raid row is dropped and the caravan confiscated without a fight; any other failure → the row is
    dropped and the caravan moves on. Never raises."""
    import asyncio
    import battle_client
    import caravan_raid_crud as raid_crud
    from sqlalchemy.exc import DBAPIError
    db = factory()
    try:
        try:
            start = begin_patrol(db, caravan_id, guard_ids[0], location_id, now)
            if start is None:
                return None
            escorts = raid_crud.active_escort_ids(db, caravan_id)
            db.rollback()
        except Exception:
            db.rollback()
            logger.exception("customs patrol: caravan %s fight not begun", caravan_id)
            return None
        try:
            created = asyncio.run(battle_client.create_customs_battle(
                start.raid_id, caravan_id, location_id, enforcer_npc_ids=guard_ids, escort_character_ids=escorts))
        except battle_client.BattleServiceError as exc:
            raid_crud.abandon_start(db, start)
            if exc.status_code == 409 and exc.detail == BS_NO_DEFENDERS:
                result = confiscate_tx(factory, caravan_id, kind=customs_core.KIND_PATROL, location_id=location_id,
                                       now=now, params=params)
                return CHECK_SEIZED if result.status == CHECK_SEIZED else None
            logger.warning("customs patrol: caravan %s fight refused (%s %s)", caravan_id, exc.status_code,
                           exc.detail)
            return None
        except Exception:
            logger.exception("customs patrol: caravan %s battle create crashed", caravan_id)
            raid_crud.abandon_start(db, start)
            return None
        battle_id = int(created["battle_id"])
        attackers = created.get("attacker_character_ids") or list(guard_ids)
        placed = [e for e in (created.get("escort_character_ids") or []) if e in set(escorts)]
        for attempt in range(2):
            try:
                raid_crud.mark_fighting(db, start.raid_id, battle_id, attackers, now, escort_ids=placed)
                break
            except DBAPIError:
                db.rollback()
                # the battle exists: the pass re-attaches a lost Tx B through battles.caravan_raid_id
                logger.exception("customs patrol %s: mark fighting failed (attempt %s)", start.raid_id, attempt + 1)
        logger.info("customs patrol %s: caravan=%s location=%s battle=%s guards=%s escorts=%s", start.raid_id,
                    caravan_id, location_id, battle_id, attackers, placed)
        return CHECK_FIGHT
    finally:
        db.rollback()
        db.close()


# --------------------------------------------------------------------------------------------- confiscation

@dataclass
class SeizeResult:
    status: str                                       # seized | already | postponed
    notices: list = field(default_factory=list)
    operation_id: Optional[int] = None
    amount: int = 0


def confiscate(db: Session, caravan_id: int, *, kind: str, location_id: Optional[int], now: datetime, params,
               raid_id: Optional[int] = None) -> SeizeResult:
    """§3.2 seizure (no commit). Lock order (§3.3): ``econ_regions (asc: seizure, from, to) → econ_region_goods (asc)
    → econ_caravans(row) → econ_caravan_raids(row) → escorts (asc) → econ_customs_officers (asc) → characters (one
    sorted call: escorts ∪ paid officers) → econ_accounts``.

    ``R = paid_total − raid_paid − freight_paid − duty_paid`` (the whole escrow rest) → op ``caravan_seizure``
    (untaxed, ``caravan:c<id>:seize``): ``floor(R × customs_officer_share)`` split among the fight's player attackers
    (``customs`` kind only), the rest → the seizure country (world when none). The buyer gets nothing back. The goods
    ``units − stolen − sunk`` go to the seizure region's market stock, else back to the origin, else are written off.
    The caravan is cancelled (``seized_customs`` | ``seized_patrol``), its active escorts cancelled without pay. With
    ``raid_id`` the raid must be ``won`` and not ``seized_done`` (it gets marked); without, the caravan must never
    have fought."""
    import caravan_escort_crud as escort_crud
    import caravan_raid_crud as raid_crud
    import economy_caravan_crud as caravan_crud
    import law_crud
    import law_notify
    already = SeizeResult("already")
    probe = db.execute(text("SELECT from_region_id, to_region_id, group_code FROM econ_caravans WHERE id = :id"),
                       {"id": int(caravan_id)}).first()
    if probe is None:
        return already
    from_id, to_id, code = int(probe[0]), int(probe[1]), probe[2]
    raid_probe = None
    if raid_id is not None:
        raid_probe = db.execute(text("SELECT location_id, region_id FROM econ_caravan_raids WHERE id = :id"),
                                {"id": int(raid_id)}).first()
        if raid_probe is None:
            return already
        location_id = int(raid_probe[0])
    seize_region, seize_country = econ_ledger.resolve_location(db, location_id)
    if seize_region is None and raid_probe is not None and raid_probe[1]:
        seize_region = int(raid_probe[1])               # a ship's deck: the law of the departure port's shore
        seize_country = caravan_crud._region_country(db, seize_region)
    regions = caravan_crud._lock_regions(db, [r for r in (seize_region, from_id, to_id) if r])
    goods = caravan_crud._lock_goods(db, [(rid, code) for rid in {seize_region, from_id} if rid and rid in regions])
    row = caravan_crud._lock_caravan(db, caravan_id)
    raid = None
    if raid_id is not None:
        raid = raid_crud._lock_raid(db, raid_id)
        if (raid is None or raid.status != raid_crud.STATUS_WON or bool(raid.seized_done)
                or int(raid.caravan_id) != int(caravan_id)):
            return already
        if row is None or row.status != caravan_crud.STATUS_IN_TRANSIT or not row.is_physical:
            raid.seized_done = True                     # the caravan is gone / finished: nothing left to seize
            return SeizeResult(SEIZE_CLOSED)
    elif row is None or row.status != caravan_crud.STATUS_IN_TRANSIT or not row.is_physical:
        return already
    elif caravan_crud.active_raid_status(db, int(row.id)) is not None:
        return already                                  # a fight runs (or ran): the follow-up path seizes it

    escort_rows = escort_crud._active_rows_locked(db, int(row.id))
    players: List[int] = []
    if raid is not None and kind == customs_core.KIND_CUSTOMS:
        players = raid_crud._players(db, raid_crud._attackers(db, raid))
    officer_rows = []
    if players:
        officer_rows = _locked(db.query(models.EconCustomsOfficer)
                               .filter(models.EconCustomsOfficer.character_id.in_(players))
                               .order_by(models.EconCustomsOfficer.character_id), db).all()
    raid_crud._lock_characters(db, [int(r.character_id) for r in escort_rows] + players)

    paid_total = int(row.paid_purse or 0) + int(row.paid_treasury or 0)
    rest = max(0, paid_total - int(row.raid_paid or 0) - int(row.freight_paid or 0) - int(row.duty_paid or 0))
    pool = customs_core.officer_pool(rest, getattr(params, "customs_officer_share", 0)) if players else 0
    each, _remainder = customs_core.officer_split(pool, len(players))
    paid_officers = list(players) if each > 0 else []
    country_ref = caravan_crud._country_or_world(db, seize_country)
    escrow_ref = core.AccountRef.caravan_escrow()
    country_part = rest - each * len(paid_officers)
    legs = [core.Leg(escrow_ref, core.AccountRef.character(cid), each) for cid in paid_officers]
    if country_part > 0:
        legs.append(core.Leg(escrow_ref, country_ref, country_part))
    caravan_crud._lock_balances(db, [escrow_ref, country_ref]
                                + [core.AccountRef.character(cid) for cid in paid_officers])

    notices = escort_crud.cancel_escorts(db, row, now)  # rows + characters already locked above (same order)
    units = caravan_crud._remaining_units(row)
    target, goods_to = None, None
    if seize_region and caravan_crud._participates(regions.get(seize_region)) and (seize_region, code) in goods:
        target, goods_to = goods[(seize_region, code)], seize_region
    elif caravan_crud._region_exists(db, from_id) and (from_id, code) in goods:
        target, goods_to = goods[(from_id, code)], from_id
    if target is not None:
        target.stock = caravan_crud._dec3(caravan_crud._dec3(target.stock) + units)
    else:
        logger.warning("caravan %s seized: neither region %s nor origin %s takes %s units of %s — written off",
                       row.id, seize_region, from_id, units, code)
    row.goods_returned = goods_to is not None and goods_to == from_id
    row.cancel_reason = (customs_core.REASON_SEIZED_CUSTOMS if kind == customs_core.KIND_CUSTOMS
                         else customs_core.REASON_SEIZED_PATROL)
    db.flush()
    try:
        posted = econ_ledger.post_operation(
            db, op_type=core.OP_CARAVAN_SEIZURE, legs=legs, source_service=caravan_crud.SOURCE_SERVICE,
            location_id=int(location_id) if location_id else None, region_id=seize_region, apply_tax=False,
            idempotency_key=caravan_crud.caravan_key(row.id, KEY_SEIZE),
            metadata={"caravan_id": int(row.id), "raid_id": int(raid.id) if raid is not None else None,
                      "kind": kind, "from_region_id": from_id, "to_region_id": to_id, "group_code": code,
                      "units": str(units), "goods_region_id": goods_to, "seized_region_id": seize_region,
                      "seized_country_id": seize_country, "rest": rest, "officer_pool": pool,
                      "officers": {str(cid): each for cid in paid_officers}, "country_part": country_part,
                      "paid_total": paid_total, "raid_paid": int(row.raid_paid or 0),
                      "freight_paid": int(row.freight_paid or 0), "duty_paid": int(row.duty_paid or 0)})
        op_id = posted.operation_id
    except core.DuplicateOperation as exc:
        op_id = exc.operation_id
    row.status = caravan_crud.STATUS_CANCELLED
    row.runs_left = 0
    row.next_move_at = None
    row.finished_at = now
    row.finished_run_id = None
    row.finish_op_id = op_id
    row.seized_region_id = int(seize_region) if seize_region else None
    row.seized_country_id = int(seize_country) if seize_country else None
    row.customs_alert_officer_id = None
    row.customs_alert_until = None
    if raid is not None:
        raid.seized_done = True
        raid.officer_paid = each * len(paid_officers)

    # the escort notice text: «Караван отменён» → «Караван конфискован» (the escort knows what he carried)
    for notice in notices:
        notice.message = MSG_ESCORT_SEIZED
    if players:
        group = _group_name(db, code)
        users = law_crud.character_user_ids(db, players)
        by_id = {int(o.character_id): o for o in officer_rows}
        for cid in players:
            share = each if cid in paid_officers else 0
            officer = by_id.get(cid)
            if officer is not None:
                officer.seizures = int(officer.seizures or 0) + 1
                officer.earned = int(officer.earned or 0) + share
            message = (MSG_OFFICER_SHARE.format(group=group, marks=share) if share > 0
                       else MSG_OFFICER_NO_SHARE.format(group=group))
            _log(db, cid, message, caravan_id=int(row.id), raid_id=int(raid.id), marks=share)
            notices.append(law_notify.Notice(users.get(cid), message, WS_CUSTOMS, law_notify.CATEGORY_PROGRESS,
                                             {"character_id": cid, "caravan_id": int(row.id),
                                              "raid_id": int(raid.id), "marks": share}))
    db.flush()
    logger.info("caravan %s seized (%s): rest=%s officers=%s x %s country=%s goods->%s units=%s", row.id, kind, rest,
                paid_officers, each, seize_country, goods_to, units)
    return SeizeResult(CHECK_SEIZED, notices, op_id, rest)


def _economy_run_in_progress(db: Session) -> bool:
    return db.execute(text("SELECT 1 FROM econ_tick_runs WHERE status = 'running' LIMIT 1")).first() is not None


def confiscate_in(db: Session, caravan_id: int, *, kind: str, location_id: Optional[int], now: datetime, params,
                  raid_id: Optional[int] = None) -> SeizeResult:
    """:func:`confiscate` as one transaction of ``db`` (commits, then publishes the notices). ``postponed`` while an
    economy run is ``running`` (a region never changes in the middle of a resumable run; the raid follow-up retries)."""
    import law_notify
    try:
        if _economy_run_in_progress(db):
            db.rollback()
            return SeizeResult("postponed")
        result = confiscate(db, caravan_id, kind=kind, location_id=location_id, now=now, params=params,
                            raid_id=raid_id)
        if result.status in (CHECK_SEIZED, SEIZE_CLOSED):
            db.commit()
        else:
            db.rollback()
    except core.DuplicateOperation:
        db.rollback()
        return SeizeResult("already")
    except Exception:
        db.rollback()
        raise
    if result.notices:
        law_notify.publish(result.notices)
    return result


def confiscate_tx(factory, caravan_id: int, *, kind: str, location_id: Optional[int], now: datetime, params,
                  raid_id: Optional[int] = None) -> SeizeResult:
    """:func:`confiscate_in` on a fresh session of ``factory``."""
    db = factory()
    try:
        return confiscate_in(db, caravan_id, kind=kind, location_id=location_id, now=now, params=params,
                             raid_id=raid_id)
    finally:
        db.close()


def raid_to_seize(db: Session, raid_id: int):
    """``(caravan_id, kind, location_id)`` of a won customs / patrol fight not confiscated yet, else None (plain
    read; the transaction is closed)."""
    try:
        row = db.execute(text("SELECT caravan_id, kind, location_id, status, seized_done FROM econ_caravan_raids "
                              "WHERE id = :id"), {"id": int(raid_id)}).first()
    finally:
        db.rollback()
    if row is None or row[1] not in customs_core.ENFORCEMENT_KINDS or row[3] != WON or bool(row[4]):
        return None
    return int(row[0]), row[1], int(row[2])


def confiscate_raid_in(db: Session, raid_id: int, now: datetime, params) -> SeizeResult:
    """Follow-up of a won ``customs`` / ``patrol`` fight on ``db`` (claimed by ``seized_done`` in :func:`confiscate`)."""
    target = raid_to_seize(db, raid_id)
    if target is None:
        return SeizeResult("already")
    caravan_id, kind, location_id = target
    return confiscate_in(db, caravan_id, kind=kind, location_id=location_id, now=now, params=params,
                         raid_id=int(raid_id))


def confiscate_raid(factory, raid_id: int, now: datetime, params) -> SeizeResult:
    """:func:`confiscate_raid_in` on a fresh session of ``factory``."""
    db = factory()
    try:
        return confiscate_raid_in(db, raid_id, now, params)
    finally:
        db.close()


# --------------------------------------------------------------------------------------------- consequences

def consequences(db: Session, raid, caravan, params, now: datetime):
    """Law Tx of a won ``customs`` / ``patrol`` fight (the caller claimed ``law_done`` and commits): the crime
    ``smuggling`` (reported, ``customs_smuggling_wanted_points``) in the seizure region for every escort of the caravan
    whose row ended ``fallen`` or ``cancelled``; for ``customs``: fame (source ``customs_seizure``) and the reputation
    action ``customs_seizure`` (echo) in the seizure region for every player attacker. Returns a
    ``shadow_crud.KillOutcome`` (publish after the commit)."""
    import caravan_escort_crud as escort_crud
    import caravan_raid_crud as raid_crud
    import law_core
    import law_crud
    import renown_crud
    import reputation_core as rc
    import reputation_crud
    import shadow_core
    import shadow_crud
    outcome = shadow_crud.KillOutcome()
    region_id = caravan.seized_region_id or raid.region_id
    if not region_id or not shadow_crud._region_exists(db, region_id):
        return outcome
    region_id = int(region_id)
    location_id = int(raid.location_id) if raid.location_id else None
    battle_id = int(raid.battle_id) if raid.battle_id else None
    points = max(0, int(getattr(params, "customs_smuggling_wanted_points", 0) or 0))
    escorts = [int(r[0]) for r in db.execute(text(
        "SELECT DISTINCT character_id FROM econ_caravan_escorts WHERE caravan_id = :c AND status IN (:f, :x) "
        "ORDER BY character_id"),
        {"c": int(caravan.id), "f": escort_crud.STATUS_FALLEN, "x": escort_crud.STATUS_CANCELLED}).fetchall()]
    if points > 0 and escorts:
        law_settings = law_crud.load_settings(db)
        levels = law_crud.load_levels(db)
        for cid in escorts:
            crime = law_crud.register_crime(
                db, crime_type=law_core.CRIME_SMUGGLING, character_id=cid, region_id=region_id, points=points,
                event_key=crime_key(raid.id, cid), location_id=location_id, battle_id=battle_id, now=now,
                settings=law_settings, levels=levels, status=law_core.CRIME_REPORTED)
            if crime.change is not None:
                outcome.wanted_changes.append(crime.change)
    if raid.kind == customs_core.KIND_CUSTOMS:
        players = raid_crud._players(db, raid_crud._attackers(db, raid))
        fame = max(0, int(getattr(params, "customs_seizure_fame", 0) or 0))
        results = []
        for cid in players:
            if fame > 0:
                result = renown_crud.add_fame(db, character_id=cid, points=fame,
                                              source=shadow_core.SOURCE_CUSTOMS_SEIZURE,
                                              event_key=fame_key(raid.id, cid), ref_id=int(raid.id), now=now)
                if result.change is not None:
                    outcome.fame_changes.append(result.change)
            results.append(reputation_crud.apply_reputation(
                db, character_id=cid, region_id=region_id, action=rc.ACTION_CUSTOMS_SEIZURE,
                idem_key=reputation_key(raid.id, cid), reason=f"Конфискация контрабанды (караван {int(caravan.id)})",
                echo=True, now=now))
        outcome.tier_changes.extend(reputation_crud.tier_changes_of(results))
        outcome.fame_changes.extend(reputation_crud.fame_changes_of(results))
    logger.info("customs raid %s consequences: region=%s escorts=%s points=%s", raid.id, region_id, escorts, points)
    return outcome
