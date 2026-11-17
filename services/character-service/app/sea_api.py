"""FEAT-213 sea routes — player HTTP API S1–S5 (features/FEAT-213 §3.7, §3.13; crud in ``sea_crud``).
Included from main.py before the main ``/characters`` router (static ``/characters/sea/...`` paths).

* S1 ``GET  /characters/sea/captain/{npc_id}?character_id=`` — the Captain dialogue (presence only);
* S2 ``POST /characters/sea/ships/{ship_id}/tickets`` — buy a ticket (201 ``PassOut``; 402 not enough money);
* S3 ``POST /characters/sea/ships/{ship_id}/sailor`` — hire as a sailor (201 ``PassOut``);
* S4 ``POST /characters/sea/ships/{ship_id}/stowaway`` — try to sneak aboard (201, a neutral message);
* S5 ``GET  /characters/sea/decks/{location_id}?character_id=`` — the deck header.

Auth: JWT + the character's owner on every call. S2 / S3 gate order (caravaneer template): owner + player, the
Captain exists / role / alive / bound to a ship, same location (read transaction closed) → the FEAT-145
``npc_dialogue`` gate over HTTP with NO open DB transaction (fail-closed 503 / 403) → the NPC reputation tier gate →
the write transaction (lock order ship → passes → character). Endpoints that call HTTP are ``async`` (sync crud in
the threadpool); the rest are plain ``def``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import law_notify
import locations_client
import sea_crud
import sea_schemas as schemas
from auth_http import UserRead, get_current_user_via_http
from economy_api import get_db
from economy_crud import EconomyApiError

logger = logging.getLogger("character-service.sea_api")

router = APIRouter(prefix="/characters", tags=["sea"])

MSG_LOAD_FAILED = "Не удалось загрузить данные корабля"
MSG_WRITE_FAILED = "Не удалось выполнить действие с кораблём"


def _read(db: Session, action):
    try:
        return action()
    except EconomyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except SQLAlchemyError:
        logger.exception("sea read failed")
        raise HTTPException(status_code=500, detail=MSG_LOAD_FAILED)
    finally:
        db.rollback()


def _write(db: Session, action):
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
        raise HTTPException(status_code=409, detail=sea_crud.MSG_ALREADY_PASS)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("sea write failed")
        raise HTTPException(status_code=500, detail=MSG_WRITE_FAILED)


async def _captain_context(db: Session, npc_id: int, character_id: int, user: UserRead, *, gated: bool):
    """Presence (S1) or presence + dialogue gate + reputation tier (S2 / S3); the DB transaction is closed before
    the gate's HTTP call."""
    ctx = await run_in_threadpool(_read, db, lambda: sea_crud.resolve_captain(db, npc_id, character_id, user.id))
    if not gated:
        return ctx
    try:
        gate_open = await locations_client.check_npc_gate(character_id, ctx.location_id, npc_id)
    except locations_client.GateUnavailable:
        raise HTTPException(status_code=503, detail=sea_crud.MSG_GATE_UNAVAILABLE)
    if not gate_open:
        raise HTTPException(status_code=403, detail=sea_crud.MSG_GATE_CLOSED)
    await run_in_threadpool(_read, db, lambda: sea_crud.require_npc_tier(db, ctx))
    return ctx


def _pass_response(db: Session, result: "sea_crud.PassResult", what: str, ctx) -> dict:
    law_notify.publish(result.notices)
    logger.info("sea %s: user=%s character=%s ship=%s pass=%s", what, ctx.user_id, ctx.character_id,
                result.ship.id, result.pass_row.id)
    return _read(db, lambda: sea_crud.pass_out(result.pass_row, result.ship))


# ---------------------------------------------------------------------------------------------------- S1

@router.get("/sea/captain/{npc_id}", response_model=schemas.CaptainViewOut)
async def get_captain(
    npc_id: int = Path(..., ge=1),
    character_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    ctx = await _captain_context(db, npc_id, character_id, current_user, gated=False)
    return await run_in_threadpool(_read, db, lambda: sea_crud.captain_view(db, ctx))


# ---------------------------------------------------------------------------------------------------- S2 / S3

@router.post("/sea/ships/{ship_id}/tickets", response_model=schemas.PassOut, status_code=201)
async def post_ticket(
    body: schemas.TicketIn,
    ship_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    ctx = await _captain_context(db, body.npc_id, body.character_id, current_user, gated=True)

    def run():
        result = _write(db, lambda: sea_crud.buy_ticket(db, ctx, ship_id, body.to_trip))
        return _pass_response(db, result, "ticket", ctx)
    return await run_in_threadpool(run)


@router.post("/sea/ships/{ship_id}/sailor", response_model=schemas.PassOut, status_code=201)
async def post_sailor(
    body: schemas.SailorIn,
    ship_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    ctx = await _captain_context(db, body.npc_id, body.character_id, current_user, gated=True)

    def run():
        result = _write(db, lambda: sea_crud.hire_sailor(db, ctx, ship_id))
        return _pass_response(db, result, "sailor", ctx)
    return await run_in_threadpool(run)


# ---------------------------------------------------------------------------------------------------- S4

@router.post("/sea/ships/{ship_id}/stowaway", response_model=schemas.MessageOut, status_code=201)
def post_stowaway(
    body: schemas.StowawayIn,
    ship_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    result = _write(db, lambda: sea_crud.sneak(db, body.character_id, current_user.id, ship_id))
    logger.info("sea stowaway attempt: user=%s character=%s ship=%s pass=%s", current_user.id, body.character_id,
                result.ship.id, result.pass_row.id)
    return {"message": sea_crud.MSG_SNEAK_DONE}


# ---------------------------------------------------------------------------------------------------- S5

@router.get("/sea/decks/{location_id}", response_model=schemas.DeckViewOut)
def get_deck(
    location_id: int = Path(..., ge=1),
    character_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    return _read(db, lambda: sea_crud.deck_view(db, location_id, character_id, current_user.id))
