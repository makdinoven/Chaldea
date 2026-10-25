"""FEAT-175: locked doors and keys — keys from chests, battles and events open
every door of their kind for the run; without a key a lock may be picked."""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import gameplay
from models import DungeonRoom, DungeonCorridor
from dungeon_harness import (  # noqa: F401
    fake_redis, world, build_dungeon, enter_solo, reload_session,
)


async def _set_room_config(db, room_id, cfg):
    room = (await db.execute(select(DungeonRoom).where(DungeonRoom.id == room_id))).scalar_one()
    room.room_config = cfg
    await db.commit()


async def _lock(db, corridor_id, **lock):
    c = (await db.execute(select(DungeonCorridor).where(DungeonCorridor.id == corridor_id))).scalar_one()
    c.lock_config = lock
    await db.commit()


async def test_locked_door_refuses_without_key_and_costs_nothing(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _lock(db_session, cors["c7"].id, key="copper", pickable=False)
    st = await enter_solo(db_session, d)
    with pytest.raises(HTTPException) as e:
        await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    assert e.value.status_code == 409 and "Медный ключ" in e.value.detail
    assert "взломать" not in e.value.detail
    assert world.characters[10]["stamina"] == 100
    s = await reload_session(db_session, st.session_id)
    assert s.current_room_id == rooms["entrance"].id


async def test_exits_and_map_show_the_lock(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _lock(db_session, cors["c7"].id, key="silver")
    st = await enter_solo(db_session, d)
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    door = next(x for x in state.current_room.exits if x.corridor_id == cors["c7"].id)
    assert door.lock_key == "silver" and door.locked and door.lock_pickable
    other = next(x for x in state.current_room.exits if x.corridor_id == cors["c8"].id)
    assert other.lock_key is None and not other.locked
    seen = next(x for x in state.seen_doors if x.corridor_id == cors["c7"].id)
    assert seen.lock_key == "silver" and seen.locked
    assert state.keys == []


async def test_chest_key_opens_every_door_of_its_kind(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _set_room_config(db_session, rooms["treasure"].id,
                           {"loot_table": [], "key_reward": "copper"})
    await _lock(db_session, cors["c7"].id, key="copper", pickable=False)
    await _lock(db_session, cors["c8"].id, key="copper", pickable=False)
    st = await enter_solo(db_session, d)
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    out = await gameplay.interact_with_room(db_session, st.session_id, 10, "open_chest")
    assert out.key_found == "copper" and out.message == "Сундук открыт!"
    assert world.events_of("key_found")
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    assert resp.new_room.id == rooms["rest"].id
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c8"].id)
    assert resp.new_room.id == rooms["merchant"].id
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    assert state.keys == ["copper"]
    assert all(not c.locked for c in state.explored_corridors)


async def test_key_of_another_kind_does_not_fit(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _set_room_config(db_session, rooms["treasure"].id, {"loot_table": [], "key_reward": "bone"})
    await _lock(db_session, cors["c7"].id, key="gold", pickable=False)
    st = await enter_solo(db_session, d)
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    await gameplay.interact_with_room(db_session, st.session_id, 10, "open_chest")
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    with pytest.raises(HTTPException) as e:
        await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    assert "Золотой ключ" in e.value.detail


async def test_battle_room_drops_its_key_when_won(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _set_room_config(db_session, rooms["battle"].id, {"mob_template_ids": [1], "key_reward": "crimson"})
    st = await enter_solo(db_session, d)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c1"].id)
    bid = resp.room_event["battle_id"]
    await gameplay.process_battle_callback(db_session, st.session_id, bid, 1, [], False)
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    assert state.keys == ["crimson"]


async def test_event_choice_gives_a_key(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _set_room_config(db_session, rooms["event"].id, {"text": "?", "choices": [
        {"text": "Обыскать скелет", "outcome_type": "key", "outcome_data": '{"key": "obsidian"}'},
    ]})
    st = await enter_solo(db_session, d)
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c3"].id)
    await gameplay.interact_with_room(db_session, st.session_id, 10, "event_choice", choice_index=0)
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    assert state.keys == ["obsidian"]


async def test_pick_lock_success_opens_the_door(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _lock(db_session, cors["c7"].id, key="copper", difficulty=20, pick_cost=3)
    world.characters[10]["stats"] = {"agility": 30}
    world.characters[10]["class_id"] = 2  # a rogue: the roll is never short of 20
    st = await enter_solo(db_session, d)
    out = await gameplay.pick_lock(db_session, st.session_id, 10, cors["c7"].id)
    assert out.passed and out.stat_check == "agility" and out.stamina_consumed == 3
    assert world.characters[10]["stamina"] == 97
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    assert resp.new_room.id == rooms["rest"].id
    # Already open: picking it again is refused.
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    with pytest.raises(HTTPException):
        await gameplay.pick_lock(db_session, st.session_id, 10, cors["c7"].id)


async def test_pick_lock_failure_costs_stamina_and_stays_shut(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _lock(db_session, cors["c7"].id, key="copper", difficulty=50)
    world.characters[10]["stats"] = {"agility": 5}
    st = await enter_solo(db_session, d)
    out = await gameplay.pick_lock(db_session, st.session_id, 10, cors["c7"].id)
    assert not out.passed and out.stamina_consumed == gameplay.LOCK_DEFAULT_PICK_COST
    assert world.characters[10]["stamina"] == 100 - gameplay.LOCK_DEFAULT_PICK_COST
    with pytest.raises(HTTPException) as e:
        await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    assert e.value.status_code == 409


async def test_pick_lock_refusals(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _lock(db_session, cors["c7"].id, key="copper", pickable=False)
    await _lock(db_session, cors["c2"].id, key="copper")
    world.add_character(11, 2)
    st = await enter_solo(db_session, d)
    for corridor, detail in ((cors["c7"].id, "не взломать"), (cors["c8"].id, "не заперта"),
                             (cors["c2"].id, "не ведёт из текущей комнаты")):
        with pytest.raises(HTTPException) as e:
            await gameplay.pick_lock(db_session, st.session_id, 10, corridor)
        assert detail in e.value.detail
    world.characters[10]["stamina"] = 1
    await _lock(db_session, cors["c8"].id, key="copper", pick_cost=5)
    with pytest.raises(HTTPException) as e:
        await gameplay.pick_lock(db_session, st.session_id, 10, cors["c8"].id)
    assert "Недостаточно стамины" in e.value.detail


def test_lock_and_key_shapes_are_validated():
    from schemas import validate_lock_config, validate_room_config
    assert validate_lock_config(None) is None
    assert validate_lock_config({"key": "gold", "pickable": False, "difficulty": 15, "pick_cost": 1})
    for bad in ({"key": "rusty"}, {"key": "gold", "pickable": "yes"}, {"key": "gold", "difficulty": -2}, "gold"):
        with pytest.raises(ValueError):
            validate_lock_config(bad)
    assert validate_room_config("treasure", {"key_reward": "bone"})
    with pytest.raises(ValueError):
        validate_room_config("battle", {"key_reward": "rusty"})
    with pytest.raises(ValueError):
        validate_room_config("event", {"choices": [{"text": "x", "outcome_type": "key", "outcome_data": "{}"}]})


async def _put_party(db, session_id, room_id):
    s = await reload_session(db, session_id)
    s.current_room_id = room_id
    await db.commit()


async def test_door_is_unbolted_from_behind_its_lock(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _lock(db_session, cors["c7"].id, key="copper", pickable=False)
    st = await enter_solo(db_session, d)
    await _put_party(db_session, st.session_id, rooms["rest"].id)  # thrown in, say, by a red portal
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    door = next(x for x in state.current_room.exits if x.corridor_id == cors["c7"].id)
    assert not door.locked
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    assert resp.new_room.id == rooms["entrance"].id
    # unbolted for good: the way back in needs no key either
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    assert resp.new_room.id == rooms["rest"].id


async def test_lift_is_not_unbolted_from_below(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    below = DungeonRoom(dungeon_id=d.id, room_type="fork", name="Низ", description="x",
                        room_config={}, sort_order=0, floor=2)
    db_session.add(below)
    await db_session.flush()
    lift = DungeonCorridor(dungeon_id=d.id, from_room_id=rooms["entrance"].id, to_room_id=below.id,
                           stamina_cost=1, is_bidirectional=True, passage_type="lift",
                           lock_config={"key": "gold", "pickable": False})
    db_session.add(lift)
    await db_session.flush()
    below_id, lift_id = below.id, lift.id
    await db_session.commit()
    st = await enter_solo(db_session, d)
    await _put_party(db_session, st.session_id, below_id)
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    assert next(x for x in state.current_room.exits if x.corridor_id == lift_id).locked
    with pytest.raises(HTTPException) as e:
        await gameplay.move_to_room(db_session, st.session_id, 10, lift_id)
    assert e.value.status_code == 409


async def test_validate_warns_of_a_room_the_party_is_stuck_in(admin_client, created_dungeon):
    did = created_dungeon["id"]

    async def room(name, **kw):
        r = await admin_client.post(f"/dungeons/admin/dungeons/{did}/rooms", json={
            "room_type": "fork", "name": name, "description": "x", **kw})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    ent = await room("Вход", is_entrance=True)
    pit = await room("Яма")
    cell = await room("Келья")
    await room("Разлом", room_type="teleport",
               room_config={"portal": "red", "target_room_ids": [pit, cell]})
    for a, b in ((pit, ent), (ent, cell)):  # the pit's lock faces the pit, the cell's faces the entrance
        r = await admin_client.post(f"/dungeons/admin/dungeons/{did}/corridors", json={
            "from_room_id": a, "to_room_id": b, "lock_config": {"key": "copper"}})
        assert r.status_code == 201, r.text
    out = (await admin_client.post(f"/dungeons/admin/dungeons/{did}/validate")).json()
    stuck = [w for w in out["warnings"] if "застрять" in w]
    assert len(stuck) == 1 and "«Яма»" in stuck[0] and "Разлом" in stuck[0]
