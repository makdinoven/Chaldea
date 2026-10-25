"""FEAT-175: dungeon battles — start before walking in, callback exactly once,
polling fallback, aborted battles, corridor continuation, wipe."""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import gameplay
import session_state
from models import DungeonRoomState, DungeonSessionInventory, DungeonSession, DungeonCorridor
from dungeon_harness import (  # noqa: F401
    fake_redis, world, build_dungeon, enter_solo, finish_battle, reload_session,
)


async def _room_state(db, sid, rid):
    db.expire_all()
    return (await db.execute(select(DungeonRoomState).where(
        DungeonRoomState.session_id == sid, DungeonRoomState.room_id == rid))).scalar_one_or_none()


async def _phase(sid):
    return (await session_state.get_session_state(sid))["phase"]


async def _enter_battle_room(db, world, mob_multiplier=1.0):
    d, rooms, cors = await build_dungeon(db, mob_multiplier=mob_multiplier)
    st = await enter_solo(db, d)
    resp = await gameplay.move_to_room(db, st.session_id, 10, cors["c1"].id)
    return d, rooms, cors, st.session_id, resp


async def test_battle_room_starts_battle_before_walking_in(db_session, world):
    d, rooms, cors, sid, resp = await _enter_battle_room(db_session, world, mob_multiplier=1.5)

    assert resp.room_event["type"] == "battle_started"
    assert resp.room_event["mob_names"] == ["Моб9001", "Моб9002"]
    assert world.spawned[0] == {"templates": [1, 2], "ids": [9001, 9002], "multiplier": 1.5}
    battle = world.battles[0]
    assert battle["session_id"] == sid
    assert {p["character_id"]: p["team"] for p in battle["players"]} == {10: 1, 9001: 2, 9002: 2}
    s = await reload_session(db_session, sid)
    assert s.current_room_id == rooms["battle"].id
    assert s.active_battle_id == battle["battle_id"]
    assert await _phase(sid) == "in_battle"
    assert world.stamina_spent[10] == 5
    started = world.events_of("battle_started")[0]["data"]
    assert started["mob_names"] == ["Моб9001", "Моб9002"]
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.current_room.room_config_visible["mob_count"] == 2, "figurines on the table, no names"


async def test_failed_battle_start_spends_nothing_and_can_be_retried(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    world.battle_fail = HTTPException(status_code=503, detail="Боевая система недоступна")
    with pytest.raises(HTTPException) as exc:
        await gameplay.move_to_room(db_session, st.session_id, 10, cors["c1"].id)
    assert exc.value.status_code == 503
    s = await reload_session(db_session, st.session_id)
    assert s.current_room_id == rooms["entrance"].id, "party did not walk past the battle room"
    assert world.stamina_spent == {}
    assert world.despawned == [9001, 9002], "spawned mobs were cleaned up"

    world.battle_fail = None
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c1"].id)
    assert resp.room_event["type"] == "battle_started"


async def test_battle_room_without_mobs_is_a_clear_error(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    from models import DungeonRoom
    room = (await db_session.execute(select(DungeonRoom).where(DungeonRoom.id == rooms["battle"].id))).scalar_one()
    room.room_config = {}
    await db_session.commit()
    st = await enter_solo(db_session, d)
    with pytest.raises(HTTPException) as exc:
        await gameplay.move_to_room(db_session, st.session_id, 10, cors["c1"].id)
    assert exc.value.status_code == 409
    assert "нет мобов" in exc.value.detail
    assert world.stamina_spent == {}


async def test_corridor_ambush_failure_spends_no_stamina(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    c = (await db_session.execute(select(DungeonCorridor).where(DungeonCorridor.id == cors["c4"].id))).scalar_one()
    c.random_battle_chance = 1.0
    c.random_battle_mob_ids = [4]
    await db_session.commit()
    st = await enter_solo(db_session, d)
    world.battle_fail = HTTPException(status_code=502, detail="Ошибка при создании боя")
    with pytest.raises(HTTPException):
        await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    assert world.stamina_spent == {}


async def test_callback_victory_clears_room_exactly_once(db_session, world):
    d, rooms, cors, sid, resp = await _enter_battle_room(db_session, world)
    bid = resp.room_event["battle_id"]

    first = await gameplay.process_battle_callback(db_session, sid, bid, 1, [9001, 9002], False)
    assert first["status"] == "processed" and first["party_won"] is True
    assert (await _room_state(db_session, sid, rooms["battle"].id)).is_cleared
    assert await _phase(sid) == "exploring"
    assert world.despawned == [9001, 9002]
    s = await reload_session(db_session, sid)
    assert s.active_battle_id is None

    again = await gameplay.process_battle_callback(db_session, sid, bid, 1, [], False)
    assert again["status"] == "ignored"
    assert len(world.events_of("battle_ended")) == 1


async def test_polling_fallback_then_late_callback_is_ignored(db_session, world):
    d, rooms, cors, sid, resp = await _enter_battle_room(db_session, world)
    bid = resp.room_event["battle_id"]
    finish_battle(world, bid, party_won=True)

    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.active_battle_id is None
    assert state.current_room.is_cleared is True
    late = await gameplay.process_battle_callback(db_session, sid, bid, 1, [], False)
    assert late["status"] == "ignored"


async def test_expired_battle_state_uses_durable_result(db_session, world):
    d, rooms, cors, sid, resp = await _enter_battle_room(db_session, world)
    bid = resp.room_event["battle_id"]
    world.battle_states[bid] = None
    world.battle_results[bid] = {"status": "finished", "winner_team": 1, "aborted": False}
    out = await gameplay.poll_active_battle(db_session, sid)
    assert out["party_won"] is True
    assert (await _room_state(db_session, sid, rooms["battle"].id)).is_cleared


async def test_running_battle_is_left_alone(db_session, world):
    d, rooms, cors, sid, resp = await _enter_battle_room(db_session, world)
    bid = resp.room_event["battle_id"]
    world.battle_states[bid] = {"runtime": {"participants": {
        "1": {"character_id": 10, "team": 1, "hp": 50}, "2": {"character_id": 9001, "team": 2, "hp": 5},
    }}}
    assert await gameplay.poll_active_battle(db_session, sid) is None
    assert (await reload_session(db_session, sid)).active_battle_id == bid


async def test_aborted_battle_allows_retry_but_not_walking_past(db_session, world):
    d, rooms, cors, sid, resp = await _enter_battle_room(db_session, world)
    bid = resp.room_event["battle_id"]
    out = await gameplay.process_battle_callback(db_session, sid, bid, None, [], True)
    assert out["aborted"] is True
    assert await _phase(sid) == "battle_pending"
    assert not (await _room_state(db_session, sid, rooms["battle"].id)).is_cleared

    with pytest.raises(HTTPException) as exc:  # boss room is unexplored -> blocked
        await gameplay.move_to_room(db_session, sid, 10, cors["c2"].id)
    assert exc.value.status_code == 409

    retry = await gameplay.interact_with_room(db_session, sid, 10, "start_battle")
    assert retry.success is True
    assert len(world.battles) == 2
    assert await _phase(sid) == "in_battle"


async def test_retreat_from_pending_battle_room_is_allowed(db_session, world):
    d, rooms, cors, sid, resp = await _enter_battle_room(db_session, world)
    await gameplay.process_battle_callback(db_session, sid, resp.room_event["battle_id"], None, [], True)
    back = await gameplay.move_to_room(db_session, sid, 10, cors["c1"].id)
    assert back.new_room.id == rooms["entrance"].id


async def test_corridor_battle_win_continues_into_target_battle_room(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    c = (await db_session.execute(select(DungeonCorridor).where(DungeonCorridor.id == cors["c1"].id))).scalar_one()
    c.random_battle_chance = 1.0
    c.random_battle_mob_ids = [4]
    await db_session.commit()
    st = await enter_solo(db_session, d)
    sid = st.session_id
    resp = await gameplay.move_to_room(db_session, sid, 10, cors["c1"].id)
    assert resp.corridor_event.type == "battle"
    assert resp.corridor_event.battle_id == world.battles[0]["battle_id"]
    assert resp.new_room is None

    await gameplay.process_battle_callback(db_session, sid, world.battles[0]["battle_id"], 1, [], False)
    s = await reload_session(db_session, sid)
    assert s.current_room_id == rooms["battle"].id
    assert len(world.battles) == 2, "the uncleared battle room's own fight starts at once"
    assert s.active_battle_id == world.battles[1]["battle_id"]


async def test_wipe_knocks_out_for_an_hour_and_frees_dungeon(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11]}
    st = await gameplay.start_run(db_session, d.id, 10, 1, party=True)
    sid = st.session_id
    db_session.add(DungeonSessionInventory(session_id=sid, item_id=5, quantity=3, source_description="x"))
    await db_session.commit()
    await gameplay.vote_route(db_session, sid, 11, cors["c1"].id, False)
    resp = await gameplay.move_to_room(db_session, sid, 10, cors["c1"].id)
    bid = resp.room_event["battle_id"]

    out = await gameplay.process_battle_callback(db_session, sid, bid, 2, [10, 11], False)
    assert out["wiped"] is True
    s = await reload_session(db_session, sid)
    assert s.status == "wiped" and s.finalized_at is not None and s.cooldown_until is None
    inv = (await db_session.execute(select(DungeonSessionInventory))).scalars().all()
    assert inv == [], "the raid loot is lost"
    assert world.knockouts == [{"ids": [10, 11], "seconds": 3600, "session_id": sid,
                                "return_location_id": d.location_id}]
    assert world.lock_of(10)["reason"] == "unconscious"
    assert await session_state.get_session_state(sid) is None
    wiped = [e for e in world.events_of("session_status") if e["data"]["status"] == "wiped"][0]["data"]
    assert wiped["phase"] == "wiped" and wiped["knocked_out_until"]

    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.phase == "wiped" and state.knocked_out_until is not None
    # no cooldown, nobody inside: another group may enter right away
    world.add_character(20, user_id=20)
    again = await enter_solo(db_session, d, character_id=20, user_id=20)
    assert again.status == "active"


async def test_wipe_falls_back_to_clearing_the_lock(db_session, world, monkeypatch):
    import http_clients
    d, rooms, cors, sid, resp = await _enter_battle_room(db_session, world)

    async def broken(*a, **kw):
        return None
    monkeypatch.setattr(http_clients, "knockout_characters", broken)
    await gameplay.process_battle_callback(db_session, sid, resp.room_event["battle_id"], 2, [10], False)
    assert world.lock_of(10)["locked"] is False


async def test_partial_casualties_mark_member_dead(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11]}
    st = await gameplay.start_run(db_session, d.id, 10, 1, party=True)
    await gameplay.vote_route(db_session, st.session_id, 11, None, False)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c1"].id)
    await gameplay.process_battle_callback(db_session, st.session_id, resp.room_event["battle_id"], 1, [11, 9001], False)
    s = await reload_session(db_session, st.session_id)
    assert {m.character_id: m.status for m in s.members} == {10: "alive", 11: "dead"}
    dead_evt = world.events_of("member_status_changed")[0]["data"]
    assert dead_evt["status"] == "dead" and dead_evt["new_status"] == "dead" and dead_evt["name"] == "Герой11"
