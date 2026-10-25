"""FEAT-176: looking ahead — scouting a corridor, disarming its trap, reading an event or a portal."""

import random

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import challenges
import gameplay
import session_state
from models import DungeonCorridor
from dungeon_harness import (  # noqa: F401
    fake_redis, world, build_dungeon, enter_solo, reload_session,
)


# ---------------------------------------------------------------- pure rules

def test_the_shadows_see_a_careless_step_and_let_a_careful_one_through():
    params = challenges.shadow_params(20, 12, False, random.Random(1))
    lamp_at = next(i for i, l in enumerate(params["lamps"]) if l)
    # A dash that waits nowhere walks into a lit cell sooner or later.
    lit_t = next(t for t in range(0, 20000, 25) if challenges.shadow_lit(params["lamps"][lamp_at], t))
    dash = [lit_t - 80 * (lamp_at + 1 - i) for i in range(lamp_at + 1)]
    if dash[0] >= 0:
        assert challenges.shadow_verdict(params, dash, 10 ** 9)[1] in ("broke", "short", "time")
    assert challenges.shadow_verdict(params, [], 10 ** 9) == (False, "time")
    assert not challenges.shadow_plausible(params, [100, 110])


def test_rods_show_their_taut_neighbours_and_a_rogue_survives_one_slip():
    public, hidden = challenges.wires_params(12, 12, False, random.Random(2))
    taut = hidden["taut"]
    shown = {i for i, _ in public["shown"]}
    # only what the game lets a player cut: the hints come already cut
    slack = [i for i, t in enumerate(taut) if not t and i not in shown]
    assert shown and hidden["cut"] == sorted(shown)
    ok, near, over = challenges.wires_cut(public, hidden, slack[0])
    assert ok and near == sum(1 for j in (slack[0] - 1, slack[0] + 1) if 0 <= j < len(taut) and taut[j])
    first_taut = taut.index(True)
    assert challenges.wires_cut(public, hidden, first_taut) == (False, None, None)  # one slip forgiven
    for i in slack[1:]:
        ok, near, over = challenges.wires_cut(public, hidden, i)
    assert over == "open"
    public, hidden = challenges.wires_params(12, 12, True, random.Random(3))
    assert public["mistakes"] == 0
    assert challenges.wires_cut(public, hidden, hidden["taut"].index(True))[2] == "broke"


def test_geared_rings_can_always_be_brought_home():
    params = challenges.stars_params(12, 12, False, random.Random(4))
    offsets, turns = list(params["offsets"]), []
    # Solve from the first ring: turning ring r fixes it and moves r + 1 along.
    for r in range(params["rings"]):
        while offsets[r] != 0:
            offsets = challenges.stars_turn(offsets, r)
            turns.append(r)
    assert challenges.stars_verdict(params, turns) == (True, "open")
    assert challenges.stars_verdict(params, turns[:-1]) == (False, "short")
    assert not challenges.stars_plausible(params, [99])


# ---------------------------------------------------------------- in the run

async def _corridor(db, corridor_id, **fields):
    c = (await db.execute(select(DungeonCorridor).where(DungeonCorridor.id == corridor_id))).scalar_one()
    for k, v in fields.items():
        setattr(c, k, v)
    await db.commit()


async def test_scouting_tells_what_waits_ahead(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    await _corridor(db_session, cors["c1"].id, trap_chance=0.5, trap_config={"fail_damage": 5})
    world.characters[10]["stats"] = {"agility": 20}
    st = await enter_solo(db_session, d)
    sid = st.session_id
    monkeypatch.setattr(challenges.random, "randint", lambda a, b: 0)
    res = await gameplay.start_challenge(db_session, sid, 10, "scout", cors["c1"].id, "roll")
    assert res.result.passed and "бой" in res.result.message and "ловушка" in res.result.message
    state = await gameplay.get_session_state(db_session, sid, 10)
    exit_ = next(e for e in state.current_room.exits if e.corridor_id == cors["c1"].id)
    assert exit_.scout.room_type == "battle" and exit_.scout.mob_count == 2 and exit_.scout.trap
    with pytest.raises(HTTPException) as exc:
        await gameplay.start_challenge(db_session, sid, 10, "scout", cors["c1"].id, "roll")
    assert exc.value.status_code == 409


async def test_a_seen_scout_puts_the_corridor_on_guard(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    await _corridor(db_session, cors["c7"].id, random_battle_chance=0.0, random_battle_mob_ids=[1])
    st = await enter_solo(db_session, d)
    sid = st.session_id
    monkeypatch.setattr(challenges.random, "randint", lambda a, b: -5)
    res = await gameplay.start_challenge(db_session, sid, 10, "scout", cors["c7"].id, "roll")
    assert not res.result.passed and world.characters[10]["hp"] == 100 - gameplay.SCOUT_SEEN_DAMAGE
    monkeypatch.setattr(gameplay.random, "random", lambda: 0.1)  # under the alert's bonus
    resp = await gameplay.move_to_room(db_session, sid, 10, cors["c7"].id)
    assert resp.corridor_event.type == "battle"


async def test_a_disarmed_trap_stays_quiet(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    await _corridor(db_session, cors["c7"].id, trap_chance=1.0,
                    trap_config={"stat_check": "agility", "difficulty": 99, "fail_damage": 9})
    world.characters[10]["stats"] = {"agility": 20}
    st = await enter_solo(db_session, d)
    sid = st.session_id
    with pytest.raises(HTTPException):
        await gameplay.start_challenge(db_session, sid, 10, "disarm", cors["c7"].id, "game")  # not found yet
    monkeypatch.setattr(challenges.random, "randint", lambda a, b: 0)
    await gameplay.start_challenge(db_session, sid, 10, "scout", cors["c7"].id, "roll")
    started = await gameplay.start_challenge(db_session, sid, 10, "disarm", cors["c7"].id, "game")
    hidden = (await session_state.get_challenge(sid, 10))["hidden"]
    result = None
    for i, t in enumerate(hidden["taut"]):
        if not t and i not in hidden["cut"]:
            step = await gameplay.step_challenge(db_session, sid, 10, started.challenge_id, index=i)
            result = step.result or result
    assert result.passed and "обезвреживает" in result.message
    resp = await gameplay.move_to_room(db_session, sid, 10, cors["c7"].id)
    assert resp.corridor_event.type == "safe" and world.characters[10]["hp"] == 100


async def test_reading_an_event_shows_where_each_choice_leads(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    world.characters[10]["class_id"] = challenges.CLASS_MAGE
    st = await enter_solo(db_session, d)
    sid = st.session_id
    with pytest.raises(HTTPException):
        await gameplay.start_challenge(db_session, sid, 10, "insight", None, "game")  # nothing to read at the entrance
    await gameplay.move_to_room(db_session, sid, 10, cors["c3"].id)
    started = await gameplay.start_challenge(db_session, sid, 10, "insight", None, "game")
    offsets, turns = list(started.params["offsets"]), []
    for r in range(started.params["rings"]):
        while offsets[r] != 0:
            offsets = challenges.stars_turn(offsets, r)
            turns.append(r)
    ch = await session_state.get_challenge(sid, 10)
    ch["issued_at"] -= 60000
    await session_state.set_challenge(sid, 10, ch, 600)
    result = await gameplay.finish_challenge(db_session, sid, 10, started.challenge_id, turns)
    assert result.passed
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.current_room.room_config_visible["choice_hints"][:3] == ["награда", "опасно", "исцеление"]


async def test_the_party_sees_who_is_in_a_minigame(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    await _corridor(db_session, cors["c7"].id, trap_chance=1.0,
                    trap_config={"stat_check": "agility", "difficulty": 99, "fail_damage": 9})
    world.characters[10]["stats"] = {"agility": 20}
    st = await enter_solo(db_session, d)
    sid = st.session_id
    monkeypatch.setattr(challenges.random, "randint", lambda a, b: 0)
    await gameplay.start_challenge(db_session, sid, 10, "scout", cors["c7"].id, "roll")
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.members[0].busy is None  # a plain roll is over at once
    started = await gameplay.start_challenge(db_session, sid, 10, "disarm", cors["c7"].id, "game")
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.members[0].busy == "disarm"
    # left without a word (the tab closed): no longer shown once its time is well past
    ch = await session_state.get_challenge(sid, 10)
    ch["issued_at"] -= gameplay.BUSY_UNTIMED_MS + gameplay.BUSY_GRACE_MS + 1000
    await session_state.set_challenge(sid, 10, ch, 600)
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.members[0].busy is None
    ch["issued_at"] += gameplay.BUSY_UNTIMED_MS + gameplay.BUSY_GRACE_MS + 1000
    await session_state.set_challenge(sid, 10, ch, 600)
    hidden = ch["hidden"]
    for i, t in enumerate(hidden["taut"]):
        if not t and i not in hidden["cut"]:
            await gameplay.step_challenge(db_session, sid, 10, started.challenge_id, index=i)
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert state.members[0].busy is None


async def test_leaving_the_rods_alone_hurts_nobody(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    await _corridor(db_session, cors["c7"].id, trap_chance=1.0,
                    trap_config={"stat_check": "agility", "difficulty": 99, "fail_damage": 9})
    world.characters[10]["stats"] = {"agility": 20}
    st = await enter_solo(db_session, d)
    sid = st.session_id
    monkeypatch.setattr(challenges.random, "randint", lambda a, b: 0)
    await gameplay.start_challenge(db_session, sid, 10, "scout", cors["c7"].id, "roll")
    started = await gameplay.start_challenge(db_session, sid, 10, "disarm", cors["c7"].id, "game")
    result = await gameplay.finish_challenge(db_session, sid, 10, started.challenge_id, [])
    assert not result.passed and result.outcome == "short" and "взведена" in result.message
    assert world.characters[10]["hp"] == 100


async def test_a_scout_looks_one_way_down_a_corridor(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    await _corridor(db_session, cors["c3"].id, trap_chance=0.5, trap_config={"fail_damage": 1})
    world.characters[10]["stats"] = {"agility": 20}
    st = await enter_solo(db_session, d)
    sid = st.session_id
    monkeypatch.setattr(challenges.random, "randint", lambda a, b: 0)
    await gameplay.start_challenge(db_session, sid, 10, "scout", cors["c3"].id, "roll")
    state = await gameplay.get_session_state(db_session, sid, 10)
    ahead = next(e for e in state.current_room.exits if e.corridor_id == cors["c3"].id)
    assert ahead.scout.room_type == "event"
    await _corridor(db_session, cors["c3"].id, trap_chance=0.0)  # walk through quietly; the scout's word stands
    await gameplay.move_to_room(db_session, sid, 10, cors["c3"].id)
    state = await gameplay.get_session_state(db_session, sid, 10)
    back = next(e for e in state.current_room.exits if e.corridor_id == cors["c3"].id)
    assert back.scout is None  # what lies back that way was never scouted
    # the trap belongs to the corridor: found from the far end, it can be disarmed from this one
    started = await gameplay.start_challenge(db_session, sid, 10, "disarm", cors["c3"].id, "game")
    assert started.challenge_id
