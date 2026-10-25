"""FEAT-176: the party decides together — votes on the way on, board marks."""

import pytest
from fastapi import HTTPException

import gameplay
from dungeon_harness import (  # noqa: F401
    fake_redis, world, build_dungeon, enter_solo, reload_session,
)


async def _party_run(db, world, members=(10, 11, 12)):
    d, rooms, cors = await build_dungeon(db)
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": list(members)}
    st = await gameplay.start_run(db, d.id, 10, 1, party=True)
    return d, rooms, cors, st.session_id


async def test_solo_run_needs_no_votes(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    assert resp.new_room.id == rooms["treasure"].id


async def test_leader_waits_until_everyone_has_had_their_say(db_session, world):
    d, rooms, cors, sid = await _party_run(db_session, world)
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert sorted(state.waiting_for) == [11, 12] and state.votes == []

    with pytest.raises(HTTPException) as exc:
        await gameplay.move_to_room(db_session, sid, 10, cors["c4"].id)
    assert exc.value.status_code == 409
    assert "Герой11" in exc.value.detail and "Герой12" in exc.value.detail

    out = await gameplay.vote_route(db_session, sid, 11, cors["c4"].id, False)
    assert out.waiting_for == [12]
    assert [(v.character_id, v.corridor_id) for v in out.votes] == [(11, cors["c4"].id)]
    vote_evt = world.events_of("party_vote")[-1]["data"]
    assert vote_evt["waiting_for"] == [12]

    with pytest.raises(HTTPException):
        await gameplay.move_to_room(db_session, sid, 10, cors["c4"].id)

    # "As the leader decides" is a say too; the leader may then go anywhere.
    await gameplay.vote_route(db_session, sid, 12, None, False)
    resp = await gameplay.move_to_room(db_session, sid, 10, cors["c5"].id)
    assert resp.new_room.id == rooms["trap"].id


async def test_a_new_room_asks_again(db_session, world):
    d, rooms, cors, sid = await _party_run(db_session, world, members=(10, 11))
    await gameplay.vote_route(db_session, sid, 11, cors["c4"].id, False)
    await gameplay.move_to_room(db_session, sid, 10, cors["c4"].id)
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.waiting_for == [11] and state.votes == []
    with pytest.raises(HTTPException) as exc:
        await gameplay.move_to_room(db_session, sid, 10, cors["c4"].id)
    assert exc.value.status_code == 409


async def test_the_fallen_are_not_waited_for(db_session, world):
    d, rooms, cors, sid = await _party_run(db_session, world, members=(10, 11))
    s = await reload_session(db_session, sid)
    next(m for m in s.members if m.character_id == 11).status = "dead"
    await db_session.commit()
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.waiting_for == []
    with pytest.raises(HTTPException) as exc:
        await gameplay.vote_route(db_session, sid, 11, None, False)
    assert exc.value.status_code == 409
    resp = await gameplay.move_to_room(db_session, sid, 10, cors["c4"].id)
    assert resp.new_room.id == rooms["treasure"].id


async def test_votes_only_for_ways_out_of_this_room(db_session, world):
    d, rooms, cors, sid = await _party_run(db_session, world, members=(10, 11))
    with pytest.raises(HTTPException) as exc:
        await gameplay.vote_route(db_session, sid, 11, cors["c2"].id, False)  # battle -> boss, not from here
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        await gameplay.vote_route(db_session, sid, 11, None, True)  # no portal at the entrance
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        await gameplay.vote_route(db_session, sid, 99, None, False)
    assert exc.value.status_code == 403


async def test_blue_portal_waits_for_the_party_too(db_session, world):
    d, rooms, cors, sid = await _party_run(db_session, world, members=(10, 11))
    await gameplay.vote_route(db_session, sid, 11, cors["c6"].id, False)
    await gameplay.move_to_room(db_session, sid, 10, cors["c6"].id)
    with pytest.raises(HTTPException) as exc:
        await gameplay.interact_with_room(db_session, sid, 10, "use_portal")
    assert exc.value.status_code == 409
    out = await gameplay.vote_route(db_session, sid, 11, None, True)
    assert out.votes[0].portal is True
    resp = await gameplay.interact_with_room(db_session, sid, 10, "use_portal")
    assert resp.teleported_to["room_id"] == rooms["battle"].id


async def test_board_marks_reach_the_party_but_not_too_often(db_session, world):
    d, rooms, cors, sid = await _party_run(db_session, world, members=(10, 11))
    await gameplay.ping_board(db_session, sid, 11, "danger", rooms["trap"].id, None)
    ping = world.events_of("party_ping")[-1]["data"]
    assert ping == {"character_id": 11, "kind": "danger", "room_id": rooms["trap"].id, "corridor_id": None}
    with pytest.raises(HTTPException) as exc:
        await gameplay.ping_board(db_session, sid, 11, "go", None, cors["c4"].id)
    assert exc.value.status_code == 429
    with pytest.raises(HTTPException) as exc:
        await gameplay.ping_board(db_session, sid, 10, "go", None, None)
    assert exc.value.status_code == 400
