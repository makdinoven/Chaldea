"""FEAT-181 Q3: dungeon gold — gaps left by test_econ_dungeon.py, on the REAL async ledger.

* rest / revive: a crash between the posting and the dungeon commit rolls back both the gold
  and the run change (the rest is not started, the member stays dead);
* revive / merchant without gold: the run change is rolled back too (member dead, stock and
  group bag unchanged);
* merchant: quantity × price is ONE operation with the country tax leg; huge / non-positive
  quantities move nothing extra;
* event gold: a payout whose key was already used pays nothing and still records the choice;
  a second choice is refused and pays nothing;
* security: a member who is not the leader cannot spend the leader's gold (403).

Each scenario ends with the world invariant Σ characters + Σ accounts = 0.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

import econ_core
import gameplay
import econ_contract_cases as cc
from models import DungeonRoomState, DungeonSessionInventory, DungeonSessionMember
from dungeon_harness import fake_redis, world, build_dungeon, enter_solo  # noqa: F401
from test_econ_dungeon import (  # noqa: F401
    econ, _fund, _one, _balance, _account, _ops, _set_room_config, _assert_world_balanced,
    LOCATION, REGION, COUNTRY,
)


def _crash_on_commit(db):
    async def boom():
        raise RuntimeError("commit failed")
    db.commit = boom          # instance attribute shadows AsyncSession.commit


def _restore_commit(db):
    del db.commit


async def _room_state(db, session_id, room_id):
    db.expire_all()
    return (await db.execute(select(DungeonRoomState).where(
        DungeonRoomState.session_id == session_id, DungeonRoomState.room_id == room_id))).scalar_one_or_none()


async def _bag(db, session_id, item_id):
    db.expire_all()
    rows = (await db.execute(select(DungeonSessionInventory).where(
        DungeonSessionInventory.session_id == session_id,
        DungeonSessionInventory.item_id == item_id))).scalars().all()
    return sum(r.quantity for r in rows)


async def _member_status(db, session_id, cid):
    db.expire_all()
    return (await db.execute(select(DungeonSessionMember.status).where(
        DungeonSessionMember.session_id == session_id, DungeonSessionMember.character_id == cid))).scalar_one()


async def _party_run_with_dead_member(db, world, d):
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11]}
    st = await gameplay.start_run(db, d.id, 10, 1, party=True)
    m = (await db.execute(select(DungeonSessionMember).where(
        DungeonSessionMember.session_id == st.session_id, DungeonSessionMember.character_id == 11))).scalar_one()
    m.status = "dead"
    await db.commit()
    return st.session_id


# ---------------------------------------------------------------- rest

async def test_rest_charge_taxes_the_country(econ, world):
    db = econ
    await _fund(db, 10, 100)
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    await _set_room_config(db, rooms["rest"].id, gold_cost=40)
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c7"].id)

    await gameplay.interact_with_room(db, st.session_id, 10, "start_rest")

    assert await _account(db, "region_treasury", REGION) == 36
    assert await _account(db, "country_treasury", COUNTRY) == 4
    await _assert_world_balanced(db)


async def test_rest_crash_before_commit_keeps_gold_and_does_not_start_the_rest(econ, world):
    db = econ
    await _fund(db, 10, 100)
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    await _set_room_config(db, rooms["rest"].id, gold_cost=40)
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c7"].id)

    _crash_on_commit(db)
    try:
        with pytest.raises(RuntimeError):
            await gameplay.interact_with_room(db, st.session_id, 10, "start_rest")
    finally:
        _restore_commit(db)
    await db.rollback()

    assert await _balance(db, 10) == 100
    assert await _ops(db, "dungeon_expense") == 0
    state = await _room_state(db, st.session_id, rooms["rest"].id)
    assert state is None or not (state.extra_data or {}).get("rest_started_at")
    # the rest can be started afterwards and is charged exactly once
    await gameplay.interact_with_room(db, st.session_id, 10, "start_rest")
    assert await _balance(db, 10) == 60
    assert await _ops(db, "dungeon_expense") == 1
    await _assert_world_balanced(db)


async def test_rest_without_gold_does_not_start_the_rest(econ, world):
    db = econ
    await _fund(db, 10, 39)
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    await _set_room_config(db, rooms["rest"].id, gold_cost=40)
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c7"].id)

    with pytest.raises(HTTPException) as exc:
        await gameplay.interact_with_room(db, st.session_id, 10, "start_rest")

    assert exc.value.status_code == 400
    state = await _room_state(db, st.session_id, rooms["rest"].id)
    assert state is None or not (state.extra_data or {}).get("rest_started_at")
    assert await _balance(db, 10) == 39
    await _assert_world_balanced(db)


# ---------------------------------------------------------------- revive

async def test_revive_crash_before_commit_keeps_the_member_dead_and_the_gold(econ, world):
    db = econ
    await _fund(db, 10, 150)
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    sid = await _party_run_with_dead_member(db, world, d)
    await gameplay.move_to_room(db, sid, 10, cors["c7"].id)

    _crash_on_commit(db)
    try:
        with pytest.raises(RuntimeError):
            await gameplay.interact_with_room(db, sid, 10, "revive_member", target_character_id=11)
    finally:
        _restore_commit(db)
    await db.rollback()

    assert await _member_status(db, sid, 11) == "dead"
    assert await _balance(db, 10) == 150
    assert await _ops(db, "dungeon_expense") == 0
    await _assert_world_balanced(db)


async def test_revive_without_gold_keeps_the_member_dead(econ, world):
    db = econ
    await _fund(db, 10, 99)
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    sid = await _party_run_with_dead_member(db, world, d)
    await gameplay.move_to_room(db, sid, 10, cors["c7"].id)

    with pytest.raises(HTTPException) as exc:
        await gameplay.interact_with_room(db, sid, 10, "revive_member", target_character_id=11)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Недостаточно марок для воскрешения (нужно 100 марок)"
    assert await _member_status(db, sid, 11) == "dead"
    assert await _balance(db, 10) == 99
    assert await _ops(db, "dungeon_expense") == 0
    await _assert_world_balanced(db)


async def test_a_member_who_is_not_the_leader_cannot_spend(econ, world):
    db = econ
    await _fund(db, 10, 150)
    await _fund(db, 11, 150)
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    # the leader walks alone (a dead member has no vote), then the member stands up again
    sid = await _party_run_with_dead_member(db, world, d)
    await gameplay.move_to_room(db, sid, 10, cors["c8"].id)
    await db.execute(text("UPDATE dungeon_session_members SET status = 'alive' "
                          "WHERE session_id = :s AND character_id = 11"), {"s": sid})
    await db.commit()
    db.expire_all()

    with pytest.raises(HTTPException) as exc:
        await gameplay.interact_with_room(db, sid, 11, "merchant_buy", item_id=33)

    assert exc.value.status_code == 403
    assert (await _balance(db, 10), await _balance(db, 11)) == (150, 150)
    assert await _ops(db, "dungeon_expense") == 0
    await _assert_world_balanced(db)


# ---------------------------------------------------------------- merchant

async def test_merchant_quantity_is_one_operation_with_tax(econ, world):
    db = econ
    await _fund(db, 10, 1000)
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    await _set_room_config(db, rooms["merchant"].id, items=[{"item_id": 33, "price": 15, "stock": 5}])
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c8"].id)

    out = await gameplay.interact_with_room(db, st.session_id, 10, "merchant_buy", item_id=33, quantity=3)

    assert out.gold_spent == 45
    assert await _balance(db, 10) == 955
    assert await _ops(db, "dungeon_expense") == 1
    assert await _account(db, "region_treasury", REGION) == 41          # 45 - floor(4.5)
    assert await _account(db, "country_treasury", COUNTRY) == 4
    assert await _bag(db, st.session_id, 33) == 3
    await _assert_world_balanced(db)


async def test_merchant_without_gold_keeps_stock_and_bag(econ, world):
    db = econ
    await _fund(db, 10, 44)
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    await _set_room_config(db, rooms["merchant"].id, items=[{"item_id": 33, "price": 15, "stock": 5}])
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c8"].id)

    with pytest.raises(HTTPException) as exc:
        await gameplay.interact_with_room(db, st.session_id, 10, "merchant_buy", item_id=33, quantity=3)

    assert exc.value.status_code == 400
    assert await _bag(db, st.session_id, 33) == 0
    state = await _room_state(db, st.session_id, rooms["merchant"].id)
    assert state is None or "33" not in ((state.extra_data or {}).get("merchant_stock") or {})
    assert await _balance(db, 10) == 44
    # the full stock is still for sale
    await _fund(db, 10, 1)
    out = await gameplay.interact_with_room(db, st.session_id, 10, "merchant_buy", item_id=33, quantity=3)
    assert out.gold_spent == 45 and await _balance(db, 10) == 0
    await _assert_world_balanced(db)


async def test_merchant_huge_quantity_is_refused_by_stock(econ, world):
    db = econ
    await _fund(db, 10, 1000)
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    await _set_room_config(db, rooms["merchant"].id, items=[{"item_id": 33, "price": 15}])  # default stock
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c8"].id)

    with pytest.raises(HTTPException) as exc:
        await gameplay.interact_with_room(db, st.session_id, 10, "merchant_buy", item_id=33, quantity=10**12)

    assert exc.value.status_code == 409
    assert await _balance(db, 10) == 1000
    assert await _ops(db, "dungeon_expense") == 0
    await _assert_world_balanced(db)


@pytest.mark.parametrize("quantity", [0, -5])
async def test_merchant_non_positive_quantity_buys_one(econ, world, quantity):
    db = econ
    await _fund(db, 10, 1000)
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    await _set_room_config(db, rooms["merchant"].id, items=[{"item_id": 33, "price": 15, "stock": 5}])
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c8"].id)

    out = await gameplay.interact_with_room(db, st.session_id, 10, "merchant_buy", item_id=33, quantity=quantity)

    assert out.gold_spent == 15, "never a negative charge / refund through a negative quantity"
    assert await _balance(db, 10) == 985
    await _assert_world_balanced(db)


# ---------------------------------------------------------------- event gold

async def test_event_payout_with_a_used_key_pays_nothing_but_records_the_choice(econ, world):
    db = econ
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c3"].id)
    key = f"dungeon_reward:s:{st.session_id}:r:{rooms['event'].id}"
    # the payout already happened (e.g. a replayed request after a lost response)
    await db.execute(text("INSERT INTO econ_operations (op_type, idempotency_key, source_service) "
                          "VALUES ('dungeon_reward', :k, 'dungeon-service')"), {"k": key})
    await db.commit()

    out = await gameplay.interact_with_room(db, st.session_id, 10, "event_choice", choice_index=0)

    assert out.success is True
    assert await _balance(db, 10) == 0
    assert await _ops(db, "dungeon_reward") == 1
    assert await _one(db, "SELECT COUNT(*) FROM econ_postings") == 0
    state = await _room_state(db, st.session_id, rooms["event"].id)
    assert state.event_choice_index == 0
    await _assert_world_balanced(db)


async def test_event_cannot_be_chosen_twice(econ, world):
    db = econ
    d, rooms, cors = await build_dungeon(db, location_id=LOCATION)
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c3"].id)

    await gameplay.interact_with_room(db, st.session_id, 10, "event_choice", choice_index=0)
    with pytest.raises(HTTPException) as exc:
        await gameplay.interact_with_room(db, st.session_id, 10, "event_choice", choice_index=0)

    assert exc.value.status_code == 409
    assert await _balance(db, 10) == 100
    assert await _ops(db, "dungeon_reward") == 1
    # a reward is not taxed: the treasury pays, nothing flows to the country
    assert await _account(db, "country_treasury", COUNTRY) is None
    await _assert_world_balanced(db)


async def test_event_gold_without_region_comes_from_the_world_treasury(econ, world):
    db = econ
    world.location_id = 1003
    for c in world.characters.values():
        c["location"] = 1003
    d, rooms, cors = await build_dungeon(db, location_id=1003)
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c3"].id)

    await gameplay.interact_with_room(db, st.session_id, 10, "event_choice", choice_index=0)

    assert await _account(db, "world_treasury", 0) == -100
    assert await _one(db, cc.WORLD_SUM_SQL) == 0
    assert econ_core.OP_DUNGEON_REWARD == "dungeon_reward"
