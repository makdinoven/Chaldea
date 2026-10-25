"""FEAT-175: floors — stairs, drops (plain and hidden), lifts opened by levers,
and depth scaling of mobs, loot and the flee loss."""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import gameplay
from models import Dungeon, DungeonRoom, DungeonCorridor, DungeonSession
from dungeon_harness import (  # noqa: F401
    fake_redis, world, build_dungeon, enter_solo, reload_session,
)


async def _room(db, d, rtype, floor, cfg=None, name=None):
    r = DungeonRoom(dungeon_id=d.id, room_type=rtype, name=name or f"{rtype}{floor}", description="x",
                    room_config=cfg or {}, sort_order=0, floor=floor)
    db.add(r)
    await db.flush()
    rid = r.id
    await db.commit()
    return rid


async def _passage(db, d, from_id, to_id, passage, **kw):
    c = DungeonCorridor(dungeon_id=d.id, from_room_id=from_id, to_room_id=to_id, stamina_cost=1,
                        is_bidirectional=passage != "drop", passage_type=passage,
                        passage_config=kw.get("config"), lock_config=kw.get("lock"))
    db.add(c)
    await db.flush()
    cid = c.id
    await db.commit()
    return cid


async def test_stairs_lead_down_and_back_up(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    below = await _room(db_session, d, "fork", 2, name="Нижний зал")
    stairs = await _passage(db_session, d, rooms["entrance"].id, below, "stairs")
    st = await enter_solo(db_session, d)
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    assert state.floors == 2 and state.current_room.floor == 1
    exit_ = next(e for e in state.current_room.exits if e.corridor_id == stairs)
    assert exit_.passage == "stairs" and exit_.to_floor == 2
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, stairs)
    assert resp.new_room.id == below and resp.new_room.floor == 2
    back = next(e for e in resp.new_room.exits if e.corridor_id == stairs)
    assert back.to_floor == 1
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, stairs)
    assert resp.new_room.id == rooms["entrance"].id
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    explored = {r.id: r.floor for r in state.explored_rooms}
    assert explored[below] == 2


async def test_plain_drop_is_one_way(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    below = await _room(db_session, d, "fork", 2)
    drop = await _passage(db_session, d, rooms["entrance"].id, below, "drop")
    st = await enter_solo(db_session, d)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, drop)
    assert resp.new_room.id == below
    assert all(e.corridor_id != drop for e in resp.new_room.exits)
    with pytest.raises(HTTPException):
        await gameplay.move_to_room(db_session, st.session_id, 10, drop)


async def test_hidden_drop_is_invisible_until_found(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    below = await _room(db_session, d, "fork", 2)
    drop = await _passage(db_session, d, rooms["rest"].id, below, "drop",
                          config={"hidden": True, "difficulty": 99})
    st = await enter_solo(db_session, d)
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    assert all(s.corridor_id != drop for s in state.seen_doors)
    with pytest.raises(HTTPException):
        await gameplay.move_to_room(db_session, st.session_id, 10, drop)


async def test_hidden_drop_spotted_becomes_a_safe_way_down(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    below = await _room(db_session, d, "fork", 2)
    drop = await _passage(db_session, d, rooms["rest"].id, below, "drop",
                          config={"hidden": True, "stat_check": "intelligence", "difficulty": 10})
    world.characters[10]["stats"] = {"intelligence": 30}
    st = await enter_solo(db_session, d)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    assert resp.room_event["type"] == "drop_spotted" and resp.room_event["passed"] is True
    assert resp.new_room.id == rooms["rest"].id
    assert any(e.corridor_id == drop and e.passage == "drop" for e in resp.new_room.exits)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, drop)
    assert resp.new_room.id == below and world.characters[10]["hp"] == 100


async def test_hidden_drop_missed_throws_party_down_with_damage(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    below = await _room(db_session, d, "fork", 2)
    stairs = await _passage(db_session, d, below, rooms["rest"].id, "stairs")
    drop = await _passage(db_session, d, rooms["rest"].id, below, "drop",
                          config={"hidden": True, "difficulty": 99, "fail_damage": 25})
    st = await enter_solo(db_session, d)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    ev = resp.room_event
    assert ev["type"] == "teleported" and ev["fell"] is True and ev["passed"] is False
    assert ev["teleported_from"] == rooms["rest"].id and ev["target_room_id"] == below
    assert world.characters[10]["hp"] == 75
    assert resp.new_room.id == below and resp.new_room.floor == 2
    # Found now: climbing back up into the room it springs no more.
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, stairs)
    assert resp.room_event is None and resp.new_room.id == rooms["rest"].id
    assert any(e.corridor_id == drop for e in resp.new_room.exits)


async def test_lift_opened_by_a_lever(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    below = await _room(db_session, d, "fork", 2)
    lift = await _passage(db_session, d, rooms["entrance"].id, below, "lift", lock={"lever": True})
    room = (await db_session.execute(select(DungeonRoom).where(DungeonRoom.id == rooms["rest"].id))).scalar_one()
    room.room_config = {**room.room_config, "lever_corridor_id": lift}
    await db_session.commit()
    st = await enter_solo(db_session, d)
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    door = next(e for e in state.current_room.exits if e.corridor_id == lift)
    assert door.locked and door.lock_lever and not door.lock_pickable and door.passage == "lift"
    with pytest.raises(HTTPException) as e:
        await gameplay.move_to_room(db_session, st.session_id, 10, lift)
    assert "рычаг" in e.value.detail
    with pytest.raises(HTTPException) as e:
        await gameplay.pick_lock(db_session, st.session_id, 10, lift)
    assert "не взломать" in e.value.detail
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    assert resp.new_room.room_config_visible["lever"] == {"pulled": False}
    out = await gameplay.interact_with_room(db_session, st.session_id, 10, "pull_lever")
    assert out.success
    with pytest.raises(HTTPException) as e:
        await gameplay.interact_with_room(db_session, st.session_id, 10, "pull_lever")
    assert e.value.status_code == 409
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, lift)
    assert resp.new_room.id == below


async def test_deeper_floor_spawns_stronger_mobs(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    deep_battle = await _room(db_session, d, "battle", 2, cfg={"mob_template_ids": [1]})
    stairs = await _passage(db_session, d, rooms["entrance"].id, deep_battle, "stairs")
    dungeon = (await db_session.execute(select(Dungeon).where(Dungeon.id == d.id))).scalar_one()
    dungeon.floor_mob_step = 0.5
    await db_session.commit()
    st = await enter_solo(db_session, d)
    await gameplay.move_to_room(db_session, st.session_id, 10, stairs)
    assert world.spawned[-1]["multiplier"] == pytest.approx(1.5)


async def test_flee_loss_grows_with_depth(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    deep = await _room(db_session, d, "fork", 3)
    st = await enter_solo(db_session, d)
    s = (await db_session.execute(select(DungeonSession).where(DungeonSession.id == st.session_id))).scalar_one()
    assert await gameplay._escape_loss_chance(db_session, s) == pytest.approx(gameplay.ESCAPE_LOSS_CHANCE)
    s.current_room_id = deep
    await db_session.commit()
    assert await gameplay._escape_loss_chance(db_session, s) == pytest.approx(gameplay.ESCAPE_LOSS_CHANCE + 0.2)


def test_floor_scaling_helpers():
    assert gameplay._floor_factor(0.15, 1) == 1.0
    assert gameplay._floor_factor(0.15, 3) == pytest.approx(1.3)
    assert gameplay._floor_factor(None, 4) == 1.0


async def test_admin_passages_follow_the_floors(admin_client, created_dungeon):
    did = created_dungeon["id"]

    async def room(floor):
        r = await admin_client.post(f"/dungeons/admin/dungeons/{did}/rooms", json={
            "room_type": "fork", "name": f"F{floor}", "description": "x", "floor": floor})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    top, mid, bottom = await room(1), await room(2), await room(3)

    async def corridor(a, b, passage):
        return await admin_client.post(f"/dungeons/admin/dungeons/{did}/corridors",
                                       json={"from_room_id": a, "to_room_id": b, "passage_type": passage})

    assert (await corridor(top, mid, "corridor")).status_code == 400
    assert (await corridor(top, bottom, "stairs")).status_code == 400
    assert (await corridor(mid, top, "drop")).status_code == 400
    drop = await corridor(top, mid, "drop")
    assert drop.status_code == 201 and drop.json()["is_bidirectional"] is False
    assert (await corridor(mid, bottom, "lift")).status_code == 201
    r = await admin_client.put(f"/dungeons/admin/corridors/{drop.json()['id']}", json={"passage_type": "corridor"})
    assert r.status_code == 400
    bad = await admin_client.post(f"/dungeons/admin/dungeons/{did}/rooms", json={
        "room_type": "fork", "name": "x", "description": "x", "floor": 0})
    assert bad.status_code == 422


async def test_validate_reports_floor_problems(admin_client, created_dungeon):
    did = created_dungeon["id"]
    ent = (await admin_client.post(f"/dungeons/admin/dungeons/{did}/rooms", json={
        "room_type": "fork", "name": "Вход", "description": "x", "is_entrance": True})).json()
    deep = (await admin_client.post(f"/dungeons/admin/dungeons/{did}/rooms", json={
        "room_type": "fork", "name": "Глубина", "description": "x", "floor": 2})).json()
    c = (await admin_client.post(f"/dungeons/admin/dungeons/{did}/corridors", json={
        "from_room_id": ent["id"], "to_room_id": deep["id"], "passage_type": "stairs",
        "lock_config": {"lever": True}})).json()
    # the deep room is moved two floors down: the stairs now skip a floor, floor 2 is empty
    await admin_client.put(f"/dungeons/admin/rooms/{deep['id']}", json={"floor": 3})
    out = (await admin_client.post(f"/dungeons/admin/dungeons/{did}/validate")).json()
    assert any("соседний этаж" in e for e in out["errors"])
    assert any("рычага в подземелье нет" in e for e in out["errors"])
    assert any("Этаж 2 пуст" in w for w in out["warnings"])
    assert c["passage_type"] == "stairs"
