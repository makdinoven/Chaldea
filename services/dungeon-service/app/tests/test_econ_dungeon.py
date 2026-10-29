"""FEAT-181 B6: dungeon gold through the REAL async ledger (econ_ledger) on SQLite.

Rest / revive / merchant (`dungeon_expense`: character -> treasury of the dungeon's region)
and event gold (`dungeon_reward`: treasury -> leader) are posted in the same transaction as
the session change; a failed dungeon commit leaves every balance untouched.
"""

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select, text

import econ_core
import econ_ledger
import econ_contract_cases as cc
import gameplay
from econ_core import AccountRef, Leg
from models import DungeonRoom, DungeonSessionMember
from dungeon_harness import (  # noqa: F401
    fake_redis, world, build_dungeon, enter_solo, reload_session,
)

LOCATION = 1000           # seeded: district 100 -> region 10 -> country 1
REGION, COUNTRY = 10, 1

_REAL_CHARGE = gameplay._charge_gold
_REAL_PAY = gameplay._pay_gold
_ECON_TABLES = ("econ_postings", "econ_operations", "econ_accounts", "econ_settings",
                "characters", "Districts", "Regions", "Countries")


@pytest_asyncio.fixture()
async def econ(db_session, world, monkeypatch):
    """Shared-table world of econ_contract_cases inside the dungeon test DB; real gold helpers."""
    econ_core.invalidate_settings_cache()
    await db_session.execute(text("DROP TABLE IF EXISTS Locations"))
    for ddl in cc.SQLITE_DDL:
        await db_session.execute(text(ddl))
    for sql, params in cc.SEED_SQL:
        await db_session.execute(text(sql), params)
    for cid in (10, 11):
        await db_session.execute(text("INSERT INTO characters (id, name, currency_balance) VALUES (:i, 'x', 0)"),
                                 {"i": cid})
    await db_session.commit()
    monkeypatch.setattr(gameplay, "_charge_gold", _REAL_CHARGE)
    monkeypatch.setattr(gameplay, "_pay_gold", _REAL_PAY)
    world.location_id = LOCATION
    for c in world.characters.values():
        c["location"] = LOCATION
    yield db_session
    await db_session.rollback()
    for t in _ECON_TABLES:
        await db_session.execute(text(f"DROP TABLE IF EXISTS {t}"))
    await db_session.commit()
    econ_core.invalidate_settings_cache()


async def _fund(db, cid, amount):
    await econ_ledger.post_operation(db, op_type=econ_core.OP_GENESIS,
                                     legs=[Leg(AccountRef.emission(), AccountRef.character(cid), amount)],
                                     source_service="test", apply_tax=False)
    await db.commit()


async def _one(db, sql, **params):
    return (await db.execute(text(sql), params)).scalar()


async def _balance(db, cid):
    return await _one(db, cc.CHARACTER_BALANCE_SQL, id=cid)


async def _account(db, kind, ref_id):
    return await _one(db, cc.ACCOUNT_BALANCE_SQL, kind=kind, ref_id=ref_id)


async def _ops(db, op_type):
    return await _one(db, "SELECT COUNT(*) FROM econ_operations WHERE op_type = :t", t=op_type)


async def _set_room_config(db, room_id, **cfg):
    room = (await db.execute(select(DungeonRoom).where(DungeonRoom.id == room_id))).scalar_one()
    room.room_config = dict(room.room_config or {}, **cfg)
    await db.commit()


async def _assert_world_balanced(db):
    assert await _one(db, cc.WORLD_SUM_SQL) == 0


# ---------------------------------------------------------------- expenses

async def test_merchant_pays_the_region_treasury_with_tax(econ, world):
    db = econ
    await _fund(db, 10, 1000)
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c8"].id)

    out = await gameplay.interact_with_room(db, st.session_id, 10, "merchant_buy", item_id=33)

    assert out.gold_spent == 10 and "10 марок" in out.message
    assert await _balance(db, 10) == 990
    assert await _account(db, "region_treasury", REGION) == 9
    assert await _account(db, "country_treasury", COUNTRY) == 1
    assert await _ops(db, "dungeon_expense") == 1
    row = (await db.execute(text("SELECT location_id, region_id, source_service FROM econ_operations "
                                 "WHERE op_type = 'dungeon_expense'"))).first()
    assert tuple(row) == (LOCATION, REGION, "dungeon-service")
    await _assert_world_balanced(db)


async def test_merchant_without_gold_moves_nothing(econ, world):
    db = econ
    await _fund(db, 10, 5)
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c8"].id)

    with pytest.raises(HTTPException) as exc:
        await gameplay.interact_with_room(db, st.session_id, 10, "merchant_buy", item_id=33)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Недостаточно марок для покупки (нужно 10 марок)"
    assert await _balance(db, 10) == 5
    assert await _ops(db, "dungeon_expense") == 0
    await _assert_world_balanced(db)


async def test_failed_dungeon_commit_leaves_the_balance(econ, world):
    db = econ
    await _fund(db, 10, 1000)
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c8"].id)

    async def boom():
        raise RuntimeError("commit failed")
    db.commit = boom          # instance attribute shadows AsyncSession.commit
    try:
        with pytest.raises(RuntimeError):
            await gameplay.interact_with_room(db, st.session_id, 10, "merchant_buy", item_id=33)
    finally:
        del db.commit
    await db.rollback()

    assert await _balance(db, 10) == 1000
    assert await _ops(db, "dungeon_expense") == 0
    assert await _account(db, "region_treasury", REGION) in (None, 0)
    await _assert_world_balanced(db)


async def test_rest_cost_is_one_operation(econ, world):
    db = econ
    await _fund(db, 10, 100)
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    await _set_room_config(db, rooms["rest"].id, gold_cost=40)
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c7"].id)

    out = await gameplay.interact_with_room(db, st.session_id, 10, "start_rest")

    assert out.gold_spent == 40
    assert await _balance(db, 10) == 60
    assert await _ops(db, "dungeon_expense") == 1
    await _assert_world_balanced(db)


async def test_rest_without_gold_is_refused(econ, world):
    db = econ
    await _fund(db, 10, 1)
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    await _set_room_config(db, rooms["rest"].id, gold_cost=40)
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c7"].id)

    with pytest.raises(HTTPException) as exc:
        await gameplay.interact_with_room(db, st.session_id, 10, "start_rest")

    assert exc.value.detail == "Недостаточно марок для отдыха (нужно 40 марок)"
    assert await _balance(db, 10) == 1
    await _assert_world_balanced(db)


async def test_revive_charges_the_leader_once(econ, world):
    db = econ
    await _fund(db, 10, 150)
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11]}
    st = await gameplay.start_run(db, d.id, 10, 1, party=True)
    sid = st.session_id
    m = (await db.execute(select(DungeonSessionMember).where(
        DungeonSessionMember.session_id == sid, DungeonSessionMember.character_id == 11))).scalar_one()
    m.status = "dead"
    await db.commit()
    await gameplay.move_to_room(db, sid, 10, cors["c7"].id)

    out = await gameplay.interact_with_room(db, sid, 10, "revive_member", target_character_id=11)
    assert out.gold_spent == 100 and out.message.endswith("за 100 марок!")
    with pytest.raises(HTTPException):
        await gameplay.interact_with_room(db, sid, 10, "revive_member", target_character_id=11)

    assert await _balance(db, 10) == 50
    assert await _ops(db, "dungeon_expense") == 1
    await _assert_world_balanced(db)


# ---------------------------------------------------------------- event gold

async def test_event_gold_is_paid_by_the_region_in_the_choice_txn(econ, world):
    db = econ
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c3"].id)

    await gameplay.interact_with_room(db, st.session_id, 10, "event_choice", choice_index=0)

    assert await _balance(db, 10) == 100
    assert await _account(db, "region_treasury", REGION) == -100, "a treasury may go negative in stage 1"
    key = await _one(db, "SELECT idempotency_key FROM econ_operations WHERE op_type = 'dungeon_reward'")
    assert key == f"dungeon_reward:s:{st.session_id}:r:{rooms['event'].id}"
    await _assert_world_balanced(db)


async def test_event_gold_rolls_back_with_a_failed_commit(econ, world):
    db = econ
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c3"].id)

    async def boom():
        raise RuntimeError("commit failed")
    db.commit = boom          # instance attribute shadows AsyncSession.commit
    try:
        with pytest.raises(RuntimeError):
            await gameplay.interact_with_room(db, st.session_id, 10, "event_choice", choice_index=0)
    finally:
        del db.commit
    await db.rollback()

    assert await _balance(db, 10) == 0
    assert await _ops(db, "dungeon_reward") == 0
    # the choice is still open and pays exactly once
    await gameplay.interact_with_room(db, st.session_id, 10, "event_choice", choice_index=0)
    assert await _balance(db, 10) == 100
    await _assert_world_balanced(db)


async def test_dungeon_without_region_uses_the_world_treasury(econ, world):
    db = econ
    world.location_id = 1003   # seeded location with no district/region/parent
    for c in world.characters.values():
        c["location"] = 1003
    await _fund(db, 10, 50)
    d, rooms, cors = await build_dungeon(db, location_id=1003)
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c8"].id)

    await gameplay.interact_with_room(db, st.session_id, 10, "merchant_buy", item_id=33)

    assert await _account(db, "world_treasury", 0) == 10
    await _assert_world_balanced(db)
