"""FEAT-181 world economy — read models and admin money actions for the economy API.

Reads are plain parameterised SQL (portable MySQL 8 / SQLite). Every money movement goes through
`econ_ledger.post_operation`; this module never writes a balance itself. Functions here never
commit: the router commits after a successful call and rolls back on any exception.
"""

import json
import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

import econ_core as core
import econ_ledger
import models

logger = logging.getLogger("character-service.economy")

SOURCE_SERVICE = "character-service"

# Admin emission may only go into a treasury or a region's population purse (FEAT-182).
EMISSION_TARGET_KINDS = frozenset({core.KIND_REGION_TREASURY, core.KIND_COUNTRY_TREASURY,
                                   core.KIND_WORLD_TREASURY, core.KIND_POPULATION_PURSE})
# Account kinds that belong to a region (name taken from Regions, operation tagged with region_id).
REGION_ACCOUNT_KINDS = frozenset({core.KIND_REGION_TREASURY, core.KIND_POPULATION_PURSE,
                                  core.KIND_BANK, core.KIND_BANK_DEPOSITS})
# Accounts an admin correction must never touch: the money sources themselves and the auction
# accounts, whose balances must equal the auction tables (sub-invariants). FEAT-184: bank accounts too — the vault
# must equal the deposit rows, the bank's own money moves only via the capital endpoint.
ADJUST_FORBIDDEN_KINDS = frozenset({core.KIND_EMISSION, core.KIND_ADJUSTMENT,
                                    core.KIND_AUCTION_ESCROW, core.KIND_AUCTION_STORAGE,
                                    core.KIND_BANK, core.KIND_BANK_DEPOSITS})

MAX_DRIFTING_CHARACTERS = 50
# LIKE escape character; '!' instead of a backslash so the same SQL works in MySQL and SQLite.
LIKE_ESCAPE = "!"


class EconomyApiError(Exception):
    """Business error with an HTTP status and a Russian message for the user."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _int(value) -> int:
    return int(value or 0)


def _like_pattern(q: str) -> str:
    escaped = q.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2).replace("%", LIKE_ESCAPE + "%").replace("_", LIKE_ESCAPE + "_")
    return f"%{escaped}%"


def _scalar(db: Session, sql: str, params: Optional[dict] = None) -> int:
    return _int(db.execute(text(sql), params or {}).scalar())


def _account_balance(db: Session, account_id: int) -> int:
    """Current balance of an account; character accounts read characters.currency_balance."""
    row = db.execute(text(
        "SELECT a.kind, a.ref_id, a.balance, c.currency_balance FROM econ_accounts a "
        "LEFT JOIN characters c ON a.kind = 'character' AND c.id = a.ref_id WHERE a.id = :id"
    ), {"id": account_id}).first()
    if row is None:
        return 0
    return _int(row[3]) if row[0] == core.KIND_CHARACTER else _int(row[2])


def ensure_treasury_accounts(db: Session) -> bool:
    """Create the missing treasury accounts of existing regions/countries (they are otherwise
    created lazily on the first posting), so the admin can address every treasury by account_id.
    Returns True when something was inserted (the caller commits)."""
    created = False
    missing_countries = db.execute(text(
        "SELECT co.id FROM Countries co LEFT JOIN econ_accounts a "
        "ON a.kind = 'country_treasury' AND a.ref_id = co.id WHERE a.id IS NULL"
    )).fetchall()
    for (country_id,) in missing_countries:
        econ_ledger.get_or_create_account(db, core.AccountRef.country(int(country_id)))
        created = True
    missing_regions = db.execute(text(
        "SELECT r.id FROM Regions r LEFT JOIN econ_accounts a "
        "ON a.kind = 'region_treasury' AND a.ref_id = r.id WHERE a.id IS NULL"
    )).fetchall()
    for (region_id,) in missing_regions:
        econ_ledger.get_or_create_account(db, core.AccountRef.region(int(region_id)))
        created = True
    return created


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def read_settings(db: Session) -> core.EconomySettings:
    """Fresh settings row (no cache): the admin must see what is stored right now."""
    row = db.execute(text(core.SQL_SELECT_SETTINGS)).first()
    return core.settings_from_row(row)


def settings_response(settings: core.EconomySettings) -> dict:
    return {"currency": settings.forms.as_dict(), "country_tax_rate": float(settings.country_tax_rate)}


def update_settings(db: Session, *, forms: Dict[str, str], country_tax_rate: Decimal,
                    user_id: Optional[int]) -> core.EconomySettings:
    params = {
        "name": forms["name"], "genitive": forms["genitive"], "one": forms["one"],
        "few": forms["few"], "many": forms["many"], "short": forms["short"],
        "rate": str(country_tax_rate), "user_id": user_id,  # str: exact DECIMAL, portable driver type
    }
    result = db.execute(text(
        "UPDATE econ_settings SET currency_name = :name, currency_genitive = :genitive, "
        "currency_one = :one, currency_few = :few, currency_many = :many, currency_short = :short, "
        "country_tax_rate = :rate, updated_by_user_id = :user_id WHERE id = 1"
    ), params)
    if result.rowcount == 0:  # singleton row missing (should not happen after migration 027)
        db.execute(text(
            "INSERT INTO econ_settings (id, currency_name, currency_genitive, currency_one, currency_few, "
            "currency_many, currency_short, country_tax_rate, updated_by_user_id) "
            "VALUES (1, :name, :genitive, :one, :few, :many, :short, :rate, :user_id)"
        ), params)
    return read_settings(db)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

SQL_CHARACTER_LEDGER = """
SELECT c.id, c.name, c.currency_balance, COALESCE(inc.s, 0) - COALESCE(outg.s, 0) AS ledger
FROM characters c
LEFT JOIN econ_accounts a ON a.kind = 'character' AND a.ref_id = c.id
LEFT JOIN (SELECT to_account_id AS acc, SUM(amount) AS s FROM econ_postings GROUP BY to_account_id) inc
       ON inc.acc = a.id
LEFT JOIN (SELECT from_account_id AS acc, SUM(amount) AS s FROM econ_postings GROUP BY from_account_id) outg
       ON outg.acc = a.id
WHERE c.currency_balance <> COALESCE(inc.s, 0) - COALESCE(outg.s, 0)
ORDER BY c.id
LIMIT :limit
"""


def get_summary(db: Session) -> dict:
    settings = econ_ledger.get_economy_settings(db)

    players = _scalar(db, "SELECT COALESCE(SUM(currency_balance), 0) FROM characters WHERE is_npc = 0")
    npcs = _scalar(db, "SELECT COALESCE(SUM(currency_balance), 0) FROM characters WHERE is_npc = 1")

    kind_sums = {
        row[0]: _int(row[1]) for row in db.execute(text(
            "SELECT kind, COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind <> 'character' GROUP BY kind"
        )).fetchall()
    }
    escrow = kind_sums.get(core.KIND_AUCTION_ESCROW, 0)
    storage = kind_sums.get(core.KIND_AUCTION_STORAGE, 0)
    regions_total = kind_sums.get(core.KIND_REGION_TREASURY, 0)
    countries_total = kind_sums.get(core.KIND_COUNTRY_TREASURY, 0)
    world = kind_sums.get(core.KIND_WORLD_TREASURY, 0)
    purses = kind_sums.get(core.KIND_POPULATION_PURSE, 0)
    banks = kind_sums.get(core.KIND_BANK, 0)
    vaults = kind_sums.get(core.KIND_BANK_DEPOSITS, 0)
    sources = sum(kind_sums.get(k, 0) for k in core.SOURCE_KINDS)

    held = players + npcs + sum(v for k, v in kind_sums.items() if k not in core.SOURCE_KINDS)
    issued = -sources
    ledger_sum = held + sources

    escrow_expected = _scalar(db, (
        "SELECT COALESCE(SUM(current_bid), 0) FROM auction_listings "
        "WHERE status = 'active' AND current_bidder_id IS NOT NULL"
    ))
    storage_expected = _scalar(db, "SELECT COALESCE(SUM(gold_amount), 0) FROM auction_storage")
    # FEAT-184 sub-invariant: the vaults hold exactly the open player deposit rows
    vaults_expected = _scalar(db, (
        "SELECT COALESCE(SUM(amount + interest_accrued), 0) FROM bank_deposits WHERE status = 'open'"
    ))

    drifting = [
        {"character_id": int(r[0]), "name": r[1], "balance": _int(r[2]), "ledger": _int(r[3])}
        for r in db.execute(text(SQL_CHARACTER_LEDGER), {"limit": MAX_DRIFTING_CHARACTERS}).fetchall()
    ]

    invariant = {
        "ok": (ledger_sum == 0 and escrow_expected == escrow and storage_expected == storage
               and vaults_expected == vaults and not drifting),
        "ledger_sum": ledger_sum,
        "escrow_expected": escrow_expected,
        "escrow_actual": escrow,
        "storage_expected": storage_expected,
        "storage_actual": storage,
        "bank_deposits_expected": vaults_expected,
        "bank_deposits_actual": vaults,
        "drifting_characters": drifting,
    }

    return {
        "currency": settings.forms.as_dict(),
        "totals": {
            "issued": issued, "held": held, "players": players, "npcs": npcs, "escrow": escrow,
            "auction_storage": storage, "region_treasuries": regions_total,
            "country_treasuries": countries_total, "world_treasury": world,
            "population_purses": purses, "banks": banks, "bank_deposits": vaults,
        },
        "invariant": invariant,
        "countries": _treasury_tree(db),
        "system_accounts": _system_accounts(db),
        "settings": {"country_tax_rate": float(settings.country_tax_rate)},
    }


def _treasury_tree(db: Session) -> List[dict]:
    """Country treasuries with their region treasuries. Current names from Countries/Regions,
    snapshot name for deleted ones. Regions whose country is unknown (deleted region, or its
    country has no treasury) go into a trailing «Без страны» group with account_id = None."""
    countries = db.execute(text(
        "SELECT a.id, a.ref_id, COALESCE(co.name, a.name), a.balance, a.is_active "
        "FROM econ_accounts a LEFT JOIN Countries co ON co.id = a.ref_id "
        "WHERE a.kind = 'country_treasury' ORDER BY COALESCE(co.name, a.name), a.id"
    )).fetchall()
    regions = db.execute(text(
        "SELECT a.id, a.ref_id, COALESCE(r.name, a.name), a.balance, a.is_active, r.country_id "
        "FROM econ_accounts a LEFT JOIN Regions r ON r.id = a.ref_id "
        "WHERE a.kind = 'region_treasury' ORDER BY COALESCE(r.name, a.name), a.id"
    )).fetchall()
    purses = {
        int(r[1]): (int(r[0]), _int(r[2])) for r in db.execute(text(
            "SELECT id, ref_id, balance FROM econ_accounts WHERE kind = 'population_purse'"
        )).fetchall()
    }

    tree: List[dict] = []
    by_country: Dict[int, dict] = {}
    for acc_id, country_id, name, balance, is_active in countries:
        node = {"account_id": int(acc_id), "country_id": int(country_id), "name": name,
                "balance": _int(balance), "is_active": bool(is_active), "regions": []}
        tree.append(node)
        by_country[int(country_id)] = node

    orphans: List[dict] = []
    for acc_id, region_id, name, balance, is_active, country_id in regions:
        purse_id, purse_balance = purses.get(int(region_id), (None, None))
        item = {"account_id": int(acc_id), "region_id": int(region_id), "name": name,
                "balance": _int(balance), "is_active": bool(is_active),
                "purse_account_id": purse_id, "purse_balance": purse_balance}
        parent = by_country.get(int(country_id)) if country_id is not None else None
        (parent["regions"] if parent else orphans).append(item)
    if orphans:
        tree.append({"account_id": None, "country_id": None, "name": "Без страны", "balance": 0,
                     "is_active": False, "regions": orphans})
    return tree


def _system_accounts(db: Session) -> List[dict]:
    rows = db.execute(text(
        "SELECT id, kind, name, balance FROM econ_accounts "
        "WHERE kind NOT IN ('character', 'region_treasury', 'country_treasury', 'population_purse', 'bank', "
        "'bank_deposits') "
        "ORDER BY id"
    )).fetchall()
    return [{"account_id": int(r[0]), "kind": r[1], "name": r[2], "balance": _int(r[3])} for r in rows]


# ---------------------------------------------------------------------------
# Accounts listing
# ---------------------------------------------------------------------------

# Non-character accounts from econ_accounts + every existing character (account_id NULL when the
# character has never had a posting; such rows get an account created for the returned page).
SQL_ACCOUNTS_UNION = """
SELECT * FROM (
    SELECT a.id AS account_id, a.kind AS kind, a.ref_id AS ref_id,
           COALESCE(r.name, co.name, a.name) AS name, a.balance AS balance, a.is_active AS is_active
    FROM econ_accounts a
    LEFT JOIN Regions r ON a.kind IN ('region_treasury', 'population_purse', 'bank', 'bank_deposits')
                       AND r.id = a.ref_id
    LEFT JOIN Countries co ON a.kind = 'country_treasury' AND co.id = a.ref_id
    WHERE a.kind <> 'character'
    UNION ALL
    SELECT a.id AS account_id, 'character' AS kind, c.id AS ref_id, c.name AS name,
           c.currency_balance AS balance, COALESCE(a.is_active, 1) AS is_active
    FROM characters c
    LEFT JOIN econ_accounts a ON a.kind = 'character' AND a.ref_id = c.id
) t
WHERE (:kind IS NULL OR t.kind = :kind)
  AND (:q IS NULL OR t.name LIKE :q ESCAPE '!')
"""


def list_accounts(db: Session, *, kind: Optional[str], q: Optional[str], page: int,
                  page_size: int) -> Tuple[List[dict], int, bool]:
    """Returns (items, total, created) — created=True when accounts were inserted (caller commits)."""
    params = {"kind": kind, "q": _like_pattern(q) if q else None}
    total = _scalar(db, f"SELECT COUNT(*) FROM ({SQL_ACCOUNTS_UNION}) cnt", params)
    rows = db.execute(text(
        SQL_ACCOUNTS_UNION + " ORDER BY CASE WHEN t.kind = 'character' THEN 1 ELSE 0 END, t.kind, t.name, t.ref_id"
        " LIMIT :limit OFFSET :offset"
    ), {**params, "limit": page_size, "offset": (page - 1) * page_size}).fetchall()

    created = False
    items = []
    for account_id, row_kind, ref_id, name, balance, is_active in rows:
        if account_id is None:  # character without an account yet — make it addressable
            account_id = econ_ledger.get_or_create_account(db, core.AccountRef(row_kind, int(ref_id)))
            created = True
        items.append({"account_id": int(account_id), "kind": row_kind, "ref_id": int(ref_id), "name": name,
                      "balance": _int(balance), "is_active": bool(is_active)})
    return items, total, created


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------

def _account_infos(db: Session, account_ids: List[int]) -> Dict[int, dict]:
    if not account_ids:
        return {}
    placeholders, params = core.in_params("a", sorted(set(account_ids)))
    rows = db.execute(text(
        "SELECT a.id, a.kind, a.ref_id, COALESCE(c.name, r.name, co.name, a.name) "
        "FROM econ_accounts a "
        "LEFT JOIN characters c ON a.kind = 'character' AND c.id = a.ref_id "
        "LEFT JOIN Regions r ON a.kind IN ('region_treasury', 'population_purse', 'bank', 'bank_deposits') "
        "AND r.id = a.ref_id "
        "LEFT JOIN Countries co ON a.kind = 'country_treasury' AND co.id = a.ref_id "
        f"WHERE a.id IN ({placeholders})"
    ), params).fetchall()
    return {int(r[0]): {"account_id": int(r[0]), "kind": r[1], "ref_id": int(r[2]), "name": r[3]} for r in rows}


def _metadata(value):
    if value is None or isinstance(value, dict):
        return value
    if isinstance(value, (str, bytes)):
        try:
            parsed = json.loads(value)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return None


def list_operations(db: Session, *, account_id: Optional[int], character_id: Optional[int],
                    op_type: Optional[str], region_id: Optional[int], date_from: Optional[date],
                    date_to: Optional[date], page: int, page_size: int,
                    exclude_op_type: Optional[str] = None) -> Tuple[List[dict], int]:
    Op, Posting = models.EconOperation, models.EconPosting
    query = db.query(Op)
    if op_type:
        query = query.filter(Op.op_type == op_type)
    if exclude_op_type:
        query = query.filter(Op.op_type != exclude_op_type)
    if region_id is not None:
        query = query.filter(Op.region_id == region_id)
    if date_from is not None:
        query = query.filter(Op.created_at >= datetime.combine(date_from, time.min))
    if date_to is not None:  # inclusive day
        query = query.filter(Op.created_at < datetime.combine(date_to + timedelta(days=1), time.min))
    account_filters = []
    if account_id is not None:
        account_filters.append(int(account_id))
    if character_id is not None:
        row = db.execute(text(core.SQL_SELECT_ACCOUNT),
                         {"kind": core.KIND_CHARACTER, "ref_id": int(character_id)}).first()
        if row is None:
            return [], 0
        account_filters.append(int(row[0]))
    for acc in account_filters:
        touching = db.query(Posting.operation_id).filter(
            (Posting.from_account_id == acc) | (Posting.to_account_id == acc))
        query = query.filter(Op.id.in_(touching))

    total = query.count()
    operations = query.order_by(Op.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    account_ids: List[int] = []
    for op in operations:
        for p in op.postings:
            account_ids.extend([int(p.from_account_id), int(p.to_account_id)])
    infos = _account_infos(db, account_ids)

    def _ref(acc_id) -> dict:
        return infos.get(int(acc_id), {"account_id": int(acc_id), "kind": None, "ref_id": None, "name": None})

    items = []
    for op in operations:
        items.append({
            "id": int(op.id),
            "op_type": op.op_type,
            "created_at": op.created_at,
            "source_service": op.source_service,
            "location_id": op.location_id,
            "region_id": op.region_id,
            "actor_user_id": op.actor_user_id,
            "comment": op.comment,
            "metadata": _metadata(op.metadata_),
            "postings": [
                {"from": _ref(p.from_account_id), "to": _ref(p.to_account_id), "amount": int(p.amount),
                 "leg_type": p.leg_type}
                for p in sorted(op.postings, key=lambda p: p.id)
            ],
        })
    return items, total


# ---------------------------------------------------------------------------
# Admin money actions
# ---------------------------------------------------------------------------

def _load_account(db: Session, account_id: int) -> Tuple[core.AccountRef, bool]:
    row = db.execute(text("SELECT kind, ref_id, is_active FROM econ_accounts WHERE id = :id"),
                     {"id": account_id}).first()
    if row is None:
        raise EconomyApiError(404, "Счёт не найден")
    return core.AccountRef(row[0], int(row[1])), bool(row[2])


def _region_of(ref: core.AccountRef) -> Optional[int]:
    return ref.ref_id if ref.kind in REGION_ACCOUNT_KINDS else None


def emit(db: Session, *, account_id: int, amount: int, comment: str, actor_user_id: Optional[int]) -> dict:
    ref, is_active = _load_account(db, account_id)
    if ref.kind not in EMISSION_TARGET_KINDS:
        raise EconomyApiError(400, "Эмиссия возможна только в казну региона, страны, Казну Скитальцев или кошелёк жителей региона")
    if not is_active:
        raise EconomyApiError(400, "Счёт закрыт")
    result = econ_ledger.post_operation(
        db, op_type=core.OP_ADMIN_EMISSION, legs=[core.Leg(core.AccountRef.emission(), ref, amount)],
        source_service=SOURCE_SERVICE, region_id=_region_of(ref), actor_user_id=actor_user_id,
        comment=comment, apply_tax=False,
    )
    return {"operation_id": result.operation_id, "account_id": account_id,
            "balance": _account_balance(db, account_id)}


def adjust(db: Session, *, account_id: int, delta: int, comment: str, actor_user_id: Optional[int]) -> dict:
    ref, is_active = _load_account(db, account_id)
    if ref.kind in ADJUST_FORBIDDEN_KINDS:
        raise EconomyApiError(400, "Этот счёт нельзя корректировать")
    if not is_active:
        raise EconomyApiError(400, "Счёт закрыт")
    if ref.is_character and db.execute(text("SELECT id FROM characters WHERE id = :id"),
                                       {"id": ref.ref_id}).first() is None:
        raise EconomyApiError(400, "Персонаж этого счёта удалён")
    source = core.AccountRef.adjustment()
    leg = core.Leg(source, ref, delta) if delta > 0 else core.Leg(ref, source, -delta)
    try:
        result = econ_ledger.post_operation(
            db, op_type=core.OP_ADMIN_ADJUST, legs=[leg], source_service=SOURCE_SERVICE,
            region_id=_region_of(ref), actor_user_id=actor_user_id, comment=comment, apply_tax=False,
        )
    except core.InsufficientFunds:
        raise EconomyApiError(400, "Недостаточно средств на счёте")
    return {"operation_id": result.operation_id, "account_id": account_id,
            "balance": _account_balance(db, account_id)}
