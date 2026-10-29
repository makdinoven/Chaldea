"""FEAT-181 world economy — HTTP API (router included from main.py).

Public:  GET /characters/economy/currency
Admin:   /characters/admin/economy/{summary,accounts,operations,emission,adjust,settings}
RBAC via user-service permissions economy:read / economy:emit / economy:adjust / economy:settings.

Endpoints are plain `def` (sync SQLAlchemy runs in the threadpool). The router is included in
main.py BEFORE the main `/characters` router, so `/characters/{character_id}`-style routes can
never shadow these static paths.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import database
import econ_core as core
import econ_ledger
import economy_crud
import schemas
from auth_http import UserRead, require_permission

logger = logging.getLogger("character-service.economy")

router = APIRouter(prefix="/characters", tags=["economy"])

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50
MAX_SEARCH_LEN = 100

GENERIC_ERROR = "Не удалось выполнить операцию с экономикой"


def get_db():
    # database.SessionLocal is read at call time so the test suite's patched factory is used.
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _run_write(db: Session, action):
    """Run a money action, commit on success, roll back and map errors otherwise."""
    try:
        result = action()
        db.commit()
        return result
    except economy_crud.EconomyApiError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except core.EconomyError:
        db.rollback()
        logger.exception("economy operation rejected")
        raise HTTPException(status_code=400, detail="Операция отклонена")
    except SQLAlchemyError:
        db.rollback()
        logger.exception("economy operation failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR)


def _read(db: Session, action):
    try:
        return action()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("economy read failed")
        raise HTTPException(status_code=500, detail="Не удалось загрузить данные экономики")


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

@router.get("/economy/currency", response_model=schemas.EconCurrencyForms)
def get_currency(db: Session = Depends(get_db)):
    """Currency word forms for the UI (cached 60 s; defaults when the table is unavailable)."""
    return econ_ledger.get_currency_forms(db).as_dict()


# ---------------------------------------------------------------------------
# Admin: read
# ---------------------------------------------------------------------------

@router.get("/admin/economy/summary", response_model=schemas.EconSummary)
def get_summary(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    def action():
        if economy_crud.ensure_treasury_accounts(db):
            db.commit()
        return economy_crud.get_summary(db)
    return _read(db, action)


@router.get("/admin/economy/accounts", response_model=schemas.EconAccountsPage)
def list_accounts(
    kind: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    kind = kind or None
    if kind is not None and kind not in core.ACCOUNT_KINDS:
        raise HTTPException(status_code=400, detail="Неизвестный тип счёта")
    q = (q or "").strip() or None
    if q is not None and len(q) > MAX_SEARCH_LEN:
        raise HTTPException(status_code=400, detail=f"Поисковый запрос — не длиннее {MAX_SEARCH_LEN} символов")

    def action():
        items, total, created = economy_crud.list_accounts(db, kind=kind, q=q, page=page, page_size=page_size)
        if created:
            db.commit()
        return {"items": items, "total": total, "page": page, "page_size": page_size}
    return _read(db, action)


@router.get("/admin/economy/operations", response_model=schemas.EconOperationsPage,
            response_model_by_alias=True)
def list_operations(
    account_id: Optional[int] = Query(None, ge=1),
    character_id: Optional[int] = Query(None, ge=1),
    op_type: Optional[str] = Query(None),
    region_id: Optional[int] = Query(None, ge=1),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    op_type = op_type or None
    if op_type is not None and op_type not in core.OP_TYPES:
        raise HTTPException(status_code=400, detail="Неизвестный тип операции")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="Дата «с» позже даты «по»")

    def action():
        items, total = economy_crud.list_operations(
            db, account_id=account_id, character_id=character_id, op_type=op_type, region_id=region_id,
            date_from=date_from, date_to=date_to, page=page, page_size=page_size,
        )
        return {"items": items, "total": total, "page": page, "page_size": page_size}
    return _read(db, action)


@router.get("/admin/economy/settings", response_model=schemas.EconSettingsBody)
def get_settings(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read(db, lambda: economy_crud.settings_response(economy_crud.read_settings(db)))


# ---------------------------------------------------------------------------
# Admin: write
# ---------------------------------------------------------------------------

@router.post("/admin/economy/emission", response_model=schemas.EconActionResponse)
def post_emission(
    body: schemas.EconEmissionRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:emit")),
):
    result = _run_write(db, lambda: economy_crud.emit(
        db, account_id=body.account_id, amount=body.amount, comment=body.comment,
        actor_user_id=current_user.id,
    ))
    logger.info("admin emission: user=%s account=%s amount=%s op=%s",
                current_user.id, body.account_id, body.amount, result["operation_id"])
    return result


@router.post("/admin/economy/adjust", response_model=schemas.EconActionResponse)
def post_adjust(
    body: schemas.EconAdjustRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:adjust")),
):
    result = _run_write(db, lambda: economy_crud.adjust(
        db, account_id=body.account_id, delta=body.delta, comment=body.comment,
        actor_user_id=current_user.id,
    ))
    logger.info("admin adjustment: user=%s account=%s delta=%s op=%s",
                current_user.id, body.account_id, body.delta, result["operation_id"])
    return result


@router.put("/admin/economy/settings", response_model=schemas.EconSettingsBody)
def put_settings(
    body: schemas.EconSettingsBody,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    settings = _run_write(db, lambda: economy_crud.update_settings(
        db, forms=body.currency.dict(), country_tax_rate=Decimal(str(body.country_tax_rate)),
        user_id=current_user.id,
    ))
    # This process sees the change immediately; other services within their 60 s TTL.
    econ_ledger.invalidate_settings_cache()
    return economy_crud.settings_response(settings)
