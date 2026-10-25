"""FEAT-176: the warrior's own — the party shield and holding up a gate."""

import random

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import challenges
import gameplay
import http_clients
import session_state
from models import DungeonCorridor
from dungeon_harness import (  # noqa: F401
    fake_redis, world, build_dungeon, enter_solo, reload_session,
)


def _parry_all(params):
    """Turn the shield to each blow a little before it lands."""
    return [(b["at_ms"] - 100) * challenges.SHIELD_CODE + b["side"] for b in params["blows"]]


def _hold_gate(params):
    """Press and release so the gate stays in the middle of its band."""
    lo, hi = params["zone"]
    mid = (lo + hi) / 2
    level, speed, holding, toggles = challenges.GATE_START, 0.0, False, []
    t = 0
    while t < params["time_limit_ms"]:
        want = level < mid
        if want != holding:
            toggles.append(t)
            holding = want
        level, speed = challenges.gate_step(params, level, speed, holding, t)
        t += challenges.GATE_TICK_MS
    return toggles


# ---------------------------------------------------------------- pure rules

def test_the_shield_counts_the_blows_turned_aside():
    params = challenges.shield_params(20, 12, False, random.Random(1))
    blows = len(params["blows"])
    assert challenges.shield_verdict(params, _parry_all(params), 10 ** 9) == (blows, blows)
    assert challenges.shield_plausible(params, _parry_all(params))
    idle, _ = challenges.shield_verdict(params, [], 10 ** 9)
    assert idle == sum(1 for b in params["blows"] if b["side"] == params["start_side"])
    # Blows that had not landed yet were never met.
    first_two = params["blows"][1]["at_ms"]
    assert challenges.shield_verdict(params, _parry_all(params), first_two)[0] == 2
    assert not challenges.shield_plausible(params, [5 * challenges.SHIELD_CODE + 3])
    assert not challenges.shield_plausible(params, [1000 * challenges.SHIELD_CODE, 1010 * challenges.SHIELD_CODE])


def test_someone_else_s_shield_sees_blows_later_and_takes_more():
    warrior = challenges.shield_params(12, 12, False, random.Random(2))
    other = challenges.shield_params(12, 12, True, random.Random(2))
    assert len(other["blows"]) == len(warrior["blows"]) + challenges.SHIELD_OFF_CLASS_BLOWS
    assert other["warn_ms"] < warrior["warn_ms"]


def test_the_gate_slams_if_let_go_and_is_propped_if_held():
    params = challenges.gate_params(20, 12, False, random.Random(3))
    assert challenges.gate_verdict(params, [], 10 ** 9) == (False, "broke")
    toggles = _hold_gate(params)
    assert challenges.gate_plausible(toggles)
    assert challenges.gate_verdict(params, toggles, 10 ** 9) == (True, "open")
    # Sent before the holding could really have been done.
    assert challenges.gate_verdict(params, toggles, 1000) == (False, "short")
    assert not challenges.gate_plausible([100, 110])


def test_someone_else_s_gate_has_a_narrower_band_held_longer():
    warrior = challenges.gate_params(12, 12, False, random.Random(4))
    other = challenges.gate_params(12, 12, True, random.Random(4))
    width = lambda p: p["zone"][1] - p["zone"][0]  # noqa: E731
    assert width(other) < width(warrior)
    assert other["hold_ms"] == warrior["hold_ms"] + challenges.GATE_OFF_CLASS_HOLD_MS


def test_gate_shapes_are_validated():
    from schemas import validate_passage_config
    assert validate_passage_config({"gate": {"look": "slab", "difficulty": 14, "fail_damage": 5}})
    for bad in ({"gate": {"look": "door"}}, {"gate": {"look": "grate", "cost": -1}},
                {"gate": {"look": "grate"}, "secret": {"kind": "rubble"}}):
        with pytest.raises(ValueError):
            validate_passage_config(bad)


# ---------------------------------------------------------------- in the run

async def _played_a_minute(sid, cid):
    ch = await session_state.get_challenge(sid, cid)
    ch["issued_at"] -= 60000
    await session_state.set_challenge(sid, cid, ch, 600)


async def _party_run(db, world):
    d, rooms, cors = await build_dungeon(db)
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11]}
    st = await gameplay.start_run(db, d.id, 10, 1, party=True)
    return d, rooms, cors, st.session_id


async def _corridor(db, corridor_id, **fields):
    c = (await db.execute(select(DungeonCorridor).where(DungeonCorridor.id == corridor_id))).scalar_one()
    for k, v in fields.items():
        setattr(c, k, v)
    await db.commit()


async def _raise_shield(db, sid, cid):
    started = await gameplay.start_challenge(db, sid, cid, "shield", None, "game")
    await _played_a_minute(sid, cid)
    return await gameplay.finish_challenge(db, sid, cid, started.challenge_id, _parry_all(started.params))


async def test_the_shield_is_raised_once_and_seen_by_all(db_session, world):
    d, rooms, cors, sid = await _party_run(db_session, world)
    result = await _raise_shield(db_session, sid, 11)
    assert result.passed and result.block == 1.0 and "наготове" in result.message
    assert world.characters[11]["stamina"] == 100 - gameplay.SHIELD_COST
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.shield.character_id == 11 and state.shield.block == 1.0
    assert world.events_of("challenge_finished")[-1]["data"]["kind"] == "shield"
    with pytest.raises(HTTPException) as exc:
        await gameplay.start_challenge(db_session, sid, 10, "shield", None, "game")
    assert exc.value.status_code == 409


async def test_the_shield_takes_the_trap_alone(db_session, world):
    d, rooms, cors, sid = await _party_run(db_session, world)
    await _raise_shield(db_session, sid, 11)
    await gameplay.vote_route(db_session, sid, 11, cors["c5"].id, False)
    resp = await gameplay.move_to_room(db_session, sid, 10, cors["c5"].id)  # the trap room: 30, never spotted
    assert not resp.room_event["passed"] and resp.room_event["damage"] == 8  # 30 at a quarter
    assert world.characters[11]["hp"] == 92 and world.characters[10]["hp"] == 100
    assert "на щит" in resp.room_event["message"]
    assert (await gameplay.get_session_state(db_session, sid, 10)).shield is None  # lowered after the move


async def test_a_shield_stays_behind_in_its_room(db_session, world):
    d, rooms, cors, sid = await _party_run(db_session, world)
    await _raise_shield(db_session, sid, 11)
    s = await reload_session(db_session, sid)
    await session_state.set_shield(sid, {"character_id": 11, "room_id": rooms["rest"].id, "block": 1.0})
    assert (await gameplay.get_session_state(db_session, sid, 10)).shield is None
    assert s.current_room_id == rooms["entrance"].id


async def test_an_ambush_strikes_everyone_first(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _corridor(db_session, cors["c7"].id, random_battle_chance=1.0, random_battle_mob_ids=[1])
    st = await enter_solo(db_session, d)
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    assert resp.corridor_event.type == "battle" and "Первый удар" in resp.corridor_event.message
    assert world.characters[10]["hp"] == 100 - gameplay.AMBUSH_STRIKE_DAMAGE


async def test_an_ambush_meets_the_shield(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    await _corridor(db_session, cors["c7"].id, random_battle_chance=1.0, random_battle_mob_ids=[1])
    st = await enter_solo(db_session, d)
    world.characters[10]["stats"] = {"strength": 20}
    monkeypatch.setattr(challenges.random, "randint", lambda a, b: 0)
    rolled = await gameplay.start_challenge(db_session, st.session_id, 10, "shield", None, "roll")
    assert rolled.result.block == gameplay.SHIELD_ROLL_BLOCK_OK
    resp = await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    assert "на щит" in resp.corridor_event.message
    assert world.characters[10]["hp"] == 96  # 10 less 60%


async def test_an_ambush_that_cannot_start_gives_its_blow_back(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    await _corridor(db_session, cors["c7"].id, random_battle_chance=1.0, random_battle_mob_ids=[1])
    st = await enter_solo(db_session, d)

    async def broken(*a, **kw):
        raise HTTPException(status_code=503, detail="Боевая система недоступна")
    monkeypatch.setattr(http_clients, "create_dungeon_battle", broken)
    with pytest.raises(HTTPException):
        await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    assert world.characters[10]["hp"] == 100 and world.characters[10]["stamina"] == 100


async def test_a_gate_bars_the_way_until_propped(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _corridor(db_session, cors["c4"].id, passage_config={"gate": {"look": "grate", "cost": 3}})
    st = await enter_solo(db_session, d)  # a warrior by default
    sid = st.session_id
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert next(e for e in state.current_room.exits if e.corridor_id == cors["c4"].id).gate == "grate"
    with pytest.raises(HTTPException) as exc:
        await gameplay.move_to_room(db_session, sid, 10, cors["c4"].id)
    assert exc.value.status_code == 409 and "решётка" in exc.value.detail

    started = await gameplay.start_challenge(db_session, sid, 10, "gate", cors["c4"].id, "game")
    assert not started.off_class and started.stamina_consumed == 3
    await _played_a_minute(sid, 10)
    result = await gameplay.finish_challenge(db_session, sid, 10, started.challenge_id, _hold_gate(started.params))
    assert result.passed and "подпирает" in result.message
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert next(e for e in state.current_room.exits if e.corridor_id == cors["c4"].id).gate is None
    resp = await gameplay.move_to_room(db_session, sid, 10, cors["c4"].id)
    assert resp.new_room.id == rooms["treasure"].id


async def test_a_slammed_gate_hurts_whoever_held_it(db_session, world, monkeypatch):
    d, rooms, cors, sid = await _party_run(db_session, world)
    await _corridor(db_session, cors["c4"].id, passage_config={"gate": {"look": "slab", "fail_damage": 15}})
    world.characters[11]["class_id"] = challenges.CLASS_MAGE
    started = await gameplay.start_challenge(db_session, sid, 11, "gate", cors["c4"].id, "game")
    assert started.off_class
    await _played_a_minute(sid, 11)
    result = await gameplay.finish_challenge(db_session, sid, 11, started.challenge_id, [])
    assert not result.passed and result.outcome == "broke" and "Плита" in result.message and "Урон: 15" in result.message
    assert world.characters[11]["hp"] == 85 and world.characters[10]["hp"] == 100

    monkeypatch.setattr(challenges.random, "randint", lambda a, b: -5)
    rolled = await gameplay.start_challenge(db_session, sid, 11, "gate", cors["c4"].id, "roll")
    assert not rolled.result.passed and world.characters[11]["hp"] == 70
    assert cors["c4"].id not in ((await reload_session(db_session, sid)).unlocked_corridor_ids or [])


async def test_the_state_says_where_an_ambush_caught_the_party(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _corridor(db_session, cors["c7"].id, random_battle_chance=1.0, random_battle_mob_ids=[1])
    st = await enter_solo(db_session, d)
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    assert state.phase == gameplay.PHASE_IN_BATTLE
    assert state.ambush.corridor_id == cors["c7"].id
    assert state.ambush.from_room_id == rooms["entrance"].id and state.ambush.to_room_id == rooms["rest"].id
