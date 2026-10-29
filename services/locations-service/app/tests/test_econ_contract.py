"""FEAT-181: the shared ledger contract (econ_contract_cases) run through the ASYNC executor.

Each case gets a fresh file-backed SQLite (aiosqlite) laid out with SQLITE_DDL + SEED_SQL.
"""

import os
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import econ_core  # noqa: E402
import econ_ledger  # noqa: E402
import econ_contract_cases as cc  # noqa: E402


async def _make_db(path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        for ddl in cc.SQLITE_DDL:
            await s.execute(text(ddl))
        for sql, params in cc.SEED_SQL:
            await s.execute(text(sql), params)
        await s.commit()
    return engine, Session


async def _scalar(Session, sql, **params):
    async with Session() as s:
        row = (await s.execute(text(sql), params)).first()
        return None if row is None else row[0]


@pytest.mark.parametrize("case", cc.CASES, ids=[c.name for c in cc.CASES])
async def test_contract_case(case, tmp_path):
    econ_core.invalidate_settings_cache()

    engine, Session = await _make_db(tmp_path / "econ.db")
    try:
        for step in case.steps:
            async with Session() as s:
                if step.error is None:
                    await econ_ledger.post_operation(
                        s, op_type=step.op_type, legs=step.legs,
                        source_service=cc.SOURCE_SERVICE, **step.kwargs)
                    await s.commit()
                else:
                    with pytest.raises(getattr(econ_core, step.error)):
                        await econ_ledger.post_operation(
                            s, op_type=step.op_type, legs=step.legs,
                            source_service=cc.SOURCE_SERVICE, **step.kwargs)
                    await s.rollback()

        for cid, expected in case.expected_characters.items():
            assert await _scalar(Session, cc.CHARACTER_BALANCE_SQL, id=cid) == expected, cid
        for (kind, ref_id), expected in case.expected_accounts.items():
            assert await _scalar(Session, cc.ACCOUNT_BALANCE_SQL, kind=kind, ref_id=ref_id) == expected, kind
        if case.expected_operations is not None:
            assert await _scalar(Session, cc.OPERATION_COUNT_SQL) == case.expected_operations
        if case.expected_postings is not None:
            assert await _scalar(Session, cc.POSTING_COUNT_SQL) == case.expected_postings
        if case.expected_tax_legs is not None:
            assert await _scalar(Session, cc.TAX_LEG_COUNT_SQL) == case.expected_tax_legs
        for leg_type, expected in case.expected_leg_counts.items():
            assert await _scalar(Session, cc.LEG_TYPE_COUNT_SQL, leg_type=leg_type) == expected, leg_type
        assert await _scalar(Session, cc.WORLD_SUM_SQL) == 0
    finally:
        await engine.dispose()


@pytest.mark.parametrize("location_id,expected", cc.RESOLVE_CASES)
async def test_resolve_location(location_id, expected, tmp_path):
    engine, Session = await _make_db(tmp_path / "econ.db")
    try:
        async with Session() as s:
            assert await econ_ledger.resolve_location(s, location_id) == expected
            ref = await econ_ledger.treasury_for_location(s, location_id)
            region_id = expected[0]
            assert ref == (econ_core.AccountRef.region(region_id) if region_id else econ_core.AccountRef.world())
    finally:
        await engine.dispose()


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


async def test_currency_forms_read_from_settings(tmp_path):
    econ_core.invalidate_settings_cache()

    engine, Session = await _make_db(tmp_path / "econ.db")
    try:
        async with Session() as s:
            await s.execute(text("UPDATE econ_settings SET currency_genitive = 'серебра'"))
            await s.commit()
        async with Session() as s:
            forms = await econ_ledger.get_currency_forms(s)
            assert forms.genitive == "серебра"
    finally:
        econ_core.invalidate_settings_cache()
        await engine.dispose()


async def test_lock_characters_and_accounts(tmp_path):
    engine, Session = await _make_db(tmp_path / "econ.db")
    try:
        async with Session() as s:
            assert await econ_ledger.lock_characters(s, [3, 1, 1]) == {1: 0, 3: 0}
            a = await econ_ledger.get_or_create_account(s, econ_core.AccountRef.region(10))
            assert await econ_ledger.get_or_create_account(s, econ_core.AccountRef.region(10)) == a
            await econ_ledger.deactivate_account(s, econ_core.AccountRef.region(10))
            row = (await s.execute(text("SELECT name, is_active, allow_negative FROM econ_accounts WHERE id = :i"),
                                   {"i": a})).first()
            assert tuple(row) == ("Region A1", 0, 1)
    finally:
        await engine.dispose()


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


async def _make_merchant_db(path):
    """FEAT-183 merchant SQL smoke world (its own SQLite, see econ_contract_cases)."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        for ddl in cc.MERCHANT_SQLITE_DDL:
            await s.execute(text(ddl))
        for sql, params in cc.MERCHANT_SEED_SQL:
            await s.execute(text(sql), params)
        await s.commit()
    return engine, Session


@pytest.mark.parametrize("name,sql,params,convert,expected", cc.MERCHANT_QUERY_CASES,
                         ids=[c[0] for c in cc.MERCHANT_QUERY_CASES])
async def test_merchant_sql(name, sql, params, convert, expected, tmp_path):
    engine, Session = await _make_merchant_db(tmp_path / "merchant.db")
    try:
        async with Session() as s:
            rows = [tuple(r) for r in (await s.execute(text(sql), params)).fetchall()]
            assert convert(rows) == expected
    finally:
        await engine.dispose()


async def test_merchant_status_from_sql(tmp_path):
    engine, Session = await _make_merchant_db(tmp_path / "merchant.db")
    try:
        async with Session() as s:
            for npc_id, expected in cc.MERCHANT_STATUS_SQL_CASES:
                npc = (await s.execute(text(econ_core.SQL_NPC_PLACE), {"id": npc_id})).first()
                region_id = (await econ_ledger.resolve_location(s, npc[3] if npc else None))[0]
                region = ((await s.execute(text(econ_core.SQL_REGION_ECON), {"region_id": region_id})).first()
                          if region_id else None)
                assert econ_core.merchant_status(npc, region) == expected, npc_id
    finally:
        await engine.dispose()


async def test_merchant_shop_stock_statements(tmp_path):
    engine, Session = await _make_merchant_db(tmp_path / "merchant.db")
    try:
        async with Session() as s:
            for sql, params, rowcount in cc.MERCHANT_STOCK_STEPS:
                assert (await s.execute(text(sql), params)).rowcount == rowcount, (sql, params)
            await s.commit()
            rows = (await s.execute(text(cc.MERCHANT_STOCK_SQL))).fetchall()
            assert dict(rows) == cc.MERCHANT_STOCK_EXPECTED
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------------------------- FEAT-184 banks

@pytest.mark.parametrize("kind,region_scoped,negative,taxed", cc.BANK_KIND_CASES,
                         ids=[c[0] for c in cc.BANK_KIND_CASES])
def test_bank_account_kinds(kind, region_scoped, negative, taxed):
    assert kind in econ_core.ACCOUNT_KINDS
    assert (kind in econ_core.REF_KINDS) is region_scoped
    assert (kind in econ_core.NEGATIVE_ALLOWED_KINDS) is negative
    assert (kind in econ_core.TAX_SOURCE_KINDS) is taxed
    assert kind not in econ_core.SOURCE_KINDS
    assert kind in econ_core.SQL_ACCOUNT_NAME
    factory = econ_core.AccountRef.bank if kind == econ_core.KIND_BANK else econ_core.AccountRef.bank_deposits
    assert factory(7) == econ_core.AccountRef(kind, 7)
    assert not factory(7).allow_negative


def test_bank_op_types_and_interest_leg():
    assert frozenset(cc.BANK_OP_TYPE_NAMES) == econ_core.BANK_OP_TYPES
    assert econ_core.BANK_OP_TYPES <= econ_core.OP_TYPES
    assert not econ_core.BANK_OP_TYPES & econ_core.SOURCE_OP_TYPES
    assert econ_core.LEG_INTEREST in econ_core.LEG_TYPES
    assert econ_core.LEG_INTEREST in econ_core.CALLER_LEG_TYPES
