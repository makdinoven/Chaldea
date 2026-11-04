"""FEAT-198 law — HTTP API (contract §3.6; router included from main.py before the main `/characters` router).

Player (JWT):
    GET  /characters/{character_id}/law                                  (private: owner or staff characters:read)
    GET  /characters/{character_id}/law/encounter                        (owner)
    POST /characters/{character_id}/law/encounter/{encounter_id}/choice  (owner)
    GET  /characters/{character_id}/law/jail                             (private)
    POST /characters/{character_id}/law/jail/escape                      (owner)
    POST /characters/{character_id}/law/jail/bail                        (owner, self-bail)
    GET  /characters/law/prisoners                                       (any authenticated user)
    POST /characters/law/bail                                            (payer owned by the user, at a banker)
Admin (user-service permissions, no new ones — user decision 9):
    GET/PUT /characters/admin/law/settings                               (reputation:read / reputation:settings)
    GET     /characters/admin/law/characters/{id}                        (reputation:read)
    POST    /characters/admin/law/characters/{id}/release                (reputation:manage)
    POST    /characters/admin/law/characters/{id}/clear-wanted           (reputation:manage)
Internal (X-Internal-Token; nginx answers 403 on /characters/internal/ from outside):
    POST /characters/internal/law/battle-result

Notifications are published after the commit (sync pika in the threadpool).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import database
import law_crud
import law_flows
import law_notify
import schemas
from auth_http import UserRead, get_current_user_via_http, require_permission, verify_internal_token
from visibility import require_private_access

logger = logging.getLogger("character-service.law_api")

router = APIRouter(prefix="/characters", tags=["law"])

GENERIC_ERROR = "Не удалось выполнить действие"
READ_ERROR = "Не удалось загрузить данные о законе"
CONCURRENT_ERROR = "Действие уже выполняется, попробуйте ещё раз"
DEFAULT_PAGE_SIZE = 20


def get_db():
    # database.SessionLocal is read at call time so the test suite's patched factory is used.
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _require_owner(db: Session, character_id: int, user: UserRead) -> None:
    """404 for a missing character, 403 for anyone but the owner."""
    owner = db.execute(text("SELECT user_id FROM characters WHERE id = :cid"),
                       {"cid": int(character_id)}).first()
    if owner is None:
        raise HTTPException(status_code=404, detail=law_crud.MSG_CHARACTER_NOT_FOUND)
    if owner[0] is None or int(owner[0]) != int(user.id):
        raise HTTPException(status_code=403, detail=law_crud.MSG_NOT_OWNER)


def _read(db: Session, action):
    try:
        return action()
    except law_crud.LawError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("law read failed")
        raise HTTPException(status_code=500, detail=READ_ERROR)


def _write(db: Session, action):
    """Run a sync write and commit; business errors keep their status, a concurrent duplicate is a 409."""
    try:
        result = action()
        db.commit()
        return result
    except law_crud.LawError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=CONCURRENT_ERROR)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("law write failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR)


async def _flow(db: Session, coro):
    """Await a ``law_flows`` coroutine; map its errors like :func:`_write` (HTTPException passes through)."""
    try:
        return await coro
    except law_crud.LawError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=CONCURRENT_ERROR)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("law flow failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR)


async def _publish(notices) -> None:
    if notices:
        await run_in_threadpool(law_notify.publish, notices)


# ---------------------------------------------------------------------------------------------- static paths first
# (declared before /{character_id}/law… so /law/... and /admin/... never match the character id)

@router.get("/law/prisoners", response_model=schemas.LawPrisonersPage)
def get_prisoners(
    q: Optional[str] = Query(None, max_length=schemas.LAW_QUERY_MAX),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=schemas.LAW_PAGE_MAX),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    return _read(db, lambda: law_crud.prisoners(db, q, page, page_size))


@router.post("/law/bail", response_model=schemas.LawBailOut)
async def post_bail(body: schemas.LawBailIn, db: Session = Depends(get_db),
                    current_user: UserRead = Depends(get_current_user_via_http)):
    result = _write(db, lambda: law_crud.bail_other(
        db, user_id=current_user.id, payer_id=body.payer_character_id, banker_id=body.banker_npc_id,
        prisoner_id=body.prisoner_character_id, request_id=str(body.request_id)))
    message = f"Залог за «{result.prisoner_name}» внесён — узник свободен"
    if not result.duplicate:
        logger.info("law bail: payer=%s prisoner=%s paid=%s user=%s", body.payer_character_id, result.prisoner_id,
                    result.paid, current_user.id)
        await _publish([law_notify.Notice(
            result.prisoner_user_id, f"За вас внесли залог: {result.payer_name}. Вы свободны",
            law_notify.WS_RELEASED, data={"character_id": result.prisoner_id})])
    return {"message": message, "paid": result.paid}


@router.get("/admin/law/settings", response_model=schemas.LawSettingsOut)
def get_settings(db: Session = Depends(get_db),
                 current_user: UserRead = Depends(require_permission("reputation:read"))):
    return _read(db, lambda: law_crud.settings_out(db))


@router.put("/admin/law/settings", response_model=schemas.LawSettingsOut)
def put_settings(body: schemas.LawSettingsBody, db: Session = Depends(get_db),
                 current_user: UserRead = Depends(require_permission("reputation:settings"))):
    result = _write(db, lambda: law_crud.update_settings(db, body))
    logger.info("law settings updated by user=%s", current_user.id)
    return result


@router.get("/admin/law/characters/{character_id}", response_model=schemas.LawAdminCharacterOut)
def get_character_admin(character_id: int, db: Session = Depends(get_db),
                        current_user: UserRead = Depends(require_permission("reputation:read"))):
    return _read(db, lambda: law_crud.admin_character(db, character_id))


@router.post("/admin/law/characters/{character_id}/release", response_model=schemas.LawStaffReleaseOut)
async def post_release(character_id: int, body: schemas.LawStaffReleaseIn, db: Session = Depends(get_db),
                       current_user: UserRead = Depends(require_permission("reputation:manage"))):
    released, cancelled, duplicate = _write(db, lambda: law_crud.staff_release(
        db, character_id, reason=body.reason, request_id=str(body.request_id), actor_user_id=current_user.id))
    if not duplicate:
        logger.info("law staff release: character=%s released=%s cancelled=%s by user=%s", character_id, released,
                    cancelled, current_user.id)
        user_id = law_crud.character_user_ids(db, [character_id]).get(int(character_id))
        await _publish([law_notify.Notice(user_id, "Решением властей вы освобождены", law_notify.WS_RELEASED,
                                          data={"character_id": int(character_id)})])
    parts = []
    if released:
        parts.append("освобождён из тюрьмы")
    if cancelled:
        parts.append("отпущен стражей")
    message = ("Персонаж " + " и ".join(parts)) if parts else "Решение уже выполнено"
    return {"message": message, "released": released, "cancelled": cancelled, "duplicate": duplicate}


@router.post("/admin/law/characters/{character_id}/clear-wanted", response_model=schemas.LawStaffClearOut)
def post_clear_wanted(character_id: int, body: schemas.LawStaffClearIn, db: Session = Depends(get_db),
                      current_user: UserRead = Depends(require_permission("reputation:manage"))):
    cleared, duplicate = _write(db, lambda: law_crud.staff_clear_wanted(
        db, character_id, region_id=body.region_id, reason=body.reason, request_id=str(body.request_id),
        actor_user_id=current_user.id))
    if not duplicate:
        logger.info("law staff clear: character=%s regions=%s by user=%s", character_id, cleared, current_user.id)
    message = "Розыск снят" if cleared else ("Решение уже выполнено" if duplicate else "Розыска нет")
    return {"message": message, "cleared_region_ids": cleared, "duplicate": duplicate}


@router.post("/internal/law/battle-result", response_model=schemas.LawBattleResultOut)
async def post_battle_result(body: schemas.LawBattleResultIn, db: Session = Depends(get_db),
                             _: None = Depends(verify_internal_token)):
    """The guard battle ended (battle-service callback). Idempotent; 404 unknown encounter, 409 another battle."""
    out, notices = await _flow(db, law_flows.battle_result(
        db, battle_id=body.battle_id, encounter_id=body.law_encounter_id, winner_team=body.winner_team,
        aborted=body.aborted))
    await _publish(notices)
    return out


# ---------------------------------------------------------------------------------------------- player

@router.get("/{character_id}/law", response_model=schemas.LawStateOut)
def get_law(character_id: int, db: Session = Depends(get_db),
            current_user: UserRead = Depends(get_current_user_via_http)):
    require_private_access(db, character_id, current_user)
    return _read(db, lambda: law_crud.player_state(db, character_id))


@router.get("/{character_id}/law/encounter", response_model=schemas.LawEncounterWrap)
def get_encounter(character_id: int, db: Session = Depends(get_db),
                  current_user: UserRead = Depends(get_current_user_via_http)):
    _require_owner(db, character_id, current_user)
    return {"encounter": _read(db, lambda: law_crud.player_encounter(db, character_id))}


@router.post("/{character_id}/law/encounter/{encounter_id}/choice", response_model=schemas.LawChoiceOut)
async def post_choice(character_id: int, encounter_id: int, body: schemas.LawChoiceIn,
                      db: Session = Depends(get_db),
                      current_user: UserRead = Depends(get_current_user_via_http)):
    _require_owner(db, character_id, current_user)
    out, notices = await _flow(db, law_flows.choose(db, character_id, encounter_id, body.choice,
                                                    str(body.request_id)))
    logger.info("law choice: character=%s encounter=%s choice=%s result=%s", character_id, encounter_id,
                body.choice, out.get("result"))
    await _publish(notices)
    return out


@router.get("/{character_id}/law/jail", response_model=schemas.LawJailWrap)
def get_jail(character_id: int, db: Session = Depends(get_db),
             current_user: UserRead = Depends(get_current_user_via_http)):
    require_private_access(db, character_id, current_user)
    return {"jail": _read(db, lambda: law_crud.player_jail(db, character_id))}


@router.post("/{character_id}/law/jail/escape", response_model=schemas.LawEscapeOut)
async def post_escape(character_id: int, body: schemas.LawRequestIn, db: Session = Depends(get_db),
                      current_user: UserRead = Depends(get_current_user_via_http)):
    _require_owner(db, character_id, current_user)
    success, message, _term = _write(db, lambda: law_crud.escape(db, character_id, str(body.request_id)))
    logger.info("law escape: character=%s success=%s", character_id, success)
    jail = _read(db, lambda: law_crud.player_jail(db, character_id))
    if success:
        user_id = law_crud.character_user_ids(db, [character_id]).get(int(character_id))
        await _publish([law_notify.Notice(user_id, message, law_notify.WS_RELEASED,
                                          data={"character_id": int(character_id)})])
    return {"success": success, "message": message, "jail": jail}


@router.post("/{character_id}/law/jail/bail", response_model=schemas.LawSelfBailOut)
def post_self_bail(character_id: int, body: schemas.LawRequestIn, db: Session = Depends(get_db),
                   current_user: UserRead = Depends(get_current_user_via_http)):
    _require_owner(db, character_id, current_user)
    paid, _term, duplicate = _write(db, lambda: law_crud.self_bail(db, character_id, str(body.request_id)))
    if not duplicate:
        logger.info("law self-bail: character=%s paid=%s", character_id, paid)
    return {"message": "Залог внесён — вы свободны", "jail": None}
