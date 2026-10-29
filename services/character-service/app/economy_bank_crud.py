"""FEAT-184 banks — DB layer (sync SQLAlchemy), shared by three parts:

* **player API** (B4, contract 3.9) — banker resolution, view, deposit / withdraw / transfer / send / loan / repay,
  summary, enabled regions;
* **tick passes** (B5, contract 3.7) — orphan purge, bank pass, collection pass (section «Tick helpers» below);
* **admin API** (B6, contract 3.10) — list / detail / debtors / flag / capital / write-off (section «Admin»).

Pure maths lives in ``econ_bank.py``; money moves only through ``econ_ledger.post_operation`` (the last DB step of
every flow, the caller commits). Business refusals raise ``economy_crud.EconomyApiError`` (Russian text + status).

Lock order (3.8, global): ``econ_regions -> econ_region_goods -> npc_shop_items -> econ_banks (asc region_id) ->
bank_deposits (asc id) -> bank_loans (asc id) -> characters (asc id) -> econ_accounts (asc id)``. Every statement that
changes balances or rows of bank X holds ``econ_banks(X) FOR UPDATE`` first. Player flows never lock ``econ_regions``.

Player-flow locks:
    deposit / withdraw at X   econ_banks(X) -> deposit row -> character -> accounts
    transfer A->B / send      econ_banks{A, B} asc -> deposit rows asc (new destination inserted last) ->
                              character (wallet source only) -> accounts
    loan at X / repay to L    econ_banks(X | L) -> the loan row -> character -> accounts

Idempotency: an optional ``request_id`` -> ledger key ``bank:<op>:c<character>:<request_id>``; the key is checked
right after the bank lock (a double submit answers 409 before any business check) and again by the ledger.
"""

import dataclasses
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import activity_lock
import econ_bank
import econ_core as core
import econ_ledger
import models
from economy_crud import EconomyApiError

logger = logging.getLogger("character-service.bank")

SOURCE_SERVICE = "character-service"
BANKER_ROLE = "banker"
NPC_DEAD = "dead"
MAX_TERM_DEPOSITS = 10
DELETED_REGION_NAME = "удалённый регион"

# Ledger idempotency key prefixes (3.2)
KEY_DEPOSIT = "dep"
KEY_WITHDRAW = "wd"
KEY_TRANSFER = "tr"
KEY_SEND = "send"
KEY_LOAN = "loan"
KEY_REPAY = "repay"

# Russian texts (contract 3.9 — tests assert them)
MSG_CHARACTER_NOT_FOUND = "Персонаж не найден"
MSG_NOT_OWNER = "Вы можете управлять только своими персонажами"
MSG_NOT_PLAYER = "Банком пользуются только персонажи игроков"
MSG_BANKER_NOT_FOUND = "Банкир не найден"
MSG_BANKER_DEAD = "Банкир больше не принимает посетителей"
MSG_WRONG_LOCATION = "Подойдите к банкиру — он в другой локации"
MSG_GATE_CLOSED = "Нужен пост-намерение «Диалог с НПС» с этим персонажем"
MSG_GATE_UNAVAILABLE = "Не удалось проверить обращение к банкиру, попробуйте позже"
MSG_NO_BANK = "Этот банкир не служит ни одному банку"
MSG_DUPLICATE = "Операция уже выполнена"
MSG_RETRY = "Не удалось выполнить операцию, попробуйте ещё раз"
MSG_DEPOSITS_CLOSED = "В этом регионе банк не принимает вклады"
MSG_MIN_AMOUNT = "Минимальная сумма — {n}"
MSG_TOO_MANY_TERM = f"Не больше {MAX_TERM_DEPOSITS} срочных вкладов"
MSG_NOT_ENOUGH = "Недостаточно {genitive}"
MSG_NOT_ENOUGH_WITH_FEE = "Недостаточно {genitive}: нужно {total} с учётом комиссии {fee}"
MSG_DEPOSIT_NOT_FOUND = "Вклад не найден"
MSG_OTHER_BANK = "Этот вклад лежит в банке региона «{name}» — снять его можно только там или перевести сюда"
MSG_AMOUNT_REQUIRED = "Укажите сумму"
MSG_DEPOSIT_SHORT = "На вкладе только {n}"
MSG_TERM_NOT_TRANSFERABLE = "Срочный вклад нельзя перевести — дождитесь окончания срока или закройте его"
MSG_SAME_BANK = "Вклад уже в этом банке"
MSG_DEST_CLOSED = "Банк региона «{name}» не принимает вклады"
MSG_DEPOSIT_SHORT_FEE = "На вкладе недостаточно средств с учётом комиссии {fee}"
MSG_RECIPIENT_NOT_FOUND = "Персонаж «{name}» не найден"
MSG_RECIPIENT_AMBIGUOUS = "Найдено несколько персонажей с таким именем"
MSG_SELF_TRANSFER = "Нельзя перевести самому себе"
MSG_LOANS_CLOSED = "Банк этого региона сейчас не выдаёт займы"
MSG_HAS_LOAN = "У вас уже есть займ — сначала погасите его"
MSG_DEBTOR = "Вы в списке должников — новые займы не выдаются"
MSG_LOAN_CAP = "Ваш лимит займа — {cap}"
MSG_BANK_LIMIT = "Банк сейчас может выдать не больше {n}"
MSG_BANK_EMPTY = "У банка сейчас нет денег на займы"
MSG_LOAN_NOT_FOUND = "Займ не найден"


# =====================================================================================================================
# Common helpers (player API, tick, admin)
# =====================================================================================================================

def now_utc() -> datetime:
    """Naive UTC without microseconds (MySQL DATETIME(0) would round them, possibly into the future)."""
    return datetime.utcnow().replace(microsecond=0)


def load_params(db: Session):
    # Lazy import: econ_tick imports this module for the bank passes (B5).
    import econ_tick
    return econ_tick.load_params(db)


def bank_account_balance(db: Session, region_id: int) -> int:
    """Balance of ``bank(region)`` — the bank's own money; 0 when the account does not exist yet."""
    value = db.execute(
        text("SELECT balance FROM econ_accounts WHERE kind = :kind AND ref_id = :ref_id"),
        {"kind": core.KIND_BANK, "ref_id": int(region_id)},
    ).scalar()
    return int(value or 0)


def region_names(db: Session, region_ids: Iterable[int]) -> Dict[int, Tuple[str, Optional[str]]]:
    """``{region_id: (region name, country name)}`` for regions that still exist."""
    ids = sorted({int(i) for i in region_ids if i})
    if not ids:
        return {}
    placeholders, params = core.in_params("r", ids)
    rows = db.execute(text(
        f"SELECT r.id, r.name, c.name FROM Regions r LEFT JOIN Countries c ON c.id = r.country_id "
        f"WHERE r.id IN ({placeholders})"), params).fetchall()
    return {int(r[0]): (r[1], r[2]) for r in rows}


def get_banks(db: Session, region_ids: Iterable[int]) -> Dict[int, "models.EconBank"]:
    """``econ_banks`` rows without a lock (reads)."""
    ids = sorted({int(i) for i in region_ids if i})
    if not ids:
        return {}
    rows = db.query(models.EconBank).filter(models.EconBank.region_id.in_(ids)).all()
    return {int(r.region_id): r for r in rows}


def lock_banks(db: Session, region_ids: Iterable[int]) -> Dict[int, "models.EconBank"]:
    """``econ_banks`` rows ``FOR UPDATE`` in ascending region id (3.8). Missing rows are simply absent."""
    ids = sorted({int(i) for i in region_ids if i})
    if not ids:
        return {}
    rows = (db.query(models.EconBank).filter(models.EconBank.region_id.in_(ids))
            .order_by(models.EconBank.region_id).with_for_update().populate_existing().all())
    return {int(r.region_id): r for r in rows}


def lock_deposits(db: Session, deposit_ids: Iterable[int]) -> Dict[int, "models.BankDeposit"]:
    ids = sorted({int(i) for i in deposit_ids if i})
    if not ids:
        return {}
    rows = (db.query(models.BankDeposit).filter(models.BankDeposit.id.in_(ids))
            .order_by(models.BankDeposit.id).with_for_update().populate_existing().all())
    return {int(r.id): r for r in rows}


def lock_loan(db: Session, loan_id: int) -> Optional["models.BankLoan"]:
    return (db.query(models.BankLoan).filter(models.BankLoan.id == int(loan_id))
            .with_for_update().populate_existing().first())


def bank_is_open(bank: Optional["models.EconBank"], names: Dict[int, tuple]) -> bool:
    """«Банк есть»: the row exists, the flag is on and the region still exists."""
    return bank is not None and bool(bank.is_enabled) and int(bank.region_id) in names


def bank_factor(bank: Optional["models.EconBank"]) -> Decimal:
    return Decimal(str(bank.deposit_rate_factor)) if bank is not None else Decimal(1)


def loan_state(row: "models.BankLoan") -> econ_bank.LoanState:
    return econ_bank.LoanState(
        id=int(row.id), character_id=int(row.character_id), principal=int(row.principal), debt=int(row.debt),
        rate_day=Decimal(str(row.rate_day)), penalty_rate_day=Decimal(str(row.penalty_rate_day)),
        due_at=row.due_at, accrued_at=row.accrued_at, status=row.status, interest_total=int(row.interest_total or 0),
        penalty_total=int(row.penalty_total or 0), interest_carry=Decimal(str(row.interest_carry or 0)),
    )


def apply_loan_state(row: "models.BankLoan", state: econ_bank.LoanState) -> None:
    """Write the accrued loan state back to the row (debt, status, clock, totals, carry)."""
    row.debt = int(state.debt)
    row.status = state.status
    row.accrued_at = state.accrued_at
    row.interest_total = int(state.interest_total)
    row.penalty_total = int(state.penalty_total)
    row.interest_carry = state.interest_carry


def project_loan(row: "models.BankLoan", now: datetime, params) -> econ_bank.LoanState:
    """The loan accrued to ``now`` (not stored)."""
    state = loan_state(row)
    return econ_bank.apply_loan_accrual(state, econ_bank.accrue_loan(state, now, params), now)


def close_deposit_if_empty(row: "models.BankDeposit", now: datetime) -> None:
    if int(row.amount) <= 0 and int(row.interest_accrued or 0) <= 0:
        row.amount = 0
        row.interest_base = 0
        row.status = econ_bank.DEPOSIT_CLOSED
        row.closed_at = now
        row.demand_owner_id = None


def close_loan(row: "models.BankLoan", now: datetime) -> None:
    row.debt = 0
    row.status = econ_bank.LOAN_CLOSED
    row.closed_at = now
    row.active_character_id = None


def _fmt(db: Session, n: int) -> str:
    return core.format_currency(int(n), econ_ledger.get_currency_forms(db))


def _not_enough(db: Session) -> str:
    return MSG_NOT_ENOUGH.format(genitive=econ_ledger.get_currency_forms(db).genitive)


def _msk(value: datetime) -> str:
    return (value + activity_lock.MSK_OFFSET).strftime("%d.%m.%Y %H:%M")


def _key(op: str, character_id: int, request_id: Optional[str]) -> Optional[str]:
    return f"bank:{op}:c{int(character_id)}:{request_id}" if request_id else None


def _check_duplicate(db: Session, key: Optional[str]) -> None:
    if key and db.execute(text(core.SQL_SELECT_OPERATION_BY_KEY), {"key": key}).first() is not None:
        raise EconomyApiError(409, MSG_DUPLICATE)


def _post(db: Session, ctx: "BankerContext", *, op_type: str, legs: Sequence[core.Leg], region_id: int,
          key: Optional[str], metadata: dict, insufficient: str) -> Optional[int]:
    """The ledger posting — always the last DB step of a flow."""
    try:
        result = econ_ledger.post_operation(
            db, op_type=op_type, legs=list(legs), source_service=SOURCE_SERVICE, location_id=ctx.location_id,
            region_id=region_id, actor_user_id=ctx.user_id, metadata=metadata, idempotency_key=key,
        )
    except core.InsufficientFunds:
        raise EconomyApiError(400, insufficient)
    except core.DuplicateOperation:
        raise EconomyApiError(409, MSG_DUPLICATE)
    return result.operation_id


def _check_min(amount: int, params, *, whole_rest: Optional[int] = None) -> None:
    minimum = int(params.bank_min_amount)
    if amount < minimum and (whole_rest is None or amount != whole_rest):
        raise EconomyApiError(400, MSG_MIN_AMOUNT.format(n=minimum))


# =====================================================================================================================
# Player API (B4, contract 3.9)
# =====================================================================================================================

@dataclass(frozen=True)
class BankerContext:
    character_id: int
    user_id: int
    npc_id: int
    npc_name: str
    location_id: int
    region_id: Optional[int] = None          # resolved by `with_region` (step 6)


def _player_character(db: Session, character_id: int, user_id: int) -> "models.Character":
    character = db.query(models.Character).filter(models.Character.id == int(character_id)).first()
    if character is None:
        raise EconomyApiError(404, MSG_CHARACTER_NOT_FOUND)
    if character.user_id != user_id:
        raise EconomyApiError(403, MSG_NOT_OWNER)
    if character.is_npc:
        raise EconomyApiError(403, MSG_NOT_PLAYER)
    return character


def resolve_banker(db: Session, npc_id: int, character_id: int, user_id: int, *, write: bool) -> BankerContext:
    """Steps 1–4 of the fixed banker check (3.9): owner + player, banker exists / role / alive, activity lock
    (POST only), same location. Step 5 (FEAT-145 gate) is awaited by the router, step 6 is :func:`with_region`."""
    character = _player_character(db, character_id, user_id)
    npc = db.query(models.Character).filter(models.Character.id == int(npc_id)).first()
    if npc is None or not npc.is_npc or npc.npc_role != BANKER_ROLE:
        raise EconomyApiError(404, MSG_BANKER_NOT_FOUND)
    if npc.npc_status == NPC_DEAD:
        raise EconomyApiError(409, MSG_BANKER_DEAD)
    if write:
        message = activity_lock.lock_message(activity_lock.lock_for_character(character))
        if message:
            raise EconomyApiError(409, message)
    if npc.current_location_id is None or character.current_location_id != npc.current_location_id:
        raise EconomyApiError(400, MSG_WRONG_LOCATION)
    return BankerContext(character_id=int(character.id), user_id=int(user_id), npc_id=int(npc.id),
                         npc_name=npc.name, location_id=int(npc.current_location_id))


def with_region(db: Session, ctx: BankerContext) -> BankerContext:
    """Step 6: the banker's location -> region (his bank)."""
    region_id, _country = econ_ledger.resolve_location(db, ctx.location_id)
    if not region_id:
        raise EconomyApiError(409, MSG_NO_BANK)
    return dataclasses.replace(ctx, region_id=int(region_id))


def banker_context(db: Session, npc_id: int, character_id: int, user_id: int, *, write: bool) -> BankerContext:
    return with_region(db, resolve_banker(db, npc_id, character_id, user_id, write=write))


# ------------------------------------------------------------------------------------------------- read models

def _deposit_out(row: "models.BankDeposit", *, now: datetime, here_region: Optional[int],
                 names: Dict[int, tuple], banks: Dict[int, "models.EconBank"], params) -> dict:
    region_id = int(row.region_id)
    if row.kind == econ_bank.DEPOSIT_TERM:
        rate = float(row.rate_day) if row.rate_day is not None else 0.0
    else:
        bank = banks.get(region_id)
        rate = float(econ_bank.demand_rate(params, bank_factor(bank))) if bank_is_open(bank, names) else 0.0
    return {
        "id": int(row.id),
        "region_id": region_id,
        "region_name": names[region_id][0] if region_id in names else None,
        "kind": row.kind,
        "amount": int(row.amount),
        "interest_accrued": int(row.interest_accrued or 0),
        "interest_total": int(row.interest_total or 0),
        "rate_day": rate,
        "term_days": int(row.term_days) if row.term_days is not None else None,
        "opened_at": row.opened_at,
        "matures_at": row.matures_at,
        "matured": bool(row.kind == econ_bank.DEPOSIT_TERM and row.matures_at is not None and now >= row.matures_at),
        "here": here_region is not None and region_id == here_region,
    }


def _loan_out(row: "models.BankLoan", *, now: datetime, names: Dict[int, tuple], params) -> dict:
    projected = project_loan(row, now, params)
    region_id = int(row.region_id)
    return {
        "id": int(row.id),
        "region_id": region_id,
        "region_name": names[region_id][0] if region_id in names else None,
        "status": projected.status,
        "principal": int(row.principal),
        "debt": int(projected.debt),
        "interest_total": int(projected.interest_total),
        "penalty_total": int(projected.penalty_total),
        "paid_total": int(row.paid_total or 0),
        "collected_total": int(row.collected_total or 0),
        "rate_day": float(row.rate_day),
        "penalty_rate_day": float(row.penalty_rate_day),
        "term_days": int(row.term_days),
        "issued_at": row.issued_at,
        "due_at": row.due_at,
        "overdue": bool(projected.debt > 0 and now >= row.due_at),
    }


def _open_deposits(db: Session, character_id: int) -> List["models.BankDeposit"]:
    return (db.query(models.BankDeposit)
            .filter(models.BankDeposit.character_id == int(character_id),
                    models.BankDeposit.status == econ_bank.DEPOSIT_OPEN)
            .order_by(models.BankDeposit.id).all())


def _open_loan(db: Session, character_id: int) -> Optional["models.BankLoan"]:
    return (db.query(models.BankLoan)
            .filter(models.BankLoan.active_character_id == int(character_id)).first())


def _own_state(db: Session, character_id: int, *, here_region: Optional[int], now: datetime, params,
               extra_regions: Iterable[int] = ()):
    deposits = _open_deposits(db, character_id)
    loan = _open_loan(db, character_id)
    region_ids = {int(d.region_id) for d in deposits} | set(extra_regions)
    if loan is not None:
        region_ids.add(int(loan.region_id))
    names = region_names(db, region_ids)
    banks = get_banks(db, region_ids)
    outs = [_deposit_out(d, now=now, here_region=here_region, names=names, banks=banks, params=params)
            for d in deposits]
    outs.sort(key=lambda d: (0 if d["here"] else 1, d["id"]))
    loan_out = _loan_out(loan, now=now, names=names, params=params) if loan is not None else None
    debtor = bool(loan_out and loan_out["overdue"])
    return outs, loan_out, debtor, names, banks


def list_bank_regions(db: Session) -> List[dict]:
    """Enabled banks of existing regions — transfer destinations (public)."""
    rows = db.execute(text(
        "SELECT b.region_id, r.name, c.name FROM econ_banks b JOIN Regions r ON r.id = b.region_id "
        "LEFT JOIN Countries c ON c.id = r.country_id WHERE b.is_enabled = 1 ORDER BY r.name, b.region_id"
    )).fetchall()
    return [{"region_id": int(r[0]), "name": r[1], "country_name": r[2]} for r in rows]


def _rates(params, factor: Decimal) -> dict:
    return {
        "demand_rate_day": float(econ_bank.demand_rate(params, factor)),
        "term_rates": [{"term_days": t, "rate_day": float(econ_bank.term_rate(params, t, factor))}
                       for t in econ_bank.BANK_TERMS],
        "loan_rate_day": float(params.bank_loan_rate_day),
        "penalty_rate_day": float(params.bank_penalty_rate_day),
        "transfer_fee_rate": float(params.bank_transfer_fee_rate),
        "transfer_fee_min": int(params.bank_transfer_fee_min),
        "min_amount": int(params.bank_min_amount),
    }


def build_view(db: Session, ctx: BankerContext, *, params=None, now: Optional[datetime] = None) -> dict:
    """``BankView`` for the character at this banker (read-only; the loan debt is projected to now)."""
    params = params or load_params(db)
    now = now or now_utc()
    region_id = ctx.region_id
    deposits, loan, debtor, names, banks = _own_state(
        db, ctx.character_id, here_region=region_id, now=now, params=params, extra_regions=[region_id])
    bank = banks.get(region_id)
    enabled = bank_is_open(bank, names)
    character = db.query(models.Character).filter(models.Character.id == ctx.character_id).first()
    wallet = int(db.execute(text("SELECT currency_balance FROM characters WHERE id = :id"),
                            {"id": ctx.character_id}).scalar() or 0)
    cap = econ_bank.loan_cap(character.level if character is not None else 1, params)
    max_loan, refusal = 0, None
    if not enabled:
        refusal = MSG_LOANS_CLOSED
    elif debtor:
        refusal = MSG_DEBTOR
    elif loan is not None:
        refusal = MSG_HAS_LOAN
    else:
        free = econ_bank.lendable(bank_account_balance(db, region_id), int(bank.resident_deposits or 0), params)
        max_loan = min(cap, free)
        if max_loan < int(params.bank_min_amount):
            max_loan, refusal = 0, MSG_BANK_EMPTY
    return {
        "npc_id": ctx.npc_id,
        "npc_name": ctx.npc_name,
        "region_id": region_id,
        "region_name": names[region_id][0] if region_id in names else None,
        "bank_enabled": enabled,
        "rates": _rates(params, bank_factor(bank)),
        "wallet": wallet,
        "deposits": deposits,
        "loan": loan,
        "debtor": debtor,
        "loan_cap": cap,
        "max_loan_now": max_loan,
        "loan_refusal": refusal,
        "bank_regions": list_bank_regions(db),
    }


def get_summary(db: Session, character_id: int, user_id: int, *, is_admin: bool) -> dict:
    """``BankSummary``: all own open deposits (here = False) and the loan. Owner or ``economy:read``."""
    if is_admin:
        exists = db.execute(text("SELECT id FROM characters WHERE id = :id"), {"id": int(character_id)}).first()
        if exists is None:
            raise EconomyApiError(404, MSG_CHARACTER_NOT_FOUND)
    else:
        _player_character(db, character_id, user_id)
    params = load_params(db)
    deposits, loan, debtor, _names, _banks = _own_state(db, character_id, here_region=None, now=now_utc(),
                                                        params=params)
    return {
        "character_id": int(character_id),
        "total_deposits": sum(d["amount"] + d["interest_accrued"] for d in deposits),
        "deposits": deposits,
        "loan": loan,
        "debtor": debtor,
    }


# ------------------------------------------------------------------------------------------------- write flows
# Each returns {"message", "operation_id"}; the router commits and rebuilds the view.

def _source_demand_deposit(db: Session, deposit_id: int, character_id: int) -> "models.BankDeposit":
    row = db.query(models.BankDeposit).filter(models.BankDeposit.id == int(deposit_id)).first()
    if row is None or int(row.character_id) != int(character_id) or row.status != econ_bank.DEPOSIT_OPEN:
        raise EconomyApiError(404, MSG_DEPOSIT_NOT_FOUND)
    if row.kind != econ_bank.DEPOSIT_DEMAND:
        raise EconomyApiError(400, MSG_TERM_NOT_TRANSFERABLE)
    return row


def _recheck_source(row: Optional["models.BankDeposit"], character_id: int) -> "models.BankDeposit":
    """After the locks: the source deposit is still an own open demand deposit."""
    if row is None or int(row.character_id) != int(character_id) or row.status != econ_bank.DEPOSIT_OPEN:
        raise EconomyApiError(404, MSG_DEPOSIT_NOT_FOUND)
    if row.kind != econ_bank.DEPOSIT_DEMAND:
        raise EconomyApiError(400, MSG_TERM_NOT_TRANSFERABLE)
    return row


def _demand_row_id(db: Session, region_id: int, owner_id: int) -> Optional[int]:
    value = db.execute(text(
        "SELECT id FROM bank_deposits WHERE region_id = :r AND demand_owner_id = :c AND status = 'open'"),
        {"r": int(region_id), "c": int(owner_id)}).scalar()
    return int(value) if value is not None else None


def _new_demand_row(db: Session, region_id: int, owner_id: int, amount: int, now: datetime) -> "models.BankDeposit":
    """A fresh demand deposit: ``interest_base = 0`` — it earns from the next period (3.0 Q3)."""
    row = models.BankDeposit(
        character_id=int(owner_id), region_id=int(region_id), kind=econ_bank.DEPOSIT_DEMAND,
        status=econ_bank.DEPOSIT_OPEN, amount=int(amount), interest_base=0, interest_accrued=0, interest_total=0,
        interest_carry=0, rate_day=None, term_days=None, opened_at=now, matures_at=None, accrued_at=now,
        demand_owner_id=int(owner_id),
    )
    db.add(row)
    db.flush()
    return row


def _destination_open(bank, names, region_id: int) -> None:
    if not bank_is_open(bank, names):
        name = names[region_id][0] if region_id in names else DELETED_REGION_NAME
        raise EconomyApiError(409, MSG_DEST_CLOSED.format(name=name))


def deposit(db: Session, ctx: BankerContext, body) -> dict:
    """Demand top-up / new demand / new term deposit at the banker's bank X: ``C -> V(X)``."""
    x = ctx.region_id
    key = _key(KEY_DEPOSIT, ctx.character_id, body.request_id)
    banks = lock_banks(db, [x])
    _check_duplicate(db, key)
    if not bank_is_open(banks.get(x), region_names(db, [x])):
        raise EconomyApiError(409, MSG_DEPOSITS_CLOSED)
    params = load_params(db)
    amount = int(body.amount)
    _check_min(amount, params)
    now = now_utc()

    if body.kind == econ_bank.DEPOSIT_TERM:
        open_terms = db.execute(text(
            "SELECT COUNT(*) FROM bank_deposits WHERE character_id = :c AND status = 'open' AND kind = 'term'"),
            {"c": ctx.character_id}).scalar()
        if int(open_terms or 0) >= MAX_TERM_DEPOSITS:
            raise EconomyApiError(409, MSG_TOO_MANY_TERM)
        term = int(body.term_days)
        row = models.BankDeposit(
            character_id=ctx.character_id, region_id=x, kind=econ_bank.DEPOSIT_TERM, status=econ_bank.DEPOSIT_OPEN,
            amount=amount, interest_base=amount, interest_accrued=0, interest_total=0, interest_carry=0,
            rate_day=econ_bank.q6(econ_bank.term_rate(params, term, bank_factor(banks[x]))), term_days=term,
            opened_at=now, matures_at=now + timedelta(days=term), accrued_at=now, demand_owner_id=None,
        )
        db.add(row)
        db.flush()
        message = f"Открыт срочный вклад на {term} дней: {_fmt(db, amount)}"
    else:
        row_id = _demand_row_id(db, x, ctx.character_id)
        if row_id is not None:
            row = lock_deposits(db, [row_id])[row_id]
            row.amount = int(row.amount) + amount        # interest_base unchanged: a top-up earns from next period
            message = f"Вклад пополнен на {_fmt(db, amount)}"
        else:
            row = _new_demand_row(db, x, ctx.character_id, amount, now)
            message = f"Открыт вклад до востребования: {_fmt(db, amount)}"

    balances = econ_ledger.lock_characters(db, [ctx.character_id])
    if balances.get(ctx.character_id, 0) < amount:
        raise EconomyApiError(400, _not_enough(db))
    op_id = _post(db, ctx, op_type=core.OP_BANK_DEPOSIT, region_id=x, key=key, insufficient=_not_enough(db),
                  legs=[core.Leg(core.AccountRef.character(ctx.character_id), core.AccountRef.bank_deposits(x),
                                 amount)],
                  metadata={"deposit_id": int(row.id), "kind": row.kind, "character_id": ctx.character_id})
    logger.info("bank deposit: character=%s region=%s deposit=%s amount=%s op=%s", ctx.character_id, x, row.id,
                amount, op_id)
    return {"message": message, "operation_id": op_id}


def withdraw(db: Session, ctx: BankerContext, body) -> dict:
    """Withdraw from a deposit of the banker's bank X: demand (part / all), term matured (with interest) or early
    (interest forfeited ``V(X) -> B(X)``)."""
    x = ctx.region_id
    key = _key(KEY_WITHDRAW, ctx.character_id, body.request_id)
    _check_duplicate(db, key)
    peek = db.query(models.BankDeposit).filter(models.BankDeposit.id == int(body.deposit_id)).first()
    if peek is None or int(peek.character_id) != ctx.character_id or peek.status != econ_bank.DEPOSIT_OPEN:
        raise EconomyApiError(404, MSG_DEPOSIT_NOT_FOUND)
    if int(peek.region_id) != x:
        names = region_names(db, [peek.region_id])
        name = names[int(peek.region_id)][0] if int(peek.region_id) in names else DELETED_REGION_NAME
        raise EconomyApiError(400, MSG_OTHER_BANK.format(name=name))

    banks = lock_banks(db, [x])
    _check_duplicate(db, key)
    row = lock_deposits(db, [peek.id]).get(int(peek.id))
    if row is None or int(row.character_id) != ctx.character_id or row.status != econ_bank.DEPOSIT_OPEN \
            or int(row.region_id) != x:
        raise EconomyApiError(404, MSG_DEPOSIT_NOT_FOUND)
    params = load_params(db)
    now = now_utc()
    legs: List[core.Leg] = []
    vault, bank_acc, me = core.AccountRef.bank_deposits(x), core.AccountRef.bank(x), core.AccountRef.character(
        ctx.character_id)

    if row.kind == econ_bank.DEPOSIT_DEMAND:
        if body.amount is None:
            raise EconomyApiError(400, MSG_AMOUNT_REQUIRED)
        amount = int(body.amount)
        have = int(row.amount)
        if amount > have:
            raise EconomyApiError(400, MSG_DEPOSIT_SHORT.format(n=_fmt(db, have)))
        _check_min(amount, params, whole_rest=have)
        row.amount = have - amount
        row.interest_base = min(int(row.interest_base or 0), int(row.amount))
        close_deposit_if_empty(row, now)
        legs.append(core.Leg(vault, me, amount))
        payout = amount
        message = (f"Вклад закрыт: получено {_fmt(db, amount)}" if row.status == econ_bank.DEPOSIT_CLOSED
                   else f"Снято со вклада: {_fmt(db, amount)}")
    else:
        principal = int(row.amount)
        accrued = int(row.interest_accrued or 0)
        matured = row.matures_at is not None and now >= row.matures_at
        if matured:
            # B5: the last partial period up to matures_at (the tick would have paid it before converting).
            final = matured_term_interest(db, row, banks.get(x), params, now)
            if final > 0:
                legs.append(core.Leg(bank_acc, vault, final, core.LEG_INTEREST))
                row.interest_total = int(row.interest_total or 0) + final
            payout = principal + accrued + final
            legs.append(core.Leg(vault, me, payout))
            message = f"Срочный вклад забран: {_fmt(db, payout)}"
        else:
            payout = principal
            legs.append(core.Leg(vault, me, principal))
            if accrued > 0:
                legs.append(core.Leg(vault, bank_acc, accrued, core.LEG_INTEREST))
                message = f"Срочный вклад закрыт досрочно: проценты ({_fmt(db, accrued)}) сгорели"
            else:
                message = f"Срочный вклад закрыт досрочно: возвращено {_fmt(db, principal)}"
        row.amount = 0
        row.interest_accrued = 0
        close_deposit_if_empty(row, now)

    econ_ledger.lock_characters(db, [ctx.character_id])
    op_id = _post(db, ctx, op_type=core.OP_BANK_WITHDRAW, region_id=x, key=key, legs=legs,
                  insufficient=MSG_RETRY,
                  metadata={"deposit_id": int(row.id), "kind": row.kind, "character_id": ctx.character_id})
    logger.info("bank withdraw: character=%s region=%s deposit=%s paid=%s op=%s", ctx.character_id, x, row.id,
                payout, op_id)
    return {"message": message, "operation_id": op_id}


def transfer(db: Session, ctx: BankerContext, body) -> dict:
    """Own demand deposit in A -> own demand deposit in B: ``V(A) -> V(B)`` + commission ``V(A) -> T(X)``."""
    x, b = ctx.region_id, int(body.to_region_id)
    key = _key(KEY_TRANSFER, ctx.character_id, body.request_id)
    _check_duplicate(db, key)
    peek = _source_demand_deposit(db, body.deposit_id, ctx.character_id)
    a = int(peek.region_id)
    if a == b:
        raise EconomyApiError(400, MSG_SAME_BANK)

    banks = lock_banks(db, [a, b])
    _check_duplicate(db, key)
    names = region_names(db, [a, b, x])
    _destination_open(banks.get(b), names, b)
    dest_id = _demand_row_id(db, b, ctx.character_id)
    rows = lock_deposits(db, [peek.id] + ([dest_id] if dest_id else []))
    source = _recheck_source(rows.get(int(peek.id)), ctx.character_id)
    params = load_params(db)
    amount = int(body.amount)
    _check_min(amount, params)
    fee = econ_bank.transfer_fee(amount, params)
    if amount + fee > int(source.amount):
        raise EconomyApiError(400, MSG_DEPOSIT_SHORT_FEE.format(fee=_fmt(db, fee)))
    now = now_utc()
    source.amount = int(source.amount) - amount - fee
    source.interest_base = min(int(source.interest_base or 0), int(source.amount))
    close_deposit_if_empty(source, now)
    if dest_id is not None:
        dest = rows[dest_id]
        dest.amount = int(dest.amount) + amount
    else:
        dest = _new_demand_row(db, b, ctx.character_id, amount, now)

    op_id = _post(db, ctx, op_type=core.OP_BANK_TRANSFER, region_id=x, key=key, insufficient=MSG_RETRY,
                  legs=[core.Leg(core.AccountRef.bank_deposits(a), core.AccountRef.bank_deposits(b), amount),
                        core.Leg(core.AccountRef.bank_deposits(a), core.AccountRef.region(x), fee,
                                 core.LEG_COMMISSION)],
                  metadata={"from_deposit_id": int(source.id), "to_deposit_id": int(dest.id), "fee": fee,
                            "character_id": ctx.character_id})
    logger.info("bank transfer: character=%s from=%s to=%s amount=%s fee=%s op=%s", ctx.character_id, a, b, amount,
                fee, op_id)
    return {"message": f"Переведено в банк региона «{names[b][0]}»: {_fmt(db, amount)}, комиссия {_fmt(db, fee)}",
            "operation_id": op_id}


def _recipient(db: Session, name: str, sender_id: int) -> int:
    rows = db.execute(text("SELECT id FROM characters WHERE name = :name AND is_npc = 0 ORDER BY id LIMIT 3"),
                      {"name": name}).fetchall()
    if not rows:
        raise EconomyApiError(404, MSG_RECIPIENT_NOT_FOUND.format(name=name))
    if len(rows) > 1:
        raise EconomyApiError(409, MSG_RECIPIENT_AMBIGUOUS)
    recipient_id = int(rows[0][0])
    if recipient_id == int(sender_id):
        raise EconomyApiError(400, MSG_SELF_TRANSFER)
    return recipient_id


def send(db: Session, ctx: BankerContext, body) -> dict:
    """Money to another player's demand deposit in bank B, from the wallet or an own demand deposit (any bank);
    commission to ``T(X)``. The response never reveals the recipient's deposits."""
    x, b = ctx.region_id, int(body.to_region_id)
    key = _key(KEY_SEND, ctx.character_id, body.request_id)
    _check_duplicate(db, key)
    recipient_id = _recipient(db, body.recipient_name, ctx.character_id)
    from_wallet = body.source == "wallet"
    peek = None if from_wallet else _source_demand_deposit(db, body.deposit_id, ctx.character_id)
    a = None if peek is None else int(peek.region_id)

    banks = lock_banks(db, [b] + ([a] if a else []))
    _check_duplicate(db, key)
    names = region_names(db, [b, x])
    _destination_open(banks.get(b), names, b)
    dest_id = _demand_row_id(db, b, recipient_id)
    rows = lock_deposits(db, ([int(peek.id)] if peek is not None else []) + ([dest_id] if dest_id else []))
    params = load_params(db)
    amount = int(body.amount)
    _check_min(amount, params)
    fee = econ_bank.transfer_fee(amount, params)
    now = now_utc()

    if from_wallet:
        source = None
        src_ref = core.AccountRef.character(ctx.character_id)
    else:
        source = _recheck_source(rows.get(int(peek.id)), ctx.character_id)
        if amount + fee > int(source.amount):
            raise EconomyApiError(400, MSG_DEPOSIT_SHORT_FEE.format(fee=_fmt(db, fee)))
        source.amount = int(source.amount) - amount - fee
        source.interest_base = min(int(source.interest_base or 0), int(source.amount))
        close_deposit_if_empty(source, now)
        src_ref = core.AccountRef.bank_deposits(a)
    if dest_id is not None:
        dest = rows[dest_id]
        dest.amount = int(dest.amount) + amount          # recipient's interest_base unchanged
    else:
        dest = _new_demand_row(db, b, recipient_id, amount, now)

    genitive = econ_ledger.get_currency_forms(db).genitive
    insufficient = MSG_NOT_ENOUGH_WITH_FEE.format(genitive=genitive, total=_fmt(db, amount + fee), fee=_fmt(db, fee))
    if from_wallet:
        balances = econ_ledger.lock_characters(db, [ctx.character_id])
        if balances.get(ctx.character_id, 0) < amount + fee:
            raise EconomyApiError(400, insufficient)
    legs = [core.Leg(src_ref, core.AccountRef.region(x), fee, core.LEG_COMMISSION)]
    dst_ref = core.AccountRef.bank_deposits(b)
    if src_ref != dst_ref:                                # same vault: the money stays, only the rows move
        legs.insert(0, core.Leg(src_ref, dst_ref, amount))
    op_id = _post(db, ctx, op_type=core.OP_BANK_TRANSFER, region_id=x, key=key, legs=legs, insufficient=insufficient,
                  metadata={"source": body.source, "from_deposit_id": int(source.id) if source else None,
                            "to_deposit_id": int(dest.id), "recipient_id": recipient_id, "fee": fee,
                            "character_id": ctx.character_id})
    logger.info("bank send: character=%s recipient=%s to=%s amount=%s fee=%s op=%s", ctx.character_id, recipient_id,
                b, amount, fee, op_id)
    # The stored name, not the typed one: the lookup ignores case and ё.
    recipient_name = db.execute(text("SELECT name FROM characters WHERE id = :id"),
                                {"id": recipient_id}).scalar() or body.recipient_name
    return {"message": f"Перевод отправлен: {recipient_name} получит {_fmt(db, amount)} в банке региона "
                       f"«{names[b][0]}» (комиссия {_fmt(db, fee)})",
            "operation_id": op_id}


def take_loan(db: Session, ctx: BankerContext, body) -> dict:
    """A loan from the banker's bank X: ``B(X) -> C``; rate and penalty fixed from params at issue."""
    x = ctx.region_id
    key = _key(KEY_LOAN, ctx.character_id, body.request_id)
    banks = lock_banks(db, [x])
    _check_duplicate(db, key)
    bank = banks.get(x)
    if not bank_is_open(bank, region_names(db, [x])):
        raise EconomyApiError(409, MSG_LOANS_CLOSED)
    params = load_params(db)
    now = now_utc()
    existing = _open_loan(db, ctx.character_id)
    if existing is not None:
        if project_loan(existing, now, params).status == econ_bank.LOAN_OVERDUE:
            raise EconomyApiError(409, MSG_DEBTOR)
        raise EconomyApiError(409, MSG_HAS_LOAN)
    amount = int(body.amount)
    _check_min(amount, params)
    level = db.execute(text("SELECT level FROM characters WHERE id = :id"), {"id": ctx.character_id}).scalar()
    cap = econ_bank.loan_cap(level, params)
    if amount > cap:
        raise EconomyApiError(400, MSG_LOAN_CAP.format(cap=_fmt(db, cap)))
    free = econ_bank.lendable(bank_account_balance(db, x), int(bank.resident_deposits or 0), params)
    if free < int(params.bank_min_amount):
        raise EconomyApiError(409, MSG_BANK_EMPTY)
    if amount > free:
        raise EconomyApiError(409, MSG_BANK_LIMIT.format(n=_fmt(db, free)))

    term = int(body.term_days)
    loan = models.BankLoan(
        character_id=ctx.character_id, region_id=x, status=econ_bank.LOAN_ACTIVE, principal=amount, debt=amount,
        interest_total=0, penalty_total=0, paid_total=0, collected_total=0, written_off=0,
        rate_day=econ_bank.q6(Decimal(str(params.bank_loan_rate_day))),
        penalty_rate_day=econ_bank.q6(Decimal(str(params.bank_penalty_rate_day))), term_days=term,
        issued_at=now, due_at=now + timedelta(days=term), accrued_at=now, interest_carry=0,
        active_character_id=ctx.character_id,
    )
    db.add(loan)
    try:
        db.flush()
    except IntegrityError:                                # uq_bank_loans_active: a concurrent loan won
        raise EconomyApiError(409, MSG_HAS_LOAN)
    econ_ledger.lock_characters(db, [ctx.character_id])
    op_id = _post(db, ctx, op_type=core.OP_LOAN_ISSUE, region_id=x, key=key, insufficient=MSG_BANK_EMPTY,
                  legs=[core.Leg(core.AccountRef.bank(x), core.AccountRef.character(ctx.character_id), amount)],
                  metadata={"loan_id": int(loan.id), "term_days": term, "character_id": ctx.character_id})
    logger.info("bank loan: character=%s region=%s loan=%s amount=%s op=%s", ctx.character_id, x, loan.id, amount,
                op_id)
    return {"message": f"Займ выдан: {_fmt(db, amount)}. Вернуть до {_msk(loan.due_at)} МСК", "operation_id": op_id}


def repay(db: Session, ctx: BankerContext, body) -> dict:
    """Repay the own loan (any banker, also when its bank is disabled): ``C -> B(L)``; accrued to now first."""
    key = _key(KEY_REPAY, ctx.character_id, body.request_id)
    _check_duplicate(db, key)
    peek = _open_loan(db, ctx.character_id)
    if peek is None:
        raise EconomyApiError(404, MSG_LOAN_NOT_FOUND)
    region = int(peek.region_id)
    lock_banks(db, [region])
    _check_duplicate(db, key)
    loan = lock_loan(db, peek.id)
    if loan is None or loan.status not in econ_bank.LOAN_OPEN_STATUSES \
            or int(loan.character_id) != ctx.character_id:
        raise EconomyApiError(404, MSG_LOAN_NOT_FOUND)
    params = load_params(db)
    now = now_utc()
    apply_loan_state(loan, project_loan(loan, now, params))
    debt = int(loan.debt)
    amount = int(body.amount)
    if debt <= 0:
        close_loan(loan, now)
        return {"message": "Займ погашен", "operation_id": None}
    if amount < debt:                                     # repaying the whole rest is always allowed
        _check_min(amount, params)
    pay = min(amount, debt)
    balances = econ_ledger.lock_characters(db, [ctx.character_id])
    if balances.get(ctx.character_id, 0) < pay:
        raise EconomyApiError(400, _not_enough(db))
    loan.debt = debt - pay
    loan.paid_total = int(loan.paid_total or 0) + pay
    if loan.debt <= 0:
        close_loan(loan, now)
        message = "Займ погашен"
    else:
        message = f"Погашено {_fmt(db, pay)}, осталось {_fmt(db, loan.debt)}"
    op_id = _post(db, ctx, op_type=core.OP_LOAN_REPAY, region_id=region, key=key, insufficient=_not_enough(db),
                  legs=[core.Leg(core.AccountRef.character(ctx.character_id), core.AccountRef.bank(region), pay)],
                  metadata={"loan_id": int(loan.id), "character_id": ctx.character_id})
    logger.info("bank repay: character=%s loan=%s paid=%s left=%s op=%s", ctx.character_id, loan.id, pay, loan.debt,
                op_id)
    return {"message": message, "operation_id": op_id}


# =====================================================================================================================
# Tick helpers (B5, contract 3.7) — orphan purge, bank pass, collection pass. Use lock_banks / lock_deposits /
# lock_loan / loan_state / apply_loan_state / close_deposit_if_empty / close_loan above.
# =====================================================================================================================
# Each function works inside the caller's transaction and never commits; ``econ_tick`` opens one session per bank /
# per loan and commits or rolls back. Keys: ``bank_tick:<run>:b:<X>``, ``loan_collect:<run>:l:<loan>``,
# ``bank_closed:r:<X>`` (orphan purge).

TICK_STATUS_DONE = "done"
TICK_STATUS_ALREADY = "already"            # processed by this run before (resumed run / rerun)
TICK_STATUS_SKIPPED = "skipped"            # nothing to do (row gone, loan no longer open)

ORPHAN_LOAN_NOTE = "Регион банка удалён — долг списан"
DELETED_LOAN_NOTE = "Персонаж удалён — долг списан"

SQL_ORPHAN_BANKS = (
    "SELECT b.region_id FROM econ_banks b LEFT JOIN Regions r ON r.id = b.region_id "
    "WHERE r.id IS NULL ORDER BY b.region_id"
)
SQL_BANKS_TO_TICK = (
    "SELECT b.region_id FROM econ_banks b WHERE b.is_enabled = 1 OR b.resident_deposits > 0 "
    "OR b.resident_loans > 0 "
    "OR EXISTS (SELECT 1 FROM bank_deposits d WHERE d.region_id = b.region_id AND d.status = 'open') "
    "OR EXISTS (SELECT 1 FROM bank_loans l WHERE l.region_id = b.region_id AND l.status IN ('active', 'overdue')) "
    "ORDER BY b.region_id"
)
SQL_DUE_LOANS = (
    "SELECT id FROM bank_loans WHERE status IN ('active', 'overdue') AND due_at <= :now ORDER BY id"
)
SQL_REGION_SIMULATED = (
    "SELECT 1 FROM econ_regions e JOIN Regions r ON r.id = e.region_id "
    "WHERE e.region_id = :r AND e.template_code IS NOT NULL AND e.population > 0"
)
SQL_ACCOUNT_BALANCE = "SELECT balance FROM econ_accounts WHERE kind = :kind AND ref_id = :ref_id"


@dataclass
class BankTickResult:
    status: str
    posted: bool = False
    stats: Dict[str, int] = dataclasses.field(default_factory=dict)


@dataclass
class CollectResult:
    status: str
    collected: int = 0
    overdue: bool = False           # the loan is still owing after the pass


def _account_balance(db: Session, ref: core.AccountRef) -> int:
    value = db.execute(text(SQL_ACCOUNT_BALANCE), {"kind": ref.kind, "ref_id": int(ref.ref_id)}).scalar()
    return int(value or 0)


def _operation_exists(db: Session, key: str) -> bool:
    return db.execute(text(core.SQL_SELECT_OPERATION_BY_KEY), {"key": key}).first() is not None


def _lock_open_deposits_of_bank(db: Session, region_id: int) -> List["models.BankDeposit"]:
    return (db.query(models.BankDeposit)
            .filter(models.BankDeposit.region_id == int(region_id),
                    models.BankDeposit.status == econ_bank.DEPOSIT_OPEN)
            .order_by(models.BankDeposit.id).with_for_update().populate_existing().all())


def _lock_open_loans(db: Session, *, region_id: Optional[int] = None,
                     character_id: Optional[int] = None) -> List["models.BankLoan"]:
    query = db.query(models.BankLoan).filter(models.BankLoan.status.in_(econ_bank.LOAN_OPEN_STATUSES))
    if region_id is not None:
        query = query.filter(models.BankLoan.region_id == int(region_id))
    if character_id is not None:
        query = query.filter(models.BankLoan.character_id == int(character_id))
    return query.order_by(models.BankLoan.id).with_for_update().populate_existing().all()


def write_off_loan_row(row: "models.BankLoan", now: datetime, note: str, user_id: Optional[int] = None) -> int:
    """The rest of the debt becomes the bank's loss (no money moves). Returns the amount written off."""
    debt = max(0, int(row.debt))
    row.written_off = int(row.written_off or 0) + debt
    row.debt = 0
    row.status = econ_bank.LOAN_WRITTEN_OFF
    row.closed_at = now
    row.closed_by_user_id = user_id
    row.note = note[:500] if note else None
    row.active_character_id = None
    return debt


def deposit_state(row: "models.BankDeposit") -> econ_bank.DepositState:
    return econ_bank.DepositState(
        id=int(row.id), character_id=int(row.character_id), kind=row.kind, amount=int(row.amount),
        accrued_at=row.accrued_at, interest_base=int(row.interest_base or 0),
        interest_accrued=int(row.interest_accrued or 0), interest_total=int(row.interest_total or 0),
        interest_carry=Decimal(str(row.interest_carry or 0)),
        rate_day=Decimal(str(row.rate_day)) if row.rate_day is not None else None,
        term_days=int(row.term_days) if row.term_days is not None else None, matures_at=row.matures_at,
        status=row.status, closed_at=row.closed_at,
    )


def apply_deposit_state(row: "models.BankDeposit", state: econ_bank.DepositState) -> None:
    row.kind = state.kind
    row.status = state.status
    row.amount = int(state.amount)
    row.interest_base = int(state.interest_base)
    row.interest_accrued = int(state.interest_accrued)
    row.interest_total = int(state.interest_total)
    row.interest_carry = state.interest_carry
    row.rate_day = state.rate_day
    row.accrued_at = state.accrued_at
    row.closed_at = state.closed_at
    row.demand_owner_id = state.demand_owner_id


def matured_term_interest(db: Session, row: "models.BankDeposit", bank: Optional["models.EconBank"], params,
                          now: datetime) -> int:
    """Interest of the last partial period ``[accrued_at, matures_at)`` of a matured term deposit that is withdrawn
    before the tick converted it (the tick would have paid it). Paid only by an enabled bank, from its free money
    (``lendable``) — the caller holds ``econ_banks(X)`` and posts ``B(X) -> V(X)`` interest."""
    if bank is None or not bool(bank.is_enabled) or row.kind != econ_bank.DEPOSIT_TERM \
            or row.matures_at is None or now < row.matures_at or row.rate_day is None:
        return 0
    seconds = econ_bank.seconds_between(row.accrued_at, row.matures_at)
    due, _carry = econ_bank.accrue(int(row.interest_base or 0), Decimal(str(row.rate_day)), seconds,
                                   Decimal(str(row.interest_carry or 0)))
    free = econ_bank.lendable(bank_account_balance(db, int(row.region_id)), int(bank.resident_deposits or 0), params)
    return max(0, min(due, free))


# ------------------------------------------------------------------------------------------------- orphan purge

def orphan_bank_ids(db: Session) -> List[int]:
    return [int(r[0]) for r in db.execute(text(SQL_ORPHAN_BANKS)).fetchall()]


def purge_orphan_bank(db: Session, region_id: int, *, run_id: int, now: datetime) -> bool:
    """A bank whose region is gone (3.7 step 1): flag off, residents gone, open loans written off, the bank's own
    money ``B(X) -> W`` (``treasury_closed``). The vault and the deposit rows stay (transferable / paid out on
    deletion). Returns True when something changed."""
    bank = lock_banks(db, [region_id]).get(int(region_id))
    if bank is None:
        return False
    loans = _lock_open_loans(db, region_id=region_id)
    balance = bank_account_balance(db, region_id)
    changed = bool(bank.is_enabled) or int(bank.resident_deposits or 0) > 0 or int(bank.resident_loans or 0) > 0 \
        or bool(loans) or balance > 0
    if not changed:
        return False
    bank.is_enabled = False
    bank.resident_deposits = 0
    bank.resident_loans = 0
    bank.resident_dep_carry = 0
    bank.resident_loan_carry = 0
    for loan in loans:
        write_off_loan_row(loan, now, ORPHAN_LOAN_NOTE)
    if balance > 0:
        key = f"bank_closed:r:{int(region_id)}"
        if _operation_exists(db, key):           # money came in after an earlier purge (e.g. burnt term interest)
            key = f"bank_closed:r:{int(region_id)}:run{int(run_id)}"
        econ_ledger.post_operation(
            db, op_type=core.OP_TREASURY_CLOSED,
            legs=[core.Leg(core.AccountRef.bank(region_id), core.AccountRef.world(), balance)],
            source_service=SOURCE_SERVICE, metadata={"bank_region_id": int(region_id), "loans_written_off": len(loans)},
            idempotency_key=key, apply_tax=False,
        )
    econ_ledger.deactivate_account(db, core.AccountRef.bank(region_id))
    logger.info("bank purge: region=%s (deleted) closed, moved=%s, loans written off=%s", region_id, balance,
                len(loans))
    return True


# ------------------------------------------------------------------------------------------------- bank pass

def banks_to_tick(db: Session) -> List[int]:
    return [int(r[0]) for r in db.execute(text(SQL_BANKS_TO_TICK)).fetchall()]


def tick_bank(db: Session, region_id: int, *, run_id: int, params, clock) -> BankTickResult:
    """One bank of the bank pass (3.7 step 2): locks ``econ_banks(X)`` -> open deposits -> open loans, runs
    ``econ_bank.bank_step``, writes every row back and posts one ``bank_tick`` (``apply_tax=False``). ``clock()`` is
    read after the bank lock so no player operation committed before it is dated after the tick."""
    region_id = int(region_id)
    bank = lock_banks(db, [region_id]).get(region_id)
    if bank is None:
        return BankTickResult(TICK_STATUS_SKIPPED)
    if bank.last_run_id is not None and int(bank.last_run_id) == int(run_id):
        return BankTickResult(TICK_STATUS_ALREADY)
    now = clock().replace(microsecond=0)
    deposits = _lock_open_deposits_of_bank(db, region_id)
    loans = _lock_open_loans(db, region_id=region_id)
    names = region_names(db, [region_id])
    simulated = db.execute(text(SQL_REGION_SIMULATED), {"r": region_id}).first() is not None
    out = econ_bank.bank_step(econ_bank.BankInput(
        region_id=region_id, now=now, enabled=bank_is_open(bank, names), simulated=simulated,
        factor=bank_factor(bank), bank_balance=bank_account_balance(db, region_id),
        purse_balance=_account_balance(db, core.AccountRef.purse(region_id)),
        residents=econ_bank.ResidentState(
            deposits=int(bank.resident_deposits or 0), loans=int(bank.resident_loans or 0),
            dep_carry=Decimal(str(bank.resident_dep_carry or 0)), loan_carry=Decimal(str(bank.resident_loan_carry or 0)),
            accrued_at=bank.accrued_at),
        deposits=tuple(deposit_state(d) for d in deposits), loans=tuple(loan_state(l) for l in loans), params=params,
    ))
    by_id = {int(d.id): d for d in deposits}
    for state in out.deposits:
        apply_deposit_state(by_id[int(state.id)], state)
    loans_by_id = {int(l.id): l for l in loans}
    for state in out.loans:
        apply_loan_state(loans_by_id[int(state.id)], state)
    res = out.residents
    bank.resident_deposits = int(res.deposits)
    bank.resident_loans = int(res.loans)
    bank.resident_dep_carry = res.dep_carry
    bank.resident_loan_carry = res.loan_carry
    bank.accrued_at = res.accrued_at
    bank.deposit_rate_factor = out.factor
    db.flush()  # row updates (merged rows release the demand UNIQUE first) before the ledger statements

    posted = False
    if out.legs:
        result = econ_ledger.post_operation(
            db, op_type=core.OP_BANK_TICK, legs=list(out.legs), source_service=SOURCE_SERVICE, region_id=region_id,
            idempotency_key=f"bank_tick:{int(run_id)}:b:{region_id}", apply_tax=False,
            metadata={"run_id": int(run_id), **out.stats},
        )
        posted = result.operation_id is not None
    bank.last_run_id = int(run_id)
    bank.last_tick_at = now
    bank.last_stats = {**out.stats, "factor": str(out.factor)}
    return BankTickResult(TICK_STATUS_DONE, posted=posted, stats=dict(out.stats))


# ------------------------------------------------------------------------------------------------- collection pass

def due_loan_ids(db: Session, now: datetime) -> List[int]:
    return [int(r[0]) for r in db.execute(text(SQL_DUE_LOANS), {"now": now}).fetchall()]


def collect_loan(db: Session, loan_id: int, *, run_id: int, params, clock) -> CollectResult:
    """One overdue loan of the collection pass (3.7 step 3): the debtor's deposits (demand first, then term —
    interest first), then the wallet; never more than is there. Op ``loan_collect`` ``V(Y) -> B(L)`` per deposit
    bank Y and ``C -> B(L)``. Locks: ``econ_banks`` {L} ∪ deposit banks asc -> deposits -> loan -> character."""
    key = f"loan_collect:{int(run_id)}:l:{int(loan_id)}"
    if _operation_exists(db, key):
        return CollectResult(TICK_STATUS_ALREADY)
    peek = db.query(models.BankLoan).filter(models.BankLoan.id == int(loan_id)).first()
    if peek is None or peek.status not in econ_bank.LOAN_OPEN_STATUSES:
        return CollectResult(TICK_STATUS_SKIPPED)
    debtor, lender = int(peek.character_id), int(peek.region_id)
    dep_banks = [int(r[0]) for r in db.execute(text(
        "SELECT DISTINCT region_id FROM bank_deposits WHERE character_id = :c AND status = 'open'"),
        {"c": debtor}).fetchall()]
    locked = lock_banks(db, [lender] + dep_banks)
    placeholders, qparams = core.in_params("b", sorted(locked))
    dep_ids = [int(r[0]) for r in db.execute(text(
        f"SELECT id FROM bank_deposits WHERE character_id = :c AND status = 'open' AND region_id IN ({placeholders})"),
        {"c": debtor, **qparams}).fetchall()] if locked else []
    deposits = lock_deposits(db, dep_ids)
    loan = lock_loan(db, loan_id)
    if loan is None or loan.status not in econ_bank.LOAN_OPEN_STATUSES:
        return CollectResult(TICK_STATUS_SKIPPED)
    now = clock().replace(microsecond=0)
    apply_loan_state(loan, project_loan(loan, now, params))
    debt = int(loan.debt)
    if debt <= 0:
        close_loan(loan, now)
        return CollectResult(TICK_STATUS_DONE)
    wallet = econ_ledger.lock_characters(db, [debtor]).get(debtor, 0)
    open_rows = [d for d in deposits.values() if d.status == econ_bank.DEPOSIT_OPEN and int(d.character_id) == debtor]
    plan = econ_bank.plan_collection(
        debt, [(int(d.id), d.kind, int(d.amount), int(d.interest_accrued or 0)) for d in open_rows], wallet)
    if plan.total <= 0:
        return CollectResult(TICK_STATUS_DONE, overdue=loan.status == econ_bank.LOAN_OVERDUE)

    bank_ref = core.AccountRef.bank(lender)
    from_vault: Dict[int, int] = {}
    for take in plan.takes:
        row = deposits[take.deposit_id]
        row.interest_accrued = int(row.interest_accrued or 0) - take.from_interest
        row.amount = int(row.amount) - take.from_amount
        row.interest_base = min(int(row.interest_base or 0), int(row.amount))
        close_deposit_if_empty(row, now)
        from_vault[int(row.region_id)] = from_vault.get(int(row.region_id), 0) + take.total
    legs = [core.Leg(core.AccountRef.bank_deposits(y), bank_ref, amount) for y, amount in sorted(from_vault.items())]
    if plan.wallet > 0:
        legs.append(core.Leg(core.AccountRef.character(debtor), bank_ref, int(plan.wallet)))
    loan.debt = debt - plan.total
    loan.collected_total = int(loan.collected_total or 0) + plan.total
    if loan.debt <= 0:
        close_loan(loan, now)
    db.flush()
    econ_ledger.post_operation(
        db, op_type=core.OP_LOAN_COLLECT, legs=legs, source_service=SOURCE_SERVICE, region_id=lender,
        idempotency_key=key, apply_tax=False,
        metadata={"run_id": int(run_id), "loan_id": int(loan.id), "character_id": debtor,
                  "from_deposits": sum(from_vault.values()), "from_wallet": int(plan.wallet)},
    )
    logger.info("bank collect: loan=%s character=%s collected=%s left=%s", loan.id, debtor, plan.total, loan.debt)
    return CollectResult(TICK_STATUS_DONE, collected=plan.total, overdue=loan.status == econ_bank.LOAN_OVERDUE)


# ------------------------------------------------------------------------------------------------- character deletion

def close_character_positions(db: Session, character_id: int, now: datetime) -> Tuple[List[core.Leg], dict]:
    """Deletion hook (3.12), called by ``crud.post_character_deletion`` before it locks the character: open
    deposits -> ``V(Y) -> T(Y)`` (``W`` when region Y is gone), rows closed; the open loan written off (no money).
    Locks ``econ_banks`` of all positions asc -> deposits -> loans. Returns the legs (posted by the caller inside
    its ``character_deleted`` operation) and metadata."""
    cid = int(character_id)
    regions = [int(r[0]) for r in db.execute(text(
        "SELECT region_id FROM bank_deposits WHERE character_id = :c AND status = 'open' "
        "UNION SELECT region_id FROM bank_loans WHERE character_id = :c AND status IN ('active', 'overdue')"),
        {"c": cid}).fetchall()]
    if not regions:
        return [], {}
    lock_banks(db, regions)
    dep_ids = [int(r[0]) for r in db.execute(text(
        "SELECT id FROM bank_deposits WHERE character_id = :c AND status = 'open'"), {"c": cid}).fetchall()]
    deposits = lock_deposits(db, dep_ids)
    loans = _lock_open_loans(db, character_id=cid)
    per_bank: Dict[int, int] = {}
    for row in deposits.values():
        if row.status != econ_bank.DEPOSIT_OPEN:
            continue
        per_bank[int(row.region_id)] = per_bank.get(int(row.region_id), 0) + int(row.amount) + int(
            row.interest_accrued or 0)
        row.amount = 0
        row.interest_accrued = 0
        close_deposit_if_empty(row, now)
    names = region_names(db, per_bank)
    legs = [core.Leg(core.AccountRef.bank_deposits(y),
                     core.AccountRef.region(y) if y in names else core.AccountRef.world(), amount)
            for y, amount in sorted(per_bank.items()) if amount > 0]
    written_off = sum(write_off_loan_row(loan, now, DELETED_LOAN_NOTE) for loan in loans)
    db.flush()
    meta = {"bank_deposits_closed": sum(per_bank.values()), "loans_written_off": written_off}
    logger.info("bank deletion: character=%s deposits paid out=%s loans written off=%s", cid, meta[
        "bank_deposits_closed"], written_off)
    return legs, meta


# =====================================================================================================================
# Admin API (B6, contract 3.10) — list / detail / debtors / flag / capital / write-off.
# =====================================================================================================================
# Locks (3.8): flag / capital / write-off  econ_banks(X) (inserted if missing) -> loan row -> accounts;
#              fill regions (open_banks)   region rows -> econ_banks asc (locked before the fill's postings) -> accounts.

ADMIN_DEPOSITS_LIMIT = 500
# «Заполнить регионы по шаблонам» opens banks in regions with these templates (PM: столица и порт).
BANK_TEMPLATE_CODES = ("capital", "port")

MSG_BANK_NOT_FOUND = "Банк не найден"
MSG_REGION_NOT_FOUND = "Регион не найден"
MSG_TREASURY_SHORT = "В казне региона только {n}"
MSG_CAPITAL_OUT_LIMIT = "Банк может вернуть не больше {n}"
MSG_LOAN_ALREADY_CLOSED = "Займ уже закрыт"


def _kind_balances(db: Session, kind: str, region_ids: Sequence[int]) -> Dict[int, int]:
    ids = sorted({int(i) for i in region_ids})
    if not ids:
        return {}
    placeholders, params = core.in_params("r", ids)
    rows = db.execute(text(f"SELECT ref_id, balance FROM econ_accounts WHERE kind = :kind AND ref_id IN "
                           f"({placeholders})"), {"kind": kind, **params}).fetchall()
    return {int(r[0]): int(r[1] or 0) for r in rows}


def _account(db: Session, ref: core.AccountRef) -> int:
    return _kind_balances(db, ref.kind, [ref.ref_id]).get(int(ref.ref_id), 0)


def _last_posting_id(db: Session, ref: core.AccountRef) -> int:
    """Newest posting touching the account (0 when none) — part of the capital idempotency key."""
    account_id = db.execute(text(core.SQL_SELECT_ACCOUNT), {"kind": ref.kind, "ref_id": ref.ref_id}).scalar()
    if account_id is None:
        return 0
    return int(db.execute(text("SELECT MAX(id) FROM econ_postings WHERE from_account_id = :a OR to_account_id = :a"),
                          {"a": int(account_id)}).scalar() or 0)


def _stats(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, (str, bytes)):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _simulated(db: Session, region_ids: Sequence[int]) -> set:
    ids = sorted({int(i) for i in region_ids})
    if not ids:
        return set()
    placeholders, params = core.in_params("r", ids)
    rows = db.execute(text(f"SELECT region_id FROM econ_regions WHERE region_id IN ({placeholders}) "
                           f"AND template_code IS NOT NULL AND population > 0"), params).fetchall()
    return {int(r[0]) for r in rows}


def bankers_by_region(db: Session) -> Dict[int, List[dict]]:
    """Living NPC bankers grouped by the region their location resolves to (3.9 step 6)."""
    rows = db.execute(text(
        "SELECT id, name, current_location_id FROM characters WHERE is_npc = 1 AND npc_role = :role "
        "AND (npc_status IS NULL OR npc_status <> :dead) AND current_location_id IS NOT NULL ORDER BY id"),
        {"role": BANKER_ROLE, "dead": NPC_DEAD}).fetchall()
    regions: Dict[int, Optional[int]] = {}
    result: Dict[int, List[dict]] = {}
    for npc_id, name, location_id in rows:
        if location_id not in regions:
            regions[location_id] = econ_ledger.resolve_location(db, int(location_id))[0]
        region_id = regions[location_id]
        if region_id:
            result.setdefault(int(region_id), []).append({"npc_id": int(npc_id), "name": name})
    return result


def _character_names(db: Session, ids: Iterable[int]) -> Dict[int, str]:
    ids = sorted({int(i) for i in ids})
    if not ids:
        return {}
    placeholders, params = core.in_params("c", ids)
    rows = db.execute(text(f"SELECT id, name FROM characters WHERE id IN ({placeholders})"), params).fetchall()
    return {int(r[0]): r[1] for r in rows}


def _open_loans(db: Session, region_ids: Optional[Sequence[int]] = None) -> List["models.BankLoan"]:
    query = db.query(models.BankLoan).filter(models.BankLoan.status.in_(econ_bank.LOAN_OPEN_STATUSES))
    if region_ids is not None:
        query = query.filter(models.BankLoan.region_id.in_([int(i) for i in region_ids]))
    return query.order_by(models.BankLoan.id).all()


def _admin_items(db: Session, banks: Sequence["models.EconBank"], *, params, now: datetime) -> List[dict]:
    """``BankAdminItem`` per bank row (same order). Loan debts are projected to ``now``."""
    ids = [int(b.region_id) for b in banks]
    if not ids:
        return []
    names = region_names(db, ids)
    simulated = _simulated(db, ids)
    bankers = bankers_by_region(db)
    own = _kind_balances(db, core.KIND_BANK, ids)
    vaults = _kind_balances(db, core.KIND_BANK_DEPOSITS, ids)
    placeholders, in_args = core.in_params("r", ids)
    deposits = {int(r[0]): (int(r[1] or 0), int(r[2] or 0), int(r[3] or 0)) for r in db.execute(text(
        "SELECT region_id, COUNT(*), SUM(CASE WHEN kind = 'term' THEN 1 ELSE 0 END), "
        "COALESCE(SUM(amount + interest_accrued), 0) FROM bank_deposits "
        f"WHERE status = 'open' AND region_id IN ({placeholders}) GROUP BY region_id"), in_args).fetchall()}
    loans: Dict[int, List[econ_bank.LoanState]] = {}
    for row in _open_loans(db, ids):
        loans.setdefault(int(row.region_id), []).append(project_loan(row, now, params))

    items = []
    for bank in banks:
        rid = int(bank.region_id)
        count, term_count, deposits_sum = deposits.get(rid, (0, 0, 0))
        own_funds, vault = own.get(rid, 0), vaults.get(rid, 0)
        resident_deposits = int(bank.resident_deposits or 0)
        factor = bank_factor(bank)
        open_loans = loans.get(rid, [])
        items.append({
            "region_id": rid,
            "region_name": names[rid][0] if rid in names else None,
            "country_name": names[rid][1] if rid in names else None,
            "enabled": bank_is_open(bank, names),
            "simulated": rid in simulated,
            "bankers": bankers.get(rid, []),
            "own_funds": own_funds,
            "vault": vault,
            "deposits_sum": deposits_sum,
            "vault_ok": vault == deposits_sum,
            "deposits_count": count,
            "term_count": term_count,
            "resident_deposits": resident_deposits,
            "resident_loans": int(bank.resident_loans or 0),
            "reserve": econ_bank.reserve(resident_deposits, params.bank_reserve_ratio),
            "lendable": econ_bank.lendable(own_funds, resident_deposits, params),
            "loans_count": len(open_loans),
            "loans_debt": sum(int(s.debt) for s in open_loans),
            "overdue_count": sum(1 for s in open_loans if econ_bank.is_overdue(s, now)),
            "rate_factor": float(factor),
            "demand_rate_day": float(econ_bank.demand_rate(params, factor)),
            "term_rates": [{"term_days": t, "rate_day": float(econ_bank.term_rate(params, t, factor))}
                           for t in econ_bank.BANK_TERMS],
            "capital_seeded_at": bank.capital_seeded_at,
            "last_tick_at": bank.last_tick_at,
            "last_stats": _stats(bank.last_stats),
        })
    return items


def list_banks_admin(db: Session) -> dict:
    """Every ``econ_banks`` row (regions without a row are not listed — the flag lives in the regions list)."""
    banks = db.query(models.EconBank).order_by(models.EconBank.region_id).all()
    items = _admin_items(db, banks, params=load_params(db), now=now_utc())
    items.sort(key=lambda i: (i["region_name"] is None, i["region_name"] or "", i["region_id"]))
    totals = {
        "banks": len(items),
        "enabled": sum(1 for i in items if i["enabled"]),
        "own_funds": sum(i["own_funds"] for i in items),
        "player_deposits": sum(i["deposits_sum"] for i in items),
        "resident_deposits": sum(i["resident_deposits"] for i in items),
        "player_loans_debt": sum(i["loans_debt"] for i in items),
        "resident_loans": sum(i["resident_loans"] for i in items),
        "debtors": sum(i["overdue_count"] for i in items),
    }
    return {"items": items, "totals": totals}


def _admin_loan_out(row: "models.BankLoan", *, now: datetime, names, chars: Dict[int, str], params) -> dict:
    out = _loan_out(row, now=now, names=names, params=params)
    out.update(character_id=int(row.character_id), character_name=chars.get(int(row.character_id)))
    return out


def get_bank_admin(db: Session, region_id: int) -> dict:
    """``BankAdminDetail``: the item + open deposits (newest ``ADMIN_DEPOSITS_LIMIT``) + open loans."""
    bank = db.query(models.EconBank).filter(models.EconBank.region_id == int(region_id)).first()
    if bank is None:
        raise EconomyApiError(404, MSG_BANK_NOT_FOUND)
    params, now = load_params(db), now_utc()
    item = _admin_items(db, [bank], params=params, now=now)[0]
    deposits = (db.query(models.BankDeposit)
                .filter(models.BankDeposit.region_id == int(region_id),
                        models.BankDeposit.status == econ_bank.DEPOSIT_OPEN)
                .order_by(models.BankDeposit.id.desc()).limit(ADMIN_DEPOSITS_LIMIT).all())
    loans = _open_loans(db, [region_id])
    names = region_names(db, [region_id])
    chars = _character_names(db, [d.character_id for d in deposits] + [l.character_id for l in loans])
    banks = {int(region_id): bank}
    deposit_outs = []
    for row in deposits:
        out = _deposit_out(row, now=now, here_region=None, names=names, banks=banks, params=params)
        out.update(character_id=int(row.character_id), character_name=chars.get(int(row.character_id)),
                   status=row.status)
        deposit_outs.append(out)
    return {"item": item, "deposits": deposit_outs,
            "loans": [_admin_loan_out(l, now=now, names=names, chars=chars, params=params) for l in loans]}


def list_debtors(db: Session) -> List[dict]:
    """Open loans past ``due_at`` with a debt (projected to now), largest debt first."""
    params, now = load_params(db), now_utc()
    rows = [r for r in _open_loans(db) if r.due_at <= now]
    names = region_names(db, [r.region_id for r in rows])
    chars = _character_names(db, [r.character_id for r in rows])
    result = []
    for row in rows:
        state = project_loan(row, now, params)
        if not econ_bank.is_overdue(state, now):
            continue
        rid = int(row.region_id)
        result.append({
            "loan_id": int(row.id), "character_id": int(row.character_id),
            "character_name": chars.get(int(row.character_id)), "region_id": rid,
            "region_name": names[rid][0] if rid in names else None, "debt": int(state.debt),
            "principal": int(row.principal), "due_at": row.due_at, "overdue_days": (now - row.due_at).days,
            "penalty_total": int(state.penalty_total),
        })
    result.sort(key=lambda d: (-d["debt"], d["loan_id"]))
    return result


def ensure_bank_row(db: Session, region_id: int, now: datetime) -> "models.EconBank":
    """``econ_banks(X)`` FOR UPDATE, inserted (disabled, residents' clock = now) when missing."""
    bank = lock_banks(db, [region_id]).get(int(region_id))
    if bank is not None:
        return bank
    bank = models.EconBank(region_id=int(region_id), is_enabled=False, deposit_rate_factor=1, resident_deposits=0,
                           resident_loans=0, resident_dep_carry=0, resident_loan_carry=0, accrued_at=now)
    db.add(bank)
    try:
        db.flush()
    except IntegrityError:                                # a concurrent request created it
        raise EconomyApiError(409, MSG_RETRY)
    return bank


def seed_capital(db: Session, bank: "models.EconBank", *, params, actor_user_id: Optional[int],
                 now: datetime) -> int:
    """One-time start capital ``T(X) -> B(X)`` = ``min(bank_start_capital, max(0, treasury))``; marks the bank as
    seeded even when the amount is 0, so re-toggling never seeds twice. Caller holds ``econ_banks(X)``."""
    if bank.capital_seeded_at is not None:
        return 0
    region_id = int(bank.region_id)
    treasury = _account(db, core.AccountRef.region(region_id))
    amount = min(int(params.bank_start_capital), max(0, treasury))
    if amount > 0:
        try:
            econ_ledger.post_operation(
                db, op_type=core.OP_BANK_CAPITAL, source_service=SOURCE_SERVICE, region_id=region_id,
                actor_user_id=actor_user_id, idempotency_key=f"bank_capital:r:{region_id}:seed", apply_tax=False,
                legs=[core.Leg(core.AccountRef.region(region_id), core.AccountRef.bank(region_id), amount)],
                metadata={"seed": True},
            )
        except core.DuplicateOperation:                   # seeded before (row flag lost) — never twice
            amount = 0
    bank.capital_seeded_at = now
    logger.info("bank capital seed: region=%s amount=%s", region_id, amount)
    return amount


def set_bank_flag(db: Session, region_id: int, *, is_enabled: bool, seed: bool,
                  actor_user_id: Optional[int]) -> dict:
    """«Банк есть»: creates the row; the first switch-on with ``seed`` takes the start capital once."""
    if int(region_id) not in region_names(db, [region_id]):
        raise EconomyApiError(404, MSG_REGION_NOT_FOUND)
    now = now_utc()
    params = load_params(db)
    bank = ensure_bank_row(db, region_id, now)
    bank.is_enabled = bool(is_enabled)
    if is_enabled and seed:
        seed_capital(db, bank, params=params, actor_user_id=actor_user_id, now=now)
    db.flush()
    return _admin_items(db, [bank], params=params, now=now)[0]


def move_capital(db: Session, region_id: int, *, direction: str, amount: int, comment: str,
                 actor_user_id: Optional[int]) -> dict:
    """«Капитал из казны» (``in``: ``T(X) -> B(X)``) / «Вернуть капитал в казну» (``out``: ``B(X) -> T(X)``, at most
    the lendable part — the reserve for residents stays)."""
    x = int(region_id)
    if x not in region_names(db, [x]):
        raise EconomyApiError(404, MSG_REGION_NOT_FOUND)
    bank = lock_banks(db, [x]).get(x)
    if bank is None:
        raise EconomyApiError(404, MSG_BANK_NOT_FOUND)
    params = load_params(db)
    amount = int(amount)
    treasury_ref, bank_ref = core.AccountRef.region(x), core.AccountRef.bank(x)
    if direction == "in":
        available = max(0, _account(db, treasury_ref))
        refusal = MSG_TREASURY_SHORT.format(n=_fmt(db, available))
        leg = core.Leg(treasury_ref, bank_ref, amount)
    else:
        available = econ_bank.lendable(bank_account_balance(db, x), int(bank.resident_deposits or 0), params)
        refusal = MSG_CAPITAL_OUT_LIMIT.format(n=_fmt(db, available))
        leg = core.Leg(bank_ref, treasury_ref, amount)
    if amount > available:
        raise EconomyApiError(400, refusal)
    key = f"bank_capital:r:{x}:p{_last_posting_id(db, bank_ref)}:{direction}:{amount}"
    try:
        result = econ_ledger.post_operation(
            db, op_type=core.OP_BANK_CAPITAL, legs=[leg], source_service=SOURCE_SERVICE, region_id=x,
            actor_user_id=actor_user_id, comment=comment, idempotency_key=key, apply_tax=False,
            metadata={"direction": direction},
        )
    except core.InsufficientFunds:
        raise EconomyApiError(400, refusal)
    except core.DuplicateOperation:
        raise EconomyApiError(409, MSG_DUPLICATE)
    logger.info("bank capital: region=%s direction=%s amount=%s op=%s", x, direction, amount, result.operation_id)
    return {"operation_id": result.operation_id, "bank_balance": bank_account_balance(db, x),
            "treasury_balance": _account(db, treasury_ref)}


def write_off_loan(db: Session, loan_id: int, *, comment: str, actor_user_id: Optional[int]) -> dict:
    """«Списать долг»: accrued to now, then the whole debt is the bank's loss (no money moves)."""
    peek = db.query(models.BankLoan).filter(models.BankLoan.id == int(loan_id)).first()
    if peek is None:
        raise EconomyApiError(404, MSG_LOAN_NOT_FOUND)
    lock_banks(db, [peek.region_id])
    loan = lock_loan(db, peek.id)
    if loan is None or loan.status not in econ_bank.LOAN_OPEN_STATUSES:
        raise EconomyApiError(409, MSG_LOAN_ALREADY_CLOSED)
    params, now = load_params(db), now_utc()
    apply_loan_state(loan, project_loan(loan, now, params))
    debt = int(loan.debt)
    loan.written_off = int(loan.written_off or 0) + debt
    loan.debt = 0
    loan.status = econ_bank.LOAN_WRITTEN_OFF
    loan.active_character_id = None
    loan.closed_at = now
    loan.closed_by_user_id = actor_user_id
    loan.note = comment
    db.flush()
    logger.info("bank loan write-off: loan=%s character=%s amount=%s user=%s", loan.id, loan.character_id, debt,
                actor_user_id)
    return _loan_out(loan, now=now, names=region_names(db, [loan.region_id]), params=params)


def enabled_bank_ids(db: Session, region_ids: Optional[Iterable[int]] = None) -> set:
    """Regions with «Банк есть» (row enabled and the region still exists)."""
    sql = "SELECT b.region_id FROM econ_banks b JOIN Regions r ON r.id = b.region_id WHERE b.is_enabled = 1"
    params: dict = {}
    if region_ids is not None:
        ids = sorted({int(i) for i in region_ids})
        if not ids:
            return set()
        placeholders, params = core.in_params("r", ids)
        sql += f" AND b.region_id IN ({placeholders})"
    return {int(r[0]) for r in db.execute(text(sql), params).fetchall()}
