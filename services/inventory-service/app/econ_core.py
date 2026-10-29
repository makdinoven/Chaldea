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
  * FEAT-183 NPC merchants: the "living merchant" predicate, item -> effective group and the
    pure price functions (ask / bid / wholesale / charisma / units / trade tax) with the SQL
    both locations-service (player shop) and character-service (6 h tick) read them with;
  * FEAT-184 banks: the bank's own money (`bank`) and the vault of player deposits
    (`bank_deposits`), both per region and never negative, the bank op types and the
    `interest` leg; the bank maths itself lives in character-service (`econ_bank.py`);
  * a small TTL cache for the economy settings row.

World invariant: the sum of all balances (characters.currency_balance plus
econ_accounts.balance of every non-character account) is always 0. Money is
created only by postings out of the `emission` / `adjustment` source accounts.
"""

import json
import time
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Mapping, NamedTuple, Optional, Sequence, Tuple

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
# FEAT-182: the money of a region's inhabitants (ref_id = Regions.id). Never negative.
KIND_POPULATION_PURSE = "population_purse"
# FEAT-184 (ref_id = Regions.id, never negative): the bank's own money (capital, residents' deposits,
# loan repayments and interest; loans and all interest are paid only from here) and the vault of player
# deposits (always equals the sum of the open deposit rows of that bank; never lent).
KIND_BANK = "bank"
KIND_BANK_DEPOSITS = "bank_deposits"

ACCOUNT_KINDS = frozenset({
    KIND_CHARACTER, KIND_REGION_TREASURY, KIND_COUNTRY_TREASURY, KIND_WORLD_TREASURY,
    KIND_AUCTION_ESCROW, KIND_AUCTION_STORAGE, KIND_EMISSION, KIND_ADJUSTMENT,
    KIND_POPULATION_PURSE, KIND_BANK, KIND_BANK_DEPOSITS,
})

# Kinds identified by a foreign id (ref_id > 0); every other kind is a singleton (ref_id = 0).
REF_KINDS = frozenset({
    KIND_CHARACTER, KIND_REGION_TREASURY, KIND_COUNTRY_TREASURY, KIND_POPULATION_PURSE,
    KIND_BANK, KIND_BANK_DEPOSITS,
})

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
# FEAT-184: player deposit money (`bank_deposits`) is taxed like wallet money (transfer commission,
# deletion payout); the bank's own money (`bank`) is not a tax source (capital return is not income).
TAX_SOURCE_KINDS = frozenset({
    KIND_CHARACTER, KIND_AUCTION_ESCROW, KIND_AUCTION_STORAGE, KIND_POPULATION_PURSE, KIND_BANK_DEPOSITS,
})

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
OP_REGION_TICK = "region_tick"            # FEAT-182: purse <-> region <-> country flows of one simulation step
# FEAT-183: a merchant's 6 h trade with the residents of his region (purse <-> NPC, NPC -> region trade_tax)
OP_MERCHANT_TRADE = "merchant_trade"
# FEAT-184 banks
OP_BANK_DEPOSIT = "bank_deposit"          # character -> vault
OP_BANK_WITHDRAW = "bank_withdraw"        # vault -> character (+ forfeited interest vault -> bank)
OP_BANK_TRANSFER = "bank_transfer"        # vault/character -> vault (+ commission -> region treasury)
OP_BANK_TICK = "bank_tick"                # 6 h bank pass: interest, residents' deposits / loans
OP_BANK_CAPITAL = "bank_capital"          # region treasury <-> bank
OP_LOAN_ISSUE = "loan_issue"              # bank -> character
OP_LOAN_REPAY = "loan_repay"              # character -> bank
OP_LOAN_COLLECT = "loan_collect"          # vault / character -> bank (overdue debt collection)

BANK_OP_TYPES = frozenset({
    OP_BANK_DEPOSIT, OP_BANK_WITHDRAW, OP_BANK_TRANSFER, OP_BANK_TICK, OP_BANK_CAPITAL,
    OP_LOAN_ISSUE, OP_LOAN_REPAY, OP_LOAN_COLLECT,
})

OP_TYPES = frozenset({
    OP_GENESIS, OP_ADMIN_EMISSION, OP_ADMIN_ADJUST, OP_STARTER_KIT, OP_BATTLE_REWARD,
    OP_BATTLE_PASS_REWARD, OP_DUNGEON_REWARD, OP_DUNGEON_EXPENSE, OP_TELEPORT, OP_TRADE,
    OP_AUCTION_BID, OP_AUCTION_REFUND, OP_AUCTION_BUYOUT, OP_AUCTION_SETTLEMENT, OP_AUCTION_CLAIM,
    OP_NPC_SHOP_BUY, OP_NPC_SHOP_BUY_REFUND, OP_NPC_SHOP_SELL, OP_QUEST_REWARD,
    OP_HOUSE_PURCHASE, OP_HOUSE_BUILD, OP_HOUSE_TAX, OP_HOUSE_RESALE,
    OP_CHARACTER_DELETED, OP_TREASURY_CLOSED, OP_REGION_TICK, OP_MERCHANT_TRADE,
}) | BANK_OP_TYPES

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
# FEAT-183: a merchant's sales tax `NPC -> region treasury`. Passed by callers (unlike the generated
# `tax` leg); being a character -> region inflow it is itself taxed 10 % to the country.
LEG_TRADE_TAX = "trade_tax"
# FEAT-184: deposit / loan interest (bank -> vault / purse, purse -> bank, forfeited vault -> bank).
LEG_INTEREST = "interest"

LEG_TYPES = frozenset({LEG_MAIN, LEG_REFUND, LEG_COMMISSION, LEG_TAX, LEG_TRADE_TAX, LEG_INTEREST})
# Tax legs are generated by plan_operation, callers never pass them.
CALLER_LEG_TYPES = frozenset({LEG_MAIN, LEG_REFUND, LEG_COMMISSION, LEG_TRADE_TAX, LEG_INTEREST})

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
    def purse(cls, region_id: int) -> "AccountRef":
        return cls(KIND_POPULATION_PURSE, int(region_id))

    @classmethod
    def bank(cls, region_id: int) -> "AccountRef":
        return cls(KIND_BANK, int(region_id))

    @classmethod
    def bank_deposits(cls, region_id: int) -> "AccountRef":
        return cls(KIND_BANK_DEPOSITS, int(region_id))

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
    name: str          # nominative, labels: «Марки»
    genitive: str      # «Недостаточно марок»
    one: str           # 1, 21, 101: «марка»
    few: str           # 2-4, 22-24: «марки»
    many: str          # 0, 5-20, 25: «марок»
    short: str         # «ṃ»

    def as_dict(self) -> Dict[str, str]:
        return {
            "name": self.name, "genitive": self.genitive, "one": self.one,
            "few": self.few, "many": self.many, "short": self.short,
        }


DEFAULT_FORMS = CurrencyForms(
    name="Марки", genitive="марок", one="марка", few="марки", many="марок", short="ṃ",
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
# Goods groups (FEAT-182) and the item -> group auto rule
# ---------------------------------------------------------------------------

GOODS_GROUPS: Tuple[str, ...] = (
    "food", "ore_metal", "wood", "herbs", "hides_textiles", "magic",
    "weapons", "armor", "jewelry", "potions", "tools", "household",
)

# Items that never trade on the regional market (their group, if any, is still reported).
OFF_MARKET_ITEM_TYPES = frozenset({"scroll", "recipe"})
OFF_MARKET_RARITIES = frozenset({"legendary", "mythical", "divine", "demonic"})

_RESOURCE_SUBCATEGORY_GROUPS = {
    "ore": "ore_metal", "ingot": "ore_metal",
    "wood": "wood",
    "herb": "herbs", "reagent": "herbs",
    "ingredient": "food",
    "trophy": "hides_textiles",
    "magic_dust": "magic", "essence": "magic", "material": "magic",
    "whetstone": "tools", "repair_kit": "tools",
}

_ITEM_TYPE_GROUPS = {
    "weapon": "weapons",
    "head": "armor", "body": "armor", "cloak": "armor", "belt": "armor",
    "ring": "jewelry", "necklace": "jewelry", "bracelet": "jewelry", "gem": "jewelry",
    "rune": "magic",
    "gathering_tool": "tools",
    "furniture": "household",
}


def auto_item_group(
    item_type: Optional[str],
    resource_subcategory: Optional[str],
    is_food,
    item_rarity: Optional[str],
) -> Tuple[Optional[str], bool]:
    """Default goods group of an item and whether it is off-market (admin overrides win over this).

    consumable -> food / potions by is_food; resource -> by subcategory (NULL -> food when is_food,
    else no group); equipment and other types by item_type; scroll / recipe / misc -> no group.
    Off-market: scroll, recipe and legendary-or-higher rarity.
    """
    food = bool(is_food)
    if item_type == "consumable":
        group: Optional[str] = "food" if food else "potions"
    elif item_type == "resource":
        if resource_subcategory:
            group = _RESOURCE_SUBCATEGORY_GROUPS.get(resource_subcategory)
        else:
            group = "food" if food else None
    else:
        group = _ITEM_TYPE_GROUPS.get(item_type) if item_type else None
    off_market = item_type in OFF_MARKET_ITEM_TYPES or item_rarity in OFF_MARKET_RARITIES
    return group, off_market


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
    """«1 марка», «3 марки», short=True -> «3 ṃ»."""
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
    KIND_POPULATION_PURSE: "SELECT name FROM Regions WHERE id = :ref_id",
    KIND_BANK: "SELECT name FROM Regions WHERE id = :ref_id",
    KIND_BANK_DEPOSITS: "SELECT name FROM Regions WHERE id = :ref_id",
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
# NPC merchants (FEAT-183): living-merchant predicate, effective item group, prices
#
# The only way locations-service (player shop) and character-service (6 h tick, merchants
# admin) compute a merchant price. Money is int; maths in Decimal with fixed rounding
# (ceil for what a player pays, floor for what a player / merchant receives).
# ---------------------------------------------------------------------------

MAX_CHARISMA_DISCOUNT = Decimal("0.5")          # 50 % at 250 charisma
CHARISMA_DISCOUNT_PER_POINT = Decimal("0.2")    # percent per charisma point
DEFAULT_MERCHANT_BID_SHARE = Decimal("0.5")     # buy-back share of item_base outside the assortment
DEFAULT_RESTOCK_TARGET = 10                     # «норма склада» of a new / migrated shop row
MAX_TRADE_TAX_RATE = Decimal("1")

# Shop price badge thresholds (same as the region card): mult <= LOW -> low, mult >= HIGH -> high.
PRICE_LEVEL_LOW_MULT = Decimal("0.85")
PRICE_LEVEL_HIGH_MULT = Decimal("1.2")
PRICE_LEVEL_LOW = "low"
PRICE_LEVEL_NORMAL = "normal"
PRICE_LEVEL_HIGH = "high"

# npc_shop_items.origin
SHOP_ORIGIN_ADMIN = "admin"      # assortment set by an admin, restocked from the region
SHOP_ORIGIN_PLAYER = "player"    # bought from players, resold only (restock_target 0)

# Why a merchant is "legacy" (fixed prices, treasury pays / receives, no restock, no resident trade).
MERCHANT_REASON_NOT_NPC = "not_npc"              # no such character, or not an NPC
MERCHANT_REASON_DEAD = "dead"
MERCHANT_REASON_NO_LOCATION = "no_location"
MERCHANT_REASON_DUNGEON = "dungeon"
MERCHANT_REASON_NO_REGION = "no_region"
MERCHANT_REASON_NOT_SIMULATED = "not_simulated"
MERCHANT_LEGACY_REASONS = frozenset({
    MERCHANT_REASON_NO_LOCATION, MERCHANT_REASON_NO_REGION, MERCHANT_REASON_DUNGEON,
    MERCHANT_REASON_NOT_SIMULATED, MERCHANT_REASON_DEAD, MERCHANT_REASON_NOT_NPC,
})

_ONE = Decimal(1)
_HUNDRED = Decimal(100)


def _dec(value) -> Decimal:
    """Decimal from int / float / str / Decimal via str (0.1 -> Decimal('0.1'), not its binary value)."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal(0)
    return Decimal(str(value))


def _floor(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def _ceil(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def effective_item_group(
    item_type: Optional[str],
    resource_subcategory: Optional[str],
    is_food,
    item_rarity: Optional[str],
    override_group: Optional[str] = None,
    override_off_market=None,
) -> Tuple[Optional[str], bool]:
    """The goods group an item trades in and whether it is off-market (econ_item_groups over the auto rule).

    A non-NULL override wins field by field; an item without a group is always off-market (it has no
    region price), even when an override says off_market = 0.
    """
    auto_group, auto_off = auto_item_group(item_type, resource_subcategory, is_food, item_rarity)
    group = override_group if override_group is not None else auto_group
    off_market = bool(override_off_market) if override_off_market is not None else bool(auto_off)
    if group is None:
        off_market = True
    return group, off_market


def item_base_price(items_price, group_base_price) -> int:
    """FEAT-182 3.6 item_base: items.price when > 0, else the group's base price, else 0."""
    price = int(items_price or 0)
    if price > 0:
        return price
    base = int(group_base_price or 0)
    return base if base > 0 else 0


def market_mult(living: bool, group: Optional[str], off_market: bool, mults: Mapping[str, Any]) -> Decimal:
    """Region multiplier of an item at a merchant: the group's price_mult for a living merchant and an
    on-market item with a known group; 1 otherwise (legacy, off-market, no group, group not in the region)."""
    if not living or off_market or group is None:
        return _ONE
    mult = mults.get(group)
    if mult is None:
        return _ONE
    mult = _dec(mult)
    return mult if mult > 0 else _ONE


def price_level(mult) -> str:
    """Badge of a shop row: low (<= 0.85), high (>= 1.2), else normal."""
    mult = _dec(mult)
    if mult <= PRICE_LEVEL_LOW_MULT:
        return PRICE_LEVEL_LOW
    if mult >= PRICE_LEVEL_HIGH_MULT:
        return PRICE_LEVEL_HIGH
    return PRICE_LEVEL_NORMAL


def market_ask(base_ask, mult) -> int:
    """Merchant's selling price: max(1, ceil(base_ask * mult))."""
    return max(1, _ceil(_dec(base_ask) * _dec(mult)))


def market_bid(base_bid, mult, ask) -> int:
    """Merchant's buying price: min(floor(base_bid * mult), floor(ask * (1 - MAX_CHARISMA_DISCOUNT))).

    The cap keeps the bid at or below the cheapest possible ask at the same merchant (max charisma),
    so buying and selling back is never profitable. 0 = «does not buy» (base_bid <= 0 or result < 1).
    """
    base_bid = _dec(base_bid)
    if base_bid <= 0:
        return 0
    bid = min(_floor(base_bid * _dec(mult)), _floor(_dec(ask) * (_ONE - MAX_CHARISMA_DISCOUNT)))
    return bid if bid >= 1 else 0


def wholesale_price(base_ask, mult, share) -> int:
    """Restock price the merchant pays the region per item: max(1, floor(base_ask * mult * share))."""
    return max(1, _floor(_dec(base_ask) * _dec(mult) * _dec(share)))


def charisma_discount_pct(charisma) -> Decimal:
    """Buy discount in percent: min(charisma * 0.2, 50); 0 for None / non-positive / garbage charisma."""
    if charisma is None or isinstance(charisma, bool):
        return Decimal(0)
    try:
        value = _dec(charisma)
    except (InvalidOperation, ValueError):
        return Decimal(0)
    if not value.is_finite() or value <= 0:
        return Decimal(0)
    return min(value * CHARISMA_DISCOUNT_PER_POINT, MAX_CHARISMA_DISCOUNT * _HUNDRED)


def discounted_ask(ask, discount_pct) -> int:
    """What the player pays per item: ceil(ask * (1 - discount_pct / 100)), discount clamped to 0..50 %."""
    pct = min(max(_dec(discount_pct), Decimal(0)), MAX_CHARISMA_DISCOUNT * _HUNDRED)
    ask = int(ask)
    if pct == 0:
        return ask
    return max(1, _ceil(_dec(ask) * (_ONE - pct / _HUNDRED)))


def units_per_item(base, group_base) -> float:
    """Abstract region units one concrete item is worth: base / group_base (value-based, 3.1 #3).

    0.0 when the group base is unknown / not positive: such a row cannot trade with the region.
    """
    group_base = _dec(group_base)
    if group_base <= 0:
        return 0.0
    return float(_dec(base) / group_base)


def trade_tax(amount, tax_rate) -> int:
    """Merchant sales tax into the region treasury: floor(amount * tax_rate), rate clamped to 0..1."""
    rate = min(max(_dec(tax_rate), Decimal(0)), MAX_TRADE_TAX_RATE)
    amount = int(amount)
    if amount <= 0 or rate <= 0:
        return 0
    return _floor(_dec(amount) * rate)


def merchant_status(npc_row, region_row) -> Tuple[bool, Optional[str]]:
    """Is the merchant "living" (trades in the regional economy)? -> (living, legacy reason or None).

    npc_row: a SQL_NPC_PLACE row `(id, is_npc, npc_status, current_location_id, marker_type)` or None.
    region_row: a SQL_REGION_ECON row `(region_id, template_code, population, tax_rate)` of the region the
    NPC's location resolves to (SQL_RESOLVE_LOCATION), or None when it resolves to no region.
    Checked in order: not_npc, dead, no_location, dungeon, no_region, not_simulated.
    """
    if npc_row is None or not npc_row[1]:
        return False, MERCHANT_REASON_NOT_NPC
    if npc_row[2] == "dead":
        return False, MERCHANT_REASON_DEAD
    if not npc_row[3]:
        return False, MERCHANT_REASON_NO_LOCATION
    if npc_row[4] == "dungeon":
        return False, MERCHANT_REASON_DUNGEON
    if region_row is None:
        return False, MERCHANT_REASON_NO_REGION
    if region_row[1] is None or int(region_row[2] or 0) <= 0:
        return False, MERCHANT_REASON_NOT_SIMULATED
    return True, None


def sim_params_dict(raw) -> Dict[str, Any]:
    """econ_sim_settings.params (JSON as str / bytes / dict / None) -> dict; garbage -> {}."""
    if raw is None:
        return {}
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return dict(raw) if isinstance(raw, Mapping) else {}


def merchant_bid_share(raw_params) -> Decimal:
    """`merchant_bid_share` from econ_sim_settings.params; DEFAULT_MERCHANT_BID_SHARE when missing / invalid;
    clamped to 0..1."""
    value = sim_params_dict(raw_params).get("merchant_bid_share")
    if value is None or isinstance(value, bool):
        return DEFAULT_MERCHANT_BID_SHARE
    try:
        share = _dec(value)
    except (InvalidOperation, ValueError):
        return DEFAULT_MERCHANT_BID_SHARE
    if not share.is_finite():
        return DEFAULT_MERCHANT_BID_SHARE
    return min(max(share, Decimal(0)), _ONE)


def default_bid(item_base, bid_share) -> int:
    """Base bid for a same-group item outside the assortment: floor(item_base * bid_share)."""
    return max(0, _floor(_dec(item_base) * _dec(bid_share)))


class ItemMarket(NamedTuple):
    """One sql_item_market row resolved to its effective group."""

    item_id: int
    name: Optional[str]
    image: Optional[str]
    price: int                 # items.price (0 when NULL)
    group: Optional[str]
    off_market: bool


def item_market_from_row(row) -> ItemMarket:
    """sql_item_market row -> ItemMarket (column order is fixed by sql_item_market)."""
    group, off_market = effective_item_group(row[1], row[2], row[3], row[4], row[8], row[9])
    return ItemMarket(int(row[0]), row[6], row[7], int(row[5] or 0), group, off_market)


def region_goods_from_rows(rows) -> Tuple[Dict[str, Decimal], Dict[str, int]]:
    """SQL_REGION_MARKET rows -> ({group: price_mult}, {group: base_price}). A group the region has no
    goods row for gets mult 1."""
    mults: Dict[str, Decimal] = {}
    bases: Dict[str, int] = {}
    for code, base_price, mult in rows:
        bases[code] = int(base_price or 0)
        mults[code] = _ONE if mult is None else _dec(mult)
    return mults, bases


# NPC + the marker of his location (merchant_status input).
SQL_NPC_PLACE = (
    "SELECT c.id, c.is_npc, c.npc_status, c.current_location_id, l.marker_type "
    "FROM characters c LEFT JOIN Locations l ON l.id = c.current_location_id WHERE c.id = :id"
)

# Region economy header (merchant_status input); template_code NULL = no econ_regions row or no template.
SQL_REGION_ECON = (
    "SELECT r.id, e.template_code, e.population, e.tax_rate "
    "FROM Regions r LEFT JOIN econ_regions e ON e.region_id = r.id WHERE r.id = :region_id"
)

# Every goods group with its base price and this region's price_mult (NULL when the region has no row).
SQL_REGION_MARKET = (
    "SELECT g.code, g.base_price, rg.price_mult FROM econ_goods_groups g "
    "LEFT JOIN econ_region_goods rg ON rg.group_code = g.code AND rg.region_id = :region_id "
    "ORDER BY g.code"
)

SQL_SIM_PARAMS = "SELECT params FROM econ_sim_settings WHERE id = 1"


def sql_item_market(placeholders: str) -> str:
    """Items with their override (item_market_from_row reads this column order)."""
    return (
        "SELECT i.id, i.item_type, i.resource_subcategory, i.is_food, i.item_rarity, i.price, i.name, i.image, "
        "o.group_code, o.off_market FROM items i LEFT JOIN econ_item_groups o ON o.item_id = i.id "
        f"WHERE i.id IN ({placeholders}) ORDER BY i.id"
    )


SHOP_ROW_COLUMNS = "id, npc_id, item_id, buy_price, sell_price, stock, restock_target, origin, is_active"


def sql_lock_shop_rows(placeholders: str, for_update: bool, by: str = "npc_id") -> str:
    """Shop rows of the given NPCs (by='npc_id') or row ids (by='id'), ascending id (lock order 3.5).
    Columns: SHOP_ROW_COLUMNS."""
    if by not in ("npc_id", "id"):
        raise EconomyError(f"unknown shop row key {by!r}")
    return (
        f"SELECT {SHOP_ROW_COLUMNS} FROM npc_shop_items WHERE {by} IN ({placeholders}) ORDER BY id"
        + (" FOR UPDATE" if for_update else "")
    )


def sql_shop_row_by_item(for_update: bool) -> str:
    """The (unique) shop row of :npc_id for :item_id. Columns: SHOP_ROW_COLUMNS."""
    return (
        f"SELECT {SHOP_ROW_COLUMNS} FROM npc_shop_items WHERE npc_id = :npc_id AND item_id = :item_id"
        + (" FOR UPDATE" if for_update else "")
    )


# Conditional take: rowcount 0 = not enough stock. NULL (unlimited, legacy only) never matches,
# so callers take only finite rows.
SQL_SHOP_STOCK_TAKE = "UPDATE npc_shop_items SET stock = stock - :q WHERE id = :id AND stock >= :q"
SQL_SHOP_STOCK_ADD = "UPDATE npc_shop_items SET stock = COALESCE(stock, 0) + :q WHERE id = :id"
SQL_SHOP_STOCK_SET = "UPDATE npc_shop_items SET stock = :stock WHERE id = :id"


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
