"""FEAT-176: magic seals, dark rooms, searching a room, the watch at a rest."""

import random

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import challenges
import gameplay
import session_state
from models import Dungeon, DungeonCorridor, DungeonRoom
from dungeon_harness import (  # noqa: F401
    fake_redis, world, build_dungeon, enter_solo, reload_session,
)


# ---------------------------------------------------------------- pure rules

def test_the_sigil_is_a_star_of_distinct_nodes():
    for seed in range(30):
        public, hidden = challenges.seal_params(14, 12, seed % 2 == 0, random.Random(seed))
        path = hidden["path"]
        assert len(path) == public["steps"] + 1 and len(set(path)) == len(path)
        assert all(not challenges._ring_neighbours(a, b) for a, b in zip(path, path[1:]))
        assert path[1] in public["pulsing"] and public["start"] == path[0]


def test_tracing_the_sigil_and_a_spark():
    public, hidden = challenges.seal_params(12, 12, False, random.Random(1))
    assert public["mistakes"] == 1
    wrong = next(n for n in hidden["pulsing"] if n != hidden["path"][1])
    ok, over, pulsing = challenges.seal_trace(public, hidden, wrong, random.Random(2))
    assert not ok and over is None and wrong not in pulsing  # ruled out, one slip forgiven
    for step in range(1, public["steps"] + 1):
        ok, over, pulsing = challenges.seal_trace(public, hidden, hidden["path"][step], random.Random(step))
        assert ok
    assert over == "open"
    with pytest.raises(ValueError):
        challenges.seal_trace(public, {**hidden, "pulsing": [0]}, 5)


def test_someone_else_s_seal_breaks_at_the_first_spark():
    public, hidden = challenges.seal_params(12, 12, True, random.Random(3))
    assert public["mistakes"] == 0 and len(hidden["pulsing"]) == 3
    wrong = next(n for n in hidden["pulsing"] if n != hidden["path"][1])
    assert challenges.seal_trace(public, hidden, wrong)[:2] == (False, "broke")


def test_traces_point_the_way():
    assert challenges.way_towards(2, 2, 2, 0) == 0   # up
    assert challenges.way_towards(2, 2, 4, 2) == 2   # right
    assert challenges.way_towards(2, 2, 2, 3) == 4   # down
    assert challenges.way_towards(2, 2, 0, 0) == 7   # up-left
    public, hidden = challenges.search_params(30, 12, False, True, random.Random(4))
    hidden["honesty"] = 1.0
    tx, ty = hidden["target"]
    x, y = (tx + 3) % public["cols"], ty
    way, over = challenges.search_probe(public, hidden, x, y)
    assert way == challenges.way_towards(x, y, tx, ty) and over is None
    assert challenges.search_probe(public, hidden, tx, ty) == (None, "open")
    with pytest.raises(ValueError):
        challenges.search_probe(public, hidden, x, y)  # looked already


def test_nothing_to_find_where_there_is_no_stash():
    public, hidden = challenges.search_params(12, 12, True, False, random.Random(5))
    over = None
    for i in range(public["probes"]):
        _, over = challenges.search_probe(public, hidden, i % public["cols"], i // public["cols"])
    assert hidden["target"] is None and over == "broke"


def test_feat176_shapes_are_validated():
    from schemas import validate_loot_list, validate_passage_config, validate_room_config
    assert validate_passage_config({"seal": {"difficulty": 14}})
    with pytest.raises(ValueError):
        validate_passage_config({"seal": {"cost": -1}})
    with pytest.raises(ValueError):
        validate_passage_config({"seal": {}, "gate": {"look": "grate"}})
    assert validate_room_config("battle", {"dark": True, "stash": {"items": [{"item_id": 3, "chance": 0.5}]}})
    assert validate_room_config("rest", {"ambush_chance": 0.3, "ambush_mob_ids": [1]})
    for rtype, bad in (("battle", {"dark": "yes"}), ("rest", {"ambush_chance": 2}),
                       ("battle", {"stash": {"items": [{"item_id": 0}]}})):
        with pytest.raises(ValueError):
            validate_room_config(rtype, bad)
    with pytest.raises(ValueError):
        validate_loot_list([{"item_id": 5, "quantity": 0}], "search_loot")


# ---------------------------------------------------------------- in the run

async def _corridor(db, corridor_id, **fields):
    c = (await db.execute(select(DungeonCorridor).where(DungeonCorridor.id == corridor_id))).scalar_one()
    for k, v in fields.items():
        setattr(c, k, v)
    await db.commit()


async def _room(db, room_id, **cfg):
    r = (await db.execute(select(DungeonRoom).where(DungeonRoom.id == room_id))).scalar_one()
    r.room_config = {**(r.room_config or {}), **cfg}
    await db.commit()


async def _hidden(sid, cid):
    return (await session_state.get_challenge(sid, cid))["hidden"]


async def test_a_seal_bars_the_way_until_broken(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _corridor(db_session, cors["c4"].id, passage_config={"seal": {"cost": 3}})
    world.characters[10]["class_id"] = challenges.CLASS_MAGE
    st = await enter_solo(db_session, d)
    sid = st.session_id
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert next(e for e in state.current_room.exits if e.corridor_id == cors["c4"].id).sealed
    with pytest.raises(HTTPException) as exc:
        await gameplay.move_to_room(db_session, sid, 10, cors["c4"].id)
    assert exc.value.status_code == 409 and "печатью" in exc.value.detail

    started = await gameplay.start_challenge(db_session, sid, 10, "seal", cors["c4"].id, "game")
    assert not started.off_class and started.stamina_consumed == 3 and "path" not in started.params
    path = (await _hidden(sid, 10))["path"]
    step = None
    for node in path[1:]:
        step = await gameplay.step_challenge(db_session, sid, 10, started.challenge_id, index=node)
        assert step.safe
    assert step.result.passed and "печать" in step.result.message
    resp = await gameplay.move_to_room(db_session, sid, 10, cors["c4"].id)
    assert resp.new_room.id == rooms["treasure"].id


async def test_a_seal_strikes_back(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _corridor(db_session, cors["c4"].id, passage_config={"seal": {"fail_damage": 20}})
    st = await enter_solo(db_session, d)  # a warrior: no slip forgiven
    sid = st.session_id
    started = await gameplay.start_challenge(db_session, sid, 10, "seal", cors["c4"].id, "game")
    hidden = await _hidden(sid, 10)
    wrong = next(n for n in hidden["pulsing"] if n != hidden["path"][1])
    step = await gameplay.step_challenge(db_session, sid, 10, started.challenge_id, index=wrong)
    assert not step.result.passed and "Урон: 20" in step.result.message
    assert world.characters[10]["hp"] == 80


async def test_in_the_dark_the_ways_are_unknown_and_a_torch_helps(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _room(db_session, rooms["entrance"].id, dark=True)
    st = await enter_solo(db_session, d)  # a warrior: a torch
    sid = st.session_id
    await gameplay.move_to_room(db_session, sid, 10, cors["c7"].id)  # see the rest room
    await gameplay.move_to_room(db_session, sid, 10, cors["c7"].id)  # and come back
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.current_room.dark and state.current_room.dark_room
    rest_exit = next(e for e in state.current_room.exits if e.corridor_id == cors["c7"].id)
    assert rest_exit.to_room_name == "???" and not rest_exit.explored
    with pytest.raises(HTTPException) as exc:
        await gameplay.start_challenge(db_session, sid, 10, "search", None, "roll")
    assert "темноте" in exc.value.detail

    lit = await gameplay.light_room(db_session, sid, 10)
    assert lit.how == "torch" and lit.stamina_consumed == gameplay.TORCH_COST
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert not state.current_room.dark
    assert next(e for e in state.current_room.exits if e.corridor_id == cors["c7"].id).to_room_name == "Rest"
    await gameplay.move_to_room(db_session, sid, 10, cors["c7"].id)
    await gameplay.move_to_room(db_session, sid, 10, cors["c7"].id)
    assert (await gameplay.get_session_state(db_session, sid, 10)).current_room.dark  # the torch stayed behind


async def test_a_mage_s_light_lasts_the_run(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _room(db_session, rooms["entrance"].id, dark=True)
    world.characters[10]["class_id"] = challenges.CLASS_MAGE
    st = await enter_solo(db_session, d)
    sid = st.session_id
    lit = await gameplay.light_room(db_session, sid, 10)
    assert lit.how == "spell" and lit.stamina_consumed == gameplay.LIGHT_SPELL_COST
    await gameplay.move_to_room(db_session, sid, 10, cors["c7"].id)
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert not next(r for r in state.explored_rooms if r.id == rooms["entrance"].id).dark
    await gameplay.move_to_room(db_session, sid, 10, cors["c7"].id)
    assert not (await gameplay.get_session_state(db_session, sid, 10)).current_room.dark
    with pytest.raises(HTTPException):
        await gameplay.light_room(db_session, sid, 10)


async def test_a_trap_in_the_dark_strikes_harder(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _room(db_session, rooms["trap"].id, dark=True)
    st = await enter_solo(db_session, d)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c5"].id)
    assert resp.room_event["damage"] == 45 and "тьме" in resp.room_event["message"]
    assert world.characters[10]["hp"] == 55


async def test_searching_finds_the_stash_once(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    await _room(db_session, rooms["entrance"].id, stash={"items": [{"item_id": 44, "quantity": 2, "chance": 1}]})
    world.characters[10]["stats"] = {"agility": 20}
    st = await enter_solo(db_session, d)
    sid = st.session_id
    monkeypatch.setattr(challenges.random, "randint", lambda a, b: 0)
    rolled = await gameplay.start_challenge(db_session, sid, 10, "search", None, "roll")
    assert rolled.result.passed and rolled.result.loot[0]["item_id"] == 44 and "тайник" in rolled.result.message
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.current_room.searched and any(i.item_id == 44 and i.quantity == 2 for i in state.group_inventory)
    with pytest.raises(HTTPException) as exc:
        await gameplay.start_challenge(db_session, sid, 10, "search", None, "roll")
    assert exc.value.status_code == 409


async def test_the_search_game_follows_the_traces(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _room(db_session, rooms["entrance"].id, stash={"items": [{"item_id": 44, "chance": 1}]})
    world.characters[10]["class_id"] = challenges.CLASS_ROGUE
    st = await enter_solo(db_session, d)
    sid = st.session_id
    started = await gameplay.start_challenge(db_session, sid, 10, "search", None, "game")
    assert "target" not in started.params and not started.off_class
    tx, ty = (await _hidden(sid, 10))["target"]
    step = await gameplay.step_challenge(db_session, sid, 10, started.challenge_id, x=tx, y=ty)
    assert step.result.passed and step.result.loot


async def test_a_lucky_find_even_without_a_stash(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    dungeon = (await db_session.execute(select(Dungeon).where(Dungeon.id == d.id))).scalar_one()
    dungeon.search_loot = [{"item_id": 91, "quantity": 1, "chance": 1}]
    await db_session.commit()
    st = await enter_solo(db_session, d)
    monkeypatch.setattr(gameplay.random, "random", lambda: 0.0)
    started = await gameplay.start_challenge(db_session, st.session_id, 10, "search", None, "game")
    result = await gameplay.finish_challenge(db_session, st.session_id, 10, started.challenge_id, [])
    assert result.loot[0]["item_id"] == 91 and "Зато" in result.message


async def _rest(db, world, *, raid=1.0):
    d, rooms, cors = await build_dungeon(db)
    await _room(db, rooms["rest"].id, ambush_chance=raid, ambush_mob_ids=[1])
    st = await enter_solo(db, d)
    sid = st.session_id
    await gameplay.move_to_room(db, sid, 10, cors["c7"].id)
    world.characters[10]["hp"] = 50
    await gameplay.interact_with_room(db, sid, 10, "start_rest")
    return sid


async def test_an_alert_watch_turns_the_raid_away(db_session, world, monkeypatch):
    sid = await _rest(db_session, world)
    world.characters[10]["stats"] = {"strength": 20}
    monkeypatch.setattr(challenges.random, "randint", lambda a, b: 0)
    with pytest.raises(HTTPException):
        await gameplay.start_challenge(db_session, sid, 10, "watch", None, "game")
    watch = await gameplay.start_challenge(db_session, sid, 10, "watch", None, "roll")
    assert watch.result.passed
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.current_room.watch.character_id == 10 and state.current_room.watch.passed
    done = await gameplay.interact_with_room(db_session, sid, 10, "complete_rest")
    assert "тревогу" in done.message and world.characters[10]["hp"] == 80


async def test_without_a_watch_the_raid_ruins_the_rest(db_session, world):
    sid = await _rest(db_session, world)
    done = await gameplay.interact_with_room(db_session, sid, 10, "complete_rest")
    assert "напали" in done.message and "Дозорного не было" in done.message
    assert world.characters[10]["hp"] == 40  # struck, not healed
    assert (await session_state.get_session_state(sid))["phase"] == gameplay.PHASE_IN_BATTLE


async def test_a_quiet_night_without_a_raid(db_session, world):
    sid = await _rest(db_session, world, raid=0.0)
    done = await gameplay.interact_with_room(db_session, sid, 10, "complete_rest")
    assert "Отдых завершён" in done.message and world.characters[10]["hp"] == 80


def test_the_true_node_pulses_in_time_and_the_false_ones_off_it():
    public, hidden = challenges.seal_params(12, 12, False, random.Random(8))
    true_node = hidden["path"][1]
    offsets = dict(zip(public["pulsing"], public["offsets"]))
    assert offsets[true_node] == 0 and all(abs(o) >= challenges.SEAL_OFFSET_MIN * 0.8
                                           for n, o in offsets.items() if n != true_node)
    sharp = challenges.seal_params(30, 12, False, random.Random(8))[1]["offset"]
    other = challenges.seal_params(12, 12, True, random.Random(8))[1]["offset"]
    assert sharp > hidden["offset"] > other
    # The next step brings new offsets for the nodes resonating then.
    ok, over, pulsing = challenges.seal_trace(public, hidden, true_node, random.Random(9))
    assert ok and len(hidden["offsets"]) == len(pulsing) and hidden["offsets"][pulsing.index(hidden["path"][2])] == 0
