"""FEAT-205 factions — HTTP API (contract: features/FEAT-205 §3.10; router included from main.py before the main
router, so the static ``/factions/...``, ``/admin/factions/...`` and ``/internal/factions/...`` paths win over
``/{character_id}/...``). Inside this router every static path is declared before a parameterised one of the same
shape (``/admin/factions/settings`` before ``/admin/factions/{faction_id}``).

Player (JWT):
    GET    /characters/factions/catalog?character_id=          (character optional, must be own)
    GET    /characters/factions/{faction_id}/public            (no auth)
    GET    /characters/{character_id}/factions                 (private: owner or staff characters:read)
    GET    /characters/{character_id}/factions/history         (private)
    GET    /characters/{character_id}/factions/public          (no auth: non-secret active memberships)
    POST   /characters/{character_id}/factions/{faction_id}/join | /apply | /leave        (owner)
    DELETE /characters/{character_id}/factions/applications/{application_id}            (owner)
Admin: /characters/admin/factions/... (factions:read / edit / delete / manage / settings)
Internal: POST /characters/internal/factions/quest-completed (X-Internal-Token)

FEAT-206 (faction economy, features/FEAT-206 §3.10):
    POST   /characters/{character_id}/factions/{faction_id}/donate                       (owner, active member)
    GET    /characters/factions/quartermaster/npc/{npc_id}/probe?character_id=           (owner)
    GET    /characters/factions/quartermaster/npc/{npc_id}?character_id=                 (owner, same location)
    POST   /characters/factions/quartermaster/npc/{npc_id}/buy                           (owner + dialogue gate)
    admin: /admin/factions/econ-templates[/{code}], /admin/factions/qm-items/{id}, /admin/factions/qm-purchases/{id}/
           retry|refund, /admin/factions/{faction_id}/economy[/fill|/history|/operations], /debts, /quartermasters,
           /qm-items, /qm-purchases (factions:read / factions:economy; fill also economy:emit)

FEAT-207 (territory / passives / kills / outlaw / item donations, features/FEAT-207 §3.9):
    GET|POST /characters/{character_id}/factions/{faction_id}/donate-items                (owner, active member)
    internal: POST /internal/factions/access/check | /access/labels | /battle-result,
              GET /internal/factions/{character_id}/passive-modifiers
    admin: /admin/factions/access/{kind}/{target_id} (GET / PUT / DELETE), /admin/factions/{faction_id}/territory,
           /enemies (GET / PUT), /outlaw-regions (GET / PUT)

Notices are published and rank rewards delivered AFTER the commit (``faction_hooks.dispatch_result``).
"""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

import database
import econ_core as core
import faction_admin_crud as fa
import faction_crud as fcr
import faction_econ_crud as fec
import faction_hooks
import faction_items as fit
import faction_kills as fk
import faction_qm_crud as fqm
import faction_territory as ft
import locations_client
import models
import schemas
from auth_http import UserRead, get_current_user_via_http, require_permission, verify_internal_token
from visibility import require_private_access

logger = logging.getLogger("character-service.faction_api")

router = APIRouter(prefix="/characters", tags=["factions"])

GENERIC_ERROR = "Не удалось выполнить действие"
READ_ERROR = "Не удалось загрузить данные о фракциях"
CONCURRENT_ERROR = "Действие уже выполняется, попробуйте ещё раз"
MSG_NOT_OWNER = "Это не ваш персонаж"
PAGE_MAX = 50

P_READ = "factions:read"
P_EDIT = "factions:edit"
P_DELETE = "factions:delete"
P_MANAGE = "factions:manage"
P_SETTINGS = "factions:settings"
P_ECONOMY = "factions:economy"            # FEAT-206
P_EMIT = "economy:emit"
MONEY_ERROR = "Операция с марками отклонена"


def require_all_permissions(*permissions: str):
    """Every listed permission is required (pattern of economy_api)."""
    def checker(user: UserRead = Depends(get_current_user_via_http)) -> UserRead:
        if any(p not in user.permissions for p in permissions):
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        return user
    return checker


def get_db():
    # database.SessionLocal is read at call time so the test suite's patched factory is used.
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _require_owner(db: Session, character_id: int, user: UserRead) -> None:
    owner = db.execute(text("SELECT user_id FROM characters WHERE id = :cid"), {"cid": int(character_id)}).first()
    if owner is None:
        raise HTTPException(status_code=404, detail=fcr.MSG_CHARACTER_NOT_FOUND)
    if owner[0] is None or int(owner[0]) != int(user.id):
        raise HTTPException(status_code=403, detail=MSG_NOT_OWNER)


def _read(db: Session, action):
    try:
        return action()
    except fcr.FactionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("faction read failed")
        raise HTTPException(status_code=500, detail=READ_ERROR)


def _write(db: Session, action):
    try:
        result = action()
        db.commit()
        return result
    except fcr.FactionError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=CONCURRENT_ERROR)
    except core.EconomyError:
        db.rollback()
        logger.exception("faction money operation rejected")
        raise HTTPException(status_code=400, detail=MONEY_ERROR)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("faction write failed")
        raise HTTPException(status_code=500, detail=GENERIC_ERROR)


def _factory_of(db: Session):
    """A session factory on the request session's engine (post-commit work in own sessions, same database)."""
    return sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())


async def _dispatch(result) -> None:
    if result is not None and (result.notices or result.deliver):
        await run_in_threadpool(faction_hooks.dispatch_result, result)


async def _eject(db: Session, character_ids) -> None:
    """FEAT-207 post-commit best effort: move the characters out of closed territories (errors only logged; the
    5-min faction pass retries)."""
    try:
        await ft.eject_many(_factory_of(db), [int(c) for c in character_ids if c])
    except Exception:
        logger.exception("faction eject of %s failed", character_ids)


async def _eject_member(db: Session, membership_id: int) -> None:
    try:
        row = db.get(models.FactionMember, int(membership_id))
        character_id = int(row.character_id) if row is not None else None
    except SQLAlchemyError:
        db.rollback()
        logger.exception("faction eject: membership %s not read", membership_id)
        return
    finally:
        db.rollback()
    if character_id:
        await _eject(db, [character_id])


# ============================================================================================ static: player catalog

@router.get("/factions/catalog")
def get_catalog(character_id: Optional[int] = Query(None, ge=1), db: Session = Depends(get_db),
                current_user: UserRead = Depends(get_current_user_via_http)):
    if character_id is not None:
        _require_owner(db, character_id, current_user)
    return _read(db, lambda: fcr.catalog(db, character_id))


@router.get("/factions/{faction_id}/public")
def get_faction_public(faction_id: int, db: Session = Depends(get_db)):
    return _read(db, lambda: fcr.faction_public(db, faction_id))


# ============================================================================================ static: quartermaster (206)

@router.get("/factions/quartermaster/npc/{npc_id}/probe")
def get_qm_probe(npc_id: int, character_id: int = Query(..., ge=1), db: Session = Depends(get_db),
                 current_user: UserRead = Depends(get_current_user_via_http)):
    return _read(db, lambda: fqm.probe(db, npc_id, character_id, current_user.id))


@router.get("/factions/quartermaster/npc/{npc_id}")
def get_qm_view(npc_id: int, character_id: int = Query(..., ge=1), db: Session = Depends(get_db),
                current_user: UserRead = Depends(get_current_user_via_http)):
    return _read(db, lambda: fqm.view(db, npc_id, character_id, current_user.id))


def _qm_precheck(db: Session, npc_id: int, body, user_id: int) -> int:
    """Gate before the dialogue-gate HTTP call; the read transaction is closed before it. Returns the location id."""
    try:
        return fqm.resolve(db, npc_id, body.character_id, user_id, write=True).location_id
    except fcr.FactionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except SQLAlchemyError:
        logger.exception("quartermaster precheck failed")
        raise HTTPException(status_code=500, detail=READ_ERROR)
    finally:
        db.rollback()


def _qm_commit_and_deliver(db: Session, npc_id: int, body, user_id: int) -> dict:
    data = _write(db, lambda: fqm.buy(db, npc_id, body, user_id))
    logger.info("quartermaster buy: user=%s character=%s npc=%s qm_item=%s qty=%s total=%s purchase=%s", user_id,
                body.character_id, npc_id, body.qm_item_id, body.quantity, data["price_total"], data["purchase_id"])
    status = None
    try:
        status = fqm.deliver(_factory_of(db), data["purchase_id"])
    except Exception:
        logger.exception("quartermaster purchase %s: delivery failed", data["purchase_id"])
    fec.settle_after_commit([data["faction_id"]], _factory_of(db))
    delivered = status == fqm.P_DONE
    return {"purchase_id": data["purchase_id"], "delivered": delivered, "price_total": data["price_total"],
            "new_balance": data["new_balance"], "message": fqm.MSG_DELIVERED if delivered else fqm.MSG_DELIVERY_LATER}


@router.post("/factions/quartermaster/npc/{npc_id}/buy")
async def post_qm_buy(npc_id: int, body: schemas.FactionQmBuyIn, db: Session = Depends(get_db),
                      current_user: UserRead = Depends(get_current_user_via_http)):
    location_id = await run_in_threadpool(_qm_precheck, db, npc_id, body, current_user.id)
    try:
        gate_open = await locations_client.check_npc_gate(body.character_id, location_id, npc_id)
    except locations_client.GateUnavailable:
        raise HTTPException(status_code=503, detail=fqm.MSG_GATE_UNAVAILABLE)
    if not gate_open:
        raise HTTPException(status_code=403, detail=fqm.MSG_GATE_CLOSED)
    return await run_in_threadpool(_qm_commit_and_deliver, db, npc_id, body, current_user.id)


# ============================================================================================ static: internal

@router.post("/internal/factions/quest-completed")
def post_quest_completed(body: schemas.FactionQuestCompletedIn, background: BackgroundTasks,
                         db: Session = Depends(get_db), _: None = Depends(verify_internal_token)):
    """Quest completion (locations-service, after its commit). Idempotent per ``cq_id``. Rewards are delivered in a
    background task after the response, so the caller is never held by inventory / locations round trips."""
    if fcr.character_row(db, body.character_id) is None:
        raise HTTPException(status_code=404, detail=fcr.MSG_CHARACTER_NOT_FOUND)
    rewards = [(r.faction_id, r.points) for r in body.rewards]
    try:
        result = _write(db, lambda: fcr.quest_completed(db, body.character_id, body.quest_id, body.cq_id, rewards))
    except HTTPException as exc:
        if exc.status_code == 409:                  # a concurrent duplicate on a UNIQUE key
            return {"applied": [], "duplicate": True, "rank_ups": 0}
        raise
    if result.notices or result.deliver:
        background.add_task(faction_hooks.dispatch_result, result)
    return result.data


@router.post("/internal/factions/access/check")
def post_access_check(body: schemas.FactionAccessCheckIn, db: Session = Depends(get_db),
                      _: None = Depends(verify_internal_token)):
    """FEAT-207: dungeon-service entry check — the whole group must pass (§3.4)."""
    return _read(db, lambda: ft.access_check(db, body.kind, body.target_id, body.character_ids))


@router.post("/internal/factions/access/labels")
def post_access_labels(body: schemas.FactionAccessLabelsIn, db: Session = Depends(get_db),
                       _: None = Depends(verify_internal_token)):
    """FEAT-207: closed marks of dungeons / locations; viewer-aware only for the user's own character."""
    return _read(db, lambda: ft.access_labels(db, body.kind, body.target_ids, body.character_id, body.user_id))


@router.post("/internal/factions/battle-result")
def post_battle_result(body: schemas.FactionBattleResultIn, background: BackgroundTasks,
                       db: Session = Depends(get_db), _: None = Depends(verify_internal_token)):
    """FEAT-207: kill points of a finished battle (battle-service, fire-and-forget). Idempotent per battle; commits
    per winner inside. Notices / rank rewards after the response."""
    try:
        result = fk.apply_battle(db, body)
    except fcr.FactionError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("faction battle result %s failed", body.battle_id)
        raise HTTPException(status_code=500, detail=GENERIC_ERROR)
    if result.notices or result.deliver:
        background.add_task(faction_hooks.dispatch_result, result)
    return result.data


@router.get("/internal/factions/{character_id}/passive-modifiers")
def get_passive_modifiers(character_id: int, db: Session = Depends(get_db),
                          _: None = Depends(verify_internal_token)):
    """FEAT-207: the sum of the character's rank passives (battle-service, at battle start)."""
    return _read(db, lambda: fk.passive_modifiers(db, character_id))


# ============================================================================================ static: admin

@router.get("/admin/factions/access/{kind}/{target_id}")
def admin_get_access(kind: str, target_id: int, db: Session = Depends(get_db),
                     current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: ft.get_rule(db, kind, target_id))


@router.put("/admin/factions/access/{kind}/{target_id}")
async def admin_put_access(kind: str, target_id: int, body: schemas.FactionAccessRuleIn,
                           db: Session = Depends(get_db),
                           current_user: UserRead = Depends(require_permission(P_EDIT))):
    result = await run_in_threadpool(_write, db, lambda: ft.put_rule(db, kind, target_id, body))
    logger.info("faction access rule %s/%s -> faction %s rank %s by user=%s", kind, target_id, body.faction_id,
                body.min_rank_id, current_user.id)
    if kind == "location":                              # post-commit: players who may no longer stand there
        try:
            await ft.eject_location(_factory_of(db), int(target_id))
        except Exception:
            logger.exception("faction eject after rule %s/%s failed", kind, target_id)
    return result


@router.delete("/admin/factions/access/{kind}/{target_id}")
def admin_delete_access(kind: str, target_id: int, db: Session = Depends(get_db),
                        current_user: UserRead = Depends(require_permission(P_EDIT))):
    result = _write(db, lambda: ft.delete_rule(db, kind, target_id))
    logger.info("faction access rule %s/%s removed by user=%s", kind, target_id, current_user.id)
    return result


@router.get("/admin/factions")
def admin_list(db: Session = Depends(get_db), current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: fa.admin_list(db))


@router.post("/admin/factions")
def admin_create(body: schemas.FactionIn, db: Session = Depends(get_db),
                 current_user: UserRead = Depends(require_permission(P_EDIT))):
    faction_id = _write(db, lambda: fa.create_faction(db, body))
    logger.info("faction %s created by user=%s", faction_id, current_user.id)
    return _read(db, lambda: fa.admin_detail(db, faction_id))


@router.get("/admin/factions/hostilities")
def admin_hostilities(db: Session = Depends(get_db), current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: fa.list_hostilities(db))


@router.post("/admin/factions/hostilities")
def admin_create_hostility(body: schemas.FactionHostilityIn, db: Session = Depends(get_db),
                           current_user: UserRead = Depends(require_permission(P_EDIT))):
    return _write(db, lambda: fa.create_hostility(db, body))


@router.put("/admin/factions/hostilities/{hostility_id}")
def admin_update_hostility(hostility_id: int, body: schemas.FactionHostilityIn, db: Session = Depends(get_db),
                           current_user: UserRead = Depends(require_permission(P_EDIT))):
    return _write(db, lambda: fa.update_hostility(db, hostility_id, body))


@router.delete("/admin/factions/hostilities/{hostility_id}")
def admin_delete_hostility(hostility_id: int, db: Session = Depends(get_db),
                           current_user: UserRead = Depends(require_permission(P_EDIT))):
    _write(db, lambda: fa.delete_hostility(db, hostility_id))
    return {"ok": True}


@router.get("/admin/factions/applications")
def admin_applications(status: Optional[str] = Query("pending", max_length=10),
                       faction_id: Optional[int] = Query(None, ge=1), page: int = Query(1, ge=1),
                       page_size: int = Query(20, ge=1, le=PAGE_MAX), db: Session = Depends(get_db),
                       current_user: UserRead = Depends(require_permission(P_READ))):
    status = status or None
    if status == "all":
        status = None
    return _read(db, lambda: fa.list_applications(db, status, faction_id, page, page_size))


@router.post("/admin/factions/applications/{application_id}/approve")
async def admin_approve(application_id: int, db: Session = Depends(get_db),
                        current_user: UserRead = Depends(require_permission(P_MANAGE))):
    result = _write(db, lambda: fa.approve(db, application_id, current_user.id))
    logger.info("faction application %s approved by user=%s", application_id, current_user.id)
    await _dispatch(result)
    return result.data


@router.post("/admin/factions/applications/{application_id}/reject")
async def admin_reject(application_id: int, body: schemas.FactionRejectIn, db: Session = Depends(get_db),
                       current_user: UserRead = Depends(require_permission(P_MANAGE))):
    result = _write(db, lambda: fa.reject(db, application_id, body.reason, current_user.id))
    logger.info("faction application %s rejected by user=%s", application_id, current_user.id)
    await _dispatch(result)
    return result.data


@router.get("/admin/factions/settings")
def admin_get_settings(db: Session = Depends(get_db), current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: fa.settings_out(db))


@router.put("/admin/factions/settings")
def admin_put_settings(body: schemas.FactionSettingsIn, db: Session = Depends(get_db),
                       current_user: UserRead = Depends(require_permission(P_SETTINGS))):
    result = _write(db, lambda: fa.update_settings(db, body))
    logger.info("faction settings updated by user=%s", current_user.id)
    return result


@router.get("/admin/factions/characters/{character_id}")
def admin_character(character_id: int, db: Session = Depends(get_db),
                    current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: fa.admin_character(db, character_id))


@router.post("/admin/factions/members/{membership_id}/points")
async def admin_points(membership_id: int, body: schemas.FactionPointsIn, db: Session = Depends(get_db),
                       current_user: UserRead = Depends(require_permission(P_MANAGE))):
    result = _write(db, lambda: fa.admin_points(db, membership_id, body.delta, body.reason, current_user.id))
    logger.info("faction points: membership=%s delta=%s by user=%s", membership_id, body.delta, current_user.id)
    await _dispatch(result)
    return result.data


@router.post("/admin/factions/members/{membership_id}/expel")
async def admin_expel(membership_id: int, body: schemas.FactionExpelIn, db: Session = Depends(get_db),
                      current_user: UserRead = Depends(require_permission(P_MANAGE))):
    result = _write(db, lambda: fa.expel(db, membership_id, body.reason, current_user.id))
    logger.info("faction expel: membership=%s by user=%s", membership_id, current_user.id)
    await _dispatch(result)
    await _eject_member(db, membership_id)                  # FEAT-207: out of a territory he may no longer enter
    return result.data


@router.post("/admin/factions/deliveries/{delivery_id}/retry")
async def admin_retry_delivery(delivery_id: int, db: Session = Depends(get_db),
                               current_user: UserRead = Depends(require_permission(P_MANAGE))):
    character_id = _write(db, lambda: fa.retry_delivery(db, delivery_id))
    logger.info("faction delivery %s retried by user=%s", delivery_id, current_user.id)
    await run_in_threadpool(faction_hooks.dispatch, [], [character_id])
    return _read(db, lambda: fa.admin_character(db, character_id))


@router.put("/admin/factions/ranks/{rank_id}")
def admin_update_rank(rank_id: int, body: schemas.FactionRankIn, db: Session = Depends(get_db),
                      current_user: UserRead = Depends(require_permission(P_EDIT))):
    return _write(db, lambda: fa.update_rank(db, rank_id, body))


@router.delete("/admin/factions/ranks/{rank_id}")
def admin_delete_rank(rank_id: int, db: Session = Depends(get_db),
                      current_user: UserRead = Depends(require_permission(P_DELETE))):
    _write(db, lambda: fa.delete_rank(db, rank_id))
    return {"ok": True}


# ============================================================================================ admin: economy (206, static)

@router.get("/admin/factions/econ-templates")
def admin_econ_templates(db: Session = Depends(get_db), current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: fec.list_templates(db))


@router.post("/admin/factions/econ-templates")
def admin_create_econ_template(body: schemas.FactionEconTemplateIn, db: Session = Depends(get_db),
                               current_user: UserRead = Depends(require_permission(P_ECONOMY))):
    result = _write(db, lambda: fec.create_template(db, body))
    logger.info("faction econ template %s created by user=%s", result["code"], current_user.id)
    return result


@router.put("/admin/factions/econ-templates/{code}")
def admin_update_econ_template(code: str, body: schemas.FactionEconTemplateIn, db: Session = Depends(get_db),
                               current_user: UserRead = Depends(require_permission(P_ECONOMY))):
    result = _write(db, lambda: fec.update_template(db, code, body))
    logger.info("faction econ template %s updated by user=%s", code, current_user.id)
    return result


@router.delete("/admin/factions/econ-templates/{code}")
def admin_delete_econ_template(code: str, db: Session = Depends(get_db),
                               current_user: UserRead = Depends(require_permission(P_ECONOMY))):
    _write(db, lambda: fec.delete_template(db, code))
    logger.info("faction econ template %s deleted by user=%s", code, current_user.id)
    return {"ok": True}


@router.put("/admin/factions/qm-items/{qm_item_id}")
def admin_update_qm_item(qm_item_id: int, body: schemas.FactionQmItemIn, db: Session = Depends(get_db),
                         current_user: UserRead = Depends(require_permission(P_ECONOMY))):
    return _write(db, lambda: fqm.update_qm_item(db, qm_item_id, body))


@router.delete("/admin/factions/qm-items/{qm_item_id}")
def admin_delete_qm_item(qm_item_id: int, db: Session = Depends(get_db),
                         current_user: UserRead = Depends(require_permission(P_ECONOMY))):
    _write(db, lambda: fqm.delete_qm_item(db, qm_item_id))
    return {"ok": True}


def _purchase_view(db: Session, purchase_id: int) -> dict:
    row = db.get(models.FactionQmPurchase, int(purchase_id))
    if row is None:
        raise fcr.FactionError(404, fqm.MSG_PURCHASE_NOT_FOUND)
    return fqm.purchase_out(row, fcr.character_brief(db, [row.character_id]), fqm.items_info(db, [row.item_id]))


@router.post("/admin/factions/qm-purchases/{purchase_id}/retry")
async def admin_retry_qm_purchase(purchase_id: int, db: Session = Depends(get_db),
                                  current_user: UserRead = Depends(require_permission(P_ECONOMY))):
    pid = await run_in_threadpool(_write, db, lambda: fqm.retry_purchase(db, purchase_id))
    logger.info("quartermaster purchase %s retried by user=%s", pid, current_user.id)
    await run_in_threadpool(fqm.deliver, _factory_of(db), pid)
    return _read(db, lambda: _purchase_view(db, pid))


@router.post("/admin/factions/qm-purchases/{purchase_id}/refund")
async def admin_refund_qm_purchase(purchase_id: int, db: Session = Depends(get_db),
                                   current_user: UserRead = Depends(require_permission(P_ECONOMY))):
    outcome, notices = await run_in_threadpool(_write, db, lambda: fqm.refund(db, purchase_id))
    logger.info("quartermaster purchase %s refunded (%s) by user=%s", purchase_id, outcome, current_user.id)
    await run_in_threadpool(faction_hooks.dispatch, notices, [])
    return _read(db, lambda: _purchase_view(db, purchase_id))


# ============================================================================================ admin: one faction

@router.get("/admin/factions/{faction_id}")
def admin_detail(faction_id: int, db: Session = Depends(get_db),
                 current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: fa.admin_detail(db, faction_id))


@router.put("/admin/factions/{faction_id}")
def admin_update(faction_id: int, body: schemas.FactionIn, db: Session = Depends(get_db),
                 current_user: UserRead = Depends(require_permission(P_EDIT))):
    _write(db, lambda: fa.update_faction(db, faction_id, body))
    logger.info("faction %s updated by user=%s", faction_id, current_user.id)
    return _read(db, lambda: fa.admin_detail(db, faction_id))


@router.delete("/admin/factions/{faction_id}")
def admin_delete(faction_id: int, db: Session = Depends(get_db),
                 current_user: UserRead = Depends(require_permission(P_DELETE))):
    _write(db, lambda: fa.delete_faction(db, faction_id))
    logger.info("faction %s deleted by user=%s", faction_id, current_user.id)
    return {"ok": True}


@router.post("/admin/factions/{faction_id}/ranks")
def admin_create_rank(faction_id: int, body: schemas.FactionRankIn, db: Session = Depends(get_db),
                      current_user: UserRead = Depends(require_permission(P_EDIT))):
    return _write(db, lambda: fa.create_rank(db, faction_id, body))


@router.put("/admin/factions/{faction_id}/ranks/order")
def admin_reorder_ranks(faction_id: int, body: schemas.FactionRankOrderIn, db: Session = Depends(get_db),
                        current_user: UserRead = Depends(require_permission(P_EDIT))):
    return _write(db, lambda: fa.reorder_ranks(db, faction_id, body.rank_ids))


@router.put("/admin/factions/{faction_id}/conditions")
def admin_set_conditions(faction_id: int, body: schemas.FactionConditionsIn, db: Session = Depends(get_db),
                         current_user: UserRead = Depends(require_permission(P_EDIT))):
    return _write(db, lambda: fa.set_conditions(db, faction_id, body.conditions))


# ---------------------------------------------------------------------------------------- admin: stage 3 (207)

@router.get("/admin/factions/{faction_id}/territory")
def admin_territory(faction_id: int, db: Session = Depends(get_db),
                    current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: ft.faction_territory(db, faction_id))


@router.get("/admin/factions/{faction_id}/enemies")
def admin_enemies(faction_id: int, db: Session = Depends(get_db),
                  current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: fk.enemies_out(db, faction_id))


@router.put("/admin/factions/{faction_id}/enemies")
def admin_put_enemies(faction_id: int, body: schemas.FactionEnemiesIn, db: Session = Depends(get_db),
                      current_user: UserRead = Depends(require_permission(P_EDIT))):
    result = _write(db, lambda: fk.put_enemies(db, faction_id, body))
    logger.info("faction %s enemies set (%d rows) by user=%s", faction_id, len(body.enemies), current_user.id)
    return result


@router.get("/admin/factions/{faction_id}/outlaw-regions")
def admin_outlaw_regions(faction_id: int, db: Session = Depends(get_db),
                         current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: fk.outlaw_out(db, faction_id))


@router.put("/admin/factions/{faction_id}/outlaw-regions")
def admin_put_outlaw_regions(faction_id: int, body: schemas.FactionOutlawRegionsIn, db: Session = Depends(get_db),
                             current_user: UserRead = Depends(require_permission(P_EDIT))):
    result = _write(db, lambda: fk.put_outlaw(db, faction_id, body))
    logger.info("faction %s outlaw regions set (%d rows) by user=%s", faction_id, len(body.regions),
                current_user.id)
    return result


# ---------------------------------------------------------------------------------------- admin: economy (206)

@router.get("/admin/factions/{faction_id}/economy")
def admin_economy(faction_id: int, db: Session = Depends(get_db),
                  current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: fec.economy_view(db, faction_id))


@router.put("/admin/factions/{faction_id}/economy")
def admin_put_economy(faction_id: int, body: schemas.FactionEconomyIn, db: Session = Depends(get_db),
                      current_user: UserRead = Depends(require_permission(P_ECONOMY))):
    _write(db, lambda: fec.update_economy(db, faction_id, body))
    logger.info("faction %s economy updated by user=%s", faction_id, current_user.id)
    return _read(db, lambda: fec.economy_view(db, faction_id))


@router.post("/admin/factions/{faction_id}/economy/fill")
def admin_fill_economy(faction_id: int, body: schemas.FactionFillIn, db: Session = Depends(get_db),
                       current_user: UserRead = Depends(require_all_permissions(P_ECONOMY, P_EMIT))):
    result = _write(db, lambda: fec.fill_from_template(db, faction_id, body.comment, body.set_members,
                                                       current_user.id))
    logger.info("faction %s filled by user=%s: members=%s emitted=%s", faction_id, current_user.id,
                result["members_count"], result["emitted"])
    fec.settle_after_commit([faction_id], _factory_of(db))
    return result


@router.get("/admin/factions/{faction_id}/economy/history")
def admin_economy_history(faction_id: int, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=PAGE_MAX),
                          db: Session = Depends(get_db), current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: fec.history_page(db, faction_id, page, page_size))


@router.get("/admin/factions/{faction_id}/economy/operations")
def admin_economy_operations(faction_id: int, page: int = Query(1, ge=1),
                             page_size: int = Query(20, ge=1, le=PAGE_MAX), db: Session = Depends(get_db),
                             current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: fec.operations_page(db, faction_id, page, page_size))


@router.get("/admin/factions/{faction_id}/debts")
def admin_faction_debts(faction_id: int, status: Optional[str] = Query("open", max_length=10),
                        page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=PAGE_MAX),
                        db: Session = Depends(get_db), current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: fec.debts_page(db, faction_id, status or None, page, page_size))


@router.get("/admin/factions/{faction_id}/quartermasters")
def admin_quartermasters(faction_id: int, db: Session = Depends(get_db),
                         current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: fqm.list_quartermasters(db, faction_id))


@router.put("/admin/factions/{faction_id}/quartermasters")
def admin_put_quartermasters(faction_id: int, body: schemas.FactionQuartermastersIn, db: Session = Depends(get_db),
                             current_user: UserRead = Depends(require_permission(P_ECONOMY))):
    result = _write(db, lambda: fqm.set_quartermasters(db, faction_id, body.npc_ids))
    logger.info("faction %s quartermasters set to %s by user=%s", faction_id, body.npc_ids, current_user.id)
    return result


@router.get("/admin/factions/{faction_id}/qm-items")
def admin_qm_items(faction_id: int, db: Session = Depends(get_db),
                   current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: fqm.list_qm_items(db, faction_id))


@router.post("/admin/factions/{faction_id}/qm-items")
def admin_create_qm_item(faction_id: int, body: schemas.FactionQmItemIn, db: Session = Depends(get_db),
                         current_user: UserRead = Depends(require_permission(P_ECONOMY))):
    return _write(db, lambda: fqm.create_qm_item(db, faction_id, body))


@router.get("/admin/factions/{faction_id}/qm-purchases")
def admin_qm_purchases(faction_id: int, status: Optional[str] = Query(None, max_length=10),
                       page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=PAGE_MAX),
                       db: Session = Depends(get_db), current_user: UserRead = Depends(require_permission(P_READ))):
    return _read(db, lambda: fqm.list_purchases(db, faction_id, status or None, page, page_size))


@router.get("/admin/factions/{faction_id}/members")
def admin_members(faction_id: int, status: Optional[str] = Query("active", max_length=10),
                  q: Optional[str] = Query(None, max_length=100), page: int = Query(1, ge=1),
                  page_size: int = Query(20, ge=1, le=PAGE_MAX), db: Session = Depends(get_db),
                  current_user: UserRead = Depends(require_permission(P_READ))):
    status = status or None
    if status == "all":
        status = None
    return _read(db, lambda: fa.list_members(db, faction_id, status, q, page, page_size))


# ============================================================================================ player: per character
# Declared last: the static paths above win over /{character_id}/....

@router.get("/{character_id}/factions")
def get_my_factions(character_id: int, db: Session = Depends(get_db),
                    current_user: UserRead = Depends(get_current_user_via_http)):
    require_private_access(db, character_id, current_user)
    return _read(db, lambda: fcr.private_view(db, character_id))


@router.get("/{character_id}/factions/history")
def get_faction_history(character_id: int, page: int = Query(1, ge=1),
                        page_size: int = Query(20, ge=1, le=PAGE_MAX), db: Session = Depends(get_db),
                        current_user: UserRead = Depends(get_current_user_via_http)):
    require_private_access(db, character_id, current_user)
    return _read(db, lambda: fcr.history(db, character_id, page, page_size))


@router.get("/{character_id}/factions/public")
def get_public_factions(character_id: int, db: Session = Depends(get_db)):
    return _read(db, lambda: fcr.public_memberships(db, character_id))


@router.post("/{character_id}/factions/{faction_id}/join")
async def post_join(character_id: int, faction_id: int, db: Session = Depends(get_db),
                    current_user: UserRead = Depends(get_current_user_via_http)):
    _require_owner(db, character_id, current_user)
    result = _write(db, lambda: fcr.join(db, character_id, faction_id))
    logger.info("faction join: character=%s faction=%s", character_id, faction_id)
    await _dispatch(result)
    return result.data


@router.post("/{character_id}/factions/{faction_id}/apply")
def post_apply(character_id: int, faction_id: int, body: schemas.FactionApplyIn, db: Session = Depends(get_db),
               current_user: UserRead = Depends(get_current_user_via_http)):
    _require_owner(db, character_id, current_user)
    result = _write(db, lambda: fcr.apply(db, character_id, faction_id, body.message))
    return result.data


@router.delete("/{character_id}/factions/applications/{application_id}")
def delete_application(character_id: int, application_id: int, db: Session = Depends(get_db),
                       current_user: UserRead = Depends(get_current_user_via_http)):
    _require_owner(db, character_id, current_user)
    result = _write(db, lambda: fcr.cancel_application(db, character_id, application_id))
    return result.data


@router.post("/{character_id}/factions/{faction_id}/donate")
async def post_donate(character_id: int, faction_id: int, body: schemas.FactionDonateIn, db: Session = Depends(get_db),
                      current_user: UserRead = Depends(get_current_user_via_http)):
    await run_in_threadpool(_require_owner, db, character_id, current_user)
    result = await run_in_threadpool(_write, db, lambda: fec.donate(db, character_id, faction_id, body.amount,
                                                                     body.request_id))
    logger.info("faction donation: character=%s faction=%s amount=%s points=%s", character_id, faction_id,
                body.amount, result.data["points_delta"])
    await _dispatch(result)
    await run_in_threadpool(fec.settle_after_commit, [faction_id], _factory_of(db))
    return {k: v for k, v in result.data.items() if k != "faction_id"}


@router.post("/{character_id}/factions/{faction_id}/leave")
async def post_leave(character_id: int, faction_id: int, db: Session = Depends(get_db),
                     current_user: UserRead = Depends(get_current_user_via_http)):
    await run_in_threadpool(_require_owner, db, character_id, current_user)
    result = await run_in_threadpool(_write, db, lambda: fcr.leave(db, character_id, faction_id))
    logger.info("faction leave: character=%s faction=%s", character_id, faction_id)
    await _eject(db, [character_id])                        # FEAT-207: out of a territory he may no longer enter
    return result.data


@router.get("/{character_id}/factions/{faction_id}/donate-items")
def get_donate_items(character_id: int, faction_id: int, db: Session = Depends(get_db),
                     current_user: UserRead = Depends(get_current_user_via_http)):
    """FEAT-207: eligible plain stacks with their value in the faction's HQ region."""
    _require_owner(db, character_id, current_user)
    return _read(db, lambda: fit.options(db, character_id, faction_id))


@router.post("/{character_id}/factions/{faction_id}/donate-items")
async def post_donate_items(character_id: int, faction_id: int, body: schemas.FactionDonateItemsIn,
                            db: Session = Depends(get_db),
                            current_user: UserRead = Depends(get_current_user_via_http)):
    """FEAT-207: items into the faction stock (sold to the HQ market in the tick) for donation points."""
    await run_in_threadpool(_require_owner, db, character_id, current_user)
    result = await run_in_threadpool(_write, db, lambda: fit.donate_items(db, character_id, faction_id, body.items,
                                                                          body.request_id))
    logger.info("faction item donation: character=%s faction=%s items=%s value=%s points=%s", character_id,
                faction_id, result.data["items_given"], result.data["value_total"], result.data["points_delta"])
    await _dispatch(result)
    return result.data
