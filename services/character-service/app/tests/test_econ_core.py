"""FEAT-181 Q1: unit tests of the pure ledger contract `econ_core` (no database).

Plural forms, tax rounding, tax-leg generation, netting and the fixed apply order, validation
(including "money is created only by genesis / admin operations"), settings parsing and cache.
"""

from decimal import Decimal

import pytest

import econ_core as core
from econ_core import AccountRef, Leg

C1, C2, C5 = AccountRef.character(1), AccountRef.character(2), AccountRef.character(5)
R10, R20 = AccountRef.region(10), AccountRef.region(20)
K1 = AccountRef.country(1)
WORLD, ESCROW, STORAGE = AccountRef.world(), AccountRef.escrow(), AccountRef.storage()
EMISSION, ADJUSTMENT = AccountRef.emission(), AccountRef.adjustment()

SRC = "unit-test"


# ---------------------------------------------------------------------------
# Plural forms / formatting
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n,expected", [
    (1, "1 марка"), (2, "2 марки"), (5, "5 марок"), (11, "11 марок"),
    (21, "21 марка"), (111, "111 марок"), (0, "0 марок"), (1001, "1001 марка"),
])
def test_format_currency_default_forms(n, expected):
    assert core.format_currency(n) == expected


@pytest.mark.parametrize("n,expected", [
    (1, "крона"), (2, "кроны"), (4, "кроны"), (5, "крон"), (11, "крон"), (12, "крон"),
    (14, "крон"), (21, "крона"), (22, "кроны"), (111, "крон"), (112, "крон"), (121, "крона"),
])
def test_plural_with_distinct_forms(n, expected):
    """Default forms share few == many, so distinct forms are needed to see the few/many split."""
    assert core.plural_ru(n, "крона", "кроны", "крон") == expected


def test_format_currency_custom_forms_and_short():
    forms = core.CurrencyForms(name="Крона", genitive="крон", one="крона", few="кроны", many="крон", short="кр.")
    assert core.format_currency(3, forms) == "3 кроны"
    assert core.format_currency(21, forms) == "21 крона"
    assert core.format_currency(5, forms, short=True) == "5 кр."
    assert forms.as_dict() == {"name": "Крона", "genitive": "крон", "one": "крона", "few": "кроны",
                               "many": "крон", "short": "кр."}


def test_default_forms_match_the_design():
    assert core.DEFAULT_FORMS.as_dict() == {"name": "Марки", "genitive": "марок", "one": "марка",
                                            "few": "марки", "many": "марок", "short": "ṃ"}


# ---------------------------------------------------------------------------
# Tax
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("amount,rate,expected", [
    (155, Decimal("0.1"), 15),
    (9, Decimal("0.1"), 0),
    (10, Decimal("0.1"), 1),
    (19, "0.1", 1),
    (25, 0.1, 2),               # floor(2.5)
    (30, 0.1, 3),               # float 0.1 * 30 = 3.0000000000000004 -> still 3
    (100, 0.29, 29),            # float 0.29 * 100 = 28.999999999999996 -> Decimal keeps 29
    (3, Decimal("0.5"), 1),
    (100, 0, 0),
    (100, Decimal("-0.1"), 0),
    (1, Decimal("0.5"), 0),
])
def test_tax_amount_floors(amount, rate, expected):
    assert core.tax_amount(amount, rate) == expected


def test_add_tax_legs_only_for_taxable_inflows_into_regions():
    legs = [
        Leg(C1, R10, 155),                       # taxable (character -> region)
        Leg(ESCROW, R10, 25, "commission"),      # taxable (escrow -> region)
        Leg(STORAGE, R10, 10),                   # taxable (storage -> region)
        Leg(WORLD, R10, 100),                    # world -> region: not taxable
        Leg(R10, C2, 40),                        # payout: not an inflow
        Leg(C1, WORLD, 100),                     # world treasury: no country above it
        Leg(C1, R20, 50),                        # region without a known country -> no tax
    ]
    out = core.add_tax_legs(legs, Decimal("0.1"), {10: 1})
    assert out == [
        Leg(C1, R10, 155), Leg(R10, K1, 15, core.LEG_TAX),
        Leg(ESCROW, R10, 25, "commission"), Leg(R10, K1, 2, core.LEG_TAX),
        Leg(STORAGE, R10, 10), Leg(R10, K1, 1, core.LEG_TAX),
        Leg(WORLD, R10, 100),
        Leg(R10, C2, 40),
        Leg(C1, WORLD, 100),
        Leg(C1, R20, 50),
    ]


def test_tax_leg_dropped_when_rounded_to_zero():
    assert core.add_tax_legs([Leg(C1, R10, 9)], Decimal("0.1"), {10: 1}) == [Leg(C1, R10, 9)]


def test_tax_region_ids():
    legs = [Leg(C1, R20, 5), Leg(C1, R10, 5), Leg(WORLD, R10, 5), Leg(ESCROW, R20, 1)]
    assert core.tax_region_ids(legs) == [10, 20]
    assert core.tax_region_ids([Leg(WORLD, R10, 5)]) == []
    assert core.tax_region_ids(legs, apply_tax=False) == []


def test_plan_operation_adds_tax_and_respects_apply_tax_false():
    plan = core.plan_operation("teleport", [Leg(C1, R10, 100)], source_service=SRC,
                               tax_rate=Decimal("0.2"), region_countries={10: 1})
    assert plan.legs == (Leg(C1, R10, 100), Leg(R10, K1, 20, core.LEG_TAX))
    assert plan.deltas == {C1: -100, R10: 80, K1: 20}

    plan = core.plan_operation("teleport", [Leg(C1, R10, 100)], source_service=SRC, apply_tax=False,
                               tax_rate=Decimal("0.2"), region_countries={10: 1})
    assert plan.legs == (Leg(C1, R10, 100),)


# ---------------------------------------------------------------------------
# Netting / order
# ---------------------------------------------------------------------------

def test_net_deltas_sums_per_account():
    deltas = core.net_deltas([Leg(C1, C2, 70), Leg(C2, C1, 30), Leg(C1, R10, 5)])
    assert deltas == {C1: -45, C2: 40, R10: 5}


def test_plan_accounts_and_character_ids_sorted():
    plan = core.plan_operation("trade", [Leg(C5, C2, 10), Leg(C2, C1, 3)], source_service=SRC)
    assert plan.accounts == [C1, C2, C5]
    assert plan.character_ids == [1, 2, 5]


def test_apply_steps_characters_first_ascending_then_accounts_by_id_skipping_zero():
    plan = core.plan_operation(
        "auction_buyout",
        [Leg(C5, ESCROW, 500), Leg(ESCROW, C2, 200, "refund"), Leg(ESCROW, STORAGE, 275),
         Leg(ESCROW, R10, 25, "commission"), Leg(C1, C5, 7), Leg(C5, C1, 7)],
        source_service=SRC, tax_rate=Decimal("0.1"), region_countries={10: 1},
    )
    # escrow nets to 0 (500 in, 500 out) and C1 nets to 0 -> neither row is touched.
    account_ids = {ESCROW: 4, STORAGE: 5, R10: 30, K1: 12, C1: 90, C2: 91, C5: 92}
    steps = core.apply_steps(plan, account_ids)
    assert [(s.target, s.row_id, s.delta) for s in steps] == [
        ("character", 2, 200),
        ("character", 5, -500),
        ("account", 5, 275),       # storage
        ("account", 12, 2),        # country (tax)
        ("account", 30, 23),       # region: 25 - 2 tax
    ]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

NON_SOURCE_OPS = sorted(core.OP_TYPES - core.SOURCE_OP_TYPES)


@pytest.mark.parametrize("op_type", NON_SOURCE_OPS)
@pytest.mark.parametrize("leg", [Leg(EMISSION, C1, 5), Leg(C1, EMISSION, 5),
                                 Leg(ADJUSTMENT, R10, 5), Leg(WORLD, ADJUSTMENT, 5)])
def test_no_money_creation_outside_admin_ops(op_type, leg):
    with pytest.raises(core.EconomyError):
        core.validate_operation(op_type, [leg], source_service=SRC, comment="x")


@pytest.mark.parametrize("op_type", sorted(core.SOURCE_OP_TYPES))
def test_source_accounts_allowed_for_genesis_and_admin_ops(op_type):
    kept = core.validate_operation(op_type, [Leg(EMISSION, C1, 5), Leg(C2, ADJUSTMENT, 1)],
                                   source_service=SRC, comment="ok")
    assert len(kept) == 2


@pytest.mark.parametrize("op_type", sorted(core.COMMENT_REQUIRED_OP_TYPES))
@pytest.mark.parametrize("comment", [None, "", "   "])
def test_admin_ops_require_comment(op_type, comment):
    with pytest.raises(core.EconomyError):
        core.validate_operation(op_type, [Leg(EMISSION, R10, 5)], source_service=SRC, comment=comment)


@pytest.mark.parametrize("legs,kwargs", [
    ([Leg(C1, R10, 5)], {"op_type": "unknown_op"}),
    ([Leg(AccountRef("bank", 1), R10, 5)], {}),                     # unknown kind
    ([Leg(AccountRef(core.KIND_WORLD_TREASURY, 3), C1, 5)], {}),    # singleton with ref_id
    ([Leg(AccountRef.character(0), R10, 5)], {}),                   # ref kind needs ref_id > 0
    ([Leg(AccountRef(core.KIND_CHARACTER, -4), R10, 5)], {}),
    ([Leg(AccountRef(core.KIND_CHARACTER, True), R10, 5)], {}),     # bool is not an id
    ([Leg(C1, R10, True)], {}),                                      # bool is not an amount
    ([Leg(C1, R10, 5.0)], {}),                                       # float amount
    ([Leg(C1, R10, "5")], {}),                                       # str amount
    ([Leg(C1, R10, -1)], {}),
    ([Leg(C1, R10, core.MAX_AMOUNT + 1)], {}),
    ([Leg(C1, R10, 5, core.LEG_TAX)], {}),                          # tax legs are generated only
    ([Leg(C1, R10, 5, "bonus")], {}),
    ([Leg(C1, C1, 5)], {}),                                          # src == dst
    ([("C1", "R10", 5)], {}),                                        # not a Leg
    ([Leg("character:1", R10, 5)], {}),                              # not an AccountRef
    ([Leg(C1, R10, 5)], {"source_service": ""}),
    ([Leg(C1, R10, 5)], {"source_service": "x" * 33}),
    ([Leg(C1, R10, 5)], {"comment": "x" * 501}),
    ([Leg(C1, R10, 5)], {"idempotency_key": ""}),
    ([Leg(C1, R10, 5)], {"idempotency_key": "k" * 129}),
    ([Leg(C1, R10, 5)], {"idempotency_key": 42}),
])
def test_validation_rejects(legs, kwargs):
    params = {"op_type": "teleport", "source_service": SRC, **kwargs}
    op_type = params.pop("op_type")
    with pytest.raises(core.EconomyError):
        core.validate_operation(op_type, legs, **params)


def test_validation_accepts_boundaries_and_drops_zero_legs():
    kept = core.validate_operation(
        "trade", [Leg(C1, C2, core.MAX_AMOUNT), Leg(C2, C1, 0)],
        source_service="x" * 32, comment="x" * 500, idempotency_key="k" * 128,
    )
    assert kept == [Leg(C1, C2, core.MAX_AMOUNT)]


def test_plan_returns_none_when_every_leg_is_zero():
    assert core.plan_operation("battle_reward", [Leg(WORLD, C1, 0)], source_service=SRC) is None
    assert core.plan_operation("battle_reward", [], source_service=SRC) is None


def test_zero_leg_still_validated():
    """A 0 leg is dropped, but only after validation — emission in a 0 leg is still rejected."""
    with pytest.raises(core.EconomyError):
        core.validate_operation("quest_reward", [Leg(EMISSION, C1, 0)], source_service=SRC)


# ---------------------------------------------------------------------------
# Value objects / exceptions
# ---------------------------------------------------------------------------

def test_account_ref_constructors_and_flags():
    assert AccountRef.character("7") == AccountRef(core.KIND_CHARACTER, 7)
    assert [r.kind for r in (WORLD, ESCROW, STORAGE, EMISSION, ADJUSTMENT)] == [
        "world_treasury", "auction_escrow", "auction_storage", "emission", "adjustment"]
    assert all(r.ref_id == 0 for r in (WORLD, ESCROW, STORAGE, EMISSION, ADJUSTMENT))
    assert R10.allow_negative and K1.allow_negative and WORLD.allow_negative
    assert EMISSION.allow_negative and ADJUSTMENT.allow_negative
    assert not C1.allow_negative and not ESCROW.allow_negative and not STORAGE.allow_negative
    assert C1.is_character and not R10.is_character


def test_exceptions_carry_details():
    exc = core.InsufficientFunds(C1, 50)
    assert isinstance(exc, core.EconomyError)
    assert exc.account == C1 and exc.needed == 50
    dup = core.DuplicateOperation(77)
    assert isinstance(dup, core.EconomyError) and dup.operation_id == 77


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

def test_in_params_and_lock_sql():
    placeholders, params = core.in_params("c", [3, 1])
    assert placeholders == ":c0, :c1" and params == {"c0": 3, "c1": 1}
    assert core.sql_lock_characters(placeholders, True).endswith("ORDER BY id FOR UPDATE")
    assert "FOR UPDATE" not in core.sql_lock_characters(placeholders, False)
    assert core.supports_for_update("mysql") and not core.supports_for_update("sqlite")


def test_conditional_balance_sql():
    """Debits are conditional (no negative characters / non-negative accounts)."""
    assert "currency_balance >= :amount" in core.SQL_DEBIT_CHARACTER
    assert "allow_negative = 1 OR balance + :delta >= 0" in core.SQL_APPLY_ACCOUNT


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def test_settings_from_row():
    assert core.settings_from_row(None) == core.DEFAULT_SETTINGS
    s = core.settings_from_row(("Крона", "крон", "крона", "кроны", "крон", "кр.", Decimal("0.2500")))
    assert s.forms.name == "Крона" and s.country_tax_rate == Decimal("0.25")
    # empty strings fall back to defaults; out-of-range rates are clamped
    s = core.settings_from_row(("", None, "", "", "", "", Decimal("0.9")))
    assert s.forms == core.DEFAULT_FORMS and s.country_tax_rate == core.MAX_COUNTRY_TAX_RATE
    assert core.settings_from_row(("a", "b", "c", "d", "e", "f", -1)).country_tax_rate == 0
    assert core.settings_from_row(("a", "b", "c", "d", "e", "f", None)).country_tax_rate == Decimal("0.1")


def test_settings_cache_ttl():
    core.invalidate_settings_cache()
    try:
        assert core.cached_settings(now=0.0) is None
        value = core.EconomySettings(forms=core.DEFAULT_FORMS, country_tax_rate=Decimal("0.3"))
        core.store_settings(value, now=100.0)
        assert core.cached_settings(now=100.0 + core.SETTINGS_TTL_SECONDS - 1) is value
        assert core.cached_settings(now=100.0 + core.SETTINGS_TTL_SECONDS) is None
        core.store_settings(value, now=100.0)
        core.invalidate_settings_cache()
        assert core.cached_settings(now=100.0) is None
    finally:
        core.invalidate_settings_cache()
