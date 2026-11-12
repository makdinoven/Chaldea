"""FEAT-212 player caravan escorts — HTTP API C1–C6 (features/FEAT-212 §3.7, §3.8, §3.12; crud in
``caravan_escort_crud``). Included from main.py after the caravan router, before the main ``/characters`` router.

* C1 ``GET  /characters/caravans/caravaneer/{npc_id}?character_id=`` — caravans preparing at the caravaneer's gate;
* C2 ``POST /characters/caravans/{caravan_id}/escort/hire`` — hire (201, the C3 job body);
* C3 ``GET  /characters/caravans/escort?character_id=`` — own job (``{"escort": null}`` when none);
* C4 ``POST /characters/caravans/escort/leave`` — «Сойти»;
* C5 ``GET  /characters/caravans/escort/messages?character_id=&after_id=`` — the caravan channel;
* C6 ``POST /characters/caravans/escort/messages`` — write to it (201; 3 s throttle per character).

Auth: JWT + the character's owner on every call. C1 / C2 gate order (banker / guild order): 1–3 owner + player,
caravaneer exists / role / alive, same location (``resolve_caravaneer``, read transaction closed) → 4 the FEAT-145
``npc_dialogue`` gate over HTTP with NO open DB transaction (fail-closed 503 / 403) → 5 the NPC reputation tier gate
→ the view / the hire transaction. Endpoints that call HTTP are ``async`` (sync crud in the threadpool); the rest are
plain ``def``. Static ``/caravans/escort...`` paths do not collide with FEAT-211's ``/caravans/{caravan_id}/raid``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import caravan_escort_crud as escort_crud
import caravan_escort_schemas as schemas
import law_notify
import locations_client
from auth_http import UserRead, get_current_user_via_http
from economy_api import get_db
from economy_crud import EconomyApiError

logger = logging.getLogger("character-service.caravan_escort_api")

router = APIRouter(prefix="/characters", tags=["caravan-escorts"])

MSG_LOAD_FAILED = "Не удалось загрузить данные охраны каравана"
MSG_WRITE_FAILED = "Не удалось выполнить действие с охраной каравана"


def _read(db: Session, action):
    try:
        return action()
    except EconomyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except SQLAlchemyError:
        logger.exception("caravan escort read failed")
        raise HTTPException(status_code=500, detail=MSG_LOAD_FAILED)
    finally:
        db.rollback()


def _write(db: Session, action, *, integrity_detail: str = MSG_WRITE_FAILED):
    """Run, commit; map business errors / conflicts / DB errors (always rolled back)."""
    try:
        result = action()
        db.commit()
        return result
    except EconomyApiError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=integrity_detail)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("caravan escort write failed")
        raise HTTPException(status_code=500, detail=MSG_WRITE_FAILED)


async def _caravaneer_context(db: Session, npc_id: int, character_id: int, user: UserRead):
    """Steps 1–5 of C1 / C2; the DB transaction is closed before the gate's HTTP call."""
    ctx = await run_in_threadpool(_read, db, lambda: escort_crud.resolve_caravaneer(
        db, npc_id, character_id, user.id))
    try:
        gate_open = await locations_client.check_npc_gate(character_id, ctx.location_id, npc_id)
    except locations_client.GateUnavailable:
        raise HTTPException(status_code=503, detail=escort_crud.MSG_GATE_UNAVAILABLE)
    if not gate_open:
        raise HTTPException(status_code=403, detail=escort_crud.MSG_GATE_CLOSED)
    await run_in_threadpool(_read, db, lambda: escort_crud.require_npc_tier(db, ctx))
    return ctx


# ---------------------------------------------------------------------------------------------------- C1 / C2

@router.get("/caravans/caravaneer/{npc_id}", response_model=schemas.CaravaneerViewOut)
async def get_caravaneer(
    npc_id: int = Path(..., ge=1),
    character_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    ctx = await _caravaneer_context(db, npc_id, character_id, current_user)
    return await run_in_threadpool(_read, db, lambda: escort_crud.caravaneer_view(db, ctx))


def _hire(db: Session, ctx, caravan_id: int):
    result = _write(db, lambda: escort_crud.hire(db, ctx, caravan_id), integrity_detail=escort_crud.MSG_NO_REJOIN)
    law_notify.publish([result.notice])
    logger.info("caravan escort hired: user=%s character=%s caravan=%s npc=%s", ctx.user_id, ctx.character_id,
                caravan_id, ctx.npc_id)
    return {"escort": _read(db, lambda: escort_crud.escort_job(db, ctx.character_id))}


@router.post("/caravans/{caravan_id}/escort/hire", response_model=schemas.EscortJobOut, status_code=201)
async def post_escort_hire(
    body: schemas.EscortHireIn,
    caravan_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    ctx = await _caravaneer_context(db, body.npc_id, body.character_id, current_user)
    out = await run_in_threadpool(_hire, db, ctx, caravan_id)
    if out["escort"] is None:                      # released in between (admin teleport) — practically never
        raise HTTPException(status_code=409, detail=escort_crud.MSG_NOT_ESCORT)
    return out["escort"]


# ---------------------------------------------------------------------------------------------------- C3 / C4

@router.get("/caravans/escort", response_model=schemas.EscortJobWrapOut)
def get_escort_job(
    character_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    def action():
        escort_crud.require_owner(db, character_id, current_user.id)
        return {"escort": escort_crud.escort_job(db, character_id)}
    return _read(db, action)


@router.post("/caravans/escort/leave", response_model=schemas.EscortLeaveOut)
def post_escort_leave(
    body: schemas.EscortCharacterIn,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    def action():
        escort_crud.require_owner(db, body.character_id, current_user.id)
        return escort_crud.leave(db, body.character_id)
    result = _write(db, action)
    law_notify.publish([result.notice])
    logger.info("caravan escort left: user=%s character=%s", current_user.id, body.character_id)
    return {"left": True, "location_id": result.location_id}


# ---------------------------------------------------------------------------------------------------- C5 / C6

@router.get("/caravans/escort/messages", response_model=schemas.EscortMessagesOut)
def get_escort_messages(
    character_id: int = Query(..., ge=1),
    after_id: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    def action():
        escort_crud.require_owner(db, character_id, current_user.id)
        return escort_crud.messages(db, character_id, after_id)
    return _read(db, action)


@router.post("/caravans/escort/messages", response_model=schemas.EscortMessageOut, status_code=201)
def post_escort_message(
    body: schemas.EscortMessageIn,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    def action():
        escort_crud.require_owner(db, body.character_id, current_user.id)
        return escort_crud.post_message(db, body.character_id, body.text)
    return _write(db, action)
