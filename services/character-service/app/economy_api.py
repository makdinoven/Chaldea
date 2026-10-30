"""FEAT-181 world economy — HTTP API (router included from main.py).

Public:  GET /characters/economy/currency, GET /characters/economy/regions/{id}/card (FEAT-182)
Admin:   /characters/admin/economy/{summary,accounts,operations,emission,adjust,settings}
         FEAT-182: /characters/admin/economy/{regions[/{id}[/apply-template|/history]],regions/fill,
                   goods-groups[/{code}],templates[/{code}],item-groups,sim[/run]}
         FEAT-183: /characters/admin/economy/merchants[/fund]
         FEAT-184: /characters/admin/economy/banks[/debtors|/{region_id}[/capital]|/loans/{loan_id}/write-off]
         FEAT-187: /characters/admin/economy/events/{templates[/{id}],active,start,history,{event_id}/cancel}
Player:  FEAT-184 banks: /characters/economy/bank/{npc/{npc_id}[/deposit|/withdraw|/transfer|/send|/loan|/repay],
                          summary,regions} (JWT + ownership; POST also the FEAT-145 gate via locations-service)
RBAC via user-service permissions economy:read / economy:emit / economy:adjust / economy:settings
(regions/fill and merchants/fund need economy:settings AND economy:emit).

Endpoints are plain `def` (sync SQLAlchemy runs in the threadpool). The router is included in
main.py BEFORE the main `/characters` router, so `/characters/{character_id}`-style routes can
never shadow these static paths.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session, sessionmaker

import database
import econ_core as core
import econ_ledger
import econ_scheduler
import econ_tick
import economy_bank_crud
import economy_crud
import economy_events_crud
import locations_client
import economy_merchants_crud
import economy_sim_crud
import schemas
from auth_http import UserRead, get_current_user_via_http, require_permission

logger = logging.getLogger("character-service.economy")

router = APIRouter(prefix="/characters", tags=["economy"])

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50
MAX_SEARCH_LEN = 100

GENERIC_ERROR = "Не удалось выполнить операцию с экономикой"
HISTORY_DEFAULT_LIMIT = 40
HISTORY_MAX_LIMIT = 200


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


def _read_or_error(db: Session, action):
    """A read that may answer a business error (404 and the like)."""
    try:
        return _read(db, action)
    except economy_crud.EconomyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


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
    exclude_op_type: Optional[str] = Query(None),
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
    exclude_op_type = exclude_op_type or None
    if exclude_op_type is not None and exclude_op_type not in core.OP_TYPES:
        raise HTTPException(status_code=400, detail="Неизвестный тип операции")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="Дата «с» позже даты «по»")

    def action():
        items, total = economy_crud.list_operations(
            db, account_id=account_id, character_id=character_id, op_type=op_type, region_id=region_id,
            date_from=date_from, date_to=date_to, page=page, page_size=page_size,
            exclude_op_type=exclude_op_type,
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


# ---------------------------------------------------------------------------
# FEAT-182 living regions (contract 3.7)
# ---------------------------------------------------------------------------

def require_all_permissions(*permissions: str):
    """Like ``require_permission``, but every listed permission is required."""
    def checker(user: UserRead = Depends(get_current_user_via_http)) -> UserRead:
        if any(p not in user.permissions for p in permissions):
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        return user
    return checker


@router.get("/economy/regions/{region_id}/card")
def get_region_card(region_id: int, db: Session = Depends(get_db)):
    """Public qualitative region card: no balances, no raw stock/price numbers; non-simulated -> participating=false."""
    return _read(db, lambda: economy_sim_crud.region_card(db, region_id))


@router.get("/admin/economy/regions")
def list_econ_regions(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read(db, lambda: {"items": economy_sim_crud.list_regions(db)})


@router.post("/admin/economy/regions/fill")
def post_regions_fill(
    body: schemas.EconFillRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_all_permissions("economy:settings", "economy:emit")),
):
    """«Заполнить регионы по шаблонам»: template goods, stocks = norm, idempotent top-up emission (purses, treasuries)."""
    result = _run_write(db, lambda: economy_sim_crud.fill_regions(
        db, region_ids=body.region_ids, population_from_template=body.population_from_template,
        reset_stocks=body.reset_stocks, fund_purses=body.fund_purses, treasury_to_reserve=body.treasury_to_reserve,
        comment=body.comment, actor_user_id=current_user.id, open_banks=body.open_banks,
        return_purse_excess=body.return_purse_excess, return_treasury_excess=body.return_treasury_excess,
    ))
    logger.info("economy fill: user=%s regions=%s emitted=%s returned=%s ops=%s", current_user.id, result["regions"],
                result["emitted"], result["returned"], result["operation_ids"])
    return result


@router.get("/admin/economy/regions/{region_id}")
def get_econ_region(
    region_id: int,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read_or_error(db, lambda: economy_sim_crud.get_region(db, region_id))


@router.put("/admin/economy/regions/{region_id}")
def put_econ_region(
    region_id: int,
    body: schemas.EconRegionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    result = _run_write(db, lambda: economy_sim_crud.update_region(db, region_id, body))
    logger.info("economy region updated: user=%s region=%s template=%s population=%s",
                current_user.id, region_id, body.template_code, body.population)
    return result


@router.post("/admin/economy/regions/{region_id}/apply-template")
def post_apply_template(
    region_id: int,
    body: Optional[schemas.EconApplyTemplateRequest] = None,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    reset_stocks = body.reset_stocks if body is not None else True
    result = _run_write(db, lambda: economy_sim_crud.apply_template(db, region_id, reset_stocks))
    logger.info("economy template applied: user=%s region=%s reset_stocks=%s", current_user.id, region_id,
                reset_stocks)
    return result


@router.get("/admin/economy/regions/{region_id}/history")
def get_region_history(
    region_id: int,
    limit: int = Query(HISTORY_DEFAULT_LIMIT, ge=1, le=HISTORY_MAX_LIMIT),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read(db, lambda: {"items": economy_sim_crud.region_history(db, region_id, limit)})


@router.get("/admin/economy/goods-groups")
def list_goods_groups(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read(db, lambda: {"items": economy_sim_crud.list_goods_groups(db)})


@router.put("/admin/economy/goods-groups/{code}")
def put_goods_group(
    code: str,
    body: schemas.EconGoodsGroupUpdateRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    result = _run_write(db, lambda: economy_sim_crud.update_goods_group(db, code, body))
    logger.info("economy goods group updated: user=%s code=%s", current_user.id, code)
    return result


@router.get("/admin/economy/templates")
def list_templates(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read(db, lambda: {"items": economy_sim_crud.list_templates(db)})


@router.put("/admin/economy/templates/{code}")
def put_template(
    code: str,
    body: schemas.EconTemplateUpdateRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    result = _run_write(db, lambda: economy_sim_crud.update_template(db, code, body))
    logger.info("economy template updated: user=%s code=%s", current_user.id, code)
    return result


@router.get("/admin/economy/item-groups")
def list_item_groups(
    q: Optional[str] = Query(None),
    item_type: Optional[str] = Query(None),
    group: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    off_market: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    q = (q or "").strip() or None
    if q is not None and len(q) > MAX_SEARCH_LEN:
        raise HTTPException(status_code=400, detail=f"Поисковый запрос — не длиннее {MAX_SEARCH_LEN} символов")
    item_type = item_type or None
    if item_type is not None and item_type not in economy_sim_crud.ITEM_TYPES:
        raise HTTPException(status_code=400, detail="Неизвестный тип предмета")
    group = group or None
    if group is not None and group != economy_sim_crud.GROUP_NONE and group not in core.GOODS_GROUPS:
        raise HTTPException(status_code=400, detail="Неизвестная группа товаров")
    source = source or None
    if source is not None and source not in (economy_sim_crud.SOURCE_AUTO, economy_sim_crud.SOURCE_MANUAL):
        raise HTTPException(status_code=400, detail="Источник группы — auto или manual")

    def action():
        items, total = economy_sim_crud.list_item_groups(
            db, q=q, item_type=item_type, group=group, source=source, off_market=off_market,
            page=page, page_size=page_size)
        return {"items": items, "total": total, "page": page, "page_size": page_size}
    return _read(db, action)


@router.put("/admin/economy/item-groups")
def put_item_groups(
    body: schemas.EconItemGroupsUpdateRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    updated = _run_write(db, lambda: economy_sim_crud.update_item_groups(
        db, item_ids=body.item_ids, fields_set=set(body.__fields_set__), group_code=body.group_code,
        off_market=body.off_market, reset=body.reset, actor_user_id=current_user.id,
    ))
    logger.info("economy item groups updated: user=%s items=%s", current_user.id, updated)
    return {"updated": updated}


# ---------------------------------------------------------------------------
# FEAT-183 NPC merchants (contract 3.7)
# ---------------------------------------------------------------------------

@router.get("/admin/economy/merchants")
def list_merchants(
    region_id: Optional[int] = Query(None, ge=1),
    living: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    """Every NPC with shop rows: living/legacy status, cash vs target, rows with current prices, last trade."""
    return _read(db, lambda: economy_merchants_crud.list_merchants(db, region_id=region_id, living=living))


@router.post("/admin/economy/merchants/fund")
def post_merchants_fund(
    body: schemas.EconMerchantFundRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_all_permissions("economy:settings", "economy:emit")),
):
    """«Пополнить кассы торговцев»: idempotent top-up of living merchants to their cash target via emission."""
    result = _run_write(db, lambda: economy_merchants_crud.fund_merchants(
        db, region_ids=body.region_ids, npc_ids=body.npc_ids, comment=body.comment, actor_user_id=current_user.id,
    ))
    logger.info("economy merchants fund: user=%s merchants=%s funded=%s emitted=%s ops=%s", current_user.id,
                result["merchants"], result["funded"], result["emitted"], result["operation_ids"])
    return result


@router.get("/admin/economy/sim")
def get_sim(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read(db, lambda: economy_sim_crud.sim_state(db, env_enabled=econ_scheduler.env_enabled()))


@router.put("/admin/economy/sim")
def put_sim(
    body: schemas.EconSimUpdateRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    _run_write(db, lambda: economy_sim_crud.update_sim(
        db, tick_enabled=body.tick_enabled, params_in=body.params.dict(), user_id=current_user.id))
    logger.info("economy sim settings updated: user=%s tick_enabled=%s", current_user.id, body.tick_enabled)
    return _read(db, lambda: economy_sim_crud.sim_state(db, env_enabled=econ_scheduler.env_enabled()))


@router.post("/admin/economy/sim/run")
def post_sim_run(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    """«Пересчитать сейчас»: a real extra step of every simulated region; waits for completion."""
    # The run opens its own sessions on the request session's engine (so a test override of get_db applies too).
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    db.close()
    try:
        summary = econ_tick.run_manual(current_user.id, session_factory=factory)
    except econ_tick.RunInProgress:
        raise HTTPException(status_code=409, detail="Пересчёт уже идёт, попробуйте позже")
    except Exception:
        logger.exception("economy manual run failed")
        raise HTTPException(status_code=500, detail="Не удалось выполнить пересчёт")
    logger.info("economy manual run: user=%s run=%s status=%s", current_user.id, summary.run_id, summary.status)
    data = summary.to_dict()
    data["id"] = data.pop("run_id")
    data["trigger_kind"] = data.pop("trigger")
    return data


# ---------------------------------------------------------------------------
# FEAT-187 region events (contract 3.7). Static paths are declared before /events/{event_id}/cancel.
# ---------------------------------------------------------------------------

EVENTS = "/admin/economy/events"


@router.get(f"{EVENTS}/templates", response_model=List[schemas.EventTemplateOut])
def list_event_templates(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read(db, lambda: economy_events_crud.list_event_templates(db))


@router.post(f"{EVENTS}/templates", response_model=schemas.EventTemplateOut, status_code=201)
def post_event_template(
    body: schemas.EventTemplateIn,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    result = _run_write(db, lambda: economy_events_crud.create_template(db, body, current_user.id))
    logger.info("economy event template created: user=%s template=%s", current_user.id, result["id"])
    return result


@router.put(f"{EVENTS}/templates/{{template_id}}", response_model=schemas.EventTemplateOut)
def put_event_template(
    template_id: int,
    body: schemas.EventTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    result = _run_write(db, lambda: economy_events_crud.update_template(db, template_id, body, current_user.id))
    logger.info("economy event template updated: user=%s template=%s", current_user.id, template_id)
    return result


@router.delete(f"{EVENTS}/templates/{{template_id}}", status_code=204)
def delete_event_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    _run_write(db, lambda: economy_events_crud.delete_template(db, template_id))
    logger.info("economy event template deleted: user=%s template=%s", current_user.id, template_id)
    return Response(status_code=204)


@router.get(f"{EVENTS}/active", response_model=List[schemas.RegionEventOut])
def list_active_events(
    region_id: Optional[int] = Query(None, ge=1, le=schemas.ECON_MAX_ID),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read(db, lambda: economy_events_crud.list_active_events(db, region_id))


@router.post(f"{EVENTS}/start", response_model=schemas.EventStartOut)
def post_event_start(
    body: schemas.EventStartIn,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    """Manual start (any template, scope expansion); one-shot effects apply at the next recount."""
    # The calendar segment is only recorded on the instance; None (calendar unreachable) is fine. Fetched before
    # any DB work so no transaction is open during the HTTP call.
    segment = locations_client.get_game_segment_sync()
    result = _run_write(db, lambda: economy_events_crud.start_manual(db, body, user_id=current_user.id,
                                                                       segment=segment))
    logger.info("economy event started: user=%s template=%s region=%s started=%s skipped=%s", current_user.id,
                body.template_id, body.region_id, [e["id"] for e in result["started"]], len(result["skipped"]))
    return result


@router.get(f"{EVENTS}/history", response_model=schemas.RegionEventsPage)
def list_events_history(
    region_id: Optional[int] = Query(None, ge=1, le=schemas.ECON_MAX_ID),
    template_code: Optional[str] = Query(None, pattern=schemas.EVENT_CODE_RE),
    kind: Optional[str] = Query(None, pattern=r"^(good|bad)$"),
    status: Optional[str] = Query(None, pattern=r"^(active|ended|cancelled)$"),
    origin: Optional[str] = Query(None, pattern=r"^(random|manual|spread|chain|riot)$"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1, le=100_000),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=schemas.EVENT_HISTORY_MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read_or_error(db, lambda: economy_events_crud.history_page(
        db, region_id=region_id, template_code=template_code, kind=kind, status=status, origin=origin,
        date_from=date_from, date_to=date_to, page=page, page_size=page_size))


@router.post(f"{EVENTS}/{{event_id}}/cancel", response_model=schemas.RegionEventOut)
def post_event_cancel(
    event_id: int,
    body: schemas.EventCancelIn,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    """Stops the ongoing effects from the next recount; one-shot results are not rolled back."""
    result = _run_write(db, lambda: economy_events_crud.cancel_event(db, event_id, comment=body.comment,
                                                                       user_id=current_user.id))
    logger.info("economy event cancelled: user=%s event=%s", current_user.id, event_id)
    return result


# ---------------------------------------------------------------------------
# FEAT-184 banks — player API (contract 3.9)
# ---------------------------------------------------------------------------
# Banker check order (fixed, tests assert it): 1 JWT + ownership + player character -> 2 banker exists / role /
# alive -> 3 activity lock (POST) -> 4 same location -> 5 FEAT-145 gate (POST, fail-closed, awaited with NO open
# DB transaction) -> 6 the banker's region. POST handlers are `async def`: the sync DB work runs in the threadpool.

BANK_REJECTED = "Операция отклонена"


@router.get("/economy/bank/regions", response_model=List[schemas.BankRegionOut])
def list_bank_regions(db: Session = Depends(get_db)):
    """Public: enabled banks (transfer destinations)."""
    return _read(db, lambda: economy_bank_crud.list_bank_regions(db))


@router.get("/economy/bank/summary", response_model=schemas.BankSummary)
def get_bank_summary(
    character_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """All own deposits and the loan, any bank. Owner, or an admin with economy:read."""
    is_admin = "economy:read" in (current_user.permissions or [])
    return _read_or_error(db, lambda: economy_bank_crud.get_summary(db, character_id, current_user.id,
                                                                     is_admin=is_admin))


@router.get("/economy/bank/npc/{npc_id}", response_model=schemas.BankView)
def get_bank_view(
    npc_id: int,
    character_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """The bank window at this banker (read-only, no gate)."""
    def action():
        ctx = economy_bank_crud.banker_context(db, npc_id, character_id, current_user.id, write=False)
        return economy_bank_crud.build_view(db, ctx)
    return _read_or_error(db, action)


def _bank_precheck(db: Session, npc_id: int, character_id: int, user_id: int):
    """Steps 1-4; the read transaction is always closed before the gate's HTTP call."""
    try:
        return economy_bank_crud.resolve_banker(db, npc_id, character_id, user_id, write=True)
    except economy_crud.EconomyApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except SQLAlchemyError:
        logger.exception("bank precheck failed")
        raise HTTPException(status_code=500, detail="Не удалось загрузить данные банка")
    finally:
        db.rollback()


def _bank_commit(db: Session, npc_id: int, character_id: int, user_id: int, flow, body) -> dict:
    """Steps 1-4 again + 6 inside the transaction, the flow, COMMIT, then the fresh view."""
    try:
        ctx = economy_bank_crud.banker_context(db, npc_id, character_id, user_id, write=True)
        result = flow(db, ctx, body)
        db.commit()
    except economy_crud.EconomyApiError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except IntegrityError:
        db.rollback()
        logger.warning("bank operation conflict: npc=%s character=%s flow=%s", npc_id, character_id, flow.__name__)
        raise HTTPException(status_code=409, detail=economy_bank_crud.MSG_RETRY)
    except core.EconomyError:
        db.rollback()
        logger.exception("bank operation rejected: npc=%s character=%s flow=%s", npc_id, character_id, flow.__name__)
        raise HTTPException(status_code=400, detail=BANK_REJECTED)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("bank operation failed: npc=%s character=%s flow=%s", npc_id, character_id, flow.__name__)
        raise HTTPException(status_code=500, detail=GENERIC_ERROR)
    view = _read(db, lambda: economy_bank_crud.build_view(db, ctx))
    return {"message": result["message"], "operation_id": result["operation_id"], "wallet": view["wallet"],
            "view": view}


async def _bank_action(db: Session, user: UserRead, npc_id: int, body, flow) -> dict:
    ctx = await run_in_threadpool(_bank_precheck, db, npc_id, body.character_id, user.id)
    try:
        gate_open = await locations_client.check_npc_gate(body.character_id, ctx.location_id, npc_id)
    except locations_client.GateUnavailable:
        raise HTTPException(status_code=503, detail=economy_bank_crud.MSG_GATE_UNAVAILABLE)
    if not gate_open:
        raise HTTPException(status_code=403, detail=economy_bank_crud.MSG_GATE_CLOSED)
    return await run_in_threadpool(_bank_commit, db, npc_id, body.character_id, user.id, flow, body)


@router.post("/economy/bank/npc/{npc_id}/deposit", response_model=schemas.BankActionOut)
async def post_bank_deposit(npc_id: int, body: schemas.BankDepositIn, db: Session = Depends(get_db),
                            current_user: UserRead = Depends(get_current_user_via_http)):
    return await _bank_action(db, current_user, npc_id, body, economy_bank_crud.deposit)


@router.post("/economy/bank/npc/{npc_id}/withdraw", response_model=schemas.BankActionOut)
async def post_bank_withdraw(npc_id: int, body: schemas.BankWithdrawIn, db: Session = Depends(get_db),
                             current_user: UserRead = Depends(get_current_user_via_http)):
    return await _bank_action(db, current_user, npc_id, body, economy_bank_crud.withdraw)


@router.post("/economy/bank/npc/{npc_id}/transfer", response_model=schemas.BankActionOut)
async def post_bank_transfer(npc_id: int, body: schemas.BankTransferIn, db: Session = Depends(get_db),
                             current_user: UserRead = Depends(get_current_user_via_http)):
    return await _bank_action(db, current_user, npc_id, body, economy_bank_crud.transfer)


@router.post("/economy/bank/npc/{npc_id}/send", response_model=schemas.BankActionOut)
async def post_bank_send(npc_id: int, body: schemas.BankSendIn, db: Session = Depends(get_db),
                         current_user: UserRead = Depends(get_current_user_via_http)):
    return await _bank_action(db, current_user, npc_id, body, economy_bank_crud.send)


@router.post("/economy/bank/npc/{npc_id}/loan", response_model=schemas.BankActionOut)
async def post_bank_loan(npc_id: int, body: schemas.BankLoanIn, db: Session = Depends(get_db),
                         current_user: UserRead = Depends(get_current_user_via_http)):
    return await _bank_action(db, current_user, npc_id, body, economy_bank_crud.take_loan)


@router.post("/economy/bank/npc/{npc_id}/repay", response_model=schemas.BankActionOut)
async def post_bank_repay(npc_id: int, body: schemas.BankRepayIn, db: Session = Depends(get_db),
                          current_user: UserRead = Depends(get_current_user_via_http)):
    return await _bank_action(db, current_user, npc_id, body, economy_bank_crud.repay)


# ---------------------------------------------------------------------------
# FEAT-184 banks — admin API (contract 3.10): reads economy:read, changes economy:settings
# ---------------------------------------------------------------------------

@router.get("/admin/economy/banks")
def list_banks_admin(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read(db, lambda: economy_bank_crud.list_banks_admin(db))


@router.get("/admin/economy/banks/debtors")       # declared before /banks/{region_id}
def list_bank_debtors(
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read(db, lambda: economy_bank_crud.list_debtors(db))


@router.get("/admin/economy/banks/{region_id}")
def get_bank_admin(
    region_id: int,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:read")),
):
    return _read_or_error(db, lambda: economy_bank_crud.get_bank_admin(db, region_id))


@router.put("/admin/economy/banks/{region_id}")
def put_bank_flag(
    region_id: int,
    body: schemas.BankFlagIn,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    """«Банк есть»: creates the row; the first switch-on with seed_capital takes the start capital once."""
    result = _run_write(db, lambda: economy_bank_crud.set_bank_flag(
        db, region_id, is_enabled=body.is_enabled, seed=body.seed_capital, actor_user_id=current_user.id))
    logger.info("bank flag: user=%s region=%s enabled=%s own_funds=%s", current_user.id, region_id,
                body.is_enabled, result["own_funds"])
    return result


@router.post("/admin/economy/banks/{region_id}/capital")
def post_bank_capital(
    region_id: int,
    body: schemas.BankCapitalIn,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    """«Капитал из казны» (in) / «Вернуть капитал в казну» (out)."""
    return _run_write(db, lambda: economy_bank_crud.move_capital(
        db, region_id, direction=body.direction, amount=body.amount, comment=body.comment,
        actor_user_id=current_user.id))


@router.post("/admin/economy/banks/loans/{loan_id}/write-off", response_model=schemas.BankLoanOut)
def post_bank_loan_write_off(
    loan_id: int,
    body: schemas.BankWriteOffIn,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(require_permission("economy:settings")),
):
    """«Списать долг»: the bank's loss, no money moves; clears «Должник»."""
    return _run_write(db, lambda: economy_bank_crud.write_off_loan(
        db, loan_id, comment=body.comment, actor_user_id=current_user.id))
