"""FEAT-181 ledger contract: shared scenarios + portable SQLite DDL.

CANONICAL COPY: services/character-service/app/tests/econ_contract_cases.py.
Byte-identical in character-, inventory-, locations- and dungeon-service (CI
`econ-contract-copies`). Every service runs CASES through its OWN executor
(sync or async econ_ledger) in `tests/test_econ_contract.py`:

    1. create a fresh SQLite database, execute SQLITE_DDL, then SEED_SQL;
    2. for each Step of a case: call
           econ_ledger.post_operation(session, op_type=step.op_type, legs=step.legs,
                                      source_service="contract-test", **step.kwargs)
       - step.error is None  -> commit;
       - step.error is a name ("InsufficientFunds", "DuplicateOperation", "EconomyError")
         -> assert that exception class (from econ_core) was raised, then roll back;
    3. assert expected_characters / expected_accounts / expected_operations /
       expected_postings with the *_SQL queries below, and world_sum() == 0.

RESOLVE_CASES check resolve_location() / treasury_for_location() on the seeded world;
PLURAL_CASES / FORMAT_CASES check econ_core directly.

Only econ_core is imported here, so this module is identical in every service.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from econ_core import AccountRef, Leg

SOURCE_SERVICE = "contract-test"

# ---------------------------------------------------------------------------
# Portable DDL (SQLite). Column names/types match MySQL migration 027 closely
# enough for the executors' SQL; INTEGER PRIMARY KEY gives autoincrement.
# ---------------------------------------------------------------------------

SQLITE_DDL = [
    """CREATE TABLE IF NOT EXISTS characters (
        id INTEGER PRIMARY KEY,
        name VARCHAR(255) NOT NULL DEFAULT '',
        currency_balance BIGINT NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS Countries (
        id INTEGER PRIMARY KEY,
        name VARCHAR(255) NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS Regions (
        id INTEGER PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        country_id BIGINT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS Districts (
        id INTEGER PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        region_id BIGINT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS Locations (
        id INTEGER PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        district_id BIGINT NULL,
        region_id BIGINT NULL,
        parent_id BIGINT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS econ_settings (
        id INTEGER PRIMARY KEY,
        currency_name VARCHAR(50) NOT NULL,
        currency_genitive VARCHAR(50) NOT NULL,
        currency_one VARCHAR(50) NOT NULL,
        currency_few VARCHAR(50) NOT NULL,
        currency_many VARCHAR(50) NOT NULL,
        currency_short VARCHAR(20) NOT NULL,
        country_tax_rate DECIMAL(5,4) NOT NULL DEFAULT 0.1,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_by_user_id INT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS econ_accounts (
        id INTEGER PRIMARY KEY,
        kind VARCHAR(32) NOT NULL,
        ref_id BIGINT NOT NULL DEFAULT 0,
        name VARCHAR(255) NULL,
        balance BIGINT NOT NULL DEFAULT 0,
        allow_negative INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (kind, ref_id)
    )""",
    """CREATE TABLE IF NOT EXISTS econ_operations (
        id INTEGER PRIMARY KEY,
        op_type VARCHAR(50) NOT NULL,
        idempotency_key VARCHAR(128) NULL UNIQUE,
        location_id BIGINT NULL,
        region_id BIGINT NULL,
        actor_user_id INT NULL,
        source_service VARCHAR(32) NOT NULL,
        comment VARCHAR(500) NULL,
        metadata TEXT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS econ_postings (
        id INTEGER PRIMARY KEY,
        operation_id BIGINT NOT NULL REFERENCES econ_operations (id),
        from_account_id BIGINT NOT NULL REFERENCES econ_accounts (id),
        to_account_id BIGINT NOT NULL REFERENCES econ_accounts (id),
        amount BIGINT NOT NULL CHECK (amount > 0),
        leg_type VARCHAR(32) NOT NULL DEFAULT 'main',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK (from_account_id <> to_account_id)
    )""",
]

# ---------------------------------------------------------------------------
# Seeded world
#   country 1 <- region 10 <- district 100 <- location 1000 <- 1002 (child, no own region)
#                                                            <- 1004 (grandchild)
#   country 2 <- region 20 <- location 1001 (Locations.region_id, no district)
#   location 1003: no district, no region, no parent -> world treasury
#   characters 1..4 start at 0; tax rate 10 %
# ---------------------------------------------------------------------------

SEED_SQL: List[Tuple[str, Dict[str, object]]] = [
    ("INSERT INTO Countries (id, name) VALUES (1, 'Country A')", {}),
    ("INSERT INTO Countries (id, name) VALUES (2, 'Country B')", {}),
    ("INSERT INTO Regions (id, name, country_id) VALUES (10, 'Region A1', 1)", {}),
    ("INSERT INTO Regions (id, name, country_id) VALUES (20, 'Region B1', 2)", {}),
    ("INSERT INTO Districts (id, name, region_id) VALUES (100, 'District A1a', 10)", {}),
    ("INSERT INTO Locations (id, name, district_id, region_id, parent_id) VALUES (1000, 'L1000', 100, NULL, NULL)", {}),
    ("INSERT INTO Locations (id, name, district_id, region_id, parent_id) VALUES (1001, 'L1001', NULL, 20, NULL)", {}),
    ("INSERT INTO Locations (id, name, district_id, region_id, parent_id) VALUES (1002, 'L1002', NULL, NULL, 1000)", {}),
    ("INSERT INTO Locations (id, name, district_id, region_id, parent_id) VALUES (1003, 'L1003', NULL, NULL, NULL)", {}),
    ("INSERT INTO Locations (id, name, district_id, region_id, parent_id) VALUES (1004, 'L1004', NULL, NULL, 1002)", {}),
    ("INSERT INTO characters (id, name, currency_balance) VALUES (1, 'Alice', 0)", {}),
    ("INSERT INTO characters (id, name, currency_balance) VALUES (2, 'Bob', 0)", {}),
    ("INSERT INTO characters (id, name, currency_balance) VALUES (3, 'Carol', 0)", {}),
    ("INSERT INTO characters (id, name, currency_balance) VALUES (4, 'Dave', 0)", {}),
    ("INSERT INTO econ_settings (id, currency_name, currency_genitive, currency_one, currency_few, currency_many, "
     "currency_short, country_tax_rate) VALUES (1, :name, :genitive, :one, :few, :many, :short, 0.1)",
     {"name": "Золото", "genitive": "золота", "one": "золотой", "few": "золотых", "many": "золотых",
      "short": "зол."}),
]

CHARACTER_BALANCE_SQL = "SELECT currency_balance FROM characters WHERE id = :id"
ACCOUNT_BALANCE_SQL = "SELECT balance FROM econ_accounts WHERE kind = :kind AND ref_id = :ref_id"
OPERATION_COUNT_SQL = "SELECT COUNT(*) FROM econ_operations"
POSTING_COUNT_SQL = "SELECT COUNT(*) FROM econ_postings"
WORLD_SUM_SQL = (
    "SELECT (SELECT COALESCE(SUM(currency_balance), 0) FROM characters) + "
    "(SELECT COALESCE(SUM(balance), 0) FROM econ_accounts WHERE kind <> 'character')"
)
TAX_LEG_COUNT_SQL = "SELECT COUNT(*) FROM econ_postings WHERE leg_type = 'tax'"

# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

C1, C2, C3 = AccountRef.character(1), AccountRef.character(2), AccountRef.character(3)
R10, R20 = AccountRef.region(10), AccountRef.region(20)
K1, K2 = AccountRef.country(1), AccountRef.country(2)
WORLD, ESCROW, STORAGE = AccountRef.world(), AccountRef.escrow(), AccountRef.storage()
EMISSION, ADJUSTMENT = AccountRef.emission(), AccountRef.adjustment()


def _fund(*pairs: Tuple[AccountRef, int]) -> "Step":
    """Admin emission funding characters / treasuries (no tax on admin ops)."""
    return Step("admin_emission", [Leg(EMISSION, ref, amount) for ref, amount in pairs],
                {"comment": "contract seed", "apply_tax": False})


@dataclass
class Step:
    op_type: str
    legs: List[Leg]
    kwargs: Dict[str, object] = field(default_factory=dict)
    error: Optional[str] = None                      # expected econ_core exception class name


@dataclass
class ContractCase:
    name: str
    steps: List[Step]
    expected_characters: Dict[int, int] = field(default_factory=dict)
    expected_accounts: Dict[Tuple[str, int], int] = field(default_factory=dict)   # (kind, ref_id) -> balance
    expected_operations: Optional[int] = None
    expected_postings: Optional[int] = None
    expected_tax_legs: Optional[int] = None


CASES: List[ContractCase] = [
    ContractCase(
        name="admin_emission_funds_character_without_tax",
        steps=[_fund((C1, 1000))],
        expected_characters={1: 1000},
        expected_accounts={("emission", 0): -1000},
        expected_operations=1, expected_postings=1, expected_tax_legs=0,
    ),
    ContractCase(
        name="spend_into_region_is_taxed_to_country",
        steps=[_fund((C1, 1000)),
               Step("teleport", [Leg(C1, R10, 155)], {"location_id": 1000})],
        expected_characters={1: 845},
        # tax = floor(155 * 0.1) = 15
        expected_accounts={("region_treasury", 10): 140, ("country_treasury", 1): 15},
        expected_operations=2, expected_postings=3, expected_tax_legs=1,
    ),
    ContractCase(
        name="payout_from_region_may_go_negative_and_is_not_taxed",
        steps=[Step("quest_reward", [Leg(R20, C2, 50)], {"location_id": 1001})],
        expected_characters={2: 50},
        expected_accounts={("region_treasury", 20): -50},
        expected_operations=1, expected_postings=1, expected_tax_legs=0,
    ),
    ContractCase(
        name="insufficient_character_funds_moves_nothing",
        steps=[_fund((C1, 10)),
               Step("teleport", [Leg(C1, R10, 11)], error="InsufficientFunds")],
        expected_characters={1: 10},
        expected_operations=1, expected_postings=1,
    ),
    ContractCase(
        name="escrow_cannot_go_negative",
        steps=[_fund((C1, 100)),
               Step("auction_bid", [Leg(C1, ESCROW, 40)]),
               Step("auction_refund", [Leg(ESCROW, C1, 41)], error="InsufficientFunds")],
        expected_characters={1: 60},
        expected_accounts={("auction_escrow", 0): 40},
        expected_operations=2,
    ),
    ContractCase(
        name="idempotency_key_posts_once",
        steps=[Step("battle_pass_reward", [Leg(WORLD, C3, 25)], {"idempotency_key": "battle_pass_reward:claim:1"}),
               Step("battle_pass_reward", [Leg(WORLD, C3, 25)], {"idempotency_key": "battle_pass_reward:claim:1"},
                    error="DuplicateOperation")],
        expected_characters={3: 25},
        expected_accounts={("world_treasury", 0): -25},
        expected_operations=1, expected_postings=1,
    ),
    ContractCase(
        name="emission_outside_admin_ops_is_rejected",
        steps=[Step("quest_reward", [Leg(EMISSION, C1, 5)], error="EconomyError")],
        expected_characters={1: 0},
        expected_operations=0, expected_postings=0,
    ),
    ContractCase(
        name="admin_ops_require_comment",
        steps=[Step("admin_emission", [Leg(EMISSION, R10, 5)], {"apply_tax": False}, error="EconomyError")],
        expected_operations=0,
    ),
    ContractCase(
        name="zero_legs_post_nothing",
        steps=[Step("battle_reward", [Leg(WORLD, C1, 0)])],
        expected_characters={1: 0},
        expected_operations=0, expected_postings=0,
    ),
    ContractCase(
        name="netting_trade_both_directions_one_operation",
        steps=[_fund((C1, 100), (C2, 100)),
               Step("trade", [Leg(C1, C2, 70), Leg(C2, C1, 30)], {"metadata": {"trade_id": 9}})],
        # C1 nets -40 (has 100) -> ok; legs are journaled unnetted
        expected_characters={1: 60, 2: 140},
        expected_operations=2, expected_postings=4,
    ),
    ContractCase(
        name="netting_allows_spend_covered_by_same_operation_income",
        steps=[_fund((C2, 100)),
               Step("trade", [Leg(C1, C2, 50), Leg(C2, C1, 80)])],
        expected_characters={1: 30, 2: 70},
    ),
    ContractCase(
        name="auction_buyout_commission_taxed_settlement",
        steps=[_fund((C1, 1000), (C2, 1000)),
               Step("auction_bid", [Leg(C2, ESCROW, 200)]),
               Step("auction_buyout", [
                   Leg(C1, ESCROW, 500),
                   Leg(ESCROW, C2, 200, "refund"),
                   Leg(ESCROW, STORAGE, 475),
                   Leg(ESCROW, R20, 25, "commission"),
               ]),
               Step("auction_claim", [Leg(STORAGE, C3, 475)])],
        # commission 25 -> tax floor(2.5) = 2 to country 2
        expected_characters={1: 500, 2: 1000, 3: 475},
        expected_accounts={("auction_escrow", 0): 0, ("auction_storage", 0): 0,
                           ("region_treasury", 20): 23, ("country_treasury", 2): 2},
        expected_tax_legs=1,
    ),
    ContractCase(
        name="tax_disabled_by_apply_tax_false",
        steps=[_fund((C1, 100)),
               Step("house_tax", [Leg(C1, R10, 100)], {"apply_tax": False})],
        expected_characters={1: 0},
        expected_accounts={("region_treasury", 10): 100},
        expected_tax_legs=0,
    ),
    ContractCase(
        name="admin_adjust_down_and_treasury_closed",
        steps=[_fund((C1, 100), (R10, 300)),
               Step("admin_adjust", [Leg(C1, ADJUSTMENT, 40)], {"comment": "fix", "apply_tax": False}),
               Step("treasury_closed", [Leg(R10, K1, 300)])],
        expected_characters={1: 60},
        expected_accounts={("adjustment", 0): 40, ("region_treasury", 10): 0, ("country_treasury", 1): 300},
        # region -> country is not a taxable inflow
        expected_tax_legs=0,
    ),
    ContractCase(
        name="unknown_character_credit_fails",
        steps=[Step("battle_reward", [Leg(WORLD, AccountRef.character(999), 5)], error="EconomyError")],
        expected_operations=0,
    ),
    ContractCase(
        name="leg_type_tax_cannot_be_passed",
        steps=[_fund((C1, 10)), Step("teleport", [Leg(C1, R10, 5, "tax")], error="EconomyError")],
        expected_characters={1: 10},
    ),
]

# location_id -> (region_id, country_id)
RESOLVE_CASES: List[Tuple[Optional[int], Tuple[Optional[int], Optional[int]]]] = [
    (1000, (10, 1)),      # via district
    (1001, (20, 2)),      # via Locations.region_id
    (1002, (10, 1)),      # via parent
    (1004, (10, 1)),      # via grandparent
    (1003, (None, None)),  # orphan -> world treasury
    (999999, (None, None)),
    (None, (None, None)),
]

# (n, expected form) with forms one="a", few="b", many="c"
PLURAL_CASES: List[Tuple[int, str]] = [
    (0, "c"), (1, "a"), (2, "b"), (4, "b"), (5, "c"), (11, "c"), (12, "c"), (14, "c"),
    (21, "a"), (22, "b"), (25, "c"), (101, "a"), (111, "c"), (112, "c"), (1001, "a"), (-1, "a"), (-3, "b"),
]

# (n, short, expected) with econ_core.DEFAULT_FORMS
FORMAT_CASES: List[Tuple[int, bool, str]] = [
    (1, False, "1 золотой"), (3, False, "3 золотых"), (5, False, "5 золотых"), (21, False, "21 золотой"),
    (7, True, "7 зол."),
]
