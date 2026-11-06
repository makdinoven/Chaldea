"""FEAT-206 faction economy — DB flows (sync SQLAlchemy). features/FEAT-206 §3.5-§3.7, §3.10.

* economy rows / settings / effective params / wealth reads (players see words only, §3.9);
* the debt queue: :func:`settle_debts` pays a faction's open debts FIFO from its treasury in its OWN transaction
  (``faction_economy`` FOR UPDATE -> open debts ascending FOR UPDATE -> one ``faction_payout`` op, key
  ``faction_payout:f<fid>:s<seq>``); :func:`settle_after_commit` is the post-commit best-effort wrapper;
* donations (:func:`donate`, one transaction, ``faction_donation`` op character -> faction);
* the 6 h tick step (:func:`plan_pass` + :func:`faction_step`, called from ``econ_tick._faction_econ_pass``);
* the admin economy flows (view / update / fill / history / operations / debts / templates).

Every money move is ONE ledger operation per transaction (``econ_ledger.post_operation`` locks characters and accounts
last, in its fixed order). Global lock order: see ``econ_tick`` docstring (FEAT-206 §3.6): ... ``faction_members (asc
id) → faction_economy (asc faction_id) → faction_qm_items (asc id) → faction_item_stock (asc faction_id, item_id;
FEAT-207) → faction_debts (asc id) → faction_donation_days → faction_pvp_kills (FEAT-207) → faction_qm_purchases →
character_inventory → characters (asc id) → econ_accounts (asc id)``.
No HTTP inside any transaction here.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import econ_core as core
import econ_ledger
import faction_core as fc
import faction_crud as fcr
import faction_econ as fe
import models
from faction_crud import FactionError, FlowResult
from faction_notify import CATEGORY_PROGRESS, Notice

logger = logging.getLogger("character-service.faction_econ_crud")

SOURCE_SERVICE = "character-service"

DEBT_OPEN = "open"
DEBT_PAID = "paid"
DEBT_STATUSES = (DEBT_OPEN, DEBT_PAID)
DEBT_RANK = "rank"
DEBT_REFUND = "refund"

MAX_DONATION = 1_000_000
PAGE_SIZE_MAX = 50
MAX_MEMBERS = 100_000
TEMPLATE_CODE_RE = r"^[a-z0-9_]{2,32}$"

MSG_DONATION_DONE = "Это пожертвование уже выполнено"
MSG_DONATION_AMOUNT = "Сумма пожертвования: от 1 до 1000000"
MSG_NOT_MEMBER = fcr.MSG_NOT_MEMBER
MSG_NPC = "NPC не может жертвовать фракциям"
MSG_NEED_TEMPLATE = "Сначала выберите шаблон"
MSG_TEMPLATE_NOT_FOUND = "Шаблон не найден"
MSG_TEMPLATE_USED = "Шаблон используется"
MSG_TEMPLATE_EXISTS = "Шаблон с таким кодом уже есть"
MSG_TEMPLATE_CODE = "Код шаблона: от 2 до 32 символов — латиница в нижнем регистре, цифры и «_»"
MSG_TEMPLATE_NAME = "Название шаблона: от 1 до 100 символов"
MSG_TEMPLATE_DESCRIPTION = "Описание шаблона: до 500 символов"
MSG_SORT = "Порядок: от -100000 до 100000"
MSG_MEMBERS = "Число участников: от 0 до 100000"
MSG_MEMBERS_BOUNDS = "Границы числа участников: от 0 до 100000, минимум не больше максимума"
MSG_COMMENT = "Комментарий: от 3 до 500 символов"
MSG_STATUS = "Неизвестный статус"

NOTICE_DEBT_RANK = ("Казна фракции «{faction}» сейчас пуста: {amount} за звание записаны в долг. "
                    "Выплатим, когда казна пополнится")
NOTICE_DEBT_PAID = "Фракция «{faction}» выплатила долг: {amount}"


# =====================================================================================================================
# settings, rows, params
# =====================================================================================================================

def now_utc() -> datetime:
    return fcr.now_utc()


def today_utc(now: Optional[datetime] = None) -> date:
    return (now or now_utc()).date()


def seconds_to_next_day(now: datetime) -> int:
    tomorrow = datetime(now.year, now.month, now.day) + timedelta(days=1)
    return max(0, int((tomorrow - now).total_seconds()))


def load_econ_settings(db: Session) -> fe.EconSettings:
    return fe.econ_settings_from_row(db.get(models.FactionSettings, 1))


def _lock(db: Session, query):
    if fcr.for_update(db):
        return query.with_for_update().populate_existing()
    return query


def economy_row(db: Session, faction_id: int, *, lock: bool = False) -> Optional["models.FactionEconomy"]:
    query = db.query(models.FactionEconomy).filter(models.FactionEconomy.faction_id == int(faction_id))
    if lock:
        query = _lock(db, query)
    return query.first()


def ensure_economy_row(db: Session, faction_id: int, now: Optional[datetime] = None) -> "models.FactionEconomy":
    """The faction's economy row, inserted (in the caller's transaction) when missing."""
    row = economy_row(db, faction_id)
    if row is None:
        row = models.FactionEconomy(faction_id=int(faction_id), updated_at=now or now_utc())
        db.add(row)
        db.flush()
    return row


def templates_by_code(db: Session) -> Dict[str, "models.FactionEconTemplate"]:
    return {t.code: t for t in db.query(models.FactionEconTemplate).all()}


def params_of(row: Optional["models.FactionEconomy"],
              templates: Mapping[str, "models.FactionEconTemplate"]) -> Optional[fe.FactionEconParams]:
    """Effective params (None = no template -> no economy)."""
    if row is None or not row.template_code:
        return None
    template = templates.get(row.template_code)
    if template is None:
        return None
    return fe.effective_params(template.params, row.overrides)


def treasury_balances(db: Session, faction_ids: Iterable[int]) -> Dict[int, int]:
    ids = sorted({int(f) for f in faction_ids})
    if not ids:
        return {}
    ph, params = fcr.in_clause("f", ids)
    rows = db.execute(text(f"SELECT ref_id, balance FROM econ_accounts WHERE kind = :k AND ref_id IN ({ph})"),
                      {"k": core.KIND_FACTION_TREASURY, **params}).fetchall()
    return {int(r[0]): int(r[1] or 0) for r in rows}


def treasury_balance(db: Session, faction_id: int) -> int:
    return treasury_balances(db, [faction_id]).get(int(faction_id), 0)


def treasury_account(db: Session, faction_id: int) -> Tuple[Optional[int], int]:
    row = db.execute(text("SELECT id, balance FROM econ_accounts WHERE kind = :k AND ref_id = :r"),
                     {"k": core.KIND_FACTION_TREASURY, "r": int(faction_id)}).first()
    return (int(row[0]), int(row[1] or 0)) if row is not None else (None, 0)


def wealth_values(db: Session, faction_ids: Iterable[int]) -> Dict[int, Optional[int]]:
    """{faction_id: wealth 0..100 | None (no template)} — staff numbers; players get words via :func:`wealth_words`."""
    ids = sorted({int(f) for f in faction_ids})
    if not ids:
        return {}
    rows = {int(r.faction_id): r for r in db.query(models.FactionEconomy).filter(
        models.FactionEconomy.faction_id.in_(ids)).all()}
    templates = templates_by_code(db) if rows else {}
    balances = treasury_balances(db, ids)
    out: Dict[int, Optional[int]] = {}
    for fid in ids:
        params = params_of(rows.get(fid), templates)
        if params is None:
            out[fid] = None
            continue
        out[fid] = fe.wealth(balances.get(fid, 0), fe.norm(int(rows[fid].members_count or 0), params))
    return out


def wealth_words(db: Session, faction_ids: Iterable[int]) -> Dict[int, Optional[dict]]:
    try:
        return {fid: fe.wealth_word(value) for fid, value in wealth_values(db, faction_ids).items()}
    except SQLAlchemyError:          # stage-2 tables not migrated yet: no words, never a broken catalog
        db.rollback()
        logger.warning("faction econ: wealth words not read", exc_info=True)
        return {}


# =====================================================================================================================
# debts
# =====================================================================================================================

def add_debt(db: Session, *, character_id: int, faction_id: int, source: str, source_key: str, amount: int,
             now: datetime, notified: bool = False) -> Optional["models.FactionDebt"]:
    """Insert a debt row (caller's transaction). ``amount <= 0`` -> nothing."""
    if int(amount) <= 0:
        return None
    row = models.FactionDebt(character_id=int(character_id), faction_id=int(faction_id), source=source,
                             source_key=source_key, amount=int(amount), paid=0, status=DEBT_OPEN,
                             unpaid_notified=bool(notified), created_at=now)
    db.add(row)
    db.flush()
    return row


def open_debt_totals(db: Session, character_id: int) -> Dict[int, int]:
    """{faction_id: unpaid remaining} of the character's open debts."""
    rows = db.execute(text(
        "SELECT faction_id, COALESCE(SUM(amount - paid), 0) FROM faction_debts "
        "WHERE character_id = :c AND status = :s GROUP BY faction_id"),
        {"c": int(character_id), "s": DEBT_OPEN}).fetchall()
    return {int(r[0]): int(r[1] or 0) for r in rows}


def factions_with_open_debts(db: Session, character_id: Optional[int] = None) -> List[int]:
    sql = "SELECT DISTINCT faction_id FROM faction_debts WHERE status = :s"
    params = {"s": DEBT_OPEN}
    if character_id is not None:
        sql += " AND character_id = :c"
        params["c"] = int(character_id)
    return sorted(int(r[0]) for r in db.execute(text(sql + " ORDER BY faction_id"), params).fetchall())


def _forms(db: Session):
    try:
        return econ_ledger.get_currency_forms(db)
    except Exception:
        return core.DEFAULT_FORMS


def debt_notices(db: Session, faction: "models.Faction", debts: Sequence["models.FactionDebt"],
                 paid_now: Mapping[int, int]) -> List[Notice]:
    """§3.5 notices for debts touched by a settle / tick step (flags set in the caller's transaction):
    still unpaid + never notified -> «записаны в долг» (+ flag); notified earlier + now paid in full -> «выплатила»."""
    if not debts:
        return []
    ph, params = fcr.in_clause("c", sorted({int(d.character_id) for d in debts}))
    users = {int(r[0]): (int(r[1]) if r[1] is not None else None) for r in db.execute(text(
        f"SELECT id, user_id FROM characters WHERE id IN ({ph})"), params).fetchall()}
    forms = _forms(db)
    out: List[Notice] = []
    for debt in debts:
        user_id = users.get(int(debt.character_id))
        data = {"faction_id": int(faction.id), "character_id": int(debt.character_id), "event": "debt"}
        remaining = int(debt.amount) - int(debt.paid)
        if debt.status == DEBT_OPEN and remaining > 0 and not debt.unpaid_notified:
            debt.unpaid_notified = True
            if debt.source == DEBT_RANK:
                out.append(Notice(user_id, NOTICE_DEBT_RANK.format(faction=faction.name,
                                                                  amount=core.format_currency(remaining, forms)),
                                  CATEGORY_PROGRESS, data))
        elif debt.status == DEBT_PAID and debt.unpaid_notified and int(paid_now.get(int(debt.id), 0)) > 0:
            out.append(Notice(user_id, NOTICE_DEBT_PAID.format(faction=faction.name,
                                                              amount=core.format_currency(int(debt.amount), forms)),
                              CATEGORY_PROGRESS, data))
    return out


def apply_debt_payments(debts: Sequence["models.FactionDebt"], paid: Mapping[int, int], now: datetime) -> None:
    for debt in debts:
        amount = int(paid.get(int(debt.id), 0))
        if amount <= 0:
            continue
        debt.paid = min(int(debt.amount), int(debt.paid) + amount)
        if int(debt.paid) >= int(debt.amount):
            debt.status = DEBT_PAID
            debt.paid_at = now


def lock_open_debts(db: Session, faction_id: int) -> List["models.FactionDebt"]:
    query = (db.query(models.FactionDebt)
             .filter(models.FactionDebt.faction_id == int(faction_id), models.FactionDebt.status == DEBT_OPEN)
             .order_by(models.FactionDebt.id))
    return _lock(db, query).all()


def debt_inputs(debts: Sequence["models.FactionDebt"]) -> List[fe.DebtIn]:
    return [fe.DebtIn(int(d.id), int(d.character_id), int(d.amount) - int(d.paid)) for d in debts
            if int(d.amount) > int(d.paid)]


def settle_debts(db: Session, faction_id: int, now: Optional[datetime] = None) -> List[Notice]:
    """Pay the faction's open debts FIFO from its treasury — OWN transaction (commits / rolls back ``db``).
    Returns the notices to publish after the commit. Nothing to pay -> no op, no seq bump (flags still set)."""
    now = now or now_utc()
    db.rollback()
    try:
        faction = db.get(models.Faction, int(faction_id))
        if faction is None:
            db.rollback()
            return []
        ensure_economy_row(db, faction.id, now)
        econ = economy_row(db, faction.id, lock=True)
        debts = lock_open_debts(db, faction.id)
        if not debts:
            db.rollback()
            return []
        balance = treasury_balance(db, faction.id)
        paid, by_char, _left = fe.plan_debts(balance, debt_inputs(debts))
        if by_char:
            seq = int(econ.payout_seq or 0) + 1
            treasury = core.AccountRef.faction(faction.id)
            econ_ledger.post_operation(
                db, op_type=core.OP_FACTION_PAYOUT,
                legs=[core.Leg(treasury, core.AccountRef.character(cid), amount)
                      for cid, amount in sorted(by_char.items())],
                source_service=SOURCE_SERVICE, idempotency_key=f"faction_payout:f{int(faction.id)}:s{seq}",
                metadata={"faction_id": int(faction.id), "debts": {str(k): v for k, v in sorted(paid.items())}},
                apply_tax=False)
            econ.payout_seq = seq
            apply_debt_payments(debts, paid, now)
        notices = debt_notices(db, faction, debts, paid)
        db.commit()
        if by_char:
            logger.info("faction %s: paid %d marks of debts to %d characters", faction.id, sum(by_char.values()),
                        len(by_char))
        return notices
    except Exception:
        db.rollback()
        raise


def _factory() -> Callable[[], Session]:
    import database  # late: tests patch database.SessionLocal
    return database.SessionLocal


def settle_after_commit(faction_ids: Iterable[int], session_factory: Optional[Callable[[], Session]] = None,
                        now: Optional[datetime] = None) -> int:
    """Best effort, post-commit: settle each faction in its own session, publish the notices. Never raises.
    Returns how many factions were settled without an error."""
    import faction_notify
    ids = sorted({int(f) for f in faction_ids or ()})
    if not ids:
        return 0
    factory = session_factory or _factory()
    done = 0
    for fid in ids:
        db = factory()
        try:
            notices = settle_debts(db, fid, now)
            done += 1
        except core.DuplicateOperation:
            logger.info("faction %s: concurrent debt settle, skipped", fid)
            continue
        except Exception:
            logger.exception("faction %s: debt settle failed", fid)
            continue
        finally:
            db.close()
        if notices:
            faction_notify.publish(notices)
    return done


def settle_for_character(character_id: int, session_factory: Optional[Callable[[], Session]] = None,
                         now: Optional[datetime] = None) -> int:
    """Settle every faction the character has an open debt with (post-commit, best effort)."""
    factory = session_factory or _factory()
    db = factory()
    try:
        fids = factions_with_open_debts(db, character_id)
    except Exception:
        logger.exception("faction debts of character %s not read", character_id)
        return 0
    finally:
        db.rollback()
        db.close()
    return settle_after_commit(fids, factory, now)


def sweep_debts(session_factory: Callable[[], Session], now: datetime) -> int:
    """5-min pass: settle every faction with open debts (covers admin adjustments / emissions)."""
    db = session_factory()
    try:
        fids = factions_with_open_debts(db)
    finally:
        db.rollback()
        db.close()
    return settle_after_commit(fids, session_factory, now)


# =====================================================================================================================
# player reads (§3.9)
# =====================================================================================================================

def member_extras(db: Session, character_id: int, memberships: Sequence[dict], now: datetime) -> None:
    """Adds ``wealth`` (active only), ``debt`` (any status) and ``donation`` (active only) to private-view entries."""
    try:
        debts = open_debt_totals(db, character_id)
        active = [m["faction"]["id"] for m in memberships if m["status"] == fc.STATUS_ACTIVE]
        words = wealth_words(db, active)
        s = load_econ_settings(db)
        day = today_utc(now)
        day_rows = {int(r.faction_id): r for r in db.query(models.FactionDonationDay).filter(
            models.FactionDonationDay.character_id == int(character_id),
            models.FactionDonationDay.day == day).all()}
    except SQLAlchemyError:
        db.rollback()
        logger.warning("faction econ: private extras of character %s not read", character_id, exc_info=True)
        debts, words, s, day_rows = {}, {}, fe.DEFAULT_ECON_SETTINGS, {}
    reset_in = seconds_to_next_day(now)
    for entry in memberships:
        fid = int(entry["faction"]["id"])
        is_active = entry["status"] == fc.STATUS_ACTIVE
        entry["debt"] = int(debts.get(fid, 0))
        entry["wealth"] = words.get(fid) if is_active else None
        if is_active:
            row = day_rows.get(fid)
            entry["donation"] = {
                "enabled": True,
                "marks_per_point": int(s.donation_marks_per_point),
                "daily_cap": int(s.donation_points_daily_cap),
                "points_today": int(row.points) if row is not None else 0,
                "marks_today": int(row.marks) if row is not None else 0,
                "resets_in_seconds": reset_in,
            }
            entry["donation"].update(_items_status(db, fid))                  # FEAT-207
        else:
            entry["donation"] = None


def _items_status(db: Session, faction_id: int) -> dict:
    """FEAT-207: whether the faction accepts item donations now (its economy ticks)."""
    import faction_items  # late: it imports this module
    try:
        faction = db.get(models.Faction, int(faction_id))
        if faction is None:
            return {"items_enabled": False, "items_disabled_reason": None}
        enabled, reason = faction_items.items_status(db, faction)
    except SQLAlchemyError:
        db.rollback()
        logger.warning("faction %s: item donation status not read", faction_id, exc_info=True)
        return {"items_enabled": False, "items_disabled_reason": None}
    return {"items_enabled": bool(enabled), "items_disabled_reason": reason}


# =====================================================================================================================
# donations (§3.7)
# =====================================================================================================================

def donation_key(character_id: int, request_id: str) -> str:
    return f"faction_donation:c{int(character_id)}:{request_id}"


def operation_exists(db: Session, key: str) -> bool:
    return db.execute(text(core.SQL_SELECT_OPERATION_BY_KEY), {"key": key}).first() is not None


def ensure_day_row(db: Session, character_id: int, faction_id: int, day: date) -> None:
    """The zero donation day row in its OWN short transaction (commits / rolls back ``db``)."""
    db.rollback()
    exists = db.execute(text("SELECT 1 FROM faction_donation_days WHERE character_id = :c AND faction_id = :f "
                             "AND day = :d"), {"c": int(character_id), "f": int(faction_id), "d": day}).first()
    if exists is not None:
        db.rollback()
        return
    try:
        db.add(models.FactionDonationDay(character_id=int(character_id), faction_id=int(faction_id), day=day,
                                         marks=0, points=0))
        db.commit()
    except IntegrityError:
        db.rollback()       # created by a concurrent request


def _lock_members(db: Session, character_id: int, faction_ids: Iterable[int]) -> Dict[int, "models.FactionMember"]:
    """Membership rows of one character in the given factions, locked in ascending id (global order)."""
    ids = sorted({int(f) for f in faction_ids})
    if not ids:
        return {}
    query = (db.query(models.FactionMember)
             .filter(models.FactionMember.character_id == int(character_id),
                     models.FactionMember.faction_id.in_(ids))
             .order_by(models.FactionMember.id))
    return {int(m.faction_id): m for m in _lock(db, query).all()}


def donate(db: Session, character_id: int, faction_id: int, amount: int, request_id: str,
           now: Optional[datetime] = None) -> FlowResult:
    """§3.7. Raises FactionError (Russian). The caller (API ``_write``) commits."""
    import crud  # late: crud is heavy
    now = now or now_utc()
    if isinstance(amount, bool) or not 1 <= int(amount) <= MAX_DONATION:
        raise FactionError(422, MSG_DONATION_AMOUNT)
    amount = int(amount)
    ch = fcr.require_character(db, character_id)
    if ch.is_npc:
        raise FactionError(403, MSG_NPC)
    faction = fcr.faction_or_404(db, faction_id)
    key = donation_key(ch.id, request_id)
    if operation_exists(db, key):
        raise FactionError(409, MSG_DONATION_DONE)
    member = fcr.member_row(db, ch.id, faction.id)
    if member is None or member.status != fc.STATUS_ACTIVE:
        raise FactionError(404, MSG_NOT_MEMBER)
    day = today_utc(now)
    ensure_day_row(db, ch.id, faction.id, day)              # commits / rolls back: nothing is open before this

    s_core = fcr.load_settings(db)
    s = load_econ_settings(db)
    hostile = sorted(fcr.hostile_map(db).get(int(faction.id), set()))
    members = _lock_members(db, ch.id, [faction.id, *hostile])
    member = members.get(int(faction.id))
    if member is None or member.status != fc.STATUS_ACTIVE:
        raise FactionError(404, MSG_NOT_MEMBER)
    day_row = _lock(db, db.query(models.FactionDonationDay).filter(
        models.FactionDonationDay.character_id == ch.id, models.FactionDonationDay.faction_id == int(faction.id),
        models.FactionDonationDay.day == day)).first()
    if day_row is None:                                      # purged between the two transactions
        day_row = models.FactionDonationDay(character_id=ch.id, faction_id=int(faction.id), day=day, marks=0,
                                            points=0)
        db.add(day_row)
        db.flush()

    # Review #1: every row write (day row, points, log, rank grants -> faction_debts INSERT) happens BEFORE the ledger
    # op, which locks characters + econ_accounts last (global order: faction_debts before characters / econ_accounts;
    # settle_debts and the tick step take debts -> accounts). A failed / duplicate posting raises FactionError and the
    # caller rolls the whole transaction back, so nothing of the above survives without the money move.
    gain, points_today = fe.donation_points(int(day_row.marks), amount, s.donation_marks_per_point,
                                            s.donation_points_daily_cap, int(day_row.points))
    day_row.marks = int(day_row.marks) + amount
    day_row.points = points_today
    event_key = f"faction:donate:c{ch.id}:{request_id}"
    reason = f"marks:{amount}"
    if gain > 0:
        actual = fcr.change_points(db, member, gain, fc.EV_DONATION, now, event_key=event_key, reason=reason)
        penalty = fc.hostile_penalty(gain, s_core.hostile_penalty_pct)
        for other in hostile:
            if penalty <= 0:
                break
            other_member = members.get(int(other))
            if other_member is None or other_member.status != fc.STATUS_ACTIVE:
                continue
            fcr.change_points(db, other_member, -penalty, fc.EV_HOSTILE, now,
                              event_key=f"{event_key}:hostile:{int(faction.id)}", reason=f"faction:{int(faction.id)}")
    else:
        actual = 0
        fcr.log_event(db, character_id=ch.id, faction_id=faction.id, event_type=fc.EV_DONATION, now=now,
                      points_delta=0, points_after=int(member.points), rank_id=member.rank_id, event_key=event_key,
                      reason=reason)
    db.flush()
    rechecked = fcr.recheck_ranks(db, ch.id, now)           # may INSERT faction_debts (rank reward marks)
    try:
        posting = econ_ledger.post_operation(                # LAST: locks characters -> econ_accounts
            db, op_type=core.OP_FACTION_DONATION,
            legs=[core.Leg(core.AccountRef.character(ch.id), core.AccountRef.faction(faction.id), amount)],
            source_service=SOURCE_SERVICE, idempotency_key=key, apply_tax=False,
            metadata={"faction_id": int(faction.id), "request_id": request_id})
    except core.InsufficientFunds:
        raise FactionError(400, crud.insufficient_funds_message(db))
    except core.DuplicateOperation:
        raise FactionError(409, MSG_DONATION_DONE)
    result = FlowResult()
    result.merge(rechecked)
    result.data = {
        "points_delta": int(actual),
        "points_after": int(member.points),
        "points_today": int(points_today),
        "daily_cap": int(s.donation_points_daily_cap),
        "marks_today": int(day_row.marks),
        "rank_ups": int(rechecked.data.get("rank_ups", 0)),
        "new_balance": int(posting.balances.get(ch.id, 0)) if posting.balances else 0,
        "faction_id": int(faction.id),
    }
    return result


# =====================================================================================================================
# 6 h tick step (§3.6) — orchestrated by econ_tick._faction_econ_pass
# =====================================================================================================================

@dataclass(frozen=True)
class TickJob:
    faction_id: int
    region_id: int
    budgets: fe.Budgets


@dataclass
class StepOutcome:
    status: str                         # done | already | skipped | failed
    posted: bool = False
    notices: List[Notice] = field(default_factory=list)
    plan: Optional[fe.FactionStepPlan] = None


SQL_TICKING = (
    "SELECT f.id, f.hq_location_id, e.template_code FROM factions f "
    "JOIN faction_economy e ON e.faction_id = f.id "
    "WHERE f.is_active = 1 AND e.econ_enabled = 1 AND e.template_code IS NOT NULL AND f.hq_location_id IS NOT NULL "
    "ORDER BY f.id"
)

SQL_REGION_PARTICIPATING = (
    "SELECT e.region_id, e.last_income FROM econ_regions e JOIN Regions r ON r.id = e.region_id "
    "WHERE e.region_id = :r AND e.template_code IS NOT NULL AND e.population > 0"
)


def not_ticking_reason(db: Session, faction: "models.Faction", econ: Optional["models.FactionEconomy"],
                       s: fe.EconSettings) -> Tuple[Optional[str], Optional[int], bool]:
    """(reason | None, hq region id, hq simulated) — Russian reason for the admin view."""
    region_id = None
    simulated = False
    if faction.hq_location_id:
        region_id, _country = econ_ledger.resolve_location(db, int(faction.hq_location_id))
        if region_id is not None:
            simulated = db.execute(text(SQL_REGION_PARTICIPATING), {"r": int(region_id)}).first() is not None
    if not s.econ_enabled:
        return "Экономика фракций выключена в настройках", region_id, simulated
    if not faction.is_active:
        return "Фракция скрыта", region_id, simulated
    if econ is None or not econ.econ_enabled:
        return "Экономика этой фракции выключена", region_id, simulated
    if econ.template_code is None:
        return "Не выбран шаблон", region_id, simulated
    if not faction.hq_location_id:
        return "Не задан штаб", region_id, simulated
    if region_id is None:
        return "Штаб не относится ни к одному краю", region_id, simulated
    if not simulated:
        return "Край штаба не участвует в экономике", region_id, simulated
    return None, region_id, simulated


def plan_pass(db: Session) -> List[TickJob]:
    """Plain reads (no locks): ticking factions grouped by HQ region, regional caps split by wants (§3.6 #1)."""
    s = load_econ_settings(db)
    if not s.econ_enabled:
        return []
    templates = templates_by_code(db)
    candidates: Dict[int, List[Tuple[int, fe.Wants]]] = {}
    region_info: Dict[int, Tuple[int, int, int]] = {}
    for fid, hq, _code in db.execute(text(SQL_TICKING)).fetchall():
        region_id, _country = econ_ledger.resolve_location(db, int(hq))
        if region_id is None:
            continue
        if region_id not in region_info:
            row = db.execute(text(SQL_REGION_PARTICIPATING), {"r": int(region_id)}).first()
            if row is None:
                region_info[region_id] = (-1, 0, 0)
            else:
                purse = treasury = 0
                for kind, ref in ((core.KIND_POPULATION_PURSE, "p"), (core.KIND_REGION_TREASURY, "t")):
                    value = db.execute(text("SELECT balance FROM econ_accounts WHERE kind = :k AND ref_id = :r"),
                                       {"k": kind, "r": int(region_id)}).scalar()
                    if ref == "p":
                        purse = int(value or 0)
                    else:
                        treasury = int(value or 0)
                region_info[region_id] = (int(row[1] or 0), purse, treasury)
        last_income, purse, treasury = region_info[region_id]
        if last_income < 0:
            continue                                    # HQ region not simulated
        econ = economy_row(db, fid)
        params = params_of(econ, templates)
        if params is None:
            continue
        want = fe.wants(int(econ.members_count or 0), params, region_treasury=treasury, last_income=last_income)
        candidates.setdefault(region_id, []).append((int(fid), want))
    jobs: List[TickJob] = []
    for region_id, items in candidates.items():
        _income, purse, treasury = region_info[region_id]
        purse_cap, treasury_cap = fe.regional_caps(purse, treasury, s)
        purse_split = fe.split_cap(purse_cap, {fid: w.purse for fid, w in items})
        treasury_split = fe.split_cap(treasury_cap, {fid: w.profile_treasury for fid, w in items})
        # FEAT-207 §3.8: donated item sales — a separate share of the HQ purse split by the stock value
        sales_split = fe.split_cap((max(0, int(purse)) * int(s.econ_item_sale_share_pct)) // 100,
                                   _sales_wants(db, [fid for fid, _w in items], region_id))
        for fid, _w in items:
            jobs.append(TickJob(fid, region_id, fe.Budgets(purse_split.get(fid, 0), treasury_split.get(fid, 0),
                                                           sales_split.get(fid, 0))))
    return sorted(jobs, key=lambda j: j.faction_id)


def _sales_wants(db: Session, faction_ids: Sequence[int], region_id: int) -> Dict[int, int]:
    """FEAT-207: {faction_id: value of its donated item stock in the HQ region} (0 when nothing to sell)."""
    import faction_items  # late: it imports this module
    out: Dict[int, int] = {}
    for fid in faction_ids:
        try:
            out[int(fid)] = faction_items.stock_value(db, fid, region_id)
        except SQLAlchemyError:
            db.rollback()
            logger.warning("faction %s: item stock value not read", fid, exc_info=True)
            out[int(fid)] = 0
    return out


def _restock_candidates(db: Session, faction_id: int) -> List[Tuple[int, int]]:
    """(qm_item_id, item_id) of active rows below their restock target (plain read)."""
    return [(int(r[0]), int(r[1])) for r in db.execute(text(
        "SELECT id, item_id FROM faction_qm_items WHERE faction_id = :f AND is_active = 1 "
        "AND restock_target > stock ORDER BY id"), {"f": int(faction_id)}).fetchall()]


def _sale_candidates(db: Session, faction_id: int) -> List[int]:
    """FEAT-207: item ids of the faction's donated stock (quantity > 0, plain read)."""
    return [int(r[0]) for r in db.execute(text(
        "SELECT item_id FROM faction_item_stock WHERE faction_id = :f AND quantity > 0 ORDER BY item_id"),
        {"f": int(faction_id)}).fetchall()]


def _round_stock(value: float) -> Decimal:
    return Decimal(str(round(max(0.0, float(value)), 3)))


def faction_step(db: Session, job: TickJob, *, run_id: int, now: datetime, wholesale_share,
                 load_item_markets: Callable) -> StepOutcome:
    """One faction's step in the caller's transaction (caller commits / rolls back). Raises DuplicateOperation when
    another runner already posted it (the caller skips)."""
    fid, region_id = int(job.faction_id), int(job.region_id)
    s = load_econ_settings(db)
    # groups the restock may need (plain read before any lock; re-filtered under the locks)
    candidates = _restock_candidates(db, fid)
    # FEAT-207: donated items waiting for the sale (only with a sales budget)
    sale_candidates = _sale_candidates(db, fid) if int(job.budgets.sales or 0) > 0 else []
    items = load_item_markets(db, [item_id for _qid, item_id in candidates] + sale_candidates) \
        if candidates or sale_candidates else {}
    wanted_groups = sorted({items[i].group for i in [i for _q, i in candidates] + sale_candidates
                            if i in items and items[i].group and not items[i].off_market})

    # locks: econ_regions(hq) -> econ_region_goods (asc group) -> faction_economy -> qm rows -> debts
    region = _lock(db, db.query(models.EconRegion).filter(models.EconRegion.region_id == region_id)).first()
    if region is None or region.template_code is None or int(region.population or 0) <= 0:
        return StepOutcome("skipped")
    goods_rows = []
    if wanted_groups:
        goods_rows = _lock(db, db.query(models.EconRegionGood).filter(
            models.EconRegionGood.region_id == region_id,
            models.EconRegionGood.group_code.in_(wanted_groups)).order_by(models.EconRegionGood.group_code)).all()
    econ = economy_row(db, fid, lock=True)
    faction = db.get(models.Faction, fid)
    if econ is None or faction is None:
        return StepOutcome("skipped")
    if econ.last_run_id is not None and int(econ.last_run_id) == int(run_id):
        return StepOutcome("already")
    templates = templates_by_code(db)
    params = params_of(econ, templates)
    if params is None or not econ.econ_enabled or not faction.is_active or not s.econ_enabled:
        return StepOutcome("skipped")
    qm_rows = _lock(db, db.query(models.FactionQmItem).filter(
        models.FactionQmItem.faction_id == fid, models.FactionQmItem.is_active.is_(True),
        models.FactionQmItem.restock_target > models.FactionQmItem.stock).order_by(models.FactionQmItem.id)).all()
    stock_rows = []                                     # FEAT-207 §3.10: faction_item_stock after the qm rows
    if sale_candidates:
        stock_rows = _lock(db, db.query(models.FactionItemStock).filter(
            models.FactionItemStock.faction_id == fid, models.FactionItemStock.quantity > 0)
            .order_by(models.FactionItemStock.item_id)).all()
    debts = lock_open_debts(db, fid)

    purse = econ_ledger_balance(db, core.AccountRef.purse(region_id))
    treasury = econ_ledger_balance(db, core.AccountRef.region(region_id))
    balance = treasury_balance(db, fid)
    group_base = {g.code: int(g.base_price or 0) for g in db.query(models.EconGoodsGroup).all()}
    market = {g.group_code: fe.MarketGroupIn(stock=float(g.stock or 0), price_mult=Decimal(str(g.price_mult or 1)),
                                             group_base=group_base.get(g.group_code, 0)) for g in goods_rows}
    missing = [int(r.item_id) for r in qm_rows if int(r.item_id) not in items]
    if missing:
        items.update(load_item_markets(db, missing))
    restock_in = []
    for row in qm_rows:
        item = items.get(int(row.item_id))
        if item is None or item.off_market or not item.group or item.group not in market:
            continue
        restock_in.append(fe.RestockRowIn(int(row.id), item.group, int(row.stock), int(row.restock_target),
                                          int(item.price or 0)))
    sale_in = []
    if stock_rows:
        import economy_guild_crud
        quest = economy_guild_crud.quest_item_ids(db, [int(r.item_id) for r in stock_rows])
        for row in stock_rows:
            item = items.get(int(row.item_id))
            if item is None or item.off_market or not item.group or item.group not in market \
                    or int(row.item_id) in quest:
                continue                                # cannot be sold now: the row stays (admin sees it)
            sale_in.append(fe.SaleRowIn(int(row.item_id), item.group, int(row.quantity), int(item.price or 0)))
    state = fe.FactionStateIn(fid, region_id, int(econ.members_count or 0), Decimal(str(econ.members_carry or 0)),
                              int(econ.members_min), int(econ.members_max))
    plan = fe.plan_faction_step(state, params, s, job.budgets, purse=purse, region_treasury=treasury,
                                last_income=int(region.last_income or 0), balance=balance,
                                open_debts=debt_inputs(debts), restock_rows=restock_in, market=market,
                                wholesale_share=Decimal(str(wholesale_share)), sale_rows=sale_in)

    outcome = StepOutcome("done", plan=plan)
    if plan.legs:
        posting = econ_ledger.post_operation(
            db, op_type=core.OP_FACTION_TICK, legs=plan.legs, source_service=SOURCE_SERVICE, region_id=region_id,
            idempotency_key=f"faction_tick:{int(run_id)}:f{fid}", apply_tax=False,
            metadata={"run_id": int(run_id), "faction_id": fid, "dues": plan.dues, "profile": plan.profile,
                      "wages_due": plan.wages_due, "wages_paid": plan.wages_paid,
                      "restock": {str(k): v for k, v in sorted(plan.restock.items())},
                      "debts": {str(k): v for k, v in sorted(plan.debts.items())},
                      **({"item_sales": {str(k): v for k, v in sorted(plan.sale.items())}} if plan.sale else {})})
        outcome.posted = posting.operation_id is not None
    by_id = {int(r.id): r for r in qm_rows}
    for qm_id, n in plan.restock.items():
        by_id[qm_id].stock = int(by_id[qm_id].stock) + int(n)
        by_id[qm_id].updated_at = now
    by_item = {int(r.item_id): r for r in stock_rows}
    for item_id, n in plan.sale.items():                # FEAT-207: sold donated items leave the stock
        by_item[item_id].quantity = max(0, int(by_item[item_id].quantity) - int(n))
        by_item[item_id].updated_at = now
    for good in goods_rows:
        delta = plan.stock_delta.get(good.group_code)
        if delta:
            good.stock = _round_stock(float(good.stock or 0) + delta)
    apply_debt_payments(debts, plan.debts, now)
    econ.members_count = plan.members_after
    econ.members_carry = plan.carry_after
    econ.last_run_id = int(run_id)
    econ.last_tick_at = now
    econ.last_dues = plan.dues
    econ.last_profile = plan.profile
    econ.last_wages_due = plan.wages_due
    econ.last_wages_paid = plan.wages_paid
    econ.last_restock = plan.restock_spent
    econ.last_debts_paid = plan.debts_paid
    econ.last_members_delta = plan.members_delta
    econ.last_wealth = plan.wealth_after
    econ.last_item_sales = plan.item_sales
    econ.updated_at = now
    db.add(models.FactionEconHistory(
        run_id=int(run_id), faction_id=fid, balance_before=plan.balance_before, balance_after=plan.balance_after,
        dues=plan.dues, profile=plan.profile, wages_due=plan.wages_due, wages_paid=plan.wages_paid,
        restock_spent=plan.restock_spent, restock_items=plan.restock_items, debts_paid=plan.debts_paid,
        members_before=plan.members_before, members_after=plan.members_after, wealth=plan.wealth_after,
        created_at=now, item_sales=plan.item_sales, items_sold=plan.items_sold))
    outcome.notices = debt_notices(db, faction, debts, plan.debts)
    db.flush()
    return outcome


def econ_ledger_balance(db: Session, ref: core.AccountRef) -> int:
    value = db.execute(text("SELECT balance FROM econ_accounts WHERE kind = :k AND ref_id = :r"),
                       {"k": ref.kind, "r": int(ref.ref_id)}).scalar()
    return int(value or 0)


def purge_history(db: Session, cutoff: datetime) -> None:
    db.execute(text("DELETE FROM faction_econ_history WHERE created_at < :cutoff"), {"cutoff": cutoff})


# =====================================================================================================================
# admin (§3.10)
# =====================================================================================================================

def _err(detail: str, status: int = 422) -> FactionError:
    return FactionError(status, detail)


def _page(page: int, page_size: int) -> Tuple[int, int]:
    return max(1, int(page)), max(1, min(PAGE_SIZE_MAX, int(page_size)))


def _template_out(t: "models.FactionEconTemplate", used_by: int = 0) -> dict:
    return {"code": t.code, "name": t.name, "description": t.description,
            "params": fe.effective_params(t.params, None).as_dict(), "sort_order": int(t.sort_order or 0),
            "updated_at": t.updated_at, "used_by": int(used_by)}


def economy_view(db: Session, faction_id: int) -> dict:
    faction = fcr.faction_or_404(db, faction_id)
    fid = int(faction.id)
    econ = economy_row(db, fid)
    templates = templates_by_code(db)
    params = params_of(econ, templates)
    s = load_econ_settings(db)
    account_id, balance = treasury_account(db, fid)
    members = int(econ.members_count or 0) if econ is not None else 0
    norm_value = fe.norm(members, params) if params is not None else None
    wealth_value = fe.wealth(balance, norm_value) if params is not None else None
    reason, region_id, simulated = not_ticking_reason(db, faction, econ, s)
    hq = None
    if faction.hq_location_id:
        loc_name = fcr.location_names(db, [faction.hq_location_id]).get(int(faction.hq_location_id))
        region_name = None
        if region_id is not None:
            row = db.execute(text("SELECT name FROM Regions WHERE id = :r"), {"r": int(region_id)}).first()
            region_name = row[0] if row is not None else None
        hq = {"location_id": int(faction.hq_location_id), "location_name": loc_name, "region_id": region_id,
              "region_name": region_name, "simulated": bool(simulated)}
    debt_row = db.execute(text("SELECT COUNT(*), COALESCE(SUM(amount - paid), 0) FROM faction_debts "
                               "WHERE faction_id = :f AND status = :s"), {"f": fid, "s": DEBT_OPEN}).first()
    qms = db.execute(text(
        "SELECT q.npc_id, c.name, c.npc_role FROM faction_quartermasters q JOIN characters c ON c.id = q.npc_id "
        "WHERE q.faction_id = :f ORDER BY q.npc_id"), {"f": fid}).fetchall()
    template = templates.get(econ.template_code) if econ is not None and econ.template_code else None
    return {
        "faction_id": fid,
        "template_code": econ.template_code if econ is not None else None,
        "template_name": template.name if template is not None else None,
        "overrides": dict(econ.overrides or {}) if econ is not None else {},
        "params": params.as_dict() if params is not None else None,
        "econ_enabled": bool(econ.econ_enabled) if econ is not None else True,
        "members_count": members,
        "members_min": int(econ.members_min) if econ is not None else 10,
        "members_max": int(econ.members_max) if econ is not None else 5000,
        "treasury": {"account_id": account_id, "balance": balance},
        "norm": norm_value,
        "wealth": wealth_value,
        "wealth_label": fe.wealth_word(wealth_value)["label"] if wealth_value is not None else None,
        "hq": hq,
        "ticking": reason is None,
        "not_ticking_reason": reason,
        "last": {
            "tick_at": econ.last_tick_at if econ is not None else None,
            "dues": int(econ.last_dues or 0) if econ is not None else 0,
            "profile": int(econ.last_profile or 0) if econ is not None else 0,
            "wages_due": int(econ.last_wages_due or 0) if econ is not None else 0,
            "wages_paid": int(econ.last_wages_paid or 0) if econ is not None else 0,
            "restock": int(econ.last_restock or 0) if econ is not None else 0,
            "debts_paid": int(econ.last_debts_paid or 0) if econ is not None else 0,
            "members_delta": int(econ.last_members_delta or 0) if econ is not None else 0,
            "item_sales": int(econ.last_item_sales or 0) if econ is not None else 0,          # FEAT-207
        },
        "debts": {"open_count": int(debt_row[0] or 0), "open_total": int(debt_row[1] or 0)},
        "item_stock": _item_stock_view(db, faction),                                          # FEAT-207
        "quartermasters": [{"npc_id": int(r[0]), "name": r[1], "npc_role": r[2]} for r in qms],
    }


def _item_stock_view(db: Session, faction: "models.Faction") -> List[dict]:
    import faction_items  # late: it imports this module
    try:
        return faction_items.stock_view(db, faction)
    except SQLAlchemyError:
        db.rollback()
        logger.warning("faction %s: item stock not read", faction.id, exc_info=True)
        return []


def update_economy(db: Session, faction_id: int, body, now: Optional[datetime] = None) -> None:
    now = now or now_utc()
    faction = fcr.faction_or_404(db, faction_id)
    ensure_economy_row(db, faction.id, now)
    econ = economy_row(db, faction.id, lock=True)
    # partial PUT (exclude_unset): an omitted template_code / overrides keeps the stored value, explicit null clears
    sent = getattr(body, "__fields_set__", None)
    sent = set(sent) if sent is not None else {"template_code", "overrides"}
    if "template_code" in sent:
        code = (body.template_code or "").strip() or None
        if code is not None and db.get(models.FactionEconTemplate, code) is None:
            raise _err(MSG_TEMPLATE_NOT_FOUND, 404)
    else:
        code = econ.template_code
    if "overrides" in sent:
        try:
            overrides = fe.validate_params(body.overrides, partial=True) if body.overrides else None
        except fe.ParamError as exc:
            raise _err(str(exc))
    else:
        overrides = econ.overrides
    lo = int(body.members_min) if body.members_min is not None else int(econ.members_min)
    hi = int(body.members_max) if body.members_max is not None else int(econ.members_max)
    if not (0 <= lo <= MAX_MEMBERS and 0 <= hi <= MAX_MEMBERS and lo <= hi):
        raise _err(MSG_MEMBERS_BOUNDS)
    members = int(body.members_count) if body.members_count is not None else int(econ.members_count)
    if not 0 <= members <= MAX_MEMBERS:
        raise _err(MSG_MEMBERS)
    econ.template_code = code
    econ.overrides = overrides or None
    if body.econ_enabled is not None:
        econ.econ_enabled = bool(body.econ_enabled)
    econ.members_min, econ.members_max = lo, hi
    econ.members_count = min(max(members, lo), hi)
    econ.updated_at = now
    db.flush()


def _fill_key_taken(db: Session, key: str) -> bool:
    """Locking read (MySQL): a concurrent «Заполнить» that waited on ``faction_economy`` FOR UPDATE derived the key from
    its REPEATABLE READ snapshot (stale balance + stale last posting = the same key as the click that just committed);
    a plain read of that snapshot would miss the committed row, the locking read sees it -> emitted 0, not an error."""
    sql = core.SQL_SELECT_OPERATION_BY_KEY + (" FOR UPDATE" if fcr.for_update(db) else "")
    return db.execute(text(sql), {"key": key}).first() is not None


def fill_from_template(db: Session, faction_id: int, comment: str, set_members: bool, actor_user_id: Optional[int],
                       now: Optional[datetime] = None) -> dict:
    """«Заполнить по шаблону»: members (when asked or 0), treasury top-up to members x start/member via ONE
    admin_emission (key stable per account state -> a re-click emits 0). Caller commits; settle post-commit."""
    now = now or now_utc()
    comment = (comment or "").strip()
    if not 3 <= len(comment) <= core.MAX_COMMENT_LEN:
        raise _err(MSG_COMMENT)
    faction = fcr.faction_or_404(db, faction_id)
    ensure_economy_row(db, faction.id, now)
    econ = economy_row(db, faction.id, lock=True)
    params = params_of(econ, templates_by_code(db))
    if params is None:
        raise _err(MSG_NEED_TEMPLATE, 409)
    if set_members or int(econ.members_count or 0) == 0:
        econ.members_count = min(max(int(params.start_members), int(econ.members_min)), int(econ.members_max))
        econ.updated_at = now
    account_id, balance = treasury_account(db, faction.id)
    target = int(econ.members_count) * int(params.start_treasury_per_member)
    top_up = max(0, target - balance)
    emitted = 0
    if top_up > 0:
        last_posting = 0
        if account_id is not None:
            last_posting = int(db.execute(text(
                "SELECT COALESCE(MAX(id), 0) FROM econ_postings WHERE from_account_id = :a OR to_account_id = :a"),
                {"a": account_id}).scalar() or 0)
        key = f"faction_fill:f{int(faction.id)}:p{last_posting}"
        if not _fill_key_taken(db, key):
            try:
                econ_ledger.post_operation(
                    db, op_type=core.OP_ADMIN_EMISSION,
                    legs=[core.Leg(core.AccountRef.emission(), core.AccountRef.faction(faction.id), top_up)],
                    source_service=SOURCE_SERVICE, idempotency_key=key, actor_user_id=actor_user_id,
                    comment=comment, apply_tax=False, metadata={"faction_id": int(faction.id), "fill": True})
                emitted = top_up
            except core.DuplicateOperation:
                pass                      # a concurrent click posted this very top-up: nothing moved, emitted 0
    db.flush()
    return {"members_count": int(econ.members_count), "emitted": emitted,
            "balance": treasury_balance(db, faction.id)}


def history_page(db: Session, faction_id: int, page: int, page_size: int) -> dict:
    fcr.faction_or_404(db, faction_id)
    page, page_size = _page(page, page_size)
    query = db.query(models.FactionEconHistory).filter(models.FactionEconHistory.faction_id == int(faction_id))
    total = query.count()
    rows = query.order_by(models.FactionEconHistory.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [{"id": int(r.id), "run_id": int(r.run_id), "balance_before": int(r.balance_before),
                       "balance_after": int(r.balance_after), "dues": int(r.dues), "profile": int(r.profile),
                       "wages_due": int(r.wages_due), "wages_paid": int(r.wages_paid),
                       "restock_spent": int(r.restock_spent), "restock_items": int(r.restock_items),
                       "debts_paid": int(r.debts_paid), "members_before": int(r.members_before),
                       "members_after": int(r.members_after), "wealth": int(r.wealth), "created_at": r.created_at,
                       "item_sales": int(r.item_sales or 0), "items_sold": int(r.items_sold or 0)}     # FEAT-207
                      for r in rows],
            "total": int(total), "page": page, "page_size": page_size}


def operations_page(db: Session, faction_id: int, page: int, page_size: int) -> dict:
    import economy_crud  # late: heavy module
    fcr.faction_or_404(db, faction_id)
    page, page_size = _page(page, page_size)
    account_id, _balance = treasury_account(db, faction_id)
    if account_id is None:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}
    items, total = economy_crud.list_operations(db, account_id=account_id, character_id=None, op_type=None,
                                                region_id=None, date_from=None, date_to=None, page=page,
                                                page_size=page_size)
    return {"items": items, "total": int(total), "page": page, "page_size": page_size}


def debts_page(db: Session, faction_id: int, status: Optional[str], page: int, page_size: int) -> dict:
    fcr.faction_or_404(db, faction_id)
    page, page_size = _page(page, page_size)
    if status not in (None, "all") and status not in DEBT_STATUSES:
        raise _err(MSG_STATUS)
    query = db.query(models.FactionDebt).filter(models.FactionDebt.faction_id == int(faction_id))
    if status in DEBT_STATUSES:
        query = query.filter(models.FactionDebt.status == status)
    total = query.count()
    rows = query.order_by(models.FactionDebt.id).offset((page - 1) * page_size).limit(page_size).all()
    names = fcr.character_brief(db, [r.character_id for r in rows])
    return {"items": [debt_out(r, names) for r in rows], "total": int(total), "page": page, "page_size": page_size}


def debt_out(r: "models.FactionDebt", names: Mapping[int, dict]) -> dict:
    return {"id": int(r.id), "faction_id": int(r.faction_id),
            "character": {"id": int(r.character_id), "name": (names.get(int(r.character_id)) or {}).get("name")},
            "source": r.source, "amount": int(r.amount), "paid": int(r.paid), "status": r.status,
            "created_at": r.created_at, "paid_at": r.paid_at}


# ---------------------------------------------------------------------------------------------- templates

def list_templates(db: Session) -> List[dict]:
    used = dict(db.query(models.FactionEconomy.template_code, func.count(models.FactionEconomy.faction_id))
                .filter(models.FactionEconomy.template_code.isnot(None))
                .group_by(models.FactionEconomy.template_code).all())
    rows = db.query(models.FactionEconTemplate).order_by(models.FactionEconTemplate.sort_order,
                                                        models.FactionEconTemplate.code).all()
    return [_template_out(t, int(used.get(t.code, 0))) for t in rows]


def _validate_template(body) -> dict:
    name = (body.name or "").strip()
    if not 1 <= len(name) <= 100:
        raise _err(MSG_TEMPLATE_NAME)
    description = (body.description or "").strip() or None
    if description is not None and len(description) > 500:
        raise _err(MSG_TEMPLATE_DESCRIPTION)
    if not -100000 <= int(body.sort_order or 0) <= 100000:
        raise _err(MSG_SORT)
    try:
        params = fe.validate_params(body.params or {}, partial=False)
    except fe.ParamError as exc:
        raise _err(str(exc))
    return {"name": name, "description": description, "params": params, "sort_order": int(body.sort_order or 0)}


def create_template(db: Session, body, now: Optional[datetime] = None) -> dict:
    import re
    now = now or now_utc()
    code = (body.code or "").strip()
    if not re.match(TEMPLATE_CODE_RE, code):
        raise _err(MSG_TEMPLATE_CODE)
    if db.get(models.FactionEconTemplate, code) is not None:
        raise _err(MSG_TEMPLATE_EXISTS, 409)
    row = models.FactionEconTemplate(code=code, updated_at=now, **_validate_template(body))
    db.add(row)
    db.flush()
    return _template_out(row)


def update_template(db: Session, code: str, body, now: Optional[datetime] = None) -> dict:
    now = now or now_utc()
    row = db.get(models.FactionEconTemplate, code)
    if row is None:
        raise _err(MSG_TEMPLATE_NOT_FOUND, 404)
    for key, value in _validate_template(body).items():
        setattr(row, key, value)
    row.updated_at = now
    db.flush()
    used = db.query(func.count(models.FactionEconomy.faction_id)).filter(
        models.FactionEconomy.template_code == code).scalar()
    return _template_out(row, int(used or 0))


def delete_template(db: Session, code: str) -> None:
    row = db.get(models.FactionEconTemplate, code)
    if row is None:
        raise _err(MSG_TEMPLATE_NOT_FOUND, 404)
    if db.query(models.FactionEconomy.faction_id).filter(models.FactionEconomy.template_code == code).first():
        raise _err(MSG_TEMPLATE_USED, 409)
    db.delete(row)
    db.flush()
