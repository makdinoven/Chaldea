"""FEAT-211 physical caravans — HTTP API (router included from main.py after the economy router, before the main
``/characters`` router).

Admin (contract 3.13): A5 caravan detail, A6 roads / trade gates, A7 gate override, A8/A9 guard template pool;
reads need ``economy:read``, writes ``economy:settings``. The extended caravan list (A4) stays in ``economy_api``.
Player (JWT + owner; FEAT-211 task 3): A1 ``GET /characters/caravans/here`` (caravans in the character's own
location — never from / to / route / value), A2 ``POST /characters/caravans/{caravan_id}/raid`` (nginx rate limit
``caravan_raid_limit``), ``GET /characters/caravans/raids/by-battle/{battle_id}`` (own loot, victory window).
Internal (X-Internal-Token): A3 ``POST /characters/internal/caravans/raid-result``
(battle-service callback with FEAT-212 ``fallen_character_ids``; the caravan pass polls lost ones). Business logic:
``caravan_raid_crud``. FEAT-212: the raid start sends the caravan's player escorts to battle-service (B1) and stores
the ones it placed.

Endpoints are plain ``def`` (sync SQLAlchemy runs in the threadpool). Route order inside this router: the static
``/roads`` and ``/guards`` paths are declared before ``/{caravan_id}``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import battle_client
import caravan_raid_crud
import econ_core as core
import economy_caravan_crud
import law_crud
import schemas
from auth_http import UserRead, get_current_user_via_http, require_permission, verify_internal_token
from economy_api import _read, _read_or_error, _run_write, get_db
from economy_crud import EconomyApiError

logger = logging.getLogger("character-service.caravan_api")

router = APIRouter(prefix="/characters", tags=["caravans"])

MSG_RAID_FAILED = "Не удалось начать налёт"
MSG_RAID_REFUSED = "Налёт невозможен"
MSG_BATTLE_UNAVAILABLE = "Сервис боя недоступен — налёт не начат"
MSG_SETTLE_FAILED = "Не удалось подвести итог налёта"


# ---------------------------------------------------------------------------
# Admin: roads / trade gates (A6, A7)
# ---------------------------------------------------------------------------

@router.get("/admin/economy/caravans/roads", response_model=schemas.CaravanRoadsOut)
def get_caravan_roads(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read(db, lambda: economy_caravan_crud.roads(db))


@router.put("/admin/economy/caravans/gates/{region_id}", response_model=schemas.CaravanGateRegionOut)
def put_caravan_gate(
    body: schemas.CaravanGateIn,
    region_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    result = _run_write(db, lambda: economy_caravan_crud.set_gate(db, region_id, body.location_id))
    logger.info("caravan trade gate: user=%s region=%s location=%s", current_user.id, region_id, body.location_id)
    return result


# ---------------------------------------------------------------------------
# Admin: guard template pool (A8, A9)
# ---------------------------------------------------------------------------

@router.get("/admin/economy/caravans/guards", response_model=schemas.CaravanGuardPoolOut)
def get_caravan_guards(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read(db, lambda: economy_caravan_crud.guard_pool(db))


@router.put("/admin/economy/caravans/guards", response_model=schemas.CaravanGuardPoolOut)
def put_caravan_guards(
    body: schemas.CaravanGuardPoolIn,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    result = _run_write(db, lambda: economy_caravan_crud.set_guard_pool(db, body.mob_template_ids))
    logger.info("caravan guard pool: user=%s templates=%s", current_user.id, body.mob_template_ids)
    return result


# ---------------------------------------------------------------------------
# Admin: one caravan (A5) — declared after the static paths above
# ---------------------------------------------------------------------------

@router.get("/admin/economy/caravans/{caravan_id}", response_model=schemas.CaravanDetailOut)
def get_caravan_detail(
    caravan_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read_or_error(db, lambda: economy_caravan_crud.caravan_detail(db, caravan_id))


# ---------------------------------------------------------------------------
# Player: caravans here (A1), raid (A2) — JWT + owner; the location is the character's own
# ---------------------------------------------------------------------------

def _require_owner(db: Session, character_id: int, user: UserRead) -> None:
    """404 for a missing character, 403 for anyone but the owner (law_api pattern)."""
    owner = db.execute(text("SELECT user_id FROM characters WHERE id = :cid"), {"cid": int(character_id)}).first()
    db.rollback()
    if owner is None:
        raise HTTPException(status_code=404, detail=law_crud.MSG_CHARACTER_NOT_FOUND)
    if owner[0] is None or int(owner[0]) != int(user.id):
        raise HTTPException(status_code=403, detail=law_crud.MSG_NOT_OWNER)


@router.get("/caravans/here", response_model=schemas.CaravansHereOut)
def get_caravans_here(
    character_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    _require_owner(db, character_id, current_user)
    return _read_or_error(db, lambda: caravan_raid_crud.caravans_here(db, character_id))


@router.get("/caravans/raids/by-battle/{battle_id}", response_model=schemas.CaravanRaidShareOut)
def get_caravan_raid_share(
    battle_id: int = Path(..., ge=1),
    character_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """The character's own loot of the raid fought in this battle (``raid = False`` for any other battle)."""
    _require_owner(db, character_id, current_user)
    return _read_or_error(db, lambda: caravan_raid_crud.raid_share_by_battle(db, battle_id, character_id))


def _start_step(db: Session, action):
    try:
        return action()
    except EconomyApiError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("caravan raid start failed")
        raise HTTPException(status_code=500, detail=MSG_RAID_FAILED)


@router.post("/caravans/{caravan_id}/raid", response_model=schemas.CaravanRaidStartOut, status_code=201)
async def post_caravan_raid(
    body: schemas.CaravanRaidIn,
    caravan_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """A2 (3.6): raid row → guards → battle-service fight → ``fighting``. Any failure after the raid row leaves no
    trace (guards despawned, row deleted); battle-service down → 503."""
    await run_in_threadpool(_require_owner, db, body.character_id, current_user)
    start = await run_in_threadpool(_start_step, db, lambda: caravan_raid_crud.begin_raid(
        db, caravan_id, body.character_id, body.group))
    # spawn_guards cleans up after itself (guards despawned, raid row deleted) before raising
    start = await run_in_threadpool(_start_step, db, lambda: caravan_raid_crud.spawn_guards(db, start.raid_id))
    # escorts only when there are any: a raid without escorts sends exactly the FEAT-211 call
    extra = {"escort_character_ids": list(start.escort_ids)} if start.escort_ids else {}
    try:
        created = await battle_client.create_caravan_raid_battle(
            start.raid_id, start.caravan_id, body.character_id, body.group, start.guard_ids, start.location_id,
            **extra)
    except battle_client.BattleServiceError as exc:
        await run_in_threadpool(caravan_raid_crud.abandon_start, db, start)
        if exc.status_code is not None and 400 <= exc.status_code < 500:
            detail = exc.detail if isinstance(exc.detail, str) and exc.detail else MSG_RAID_REFUSED
            raise HTTPException(status_code=exc.status_code, detail=detail)
        raise HTTPException(status_code=503, detail=MSG_BATTLE_UNAVAILABLE)
    except Exception:
        logger.exception("caravan raid %s: battle create crashed", start.raid_id)
        await run_in_threadpool(caravan_raid_crud.abandon_start, db, start)
        raise HTTPException(status_code=503, detail=MSG_BATTLE_UNAVAILABLE)
    battle_id = created["battle_id"]
    attackers = created["attacker_character_ids"] or [body.character_id]
    # the escorts battle-service placed (an old battle-service answers none → they stay out of the fight)
    placed = [e for e in (created.get("escort_character_ids") or []) if e in set(start.escort_ids)]
    for attempt in range(2):
        try:
            await run_in_threadpool(lambda: caravan_raid_crud.mark_fighting(
                db, start.raid_id, battle_id, attackers, escort_ids=placed))
            break
        except SQLAlchemyError:
            db.rollback()
            # the battle exists: the caravan pass re-attaches a lost Tx B through battles.caravan_raid_id
            logger.exception("caravan raid %s: Tx B failed (attempt %s)", start.raid_id, attempt + 1)
    logger.info("caravan raid %s: caravan=%s leader=%s group=%s battle=%s attackers=%s guards=%s escorts=%s user=%s",
                start.raid_id, caravan_id, body.character_id, body.group, battle_id, attackers,
                list(start.guard_ids), placed, current_user.id)
    return {"raid_id": start.raid_id, "battle_id": battle_id}


# ---------------------------------------------------------------------------
# Internal: battle-service callback (A3) — X-Internal-Token (nginx answers 403 on /characters/internal/ outside)
# ---------------------------------------------------------------------------

@router.post("/internal/caravans/raid-result", response_model=schemas.CaravanRaidResultOut)
def post_caravan_raid_result(
    body: schemas.CaravanRaidResultIn,
    db: Session = Depends(get_db),
    _: None = Depends(verify_internal_token),
):
    """The raid fight ended (or was force-finished). Idempotent; an unknown raid answers ``unknown``."""
    try:
        status = caravan_raid_crud.battle_result(db, battle_id=body.battle_id, raid_id=body.caravan_raid_id,
                                                 winner_team=body.winner_team, aborted=body.aborted,
                                                 fallen_character_ids=body.fallen_character_ids)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("caravan raid %s: settlement failed (the caravan pass polls it)", body.caravan_raid_id)
        raise HTTPException(status_code=500, detail=MSG_SETTLE_FAILED)
    except core.EconomyError:
        db.rollback()
        logger.exception("caravan raid %s: payout rejected by the ledger", body.caravan_raid_id)
        raise HTTPException(status_code=500, detail=MSG_SETTLE_FAILED)
    return {"status": status}
