"""FEAT-175: run endings — completion + cooldown, finalize, escape, loot
distribution, abandoned runs (sweeper), lost Redis state, leadership."""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import gameplay
import session_state
from models import DungeonSession, DungeonSessionInventory, DungeonSessionMember
from dungeon_harness import (  # noqa: F401
    fake_redis, world, build_dungeon, enter_solo, reload_session,
)


async def _inventory(db, sid):
    db.expire_all()
    rows = (await db.execute(select(DungeonSessionInventory).where(
        DungeonSessionInventory.session_id == sid))).scalars().all()
    return sorted((r.item_id, r.quantity) for r in rows)


async def _clear_dungeon(db, world, cors, sid):
    r = await gameplay.move_to_room(db, sid, 10, cors["c1"].id)
    await gameplay.process_battle_callback(db, sid, r.room_event["battle_id"], 1, [], False)
    r = await gameplay.move_to_room(db, sid, 10, cors["c2"].id)
    await gameplay.process_battle_callback(db, sid, r.room_event["battle_id"], 1, [], False)


async def _add_loot(db, sid, *items):
    for item_id, qty in items:
        db.add(DungeonSessionInventory(session_id=sid, item_id=item_id, quantity=qty, source_description="t"))
    await db.commit()


# ---------------------------------------------------------------- completion

async def test_cooldown_starts_only_when_boss_chest_is_opened(db_session, world):
    d, rooms, cors = await build_dungeon(db_session, cooldown_hours=10)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    await _clear_dungeon(db_session, world, cors, sid)
    assert (await session_state.check_dungeon_cooldown(d.id))[0] is False, "boss victory alone sets no cooldown"
    s = await reload_session(db_session, sid)
    assert s.status == "active" and s.cooldown_until is None

    await gameplay.interact_with_room(db_session, sid, 10, "open_chest")
    s = await reload_session(db_session, sid)
    assert s.status == "completed"
    assert s.cooldown_until is not None
    assert timedelta(hours=9, minutes=59) < s.cooldown_until - datetime.utcnow() <= timedelta(hours=10)
    on_cd, remaining = await session_state.check_dungeon_cooldown(d.id)
    assert on_cd and remaining > 9 * 3600
    assert world.lock_of(10)["locked"] is False, "a won run frees its members at once"
    assert await gameplay.find_character_session(db_session, 10) == (None, sid), "loot still to divide"
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.phase == "distributing_loot" and state.cooldown_until is not None


async def test_finalize_clears_locks_and_keeps_cooldown(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    await _clear_dungeon(db_session, world, cors, sid)
    await gameplay.interact_with_room(db_session, sid, 10, "open_chest")
    cooldown = (await reload_session(db_session, sid)).cooldown_until

    with pytest.raises(HTTPException) as exc:
        await gameplay.finalize_session(db_session, sid, 10)
    assert exc.value.status_code == 409, "leftovers need force"

    await gameplay.distribute_loot(db_session, sid, 10, [{"item_id": 77, "quantity": 2, "to_character_id": 10}])
    out = await gameplay.finalize_session(db_session, sid, 10)
    assert out.cooldown_until == cooldown
    assert world.given == [(10, 77, 2)]
    assert world.lock_of(10)["locked"] is False
    s = await reload_session(db_session, sid)
    assert s.finalized_at is not None
    assert await session_state.get_session_state(sid) is None
    again = await gameplay.finalize_session(db_session, sid, 10)
    assert again.message == "Забег уже завершён."
    # cooldown keeps others out
    world.add_character(20, user_id=20)
    with pytest.raises(HTTPException) as exc:
        await enter_solo(db_session, d, character_id=20, user_id=20)
    assert exc.value.status_code == 403


async def test_partial_distribution_then_forced_finalize(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    await _clear_dungeon(db_session, world, cors, sid)
    await gameplay.interact_with_room(db_session, sid, 10, "open_chest")
    await _add_loot(db_session, sid, (5, 3))

    part = await gameplay.distribute_loot(db_session, sid, 10, [{"item_id": 77, "quantity": 1, "to_character_id": 10}])
    assert sorted((i.item_id, i.quantity) for i in part.remaining_inventory) == [(5, 3), (77, 1)]
    with pytest.raises(HTTPException) as exc:  # the same request again: only 1 left
        await gameplay.distribute_loot(db_session, sid, 10, [{"item_id": 77, "quantity": 2, "to_character_id": 10}])
    assert exc.value.status_code == 409
    out = await gameplay.finalize_session(db_session, sid, 10, force=True)
    assert out.items_lost == 4
    assert await _inventory(db_session, sid) == []


async def test_failed_delivery_returns_item_to_group(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    await _add_loot(db_session, sid, (5, 2))
    # an escaped run awaiting distribution
    s = await reload_session(db_session, sid)
    s.status = "escaped"
    await db_session.commit()
    await session_state.update_session_state(sid, phase="distributing_loot", status="escaped")
    world.give_fail_items = {5}
    out = await gameplay.distribute_loot(db_session, sid, 10, [{"item_id": 5, "quantity": 2, "to_character_id": 10}])
    assert out.success is False and out.failed
    assert await _inventory(db_session, sid) == [(5, 2)]


async def test_loot_goes_only_to_living_members(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    db_session.add(DungeonSessionMember(session_id=sid, character_id=11, user_id=11, status="dead"))
    await _add_loot(db_session, sid, (5, 2))
    s = await reload_session(db_session, sid)
    s.status = "escaped"
    await db_session.commit()
    await session_state.update_session_state(sid, phase="distributing_loot", status="escaped")
    with pytest.raises(HTTPException) as exc:
        await gameplay.distribute_loot(db_session, sid, 10, [{"item_id": 5, "quantity": 1, "to_character_id": 11}])
    assert exc.value.status_code == 400
    assert await _inventory(db_session, sid) == [(5, 2)], "nothing is handed out on a refused request"


# ---------------------------------------------------------------- escape

async def test_escape_loses_half_frees_dungeon_no_cooldown(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    await _add_loot(db_session, sid, (1, 1), (2, 2), (3, 3))
    rolls = iter([0.1, 0.9, 0.4])  # < 0.5 -> lost
    monkeypatch.setattr(gameplay.random, "random", lambda: next(rolls))
    out = await gameplay.flee_dungeon(db_session, sid, 10)

    assert [(i.item_id, i.item_name) for i in out.items_lost] == [(1, "Предмет1"), (3, "Предмет3")]
    assert [i.item_id for i in out.items_remaining] == [2]
    s = await reload_session(db_session, sid)
    assert s.status == "escaped" and s.cooldown_until is None and s.finalized_at is None
    assert world.lock_of(10)["locked"] is False, "escape releases the lock at once"
    assert (await session_state.check_dungeon_cooldown(d.id))[0] is False
    world.add_character(20, user_id=20)
    assert (await enter_solo(db_session, d, character_id=20, user_id=20)).status == "active"

    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.phase == "distributing_loot"
    await gameplay.distribute_loot(db_session, sid, 10, [{"item_id": 2, "quantity": 2, "to_character_id": 10}])
    await gameplay.finalize_session(db_session, sid, 10)
    assert (await reload_session(db_session, sid)).finalized_at is not None


async def test_escape_with_nothing_left_closes_at_once(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    await gameplay.flee_dungeon(db_session, st.session_id, 10)
    assert (await reload_session(db_session, st.session_id)).finalized_at is not None


async def test_cannot_flee_mid_battle(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c1"].id)
    with pytest.raises(HTTPException) as exc:
        await gameplay.flee_dungeon(db_session, st.session_id, 10)
    assert exc.value.status_code == 400


# ---------------------------------------------------------------- abandonment / sweeper

async def _age(db, sid, hours):
    s = await reload_session(db, sid)
    s.last_activity_at = datetime.utcnow() - timedelta(hours=hours)
    await db.commit()


async def test_sweeper_treats_24h_idle_run_as_escape(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    await _add_loot(db_session, sid, (1, 1), (2, 2))
    await _age(db_session, sid, 25)
    rolls = iter([0.1, 0.9])
    monkeypatch.setattr(gameplay.random, "random", lambda: next(rolls))

    stats = await gameplay.sweep_sessions(db_session)
    assert stats["abandoned"] == 1
    s = await reload_session(db_session, sid)
    assert s.status == "escaped" and s.finalized_at is not None and s.cooldown_until is None
    assert world.given == [(10, 2, 2)], "kept loot goes to the leader"
    assert world.lock_of(10)["locked"] is False
    assert await gameplay.sweep_sessions(db_session) == {"abandoned": 0, "battles": 0, "redis_rebuilt": 0}


async def test_fresh_run_is_not_swept(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    await _age(db_session, st.session_id, 23)
    await gameplay.sweep_sessions(db_session)
    assert (await reload_session(db_session, st.session_id)).status == "active"


async def test_abandoned_run_is_expired_lazily_on_entry(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    await _age(db_session, st.session_id, 30)
    world.add_character(20, user_id=20)
    new = await enter_solo(db_session, d, character_id=20, user_id=20)
    assert new.status == "active"
    assert (await reload_session(db_session, st.session_id)).status == "escaped"


async def test_abandoned_distribution_is_closed(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    await _clear_dungeon(db_session, world, cors, sid)
    await gameplay.interact_with_room(db_session, sid, 10, "open_chest")
    await _age(db_session, sid, 25)
    await gameplay.sweep_sessions(db_session)
    s = await reload_session(db_session, sid)
    assert s.status == "completed" and s.finalized_at is not None
    assert world.given == [(10, 77, 2)]
    assert world.lock_of(10)["locked"] is False


async def test_sweeper_finishes_unseen_battle(db_session, world):
    from dungeon_harness import finish_battle
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    r = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c1"].id)
    finish_battle(world, r.room_event["battle_id"], party_won=True)
    stats = await gameplay.sweep_sessions(db_session)
    assert stats["battles"] == 1
    assert (await reload_session(db_session, st.session_id)).active_battle_id is None


async def test_lost_redis_state_is_rebuilt_not_500(db_session, world, fake_redis):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    fake_redis.flush()
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    assert resp.new_room.id == rooms["entrance"].id
    fake_redis.flush()
    stats = await gameplay.sweep_sessions(db_session)
    assert stats["redis_rebuilt"] == 1
    assert (await session_state.get_session_state(st.session_id))["phase"] == "exploring"


# ---------------------------------------------------------------- leadership

async def test_idle_offline_leader_is_replaced(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11]}
    st = await gameplay.start_run(db_session, d.id, 10, 1, party=True)
    sid = st.session_id
    with pytest.raises(HTTPException) as exc:
        await gameplay.move_to_room(db_session, sid, 11, cors["c4"].id)
    assert exc.value.status_code == 403

    # The old leader had their say before going quiet; once replaced, it counts like anyone's.
    await gameplay.vote_route(db_session, sid, 10, None, False)
    await _age(db_session, sid, 1)
    resp = await gameplay.move_to_room(db_session, sid, 11, cors["c4"].id)
    assert resp.new_room.id == rooms["treasure"].id
    assert (await reload_session(db_session, sid)).leader_character_id == 11
    assert world.events_of("leader_changed")


async def test_online_leader_is_not_replaced(db_session, world, monkeypatch):
    import ws_manager
    d, rooms, cors = await build_dungeon(db_session)
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11]}
    st = await gameplay.start_run(db_session, d.id, 10, 1, party=True)
    await _age(db_session, st.session_id, 1)
    monkeypatch.setattr(ws_manager, "get_connected_users", lambda sid: [1])
    with pytest.raises(HTTPException):
        await gameplay.move_to_room(db_session, st.session_id, 11, cors["c4"].id)


# ---------------------------------------------------------------- admin cleanup

async def test_admin_cleanup_of_completed_leftovers_releases_locks(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    await _clear_dungeon(db_session, world, cors, sid)
    await gameplay.interact_with_room(db_session, sid, 10, "open_chest")
    out = await gameplay.admin_force_cleanup_session(db_session, sid)
    assert out["previous_status"] == "completed"
    s = await reload_session(db_session, sid)
    assert s.status == "completed" and s.finalized_at is not None and s.cooldown_until is not None
    assert world.lock_of(10)["locked"] is False
    assert await _inventory(db_session, sid) == []


async def test_find_character_session(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    assert await gameplay.find_character_session(db_session, 10) == (st.session_id, None)
    await _add_loot(db_session, st.session_id, (1, 1))
    monkeypatch.setattr(gameplay.random, "random", lambda: 0.9)  # loot survives
    await gameplay.flee_dungeon(db_session, st.session_id, 10)
    assert await gameplay.find_character_session(db_session, 10) == (None, st.session_id)
