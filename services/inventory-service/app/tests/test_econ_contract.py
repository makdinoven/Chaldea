"""FEAT-181: the shared ledger contract (econ_contract_cases) run through inventory-service's
SYNC executor (a byte-identical copy of character-service's econ_ledger).

Each case gets a fresh in-memory SQLite laid out with SQLITE_DDL + SEED_SQL, independent of
the service's ORM tables, so the contract is checked exactly as the other services check it.
"""

import os
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import econ_core  # noqa: E402
import econ_ledger  # noqa: E402
import econ_contract_cases as cc  # noqa: E402


@pytest.fixture()
def contract_db():
    """Fresh SQLite world per test; yields a session factory."""
    econ_core.invalidate_settings_cache()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    s = Session()
    for ddl in cc.SQLITE_DDL:
        s.execute(text(ddl))
    for sql, params in cc.SEED_SQL:
        s.execute(text(sql), params)
    s.commit()
    s.close()
    try:
        yield Session
    finally:
        econ_core.invalidate_settings_cache()
        engine.dispose()


def _scalar(Session, sql, **params):
    s = Session()
    try:
        row = s.execute(text(sql), params).first()
        return None if row is None else row[0]
    finally:
        s.close()


@pytest.mark.parametrize("case", cc.CASES, ids=[c.name for c in cc.CASES])
def test_contract_case(case, contract_db):
    Session = contract_db
    for step in case.steps:
        s = Session()
        try:
            if step.error is None:
                econ_ledger.post_operation(s, op_type=step.op_type, legs=step.legs,
                                           source_service=cc.SOURCE_SERVICE, **step.kwargs)
                s.commit()
            else:
                with pytest.raises(getattr(econ_core, step.error)):
                    econ_ledger.post_operation(s, op_type=step.op_type, legs=step.legs,
                                               source_service=cc.SOURCE_SERVICE, **step.kwargs)
                s.rollback()
        finally:
            s.close()

    for cid, expected in case.expected_characters.items():
        assert _scalar(Session, cc.CHARACTER_BALANCE_SQL, id=cid) == expected, cid
    for (kind, ref_id), expected in case.expected_accounts.items():
        assert _scalar(Session, cc.ACCOUNT_BALANCE_SQL, kind=kind, ref_id=ref_id) == expected, (kind, ref_id)
    if case.expected_operations is not None:
        assert _scalar(Session, cc.OPERATION_COUNT_SQL) == case.expected_operations
    if case.expected_postings is not None:
        assert _scalar(Session, cc.POSTING_COUNT_SQL) == case.expected_postings
    if case.expected_tax_legs is not None:
        assert _scalar(Session, cc.TAX_LEG_COUNT_SQL) == case.expected_tax_legs
    assert _scalar(Session, cc.WORLD_SUM_SQL) == 0


@pytest.mark.parametrize("location_id,expected", cc.RESOLVE_CASES)
def test_resolve_location(location_id, expected, contract_db):
    s = contract_db()
    try:
        assert econ_ledger.resolve_location(s, location_id) == expected
        region_id = expected[0]
        assert econ_ledger.treasury_for_location(s, location_id) == (
            econ_core.AccountRef.region(region_id) if region_id else econ_core.AccountRef.world()
        )
    finally:
        s.close()


@pytest.mark.parametrize("n,expected", cc.PLURAL_CASES)
def test_plural(n, expected):
    assert econ_core.plural_ru(n, "a", "b", "c") == expected


@pytest.mark.parametrize("n,short,expected", cc.FORMAT_CASES)
def test_format(n, short, expected):
    assert econ_core.format_currency(n, econ_core.DEFAULT_FORMS, short=short) == expected


def test_currency_forms_read_from_settings(contract_db):
    s = contract_db()
    try:
        s.execute(text("UPDATE econ_settings SET currency_genitive = 'серебра'"))
        s.commit()
        econ_core.invalidate_settings_cache()
        assert econ_ledger.get_currency_forms(s).genitive == "серебра"
    finally:
        s.close()


def test_lock_characters_and_accounts(contract_db):
    s = contract_db()
    try:
        assert econ_ledger.lock_characters(s, [3, 1, 1]) == {1: 0, 3: 0}
        a = econ_ledger.get_or_create_account(s, econ_core.AccountRef.region(10))
        assert econ_ledger.get_or_create_account(s, econ_core.AccountRef.region(10)) == a
        econ_ledger.deactivate_account(s, econ_core.AccountRef.region(10))
        row = s.execute(text("SELECT name, is_active, allow_negative FROM econ_accounts WHERE id = :i"),
                        {"i": a}).first()
        assert tuple(row) == ("Region A1", 0, 1)
    finally:
        s.close()


def test_contract_files_are_the_shared_copies():
    """The copies must stay byte-identical to character-service's canonicals (CI checks the hashes);
    here we only guard that the inventory copies still carry the canonical markers."""
    here = os.path.dirname(__file__)
    with open(os.path.join(here, "econ_contract_cases.py"), encoding="utf-8") as fh:
        assert "CANONICAL COPY: services/character-service/app/tests/econ_contract_cases.py" in fh.read()
    with open(os.path.join(here, "..", "econ_ledger.py"), encoding="utf-8") as fh:
        assert "CANONICAL SYNC COPY: services/character-service/app/econ_ledger.py" in fh.read()
