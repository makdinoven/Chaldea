"""Basic movement / validation rules, carried over from the pre-FEAT-175
mock tests (test_gameplay.py, test_sessions.py, test_boss_chest_bugfix.py,
test_wipe_finished_at.py) onto the real-code harness."""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import gameplay
import session_state
from models import Dungeon, DungeonCorridor, DungeonSessionInventory
from dungeon_harness import fake_redis, world, build_dungeon, enter_solo, reload_session  # noqa: F401


async def test_move_spends_stamina_with_dead_penalty_and_multiplier(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    dungeon = (await db_session.execute(select(Dungeon).where(Dungeon.id == d.id))).scalar_one()
    dungeon.stamina_multiplier = 2.0
    await db_session.commit()
    st = await enter_solo(db_session, d)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    assert resp.stamina_consumed == 10
    assert world.stamina_spent[10] == 10
    assert resp.corridor_event.type == "safe"


async def test_move_back_through_bidirectional_corridor(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    back = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    assert back.new_room.id == rooms["entrance"].id


async def test_move_insufficient_stamina(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    world.characters[10]["stamina"] = 2
    st = await enter_solo(db_session, d)
    with pytest.raises(HTTPException) as exc:
        await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    assert exc.value.status_code == 400
    assert "Герой10" in exc.value.detail


async def test_move_wrong_corridor(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    with pytest.raises(HTTPException) as exc:
        await gameplay.move_to_room(db_session, st.session_id, 10, cors["c2"].id)
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        await gameplay.move_to_room(db_session, st.session_id, 10, 999999)
    assert exc.value.status_code == 404


async def test_non_member_cannot_act_or_read(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    with pytest.raises(HTTPException) as exc:
        await gameplay.move_to_room(db_session, st.session_id, 11, cors["c4"].id)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        await gameplay.get_session_state(db_session, st.session_id, 11)
    assert exc.value.status_code == 403


async def test_inactive_and_missing_dungeon(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    dungeon = (await db_session.execute(select(Dungeon).where(Dungeon.id == d.id))).scalar_one()
    dungeon.is_active = False
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await enter_solo(db_session, d)
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        await gameplay.start_run(db_session, 424242, 10, 1, party=False)
    assert exc.value.status_code == 404


async def test_treasure_chest_does_not_end_run(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    await gameplay.interact_with_room(db_session, st.session_id, 10, "open_chest")
    s = await reload_session(db_session, st.session_id)
    assert s.status == "active" and s.cooldown_until is None
    assert (await session_state.get_session_state(st.session_id))["phase"] == "exploring"


async def test_boss_chest_needs_boss_dead(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    r = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c1"].id)
    await gameplay.process_battle_callback(db_session, st.session_id, r.room_event["battle_id"], 1, [], False)
    r = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c2"].id)
    # boss fight running
    with pytest.raises(HTTPException):
        await gameplay.interact_with_room(db_session, st.session_id, 10, "open_chest")


async def test_distribute_validation(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    db_session.add(DungeonSessionInventory(session_id=sid, item_id=5, quantity=1, source_description="x"))
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:  # run still active
        await gameplay.distribute_loot(db_session, sid, 10, [{"item_id": 5, "quantity": 1, "to_character_id": 10}])
    assert exc.value.status_code == 400
    s = await reload_session(db_session, sid)
    s.status = "escaped"
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await gameplay.distribute_loot(db_session, sid, 10, [{"item_id": 5, "quantity": 1, "to_character_id": 12}])
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        await gameplay.distribute_loot(db_session, sid, 10, [{"item_id": 5, "quantity": 0, "to_character_id": 10}])
    assert exc.value.status_code == 400


async def test_item_name_failure_is_graceful(db_session, world, monkeypatch):
    import http_clients
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    db_session.add(DungeonSessionInventory(session_id=st.session_id, item_id=5, quantity=1, source_description="x"))
    await db_session.commit()

    async def boom(item_id):
        raise HTTPException(status_code=503, detail="down")
    monkeypatch.setattr(http_clients, "get_item_info", boom)
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    assert state.group_inventory[0].item_name is None
