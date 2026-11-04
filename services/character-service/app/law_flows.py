"""FEAT-198 law — flows that commit and call other services (§3.5).

The routers (``law_api``) and the scheduler pass (``law_pass``, through ``asyncio.run``) share these coroutines:

* :func:`choose`         — the player's answer to the guards (fine / surrender / flee / fight);
* :func:`send_to_jail`   — the forced move to the region jail + the term (reuses ``main._prepare_move`` and
                           ``crud.apply_admin_move(commit=False)``, so the move and the jail commit together);
* :func:`battle_result`  — the guard battle end (callback from battle-service or the pass polling);
* :func:`auto_resolve`   — an ignored encounter after ``encounter_timeout_hours``.

DB work is sync SQLAlchemy (the service pattern); HTTP side effects never run while a row lock is held. Every flow
returns the notifications to publish AFTER its commit (``law_notify.publish``); the flows never publish themselves.
"""

import logging
from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

import activity_lock
import battle_client
import crud
import law_core as lc
import law_crud
import law_notify
from law_crud import LawError

logger = logging.getLogger("character-service.law_flows")

PLAYER_TEAM = 1                     # the player is team 1 in a guard battle (§3.6 battle-service contract)

MSG_JAIL_MOVE_FAILED = "Не удалось доставить в тюрьму, попробуйте ещё раз"
MSG_BATTLE_FAILED = "Не удалось начать бой со стражей"
MSG_FINED = "Штраф уплачен — стража больше вас не разыскивает в этом крае"
MSG_JAILED = "Вы сдались страже и заключены под стражу — срок {until}"
MSG_FLED = "Вам удалось скрыться от стражи"
MSG_FLED_BACK = "Вам удалось скрыться от стражи — вы вернулись в «{name}»"
MSG_FLEE_BLOCKED = "Бежать не удалось — стража преградила путь"
MSG_AWAITING_CHOICE = "Стража ждёт вашего решения"
MSG_FIGHT = "Бой со стражей начался"
MSG_FLEE_FIGHT = "Бежать не удалось — стражник вступает в бой"
MSG_GUARD_GONE = "Стражника на месте не оказалось — вас отпустили"
MSG_WON = "Вы одолели стражника — путь свободен"
MSG_LOST_FINE_FULL = "Стража одолела вас и взяла штраф"
MSG_LOST_FINE_PART = "Стража одолела вас и забрала всё золото в счёт штрафа — розыск не снят"
MSG_AUTO_FINE_FULL = "Вы так и не ответили страже — с вас взыскан штраф"
MSG_AUTO_FINE_PART = "Вы так и не ответили страже — в счёт штрафа забрано всё золото, розыск не снят"
MSG_AUTO_JAIL = "Вы так и не ответили страже — вас заключили под стражу, срок {until}"


def _main():
    import main  # late: main includes the law router, so a top-level import would be circular
    return main


def _user_notice(db: Session, character_id: int, message: str, ws_type: str, **data) -> law_notify.Notice:
    user_id = law_crud.character_user_ids(db, [character_id]).get(int(character_id))
    return law_notify.Notice(user_id, message, ws_type, data={"character_id": int(character_id), **data})


# =====================================================================================================================
# jail
# =====================================================================================================================

async def send_to_jail(db: Session, character_id: int, encounter_id: int, *, action: str,
                       key: str, statuses: Tuple[str, ...] = lc.ENC_OPEN,
                       ) -> Optional[Tuple["law_crud.models.LawJailTerm", List[law_notify.Notice]]]:
    """Move the character to the region jail and start the term (§3.5). None when the encounter is no longer open
    (another worker resolved it) or no longer in one of ``statuses`` (FEAT-200: the auto-resolution passes only
    ``pending`` so a fight chosen meanwhile is never auto-closed). Raises LawError 409 (no jail) or
    HTTPException 409/502 from ``_prepare_move``."""
    enc = law_crud.get_encounter(db, encounter_id)
    if enc is None:
        raise LawError(404, law_crud.MSG_ENCOUNTER_NOT_FOUND)
    if enc.status not in statuses:
        return None
    jail_location = law_crud.region_jail_location(db, enc.region_id)
    if jail_location is None:
        raise LawError(409, law_crud.MSG_NO_JAIL)
    character = law_crud._require_character(db, character_id)
    from_location = character.current_location_id
    moving = from_location is None or int(from_location) != int(jail_location)
    from_name = crud._get_location_name(db, from_location)
    to_name = crud._get_location_name(db, jail_location)
    gathering_cancelled = False
    db.rollback()                               # nothing held across the HTTP calls
    if moving:
        gathering_cancelled = await _main()._prepare_move(db, character_id, from_location, "jail")
    try:
        character = law_crud.lock_character(db, character_id)
        enc = law_crud.get_encounter(db, encounter_id, lock=True)
        if character is None or enc is None or enc.status not in statuses:
            db.rollback()
            return None
        now = law_crud.now_utc()
        settings = law_crud.load_settings(db)
        if moving:
            crud.apply_admin_move(
                db, character_id=character_id, from_location_id=from_location, from_location_name=from_name,
                to_location_id=jail_location, to_location_name=to_name, gathering_cancelled=gathering_cancelled,
                event_type="jail",
                description=f"Заключён под стражу: «{from_name or '—'}» → «{to_name or '—'}»", commit=False)
        term = law_crud.jail_writes(db, character, enc, jail_location, key=key, action=action, now=now,
                                    settings=settings)
        db.commit()
    except Exception:
        db.rollback()
        raise
    region_name = law_crud.region_names(db, [term.region_id]).get(int(term.region_id))
    notice = _user_notice(db, character_id, law_notify.jailed_message(region_name, term.until, now),
                          law_notify.WS_JAILED, term_id=int(term.id))
    return term, [notice]


def _jail_message(template: str, term) -> str:
    return template.format(until=law_notify.remaining(term.until, law_crud.now_utc()))


# =====================================================================================================================
# the player's choice
# =====================================================================================================================

def _replay(db: Session, character_id: int, encounter_id: int, key: str) -> dict:
    """A repeated ``request_id``: answer from the current state, change nothing."""
    enc = law_crud.get_encounter(db, encounter_id)
    if enc is None or int(enc.character_id) != int(character_id):
        raise LawError(404, law_crud.MSG_ENCOUNTER_NOT_FOUND)
    out = {"result": None, "message": "", "battle_id": None, "jail": None, "encounter": None}
    if enc.status == lc.ENC_JAILED:
        term = law_crud.active_term(db, character_id, law_crud.now_utc())
        out.update(result=law_crud.RESULT_JAILED, jail=law_crud.jail_out(db, term) if term else None,
                   message=_jail_message(MSG_JAILED, term) if term else "Вы в тюрьме")
    elif enc.status in (lc.ENC_FINED, lc.ENC_AUTO_FINED):
        out.update(result=law_crud.RESULT_FINED, message=MSG_FINED)
    elif enc.status == lc.ENC_FLED:
        out.update(result=law_crud.RESULT_FLED, message=MSG_FLED)
    elif enc.status == lc.ENC_FIGHTING:
        out.update(result=law_crud.RESULT_FIGHT, message=MSG_FIGHT, battle_id=enc.battle_id)
    elif enc.status == lc.ENC_GUARD_GONE:
        out.update(result=law_crud.RESULT_GUARD_GONE, message=MSG_GUARD_GONE)
    elif enc.status == lc.ENC_PENDING:
        # Pending again: a failed flee with every guard busy — or a reverted fight / move (502). Only the first
        # really was a blocked flee; otherwise the choice is simply offered again.
        message = MSG_FLEE_BLOCKED if law_crud.log_action(db, key) == lc.LOG_FLEE_FAIL else MSG_AWAITING_CHOICE
        out.update(result=law_crud.RESULT_FLEE_BLOCKED, message=message,
                   encounter=law_crud.encounter_out(db, enc))
    else:
        raise LawError(409, law_crud.MSG_ENCOUNTER_CLOSED)
    return out


async def _fight(db: Session, character, enc, *, key: str, after_flee: bool) -> Tuple[dict, list]:
    """Start the guard battle. Called with the character + encounter rows locked (pending, or after a failed flee)."""
    now = law_crud.now_utc()
    guard_id, any_alive = law_crud.pick_free_guard(db, enc, now)
    if guard_id is None:
        if any_alive:
            if after_flee:                      # the flee_fail row and flee_used stay; the choice is offered again
                db.commit()
                return ({"result": law_crud.RESULT_FLEE_BLOCKED, "message": MSG_FLEE_BLOCKED,
                         "encounter": law_crud.encounter_out(db, enc)}, [])
            db.rollback()
            raise LawError(409, law_crud.MSG_GUARD_BUSY)
        law_crud.guard_gone(db, character, enc, key=f"{key}:gone", now=now)
        db.commit()
        return {"result": law_crud.RESULT_GUARD_GONE, "message": MSG_GUARD_GONE}, []
    encounter_id, character_id = int(enc.id), int(character.id)
    law_crud.start_fight(db, character, enc, guard_id, key=f"{key}:fight" if after_flee else key, now=now)
    db.commit()
    try:
        battle_id = await battle_client.create_guard_battle(encounter_id, character_id, guard_id)
    except battle_client.BattleServiceError as exc:
        _revert_fight(db, character_id, encounter_id)
        if exc.status_code == 409:
            raise LawError(409, exc.detail if isinstance(exc.detail, str) and exc.detail else
                           law_crud.MSG_GUARD_BUSY)
        raise LawError(502, MSG_BATTLE_FAILED)
    try:
        law_crud.lock_character(db, character_id)
        enc = law_crud.get_encounter(db, encounter_id, lock=True)
        if enc is not None and enc.status == lc.ENC_FIGHTING and not enc.battle_id:
            enc.battle_id = int(battle_id)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("law: battle %s of encounter %s not stored (the callback will still match)", battle_id,
                         encounter_id)
    return ({"result": law_crud.RESULT_FIGHT, "message": MSG_FLEE_FIGHT if after_flee else MSG_FIGHT,
             "battle_id": int(battle_id)}, [])


def _revert_fight(db: Session, character_id: int, encounter_id: int) -> None:
    try:
        law_crud.lock_character(db, character_id)
        enc = law_crud.get_encounter(db, encounter_id, lock=True)
        if enc is not None and enc.status == lc.ENC_FIGHTING and not enc.battle_id:
            enc.status = lc.ENC_PENDING
            enc.fight_started_at = None
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("law: fight of encounter %s not reverted (the pass will reset it)", encounter_id)


async def _flee_move_back(db: Session, character_id: int, encounter_id: int) -> Optional[str]:
    """§3.14-ANSWERED A7: after a successful flee the character goes back where they came from (a system move: no
    entry evaluation, so no new encounter there). Best-effort: on any failure the character stays. Returns the
    origin location name when moved."""
    enc = law_crud.get_encounter(db, encounter_id)
    if enc is None or not enc.from_location_id or int(enc.from_location_id) == int(enc.location_id):
        return None
    to_name = crud._get_location_name(db, enc.from_location_id)
    if to_name is None:
        return None
    character = law_crud._require_character(db, character_id)
    if character.current_location_id is None or int(character.current_location_id) != int(enc.location_id):
        return None
    if activity_lock.lock_for_character(character)["locked"]:
        return None
    from_name = crud._get_location_name(db, enc.location_id)
    db.rollback()
    try:
        gathering = await _main()._prepare_move(db, character_id, int(enc.location_id), "law_flee")
        crud.apply_admin_move(
            db, character_id=character_id, from_location_id=int(enc.location_id), from_location_name=from_name,
            to_location_id=int(enc.from_location_id), to_location_name=to_name, gathering_cancelled=gathering,
            event_type="law_flee", description=f"Скрылся от стражи: «{from_name or '—'}» → «{to_name or '—'}»")
    except HTTPException as exc:
        db.rollback()
        logger.warning("law: flee move back of character %s failed: %s", character_id, exc.detail)
        return None
    except Exception:
        db.rollback()
        logger.exception("law: flee move back of character %s failed", character_id)
        return None
    return to_name


async def choose(db: Session, character_id: int, encounter_id: int, choice: str,
                 request_id: str) -> Tuple[dict, List[law_notify.Notice]]:
    """``POST …/law/encounter/{id}/choice`` (owner checked by the router). Returns (LawChoiceOut dict, notices)."""
    key = f"law:choice:{encounter_id}:{request_id}"
    if law_crud.log_exists(db, key):
        return _replay(db, character_id, encounter_id, key), []
    character, enc = law_crud.lock_open_encounter(db, character_id, encounter_id)
    options = law_crud.encounter_options(db, enc)
    if choice == lc.CHOICE_SURRENDER and lc.CHOICE_SURRENDER not in options and enc.has_jail:
        db.rollback()
        raise LawError(409, law_crud.MSG_NO_JAIL)
    if choice not in options:
        db.rollback()
        raise LawError(400, law_crud.MSG_CHOICE_UNAVAILABLE)
    settings, now = law_crud.load_settings(db), law_crud.now_utc()

    if choice == lc.CHOICE_FINE:
        try:
            law_crud.pay_fine(db, character, enc, key=key, now=now, settings=settings)
            db.commit()
        except Exception:
            db.rollback()
            raise
        notice = _user_notice(db, character_id, MSG_FINED, law_notify.WS_RESOLVED, encounter_id=int(encounter_id))
        return {"result": law_crud.RESULT_FINED, "message": MSG_FINED}, [notice]

    if choice == lc.CHOICE_SURRENDER:
        db.rollback()
        try:
            done = await send_to_jail(db, character_id, encounter_id, action=lc.LOG_SURRENDER, key=key)
        except HTTPException as exc:
            if exc.status_code == 502:
                raise LawError(502, MSG_JAIL_MOVE_FAILED)
            raise
        if done is None:
            raise LawError(409, law_crud.MSG_ENCOUNTER_CLOSED)
        term, notices = done
        return ({"result": law_crud.RESULT_JAILED, "message": _jail_message(MSG_JAILED, term),
                 "jail": law_crud.jail_out(db, term)}, notices)

    if choice == lc.CHOICE_FLEE:
        try:
            ok, _chance, _roll = law_crud.flee_roll(db, character, enc, key=key, now=now, settings=settings)
        except Exception:
            db.rollback()
            raise
        if ok:
            db.commit()
            name = await _flee_move_back(db, character_id, encounter_id)
            message = MSG_FLED_BACK.format(name=name) if name else MSG_FLED
            notice = _user_notice(db, character_id, message, law_notify.WS_RESOLVED, encounter_id=int(encounter_id))
            return {"result": law_crud.RESULT_FLED, "message": message}, [notice]
        db.flush()
        return await _fight(db, character, enc, key=key, after_flee=True)

    return await _fight(db, character, enc, key=key, after_flee=False)


# =====================================================================================================================
# battle end / timeout
# =====================================================================================================================

def _forced_fine_commit(db: Session, character_id: int, encounter_id: int, *, key: str, action: str,
                        full_message: str, part_message: str,
                        statuses: Tuple[str, ...] = lc.ENC_OPEN) -> Optional[List[law_notify.Notice]]:
    try:
        character = law_crud.lock_character(db, character_id)
        enc = law_crud.get_encounter(db, encounter_id, lock=True)
        if character is None or enc is None or enc.status not in statuses:
            db.rollback()
            return None
        settings, now = law_crud.load_settings(db), law_crud.now_utc()
        _amount, full = law_crud.forced_fine(db, character, enc, key=key, action=action, now=now, settings=settings)
        db.commit()
    except Exception:
        db.rollback()
        raise
    message = full_message if full else part_message
    return [_user_notice(db, character_id, message, law_notify.WS_RESOLVED, encounter_id=int(encounter_id))]


async def battle_result(db: Session, *, battle_id: int, encounter_id: int, winner_team: Optional[int],
                        aborted: bool) -> Tuple[dict, List[law_notify.Notice]]:
    """The guard battle ended (§3.5). Idempotent: anything but a ``fighting`` encounter is a duplicate."""
    enc = law_crud.get_encounter(db, encounter_id)
    if enc is None:
        raise LawError(404, law_crud.MSG_ENCOUNTER_NOT_FOUND)
    if enc.battle_id and int(enc.battle_id) != int(battle_id):
        raise LawError(409, law_crud.MSG_BATTLE_MISMATCH)
    if enc.status != lc.ENC_FIGHTING:
        return {"ok": True, "status": enc.status, "duplicate": True}, []
    character_id = int(enc.character_id)
    base_key = f"law:fight:{encounter_id}:{battle_id}"
    notices: List[law_notify.Notice] = []

    if aborted or winner_team == PLAYER_TEAM:
        try:
            character = law_crud.lock_character(db, character_id)
            enc = law_crud.get_encounter(db, encounter_id, lock=True)
            if character is None or enc is None or enc.status != lc.ENC_FIGHTING:
                db.rollback()
                return {"ok": True, "status": enc.status if enc else "", "duplicate": True}, []
            now = law_crud.now_utc()
            if aborted:                         # admin force-finish: the choice is offered again
                enc.status = lc.ENC_PENDING
                enc.battle_id = None
                enc.fight_started_at = None
                law_crud._log(db, key=f"{base_key}:aborted", character_id=character_id,
                              action=lc.LOG_FIGHT_ABORTED, region_id=int(enc.region_id), ref_id=int(encounter_id),
                              now=now)
            else:
                law_crud._close(character, enc, lc.ENC_WON, now)
                law_crud._log(db, key=f"{base_key}:won", character_id=character_id, action=lc.LOG_FIGHT_WON,
                              region_id=int(enc.region_id), ref_id=int(encounter_id), now=now)
                notices.append(_user_notice(db, character_id, MSG_WON, law_notify.WS_RESOLVED,
                                            encounter_id=int(encounter_id)))
            db.commit()
        except Exception:
            db.rollback()
            raise
        return {"ok": True, "status": lc.ENC_PENDING if aborted else lc.ENC_WON, "duplicate": False}, notices

    # lost (incl. a timeout)
    if law_crud.region_jail_location(db, enc.region_id) is not None:
        done = await send_to_jail(db, character_id, encounter_id, action=lc.LOG_FIGHT_LOST, key=f"{base_key}:lost")
        if done is None:
            current = law_crud.get_encounter(db, encounter_id)
            return {"ok": True, "status": current.status if current else "", "duplicate": True}, []
        return {"ok": True, "status": lc.ENC_JAILED, "duplicate": False}, done[1]
    sent = _forced_fine_commit(db, character_id, encounter_id, key=f"{base_key}:lost", action=lc.LOG_FIGHT_LOST,
                               full_message=MSG_LOST_FINE_FULL, part_message=MSG_LOST_FINE_PART)
    if sent is None:
        current = law_crud.get_encounter(db, encounter_id)
        return {"ok": True, "status": current.status if current else "", "duplicate": True}, []
    return {"ok": True, "status": lc.ENC_AUTO_FINED, "duplicate": False}, sent


async def auto_resolve(db: Session, encounter_id: int) -> List[law_notify.Notice]:
    """An ignored encounter (user decision 5): auto-surrender when the region has a jail, else a forced fine."""
    enc = law_crud.get_encounter(db, encounter_id)
    if enc is None or enc.status != lc.ENC_PENDING:
        return []
    character_id = int(enc.character_id)
    key = f"law:auto:{encounter_id}"
    if law_crud.region_jail_location(db, enc.region_id) is not None:
        # FEAT-200 (fix 5): only a still-pending encounter (re-checked under the row lock) — a fight chosen
        # in the meantime is never auto-surrendered / auto-fined
        done = await send_to_jail(db, character_id, encounter_id, action=lc.LOG_AUTO_SURRENDER, key=key,
                                  statuses=(lc.ENC_PENDING,))
        if done is None:
            return []
        term, _notices = done
        return [_user_notice(db, character_id, _jail_message(MSG_AUTO_JAIL, term), law_notify.WS_JAILED,
                             term_id=int(term.id))]
    return _forced_fine_commit(db, character_id, encounter_id, key=key, action=lc.LOG_AUTO_FINE,
                               full_message=MSG_AUTO_FINE_FULL, part_message=MSG_AUTO_FINE_PART,
                               statuses=(lc.ENC_PENDING,)) or []
