"""FEAT-175 review tails: a lost Redis mid-ambush, leadership with the action, a trap that must not hurt twice,
a lost battle with a bystander, leftovers handed over once, an unexplored room's size."""
import asyncio
import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import gameplay
from models import Dungeon, DungeonCorridor, DungeonRoom, DungeonSession, DungeonSessionInventory
from dungeon_harness import (  # noqa: F401
    fake_redis, world, build_dungeon, enter_solo, reload_session,
)


async def _set(db, model, row_id, **fields):
    row = (await db.execute(select(model).where(model.id == row_id))).scalar_one()
    for k, v in fields.items():
        setattr(row, k, v)
    await db.commit()


async def test_a_won_ambush_reaches_its_room_after_redis_is_lost(db_session, world, fake_redis):
    d, rooms, cors = await build_dungeon(db_session)
    await _set(db_session, DungeonCorridor, cors["c4"].id, random_battle_chance=1.0, random_battle_mob_ids=[4])
    st = await enter_solo(db_session, d)
    sid = st.session_id
    resp = await gameplay.move_to_room(db_session, sid, 10, cors["c4"].id)
    battle_id = resp.corridor_event.battle_id
    mobs = world.spawned[-1]["ids"]
    fake_redis.flush()  # Redis restarted mid-fight
    await gameplay.complete_battle(db_session, sid, battle_id, party_won=True, casualties=[])
    session = await reload_session(db_session, sid)
    assert session.current_room_id == rooms["treasure"].id
    assert set(mobs) <= set(world.despawned)
    assert session.battle_mob_ids is None and session.pending_target_room_id is None


async def test_a_failed_action_hands_no_leadership_over(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11]}
    st = await gameplay.start_run(db_session, d.id, 10, 1, party=True)
    sid = st.session_id
    session = await reload_session(db_session, sid)
    session.last_activity_at = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    await db_session.commit()
    with pytest.raises(HTTPException):
        # the old leader has not had their say yet: the move is refused
        await gameplay.move_to_room(db_session, sid, 11, cors["c4"].id)
    await db_session.rollback()  # what the request's session does when the action fails
    await db_session.commit()
    await asyncio.sleep(0)
    assert (await reload_session(db_session, sid)).leader_character_id == 10
    assert not world.events_of("leader_changed")


async def test_a_trap_is_given_back_when_the_room_battle_will_not_start(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _set(db_session, DungeonCorridor, cors["c1"].id, trap_chance=1.0,
               trap_config={"stat_check": "agility", "difficulty": 99, "fail_damage": 9})
    st = await enter_solo(db_session, d)
    world.battle_fail = HTTPException(status_code=502, detail="Боевая система недоступна")
    with pytest.raises(HTTPException):
        await gameplay.move_to_room(db_session, st.session_id, 10, cors["c1"].id)
    assert world.characters[10]["hp"] == 100  # the trap's blow taken back: a retry hurts once, not twice


async def test_a_lost_battle_is_a_wipe_even_with_someone_still_standing(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11]}
    st = await gameplay.start_run(db_session, d.id, 10, 1, party=True)
    sid = st.session_id
    await gameplay.vote_route(db_session, sid, 11, None, False)
    resp = await gameplay.move_to_room(db_session, sid, 10, cors["c1"].id)
    battle_id = resp.room_event["battle_id"]
    # 11 sat the fight out and still stands, but the party lost
    result = await gameplay.complete_battle(db_session, sid, battle_id, party_won=False, casualties=[10])
    assert result.get("wiped")
    assert (await reload_session(db_session, sid)).status == "wiped"


async def test_leftovers_are_handed_over_once(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    db_session.add_all([
        DungeonSessionInventory(session_id=sid, item_id=10, quantity=2, source_description="Сундук"),
        DungeonSessionInventory(session_id=sid, item_id=11, quantity=1, source_description="Событие"),
    ])
    await db_session.commit()
    world.give_fail_items = {11}
    session = await reload_session(db_session, sid)
    assert await gameplay._deliver_leftovers_to_leader(db_session, session) is False
    left = (await db_session.execute(select(DungeonSessionInventory).where(
        DungeonSessionInventory.session_id == sid))).scalars().all()
    assert [(r.item_id, r.source_description) for r in left] == [(11, "Событие")]
    world.give_fail_items = set()
    assert await gameplay._deliver_leftovers_to_leader(db_session, await reload_session(db_session, sid))
    assert sorted(world.given) == [(10, 10, 2), (10, 11, 1)]  # item 10 once, though it ran twice


async def test_an_unexplored_room_keeps_its_size_to_itself(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _set(db_session, DungeonRoom, rooms["treasure"].id, grid_w=4, grid_d=4)
    await _set(db_session, Dungeon, d.id, stability_type="unstable")
    st = await enter_solo(db_session, d)
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    exit_ = next(e for e in state.current_room.exits if e.corridor_id == cors["c4"].id)
    assert exit_.grid_w is None and exit_.grid_d is None
    await _set(db_session, Dungeon, d.id, stability_type="static")  # a charted dungeon shows it
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    exit_ = next(e for e in state.current_room.exits if e.corridor_id == cors["c4"].id)
    assert exit_.grid_w == 4


# ---------------------------------------------------------------- FEAT-176 review

import challenges  # noqa: E402
import session_state  # noqa: E402


async def test_a_game_the_party_walked_away_from_is_void(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    started = await gameplay.start_challenge(db_session, sid, 10, "search", None, "game")
    await gameplay.move_to_room(db_session, sid, 10, cors["c4"].id)
    with pytest.raises(HTTPException) as exc:
        await gameplay.step_challenge(db_session, sid, 10, started.challenge_id, x=0, y=0)
    assert exc.value.status_code == 409
    assert await session_state.get_challenge(sid, 10) is None


async def test_runes_cannot_be_answered_before_they_are_shown(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _set(db_session, DungeonCorridor, cors["c4"].id, passage_config={"secret": {"kind": "illusion"}})
    world.characters[10]["class_id"] = challenges.CLASS_MAGE
    st = await enter_solo(db_session, d)
    started = await gameplay.start_challenge(db_session, st.session_id, 10, "illusion", cors["c4"].id, "game")
    result = await gameplay.finish_challenge(db_session, st.session_id, 10, started.challenge_id,
                                             started.params["sequence"])
    assert not result.passed and result.outcome == "broke"


async def test_a_new_game_frees_the_door_of_the_one_left(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _set(db_session, DungeonCorridor, cors["c4"].id, passage_config={"secret": {"kind": "illusion"}})
    world.characters[10]["class_id"] = challenges.CLASS_MAGE
    st = await enter_solo(db_session, d)
    sid = st.session_id
    await gameplay.start_challenge(db_session, sid, 10, "illusion", cors["c4"].id, "game")
    await gameplay.start_challenge(db_session, sid, 10, "search", None, "game")  # walked off to search instead
    assert await session_state.claim_target(sid, f"corridor:{cors['c4'].id}", 11, 60) is None


async def test_a_look_cannot_be_emptied(admin_client, created_dungeon):
    resp = await admin_client.put(f"/dungeons/admin/dungeons/{created_dungeon['id']}", json={"theme": None})
    assert resp.status_code == 422


async def test_marks_stay_inside_the_dungeon(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    other, other_rooms, _ = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    with pytest.raises(HTTPException) as exc:
        await gameplay.ping_board(db_session, st.session_id, 10, "go", other_rooms["treasure"].id, None)
    assert exc.value.status_code == 404
