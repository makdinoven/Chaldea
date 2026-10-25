"""FEAT-175: room mechanics — teleport, traps, events, chests, merchant,
revive, mana core, map payload (incl. 3D grid size)."""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import gameplay
import session_state
from models import DungeonRoom, DungeonCorridor, DungeonSessionInventory, DungeonSessionMember, Dungeon
from dungeon_harness import (  # noqa: F401
    fake_redis, world, build_dungeon, enter_solo, finish_battle, reload_session,
)


async def _set_room_config(db, room_id, cfg):
    room = (await db.execute(select(DungeonRoom).where(DungeonRoom.id == room_id))).scalar_one()
    room.room_config = cfg
    await db.commit()


async def _inventory(db, sid):
    db.expire_all()
    rows = (await db.execute(select(DungeonSessionInventory).where(
        DungeonSessionInventory.session_id == sid))).scalars().all()
    return sorted((r.item_id, r.quantity) for r in rows)


# ---------------------------------------------------------------- portals

async def test_blue_portal_waits_for_the_party(db_session, world):
    """Walking into a blue portal does nothing: the party stands there and may walk on."""
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c6"].id)
    assert resp.room_event is None
    assert resp.new_room.id == rooms["teleport"].id
    assert resp.new_room.room_config_visible["portal"] == "blue"
    assert resp.new_room.room_config_visible["target_room_id"] == rooms["battle"].id


async def test_use_blue_portal_moves_party_and_starts_target_battle(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c6"].id)
    out = await gameplay.interact_with_room(db_session, st.session_id, 10, "use_portal")
    assert out.success and out.teleported_to["room_id"] == rooms["battle"].id
    s = await reload_session(db_session, st.session_id)
    assert s.current_room_id == rooms["battle"].id and s.active_battle_id


async def test_blue_portal_pair_works_both_ways_and_again(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    a_id = rooms["teleport"].id
    b = DungeonRoom(dungeon_id=d.id, room_type="teleport", name="B", description="b",
                    room_config={"target_room_id": a_id}, sort_order=0)
    db_session.add(b)
    await db_session.flush()
    b_id = b.id
    await _set_room_config(db_session, a_id, {"target_room_id": b_id})
    st = await enter_solo(db_session, d)
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c6"].id)
    for expected in (b_id, a_id, b_id):
        out = await gameplay.interact_with_room(db_session, st.session_id, 10, "use_portal")
        assert out.teleported_to["room_id"] == expected
        assert (await reload_session(db_session, st.session_id)).current_room_id == expected


async def test_use_portal_refused_outside_a_blue_portal(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    with pytest.raises(HTTPException) as e:
        await gameplay.interact_with_room(db_session, st.session_id, 10, "use_portal")
    assert e.value.status_code == 400
    await _set_room_config(db_session, rooms["teleport"].id,
                           {"portal": "red", "target_room_ids": [rooms["treasure"].id], "difficulty": 0})
    world.characters[10]["stats"] = {"intelligence": 50}
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c6"].id)
    with pytest.raises(HTTPException) as e:
        await gameplay.interact_with_room(db_session, st.session_id, 10, "use_portal")
    assert e.value.status_code == 400


async def test_blue_portal_to_foreign_or_missing_room_is_refused(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _set_room_config(db_session, rooms["teleport"].id, {"target_room_id": -15})
    st = await enter_solo(db_session, d)
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c6"].id)
    with pytest.raises(HTTPException) as e:
        await gameplay.interact_with_room(db_session, st.session_id, 10, "use_portal")
    assert e.value.status_code == 400
    assert (await reload_session(db_session, st.session_id)).current_room_id == rooms["teleport"].id


async def test_red_portal_spotted_is_harmless_after(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _set_room_config(db_session, rooms["teleport"].id, {
        "portal": "red", "target_room_ids": [rooms["battle"].id], "stat_check": "intelligence", "difficulty": 20})
    world.characters[10]["stats"] = {"intelligence": 80}
    st = await enter_solo(db_session, d)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c6"].id)
    assert resp.room_event["type"] == "portal_spotted" and resp.room_event["passed"] is True
    assert resp.new_room.id == rooms["teleport"].id and resp.new_room.is_cleared
    visible = resp.new_room.room_config_visible
    assert visible["portal"] == "red" and visible["portal_result"] == {"passed": True}
    assert "target_room_ids" not in visible and "target_room_id" not in visible
    # A dull party walks back in later: the spotted portal no longer rolls.
    world.characters[10]["stats"] = {"intelligence": 0}
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c6"].id)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c6"].id)
    assert resp.room_event is None and resp.new_room.id == rooms["teleport"].id


async def test_red_portal_missed_throws_party_into_a_configured_room(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    targets = [rooms["battle"].id, rooms["treasure"].id]
    await _set_room_config(db_session, rooms["teleport"].id, {
        "portal": "red", "target_room_ids": targets, "stat_check": "intelligence", "difficulty": 99})
    world.characters[10]["stats"] = {"intelligence": 1}
    monkeypatch.setattr(gameplay.random, "choice", lambda seq: seq[-1])
    st = await enter_solo(db_session, d)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c6"].id)
    ev = resp.room_event
    assert ev["type"] == "teleported" and ev["red_portal"] is True and ev["passed"] is False
    assert ev["stat_check"] == "intelligence" and ev["target_room_id"] == rooms["treasure"].id
    assert resp.new_room.id == rooms["treasure"].id
    # The portal stays live: the next walk-in rolls again.
    state = await gameplay._get_room_state(db_session, st.session_id, rooms["teleport"].id)
    assert not state.is_cleared and state.extra_data["portal"] == {"passed": False}


async def test_red_portal_into_a_battle_room_starts_the_ambush(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _set_room_config(db_session, rooms["teleport"].id, {
        "portal": "red", "target_room_ids": [rooms["battle"].id], "difficulty": 99})
    st = await enter_solo(db_session, d)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c6"].id)
    assert resp.room_event["followup"]["type"] == "battle_started"
    s = await reload_session(db_session, st.session_id)
    assert s.current_room_id == rooms["battle"].id and s.active_battle_id


async def test_red_portal_without_rooms_is_harmless(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _set_room_config(db_session, rooms["teleport"].id, {"portal": "red", "difficulty": 99})
    st = await enter_solo(db_session, d)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c6"].id)
    assert resp.room_event["type"] == "portal_spotted" and resp.room_event["passed"] is False
    assert resp.new_room.id == rooms["teleport"].id


def test_portal_config_shape_is_validated():
    from schemas import validate_room_config
    assert validate_room_config("teleport", {"portal": "red", "target_room_ids": [3, 4], "difficulty": 12})
    for bad in ({"portal": "green"}, {"target_room_ids": [0]}, {"target_room_ids": "3"},
                {"difficulty": -1}, {"stat_check": 5}):
        with pytest.raises(ValueError):
            validate_room_config("teleport", bad)


# ---------------------------------------------------------------- traps

async def test_trap_room_deals_damage_but_never_kills(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    world.characters[10]["hp"] = 20
    st = await enter_solo(db_session, d)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c5"].id)
    assert resp.room_event["type"] == "trap_triggered"
    assert resp.room_event["passed"] is False
    assert world.characters[10]["hp"] == 1, "30 damage capped to leave 1 HP"
    # re-entering a sprung trap does nothing
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c5"].id)
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c5"].id)
    assert world.characters[10]["hp"] == 1


async def test_trap_passed_with_high_stat(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    world.characters[10]["stats"] = {"agility": 80}
    st = await enter_solo(db_session, d)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c5"].id)
    assert resp.room_event["passed"] is True
    assert world.characters[10]["hp"] == 100


async def test_corridor_trap_damage_is_applied(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    c = (await db_session.execute(select(DungeonCorridor).where(DungeonCorridor.id == cors["c4"].id))).scalar_one()
    c.trap_chance = 1.0
    c.trap_config = {"stat_check": "strength", "difficulty": 99, "fail_damage": 15}
    await db_session.commit()
    st = await enter_solo(db_session, d)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    assert resp.corridor_event.type == "trap"
    assert resp.corridor_event.passed is False and resp.corridor_event.damage == 15
    assert world.characters[10]["hp"] == 85


# ---------------------------------------------------------------- events

async def _at_event(db, world):
    d, rooms, cors = await build_dungeon(db)
    st = await enter_solo(db, d)
    await gameplay.move_to_room(db, st.session_id, 10, cors["c3"].id)
    return d, rooms, cors, st.session_id


async def test_event_reward(db_session, world):
    d, rooms, cors, sid = await _at_event(db_session, world)
    out = await gameplay.interact_with_room(db_session, sid, 10, "event_choice", choice_index=0)
    assert out.success
    assert await _inventory(db_session, sid) == [(5, 1)]
    assert world.gold[10] == 1100


async def test_event_damage_is_dealt(db_session, world):
    d, rooms, cors, sid = await _at_event(db_session, world)
    out = await gameplay.interact_with_room(db_session, sid, 10, "event_choice", choice_index=1)
    assert out.damage_taken == 30
    assert world.characters[10]["hp"] == 70


async def test_event_heal_percent_from_editor(db_session, world):
    d, rooms, cors, sid = await _at_event(db_session, world)
    world.characters[10]["hp"] = 10
    await gameplay.interact_with_room(db_session, sid, 10, "event_choice", choice_index=2)
    assert world.characters[10]["hp"] == 60, "50% of 100 max HP"


async def test_event_heal_amount_backward_compat(db_session, world):
    d, rooms, cors, sid = await _at_event(db_session, world)
    world.characters[10]["hp"] = 10
    await gameplay.interact_with_room(db_session, sid, 10, "event_choice", choice_index=3)
    assert world.characters[10]["hp"] == 17


async def test_event_battle_uses_outcome_mobs(db_session, world):
    d, rooms, cors, sid = await _at_event(db_session, world)
    out = await gameplay.interact_with_room(db_session, sid, 10, "event_choice", choice_index=4)
    assert out.effect_applied == "бой"
    assert world.spawned[-1]["templates"] == [3]
    assert (await reload_session(db_session, sid)).active_battle_id == world.battles[-1]["battle_id"]


async def test_event_battle_failure_keeps_choice_open(db_session, world):
    d, rooms, cors, sid = await _at_event(db_session, world)
    world.battle_fail = HTTPException(status_code=503, detail="Боевая система недоступна")
    with pytest.raises(HTTPException):
        await gameplay.interact_with_room(db_session, sid, 10, "event_choice", choice_index=4)
    world.battle_fail = None
    out = await gameplay.interact_with_room(db_session, sid, 10, "event_choice", choice_index=4)
    assert out.success


async def test_event_teleport_within_dungeon(db_session, world):
    d, rooms, cors, sid = await _at_event(db_session, world)
    out = await gameplay.interact_with_room(db_session, sid, 10, "event_choice", choice_index=5)
    assert out.teleported_to["room_id"] == rooms["treasure"].id
    assert (await reload_session(db_session, sid)).current_room_id == rooms["treasure"].id


async def test_event_teleport_to_other_dungeon_is_refused(db_session, world):
    d, rooms, cors, sid = await _at_event(db_session, world)
    d2, rooms2, _ = await build_dungeon(db_session)
    room = (await db_session.execute(select(DungeonRoom).where(DungeonRoom.id == rooms["event"].id))).scalar_one()
    choices = list(room.room_config["choices"])
    choices[5] = dict(choices[5], outcome_data='{"target_room_id": %d}' % rooms2["treasure"].id)
    room.room_config = dict(room.room_config, choices=choices)
    await db_session.commit()
    out = await gameplay.interact_with_room(db_session, sid, 10, "event_choice", choice_index=5)
    assert out.teleported_to is None
    assert (await reload_session(db_session, sid)).current_room_id == rooms["event"].id


async def test_event_choice_only_once(db_session, world):
    d, rooms, cors, sid = await _at_event(db_session, world)
    await gameplay.interact_with_room(db_session, sid, 10, "event_choice", choice_index=1)
    with pytest.raises(HTTPException) as exc:
        await gameplay.interact_with_room(db_session, sid, 10, "event_choice", choice_index=0)
    assert exc.value.status_code == 409
    assert world.gold[10] == 1000


# ---------------------------------------------------------------- chest / merchant / revive

async def test_chest_opens_once(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    out = await gameplay.interact_with_room(db_session, st.session_id, 10, "open_chest")
    assert out.loot_gained[0]["item_name"] == "Предмет10"
    with pytest.raises(HTTPException) as exc:
        await gameplay.interact_with_room(db_session, st.session_id, 10, "open_chest")
    assert exc.value.status_code == 409
    assert await _inventory(db_session, st.session_id) == [(10, 5)]
    loot_evt = world.events_of("loot_added")[0]["data"]
    assert loot_evt["items"][0]["item_name"] == "Предмет10" and loot_evt["item_name"] == "Предмет10"



async def test_map_remembers_an_emptied_chest_and_a_taken_rest(db_session, world):
    """Rooms left behind tell the 3D table their one-off use is spent."""
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    await gameplay.move_to_room(db_session, sid, 10, cors["c4"].id)
    await gameplay.interact_with_room(db_session, sid, 10, "open_chest")
    here = await gameplay.get_session_state(db_session, sid, 10)
    await gameplay.move_to_room(db_session, sid, 10, here.current_room.exits[0].corridor_id)
    away = await gameplay.get_session_state(db_session, sid, 10)
    assert away.current_room.id == rooms["entrance"].id
    await gameplay.move_to_room(db_session, sid, 10, cors["c7"].id)
    seen = {r.id: r for r in (await gameplay.get_session_state(db_session, sid, 10)).explored_rooms}
    assert seen[rooms["treasure"].id].used is True
    await gameplay.interact_with_room(db_session, sid, 10, "start_rest")
    await gameplay.interact_with_room(db_session, sid, 10, "complete_rest")
    await gameplay.move_to_room(db_session, sid, 10, cors["c7"].id)
    away = await gameplay.get_session_state(db_session, sid, 10)
    seen = {r.id: r for r in away.explored_rooms}
    assert seen[rooms["rest"].id].used is True
    assert not any(r.used for r in away.explored_rooms if r.room_type not in ("treasure", "rest"))


async def test_merchant_stock_and_failed_payment(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    await gameplay.move_to_room(db_session, sid, 10, cors["c8"].id)
    world.gold[10] = 5
    with pytest.raises(HTTPException) as exc:
        await gameplay.interact_with_room(db_session, sid, 10, "merchant_buy", item_id=33)
    assert exc.value.status_code == 400
    assert await _inventory(db_session, sid) == [], "nothing bought, stock released"

    world.gold[10] = 100
    await gameplay.interact_with_room(db_session, sid, 10, "merchant_buy", item_id=33)
    with pytest.raises(HTTPException) as exc:
        await gameplay.interact_with_room(db_session, sid, 10, "merchant_buy", item_id=33)
    assert exc.value.status_code == 409
    assert world.gold[10] == 90
    assert await _inventory(db_session, sid) == [(33, 1)]


async def test_revive_charges_once(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11]}
    st = await gameplay.start_run(db_session, d.id, 10, 1, party=True)
    sid = st.session_id
    m = (await db_session.execute(select(DungeonSessionMember).where(
        DungeonSessionMember.session_id == sid, DungeonSessionMember.character_id == 11))).scalar_one()
    m.status = "dead"
    await db_session.commit()
    await session_state.update_member_status(sid, "11", "dead")
    await gameplay.move_to_room(db_session, sid, 10, cors["c7"].id)

    out = await gameplay.interact_with_room(db_session, sid, 10, "revive_member", target_character_id=11)
    assert out.gold_spent == 100
    with pytest.raises(HTTPException) as exc:
        await gameplay.interact_with_room(db_session, sid, 10, "revive_member", target_character_id=11)
    assert exc.value.status_code == 409
    assert world.gold[10] == 900


async def test_revive_without_gold_keeps_member_dead(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11]}
    st = await gameplay.start_run(db_session, d.id, 10, 1, party=True)
    sid = st.session_id
    m = (await db_session.execute(select(DungeonSessionMember).where(
        DungeonSessionMember.session_id == sid, DungeonSessionMember.character_id == 11))).scalar_one()
    m.status = "dead"
    await db_session.commit()
    await gameplay.move_to_room(db_session, sid, 10, cors["c7"].id)
    world.gold[10] = 0
    with pytest.raises(HTTPException):
        await gameplay.interact_with_room(db_session, sid, 10, "revive_member", target_character_id=11)
    s = await reload_session(db_session, sid)
    assert {x.character_id: x.status for x in s.members}[11] == "dead"


async def test_rest_heals_percent(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    world.characters[10]["hp"] = 10
    st = await enter_solo(db_session, d)
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    await gameplay.interact_with_room(db_session, st.session_id, 10, "start_rest")
    await gameplay.interact_with_room(db_session, st.session_id, 10, "complete_rest")
    assert world.characters[10]["hp"] == 40
    with pytest.raises(HTTPException):
        await gameplay.interact_with_room(db_session, st.session_id, 10, "start_rest")


# ---------------------------------------------------------------- boss / mana core

async def _beat_boss(db, world, d, rooms, cors, sid):
    r = await gameplay.move_to_room(db, sid, 10, cors["c1"].id)
    await gameplay.process_battle_callback(db, sid, r.room_event["battle_id"], 1, [], False)
    r = await gameplay.move_to_room(db, sid, 10, cors["c2"].id)
    await gameplay.process_battle_callback(db, sid, r.room_event["battle_id"], 1, [], False)


async def test_mana_core_single_roll_reveal_search_then_chest(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session, mana_core=True, mana_core_chance=0.3, mana_core_item_id=999)
    rolls = []

    def fake_random():
        rolls.append(1)
        return 0.29
    monkeypatch.setattr(gameplay.random, "random", fake_random)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    await _beat_boss(db_session, world, d, rooms, cors, sid)

    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.mana_core.revealed and state.mana_core.accessible
    assert state.mana_core.room_id == rooms["core"].id
    assert len(rolls) == 1, "one roll at the boss"
    # the dungeon graph is NOT modified
    corridors = (await db_session.execute(select(DungeonCorridor).where(
        DungeonCorridor.to_room_id == rooms["core"].id))).scalars().all()
    assert corridors == []

    await gameplay.interact_with_room(db_session, sid, 10, "enter_mana_core")
    assert (await reload_session(db_session, sid)).current_room_id == rooms["core"].id
    out = await gameplay.interact_with_room(db_session, sid, 10, "search_mana_core")
    assert out.success is True and out.loot_gained[0]["item_id"] == 999
    assert len(rolls) == 1, "the search does not roll again"
    s = await reload_session(db_session, sid)
    assert s.current_room_id == rooms["boss"].id, "party is back at the boss chest"
    dungeon = (await db_session.execute(select(Dungeon).where(Dungeon.id == d.id))).scalar_one()
    assert dungeon.is_active is False

    await gameplay.interact_with_room(db_session, sid, 10, "open_chest")
    s = await reload_session(db_session, sid)
    assert s.status == "completed"
    assert await _inventory(db_session, sid) == [(77, 2), (999, 1)]


async def test_mana_core_not_revealed_when_roll_fails(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session, mana_core=True, mana_core_chance=0.3, mana_core_item_id=999)
    monkeypatch.setattr(gameplay.random, "random", lambda: 0.9)
    st = await enter_solo(db_session, d)
    await _beat_boss(db_session, world, d, rooms, cors, st.session_id)
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    assert state.mana_core.revealed is False and state.mana_core.accessible is False
    with pytest.raises(HTTPException):
        await gameplay.interact_with_room(db_session, st.session_id, 10, "enter_mana_core")


# ---------------------------------------------------------------- map payload

async def test_map_payload_has_positions_grid_and_reliability(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    room = (await db_session.execute(select(DungeonRoom).where(DungeonRoom.id == rooms["treasure"].id))).scalar_one()
    room.grid_w, room.grid_d = 5, 6
    await db_session.commit()
    st = await enter_solo(db_session, d)
    assert st.current_room.grid_w == 3 and st.current_room.grid_d == 4
    assert st.current_room.is_mana_core_room is False
    assert st.stability_type == "static"
    ex = {e.to_room_id: e for e in st.current_room.exits}
    assert ex[rooms["treasure"].id].grid_w == 5 and ex[rooms["treasure"].id].grid_d == 6
    assert ex[rooms["treasure"].id].to_room_name == "???" and ex[rooms["treasure"].id].explored is False
    assert all(e.reliability == "reliable" for e in st.current_room.exits)

    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    assert state.current_room.grid_w == 5
    explored = {r.id: r for r in state.explored_rooms}
    assert explored[rooms["entrance"].id].grid_w == 3 and explored[rooms["entrance"].id].position_x == 0.0
    assert explored[rooms["entrance"].id].is_entrance is True
    assert explored[rooms["entrance"].id].mob_count is None, "only battle rooms count enemies"
    assert rooms["battle"].id not in explored, "fog of war"
    assert {c.corridor_id for c in state.explored_corridors} == {cors["c4"].id}
    # Doors the party has seen stay on the map, even from rooms it has left — without giving the rooms away.
    seen = {d.corridor_id: d for d in state.seen_doors}
    entrance_exits = {cors[k].id for k in ("c1", "c3", "c5", "c6", "c7", "c8")}
    assert entrance_exits <= set(seen), "the entrance's other doors are remembered"
    assert seen[cors["c1"].id].from_room_id == rooms["entrance"].id
    assert all(d.to_room_id not in explored for d in state.seen_doors)
    assert not hasattr(next(iter(seen.values())), "room_type")
    assert state.abandon_at is not None and state.finalized is False
