"""FEAT-197 region reputation — HTTP API (router included from main.py before the main `/characters` router).

Player (JWT + private access: owner, or admin/moderator with characters:read; no numbers):
    GET  /characters/{character_id}/reputation[?region_id=]
    GET  /characters/{character_id}/reputation/history[?region_id=&page=&page_size=]
Admin (user-service permissions reputation:read / reputation:manage / reputation:settings):
    GET/PUT    /characters/admin/reputation/settings
    GET/POST   /characters/admin/reputation/actions,  PUT/DELETE /characters/admin/reputation/actions/{code}
    GET/PUT    /characters/admin/reputation/npc-roles
    GET        /characters/admin/reputation/characters/{character_id}[/history]
    POST       /characters/admin/reputation/characters/{character_id}/adjust
Internal (X-Internal-Token; nginx answers 403 on /characters/internal/ from outside):
    POST /characters/internal/reputation/apply

Endpoints are plain `def` (sync SQLAlchemy in the threadpool); tier-change notifications are published after the
commit (sync pika, best-effort).
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import database
import reputation_crud
import reputation_notify
import schemas
from auth_http import UserRead, get_current_user_via_http, require_permission, verify_internal_token
from visibility import require_private_access

logger = logging.getLogger("character-service.reputation_api")

router = APIRouter(prefix="/characters", tags=["reputation"])

GENERIC_ERROR = "Не удалось выполнить операцию с репутацией"
READ_ERROR = "Не удалось загрузить репутацию"
DEFAULT_PAGE_SIZE = 20


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
    except reputation_crud.ReputationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("reputation read failed")
        raise HTTPException(status_code=500, detail=READ_ERROR)


def _write(db: Session, action):
    """Run a write, commit; map business errors; a concurrent duplicate (UNIQUE event key) is re-raised as
    IntegrityError for the caller to answer."""
    try:
        result = action()
        db.commit()
        return result
    except reputation_crud.ReputationError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except IntegrityError:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("reputation write failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR)


# ---------------------------------------------------------------------------------------------- admin: settings

@router.get("/admin/reputation/settings", response_model=schemas.ReputationSettingsOut)
def get_settings(db: Session = Depends(get_db),
                 current_user: UserRead = Depends(require_permission("reputation:read"))):
    return _read(db, lambda: reputation_crud.settings_out(db))


@router.put("/admin/reputation/settings", response_model=schemas.ReputationSettingsOut)
def put_settings(body: schemas.ReputationSettingsBody, db: Session = Depends(get_db),
                 current_user: UserRead = Depends(require_permission("reputation:settings"))):
    try:
        result = _write(db, lambda: reputation_crud.update_settings(db, body))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Настройки изменились одновременно, попробуйте ещё раз")
    logger.info("reputation settings updated by user=%s", current_user.id)
    return result


@router.get("/admin/reputation/actions", response_model=List[schemas.ReputationActionOut])
def list_actions(db: Session = Depends(get_db),
                 current_user: UserRead = Depends(require_permission("reputation:read"))):
    return _read(db, lambda: reputation_crud.actions_out(db))


@router.post("/admin/reputation/actions", response_model=schemas.ReputationActionOut, status_code=201)
def create_action(body: schemas.ReputationActionCreate, db: Session = Depends(get_db),
                  current_user: UserRead = Depends(require_permission("reputation:settings"))):
    try:
        return _write(db, lambda: reputation_crud.create_action(db, body))
    except IntegrityError:
        raise HTTPException(status_code=409, detail=reputation_crud.MSG_ACTION_EXISTS)


@router.put("/admin/reputation/actions/{code}", response_model=schemas.ReputationActionOut)
def update_action(code: str, body: schemas.ReputationActionUpdate, db: Session = Depends(get_db),
                  current_user: UserRead = Depends(require_permission("reputation:settings"))):
    try:
        return _write(db, lambda: reputation_crud.update_action(db, code, body))
    except IntegrityError:
        raise HTTPException(status_code=409, detail=GENERIC_ERROR)


@router.delete("/admin/reputation/actions/{code}", status_code=204)
def delete_action(code: str, db: Session = Depends(get_db),
                  current_user: UserRead = Depends(require_permission("reputation:settings"))):
    try:
        _write(db, lambda: reputation_crud.delete_action(db, code))
    except IntegrityError:
        raise HTTPException(status_code=409, detail=GENERIC_ERROR)
    return Response(status_code=204)


@router.get("/admin/reputation/npc-roles", response_model=List[schemas.ReputationRoleWeight])
def get_npc_roles(db: Session = Depends(get_db),
                  current_user: UserRead = Depends(require_permission("reputation:read"))):
    return _read(db, lambda: reputation_crud.roles_out(db))


@router.put("/admin/reputation/npc-roles", response_model=List[schemas.ReputationRoleWeight])
def put_npc_roles(body: List[schemas.ReputationRoleWeight], db: Session = Depends(get_db),
                  current_user: UserRead = Depends(require_permission("reputation:settings"))):
    if len(body) > 200:
        raise HTTPException(status_code=400, detail="Слишком много ролей")
    try:
        return _write(db, lambda: reputation_crud.replace_roles(db, body))
    except IntegrityError:
        raise HTTPException(status_code=409, detail=GENERIC_ERROR)


# ---------------------------------------------------------------------------------------------- admin: characters

@router.get("/admin/reputation/characters/{character_id}", response_model=List[schemas.ReputationAdminRegionOut])
def get_character_admin(character_id: int, db: Session = Depends(get_db),
                        current_user: UserRead = Depends(require_permission("reputation:read"))):
    return _read(db, lambda: reputation_crud.admin_character(db, character_id))


@router.get("/admin/reputation/characters/{character_id}/history",
            response_model=schemas.ReputationAdminHistoryPage)
def get_character_admin_history(
    character_id: int,
    region_id: Optional[int] = Query(None, ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=schemas.REPUTATION_PAGE_MAX),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("reputation:read")),
):
    return _read(db, lambda: reputation_crud.admin_history(db, character_id, region_id, page, page_size))


@router.post("/admin/reputation/characters/{character_id}/adjust", response_model=schemas.ReputationAdjustOut)
def post_adjust(character_id: int, body: schemas.ReputationAdjustIn, db: Session = Depends(get_db),
                current_user: UserRead = Depends(require_permission("reputation:manage"))):
    """Staff edit with a mandatory reason; repeat of the same request_id = duplicate (no second change)."""
    try:
        out, result = _write(db, lambda: reputation_crud.admin_adjust(
            db, character_id, region_id=body.region_id, delta=body.delta, action_code=body.action_code,
            reason=body.reason, echo=body.echo, request_id=str(body.request_id), actor_user_id=current_user.id))
    except IntegrityError:
        return {"changes": [], "duplicate": True}
    logger.info("reputation adjust: user=%s character=%s region=%s delta=%s action=%s duplicate=%s",
                current_user.id, character_id, body.region_id, body.delta, body.action_code, out["duplicate"])
    reputation_notify.publish_tier_changes(result.tier_changes)
    return out


# ---------------------------------------------------------------------------------------------- internal

@router.post("/internal/reputation/apply", response_model=schemas.ReputationApplyOut)
def post_internal_apply(body: schemas.ReputationApplyIn, db: Session = Depends(get_db),
                        _: None = Depends(verify_internal_token)):
    """One automatic reputation event (quest completion in locations-service). Retry-safe by idempotency_key."""
    try:
        result = _write(db, lambda: reputation_crud.apply_reputation(
            db, character_id=body.character_id, region_id=body.region_id, action=body.action,
            idem_key=body.idempotency_key, delta=body.delta, reason=body.reason, echo=body.echo))
    except IntegrityError:
        return {"applied": False, "duplicate": True, "skipped": None}
    reputation_notify.publish_tier_changes(result.tier_changes)
    return {"applied": result.applied, "duplicate": result.duplicate, "skipped": result.skipped}


# ---------------------------------------------------------------------------------------------- player
# Declared last: the static /admin/... and /internal/... paths above win over /{character_id}/....

@router.get("/{character_id}/reputation", response_model=schemas.ReputationView)
def get_reputation(
    character_id: int,
    region_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    require_private_access(db, character_id, current_user)
    return _read(db, lambda: reputation_crud.player_view(db, character_id, region_id))


@router.get("/{character_id}/reputation/history", response_model=schemas.ReputationHistoryPage)
def get_reputation_history(
    character_id: int,
    region_id: Optional[int] = Query(None, ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=schemas.REPUTATION_PAGE_MAX),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    require_private_access(db, character_id, current_user)
    return _read(db, lambda: reputation_crud.player_history(db, character_id, region_id, page, page_size))
