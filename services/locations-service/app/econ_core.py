"""FEAT-181 world economy — the shared ledger contract (pure, framework-free).

CANONICAL COPY: services/character-service/app/econ_core.py.
Byte-identical copies live in inventory-, locations- and dungeon-service; CI
(`econ-contract-copies`) fails the pipeline when a copy differs. Edit this file
here and copy it verbatim to the other services.

This module never touches a database driver. It holds:
  * account kinds, operation types, leg types (VARCHAR values in the DB);
  * AccountRef / Leg value objects and the PostingResult returned to callers;
  * validation, tax-leg generation, netting and the fixed apply order;
  * every SQL statement the executors (`econ_ledger.py`, sync or async) run;
  * Russian plural forms and currency formatting;
  * a small TTL cache for the economy settings row.

World invariant: the sum of all balances (characters.currency_balance plus
econ_accounts.balance of every non-character account) is always 0. Money is
created only by postings out of the `emission` / `adjustment` source accounts.
"""

import time
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import Dict, Iterable, List, Mapping, NamedTuple, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Account kinds
# ---------------------------------------------------------------------------

KIND_CHARACTER = "character"
KIND_REGION_TREASURY = "region_treasury"
KIND_COUNTRY_TREASURY = "country_treasury"
KIND_WORLD_TREASURY = "world_treasury"
KIND_AUCTION_ESCROW = "auction_escrow"
KIND_AUCTION_STORAGE = "auction_storage"
KIND_EMISSION = "emission"
KIND_ADJUSTMENT = "adjustment"

ACCOUNT_KINDS = frozenset({
    KIND_CHARACTER, KIND_REGION_TREASURY, KIND_COUNTRY_TREASURY, KIND_WORLD_TREASURY,
    KIND_AUCTION_ESCROW, KIND_AUCTION_STORAGE, KIND_EMISSION, KIND_ADJUSTMENT,
})

# Kinds identified by a foreign id (ref_id > 0); every other kind is a singleton (ref_id = 0).
REF_KINDS = frozenset({KIND_CHARACTER, KIND_REGION_TREASURY, KIND_COUNTRY_TREASURY})

# Display names of singleton accounts (snapshotted into econ_accounts.name on creation).
SINGLETON_NAMES = {
    KIND_WORLD_TREASURY: "Казна Скитальцев",
    KIND_AUCTION_ESCROW: "Ставки аукциона",
    KIND_AUCTION_STORAGE: "Хранилище аукциона",
    KIND_EMISSION: "Эмиссия",
    KIND_ADJUSTMENT: "Корректировки",
}

# Accounts whose balance may go below zero (stage 1: treasuries and money sources).
NEGATIVE_ALLOWED_KINDS = frozenset({
    KIND_REGION_TREASURY, KIND_COUNTRY_TREASURY, KIND_WORLD_TREASURY, KIND_EMISSION, KIND_ADJUSTMENT,
})

# Money sources: postings out of them create money, into them destroy it.
SOURCE_KINDS = frozenset({KIND_EMISSION, KIND_ADJUSTMENT})

# Inflows into a region treasury from these kinds are taxed in favour of the country.
TAX_SOURCE_KINDS = frozenset({KIND_CHARACTER, KIND_AUCTION_ESCROW, KIND_AUCTION_STORAGE})

# ---------------------------------------------------------------------------
# Operation types
# ---------------------------------------------------------------------------

OP_GENESIS = "genesis"
OP_ADMIN_EMISSION = "admin_emission"
OP_ADMIN_ADJUST = "admin_adjust"
OP_STARTER_KIT = "starter_kit"
OP_BATTLE_REWARD = "battle_reward"
OP_BATTLE_PASS_REWARD = "battle_pass_reward"
OP_DUNGEON_REWARD = "dungeon_reward"
OP_DUNGEON_EXPENSE = "dungeon_expense"
OP_TELEPORT = "teleport"
OP_TRADE = "trade"
OP_AUCTION_BID = "auction_bid"
OP_AUCTION_REFUND = "auction_refund"
OP_AUCTION_BUYOUT = "auction_buyout"
OP_AUCTION_SETTLEMENT = "auction_settlement"
OP_AUCTION_CLAIM = "auction_claim"
OP_NPC_SHOP_BUY = "npc_shop_buy"
OP_NPC_SHOP_BUY_REFUND = "npc_shop_buy_refund"
OP_NPC_SHOP_SELL = "npc_shop_sell"
OP_QUEST_REWARD = "quest_reward"
OP_HOUSE_PURCHASE = "house_purchase"
OP_HOUSE_BUILD = "house_build"
OP_HOUSE_TAX = "house_tax"
OP_HOUSE_RESALE = "house_resale"
OP_CHARACTER_DELETED = "character_deleted"
OP_TREASURY_CLOSED = "treasury_closed"

OP_TYPES = frozenset({
    OP_GENESIS, OP_ADMIN_EMISSION, OP_ADMIN_ADJUST, OP_STARTER_KIT, OP_BATTLE_REWARD,
    OP_BATTLE_PASS_REWARD, OP_DUNGEON_REWARD, OP_DUNGEON_EXPENSE, OP_TELEPORT, OP_TRADE,
    OP_AUCTION_BID, OP_AUCTION_REFUND, OP_AUCTION_BUYOUT, OP_AUCTION_SETTLEMENT, OP_AUCTION_CLAIM,
    OP_NPC_SHOP_BUY, OP_NPC_SHOP_BUY_REFUND, OP_NPC_SHOP_SELL, OP_QUEST_REWARD,
    OP_HOUSE_PURCHASE, OP_HOUSE_BUILD, OP_HOUSE_TAX, OP_HOUSE_RESALE,
    OP_CHARACTER_DELETED, OP_TREASURY_CLOSED,
})

# Only these operations may move money out of / into the source accounts.
SOURCE_OP_TYPES = frozenset({OP_GENESIS, OP_ADMIN_EMISSION, OP_ADMIN_ADJUST})

# Operations that must carry a non-empty comment (audit trail).
COMMENT_REQUIRED_OP_TYPES = frozenset({OP_ADMIN_EMISSION, OP_ADMIN_ADJUST})

# ---------------------------------------------------------------------------
# Leg types
# ---------------------------------------------------------------------------

LEG_MAIN = "main"
LEG_REFUND = "refund"
LEG_COMMISSION = "commission"
LEG_TAX = "tax"

LEG_TYPES = frozenset({LEG_MAIN, LEG_REFUND, LEG_COMMISSION, LEG_TAX})
# Tax legs are generated by plan_operation, callers never pass them.
CALLER_LEG_TYPES = frozenset({LEG_MAIN, LEG_REFUND, LEG_COMMISSION})

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

MAX_IDEMPOTENCY_KEY_LEN = 128
MAX_COMMENT_LEN = 500
MAX_SOURCE_SERVICE_LEN = 32
MAX_AMOUNT = 10 ** 15            # far below BIGINT; guards against garbage input
LOCATION_PARENT_DEPTH = 5        # how far resolve_location walks Locations.parent_id
SETTINGS_TTL_SECONDS = 60
DEFAULT_COUNTRY_TAX_RATE = Decimal("0.1")
MAX_COUNTRY_TAX_RATE = Decimal("0.5")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class EconomyError(Exception):
    """Invalid operation or broken ledger state. Message is technical (English)."""


class InsufficientFunds(EconomyError):
    """A non-negative account would go below zero. `account` is an AccountRef, `needed` the debit."""

    def __init__(self, account: "AccountRef", needed: int):
        self.account = account
        self.needed = needed
        super().__init__(f"insufficient funds on {account.kind}:{account.ref_id} (needed {needed})")


class DuplicateOperation(EconomyError):
    """An operation with the same idempotency key already exists; nothing was moved."""

    def __init__(self, operation_id: int):
        self.operation_id = operation_id
        super().__init__(f"duplicate operation (existing id {operation_id})")


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AccountRef:
    """A ledger account named by (kind, ref_id). Callers never use raw account ids."""

    kind: str
    ref_id: int = 0

    @classmethod
    def character(cls, character_id: int) -> "AccountRef":
        return cls(KIND_CHARACTER, int(character_id))

    @classmethod
    def region(cls, region_id: int) -> "AccountRef":
        return cls(KIND_REGION_TREASURY, int(region_id))

    @classmethod
    def country(cls, country_id: int) -> "AccountRef":
        return cls(KIND_COUNTRY_TREASURY, int(country_id))

    @classmethod
    def world(cls) -> "AccountRef":
        return cls(KIND_WORLD_TREASURY, 0)

    @classmethod
    def escrow(cls) -> "AccountRef":
        return cls(KIND_AUCTION_ESCROW, 0)

    @classmethod
    def storage(cls) -> "AccountRef":
        return cls(KIND_AUCTION_STORAGE, 0)

    @classmethod
    def emission(cls) -> "AccountRef":
        return cls(KIND_EMISSION, 0)

    @classmethod
    def adjustment(cls) -> "AccountRef":
        return cls(KIND_ADJUSTMENT, 0)

    @property
    def is_character(self) -> bool:
        return self.kind == KIND_CHARACTER

    @property
    def allow_negative(self) -> bool:
        return self.kind in NEGATIVE_ALLOWED_KINDS

    def sort_key(self) -> Tuple[str, int]:
        return (self.kind, self.ref_id)


@dataclass(frozen=True)
class Leg:
    """One transfer `src -> dst`. Amount is a positive int; 0 legs are dropped."""

    src: AccountRef
    dst: AccountRef
    amount: int
    leg_type: str = LEG_MAIN


class PostingResult(NamedTuple):
    """operation_id is None when every leg was 0 (nothing posted). balances: {character_id: new balance}."""

    operation_id: Optional[int]
    balances: Dict[int, int]


@dataclass(frozen=True)
class CurrencyForms:
    name: str          # nominative, labels: «Золото»
    genitive: str      # «Недостаточно золота»
    one: str           # 1, 21, 101: «золотой»
    few: str           # 2-4, 22-24: «золотых»
    many: str          # 0, 5-20, 25: «золотых»
    short: str         # «зол.»

    def as_dict(self) -> Dict[str, str]:
        return {
            "name": self.name, "genitive": self.genitive, "one": self.one,
            "few": self.few, "many": self.many, "short": self.short,
        }


DEFAULT_FORMS = CurrencyForms(
    name="Золото", genitive="золота", one="золотой", few="золотых", many="золотых", short="зол.",
)


@dataclass(frozen=True)
class EconomySettings:
    forms: CurrencyForms
    country_tax_rate: Decimal


DEFAULT_SETTINGS = EconomySettings(forms=DEFAULT_FORMS, country_tax_rate=DEFAULT_COUNTRY_TAX_RATE)


@dataclass(frozen=True)
class OperationPlan:
    """Result of plan_operation: final legs (incl. tax) and the net delta per account."""

    op_type: str
    legs: Tuple[Leg, ...]
    deltas: Dict[AccountRef, int]

    @property
    def accounts(self) -> List[AccountRef]:
        seen = {}
        for leg in self.legs:
            seen.setdefault(leg.src, None)
            seen.setdefault(leg.dst, None)
        return sorted(seen, key=AccountRef.sort_key)

    @property
    def character_ids(self) -> List[int]:
        return sorted({a.ref_id for a in self.accounts if a.is_character})


class ApplyStep(NamedTuple):
    """One balance UPDATE. target 'character' -> characters.id, 'account' -> econ_accounts.id."""

    target: str
    row_id: int
    delta: int
    account: AccountRef


# ---------------------------------------------------------------------------
# Plural forms / formatting
# ---------------------------------------------------------------------------

def plural_ru(n: int, one: str, few: str, many: str) -> str:
    """Russian counting form for n: 1/21/101 -> one, 2-4/22-24 -> few, 0/5-20/25 -> many."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def format_currency(n: int, forms: CurrencyForms = DEFAULT_FORMS, short: bool = False) -> str:
    """«1 золотой», «3 золотых», short=True -> «3 зол.»."""
    n = int(n)
    word = forms.short if short else plural_ru(n, forms.one, forms.few, forms.many)
    return f"{n} {word}"


# ---------------------------------------------------------------------------
# Validation / planning
# ---------------------------------------------------------------------------

def validate_account(ref: AccountRef) -> None:
    if not isinstance(ref, AccountRef):
        raise EconomyError(f"account must be AccountRef, got {type(ref).__name__}")
    if ref.kind not in ACCOUNT_KINDS:
        raise EconomyError(f"unknown account kind {ref.kind!r}")
    if not isinstance(ref.ref_id, int) or isinstance(ref.ref_id, bool):
        raise EconomyError("account ref_id must be int")
    if ref.kind in REF_KINDS:
        if ref.ref_id <= 0:
            raise EconomyError(f"{ref.kind} account needs a positive ref_id")
    elif ref.ref_id != 0:
        raise EconomyError(f"{ref.kind} is a singleton account (ref_id must be 0)")


def validate_operation(
    op_type: str,
    legs: Iterable[Leg],
    *,
    source_service: str,
    comment: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> List[Leg]:
    """Check the request and return the legs with amount 0 dropped. Raises EconomyError."""
    if op_type not in OP_TYPES:
        raise EconomyError(f"unknown op_type {op_type!r}")
    if not source_service or not isinstance(source_service, str) or len(source_service) > MAX_SOURCE_SERVICE_LEN:
        raise EconomyError("source_service must be a non-empty string of at most 32 chars")
    if comment is not None and len(comment) > MAX_COMMENT_LEN:
        raise EconomyError("comment is longer than 500 chars")
    if op_type in COMMENT_REQUIRED_OP_TYPES and not (comment and comment.strip()):
        raise EconomyError(f"{op_type} requires a comment")
    if idempotency_key is not None:
        if not isinstance(idempotency_key, str) or not idempotency_key or len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LEN:
            raise EconomyError("idempotency_key must be a non-empty string of at most 128 chars")

    kept: List[Leg] = []
    for leg in legs:
        if not isinstance(leg, Leg):
            raise EconomyError(f"leg must be Leg, got {type(leg).__name__}")
        validate_account(leg.src)
        validate_account(leg.dst)
        if not isinstance(leg.amount, int) or isinstance(leg.amount, bool):
            raise EconomyError("leg amount must be int")
        if leg.amount < 0:
            raise EconomyError("leg amount must not be negative")
        if leg.amount > MAX_AMOUNT:
            raise EconomyError("leg amount is too large")
        if leg.leg_type not in CALLER_LEG_TYPES:
            raise EconomyError(f"leg_type {leg.leg_type!r} cannot be passed by a caller")
        if leg.src == leg.dst:
            raise EconomyError("leg src and dst must differ")
        if (leg.src.kind in SOURCE_KINDS or leg.dst.kind in SOURCE_KINDS) and op_type not in SOURCE_OP_TYPES:
            raise EconomyError(f"{op_type} may not touch emission/adjustment accounts")
        if leg.amount == 0:
            continue
        kept.append(leg)
    return kept


def tax_region_ids(legs: Iterable[Leg], apply_tax: bool = True) -> List[int]:
    """Regions whose country is needed to generate tax legs."""
    if not apply_tax:
        return []
    return sorted({
        leg.dst.ref_id for leg in legs
        if leg.dst.kind == KIND_REGION_TREASURY and leg.src.kind in TAX_SOURCE_KINDS
    })


def tax_amount(amount: int, rate) -> int:
    """floor(amount * rate); rate given as Decimal / str / float in [0, 0.5]."""
    rate = Decimal(str(rate))
    if rate <= 0:
        return 0
    return int((Decimal(int(amount)) * rate).to_integral_value(rounding=ROUND_FLOOR))


def add_tax_legs(legs: Sequence[Leg], tax_rate, region_countries: Mapping[int, Optional[int]]) -> List[Leg]:
    """Append a `region -> country` tax leg after every taxable inflow into a region treasury.

    Regions without a known country (deleted region, missing row) are not taxed.
    """
    result: List[Leg] = []
    for leg in legs:
        result.append(leg)
        if leg.dst.kind != KIND_REGION_TREASURY or leg.src.kind not in TAX_SOURCE_KINDS:
            continue
        country_id = region_countries.get(leg.dst.ref_id)
        if not country_id:
            continue
        tax = tax_amount(leg.amount, tax_rate)
        if tax > 0:
            result.append(Leg(leg.dst, AccountRef.country(country_id), tax, LEG_TAX))
    return result


def net_deltas(legs: Iterable[Leg]) -> Dict[AccountRef, int]:
    deltas: Dict[AccountRef, int] = {}
    for leg in legs:
        deltas[leg.src] = deltas.get(leg.src, 0) - leg.amount
        deltas[leg.dst] = deltas.get(leg.dst, 0) + leg.amount
    return deltas


def plan_operation(
    op_type: str,
    legs: Iterable[Leg],
    *,
    source_service: str,
    comment: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    apply_tax: bool = True,
    tax_rate=DEFAULT_COUNTRY_TAX_RATE,
    region_countries: Optional[Mapping[int, Optional[int]]] = None,
) -> Optional[OperationPlan]:
    """Validate, add tax legs, net. Returns None when nothing is left to post (all legs 0)."""
    kept = validate_operation(
        op_type, legs, source_service=source_service, comment=comment, idempotency_key=idempotency_key,
    )
    if not kept:
        return None
    if apply_tax:
        kept = add_tax_legs(kept, tax_rate, region_countries or {})
    return OperationPlan(op_type=op_type, legs=tuple(kept), deltas=net_deltas(kept))


def apply_steps(plan: OperationPlan, account_ids: Mapping[AccountRef, int]) -> List[ApplyStep]:
    """Fixed lock order (3.5): characters by ascending id, then econ_accounts by ascending id.

    Accounts whose net delta is 0 are not touched.
    """
    chars: List[ApplyStep] = []
    others: List[ApplyStep] = []
    for ref, delta in plan.deltas.items():
        if delta == 0:
            continue
        if ref.is_character:
            chars.append(ApplyStep("character", ref.ref_id, delta, ref))
        else:
            others.append(ApplyStep("account", int(account_ids[ref]), delta, ref))
    chars.sort(key=lambda s: s.row_id)
    others.sort(key=lambda s: s.row_id)
    return chars + others


# ---------------------------------------------------------------------------
# SQL (portable between MySQL 8 and SQLite; `FOR UPDATE` only where supported)
# ---------------------------------------------------------------------------

def in_params(prefix: str, values: Sequence) -> Tuple[str, Dict[str, object]]:
    """Build ':p0, :p1, ...' and the matching params for an IN (...) clause."""
    names = [f"{prefix}{i}" for i in range(len(values))]
    return ", ".join(f":{n}" for n in names), dict(zip(names, values))


def supports_for_update(dialect_name: str) -> bool:
    return dialect_name != "sqlite"


def sql_lock_characters(placeholders: str, for_update: bool) -> str:
    return (
        f"SELECT id, currency_balance FROM characters WHERE id IN ({placeholders}) ORDER BY id"
        + (" FOR UPDATE" if for_update else "")
    )


SQL_SELECT_OPERATION_BY_KEY = "SELECT id FROM econ_operations WHERE idempotency_key = :key"

SQL_INSERT_OPERATION = (
    "INSERT INTO econ_operations (op_type, idempotency_key, location_id, region_id, actor_user_id, "
    "source_service, comment, metadata) VALUES (:op_type, :idempotency_key, :location_id, :region_id, "
    ":actor_user_id, :source_service, :comment, :metadata)"
)

SQL_SELECT_ACCOUNT = "SELECT id FROM econ_accounts WHERE kind = :kind AND ref_id = :ref_id"

SQL_INSERT_ACCOUNT = (
    "INSERT INTO econ_accounts (kind, ref_id, name, balance, allow_negative, is_active) "
    "VALUES (:kind, :ref_id, :name, 0, :allow_negative, 1)"
)

SQL_DEACTIVATE_ACCOUNT = "UPDATE econ_accounts SET is_active = 0 WHERE kind = :kind AND ref_id = :ref_id"

# Name snapshot for a lazily created account, by kind (singletons use SINGLETON_NAMES).
SQL_ACCOUNT_NAME = {
    KIND_CHARACTER: "SELECT name FROM characters WHERE id = :ref_id",
    KIND_REGION_TREASURY: "SELECT name FROM Regions WHERE id = :ref_id",
    KIND_COUNTRY_TREASURY: "SELECT name FROM Countries WHERE id = :ref_id",
}

SQL_DEBIT_CHARACTER = (
    "UPDATE characters SET currency_balance = currency_balance - :amount "
    "WHERE id = :id AND currency_balance >= :amount"
)
SQL_CREDIT_CHARACTER = "UPDATE characters SET currency_balance = currency_balance + :amount WHERE id = :id"
SQL_APPLY_ACCOUNT = (
    "UPDATE econ_accounts SET balance = balance + :delta "
    "WHERE id = :id AND (allow_negative = 1 OR balance + :delta >= 0)"
)

SQL_INSERT_POSTING = (
    "INSERT INTO econ_postings (operation_id, from_account_id, to_account_id, amount, leg_type) "
    "VALUES (:operation_id, :from_account_id, :to_account_id, :amount, :leg_type)"
)


def sql_character_balances(placeholders: str) -> str:
    return f"SELECT id, currency_balance FROM characters WHERE id IN ({placeholders})"


def sql_region_countries(placeholders: str) -> str:
    return f"SELECT id, country_id FROM Regions WHERE id IN ({placeholders})"


# Location -> (region_id, country_id): COALESCE(Districts.region_id, Locations.region_id) of the
# location itself, else of the nearest ancestor via Locations.parent_id (up to LOCATION_PARENT_DEPTH).
SQL_RESOLVE_LOCATION = f"""
WITH RECURSIVE chain (id, parent_id, district_id, region_id, depth) AS (
    SELECT id, parent_id, district_id, region_id, 0 FROM Locations WHERE id = :location_id
    UNION ALL
    SELECT l.id, l.parent_id, l.district_id, l.region_id, c.depth + 1
    FROM Locations l JOIN chain c ON l.id = c.parent_id
    WHERE c.depth < {LOCATION_PARENT_DEPTH}
)
SELECT r.id AS region_id, r.country_id AS country_id
FROM chain c
LEFT JOIN Districts d ON d.id = c.district_id
JOIN Regions r ON r.id = COALESCE(d.region_id, c.region_id)
ORDER BY c.depth
LIMIT 1
"""

SQL_SELECT_SETTINGS = (
    "SELECT currency_name, currency_genitive, currency_one, currency_few, currency_many, currency_short, "
    "country_tax_rate FROM econ_settings WHERE id = 1"
)


def settings_from_row(row) -> EconomySettings:
    """Build EconomySettings from a SQL_SELECT_SETTINGS row (None -> defaults)."""
    if row is None:
        return DEFAULT_SETTINGS
    forms = CurrencyForms(
        name=row[0] or DEFAULT_FORMS.name,
        genitive=row[1] or DEFAULT_FORMS.genitive,
        one=row[2] or DEFAULT_FORMS.one,
        few=row[3] or DEFAULT_FORMS.few,
        many=row[4] or DEFAULT_FORMS.many,
        short=row[5] or DEFAULT_FORMS.short,
    )
    rate = DEFAULT_COUNTRY_TAX_RATE if row[6] is None else Decimal(str(row[6]))
    rate = min(max(rate, Decimal(0)), MAX_COUNTRY_TAX_RATE)
    return EconomySettings(forms=forms, country_tax_rate=rate)


# ---------------------------------------------------------------------------
# Settings cache (per process, TTL)
# ---------------------------------------------------------------------------

_settings_cache: Dict[str, object] = {"value": None, "expires": 0.0}


def cached_settings(now: Optional[float] = None) -> Optional[EconomySettings]:
    now = time.monotonic() if now is None else now
    if _settings_cache["value"] is not None and now < _settings_cache["expires"]:
        return _settings_cache["value"]  # type: ignore[return-value]
    return None


def store_settings(value: EconomySettings, now: Optional[float] = None) -> EconomySettings:
    now = time.monotonic() if now is None else now
    _settings_cache["value"] = value
    _settings_cache["expires"] = now + SETTINGS_TTL_SECONDS
    return value


def invalidate_settings_cache() -> None:
    _settings_cache["value"] = None
    _settings_cache["expires"] = 0.0
