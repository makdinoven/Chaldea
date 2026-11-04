"""FEAT-199 the shadow + renown — HTTP API (contract §3.7; router included from main.py before the main router).

Public / player:
    GET  /characters/renown/fame-tiers                           (no auth: names only, for editors and legends)
    GET  /characters/{character_id}/renown                       (private: owner or staff characters:read; no numbers)
Admin (no new permissions — reputation:read / manage / settings):
    GET/PUT /characters/admin/shadow/settings                    (reputation:read / reputation:settings)
    GET     /characters/admin/shadow/crimes                      (reputation:read)
    POST    /characters/admin/shadow/crimes/{id}/reveal          (reputation:manage)
    POST    /characters/admin/shadow/crimes/{id}/close           (reputation:manage)
    GET     /characters/admin/shadow/regions/suspicion           (reputation:read)
    POST    /characters/admin/shadow/characters/{id}/renown-adjust (reputation:manage)
Internal (X-Internal-Token; nginx answers 403 on /characters/internal/ from outside):
    POST /characters/internal/fame/apply                         (quest completion in locations-service)

Notifications are published after the commit (sync pika in the threadpool).
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import database
import law_crud
import renown_crud
import schemas
import shadow_core as sc
import shadow_crud
from auth_http import UserRead, get_current_user_via_http, require_permission, verify_internal_token
from visibility import require_private_access

logger = logging.getLogger("character-service.shadow_api")

router = APIRouter(prefix="/characters", tags=["shadow"])

GENERIC_ERROR = "Не удалось выполнить действие"
READ_ERROR = "Не удалось загрузить данные"
CONCURRENT_ERROR = "Действие уже выполняется, попробуйте ещё раз"
MSG_REVEALED = "Преступление раскрыто"
MSG_CLOSED = "Дело закрыто"


def get_db():
    # database.SessionLocal is read at call time so the test suite's patched factory is used.
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _read(db: Session, action):
    try:
        return action()
    except law_crud.LawError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("shadow read failed")
        raise HTTPException(status_code=500, detail=READ_ERROR)


def _write(db: Session, action):
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
        logger.exception("shadow write failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR)


# ---------------------------------------------------------------------------------------------- static paths first

@router.get("/renown/fame-tiers", response_model=List[schemas.FameTierPublicOut])
def get_fame_tiers(db: Session = Depends(get_db)):
    return _read(db, lambda: renown_crud.fame_tiers_public(db))


@router.get("/admin/shadow/settings", response_model=schemas.ShadowSettingsOut)
def get_settings(db: Session = Depends(get_db),
                 current_user: UserRead = Depends(require_permission("reputation:read"))):
    return _read(db, lambda: shadow_crud.settings_out(db))


@router.put("/admin/shadow/settings", response_model=schemas.ShadowSettingsOut)
def put_settings(body: schemas.ShadowSettingsBody, db: Session = Depends(get_db),
                 current_user: UserRead = Depends(require_permission("reputation:settings"))):
    result = _write(db, lambda: shadow_crud.update_settings(db, body))
    logger.info("shadow settings updated by user=%s", current_user.id)
    return result


@router.get("/admin/shadow/crimes", response_model=schemas.ShadowCrimesPage)
def get_crimes(
    status: str = Query(shadow_crud.STATUS_FILTER_OPEN),
    region_id: Optional[int] = Query(None, ge=1),
    character_id: Optional[int] = Query(None, ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=schemas.SHADOW_PAGE_MAX),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("reputation:read")),
):
    if status not in shadow_crud.STATUS_FILTERS:
        raise HTTPException(status_code=422, detail="Неизвестный статус дела")
    return _read(db, lambda: shadow_crud.admin_crimes(db, status=status, region_id=region_id,
                                                      character_id=character_id, page=page, page_size=page_size))


@router.post("/admin/shadow/crimes/{crime_id}/reveal", response_model=schemas.ShadowCrimeActionOut)
async def post_reveal(crime_id: int, body: schemas.ShadowStaffIn, db: Session = Depends(get_db),
                      current_user: UserRead = Depends(require_permission("reputation:manage"))):
    result = _write(db, lambda: shadow_crud.staff_reveal(db, crime_id, reason=body.reason,
                                                         actor_user_id=current_user.id))
    logger.info("shadow staff reveal: crime=%s by user=%s request=%s", crime_id, current_user.id, body.request_id)
    await run_in_threadpool(result.publish)
    return {"message": MSG_REVEALED, "crime": _read(db, lambda: shadow_crud.crime_detail(db, crime_id))}


@router.post("/admin/shadow/crimes/{crime_id}/close", response_model=schemas.ShadowCrimeActionOut)
def post_close(crime_id: int, body: schemas.ShadowStaffIn, db: Session = Depends(get_db),
               current_user: UserRead = Depends(require_permission("reputation:manage"))):
    _write(db, lambda: shadow_crud.staff_close(db, crime_id, reason=body.reason, actor_user_id=current_user.id))
    logger.info("shadow staff close: crime=%s by user=%s request=%s", crime_id, current_user.id, body.request_id)
    return {"message": MSG_CLOSED, "crime": _read(db, lambda: shadow_crud.crime_detail(db, crime_id))}


@router.get("/admin/shadow/regions/suspicion", response_model=List[schemas.RegionSuspicionOut])
def get_regions_suspicion(db: Session = Depends(get_db),
                          current_user: UserRead = Depends(require_permission("reputation:read"))):
    return _read(db, lambda: shadow_crud.regions_suspicion(db))


@router.post("/admin/shadow/characters/{character_id}/renown-adjust", response_model=schemas.RenownAdjustOut)
async def post_renown_adjust(character_id: int, body: schemas.RenownAdjustIn, db: Session = Depends(get_db),
                             current_user: UserRead = Depends(require_permission("reputation:manage"))):
    out = _write(db, lambda: shadow_crud.staff_renown_adjust(
        db, character_id, scale=body.scale, delta=body.delta, reason=body.reason, request_id=str(body.request_id),
        actor_user_id=current_user.id))
    change = out.pop("change", None)
    if not out["duplicate"]:
        logger.info("renown adjust: character=%s scale=%s delta=%s by user=%s", character_id, body.scale,
                    body.delta, current_user.id)
        if change is not None:
            await run_in_threadpool(renown_crud.publish_fame_changes, [change])
    return out


@router.post("/internal/fame/apply", response_model=schemas.FameApplyOut)
async def post_internal_fame(body: schemas.FameApplyIn, db: Session = Depends(get_db),
                             _: None = Depends(verify_internal_token)):
    """Fame of a completed quest (locations-service, after its commit). Retry-safe by ``idempotency_key``."""
    if db.execute(text("SELECT 1 FROM characters WHERE id = :c"), {"c": body.character_id}).first() is None:
        raise HTTPException(status_code=404, detail=law_crud.MSG_CHARACTER_NOT_FOUND)

    def action():
        points = body.points
        if points is None:
            points = renown_crud.load_shadow_settings(db).fame_quest_default
        return renown_crud.add_fame(db, character_id=body.character_id, points=int(points), source=sc.SOURCE_QUEST,
                                    event_key=body.idempotency_key, ref_id=body.ref_id)

    try:
        result = _write(db, action)
    except HTTPException as exc:
        if exc.status_code == 409:                  # concurrent duplicate on the UNIQUE key
            return {"applied": False, "duplicate": True, "tier_changed": False}
        raise
    if result.change is not None:
        await run_in_threadpool(renown_crud.publish_fame_changes, [result.change])
    applied = not result.duplicate and not result.skipped
    return {"applied": applied, "duplicate": result.duplicate, "tier_changed": result.change is not None}


# ---------------------------------------------------------------------------------------------- player
# Declared last: the static /admin/... and /internal/... paths above win over /{character_id}/....

@router.get("/{character_id}/renown", response_model=schemas.RenownPlayerOut)
def get_renown(character_id: int, db: Session = Depends(get_db),
               current_user: UserRead = Depends(get_current_user_via_http)):
    require_private_access(db, character_id, current_user)
    return _read(db, lambda: renown_crud.player_renown(db, character_id))
