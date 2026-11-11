"""FEAT-211 3.13 A11/A12 — fence («Скупщик») settings, admin HTTP API (router included from main.py before the main
`/characters` router).

    GET /characters/admin/npcs/{npc_id}/fence   (npcs:read)    -> FenceSettingsOut (defaults without a row)
    PUT /characters/admin/npcs/{npc_id}/fence   (npcs:update)  -> FenceSettingsOut

Existing permissions only (no RBAC migration). Errors are Russian: 404 «НПС не найден», 409 «Настройки скупки
доступны только скупщику» (saved role ≠ fence), 400 for bad values / unknown goods groups.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import database
import fence_crud
import fence_schemas
from auth_http import UserRead, require_permission

logger = logging.getLogger("character-service.fence_api")

router = APIRouter(prefix="/characters", tags=["fences"])

READ_ERROR = "Не удалось загрузить настройки скупщика"
WRITE_ERROR = "Не удалось сохранить настройки скупщика"
CONCURRENT_ERROR = "Настройки скупщика сейчас меняются, попробуйте ещё раз"


def get_db():
    # database.SessionLocal is read at call time so the test suite's patched factory is used.
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/admin/npcs/{npc_id}/fence", response_model=fence_schemas.FenceSettingsOut)
def get_fence(npc_id: int, db: Session = Depends(get_db),
              current_user: UserRead = Depends(require_permission("npcs:read"))):
    try:
        return fence_crud.fence_out(db, npc_id)
    except fence_crud.FenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("fence read of npc %s failed", npc_id)
        raise HTTPException(status_code=500, detail=READ_ERROR)


@router.put("/admin/npcs/{npc_id}/fence", response_model=fence_schemas.FenceSettingsOut)
def put_fence(npc_id: int, body: fence_schemas.FenceSettingsIn, db: Session = Depends(get_db),
              current_user: UserRead = Depends(require_permission("npcs:update"))):
    try:
        fence_crud.save_fence(db, npc_id, body, user_id=current_user.id)
        db.commit()
    except fence_crud.FenceError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=CONCURRENT_ERROR)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("fence save of npc %s failed", npc_id)
        raise HTTPException(status_code=500, detail=WRITE_ERROR)
    logger.info("fence settings of npc %s saved by user=%s (active=%s, pct=%s, target=%s)", npc_id,
                current_user.id, body.is_active, body.price_pct, body.cash_target)
    return get_fence(npc_id, db, current_user)
