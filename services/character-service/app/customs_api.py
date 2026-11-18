"""FEAT-216 customs — HTTP API (features/FEAT-216 §3.7; crud in ``customs_crud``). Included from main.py BEFORE the
economy / caravan routers (``/admin/economy/caravans/customs`` must win over FEAT-211's
``/admin/economy/caravans/{caravan_id}``) and before the main ``/characters`` router.

* C1 ``GET  /characters/customs/officer/{npc_id}?character_id=`` — the «Таможенник» window;
* C2 ``POST /characters/customs/officer/{npc_id}/enlist`` — enlist (201 ``{"job": …}``);
* C3 ``POST /characters/customs/resign`` — resign (``{"ok": true}``);
* C4 ``GET  /characters/customs/job?character_id=`` — own job (``{"job": null}`` when none);
* C5 ``POST /characters/caravans/{caravan_id}/inspect`` — the alerted officer's «Досмотреть» (201
  ``{"raid_id", "battle_id"}``; nginx rate limit ``caravan_raid_limit``; one generic 404 for every non-eligibility);
* A1 ``GET  /characters/admin/economy/caravans/customs`` — ``economy:read``;
* A2 ``PUT  /characters/admin/economy/caravans/customs/{country_id}`` — ``economy:settings``.

Auth: JWT + the character's owner on every player call. C1 / C2 gate order (FEAT-212 order): 1–3 owner + player,
customs NPC exists / role / alive, same location, NPC location in a country (``resolve_officer_npc``, read transaction
closed) → 4 the FEAT-145 ``npc_dialogue`` gate over HTTP with NO open DB transaction (fail-closed 503 / 403) → 5 the
NPC reputation tier gate → the view / the enlist transaction. Endpoints that call HTTP are ``async`` (sync crud in the
threadpool); the rest are plain ``def``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import battle_client
import caravan_raid_crud
import customs_crud
import customs_schemas as schemas
import locations_client
from auth_http import UserRead, get_current_user_via_http, require_permission
from economy_api import get_db
from economy_crud import EconomyApiError

logger = logging.getLogger("character-service.customs_api")

router = APIRouter(prefix="/characters", tags=["customs"])

MSG_LOAD_FAILED = "Не удалось загрузить данные таможни"
MSG_WRITE_FAILED = "Не удалось выполнить действие на таможне"


def _read(db: Session, action):
    try:
        return action()
    except EconomyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except SQLAlchemyError:
        logger.exception("customs read failed")
        raise HTTPException(status_code=500, detail=MSG_LOAD_FAILED)
    finally:
        db.rollback()


def _write(db: Session, action, *, integrity_detail: str = MSG_WRITE_FAILED):
    """Run, commit; map business errors / conflicts / DB errors (always rolled back on failure)."""
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
        logger.exception("customs write failed")
        raise HTTPException(status_code=500, detail=MSG_WRITE_FAILED)


async def _officer_context(db: Session, npc_id: int, character_id: int, user: UserRead):
    """Steps 1–5 of C1 / C2; the DB transaction is closed before the gate's HTTP call."""
    ctx = await run_in_threadpool(_read, db, lambda: customs_crud.resolve_officer_npc(
        db, npc_id, character_id, user.id))
    try:
        gate_open = await locations_client.check_npc_gate(character_id, ctx.location_id, npc_id)
    except locations_client.GateUnavailable:
        raise HTTPException(status_code=503, detail=customs_crud.MSG_GATE_UNAVAILABLE)
    if not gate_open:
        raise HTTPException(status_code=403, detail=customs_crud.MSG_GATE_CLOSED)
    await run_in_threadpool(_read, db, lambda: customs_crud.require_npc_tier(db, ctx))
    return ctx


# ---------------------------------------------------------------------------------------------------- C1 / C2

@router.get("/customs/officer/{npc_id}", response_model=schemas.CustomsOfficerViewOut)
async def get_customs_officer(
    npc_id: int = Path(..., ge=1),
    character_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    ctx = await _officer_context(db, npc_id, character_id, current_user)
    return await run_in_threadpool(_read, db, lambda: customs_crud.officer_view(db, ctx))


def _enlist(db: Session, ctx):
    job = _write(db, lambda: customs_crud.enlist(db, ctx), integrity_detail=customs_crud.MSG_ALREADY_OFFICER)
    logger.info("customs officer enlisted: user=%s character=%s npc=%s country=%s", ctx.user_id, ctx.character_id,
                ctx.npc_id, ctx.country_id)
    return {"job": job}


@router.post("/customs/officer/{npc_id}/enlist", response_model=schemas.CustomsJobWrapOut, status_code=201)
async def post_customs_enlist(
    body: schemas.CustomsCharacterIn,
    npc_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    ctx = await _officer_context(db, npc_id, body.character_id, current_user)
    return await run_in_threadpool(_enlist, db, ctx)


# ---------------------------------------------------------------------------------------------------- C3 / C4

@router.post("/customs/resign", response_model=schemas.CustomsResignOut)
def post_customs_resign(
    body: schemas.CustomsCharacterIn,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    def action():
        customs_crud.require_player(db, body.character_id, current_user.id)
        customs_crud.resign(db, body.character_id)
    _write(db, action)
    logger.info("customs officer resigned: user=%s character=%s", current_user.id, body.character_id)
    return {"ok": True}


@router.get("/customs/job", response_model=schemas.CustomsJobWrapOut)
def get_customs_job(
    character_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    def action():
        customs_crud.require_player(db, character_id, current_user.id)
        return {"job": customs_crud.job(db, character_id)}
    return _read(db, action)


# ---------------------------------------------------------------------------------------------------- C5

MSG_BATTLE_UNAVAILABLE = "Сервис боя недоступен — досмотр не начат"
MSG_INSPECT_FAILED = "Не удалось начать досмотр"


def _require_owner(db: Session, character_id: int, user: UserRead) -> None:
    def action():
        customs_crud.require_player(db, character_id, user.id)
    _read(db, action)


def _start_step(db: Session, action):
    try:
        return action()
    except EconomyApiError as exc:
        db.rollback()
        detail = exc.detail
        if exc.status_code == 409 and detail == caravan_raid_crud.MSG_NO_GUARDS:
            detail = customs_crud.MSG_INSPECT_UNAVAILABLE           # «налёт» wording never reaches the officer
        raise HTTPException(status_code=exc.status_code, detail=detail)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("customs inspect start failed")
        raise HTTPException(status_code=500, detail=MSG_INSPECT_FAILED)


@router.post("/caravans/{caravan_id}/inspect", response_model=schemas.CustomsInspectOut, status_code=201)
async def post_caravan_inspect(
    body: schemas.CustomsInspectIn,
    caravan_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """C5: the alerted officer (+ his free squad when ``group``) fights the caravan's guards and escorts. Raid row
    ``kind = customs`` → guards → battle-service ``/battles/internal/customs-fight`` → ``fighting``. Any failure after
    the raid row leaves no trace (guards despawned, row deleted); the alert is not restored (the caravan moves on)."""
    await run_in_threadpool(_require_owner, db, body.character_id, current_user)
    start = await run_in_threadpool(_start_step, db, lambda: customs_crud.begin_inspection(
        db, caravan_id, body.character_id, body.group))
    # spawn_guards cleans up after itself (guards despawned, raid row deleted) before raising
    start = await run_in_threadpool(_start_step, db, lambda: caravan_raid_crud.spawn_guards(db, start.raid_id))
    try:
        created = await battle_client.create_customs_battle(
            start.raid_id, start.caravan_id, start.location_id, leader_character_id=body.character_id,
            group=body.group, guard_character_ids=start.guard_ids, escort_character_ids=start.escort_ids)
    except battle_client.BattleServiceError as exc:
        await run_in_threadpool(caravan_raid_crud.abandon_start, db, start)
        if exc.status_code is not None and 400 <= exc.status_code < 500:
            detail = exc.detail if isinstance(exc.detail, str) and exc.detail else MSG_INSPECT_FAILED
            raise HTTPException(status_code=exc.status_code, detail=detail)
        raise HTTPException(status_code=503, detail=MSG_BATTLE_UNAVAILABLE)
    except Exception:
        logger.exception("customs inspect %s: battle create crashed", start.raid_id)
        await run_in_threadpool(caravan_raid_crud.abandon_start, db, start)
        raise HTTPException(status_code=503, detail=MSG_BATTLE_UNAVAILABLE)
    battle_id = created["battle_id"]
    attackers = created["attacker_character_ids"] or [body.character_id]
    placed = [e for e in (created.get("escort_character_ids") or []) if e in set(start.escort_ids)]
    for attempt in range(2):
        try:
            await run_in_threadpool(lambda: caravan_raid_crud.mark_fighting(
                db, start.raid_id, battle_id, attackers, escort_ids=placed))
            break
        except SQLAlchemyError:
            db.rollback()
            # the battle exists: the caravan pass re-attaches a lost Tx B through battles.caravan_raid_id
            logger.exception("customs inspect %s: Tx B failed (attempt %s)", start.raid_id, attempt + 1)
    logger.info("customs inspect %s: caravan=%s officer=%s group=%s battle=%s attackers=%s guards=%s escorts=%s "
                "user=%s", start.raid_id, caravan_id, body.character_id, body.group, battle_id, attackers,
                list(start.guard_ids), placed, current_user.id)
    return {"raid_id": start.raid_id, "battle_id": battle_id}


# ---------------------------------------------------------------------------------------------------- A1 / A2

@router.get("/admin/economy/caravans/customs", response_model=schemas.CustomsAdminOut)
def get_customs_admin(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read(db, lambda: customs_crud.customs_admin(db))


@router.put("/admin/economy/caravans/customs/{country_id}", response_model=schemas.CustomsCountryOut)
def put_customs_bans(
    body: schemas.CustomsBansIn,
    country_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    out = _write(db, lambda: customs_crud.replace_bans(db, country_id, body.banned_groups))
    logger.info("customs bans replaced: user=%s country=%s groups=%s", current_user.id, country_id,
                out["banned_groups"])
    return out
