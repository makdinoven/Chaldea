"""FEAT-181 Q1: the shared ledger contract (econ_contract_cases) run through character-service's
SYNC executor — the canonical econ_ledger.py.

Each test gets a fresh in-memory SQLite laid out with SQLITE_DDL + SEED_SQL, independent of the
service's ORM tables, exactly as inventory-, locations- and dungeon-service run the same cases.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import econ_core
import econ_ledger
from tests import econ_contract_cases as cc


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
    for leg_type, expected in case.expected_leg_counts.items():
        assert _scalar(Session, cc.LEG_TYPE_COUNT_SQL, leg_type=leg_type) == expected, leg_type
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


@pytest.mark.parametrize("args,expected", cc.ITEM_GROUP_CASES)
def test_auto_item_group(args, expected):
    group, off_market = econ_core.auto_item_group(*args)
    assert (group, off_market) == expected
    assert group is None or group in econ_core.GOODS_GROUPS


def test_currency_forms_read_from_settings(contract_db):
    s = contract_db()
    try:
        s.execute(text("UPDATE econ_settings SET currency_genitive = 'серебра'"))
        s.commit()
        econ_core.invalidate_settings_cache()
        assert econ_ledger.get_currency_forms(s).genitive == "серебра"
    finally:
        s.close()


def test_contract_cases_is_the_canonical_copy():
    """character-service holds the canonical copies; CI compares the hashes of the others to these."""
    here = os.path.dirname(__file__)
    with open(os.path.join(here, "econ_contract_cases.py"), encoding="utf-8") as fh:
        assert "CANONICAL COPY: services/character-service/app/tests/econ_contract_cases.py" in fh.read()
    with open(os.path.join(here, "..", "econ_core.py"), encoding="utf-8") as fh:
        assert "CANONICAL COPY: services/character-service/app/econ_core.py" in fh.read()
    with open(os.path.join(here, "..", "econ_ledger.py"), encoding="utf-8") as fh:
        assert "CANONICAL SYNC COPY: services/character-service/app/econ_ledger.py" in fh.read()


# --------------------------------------------------------------------------------------------- FEAT-183 merchants

@pytest.mark.parametrize("name,args,expected", cc.PRICING_CASES,
                         ids=[f"{c[0]}-{i}" for i, c in enumerate(cc.PRICING_CASES)])
def test_merchant_pricing(name, args, expected):
    assert getattr(econ_core, name)(*args) == expected


@pytest.mark.parametrize("args,expected", cc.EFFECTIVE_GROUP_CASES)
def test_effective_item_group(args, expected):
    assert econ_core.effective_item_group(*args) == expected


@pytest.mark.parametrize("args,expected", cc.ITEM_GROUP_CASES)
def test_effective_item_group_without_override_follows_auto_rule(args, expected):
    group, off_market = expected
    assert econ_core.effective_item_group(*args) == (group, off_market or group is None)


@pytest.mark.parametrize("npc_row,region_row,expected", cc.MERCHANT_STATUS_CASES)
def test_merchant_status(npc_row, region_row, expected):
    assert econ_core.merchant_status(npc_row, region_row) == expected
    assert expected[1] is None or expected[1] in econ_core.MERCHANT_LEGACY_REASONS


def test_merchant_bid_never_beats_the_cheapest_ask():
    best_pct = econ_core.charisma_discount_pct(10 ** 6)
    for base_ask, base_bid, mult in cc.BID_CAP_GRID:
        ask = econ_core.market_ask(base_ask, mult)
        bid = econ_core.market_bid(base_bid, mult, ask)
        assert 0 <= bid <= econ_core.discounted_ask(ask, best_pct), (base_ask, base_bid, mult)
        assert 2 * bid <= ask, (base_ask, base_bid, mult)


@pytest.fixture()
def merchant_db():
    """FEAT-183 merchant SQL smoke world (its own SQLite, see econ_contract_cases)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    s = Session()
    for ddl in cc.MERCHANT_SQLITE_DDL:
        s.execute(text(ddl))
    for sql, params in cc.MERCHANT_SEED_SQL:
        s.execute(text(sql), params)
    s.commit()
    s.close()
    try:
        yield Session
    finally:
        engine.dispose()


@pytest.mark.parametrize("name,sql,params,convert,expected", cc.MERCHANT_QUERY_CASES,
                         ids=[c[0] for c in cc.MERCHANT_QUERY_CASES])
def test_merchant_sql(name, sql, params, convert, expected, merchant_db):
    s = merchant_db()
    try:
        rows = [tuple(r) for r in s.execute(text(sql), params).fetchall()]
        assert convert(rows) == expected
    finally:
        s.close()


@pytest.mark.parametrize("npc_id,expected", cc.MERCHANT_STATUS_SQL_CASES)
def test_merchant_status_from_sql(npc_id, expected, merchant_db):
    s = merchant_db()
    try:
        npc = s.execute(text(econ_core.SQL_NPC_PLACE), {"id": npc_id}).first()
        region_id = econ_ledger.resolve_location(s, npc[3] if npc else None)[0]
        region = (s.execute(text(econ_core.SQL_REGION_ECON), {"region_id": region_id}).first()
                  if region_id else None)
        assert econ_core.merchant_status(npc, region) == expected
    finally:
        s.close()


def test_merchant_shop_stock_statements(merchant_db):
    s = merchant_db()
    try:
        for sql, params, rowcount in cc.MERCHANT_STOCK_STEPS:
            assert s.execute(text(sql), params).rowcount == rowcount, (sql, params)
        s.commit()
        assert dict(s.execute(text(cc.MERCHANT_STOCK_SQL)).fetchall()) == cc.MERCHANT_STOCK_EXPECTED
    finally:
        s.close()
