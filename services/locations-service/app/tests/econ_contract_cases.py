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
       expected_postings / expected_tax_legs / expected_leg_counts (LEG_TYPE_COUNT_SQL per
       leg type) with the *_SQL queries below, and world_sum() == 0.

RESOLVE_CASES check resolve_location() / treasury_for_location() on the seeded world;
PLURAL_CASES / FORMAT_CASES / ITEM_GROUP_CASES check econ_core directly.

FEAT-183 (NPC merchants) adds, at the end of this module: merchant ledger CASES (character 4
plays the merchant NPC), PRICING_CASES / EFFECTIVE_GROUP_CASES / MERCHANT_STATUS_CASES /
BID_CAP_GRID (pure econ_core functions) and a separate merchant SQL smoke world
(MERCHANT_SQLITE_DDL, MERCHANT_QUERY_CASES, MERCHANT_STATUS_SQL_CASES, MERCHANT_STOCK_STEPS);
see the comments there for how a runner executes them.

Only econ_core is imported here, so this module is identical in every service.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from econ_core import (
    SQL_NPC_PLACE,
    SQL_REGION_ECON,
    SQL_REGION_MARKET,
    SQL_SHOP_STOCK_ADD,
    SQL_SHOP_STOCK_SET,
    SQL_SHOP_STOCK_TAKE,
    SQL_SIM_PARAMS,
    AccountRef,
    ItemMarket,
    Leg,
    in_params,
    item_market_from_row,
    merchant_bid_share,
    region_goods_from_rows,
    sql_item_market,
    sql_lock_shop_rows,
    sql_shop_row_by_item,
)

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
     {"name": "Марки", "genitive": "марок", "one": "марка", "few": "марки", "many": "марок",
      "short": "ṃ"}),
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
LEG_TYPE_COUNT_SQL = "SELECT COUNT(*) FROM econ_postings WHERE leg_type = :leg_type"

# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

C1, C2, C3 = AccountRef.character(1), AccountRef.character(2), AccountRef.character(3)
R10, R20 = AccountRef.region(10), AccountRef.region(20)
K1, K2 = AccountRef.country(1), AccountRef.country(2)
WORLD, ESCROW, STORAGE = AccountRef.world(), AccountRef.escrow(), AccountRef.storage()
EMISSION, ADJUSTMENT = AccountRef.emission(), AccountRef.adjustment()
P10, P20 = AccountRef.purse(10), AccountRef.purse(20)


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
    expected_leg_counts: Dict[str, int] = field(default_factory=dict)            # leg_type -> postings


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
    # --- FEAT-182: population purse + region_tick ---------------------------------------------
    ContractCase(
        name="emission_into_population_purse",
        steps=[_fund((P10, 5000))],
        expected_accounts={("population_purse", 10): 5000, ("emission", 0): -5000},
        expected_operations=1, expected_postings=1, expected_tax_legs=0,
    ),
    ContractCase(
        name="region_tick_purse_to_region_is_taxed_to_country",
        steps=[_fund((P10, 1000)),
               Step("region_tick", [Leg(P10, R10, 205), Leg(K1, R10, 7), Leg(R10, P10, 100)],
                    {"region_id": 10, "idempotency_key": "region_tick:1:r:10"})],
        # tax = floor(205 * 0.1) = 20 (only the purse inflow is taxed; the grant country -> region is not)
        expected_accounts={("population_purse", 10): 895, ("region_treasury", 10): 92,
                           ("country_treasury", 1): 13},
        expected_operations=2, expected_postings=5, expected_tax_legs=1,
    ),
    ContractCase(
        name="population_purse_cannot_go_negative",
        steps=[_fund((P20, 50)),
               Step("region_tick", [Leg(P20, R20, 51)], {"region_id": 20}, error="InsufficientFunds")],
        expected_accounts={("population_purse", 20): 50},
        expected_operations=1, expected_postings=1, expected_tax_legs=0,
    ),
    ContractCase(
        name="region_tick_may_not_touch_emission",
        steps=[Step("region_tick", [Leg(EMISSION, P10, 5)], {"region_id": 10}, error="EconomyError")],
        expected_operations=0, expected_postings=0,
    ),
    ContractCase(
        name="purse_closed_into_country_is_not_taxed",
        steps=[_fund((P10, 300)),
               Step("treasury_closed", [Leg(P10, K1, 300)])],
        expected_accounts={("population_purse", 10): 0, ("country_treasury", 1): 300},
        expected_tax_legs=0,
    ),
    # --- FEAT-182 Q1: purse edge cases ---------------------------------------------------------
    ContractCase(
        name="purse_inflow_taxed_like_player_inflow",
        steps=[_fund((C1, 100), (P10, 100)),
               Step("teleport", [Leg(C1, R10, 100)], {"location_id": 1000}),
               Step("region_tick", [Leg(P10, R10, 100)], {"region_id": 10})],
        # both inflows: floor(100 * 0.1) = 10 to country 1
        expected_characters={1: 0},
        expected_accounts={("population_purse", 10): 0, ("region_treasury", 10): 180,
                           ("country_treasury", 1): 20},
        expected_operations=3, expected_postings=6, expected_tax_legs=2,
    ),
    ContractCase(
        name="population_purse_can_be_drained_to_exactly_zero",
        steps=[_fund((P20, 50)),
               Step("region_tick", [Leg(P20, R20, 50)], {"region_id": 20})],
        expected_accounts={("population_purse", 20): 0, ("region_treasury", 20): 45, ("country_treasury", 2): 5},
        expected_operations=2, expected_postings=3, expected_tax_legs=1,
    ),
    ContractCase(
        name="region_tick_purse_debit_covered_by_wages_in_same_operation",
        steps=[_fund((P10, 60)),
               Step("region_tick", [Leg(R10, P10, 100), Leg(P10, R10, 150)], {"region_id": 10})],
        # purse nets -50 (has 60) -> ok; region -100 +150 -15 tax
        expected_accounts={("population_purse", 10): 10, ("region_treasury", 10): 35, ("country_treasury", 1): 15},
        expected_operations=2, expected_postings=4, expected_tax_legs=1,
    ),
    ContractCase(
        name="region_tick_grant_and_wages_are_not_taxed",
        steps=[Step("region_tick", [Leg(K1, R10, 40), Leg(R10, P10, 30), Leg(WORLD, P10, 5)], {"region_id": 10})],
        expected_accounts={("country_treasury", 1): -40, ("region_treasury", 10): 10, ("population_purse", 10): 35,
                           ("world_treasury", 0): -5},
        expected_operations=1, expected_postings=3, expected_tax_legs=0,
    ),
    ContractCase(
        name="region_tick_idempotency_key_posts_once",
        steps=[_fund((P10, 1000)),
               Step("region_tick", [Leg(P10, R10, 100)], {"region_id": 10, "idempotency_key": "region_tick:7:r:10"}),
               Step("region_tick", [Leg(P10, R10, 100)], {"region_id": 10, "idempotency_key": "region_tick:7:r:10"},
                    error="DuplicateOperation")],
        expected_accounts={("population_purse", 10): 900, ("region_treasury", 10): 90, ("country_treasury", 1): 10},
        expected_operations=2, expected_postings=3, expected_tax_legs=1,
    ),
    ContractCase(
        name="region_tick_may_not_touch_adjustment",
        steps=[_fund((P10, 100)),
               Step("region_tick", [Leg(P10, ADJUSTMENT, 5)], {"region_id": 10}, error="EconomyError"),
               Step("region_tick", [Leg(ADJUSTMENT, P10, 5)], {"region_id": 10}, error="EconomyError")],
        expected_accounts={("population_purse", 10): 100},
        expected_operations=1, expected_postings=1,
    ),
    ContractCase(
        name="region_tick_into_emission_is_rejected",
        steps=[_fund((P10, 100)),
               Step("region_tick", [Leg(P10, EMISSION, 5)], {"region_id": 10}, error="EconomyError")],
        expected_accounts={("population_purse", 10): 100, ("emission", 0): -100},
        expected_operations=1, expected_postings=1,
    ),
    ContractCase(
        name="admin_adjust_on_purse_respects_non_negative",
        steps=[_fund((P10, 100)),
               Step("admin_adjust", [Leg(P10, ADJUSTMENT, 101)], {"comment": "fix", "apply_tax": False},
                    error="InsufficientFunds"),
               Step("admin_adjust", [Leg(P10, ADJUSTMENT, 40)], {"comment": "fix", "apply_tax": False}),
               Step("admin_adjust", [Leg(ADJUSTMENT, P10, 15)], {"comment": "fix", "apply_tax": False})],
        expected_accounts={("population_purse", 10): 75, ("adjustment", 0): 25},
        expected_operations=3, expected_postings=3, expected_tax_legs=0,
    ),
    ContractCase(
        name="purse_needs_a_positive_region_id",
        steps=[Step("region_tick", [Leg(AccountRef("population_purse", 0), R10, 1)], error="EconomyError")],
        expected_operations=0, expected_postings=0,
    ),
    ContractCase(
        name="injected_or_unknown_op_type_is_rejected",
        steps=[_fund((P10, 100)),
               Step("region_tick'; DROP TABLE econ_postings; --", [Leg(P10, R10, 1)], error="EconomyError"),
               Step("REGION_TICK", [Leg(P10, R10, 1)], error="EconomyError"),
               Step("region_tick OR 1=1", [Leg(P10, R10, 1)], error="EconomyError")],
        expected_accounts={("population_purse", 10): 100},
        expected_operations=1, expected_postings=1,
    ),
]

# ---------------------------------------------------------------------------
# FEAT-183 NPC merchants: ledger scenarios (character 4 = the merchant NPC), appended to CASES
# ---------------------------------------------------------------------------

C4 = AccountRef.character(4)

_LIVING_BUY = Step("npc_shop_buy", [Leg(C1, C4, 200), Leg(C4, R10, 30, "trade_tax")],
                   {"location_id": 1000, "region_id": 10})

CASES += [
    ContractCase(
        name="merchant_buy_player_to_npc_with_trade_tax",
        steps=[_fund((C1, 1000)), _LIVING_BUY],
        # trade_tax = floor(200 * 0.15) = 30 is a character -> region inflow: floor(30 * 0.1) = 3 to the country
        expected_characters={1: 800, 4: 170},
        expected_accounts={("region_treasury", 10): 27, ("country_treasury", 1): 3},
        expected_operations=2, expected_postings=4, expected_tax_legs=1,
        expected_leg_counts={"main": 2, "trade_tax": 1, "tax": 1},
    ),
    ContractCase(
        name="merchant_debit_above_cash_moves_nothing",
        steps=[_fund((C4, 50)),
               Step("npc_shop_sell", [Leg(C4, C1, 51)], {"location_id": 1000}, error="InsufficientFunds"),
               Step("npc_shop_sell", [Leg(C4, C1, 50)], {"location_id": 1000})],
        expected_characters={1: 50, 4: 0},
        expected_operations=2, expected_postings=2, expected_tax_legs=0,
    ),
    ContractCase(
        name="merchant_trade_cannot_restock_beyond_cash",
        steps=[_fund((P10, 1000), (C4, 10)),
               Step("merchant_trade", [Leg(P10, C4, 100), Leg(C4, R10, 15, "trade_tax"), Leg(C4, P10, 96)],
                    {"region_id": 10}, error="InsufficientFunds")],
        # NPC nets 10 + 100 - 15 - 96 = -1 -> refused, nothing moved
        expected_characters={4: 10},
        expected_accounts={("population_purse", 10): 1000},
        expected_operations=1, expected_postings=2, expected_tax_legs=0,
    ),
    ContractCase(
        name="merchant_buy_reversal_restores_every_balance",
        steps=[_fund((C1, 1000)), _LIVING_BUY,
               Step("npc_shop_buy_refund",
                    [Leg(C4, C1, 200, "refund"), Leg(R10, C4, 30, "refund"), Leg(K1, R10, 3, "refund")],
                    {"location_id": 1000, "region_id": 10, "apply_tax": False})],
        expected_characters={1: 1000, 4: 0},
        expected_accounts={("region_treasury", 10): 0, ("country_treasury", 1): 0},
        expected_operations=3, expected_postings=7, expected_tax_legs=1,
        expected_leg_counts={"refund": 3, "trade_tax": 1},
    ),
    ContractCase(
        name="merchant_refund_falls_back_to_treasury_when_npc_cash_spent",
        steps=[_fund((C1, 1000)), _LIVING_BUY,
               Step("npc_shop_sell", [Leg(C4, C2, 170)], {"location_id": 1000}),
               Step("npc_shop_buy_refund",
                    [Leg(C4, C1, 200, "refund"), Leg(R10, C4, 30, "refund"), Leg(K1, R10, 3, "refund")],
                    {"apply_tax": False}, error="InsufficientFunds"),
               Step("npc_shop_buy_refund", [Leg(R10, C1, 200, "refund")],
                    {"location_id": 1000, "metadata": {"fallback": True}})],
        expected_characters={1: 1000, 2: 170, 4: 0},
        expected_accounts={("region_treasury", 10): -173, ("country_treasury", 1): 3},
        expected_operations=4, expected_postings=6, expected_tax_legs=1,
    ),
    ContractCase(
        name="merchant_trade_residents_tax_restock_upkeep",
        steps=[_fund((P10, 1000), (C4, 100)),
               Step("merchant_trade",
                    [Leg(P10, C4, 300), Leg(C4, R10, 45, "trade_tax"), Leg(C4, P10, 120), Leg(C4, P10, 20)],
                    {"region_id": 10, "idempotency_key": "merchant_trade:1:r:10",
                     "metadata": {"merchants": {"4": {"sold_value": 300, "tax": 45, "restock_value": 120,
                                                      "upkeep": 20}}}}),
               Step("merchant_trade", [Leg(P10, C4, 300)],
                    {"region_id": 10, "idempotency_key": "merchant_trade:1:r:10"}, error="DuplicateOperation")],
        # NPC 100 + 300 - 45 - 120 - 20 = 215; purse 1000 - 300 + 140 = 840; tax floor(4.5) = 4
        expected_characters={4: 215},
        expected_accounts={("population_purse", 10): 840, ("region_treasury", 10): 41, ("country_treasury", 1): 4},
        expected_operations=2, expected_postings=7, expected_tax_legs=1,
        expected_leg_counts={"trade_tax": 1, "main": 5},
    ),
    ContractCase(
        name="merchant_trade_may_not_touch_emission",
        steps=[Step("merchant_trade", [Leg(EMISSION, C4, 5)], {"region_id": 10}, error="EconomyError"),
               Step("merchant_trade", [Leg(C4, ADJUSTMENT, 0)], {"region_id": 10}, error="EconomyError")],
        expected_characters={4: 0},
        expected_operations=0, expected_postings=0,
    ),
    ContractCase(
        name="trade_tax_without_apply_tax_is_not_taxed",
        steps=[_fund((C4, 100)),
               Step("npc_shop_buy", [Leg(C4, R10, 40, "trade_tax")], {"region_id": 10, "apply_tax": False})],
        expected_characters={4: 60},
        expected_accounts={("region_treasury", 10): 40},
        expected_tax_legs=0, expected_leg_counts={"trade_tax": 1},
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

# ((item_type, resource_subcategory, is_food, item_rarity), (group_code, off_market)) for
# econ_core.auto_item_group (FEAT-182 3.6).
ITEM_GROUP_CASES: List[Tuple[Tuple[Optional[str], Optional[str], bool, Optional[str]], Tuple[Optional[str], bool]]] = [
    (("consumable", None, True, "common"), ("food", False)),
    (("consumable", None, False, "rare"), ("potions", False)),
    (("resource", "ore", False, "common"), ("ore_metal", False)),
    (("resource", "ingot", False, "common"), ("ore_metal", False)),
    (("resource", "wood", False, "common"), ("wood", False)),
    (("resource", "herb", False, "common"), ("herbs", False)),
    (("resource", "reagent", False, "common"), ("herbs", False)),
    (("resource", "ingredient", False, "common"), ("food", False)),
    (("resource", "trophy", False, "common"), ("hides_textiles", False)),
    (("resource", "magic_dust", False, "common"), ("magic", False)),
    (("resource", "essence", False, "epic"), ("magic", False)),
    (("resource", "material", False, "common"), ("magic", False)),
    (("resource", "whetstone", False, "common"), ("tools", False)),
    (("resource", "repair_kit", False, "common"), ("tools", False)),
    (("resource", None, True, "common"), ("food", False)),
    (("resource", None, False, "common"), (None, False)),
    (("resource", "ore", False, "legendary"), ("ore_metal", True)),
    (("weapon", None, False, "epic"), ("weapons", False)),
    (("weapon", None, False, "divine"), ("weapons", True)),
    (("head", None, False, "common"), ("armor", False)),
    (("body", None, False, "common"), ("armor", False)),
    (("cloak", None, False, "common"), ("armor", False)),
    (("belt", None, False, "common"), ("armor", False)),
    (("ring", None, False, "common"), ("jewelry", False)),
    (("necklace", None, False, "rare"), ("jewelry", False)),
    (("bracelet", None, False, "common"), ("jewelry", False)),
    (("gem", None, False, "mythical"), ("jewelry", True)),
    (("rune", None, False, "common"), ("magic", False)),
    (("gathering_tool", None, False, "common"), ("tools", False)),
    (("furniture", None, False, "demonic"), ("household", True)),
    (("misc", None, False, "common"), (None, False)),
    (("scroll", None, False, "common"), (None, True)),
    (("recipe", None, False, "common"), (None, True)),
    ((None, None, False, None), (None, False)),
    # FEAT-182 Q1 edge cases
    (("consumable", None, True, "legendary"), ("food", True)),
    (("consumable", None, False, "demonic"), ("potions", True)),
    (("consumable", "herb", False, "common"), ("potions", False)),       # subcategory ignored outside resources
    (("consumable", None, None, None), ("potions", False)),
    (("resource", "ore", True, "common"), ("ore_metal", False)),         # is_food ignored when subcategory set
    (("resource", "ingredient", True, "mythical"), ("food", True)),
    (("resource", "", True, "common"), ("food", False)),                 # empty subcategory == NULL
    (("resource", None, 1, None), ("food", False)),
    (("resource", None, 0, None), (None, False)),
    (("resource", None, None, "rare"), (None, False)),
    (("resource", "unknown_sub", True, "common"), (None, False)),
    (("weapon", None, False, None), ("weapons", False)),
    (("weapon", None, False, "unknown_rarity"), ("weapons", False)),
    (("shield", None, False, "common"), (None, False)),                  # unknown item type
    (("", None, True, "common"), (None, False)),
    (("misc", None, True, "mythical"), (None, True)),
    (("scroll", None, False, "legendary"), (None, True)),
    (("recipe", "ore", True, "common"), (None, True)),
    ((None, None, False, "divine"), (None, True)),
]

# (n, short, expected) with econ_core.DEFAULT_FORMS
FORMAT_CASES: List[Tuple[int, bool, str]] = [
    (1, False, "1 марка"), (3, False, "3 марки"), (5, False, "5 марок"), (21, False, "21 марка"),
    (7, True, "7 ṃ"),
]

# ---------------------------------------------------------------------------
# FEAT-183 pure merchant functions (econ_core). (function name, args, expected): the runner asserts
# getattr(econ_core, name)(*args) == expected.
# ---------------------------------------------------------------------------

PRICING_CASES: List[Tuple[str, tuple, object]] = [
    # ask = max(1, ceil(base_ask * mult))
    ("market_ask", (20, "1"), 20),
    ("market_ask", (20, "1.25"), 25),
    ("market_ask", (20, "0.5"), 10),
    ("market_ask", (7, "1.1"), 8),
    ("market_ask", (3, "0.333"), 1),
    ("market_ask", (1, "0.5"), 1),
    ("market_ask", (0, "2"), 1),
    ("market_ask", (100, "3"), 300),
    ("market_ask", (100, 0.07), 7),                  # float mult goes through str: no 7.000000000000001 -> 8
    ("market_ask", (20, Decimal("1.4")), 28),
    # bid = min(floor(base_bid * mult), floor(ask * 0.5)); < 1 -> 0 («does not buy»)
    ("market_bid", (10, "1", 20), 10),
    ("market_bid", (15, "1", 20), 10),               # admin sell_price above buy/2 is capped
    ("market_bid", (19, "1", 20), 10),
    ("market_bid", (10, "1.25", 25), 12),
    ("market_bid", (10, "3", 60), 30),
    ("market_bid", (10, "0.5", 10), 5),
    ("market_bid", (0, "1", 20), 0),
    ("market_bid", (-5, "1", 20), 0),
    ("market_bid", (1, "0.5", 1), 0),
    ("market_bid", (10, "1", 1), 0),
    # wholesale = max(1, floor(base_ask * mult * share))
    ("wholesale_price", (20, "1", "0.5"), 10),
    ("wholesale_price", (20, "1.25", "0.5"), 12),
    ("wholesale_price", (7, "1.1", "0.5"), 3),
    ("wholesale_price", (2500, "0.8", "0.5"), 1000),
    ("wholesale_price", (1, "0.5", "0.5"), 1),
    # charisma -> discount percent (same numbers as the stage-1 shop)
    ("charisma_discount_pct", (None,), Decimal(0)),
    ("charisma_discount_pct", (0,), Decimal(0)),
    ("charisma_discount_pct", (-5,), Decimal(0)),
    ("charisma_discount_pct", (3,), Decimal("0.6")),
    ("charisma_discount_pct", (30,), Decimal(6)),
    ("charisma_discount_pct", (249,), Decimal("49.8")),
    ("charisma_discount_pct", (250,), Decimal(50)),
    ("charisma_discount_pct", (100000,), Decimal(50)),
    ("charisma_discount_pct", ("abc",), Decimal(0)),
    # player pays ceil(ask * (1 - pct / 100)), pct clamped to 0..50
    ("discounted_ask", (20, 0), 20),
    ("discounted_ask", (20, 6), 19),
    ("discounted_ask", (100, 7), 93),                # float maths gave 94 (93.00000000000001)
    ("discounted_ask", (20, 50), 10),
    ("discounted_ask", (21, 50), 11),
    ("discounted_ask", (1, 50), 1),
    ("discounted_ask", (20, 80), 10),
    ("discounted_ask", (20, -10), 20),
    ("discounted_ask", (100, Decimal("49.8")), 51),
    # units (value-based mapping item -> region units)
    ("units_per_item", (2500, 10), 250.0),
    ("units_per_item", (20, 2), 10.0),
    ("units_per_item", (5, 10), 0.5),
    ("units_per_item", (5, 0), 0.0),
    ("units_per_item", (5, None), 0.0),
    # merchant sales tax
    ("trade_tax", (200, "0.15"), 30),
    ("trade_tax", (199, "0.1"), 19),
    ("trade_tax", (7, "0.1"), 0),
    ("trade_tax", (0, "0.1"), 0),
    ("trade_tax", (-50, "0.1"), 0),
    ("trade_tax", (100, "0"), 0),
    ("trade_tax", (100, "-0.2"), 0),
    ("trade_tax", (100, "1.5"), 100),
    ("trade_tax", (100, Decimal("0.1250")), 12),
    # item_base = items.price if > 0 else group base
    ("item_base_price", (2500, 10), 2500),
    ("item_base_price", (None, 10), 10),
    ("item_base_price", (0, 120), 120),
    ("item_base_price", (-5, 120), 120),
    ("item_base_price", (None, None), 0),
    ("item_base_price", (0, 0), 0),
    # region multiplier of an item at a merchant
    ("market_mult", (True, "food", False, {"food": "1.4"}), Decimal("1.4")),
    ("market_mult", (False, "food", False, {"food": "1.4"}), Decimal(1)),
    ("market_mult", (True, "food", True, {"food": "1.4"}), Decimal(1)),
    ("market_mult", (True, None, False, {"food": "1.4"}), Decimal(1)),
    ("market_mult", (True, "ore_metal", False, {"food": "1.4"}), Decimal(1)),
    ("market_mult", (True, "food", False, {"food": 0}), Decimal(1)),
    ("market_mult", (True, "food", False, {"food": 2.5}), Decimal("2.5")),
    # shop badge
    ("price_level", ("0.5",), "low"),
    ("price_level", ("0.85",), "low"),
    ("price_level", ("0.86",), "normal"),
    ("price_level", (1,), "normal"),
    ("price_level", ("1.19",), "normal"),
    ("price_level", ("1.2",), "high"),
    ("price_level", ("3",), "high"),
    # merchant_bid_share from econ_sim_settings.params
    ("merchant_bid_share", (None,), Decimal("0.5")),
    ("merchant_bid_share", ("{}",), Decimal("0.5")),
    ("merchant_bid_share", ('{"merchant_bid_share": 0.3}',), Decimal("0.3")),
    ("merchant_bid_share", (b'{"merchant_bid_share": 0.4}',), Decimal("0.4")),
    ("merchant_bid_share", ({"merchant_bid_share": 2},), Decimal(1)),
    ("merchant_bid_share", ({"merchant_bid_share": -1},), Decimal(0)),
    ("merchant_bid_share", ({"merchant_bid_share": "abc"},), Decimal("0.5")),
    ("merchant_bid_share", ({"merchant_bid_share": True},), Decimal("0.5")),
    ("merchant_bid_share", ("not json",), Decimal("0.5")),
    ("merchant_bid_share", ("[1, 2]",), Decimal("0.5")),
    # base bid outside the assortment
    ("default_bid", (2500, "0.5"), 1250),
    ("default_bid", (25, "0.5"), 12),
    ("default_bid", (1, "0.5"), 0),
    ("default_bid", (100, Decimal("0.4")), 40),
]

# ((item_type, resource_subcategory, is_food, item_rarity, override_group, override_off_market),
#  (group, off_market)) for econ_core.effective_item_group. The runner also checks every
# ITEM_GROUP_CASES row without override: same group, off-market = auto off-market or no group.
EFFECTIVE_GROUP_CASES: List[Tuple[tuple, Tuple[Optional[str], bool]]] = [
    (("consumable", None, True, "common", None, None), ("food", False)),
    (("misc", None, False, "common", None, None), (None, True)),            # no group -> off-market
    (("misc", None, False, "common", "tools", None), ("tools", False)),
    (("misc", None, False, "common", None, False), (None, True)),           # still no group -> off-market
    (("resource", None, False, "common", None, None), (None, True)),
    (("resource", "ore", False, "common", None, 1), ("ore_metal", True)),   # DB tinyint 1
    (("weapon", None, False, "common", None, True), ("weapons", True)),
    (("weapon", None, False, "legendary", None, False), ("weapons", False)),
    (("weapon", None, False, "legendary", None, 0), ("weapons", False)),    # DB tinyint 0
    (("weapon", None, False, "common", "armor", None), ("armor", False)),
    (("scroll", None, False, "common", "magic", None), ("magic", True)),    # scroll stays off-market
    (("scroll", None, False, "common", "magic", False), ("magic", False)),
    ((None, None, None, None, "food", None), ("food", False)),
]

# (npc_row (id, is_npc, npc_status, current_location_id, marker_type) | None,
#  region_row (region_id, template_code, population, tax_rate) | None) -> (living, reason)
_LIVING_REGION = (10, "capital", 1200, "0.15")
MERCHANT_STATUS_CASES: List[Tuple[Optional[tuple], Optional[tuple], Tuple[bool, Optional[str]]]] = [
    ((5, 1, "alive", 1000, "safe"), _LIVING_REGION, (True, None)),
    ((5, True, "alive", 1000, "farm"), _LIVING_REGION, (True, None)),
    ((5, 1, "alive", 1000, "dangerous"), _LIVING_REGION, (True, None)),
    (None, _LIVING_REGION, (False, "not_npc")),
    ((5, 0, "alive", 1000, "safe"), _LIVING_REGION, (False, "not_npc")),
    ((5, 1, "dead", 1000, "safe"), _LIVING_REGION, (False, "dead")),
    ((5, 1, "dead", 1000, "dungeon"), None, (False, "dead")),
    ((5, 1, "alive", None, None), None, (False, "no_location")),
    ((5, 1, "alive", 0, None), None, (False, "no_location")),
    ((5, 1, "alive", 1000, "dungeon"), _LIVING_REGION, (False, "dungeon")),
    ((5, 1, "alive", 1000, "safe"), None, (False, "no_region")),
    ((5, 1, "alive", 4040, None), None, (False, "no_region")),             # location row is gone
    ((5, 1, "alive", 1000, "safe"), (10, None, None, None), (False, "not_simulated")),
    ((5, 1, "alive", 1000, "safe"), (10, None, 1200, "0.1"), (False, "not_simulated")),
    ((5, 1, "alive", 1000, "safe"), (10, "rural", 0, "0.1"), (False, "not_simulated")),
    ((5, 1, "alive", 1000, "safe"), (10, "rural", None, "0.1"), (False, "not_simulated")),
]

# (base_ask, base_bid, mult) grid for the no-profit property: for every row the runner asserts
#   bid <= discounted_ask(ask, charisma_discount_pct(10 ** 6))  and  2 * bid <= ask,
# where ask = market_ask(base_ask, mult) and bid = market_bid(base_bid, mult, ask).
BID_CAP_GRID: List[Tuple[int, int, str]] = [
    (base_ask, base_bid, mult)
    for base_ask in (1, 2, 3, 7, 10, 19, 20, 99, 100, 2500)
    for base_bid in sorted({0, 1, base_ask // 3, base_ask // 2, (3 * base_ask) // 4, base_ask, 2 * base_ask})
    for mult in ("0.5", "0.73", "0.85", "1", "1.17", "2.5", "3")
]

# ---------------------------------------------------------------------------
# FEAT-183 merchant SQL smoke world (its OWN fresh SQLite, separate from SQLITE_DDL so the service
# test suites that reuse SQLITE_DDL are unaffected). Runners: execute MERCHANT_SQLITE_DDL +
# MERCHANT_SEED_SQL, then
#   * MERCHANT_QUERY_CASES: rows = [tuple(r) for r in execute(sql, params)]; assert convert(rows) == expected;
#   * MERCHANT_STATUS_SQL_CASES: npc = first(SQL_NPC_PLACE, id); region_id = econ_ledger.resolve_location(
#       npc[3] if npc else None)[0]; region = first(SQL_REGION_ECON, region_id) if region_id else None;
#       assert econ_core.merchant_status(npc, region) == expected;
#   * MERCHANT_STOCK_STEPS in order on one database: assert execute(sql, params).rowcount == rowcount;
#     then dict(MERCHANT_STOCK_SQL rows) == MERCHANT_STOCK_EXPECTED.
#
#   country 1 <- region 10 (capital, pop 1200, tax 0.15) <- district 100 <- location 1000 <- 1005 (farm)
#                region 10 <- location 1004 (dungeon)
#   region 20: econ_regions row without template <- 1001;  region 30: no econ_regions row <- 1002
#   region 40: template, population 0 <- 1006;  location 1003: no region
# ---------------------------------------------------------------------------

MERCHANT_SQLITE_DDL = [
    """CREATE TABLE characters (
        id INTEGER PRIMARY KEY,
        name VARCHAR(255) NOT NULL DEFAULT '',
        is_npc INTEGER NOT NULL DEFAULT 0,
        npc_status VARCHAR(10) NOT NULL DEFAULT 'alive',
        current_location_id BIGINT NULL,
        currency_balance BIGINT NOT NULL DEFAULT 0
    )""",
    "CREATE TABLE Countries (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL)",
    "CREATE TABLE Regions (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, country_id BIGINT NOT NULL)",
    "CREATE TABLE Districts (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, region_id BIGINT NOT NULL)",
    """CREATE TABLE Locations (
        id INTEGER PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        district_id BIGINT NULL,
        region_id BIGINT NULL,
        parent_id BIGINT NULL,
        marker_type VARCHAR(16) NOT NULL DEFAULT 'safe'
    )""",
    """CREATE TABLE econ_regions (
        region_id INTEGER PRIMARY KEY,
        template_code VARCHAR(32) NULL,
        population INTEGER NOT NULL DEFAULT 0,
        tax_rate DECIMAL(5,4) NOT NULL DEFAULT 0.1
    )""",
    """CREATE TABLE econ_goods_groups (
        code VARCHAR(32) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        base_price INTEGER NOT NULL
    )""",
    """CREATE TABLE econ_region_goods (
        region_id BIGINT NOT NULL,
        group_code VARCHAR(32) NOT NULL,
        stock DECIMAL(16,3) NOT NULL DEFAULT 0,
        norm_stock DECIMAL(16,3) NOT NULL DEFAULT 0,
        price_mult DECIMAL(6,3) NOT NULL DEFAULT 1,
        PRIMARY KEY (region_id, group_code)
    )""",
    """CREATE TABLE items (
        id INTEGER PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        image VARCHAR(255) NULL,
        item_type VARCHAR(32) NOT NULL,
        item_rarity VARCHAR(32) NULL,
        resource_subcategory VARCHAR(32) NULL,
        is_food INTEGER NOT NULL DEFAULT 0,
        price INTEGER NULL
    )""",
    """CREATE TABLE econ_item_groups (
        item_id INTEGER PRIMARY KEY,
        group_code VARCHAR(32) NULL,
        off_market INTEGER NULL
    )""",
    """CREATE TABLE econ_sim_settings (
        id INTEGER PRIMARY KEY,
        tick_enabled INTEGER NOT NULL DEFAULT 1,
        params TEXT NOT NULL
    )""",
    """CREATE TABLE npc_shop_items (
        id INTEGER PRIMARY KEY,
        npc_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        buy_price INTEGER NOT NULL,
        sell_price INTEGER NOT NULL DEFAULT 0,
        stock INTEGER NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        restock_target INTEGER NOT NULL DEFAULT 0,
        origin VARCHAR(16) NOT NULL DEFAULT 'admin',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (npc_id, item_id)
    )""",
]

MERCHANT_SEED_SQL: List[Tuple[str, Dict[str, object]]] = [
    ("INSERT INTO Countries (id, name) VALUES (1, 'Country A')", {}),
    ("INSERT INTO Regions (id, name, country_id) VALUES (10, 'Capital', 1), (20, 'No template', 1), "
     "(30, 'Not in econ', 1), (40, 'Empty', 1)", {}),
    ("INSERT INTO Districts (id, name, region_id) VALUES (100, 'Old town', 10)", {}),
    ("INSERT INTO Locations (id, name, district_id, region_id, parent_id, marker_type) VALUES "
     "(1000, 'Market', 100, NULL, NULL, 'safe'), (1001, 'L1001', NULL, 20, NULL, 'safe'), "
     "(1002, 'L1002', NULL, 30, NULL, 'safe'), (1003, 'Nowhere', NULL, NULL, NULL, 'safe'), "
     "(1004, 'Crypt', NULL, 10, NULL, 'dungeon'), (1005, 'Farm', NULL, NULL, 1000, 'farm'), "
     "(1006, 'L1006', NULL, 40, NULL, 'safe')", {}),
    ("INSERT INTO econ_regions (region_id, template_code, population, tax_rate) VALUES "
     "(10, 'capital', 1200, 0.15), (20, NULL, 500, 0.1), (40, 'rural', 0, 0.1)", {}),
    ("INSERT INTO characters (id, name, is_npc, npc_status, current_location_id, currency_balance) VALUES "
     "(31, 'Trader', 1, 'alive', 1000, 500), (32, 'Farmer', 1, 'alive', 1005, 0), "
     "(33, 'Ghost', 1, 'dead', 1000, 0), (34, 'Wanderer', 1, 'alive', NULL, 0), "
     "(35, 'Crypt keeper', 1, 'alive', 1004, 0), (36, 'Hermit', 1, 'alive', 1003, 0), "
     "(37, 'T37', 1, 'alive', 1001, 0), (38, 'T38', 1, 'alive', 1002, 0), (39, 'T39', 1, 'alive', 1006, 0), "
     "(40, 'Player', 0, 'alive', 1000, 0), (41, 'Lost', 1, 'alive', 4040, 0)", {}),
    ("INSERT INTO econ_goods_groups (code, name, base_price) VALUES "
     "('food', 'Еда', 2), ('ore_metal', 'Руда', 10), ('tools', 'Инструменты', 15), ('weapons', 'Оружие', 120)", {}),
    ("INSERT INTO econ_region_goods (region_id, group_code, price_mult) VALUES "
     "(10, 'food', 1.4), (10, 'ore_metal', 0.8), (10, 'weapons', 1), (20, 'food', 2.5)", {}),
    ("INSERT INTO items (id, name, image, item_type, item_rarity, resource_subcategory, is_food, price) VALUES "
     "(1, 'Хлеб', 'b.png', 'consumable', 'common', NULL, 1, 3), (2, 'Руда', NULL, 'resource', 'common', 'ore', 0, 2500), "
     "(3, 'Меч', NULL, 'weapon', 'common', NULL, 0, NULL), (4, 'Свиток', NULL, 'scroll', 'rare', NULL, 0, 50), "
     "(5, 'Штука', NULL, 'misc', 'common', NULL, 0, 0), (6, 'Молот', NULL, 'misc', 'common', NULL, 0, 40), "
     "(7, 'Клинок', NULL, 'weapon', 'legendary', NULL, 0, 900)", {}),
    ("INSERT INTO econ_item_groups (item_id, group_code, off_market) VALUES (6, 'tools', NULL), (7, NULL, 0)", {}),
    ("INSERT INTO econ_sim_settings (id, tick_enabled, params) VALUES (1, 1, :params)",
     {"params": '{"dt": 0.25, "merchant_bid_share": 0.4}'}),
    ("INSERT INTO npc_shop_items (id, npc_id, item_id, buy_price, sell_price, stock, is_active, restock_target, "
     "origin) VALUES (1, 31, 1, 4, 2, 5, 1, 10, 'admin'), (2, 31, 2, 3000, 1250, NULL, 1, 10, 'admin'), "
     "(3, 32, 3, 150, 60, 0, 1, 0, 'player'), (4, 31, 4, 60, 0, 3, 0, 0, 'admin')", {}),
]


def _rows(rows):
    return rows


def _item_markets(rows):
    return [item_market_from_row(r) for r in rows]


def _bid_share(rows):
    return merchant_bid_share(rows[0][0] if rows else None)


_ITEM_IDS_PH, _ITEM_IDS = in_params("i", [7, 1, 2, 6, 404])
_NPC_IDS_PH, _NPC_IDS = in_params("n", [31, 999])
_ROW_IDS_PH, _ROW_IDS = in_params("r", [3, 1])

# (name, sql, params, convert(rows), expected)
MERCHANT_QUERY_CASES: List[Tuple[str, str, Dict[str, object], object, object]] = [
    ("npc_place_living", SQL_NPC_PLACE, {"id": 31}, _rows, [(31, 1, "alive", 1000, "safe")]),
    ("npc_place_no_location", SQL_NPC_PLACE, {"id": 34}, _rows, [(34, 1, "alive", None, None)]),
    ("npc_place_location_gone", SQL_NPC_PLACE, {"id": 41}, _rows, [(41, 1, "alive", 4040, None)]),
    ("npc_place_unknown", SQL_NPC_PLACE, {"id": 999}, _rows, []),
    ("region_econ_simulated", SQL_REGION_ECON, {"region_id": 10}, _rows, [(10, "capital", 1200, 0.15)]),
    ("region_econ_without_row", SQL_REGION_ECON, {"region_id": 30}, _rows, [(30, None, None, None)]),
    ("region_econ_unknown", SQL_REGION_ECON, {"region_id": 999}, _rows, []),
    ("region_market", SQL_REGION_MARKET, {"region_id": 10}, region_goods_from_rows,
     ({"food": Decimal("1.4"), "ore_metal": Decimal("0.8"), "tools": Decimal(1), "weapons": Decimal(1)},
      {"food": 2, "ore_metal": 10, "tools": 15, "weapons": 120})),
    ("region_market_without_goods", SQL_REGION_MARKET, {"region_id": 30}, region_goods_from_rows,
     ({"food": Decimal(1), "ore_metal": Decimal(1), "tools": Decimal(1), "weapons": Decimal(1)},
      {"food": 2, "ore_metal": 10, "tools": 15, "weapons": 120})),
    ("item_market", sql_item_market(_ITEM_IDS_PH), _ITEM_IDS, _item_markets, [
        ItemMarket(1, "Хлеб", "b.png", 3, "food", False),
        ItemMarket(2, "Руда", None, 2500, "ore_metal", False),
        ItemMarket(6, "Молот", None, 40, "tools", False),          # override group on a misc item
        ItemMarket(7, "Клинок", None, 900, "weapons", False),      # override un-offs a legendary
    ]),
    ("sim_params_bid_share", SQL_SIM_PARAMS, {}, _bid_share, Decimal("0.4")),
    ("shop_rows_by_npc", sql_lock_shop_rows(_NPC_IDS_PH, False), _NPC_IDS, _rows, [
        (1, 31, 1, 4, 2, 5, 10, "admin", 1),
        (2, 31, 2, 3000, 1250, None, 10, "admin", 1),
        (4, 31, 4, 60, 0, 3, 0, "admin", 0),
    ]),
    ("shop_rows_by_id", sql_lock_shop_rows(_ROW_IDS_PH, False, by="id"), _ROW_IDS, _rows, [
        (1, 31, 1, 4, 2, 5, 10, "admin", 1),
        (3, 32, 3, 150, 60, 0, 0, "player", 1),
    ]),
    ("shop_row_by_item", sql_shop_row_by_item(False), {"npc_id": 31, "item_id": 2}, _rows,
     [(2, 31, 2, 3000, 1250, None, 10, "admin", 1)]),
    ("shop_row_by_item_missing", sql_shop_row_by_item(False), {"npc_id": 32, "item_id": 2}, _rows, []),
]

# npc id -> merchant_status through the SQL above + econ_ledger.resolve_location
MERCHANT_STATUS_SQL_CASES: List[Tuple[int, Tuple[bool, Optional[str]]]] = [
    (31, (True, None)),
    (32, (True, None)),                 # via the parent location
    (33, (False, "dead")),
    (34, (False, "no_location")),
    (35, (False, "dungeon")),
    (36, (False, "no_region")),
    (37, (False, "not_simulated")),     # econ_regions row without template
    (38, (False, "not_simulated")),     # no econ_regions row
    (39, (False, "not_simulated")),     # population 0
    (40, (False, "not_npc")),
    (41, (False, "no_region")),         # location row is gone
    (999, (False, "not_npc")),
]

# (sql, params, expected rowcount), executed in order on one database
MERCHANT_STOCK_STEPS: List[Tuple[str, Dict[str, object], int]] = [
    (SQL_SHOP_STOCK_TAKE, {"id": 1, "q": 3}, 1),      # 5 -> 2
    (SQL_SHOP_STOCK_TAKE, {"id": 1, "q": 3}, 0),      # 2 < 3: refused, unchanged
    (SQL_SHOP_STOCK_TAKE, {"id": 1, "q": 2}, 1),      # 2 -> 0 (exactly the last units)
    (SQL_SHOP_STOCK_TAKE, {"id": 2, "q": 1}, 0),      # NULL (unlimited) never matches
    (SQL_SHOP_STOCK_ADD, {"id": 2, "q": 4}, 1),       # NULL -> 4
    (SQL_SHOP_STOCK_ADD, {"id": 1, "q": 1}, 1),       # 0 -> 1
    (SQL_SHOP_STOCK_SET, {"id": 3, "stock": 7}, 1),
    (SQL_SHOP_STOCK_TAKE, {"id": 404, "q": 1}, 0),
]
MERCHANT_STOCK_SQL = "SELECT id, stock FROM npc_shop_items ORDER BY id"
MERCHANT_STOCK_EXPECTED: Dict[int, Optional[int]] = {1: 1, 2: 4, 3: 7, 4: 3}
