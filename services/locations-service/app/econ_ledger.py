"""FEAT-181 world economy — async executor of the econ_core contract (SQLAlchemy AsyncSession).

CANONICAL ASYNC COPY: services/locations-service/app/econ_ledger.py.
A byte-identical copy lives in dungeon-service (CI `econ-contract-copies`).
It mirrors the sync executor (canonical in character-service) function by function:
same names, same behaviour, `async def` where the database is touched.
Keep this file free of service-specific imports — only econ_core and SQLAlchemy.

Rules for callers (see docs/services/character-service.md, «Economy ledger»):
  * nobody changes characters.currency_balance or econ_accounts.balance except via post_operation;
  * lock your business rows first, call post_operation as the last DB step, then commit;
  * post_operation NEVER commits or rolls back: on an exception roll back your transaction;
  * never keep the transaction open across an HTTP call.
"""

import json
import logging
from contextlib import asynccontextmanager, contextmanager
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import event, inspect as sa_inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import econ_core as core
from econ_core import (  # noqa: F401  (re-exported for callers: `from econ_ledger import AccountRef, Leg, ...`)
    AccountRef,
    CurrencyForms,
    DuplicateOperation,
    EconomyError,
    EconomySettings,
    InsufficientFunds,
    Leg,
    PostingResult,
    format_currency,
    plural_ru,
)

logger = logging.getLogger("econ_ledger")

# Session.info flag that lets a block write characters.currency_balance through the ORM
# without tripping the balance guard (test fixtures, data repair scripts).
ALLOW_DIRECT_BALANCE_KEY = "econ_allow_direct_balance"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _dialect(session: AsyncSession) -> str:
    return session.get_bind().dialect.name


@asynccontextmanager
async def _savepoint(session: AsyncSession):
    """SAVEPOINT so a failed INSERT leaves the caller's transaction usable.

    SQLite (tests) is skipped: pysqlite emits SAVEPOINT outside its implicit transaction,
    and RELEASE would then commit the caller's work. Races do not happen there anyway.
    """
    if _dialect(session) == "sqlite":
        yield
        return
    async with session.begin_nested():
        yield


def _expire_character_balances(session: AsyncSession, character_ids: Iterable[int]) -> None:
    """Drop stale ORM copies of currency_balance after the raw UPDATEs."""
    ids = set(character_ids)
    if not ids:
        return
    for obj in list(session.sync_session.identity_map.values()):
        if getattr(type(obj), "__tablename__", None) == "characters" and getattr(obj, "id", None) in ids:
            session.expire(obj, ["currency_balance"])


# ---------------------------------------------------------------------------
# Settings / currency
# ---------------------------------------------------------------------------

async def get_economy_settings(session: AsyncSession) -> EconomySettings:
    """econ_settings row with a 60 s per-process cache; defaults when the row/table is missing."""
    cached = core.cached_settings()
    if cached is not None:
        return cached
    try:
        row = (await session.execute(text(core.SQL_SELECT_SETTINGS))).first()
    except Exception:  # table not migrated yet — never break a money flow over a label
        logger.warning("econ_settings unavailable, using defaults", exc_info=True)
        return core.DEFAULT_SETTINGS
    return core.store_settings(core.settings_from_row(row))


async def get_currency_forms(session: AsyncSession) -> CurrencyForms:
    return (await get_economy_settings(session)).forms


def invalidate_settings_cache() -> None:
    core.invalidate_settings_cache()


# ---------------------------------------------------------------------------
# World hierarchy
# ---------------------------------------------------------------------------

async def resolve_location(session: AsyncSession, location_id: Optional[int]) -> Tuple[Optional[int], Optional[int]]:
    """Location -> (region_id, country_id); (None, None) when the location has no region."""
    if not location_id:
        return None, None
    row = (await session.execute(text(core.SQL_RESOLVE_LOCATION), {"location_id": int(location_id)})).first()
    if row is None:
        return None, None
    return (int(row[0]) if row[0] is not None else None, int(row[1]) if row[1] is not None else None)


async def treasury_for_location(session: AsyncSession, location_id: Optional[int]) -> AccountRef:
    """Region treasury of the location, else the world treasury («Казна Скитальцев»)."""
    region_id, _country_id = await resolve_location(session, location_id)
    return AccountRef.region(region_id) if region_id else AccountRef.world()


async def _region_countries(session: AsyncSession, region_ids: Sequence[int]) -> Dict[int, Optional[int]]:
    if not region_ids:
        return {}
    placeholders, params = core.in_params("r", list(region_ids))
    rows = (await session.execute(text(core.sql_region_countries(placeholders)), params)).fetchall()
    return {int(r[0]): (int(r[1]) if r[1] is not None else None) for r in rows}


# ---------------------------------------------------------------------------
# Locks / accounts
# ---------------------------------------------------------------------------

async def lock_characters(session: AsyncSession, character_ids: Iterable[int]) -> Dict[int, int]:
    """SELECT ... FOR UPDATE the characters rows in ascending id order -> {id: balance}."""
    ids = sorted({int(i) for i in character_ids})
    if not ids:
        return {}
    placeholders, params = core.in_params("c", ids)
    sql = core.sql_lock_characters(placeholders, core.supports_for_update(_dialect(session)))
    rows = (await session.execute(text(sql), params)).fetchall()
    return {int(r[0]): int(r[1] or 0) for r in rows}


async def _account_name(session: AsyncSession, ref: AccountRef) -> Optional[str]:
    if ref.kind in core.SINGLETON_NAMES:
        return core.SINGLETON_NAMES[ref.kind]
    sql = core.SQL_ACCOUNT_NAME.get(ref.kind)
    if sql is None:
        return None
    try:
        row = (await session.execute(text(sql), {"ref_id": ref.ref_id})).first()
    except Exception:  # hierarchy table absent (fresh DB) — the name is cosmetic
        return None
    return row[0] if row else None


async def get_or_create_account(session: AsyncSession, ref: AccountRef) -> int:
    """econ_accounts.id for (kind, ref_id); inserts the row on first use."""
    core.validate_account(ref)
    params = {"kind": ref.kind, "ref_id": ref.ref_id}
    row = (await session.execute(text(core.SQL_SELECT_ACCOUNT), params)).first()
    if row is not None:
        return int(row[0])
    name = await _account_name(session, ref)
    try:
        async with _savepoint(session):
            result = await session.execute(text(core.SQL_INSERT_ACCOUNT), {
                **params,
                "name": name,
                "allow_negative": 1 if ref.allow_negative else 0,
            })
            return int(result.lastrowid)
    except IntegrityError:  # created concurrently
        row = (await session.execute(text(core.SQL_SELECT_ACCOUNT), params)).first()
        if row is None:
            raise
        return int(row[0])


async def deactivate_account(session: AsyncSession, ref: AccountRef) -> None:
    """Mark an account inactive (character / region / country deleted). The row and journal stay."""
    core.validate_account(ref)
    await session.execute(text(core.SQL_DEACTIVATE_ACCOUNT), {"kind": ref.kind, "ref_id": ref.ref_id})


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------

async def _insert_operation(session: AsyncSession, plan: core.OperationPlan, *, idempotency_key, location_id,
                            region_id, actor_user_id, source_service, comment, metadata) -> int:
    if idempotency_key is not None:
        row = (await session.execute(text(core.SQL_SELECT_OPERATION_BY_KEY), {"key": idempotency_key})).first()
        if row is not None:
            raise DuplicateOperation(int(row[0]))
    params = {
        "op_type": plan.op_type,
        "idempotency_key": idempotency_key,
        "location_id": location_id,
        "region_id": region_id,
        "actor_user_id": actor_user_id,
        "source_service": source_service,
        "comment": comment,
        "metadata": json.dumps(metadata, ensure_ascii=False, default=str) if metadata is not None else None,
    }
    try:
        async with _savepoint(session):
            return int((await session.execute(text(core.SQL_INSERT_OPERATION), params)).lastrowid)
    except IntegrityError:
        if idempotency_key is None:
            raise
        row = (await session.execute(text(core.SQL_SELECT_OPERATION_BY_KEY), {"key": idempotency_key})).first()
        if row is None:
            raise
        raise DuplicateOperation(int(row[0]))


async def post_operation(
    session: AsyncSession,
    *,
    op_type: str,
    legs: Iterable[Leg],
    source_service: str,
    location_id: Optional[int] = None,
    region_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    comment: Optional[str] = None,
    metadata: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
    apply_tax: bool = True,
) -> PostingResult:
    """Post one business operation (journal header + legs) inside the caller's transaction.

    Raises EconomyError (invalid request / missing character), InsufficientFunds (a non-negative
    account would go below 0) or DuplicateOperation (idempotency_key already used; nothing moved).
    Never commits or rolls back. Returns PostingResult(operation_id, {character_id: new_balance});
    operation_id is None when every leg amount was 0 (no journal row is written).
    """
    legs = list(legs)
    # Cheap validation first: a bad request must not touch the DB at all.
    core.validate_operation(op_type, legs, source_service=source_service, comment=comment,
                            idempotency_key=idempotency_key)
    region_countries: Dict[int, Optional[int]] = {}
    tax_rate = core.DEFAULT_COUNTRY_TAX_RATE
    regions = core.tax_region_ids([leg for leg in legs if leg.amount > 0], apply_tax)
    if regions:
        tax_rate = (await get_economy_settings(session)).country_tax_rate
        region_countries = await _region_countries(session, regions)
    plan = core.plan_operation(
        op_type, legs, source_service=source_service, comment=comment, idempotency_key=idempotency_key,
        apply_tax=apply_tax, tax_rate=tax_rate, region_countries=region_countries,
    )
    if plan is None:
        return PostingResult(None, {})

    if region_id is None and location_id is not None:
        region_id, _country = await resolve_location(session, location_id)

    # Pending ORM inserts (e.g. a just-created row the caller relies on) must exist before the raw SQL below.
    await session.flush()

    operation_id = await _insert_operation(
        session, plan, idempotency_key=idempotency_key, location_id=location_id, region_id=region_id,
        actor_user_id=actor_user_id, source_service=source_service, comment=comment, metadata=metadata,
    )
    account_ids = {}
    for ref in plan.accounts:
        account_ids[ref] = await get_or_create_account(session, ref)

    for step in core.apply_steps(plan, account_ids):
        if step.target == "character":
            if step.delta < 0:
                res = await session.execute(text(core.SQL_DEBIT_CHARACTER),
                                            {"id": step.row_id, "amount": -step.delta})
                if res.rowcount == 0:
                    raise InsufficientFunds(step.account, -step.delta)
            else:
                res = await session.execute(text(core.SQL_CREDIT_CHARACTER),
                                            {"id": step.row_id, "amount": step.delta})
                if res.rowcount == 0:
                    raise EconomyError(f"character {step.row_id} not found")
        else:
            res = await session.execute(text(core.SQL_APPLY_ACCOUNT), {"id": step.row_id, "delta": step.delta})
            if res.rowcount == 0:
                raise InsufficientFunds(step.account, -step.delta)

    for leg in plan.legs:
        await session.execute(text(core.SQL_INSERT_POSTING), {
            "operation_id": operation_id,
            "from_account_id": account_ids[leg.src],
            "to_account_id": account_ids[leg.dst],
            "amount": leg.amount,
            "leg_type": leg.leg_type,
        })

    balances: Dict[int, int] = {}
    char_ids = plan.character_ids
    if char_ids:
        placeholders, params = core.in_params("c", char_ids)
        rows = (await session.execute(text(core.sql_character_balances(placeholders)), params)).fetchall()
        balances = {int(r[0]): int(r[1] or 0) for r in rows}
        _expire_character_balances(session, char_ids)
    return PostingResult(operation_id, balances)


# ---------------------------------------------------------------------------
# ORM guard: nobody writes Character.currency_balance through the ORM.
# AsyncSession flushes through its sync Session, so the sync `before_flush` event covers it.
# ---------------------------------------------------------------------------

_installed_guards: List[Tuple[type, str]] = []


@contextmanager
def allow_direct_balance_write(session):
    """Let this block flush ORM changes of the guarded balance column (fixtures, repair scripts)."""
    info = session.info
    previous = info.get(ALLOW_DIRECT_BALANCE_KEY)
    info[ALLOW_DIRECT_BALANCE_KEY] = True
    try:
        yield session
    finally:
        if previous is None:
            info.pop(ALLOW_DIRECT_BALANCE_KEY, None)
        else:
            info[ALLOW_DIRECT_BALANCE_KEY] = previous


def install_balance_guard(model_cls: type, attr: str = "currency_balance", *, strict: bool = True,
                          session_cls: type = Session) -> None:
    """`before_flush` listener: a persistent `model_cls.attr` modified via the ORM raises EconomyError
    (strict) or logs a warning (strict=False). New rows are not checked (insert them with 0 and post
    the opening balance). Idempotent per (model, attr).
    """
    key = (model_cls, attr)
    if key in _installed_guards:
        return
    _installed_guards.append(key)

    def _guard(session, flush_context, instances):
        if session.info.get(ALLOW_DIRECT_BALANCE_KEY):
            return
        for obj in session.dirty:
            if not isinstance(obj, model_cls):
                continue
            history = sa_inspect(obj).attrs[attr].history
            if not history.added:
                continue
            if history.deleted and list(history.added) == list(history.deleted):
                continue
            message = (f"direct write of {model_cls.__name__}.{attr} (id={getattr(obj, 'id', None)}); "
                       f"use econ_ledger.post_operation")
            if strict:
                raise EconomyError(message)
            logger.warning(message)

    event.listen(session_cls, "before_flush", _guard)
