"""FEAT-204 guard patrols — admin HTTP API (router included from main.py before the main `/characters` router).

    GET  /characters/admin/npcs/{npc_id}/patrol        (npcs:read)    -> PatrolOut (defaults without a row)
    PUT  /characters/admin/npcs/{npc_id}/patrol        (npcs:update)  -> PatrolOut
    POST /characters/admin/npcs/{npc_id}/patrol/step   (npcs:update)  -> PatrolStepOut («Шаг сейчас»)

Existing permissions only (no RBAC migration). Errors are Russian (400 validation, 404 NPC). The step commits in its
own transactions and publishes the encounter notifications after each commit (sync route = FastAPI threadpool).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import database
import law_crud
import patrol_crud
import schemas
from auth_http import UserRead, require_permission

logger = logging.getLogger("character-service.patrol_api")

router = APIRouter(prefix="/characters", tags=["patrols"])

READ_ERROR = "Не удалось загрузить патруль стражника"
WRITE_ERROR = "Не удалось сохранить патруль стражника"
STEP_ERROR = "Не удалось выполнить шаг патруля"
CONCURRENT_ERROR = "Патруль сейчас меняется, попробуйте ещё раз"


def get_db():
    # database.SessionLocal is read at call time so the test suite's patched factory is used.
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/admin/npcs/{npc_id}/patrol", response_model=schemas.PatrolOut)
def get_patrol(npc_id: int, db: Session = Depends(get_db),
               current_user: UserRead = Depends(require_permission("npcs:read"))):
    try:
        return patrol_crud.patrol_out(db, npc_id)
    except law_crud.LawError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("patrol read of npc %s failed", npc_id)
        raise HTTPException(status_code=500, detail=READ_ERROR)


@router.put("/admin/npcs/{npc_id}/patrol", response_model=schemas.PatrolOut)
def put_patrol(npc_id: int, body: schemas.PatrolIn, db: Session = Depends(get_db),
               current_user: UserRead = Depends(require_permission("npcs:update"))):
    try:
        patrol_crud.save_patrol(db, npc_id, body, user_id=current_user.id)
        db.commit()
    except law_crud.LawError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=CONCURRENT_ERROR)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("patrol save of npc %s failed", npc_id)
        raise HTTPException(status_code=500, detail=WRITE_ERROR)
    logger.info("patrol of npc %s saved by user=%s (mode=%s)", npc_id, current_user.id, body.mode)
    return get_patrol(npc_id, db, current_user)


@router.post("/admin/npcs/{npc_id}/patrol/step", response_model=schemas.PatrolStepOut)
def post_patrol_step(npc_id: int, db: Session = Depends(get_db),
                     current_user: UserRead = Depends(require_permission("npcs:update"))):
    try:
        patrol_crud.require_npc(db, npc_id)             # 404 for a missing NPC / a mob
        db.rollback()
        outcome = patrol_crud.step_guard(db, npc_id, force=True)
    except law_crud.LawError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("patrol step of npc %s failed", npc_id)
        raise HTTPException(status_code=500, detail=STEP_ERROR)
    logger.info("patrol step of npc %s by user=%s: %s", npc_id, current_user.id, outcome.outcome)
    return {
        "outcome": outcome.outcome,
        "blocked_reason": outcome.blocked_reason,
        "from_location_id": outcome.from_location_id,
        "to_location_id": outcome.to_location_id,
        "checked": outcome.checked,
        "encounters": outcome.encounters,
        "slipped": outcome.slipped,
        "patrol": get_patrol(npc_id, db, current_user),
    }
