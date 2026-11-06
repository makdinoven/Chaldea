"""FEAT-206 §3.8: the faction quartermaster («Интендант») — player view / buy, item delivery outbox, refunds, admin.

Binding = ``faction_quartermasters`` (source of truth); ``characters.npc_role = 'quartermaster'`` is only the visible
label. The assortment (``faction_qm_items``) is one per faction, shared by its quartermasters. Not an
``npc_shop_items`` merchant: the region tick, «Пополнить кассы» and the public NPC shop never see it.

Buy = ONE transaction (``faction_members`` FOR UPDATE → ``faction_qm_items`` FOR UPDATE → conditional stock take →
``faction_qm_sale`` op character -> faction → ``faction_qm_purchases`` row ``pending``) → COMMIT → delivery after the
commit: the claim ``pending -> sending`` (attempts + 1) is committed BEFORE the HTTP call to inventory (not
idempotent). 2xx -> ``done``; a definite failure (refused / 4xx / 5xx) -> ``pending`` with backoff ``2^attempts`` min,
auto-refund after :data:`MAX_ATTEMPTS`; a timeout / read error (maybe applied) -> ``failed`` + ``uncertain``, never
auto-retried (admin «Повторить» / «Вернуть деньги»). Stale ``sending`` -> ``failed`` uncertain.

Refund = ONE transaction: ``faction_economy`` FOR UPDATE (serialises every debit of the treasury) →
``faction_qm_items`` → ``faction_qm_purchases`` FOR UPDATE (pending | failed) → stock back → ``faction_qm_refund`` op
faction -> character (key ``faction_qm_refund:p<id>``), or — the treasury cannot pay — a ``refund`` debt (key
``refund:p<id>``, paid by the debt queue) → ``refunded``.

Secrecy (§3.9): a non-member of a secret faction gets 403 «Этот человек с вами не разговаривает» (NPC role label
«Интендант») or the plain-NPC 404 «Интендант не найден» (any other role) before anything faction-specific is returned
or checked; the probe answers ``none`` / ``silent`` / ``open`` the same way.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import activity_lock
import econ_core as core
import econ_ledger
import faction_core as fc
import faction_crud as fcr
import faction_econ as fe
import faction_econ_crud as fec
import models
from faction_crud import FactionError
from faction_notify import CATEGORY_PROGRESS, Notice

logger = logging.getLogger("character-service.faction_qm_crud")

SOURCE_SERVICE = "character-service"
QM_ROLE = "quartermaster"
NPC_DEAD = "dead"

P_PENDING = "pending"
P_SENDING = "sending"
P_DONE = "done"
P_FAILED = "failed"
P_REFUNDED = "refunded"
PURCHASE_STATUSES = (P_PENDING, P_SENDING, P_DONE, P_FAILED, P_REFUNDED)
UNCERTAIN = "uncertain"

PROBE_NONE = "none"
PROBE_SILENT = "silent"
PROBE_OPEN = "open"

MAX_ATTEMPTS = 5
MAX_BACKOFF_MINUTES = 24 * 60
STALE_SENDING = timedelta(minutes=10)
BATCH_SIZE = 200
MAX_QUARTERMASTERS = 10
MAX_PRICE = 10_000_000
MAX_STOCK = 100_000
PAGE_SIZE_MAX = 50

MSG_NOT_OWNER = "Это не ваш персонаж"
MSG_NOT_PLAYER = "Интендант работает только с персонажами игроков"
MSG_QM_NOT_FOUND = "Интендант не найден"
MSG_QM_DEAD = "Интендант мёртв"
MSG_WRONG_LOCATION = "Вы не рядом с интендантом"
MSG_SILENT = "Этот человек с вами не разговаривает"
MSG_MEMBERS_ONLY = "Только для членов фракции «{name}»"
MSG_NEED_RANK = "Нужно звание «{name}»"
MSG_ITEM_NOT_FOUND = "Такого товара у интенданта нет"
MSG_NO_STOCK = "Недостаточно товара у интенданта"
MSG_DONE = "Покупка уже выполнена"
MSG_DELIVERED = "Покупка выполнена — предмет в инвентаре"
MSG_DELIVERY_LATER = "Предмет будет доставлен в инвентарь в ближайшее время"
MSG_GATE_CLOSED = "Нужен пост-намерение «Диалог с НПС» с этим персонажем"
MSG_GATE_UNAVAILABLE = "Не удалось проверить обращение к интенданту, попробуйте позже"
MSG_PURCHASE_NOT_FOUND = "Покупка не найдена"
MSG_RETRY_STATE = "Повторить можно только неудавшуюся выдачу"
MSG_REFUND_STATE = "Вернуть деньги можно только за невыданную покупку"
MSG_QMS_MAX = "Интендантов у фракции может быть не больше 10"
MSG_QM_NPC = "Интендантом может быть только существующий NPC"
MSG_QM_TAKEN = "NPC уже интендант фракции «{name}»"
MSG_ITEM_MISSING = "Предмет не найден"
MSG_ITEM_DUP = "Этот предмет уже есть в ассортименте"
MSG_PRICE = "Цена: от 1 до 10000000"
MSG_STOCK = "Запас: от 0 до 100000"
MSG_TARGET = "Норма запаса: от 0 до 100000"
MSG_OFF_MARKET = "Этот предмет не продаётся на рынке — запас пополняет только администратор"
MSG_RANK_FOREIGN = "Звание не из этой фракции"
MSG_SORT = "Порядок: от -100000 до 100000"
MSG_QM_ITEM_NOT_FOUND = "Строка ассортимента не найдена"
MSG_STATUS = "Неизвестный статус"
NOTICE_REFUNDED = "Интендант не смог выдать «{item}» — марки возвращены"
NOTICE_REFUND_DEBT = "Интендант не смог выдать «{item}» — марки вернут из казны фракции позже"


def now_utc() -> datetime:
    return fcr.now_utc()


def _lock(db: Session, query):
    return fec._lock(db, query)


def backoff(attempts: int) -> timedelta:
    return timedelta(minutes=min(MAX_BACKOFF_MINUTES, 2 ** max(0, int(attempts))))


def purchase_key(character_id: int, request_id: str) -> str:
    return f"faction_qm:c{int(character_id)}:{request_id}"


# =====================================================================================================================
# gate / context
# =====================================================================================================================

@dataclass
class QmContext:
    character: "models.Character"
    npc: "models.Character"
    faction: "models.Faction"
    member: Optional["models.FactionMember"]
    location_id: int

    @property
    def is_member(self) -> bool:
        return self.member is not None and self.member.status == fc.STATUS_ACTIVE


def _player(db: Session, character_id: int, user_id: int) -> "models.Character":
    ch = db.query(models.Character).filter(models.Character.id == int(character_id)).first()
    if ch is None:
        raise FactionError(404, fcr.MSG_CHARACTER_NOT_FOUND)
    if ch.user_id is None or int(ch.user_id) != int(user_id):
        raise FactionError(403, MSG_NOT_OWNER)
    if ch.is_npc:
        raise FactionError(403, MSG_NOT_PLAYER)
    return ch


def binding(db: Session, npc_id: int) -> Optional[int]:
    row = db.execute(text("SELECT faction_id FROM faction_quartermasters WHERE npc_id = :n"),
                     {"n": int(npc_id)}).first()
    return int(row[0]) if row is not None else None


def probe(db: Session, npc_id: int, character_id: int, user_id: int) -> dict:
    _player(db, character_id, user_id)
    fid = binding(db, npc_id)
    if fid is None:
        return {"state": PROBE_NONE}
    faction = db.get(models.Faction, fid)
    if faction is None:
        return {"state": PROBE_NONE}
    if not faction.is_secret:
        return {"state": PROBE_OPEN}
    member = fcr.member_row(db, character_id, fid)
    if member is not None and member.status == fc.STATUS_ACTIVE:
        return {"state": PROBE_OPEN}
    npc = db.get(models.Character, int(npc_id))
    return {"state": PROBE_SILENT if npc is not None and npc.npc_role == QM_ROLE else PROBE_NONE}


def secret_refusal(npc: "models.Character") -> FactionError:
    """A secret faction's quartermaster to a non-member — mirrors the probe: role label «Интендант» → 403 silent;
    any other role → exactly the answer of a plain, unbound NPC (404), so the API does not reveal the binding."""
    if npc.npc_role == QM_ROLE:
        return FactionError(403, MSG_SILENT)
    return FactionError(404, MSG_QM_NOT_FOUND)


def resolve(db: Session, npc_id: int, character_id: int, user_id: int, *, write: bool) -> QmContext:
    """Gate (§3.8): owner & player → NPC / binding (404) → secret + non-member (403 silent, or the plain-NPC 404 —
    :func:`secret_refusal`) → dead (409) → location (400) → activity lock (buy, 409). No faction data is returned and
    no quartermaster-specific check is answered before the secrecy check passes."""
    ch = _player(db, character_id, user_id)
    npc = db.query(models.Character).filter(models.Character.id == int(npc_id)).first()
    fid = binding(db, npc_id)
    if npc is None or not npc.is_npc or fid is None:
        raise FactionError(404, MSG_QM_NOT_FOUND)
    faction = db.get(models.Faction, fid)
    if faction is None:
        raise FactionError(404, MSG_QM_NOT_FOUND)
    member = fcr.member_row(db, ch.id, faction.id)
    is_member = member is not None and member.status == fc.STATUS_ACTIVE
    if faction.is_secret and not is_member:
        raise secret_refusal(npc)
    if npc.npc_status == NPC_DEAD:
        raise FactionError(409, MSG_QM_DEAD)
    if npc.current_location_id is None or ch.current_location_id is None or \
            int(ch.current_location_id) != int(npc.current_location_id):
        raise FactionError(400, MSG_WRONG_LOCATION)
    if write:
        message = activity_lock.lock_message(activity_lock.lock_for_character(ch))
        if message:
            raise FactionError(409, message)
    return QmContext(character=ch, npc=npc, faction=faction, member=member, location_id=int(npc.current_location_id))


def _rank_info(db: Session, ctx: QmContext) -> Tuple[Optional["models.FactionRank"], Dict[int, "models.FactionRank"]]:
    ranks = {int(r.id): r for r in fcr.load_ranks(db, [ctx.faction.id]).get(int(ctx.faction.id), [])}
    rank = ranks.get(int(ctx.member.rank_id)) if ctx.is_member and ctx.member.rank_id else None
    return rank, ranks


def _locked_reason(ctx: QmContext, rank, min_rank) -> Optional[str]:
    if not ctx.is_member:
        return MSG_MEMBERS_ONLY.format(name=ctx.faction.name)
    if min_rank is not None and not fe.rank_allows(int(rank.sort_order) if rank is not None else None,
                                                   int(min_rank.sort_order)):
        return MSG_NEED_RANK.format(name=min_rank.name)
    return None


def items_info(db: Session, item_ids) -> Dict[int, dict]:
    ids = sorted({int(i) for i in item_ids})
    if not ids:
        return {}
    ph, params = fcr.in_clause("i", ids)
    rows = db.execute(text(f"SELECT id, name, image, item_type, item_rarity FROM items WHERE id IN ({ph})"),
                      params).fetchall()
    return {int(r[0]): {"id": int(r[0]), "name": r[1], "image": r[2], "item_type": r[3], "item_rarity": r[4]}
            for r in rows}


def view(db: Session, npc_id: int, character_id: int, user_id: int) -> dict:
    ctx = resolve(db, npc_id, character_id, user_id, write=False)
    rank, ranks = _rank_info(db, ctx)
    discount = int(rank.qm_discount_pct or 0) if rank is not None else 0
    rows = (db.query(models.FactionQmItem)
            .filter(models.FactionQmItem.faction_id == int(ctx.faction.id), models.FactionQmItem.is_active.is_(True))
            .order_by(models.FactionQmItem.sort_order, models.FactionQmItem.id).all())
    items = items_info(db, [r.item_id for r in rows])
    out = []
    for row in rows:
        item = items.get(int(row.item_id))
        if item is None:
            continue
        min_rank = ranks.get(int(row.min_rank_id)) if row.min_rank_id else None
        out.append({
            "qm_item_id": int(row.id), "item": item, "price": int(row.price),
            "final_price": fe.qm_unit_price(int(row.price), discount if ctx.is_member else 0),
            "stock": int(row.stock),
            "min_rank": {"id": int(min_rank.id), "name": min_rank.name} if min_rank is not None else None,
            "locked_reason": _locked_reason(ctx, rank, min_rank),
        })
    return {
        "npc": {"id": int(ctx.npc.id), "name": ctx.npc.name},
        "faction": {"id": int(ctx.faction.id), "name": ctx.faction.name, "emblem_url": ctx.faction.emblem_url},
        "member": ctx.is_member,
        "rank": {"id": int(rank.id), "name": rank.name, "discount_pct": discount} if rank is not None else None,
        "balance": int(ctx.character.currency_balance or 0),
        "items": out,
    }


# =====================================================================================================================
# buy
# =====================================================================================================================

def buy(db: Session, npc_id: int, body, user_id: int, now: Optional[datetime] = None) -> dict:
    """The purchase transaction (caller commits). Returns {purchase_id, faction_id, price_total, new_balance}."""
    import crud  # late: heavy
    now = now or now_utc()
    ctx = resolve(db, npc_id, body.character_id, user_id, write=True)
    key = purchase_key(ctx.character.id, body.request_id)
    if fec.operation_exists(db, key):
        raise FactionError(409, MSG_DONE)
    fid = int(ctx.faction.id)
    # locks: faction_members -> faction_qm_items (global order)
    member = fcr.member_row(db, ctx.character.id, fid, lock=True)
    if member is None or member.status != fc.STATUS_ACTIVE:
        if ctx.faction.is_secret:
            raise secret_refusal(ctx.npc)
        raise FactionError(403, MSG_MEMBERS_ONLY.format(name=ctx.faction.name))
    row = _lock(db, db.query(models.FactionQmItem).filter(models.FactionQmItem.id == int(body.qm_item_id))).first()
    if row is None or int(row.faction_id) != fid or not row.is_active:
        raise FactionError(404, MSG_ITEM_NOT_FOUND)
    ranks = {int(r.id): r for r in fcr.load_ranks(db, [fid]).get(fid, [])}
    rank = ranks.get(int(member.rank_id)) if member.rank_id else None
    min_rank = ranks.get(int(row.min_rank_id)) if row.min_rank_id else None
    if min_rank is not None and not fe.rank_allows(int(rank.sort_order) if rank is not None else None,
                                                   int(min_rank.sort_order)):
        raise FactionError(403, MSG_NEED_RANK.format(name=min_rank.name))
    if db.execute(text("SELECT id FROM items WHERE id = :i"), {"i": int(row.item_id)}).first() is None:
        raise FactionError(404, MSG_ITEM_NOT_FOUND)
    quantity = int(body.quantity)
    taken = db.execute(text("UPDATE faction_qm_items SET stock = stock - :q, updated_at = :now "
                            "WHERE id = :id AND stock >= :q"),
                       {"q": quantity, "id": int(row.id), "now": now}).rowcount
    if not taken:
        raise FactionError(409, MSG_NO_STOCK)
    total = fe.qm_total(int(row.price), int(rank.qm_discount_pct or 0) if rank is not None else 0, quantity)
    # Review #1: the purchase row is written BEFORE the ledger op (global order: faction_qm_purchases before
    # characters / econ_accounts); a failed posting raises FactionError and the caller rolls everything back.
    purchase = models.FactionQmPurchase(
        character_id=int(ctx.character.id), faction_id=fid, qm_item_id=int(row.id), npc_id=int(ctx.npc.id),
        item_id=int(row.item_id), quantity=quantity, price_total=total, op_key=key, status=P_PENDING, attempts=0,
        next_attempt_at=now, created_at=now, updated_at=now)
    db.add(purchase)
    try:
        db.flush()
    except IntegrityError:                                  # UNIQUE(op_key): the same request_id raced in
        raise FactionError(409, MSG_DONE)
    try:
        posting = econ_ledger.post_operation(                # LAST: locks characters -> econ_accounts
            db, op_type=core.OP_FACTION_QM_SALE,
            legs=[core.Leg(core.AccountRef.character(ctx.character.id), core.AccountRef.faction(fid), total)],
            source_service=SOURCE_SERVICE, idempotency_key=key, apply_tax=False, location_id=ctx.location_id,
            metadata={"faction_id": fid, "npc_id": int(ctx.npc.id), "qm_item_id": int(row.id),
                      "item_id": int(row.item_id), "quantity": quantity})
    except core.InsufficientFunds:
        raise FactionError(400, crud.insufficient_funds_message(db))
    except core.DuplicateOperation:
        raise FactionError(409, MSG_DONE)
    return {"purchase_id": int(purchase.id), "faction_id": fid, "price_total": int(total),
            "new_balance": int(posting.balances.get(int(ctx.character.id), 0)) if posting.balances else 0}


# =====================================================================================================================
# delivery outbox
# =====================================================================================================================

def _factory() -> Callable[[], Session]:
    import database  # late: tests patch database.SessionLocal
    return database.SessionLocal


def _http_post(url: str, payload: dict):
    import faction_rewards  # the shared network seam (tests replace faction_rewards.http_post)
    return faction_rewards.http_post(url, payload)


def _inventory_url(character_id: int) -> str:
    import faction_rewards
    return faction_rewards.inventory_url(character_id)


def _set(db: Session, purchase_id: int, now: datetime, status: str, *, error: Optional[str] = None,
         next_attempt_at: Optional[datetime] = None, expect: Optional[str] = None) -> int:
    params = {"s": status, "now": now, "id": int(purchase_id), "err": (error or None) and str(error)[:255]}
    sql = "UPDATE faction_qm_purchases SET status = :s, updated_at = :now, last_error = :err"
    if next_attempt_at is not None:
        sql += ", next_attempt_at = :next"
        params["next"] = next_attempt_at
    sql += " WHERE id = :id"
    if expect is not None:
        sql += " AND status = :expect"
        params["expect"] = expect
    return int(db.execute(text(sql), params).rowcount or 0)


def deliver(factory: Callable[[], Session], purchase_id: int, now: Optional[datetime] = None) -> Optional[str]:
    """Claim + deliver one purchase. Returns the resulting status (None = not claimed by this call)."""
    now = now or now_utc()
    db = factory()
    try:
        claimed = db.execute(text(
            "UPDATE faction_qm_purchases SET status = :sending, attempts = attempts + 1, updated_at = :now "
            "WHERE id = :id AND status = :pending"),
            {"sending": P_SENDING, "pending": P_PENDING, "now": now, "id": int(purchase_id)}).rowcount
        db.commit()
        if not claimed:
            return None
        row = db.get(models.FactionQmPurchase, int(purchase_id), populate_existing=True)
        if row is None:
            return None
        url = _inventory_url(row.character_id)
        payload = {"item_id": int(row.item_id), "quantity": int(row.quantity)}
        attempts = int(row.attempts)
        db.rollback()                                       # nothing open while the HTTP call runs
        try:
            response = _http_post(url, payload)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            return _retry_or_refund(factory, db, purchase_id, attempts, f"connect: {type(exc).__name__}", now)
        except httpx.HTTPError as exc:                      # read / write timeout, broken response: maybe applied
            _set(db, purchase_id, now, P_FAILED, error=f"{UNCERTAIN}: {type(exc).__name__}", expect=P_SENDING)
            db.commit()
            logger.warning("quartermaster purchase %s: delivery uncertain (%s)", purchase_id, type(exc).__name__)
            return P_FAILED
        except Exception as exc:                            # unknown: treat as maybe applied
            _set(db, purchase_id, now, P_FAILED, error=f"{UNCERTAIN}: {type(exc).__name__}", expect=P_SENDING)
            db.commit()
            logger.exception("quartermaster purchase %s: delivery crashed", purchase_id)
            return P_FAILED
        if 200 <= response.status_code < 300:
            _set(db, purchase_id, now, P_DONE, expect=P_SENDING)
            db.commit()
            return P_DONE
        return _retry_or_refund(factory, db, purchase_id, attempts, f"http {response.status_code}", now)
    finally:
        db.close()


def _retry_or_refund(factory, db: Session, purchase_id: int, attempts: int, error: str, now: datetime) -> str:
    if attempts >= MAX_ATTEMPTS:
        _set(db, purchase_id, now, P_FAILED, error=error, expect=P_SENDING)
        db.commit()
        try:
            refund_after_commit(factory, purchase_id, now)
        except Exception:
            logger.exception("quartermaster purchase %s: auto-refund failed", purchase_id)
        return P_REFUNDED
    _set(db, purchase_id, now, P_PENDING, error=error, next_attempt_at=now + backoff(attempts), expect=P_SENDING)
    db.commit()
    return P_PENDING


def recover_stale(factory: Callable[[], Session], now: datetime) -> int:
    db = factory()
    try:
        Row = models.FactionQmPurchase
        ids = [int(r[0]) for r in db.query(Row.id).filter(Row.status == P_SENDING,
                                                          Row.updated_at <= now - STALE_SENDING)
               .order_by(Row.id).limit(BATCH_SIZE).all()]
        count = 0
        for pid in ids:
            count += _set(db, pid, now, P_FAILED, error=f"{UNCERTAIN}: stale", expect=P_SENDING)
            db.commit()
        return count
    finally:
        db.close()


def retry_due(factory: Callable[[], Session], now: datetime) -> Dict[str, int]:
    """5-min pass step: stale claims, then every due pending purchase."""
    stats = {"stale": recover_stale(factory, now), "done": 0, "pending": 0, "failed": 0, "refunded": 0}
    db = factory()
    try:
        Row = models.FactionQmPurchase
        ids = [int(r[0]) for r in db.query(Row.id).filter(Row.status == P_PENDING, Row.next_attempt_at <= now)
               .order_by(Row.id).limit(BATCH_SIZE).all()]
    finally:
        db.close()
    for pid in ids:
        status = deliver(factory, pid, now)
        if status in stats:
            stats[status] += 1
    return stats


# =====================================================================================================================
# refund
# =====================================================================================================================

def _item_name(db: Session, item_id: int) -> str:
    row = db.execute(text("SELECT name FROM items WHERE id = :i"), {"i": int(item_id)}).first()
    return row[0] if row is not None and row[0] else f"#{int(item_id)}"


def refund(db: Session, purchase_id: int, now: Optional[datetime] = None) -> Tuple[str, List[Notice]]:
    """One transaction in the caller's session (caller commits). Returns ('paid' | 'debt', notices)."""
    now = now or now_utc()
    head = db.get(models.FactionQmPurchase, int(purchase_id))
    if head is None:
        raise FactionError(404, MSG_PURCHASE_NOT_FOUND)
    fid, qm_item_id = int(head.faction_id), head.qm_item_id
    # locks: faction_economy -> faction_qm_items -> faction_qm_purchases (global order)
    fec.ensure_economy_row(db, fid, now)
    fec.economy_row(db, fid, lock=True)
    qm_row = None
    if qm_item_id is not None:
        qm_row = _lock(db, db.query(models.FactionQmItem).filter(models.FactionQmItem.id == int(qm_item_id))).first()
    row = _lock(db, db.query(models.FactionQmPurchase).filter(models.FactionQmPurchase.id == int(purchase_id))).first()
    if row is None or row.status not in (P_PENDING, P_FAILED):
        raise FactionError(409, MSG_REFUND_STATE)
    if qm_row is not None:
        qm_row.stock = min(MAX_STOCK, int(qm_row.stock) + int(row.quantity))
        qm_row.updated_at = now
    amount = int(row.price_total)
    outcome = "paid"
    if fec.treasury_balance(db, fid) >= amount:
        econ_ledger.post_operation(
            db, op_type=core.OP_FACTION_QM_REFUND,
            legs=[core.Leg(core.AccountRef.faction(fid), core.AccountRef.character(int(row.character_id)), amount)],
            source_service=SOURCE_SERVICE, idempotency_key=f"faction_qm_refund:p{int(row.id)}", apply_tax=False,
            metadata={"faction_id": fid, "purchase_id": int(row.id)})
    else:
        fec.add_debt(db, character_id=int(row.character_id), faction_id=fid, source=fec.DEBT_REFUND,
                     source_key=f"refund:p{int(row.id)}", amount=amount, now=now, notified=True)
        outcome = "debt"
    row.status = P_REFUNDED
    row.updated_at = now
    db.flush()
    user = db.execute(text("SELECT user_id FROM characters WHERE id = :c"), {"c": int(row.character_id)}).first()
    text_ = (NOTICE_REFUNDED if outcome == "paid" else NOTICE_REFUND_DEBT).format(item=_item_name(db, row.item_id))
    notices = [Notice(int(user[0]) if user is not None and user[0] is not None else None, text_, CATEGORY_PROGRESS,
                      {"faction_id": fid, "character_id": int(row.character_id), "event": "qm_refund"})]
    return outcome, notices


def refund_after_commit(factory: Callable[[], Session], purchase_id: int, now: Optional[datetime] = None) -> None:
    import faction_notify
    db = factory()
    try:
        try:
            _outcome, notices = refund(db, purchase_id, now)
            db.commit()
        except FactionError:
            db.rollback()
            return
        except Exception:
            db.rollback()
            raise
    finally:
        db.close()
    faction_notify.publish(notices)


# =====================================================================================================================
# admin: quartermasters, assortment, purchases
# =====================================================================================================================

def _err(detail: str, status: int = 422) -> FactionError:
    return FactionError(status, detail)


def _int(value, message: str) -> int:
    if isinstance(value, bool):
        raise _err(message)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise _err(message)


def list_quartermasters(db: Session, faction_id: int) -> List[dict]:
    fcr.faction_or_404(db, faction_id)
    rows = db.execute(text(
        "SELECT q.npc_id, c.name, c.npc_role, c.current_location_id, c.npc_status FROM faction_quartermasters q "
        "JOIN characters c ON c.id = q.npc_id WHERE q.faction_id = :f ORDER BY q.npc_id"),
        {"f": int(faction_id)}).fetchall()
    names = fcr.location_names(db, [r[3] for r in rows if r[3]])
    return [{"npc_id": int(r[0]), "name": r[1], "npc_role": r[2],
             "location_id": int(r[3]) if r[3] is not None else None,
             "location_name": names.get(int(r[3])) if r[3] is not None else None,
             "npc_status": r[4] or "alive"} for r in rows]


def set_quartermasters(db: Session, faction_id: int, npc_ids: List[int], now: Optional[datetime] = None) -> List[dict]:
    now = now or now_utc()
    faction = fcr.faction_or_404(db, faction_id)
    ids = []
    for raw in npc_ids or []:
        npc_id = _int(raw, MSG_QM_NPC)
        if npc_id not in ids:
            ids.append(npc_id)
    if len(ids) > MAX_QUARTERMASTERS:
        raise _err(MSG_QMS_MAX)
    if ids:
        ph, params = fcr.in_clause("n", ids)
        npcs = {int(r[0]) for r in db.execute(text(f"SELECT id FROM characters WHERE id IN ({ph}) AND is_npc = 1"),
                                               params).fetchall()}
        for npc_id in ids:
            if npc_id not in npcs:
                raise _err(MSG_QM_NPC)
        taken = db.execute(text(
            f"SELECT q.npc_id, f.name FROM faction_quartermasters q JOIN factions f ON f.id = q.faction_id "
            f"WHERE q.npc_id IN ({ph}) AND q.faction_id <> :fid"), {**params, "fid": int(faction.id)}).fetchall()
        if taken:
            raise _err(MSG_QM_TAKEN.format(name=taken[0][1]), 409)
    current = {int(r.npc_id): r for r in db.query(models.FactionQuartermaster).filter(
        models.FactionQuartermaster.faction_id == int(faction.id)).all()}
    for npc_id, row in current.items():
        if npc_id not in ids:
            db.delete(row)
    for npc_id in ids:
        if npc_id not in current:
            db.add(models.FactionQuartermaster(npc_id=npc_id, faction_id=int(faction.id), created_at=now))
    db.flush()
    return list_quartermasters(db, faction.id)


def _market_info(db: Session, item_ids) -> Dict[int, "core.ItemMarket"]:
    import econ_tick  # late: heavy module
    return econ_tick.load_item_markets(db, item_ids)


def _qm_item_out(row: "models.FactionQmItem", items: Dict[int, dict], markets, ranks: Dict[int, str]) -> dict:
    market = markets.get(int(row.item_id))
    return {"id": int(row.id), "faction_id": int(row.faction_id), "item_id": int(row.item_id),
            "item": items.get(int(row.item_id)), "price": int(row.price),
            "min_rank_id": int(row.min_rank_id) if row.min_rank_id else None,
            "min_rank_name": ranks.get(int(row.min_rank_id)) if row.min_rank_id else None,
            "stock": int(row.stock), "restock_target": int(row.restock_target), "is_active": bool(row.is_active),
            "sort_order": int(row.sort_order), "off_market": bool(market.off_market) if market else True,
            "group": market.group if market else None, "updated_at": row.updated_at}


def list_qm_items(db: Session, faction_id: int) -> List[dict]:
    fcr.faction_or_404(db, faction_id)
    rows = (db.query(models.FactionQmItem).filter(models.FactionQmItem.faction_id == int(faction_id))
            .order_by(models.FactionQmItem.sort_order, models.FactionQmItem.id).all())
    item_ids = [r.item_id for r in rows]
    ranks = {int(r.id): r.name for r in fcr.load_ranks(db, [faction_id]).get(int(faction_id), [])}
    return [_qm_item_out(r, items_info(db, item_ids), _market_info(db, item_ids), ranks) for r in rows]


def _validate_qm_item(db: Session, faction_id: int, body, *, item_id: int) -> dict:
    price = _int(body.price, MSG_PRICE)
    if not 1 <= price <= MAX_PRICE:
        raise _err(MSG_PRICE)
    stock = _int(body.stock, MSG_STOCK)
    if not 0 <= stock <= MAX_STOCK:
        raise _err(MSG_STOCK)
    target = _int(body.restock_target, MSG_TARGET)
    if not 0 <= target <= MAX_STOCK:
        raise _err(MSG_TARGET)
    sort = _int(body.sort_order, MSG_SORT)
    if not -100000 <= sort <= 100000:
        raise _err(MSG_SORT)
    market = _market_info(db, [item_id]).get(int(item_id))
    if market is None:
        raise _err(MSG_ITEM_MISSING)
    if target > 0 and (market.off_market or not market.group):
        raise _err(MSG_OFF_MARKET)
    min_rank = None
    if body.min_rank_id is not None:
        rank = db.get(models.FactionRank, _int(body.min_rank_id, MSG_RANK_FOREIGN))
        if rank is None or int(rank.faction_id) != int(faction_id):
            raise _err(MSG_RANK_FOREIGN)
        min_rank = int(rank.id)
    return {"price": price, "stock": stock, "restock_target": target, "sort_order": sort,
            "min_rank_id": min_rank, "is_active": bool(body.is_active)}


def create_qm_item(db: Session, faction_id: int, body, now: Optional[datetime] = None) -> dict:
    now = now or now_utc()
    faction = fcr.faction_or_404(db, faction_id)
    item_id = _int(body.item_id, MSG_ITEM_MISSING)
    data = _validate_qm_item(db, faction.id, body, item_id=item_id)
    if db.query(models.FactionQmItem.id).filter(models.FactionQmItem.faction_id == int(faction.id),
                                                models.FactionQmItem.item_id == item_id).first():
        raise _err(MSG_ITEM_DUP, 409)
    row = models.FactionQmItem(faction_id=int(faction.id), item_id=item_id, updated_at=now, **data)
    db.add(row)
    db.flush()
    ranks = {int(r.id): r.name for r in fcr.load_ranks(db, [faction.id]).get(int(faction.id), [])}
    return _qm_item_out(row, items_info(db, [item_id]), _market_info(db, [item_id]), ranks)


def _qm_item_or_404(db: Session, qm_item_id: int, *, lock: bool = False) -> "models.FactionQmItem":
    query = db.query(models.FactionQmItem).filter(models.FactionQmItem.id == int(qm_item_id))
    row = (_lock(db, query) if lock else query).first()
    if row is None:
        raise _err(MSG_QM_ITEM_NOT_FOUND, 404)
    return row


def update_qm_item(db: Session, qm_item_id: int, body, now: Optional[datetime] = None) -> dict:
    now = now or now_utc()
    row = _qm_item_or_404(db, qm_item_id, lock=True)
    item_id = _int(body.item_id, MSG_ITEM_MISSING) if body.item_id is not None else int(row.item_id)
    data = _validate_qm_item(db, row.faction_id, body, item_id=item_id)
    if item_id != int(row.item_id) and db.query(models.FactionQmItem.id).filter(
            models.FactionQmItem.faction_id == int(row.faction_id), models.FactionQmItem.item_id == item_id).first():
        raise _err(MSG_ITEM_DUP, 409)
    row.item_id = item_id
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = now
    db.flush()
    ranks = {int(r.id): r.name for r in fcr.load_ranks(db, [row.faction_id]).get(int(row.faction_id), [])}
    return _qm_item_out(row, items_info(db, [item_id]), _market_info(db, [item_id]), ranks)


def delete_qm_item(db: Session, qm_item_id: int) -> None:
    row = _qm_item_or_404(db, qm_item_id)
    db.delete(row)                                          # purchases keep their item_id (qm_item_id SET NULL)
    db.flush()


def purchase_out(r: "models.FactionQmPurchase", names: Dict[int, dict], items: Dict[int, dict]) -> dict:
    return {"id": int(r.id), "faction_id": int(r.faction_id),
            "character": {"id": int(r.character_id), "name": (names.get(int(r.character_id)) or {}).get("name")},
            "item": items.get(int(r.item_id)) or {"id": int(r.item_id), "name": None},
            "qm_item_id": int(r.qm_item_id) if r.qm_item_id is not None else None,
            "npc_id": int(r.npc_id) if r.npc_id is not None else None, "quantity": int(r.quantity),
            "price_total": int(r.price_total), "status": r.status, "attempts": int(r.attempts),
            "next_attempt_at": r.next_attempt_at, "last_error": r.last_error, "created_at": r.created_at,
            "updated_at": r.updated_at}


def list_purchases(db: Session, faction_id: int, status: Optional[str], page: int, page_size: int) -> dict:
    fcr.faction_or_404(db, faction_id)
    page, page_size = max(1, int(page)), max(1, min(PAGE_SIZE_MAX, int(page_size)))
    if status not in (None, "", "all") and status not in PURCHASE_STATUSES:
        raise _err(MSG_STATUS)
    query = db.query(models.FactionQmPurchase).filter(models.FactionQmPurchase.faction_id == int(faction_id))
    if status in PURCHASE_STATUSES:
        query = query.filter(models.FactionQmPurchase.status == status)
    total = query.count()
    rows = query.order_by(models.FactionQmPurchase.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    names = fcr.character_brief(db, [r.character_id for r in rows])
    items = items_info(db, [r.item_id for r in rows])
    return {"items": [purchase_out(r, names, items) for r in rows], "total": int(total), "page": page,
            "page_size": page_size}


def character_purchases(db: Session, character_id: int, limit: int = 100) -> List[dict]:
    rows = (db.query(models.FactionQmPurchase).filter(models.FactionQmPurchase.character_id == int(character_id))
            .order_by(models.FactionQmPurchase.id.desc()).limit(limit).all())
    names = fcr.character_brief(db, [character_id])
    items = items_info(db, [r.item_id for r in rows])
    return [purchase_out(r, names, items) for r in rows]


def retry_purchase(db: Session, purchase_id: int, now: Optional[datetime] = None) -> int:
    """failed -> pending (attempts reset). Returns the purchase id to deliver after the commit."""
    now = now or now_utc()
    row = db.get(models.FactionQmPurchase, int(purchase_id))
    if row is None:
        raise _err(MSG_PURCHASE_NOT_FOUND, 404)
    updated = db.execute(text(
        "UPDATE faction_qm_purchases SET status = :p, attempts = 0, next_attempt_at = :now, last_error = NULL, "
        "updated_at = :now WHERE id = :id AND status = :f"),
        {"p": P_PENDING, "f": P_FAILED, "now": now, "id": int(row.id)}).rowcount
    if not updated:
        raise _err(MSG_RETRY_STATE, 409)
    return int(row.id)
