"""FEAT-205 §3.6: delivery of rank rewards (the ``faction_reward_deliveries`` outbox).

Grants + delivery rows are created in the rank-up transaction (``faction_crud.grant_rank``). Here, AFTER that commit,
each row is claimed by a conditional UPDATE (pending -> sending, attempts + 1, committed) and delivered:

* ``xp``      — one transaction: passive XP + row ``done``; then ``crud.check_and_update_level`` (post-commit). Once.
* ``title``   — ``crud.grant_title`` (idempotent by ``character_titles``), then ``done``.
* ``item``    — HTTP to inventory (NOT idempotent). The claim is committed BEFORE the call. 2xx -> done; connection
                refused / 4xx / 5xx (definitely not applied) -> back to pending with backoff, failed after
                :data:`MAX_ITEM_ATTEMPTS`; timeout / read error (ambiguous) -> ``failed`` with ``last_error='uncertain'``,
                never auto-retried (an admin can press «Повторить»).
* ``voucher`` — HTTP to locations (idempotent by ``source_key``) -> retried on any error, failed after
                :data:`MAX_VOUCHER_ATTEMPTS`.

Rows stuck in ``sending`` longer than :data:`STALE_SENDING`: xp / title / voucher -> pending; item -> failed uncertain.
Retries run from the periodic pass (``faction_pass``). The level-up hook only records while a delivery runs
(``faction_hooks.collecting``), so a rank-reward XP -> level-up -> new rank chain never recurses: the outer loop
picks the new rows up (at most :data:`MAX_ROUNDS` rounds; the ladder is finite and grants are unique anyway).
"""

import logging
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

import faction_core as fc
import faction_crud
import faction_hooks
import models
from config import settings

logger = logging.getLogger("character-service.faction_rewards")

HTTP_TIMEOUT_SECONDS = 5.0
MAX_ITEM_ATTEMPTS = 5
MAX_VOUCHER_ATTEMPTS = 10
MAX_OTHER_ATTEMPTS = 10
MAX_ROUNDS = 10
MAX_BACKOFF_MINUTES = 24 * 60
STALE_SENDING = timedelta(minutes=10)
BATCH_SIZE = 200


def _factory() -> Callable[[], Session]:
    import database  # late: tests patch database.SessionLocal
    return database.SessionLocal


def _headers() -> dict:
    import crud
    return crud._internal_token_headers()


def http_post(url: str, payload: dict) -> httpx.Response:
    """THE network seam of the outbox (tests replace it)."""
    return httpx.post(url, json=payload, headers=_headers(), timeout=HTTP_TIMEOUT_SECONDS)


def inventory_url(character_id: int) -> str:
    return f"{settings.INVENTORY_SERVICE_URL.rstrip('/')}/internal/characters/{int(character_id)}/items"


def voucher_url() -> str:
    return f"{settings.LOCATIONS_SERVICE_URL.rstrip('/')}/locations/houses/internal/vouchers"


def backoff(attempts: int) -> timedelta:
    return timedelta(minutes=min(MAX_BACKOFF_MINUTES, 2 ** max(0, int(attempts))))


class _Retry(Exception):
    """Definitely not applied -> back to pending (or failed past the attempt limit)."""


class _Uncertain(Exception):
    """Maybe applied -> failed, never auto-retried."""


class _Fatal(Exception):
    """Can never succeed (missing title, ...) -> failed."""


# --------------------------------------------------------------------------------------------------- row state

def _claim(db: Session, delivery_id: int, now: datetime) -> bool:
    result = db.execute(text(
        "UPDATE faction_reward_deliveries SET status = :sending, attempts = attempts + 1, updated_at = :now "
        "WHERE id = :id AND status = :pending"),
        {"sending": fc.DLV_SENDING, "pending": fc.DLV_PENDING, "now": now, "id": int(delivery_id)})
    db.commit()
    return (result.rowcount or 0) == 1


def _set(db: Session, delivery_id: int, now: datetime, status: str, *, error: Optional[str] = None,
         next_attempt_at: Optional[datetime] = None) -> None:
    params = {"s": status, "now": now, "id": int(delivery_id), "err": (error or None) and str(error)[:255]}
    sql = "UPDATE faction_reward_deliveries SET status = :s, updated_at = :now, last_error = :err"
    if next_attempt_at is not None:
        sql += ", next_attempt_at = :next"
        params["next"] = next_attempt_at
    db.execute(text(sql + " WHERE id = :id"), params)


def _grant_info(db: Session, grant_id: int) -> Dict[str, object]:
    row = db.execute(text(
        "SELECT g.faction_id, r.name, f.name FROM faction_rank_grants g "
        "JOIN faction_ranks r ON r.id = g.rank_id JOIN factions f ON f.id = g.faction_id WHERE g.id = :g"),
        {"g": int(grant_id)}).first()
    if row is None:
        return {"faction_id": None, "rank_name": None, "faction_name": None}
    return {"faction_id": int(row[0]), "rank_name": row[1], "faction_name": row[2]}


def _log_failure(db: Session, delivery: "models.FactionRewardDelivery", error: str, now: datetime) -> None:
    info = _grant_info(db, delivery.grant_id)
    if info["faction_id"] is None:
        return
    faction_crud.log_event(db, character_id=int(delivery.character_id), faction_id=int(info["faction_id"]),
                           event_type=fc.EV_REWARD_FAILED, now=now,
                           reason=f"{delivery.kind}#{int(delivery.id)}: {error}"[:500])


def _fail(db: Session, delivery: "models.FactionRewardDelivery", error: str, now: datetime) -> None:
    _set(db, delivery.id, now, fc.DLV_FAILED, error=error)
    _log_failure(db, delivery, error, now)
    db.commit()
    logger.warning("faction reward delivery %s (%s) failed: %s", delivery.id, delivery.kind, error)


def _retry_or_fail(db: Session, delivery: "models.FactionRewardDelivery", error: str, now: datetime,
                   max_attempts: int) -> None:
    if int(delivery.attempts) >= max_attempts:
        _fail(db, delivery, error, now)
        return
    _set(db, delivery.id, now, fc.DLV_PENDING, error=error, next_attempt_at=now + backoff(delivery.attempts))
    db.commit()


# --------------------------------------------------------------------------------------------------- kinds

def _deliver_xp(db: Session, delivery, now: datetime) -> None:
    import crud
    xp = int((delivery.payload or {}).get("xp") or 0)
    total = crud.add_passive_xp(db, delivery.character_id, xp) if xp > 0 else None
    if xp > 0 and total is None:
        db.rollback()
        raise _Retry("no_attributes")
    _set(db, delivery.id, now, fc.DLV_DONE)
    db.commit()
    if total is not None:
        crud.check_and_update_level(db, int(delivery.character_id), int(total))     # post-commit, hook collects


def _deliver_title(db: Session, delivery, now: datetime) -> None:
    import crud
    title_id = int((delivery.payload or {}).get("title_id") or 0)
    ok, reason = crud.grant_title(db, int(delivery.character_id), title_id, xp_multiplier=None)
    if ok is None:
        raise _Fatal(str(reason))
    _set(db, delivery.id, now, fc.DLV_DONE)
    db.commit()


def _deliver_item(db: Session, delivery, now: datetime) -> None:
    payload = delivery.payload or {}
    url = inventory_url(delivery.character_id)             # read before the rollback expires the row
    db.rollback()                                           # nothing open while the HTTP call runs
    try:
        response = http_post(url,
                             {"item_id": int(payload.get("item_id") or 0),
                              "quantity": int(payload.get("quantity") or 0)})
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
        raise _Retry(f"connect: {type(exc).__name__}")
    except httpx.HTTPError as exc:                          # read / write timeout, broken response: maybe applied
        raise _Uncertain(type(exc).__name__)
    if 200 <= response.status_code < 300:
        _set(db, delivery.id, now, fc.DLV_DONE)
        db.commit()
        return
    raise _Retry(f"http {response.status_code}")


def _deliver_voucher(db: Session, delivery, now: datetime) -> None:
    payload = delivery.payload or {}
    info = _grant_info(db, delivery.grant_id)
    kind = payload.get("kind") or fc.VOUCHER_READY
    what = "дом" if kind == fc.VOUCHER_READY else "участок"
    source_text = f"Награда за звание «{info['rank_name'] or '—'}» ({info['faction_name'] or '—'}): {what}"
    body = {
        "character_id": int(delivery.character_id),
        "location_id": int(payload.get("location_id") or 0),
        "kind": kind,
        "source_key": f"faction:grant:{int(delivery.grant_id)}:voucher:{kind}",
        "source_text": source_text[:255],
    }
    db.rollback()                                           # nothing open while the HTTP call runs
    try:
        response = http_post(voucher_url(), body)
    except httpx.HTTPError as exc:
        raise _Retry(type(exc).__name__)
    if 200 <= response.status_code < 300:
        _set(db, delivery.id, now, fc.DLV_DONE)
        db.commit()
        return
    raise _Retry(f"http {response.status_code}")


_HANDLERS = {
    fc.KIND_XP: (_deliver_xp, MAX_OTHER_ATTEMPTS),
    fc.KIND_TITLE: (_deliver_title, MAX_OTHER_ATTEMPTS),
    fc.KIND_ITEM: (_deliver_item, MAX_ITEM_ATTEMPTS),
    fc.KIND_VOUCHER: (_deliver_voucher, MAX_VOUCHER_ATTEMPTS),
}


def deliver_one(factory: Callable[[], Session], delivery_id: int, now: Optional[datetime] = None) -> Optional[str]:
    """Claim and deliver one row. Returns the resulting status (None = not claimed by this call)."""
    db = factory()
    try:
        now = now or faction_crud.now_utc()
        if not _claim(db, delivery_id, now):
            return None
        delivery = db.get(models.FactionRewardDelivery, int(delivery_id), populate_existing=True)
        if delivery is None:
            return None
        handler, max_attempts = _HANDLERS.get(delivery.kind, (None, 0))
        if handler is None:
            _fail(db, delivery, "unknown_kind", now)
            return fc.DLV_FAILED
        try:
            handler(db, delivery, now)
            return fc.DLV_DONE
        except _Retry as exc:
            db.rollback()
            _retry_or_fail(db, delivery, str(exc), now, max_attempts)
            return fc.DLV_PENDING
        except _Uncertain as exc:
            db.rollback()
            _fail(db, delivery, f"{fc.DLV_UNCERTAIN}: {exc}", now)
            return fc.DLV_FAILED
        except _Fatal as exc:
            db.rollback()
            _fail(db, delivery, str(exc), now)
            return fc.DLV_FAILED
        except Exception as exc:
            db.rollback()
            logger.exception("faction reward delivery %s crashed", delivery_id)
            if delivery.kind == fc.KIND_ITEM:
                _fail(db, delivery, f"{fc.DLV_UNCERTAIN}: {type(exc).__name__}", now)
                return fc.DLV_FAILED
            _retry_or_fail(db, delivery, type(exc).__name__, now, max_attempts)
            return fc.DLV_PENDING
    finally:
        db.close()


def _due_ids(factory: Callable[[], Session], character_id: Optional[int], now: datetime) -> List[int]:
    db = factory()
    try:
        # ORM (not raw text): the DateTime comparison goes through the column type on every dialect.
        Row = models.FactionRewardDelivery
        query = db.query(Row.id).filter(Row.status == fc.DLV_PENDING, Row.next_attempt_at <= now)
        if character_id is not None:
            query = query.filter(Row.character_id == int(character_id))
        return [int(r[0]) for r in query.order_by(Row.id).limit(BATCH_SIZE).all()]
    finally:
        db.close()


def deliver_pending(character_id: Optional[int] = None, session_factory: Optional[Callable[[], Session]] = None,
                    now: Optional[datetime] = None) -> Dict[str, int]:
    """Deliver the due pending rows (of one character, or all with None). Sync; HTTP inside; never in a transaction.
    Publishes the notices collected from level-ups it caused (unless an outer collector owns them)."""
    factory = session_factory or _factory()
    stats = {"done": 0, "pending": 0, "failed": 0}
    owner = not faction_hooks.is_collecting()
    with faction_hooks.collecting() as bucket:
        for _round in range(MAX_ROUNDS):
            ids = _due_ids(factory, character_id, now or faction_crud.now_utc())
            if not ids:
                break
            progressed = False
            for delivery_id in ids:
                status = deliver_one(factory, delivery_id, now)
                if status is None:
                    continue
                stats[status if status in stats else "failed"] += 1
                progressed = progressed or status == fc.DLV_DONE
            if not progressed:
                break
    if character_id is not None:
        # FEAT-206 §3.5: rank marks wait in the debt queue — settle the character's factions (own transactions)
        try:
            import faction_econ_crud
            faction_econ_crud.settle_for_character(int(character_id), factory, now)
        except Exception:
            logger.exception("faction debts of character %s not settled", character_id)
    if owner and bucket.notices:
        import faction_notify
        faction_notify.publish(bucket.notices)
    return stats


def recover_stale(factory: Callable[[], Session], now: datetime) -> int:
    """Rows stuck in ``sending``: xp / title / voucher -> pending; item -> failed uncertain."""
    db = factory()
    count = 0
    try:
        rows = (db.query(models.FactionRewardDelivery)
                .filter(models.FactionRewardDelivery.status == fc.DLV_SENDING,
                        models.FactionRewardDelivery.updated_at <= now - STALE_SENDING)
                .order_by(models.FactionRewardDelivery.id).limit(BATCH_SIZE).all())
        for row in rows:
            try:
                if row.kind == fc.KIND_ITEM:
                    updated = db.execute(text(
                        "UPDATE faction_reward_deliveries SET status = :f, last_error = :e, updated_at = :now "
                        "WHERE id = :id AND status = :s"),
                        {"f": fc.DLV_FAILED, "e": f"{fc.DLV_UNCERTAIN}: stale", "now": now, "id": int(row.id),
                         "s": fc.DLV_SENDING}).rowcount
                    if updated:
                        _log_failure(db, row, f"{fc.DLV_UNCERTAIN}: stale", now)
                else:
                    updated = db.execute(text(
                        "UPDATE faction_reward_deliveries SET status = :p, next_attempt_at = :now, updated_at = :now "
                        "WHERE id = :id AND status = :s"),
                        {"p": fc.DLV_PENDING, "now": now, "id": int(row.id), "s": fc.DLV_SENDING}).rowcount
                db.commit()
                count += int(updated or 0)
            except Exception:
                db.rollback()
                logger.exception("faction: stale delivery %s not recovered", row.id)
    finally:
        db.close()
    return count


def retry_due(factory: Callable[[], Session], now: datetime) -> Dict[str, int]:
    """Periodic pass step: stale rows, then every due pending row (all characters)."""
    stats = {"stale": recover_stale(factory, now), "done": 0, "pending": 0, "failed": 0}
    out = deliver_pending(None, factory, now)
    for key in ("done", "pending", "failed"):
        stats[key] += out.get(key, 0)
    return stats
