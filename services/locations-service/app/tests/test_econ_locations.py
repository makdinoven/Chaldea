"""FEAT-181: locations-service money wrappers over the async ledger (replace the old
deduct_currency / add_currency / _log_gold_transaction and their gold_transactions tests).

Real aiosqlite with the contract DDL + seed (econ_contract_cases): region 10 (country 1) holds
location 1000, region 20 (country 2) holds 1001, location 1003 has no region (world treasury).
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

import crud  # noqa: E402
import econ_core  # noqa: E402
import econ_ledger  # noqa: E402
import econ_contract_cases as cc  # noqa: E402
from econ_core import AccountRef  # noqa: E402


@pytest.fixture()
async def db(tmp_path):
    econ_core.invalidate_settings_cache()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'loc_econ.db'}", poolclass=NullPool)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        for ddl in cc.SQLITE_DDL:
            await s.execute(text(ddl))
        for sql, params in cc.SEED_SQL:
            await s.execute(text(sql), params)
        await s.commit()
        await econ_ledger.post_operation(
            s, op_type="admin_emission", legs=[econ_core.Leg(AccountRef.emission(), AccountRef.character(1), 1000)],
            source_service="test", comment="seed", apply_tax=False)
        await s.commit()
    async with Session() as s:
        yield s
    await engine.dispose()


async def _one(s, sql, **p):
    return (await s.execute(text(sql), p)).first()[0]


async def _account(s, kind, ref_id=0):
    row = (await s.execute(text(cc.ACCOUNT_BALANCE_SQL), {"kind": kind, "ref_id": ref_id})).first()
    return None if row is None else row[0]


async def _world_sum(s):
    return await _one(s, cc.WORLD_SUM_SQL)


async def test_charge_goes_to_the_location_region_with_tax(db):
    balance = await crud.charge_character(db, 1, 200, op_type="npc_shop_buy", location_id=1000,
                                          metadata={"npc_id": 5})
    await db.commit()
    assert balance == 800
    assert await _account(db, "region_treasury", 10) == 180
    assert await _account(db, "country_treasury", 1) == 20
    row = (await db.execute(text("SELECT op_type, location_id, region_id, source_service FROM econ_operations "
                                 "ORDER BY id DESC LIMIT 1"))).first()
    assert tuple(row) == ("npc_shop_buy", 1000, 10, "locations-service")
    assert await _world_sum(db) == 0


async def test_charge_prefers_the_explicit_region(db):
    await crud.charge_character(db, 1, 100, op_type="house_tax", location_id=1000, region_id=20)
    await db.commit()
    assert await _account(db, "region_treasury", 20) == 90
    assert await _account(db, "region_treasury", 10) is None


async def test_charge_without_enough_gold_moves_nothing(db):
    assert await crud.charge_character(db, 1, 1001, op_type="house_build", location_id=1000) is None
    await db.rollback()
    assert await _one(db, "SELECT currency_balance FROM characters WHERE id = 1") == 1000
    assert await _one(db, "SELECT COUNT(*) FROM econ_operations") == 1  # only the seed


async def test_zero_charge_returns_the_balance_and_posts_nothing(db):
    assert await crud.charge_character(db, 1, 0, op_type="house_tax", location_id=1000) == 1000
    assert await _one(db, "SELECT COUNT(*) FROM econ_operations") == 1


async def test_pay_from_a_place_without_region_uses_the_world_treasury(db):
    assert await crud.pay_character(db, 2, 50, op_type="npc_shop_sell", location_id=1003) == 50
    await db.commit()
    assert await _account(db, "world_treasury") == -50
    assert await _world_sum(db) == 0


async def test_quest_reward_key_pays_once(db):
    key = "quest_reward:cq:7"
    await crud.pay_character(db, 2, 30, op_type="quest_reward", location_id=1001, idempotency_key=key)
    await db.commit()
    with pytest.raises(econ_ledger.DuplicateOperation):
        await crud.pay_character(db, 2, 30, op_type="quest_reward", location_id=1001, idempotency_key=key)
    await db.rollback()
    assert await _one(db, "SELECT currency_balance FROM characters WHERE id = 2") == 30
    assert await _account(db, "region_treasury", 20) == -30


async def test_house_resale_is_one_operation_between_players(db):
    balance = await crud.transfer_between_characters(db, 1, 3, 400, op_type="house_resale", location_id=1000,
                                                     metadata={"house_id": 1})
    await db.commit()
    assert balance == 600
    assert await _one(db, "SELECT currency_balance FROM characters WHERE id = 3") == 400
    assert await _one(db, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'house_resale'") == 1
    assert await _one(db, "SELECT COUNT(*) FROM econ_postings WHERE leg_type = 'tax'") == 0


async def test_house_resale_without_gold_moves_nothing(db):
    assert await crud.transfer_between_characters(db, 2, 3, 1, op_type="house_resale") is None
    await db.rollback()
    assert await _one(db, "SELECT currency_balance FROM characters WHERE id = 3") == 0


async def test_closing_region_and_country_treasuries(db):
    # region 10 gets +180 (and its country +20); region 20 goes to -40
    await crud.charge_character(db, 1, 200, op_type="npc_shop_buy", location_id=1000)
    await crud.pay_character(db, 2, 40, op_type="npc_shop_sell", location_id=1001)
    await db.commit()

    await crud._close_treasury(db, AccountRef.region(10), AccountRef.country(1), {"region_id": 10})
    await crud._close_treasury(db, AccountRef.country(1), AccountRef.world(), {"country_id": 1})
    await crud._close_treasury(db, AccountRef.region(20), AccountRef.country(2), {"region_id": 20})
    await db.commit()

    assert await _account(db, "region_treasury", 10) == 0
    assert await _account(db, "country_treasury", 1) == 0
    assert await _account(db, "world_treasury") == 200
    assert await _account(db, "region_treasury", 20) == 0
    assert await _account(db, "country_treasury", 2) == -40
    inactive = (await db.execute(text(
        "SELECT kind, ref_id FROM econ_accounts WHERE is_active = 0 ORDER BY kind, ref_id"))).fetchall()
    assert [tuple(r) for r in inactive] == [("country_treasury", 1), ("region_treasury", 10), ("region_treasury", 20)]
    assert await _one(db, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'treasury_closed'") == 3
    assert await _world_sum(db) == 0


async def test_closing_an_untouched_treasury_posts_nothing(db):
    await crud._close_treasury(db, AccountRef.region(20), AccountRef.country(2), {"region_id": 20})
    assert await _one(db, "SELECT COUNT(*) FROM econ_operations WHERE op_type = 'treasury_closed'") == 0


async def test_messages_use_the_configured_currency(db):
    await db.execute(text("UPDATE econ_settings SET currency_genitive = 'серебра', currency_one = 'серебряк', "
                          "currency_few = 'серебряка', currency_many = 'серебряков'"))
    await db.commit()
    econ_core.invalidate_settings_cache()
    try:
        assert await crud.not_enough_gold_message(db) == "Не хватает серебра"
        assert await crud.format_gold(db, 3) == "3 серебряка"
    finally:
        econ_core.invalidate_settings_cache()


async def test_npc_buy_refund_restores_region_and_country_exactly(db):
    before_region = await _account(db, "region_treasury", 10) or 0
    before_country = await _account(db, "country_treasury", 1) or 0
    balance, op_id = await crud.charge_character_op(db, 1, 155, op_type="npc_shop_buy", location_id=1000)
    await db.commit()
    assert balance == 845
    assert await _account(db, "country_treasury", 1) == before_country + 15  # tax leg was taken

    await crud.reverse_operation(db, op_id, op_type="npc_shop_buy_refund", metadata={"reason": "test"})
    await db.commit()

    assert await _one(db, "SELECT currency_balance FROM characters WHERE id = 1") == 1000
    assert await _account(db, "region_treasury", 10) == before_region
    assert await _account(db, "country_treasury", 1) == before_country
    legs = (await db.execute(text(
        "SELECT p.leg_type, COUNT(*) FROM econ_postings p JOIN econ_operations o ON o.id = p.operation_id "
        "WHERE o.op_type = 'npc_shop_buy_refund' GROUP BY p.leg_type"))).fetchall()
    assert [tuple(r) for r in legs] == [("refund", 2)]
    assert await _world_sum(db) == 0
