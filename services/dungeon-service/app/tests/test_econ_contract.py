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
