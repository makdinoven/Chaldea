"""FEAT-175: entry rules — one group per dungeon, atomic entry, locks, cooldown, squads."""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

import gameplay
import session_state
from models import DungeonSession, DungeonSessionMember
from dungeon_harness import fake_redis, world, build_dungeon, enter_solo  # noqa: F401


async def _session_count(db):
    return (await db.execute(select(func.count()).select_from(DungeonSession))).scalar()


async def test_solo_entry_creates_active_run_and_locks(db_session, world):
    d, rooms, _ = await build_dungeon(db_session)
    state = await enter_solo(db_session, d)

    assert state.status == "active"
    assert state.phase == "exploring"
    assert state.current_room.id == rooms["entrance"].id
    assert world.lock_of(10)["dungeon_session_id"] == state.session_id
    assert await session_state.get_character_active_session(10) == state.session_id
    s = await gameplay._get_session(db_session, state.session_id)
    assert s.last_activity_at is not None and s.started_at is not None


async def test_members_come_with_their_frames(db_session, world):
    """Portrait, level and resource bars for the party frames."""
    d, _, _ = await build_dungeon(db_session)
    world.characters[10]["hp"] = 64
    state = await enter_solo(db_session, d)
    me = state.members[0]
    assert (me.current_health, me.max_health, me.current_stamina) == (64, 100, 100)


async def test_members_carry_their_class_for_the_board_miniature(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    world.characters[10]["class_id"] = 3
    state = await enter_solo(db_session, d)
    assert state.members[0].class_id == 3


async def test_member_frame_survives_a_silent_attributes_service(db_session, world, monkeypatch):
    d, _, _ = await build_dungeon(db_session)
    state = await enter_solo(db_session, d)

    async def down(cid):
        raise HTTPException(status_code=503, detail="Сервис атрибутов недоступен")

    monkeypatch.setattr(gameplay.http_clients, "get_character_attributes", down)
    again = await gameplay.get_session_state(db_session, state.session_id, 10)
    assert again.members[0].name == "Герой10" and again.members[0].current_health is None


async def test_second_group_is_refused_while_occupied(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    await enter_solo(db_session, d)
    with pytest.raises(HTTPException) as exc:
        await enter_solo(db_session, d, character_id=11, user_id=2)
    assert exc.value.status_code == 409
    assert exc.value.detail == "В подземелье уже находится другая группа"
    assert await _session_count(db_session) == 1
    assert world.lock_of(11)["locked"] is False


async def test_missing_gate_post_leaves_nothing_behind(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    world.gate_ok = False
    with pytest.raises(HTTPException) as exc:
        await enter_solo(db_session, d)
    assert exc.value.status_code == 403
    assert "Данж" in exc.value.detail
    assert await _session_count(db_session) == 0
    assert world.lock_of(10)["locked"] is False
    assert await session_state.get_character_active_session(10) is None
    # and the dungeon is still enterable once the post exists
    world.gate_ok = True
    assert (await enter_solo(db_session, d)).status == "active"


async def test_unconscious_character_cannot_enter(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    world.locks[10] = {"unconscious": datetime.utcnow() + timedelta(minutes=30)}
    with pytest.raises(HTTPException) as exc:
        await enter_solo(db_session, d)
    assert exc.value.status_code == 409
    assert exc.value.detail.startswith("Персонаж без сознания до")
    assert await _session_count(db_session) == 0


async def test_expired_knockout_does_not_block(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    world.locks[10] = {"unconscious": datetime.utcnow() - timedelta(seconds=1)}
    assert (await enter_solo(db_session, d)).status == "active"


async def test_must_stand_on_dungeon_location(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    world.characters[10]["location"] = 5
    with pytest.raises(HTTPException) as exc:
        await enter_solo(db_session, d)
    assert exc.value.status_code == 400


async def test_foreign_character_refused(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    with pytest.raises(HTTPException) as exc:
        await gameplay.start_run(db_session, d.id, 10, 999, party=False)
    assert exc.value.status_code == 403


async def test_cooldown_redis_and_db_fallback(db_session, world, fake_redis):
    d, _, _ = await build_dungeon(db_session)
    await session_state.set_dungeon_cooldown(d.id, 1, 2)
    with pytest.raises(HTTPException) as exc:
        await enter_solo(db_session, d)
    assert exc.value.status_code == 403
    assert "откате" in exc.value.detail

    # Redis lost, the DB still remembers the cooldown
    fake_redis.flush()
    db_session.add(DungeonSession(dungeon_id=d.id, leader_character_id=99, status="completed",
                                  cooldown_until=datetime.utcnow() + timedelta(hours=1),
                                  finalized_at=datetime.utcnow()))
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await enter_solo(db_session, d)
    assert exc.value.status_code == 403
    on_cd, _ = await session_state.check_dungeon_cooldown(d.id)
    assert on_cd, "the DB fallback re-arms the Redis key"


async def test_party_run_takes_free_colocated_squadmates(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    world.add_character(13, user_id=4, location=5)
    world.locks[12] = {"unconscious": datetime.utcnow() + timedelta(hours=1)}
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11, 12, 13]}
    state = await gameplay.start_run(db_session, d.id, 10, 1, party=True)

    assert sorted(m.character_id for m in state.members) == [10, 11]
    skipped = {s.character_id: s.reason for s in state.skipped_members}
    assert skipped == {12: "без сознания", 13: "не на локации подземелья"}
    assert world.lock_of(11)["dungeon_session_id"] == state.session_id
    names = {m.character_id: m.name for m in state.members}
    assert names[11] == "Герой11", "member names come from profile.character_name"


async def test_busy_squadmates_stay_outside(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    world.add_character(12, user_id=3)
    world.busy = {11: "в бою", 12: "занят добычей"}
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11, 12]}
    state = await gameplay.start_run(db_session, d.id, 10, 1, party=True)
    assert [m.character_id for m in state.members] == [10]
    assert {s.character_id: s.reason for s in state.skipped_members} == {11: "в бою", 12: "занят добычей"}
    assert world.lock_of(11)["locked"] is False


async def test_leader_in_a_surface_battle_cannot_enter(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    world.busy = {10: "в бою"}
    with pytest.raises(HTTPException) as exc:
        await enter_solo(db_session, d)
    assert exc.value.status_code == 409
    assert "в бою" in exc.value.detail
    assert await _session_count(db_session) == 0


async def test_lock_left_by_a_timed_out_call_is_cleared(db_session, world):
    """character-service committed the lock, but the answer never came back."""
    d, _, _ = await build_dungeon(db_session)
    import http_clients
    orig = http_clients.set_dungeon_lock

    async def timed_out(ids, sid):
        await orig(ids, sid)
        raise HTTPException(status_code=503, detail="Сервис персонажей недоступен")

    http_clients.set_dungeon_lock = timed_out
    try:
        with pytest.raises(HTTPException):
            await enter_solo(db_session, d)
    finally:
        http_clients.set_dungeon_lock = orig
    assert world.lock_of(10)["locked"] is False
    assert await _session_count(db_session) == 0


async def test_party_run_only_for_squad_leader(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    world.party = {"party_id": 1, "leader_character_id": 11, "member_character_ids": [10, 11]}
    with pytest.raises(HTTPException) as exc:
        await gameplay.start_run(db_session, d.id, 10, 1, party=True)
    assert exc.value.status_code == 400
    assert await _session_count(db_session) == 0


async def test_lock_conflict_rolls_back(db_session, world):
    """Someone got locked elsewhere between validation and locking."""
    d, _, _ = await build_dungeon(db_session)
    orig = world.set_dungeon_lock

    async def conflict(ids, sid):
        raise HTTPException(status_code=409, detail="Герой10 находится в подземелье")

    world_set = conflict
    import http_clients
    http_clients.set_dungeon_lock = world_set
    try:
        with pytest.raises(HTTPException) as exc:
            await enter_solo(db_session, d)
    finally:
        http_clients.set_dungeon_lock = orig
    assert exc.value.status_code == 409
    assert await _session_count(db_session) == 0


async def test_legacy_enter_is_idempotent(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    state = await enter_solo(db_session, d)
    again = await gameplay.enter_dungeon(db_session, state.session_id, 10)
    assert again.session_id == state.session_id and again.status == "active"


async def test_create_session_endpoint_shape(db_session, world):
    d, _, _ = await build_dungeon(db_session)
    resp = await gameplay.create_session(db_session, 10, d.id, 1)
    assert resp.status == "active"
    assert resp.leader_character_id == 10
    members = (await db_session.execute(select(DungeonSessionMember))).scalars().all()
    assert [m.character_id for m in members] == [10]
