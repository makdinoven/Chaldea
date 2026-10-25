"""FEAT-176: class challenges — the lock minigame and the plain roll."""

import math
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

def _good_press(pin, woke_at):
    """The first moment after `woke_at` (ms) the pin is inside its window."""
    t = woke_at + challenges.MIN_PRESS_GAP_MS
    while abs(challenges.pin_height(pin, t - woke_at) - pin["center"]) > pin["width"] * 0.9:
        t += 1
    return t


def _bad_press(pin, woke_at, after):
    """The first moment after `after` the pin is outside its window (the grace included)."""
    t = after + challenges.MIN_PRESS_GAP_MS
    while challenges.in_window(pin, t - woke_at):
        t += 1
    return t


def _solve(params):
    presses, woke = [], 0
    for pin in params["pins"]:
        woke = _good_press(pin, woke)
        presses.append(woke)
    return presses


def test_a_steady_hand_opens_the_lock():
    params = challenges.lockpick_params(20, 12, False, random.Random(1))
    assert challenges.lockpick_verdict(params, _solve(params)) == (True, "open")


def test_too_many_strains_break_the_pick():
    params = challenges.lockpick_params(20, 12, False, random.Random(2))
    pin = params["pins"][0]
    presses, t = [], 0
    for _ in range(params["strains"] + 1):
        t = _bad_press(pin, 0, t)
        presses.append(t)
    assert challenges.lockpick_verdict(params, presses) == (False, "broke")


def test_late_presses_run_out_of_time():
    params = challenges.lockpick_params(20, 12, False, random.Random(3))
    assert challenges.lockpick_verdict(params, [params["time_limit_ms"] + 1]) == (False, "time")
    assert challenges.lockpick_verdict(params, []) == (False, "short")


def test_someone_else_s_craft_is_harder():
    rogue = challenges.lockpick_params(20, 12, False, random.Random(4))
    other = challenges.lockpick_params(20, 12, True, random.Random(4))
    assert len(other["pins"]) == len(rogue["pins"]) + 1
    assert other["pins"][0]["width"] < rogue["pins"][0]["width"]
    assert other["strains"] < rogue["strains"]


def test_agility_widens_the_window_and_difficulty_adds_pins():
    clumsy = challenges.lockpick_params(5, 12, False, random.Random(5))
    deft = challenges.lockpick_params(30, 12, False, random.Random(5))
    assert deft["pins"][0]["width"] > clumsy["pins"][0]["width"]
    hard = challenges.lockpick_params(30, 30, False, random.Random(5))
    assert len(hard["pins"]) > len(deft["pins"])


def test_inhuman_presses_are_rejected():
    params = challenges.lockpick_params(20, 12, False, random.Random(6))
    assert not challenges.presses_plausible(params, [100, 120], None)
    assert not challenges.presses_plausible(params, [500, 300], None)
    assert not challenges.presses_plausible(params, [100] * 20, None)
    assert not challenges.presses_plausible(params, [9000], elapsed_ms=1000)
    assert challenges.presses_plausible(params, [500, 900], elapsed_ms=2000)


# ---------------------------------------------------------------- in the run

async def _lock(db, corridor_id, **cfg):
    c = (await db.execute(select(DungeonCorridor).where(DungeonCorridor.id == corridor_id))).scalar_one()
    c.lock_config = {"key": "copper", **cfg}
    await db.commit()


async def _played_a_minute(sid, cid):
    """The game began a minute ago: presses that far in are plausible."""
    ch = await session_state.get_challenge(sid, cid)
    ch["issued_at"] -= 60000
    await session_state.set_challenge(sid, cid, ch, 600)


async def _party_run(db, world):
    d, rooms, cors = await build_dungeon(db)
    world.party = {"party_id": 1, "leader_character_id": 10, "member_character_ids": [10, 11]}
    st = await gameplay.start_run(db, d.id, 10, 1, party=True)
    return d, rooms, cors, st.session_id


async def test_any_member_picks_with_their_own_stamina(db_session, world):
    d, rooms, cors, sid = await _party_run(db_session, world)
    await _lock(db_session, cors["c7"].id, difficulty=12, pick_cost=4)
    world.characters[11]["stats"] = {"agility": 20}
    world.characters[11]["class_id"] = challenges.CLASS_ROGUE
    started = await gameplay.start_challenge(db_session, sid, 11, "lockpick", cors["c7"].id, "game")
    assert started.challenge_id and not started.off_class and started.stamina_consumed == 4
    assert world.characters[11]["stamina"] == 96 and world.characters[10]["stamina"] == 100
    assert world.events_of("challenge_started")[-1]["data"]["character_id"] == 11

    await _played_a_minute(sid, 11)
    result = await gameplay.finish_challenge(db_session, sid, 11, started.challenge_id, _solve(started.params))
    assert result.passed and result.outcome == "open"
    assert world.events_of("challenge_finished")[-1]["data"]["passed"] is True
    s = await reload_session(db_session, sid)
    assert cors["c7"].id in (s.unlocked_corridor_ids or [])
    # The game is settled once.
    with pytest.raises(HTTPException) as exc:
        await gameplay.finish_challenge(db_session, sid, 11, started.challenge_id, [])
    assert exc.value.status_code == 404


async def test_a_broken_pick_leaves_the_door_shut(db_session, world):
    d, rooms, cors, sid = await _party_run(db_session, world)
    await _lock(db_session, cors["c7"].id, difficulty=12)
    started = await gameplay.start_challenge(db_session, sid, 10, "lockpick", cors["c7"].id, "game")
    assert started.off_class  # a warrior at a lock
    result = await gameplay.finish_challenge(db_session, sid, 10, started.challenge_id, [])
    assert not result.passed and result.outcome == "short"
    s = await reload_session(db_session, sid)
    assert cors["c7"].id not in (s.unlocked_corridor_ids or [])


async def test_one_member_at_a_lock_at_a_time(db_session, world):
    d, rooms, cors, sid = await _party_run(db_session, world)
    await _lock(db_session, cors["c7"].id, difficulty=12)
    started = await gameplay.start_challenge(db_session, sid, 11, "lockpick", cors["c7"].id, "game")
    with pytest.raises(HTTPException) as exc:
        await gameplay.start_challenge(db_session, sid, 10, "lockpick", cors["c7"].id, "game")
    assert exc.value.status_code == 409 and "Герой11" in exc.value.detail
    await gameplay.finish_challenge(db_session, sid, 11, started.challenge_id, [])
    # Free again once the first gave up.
    again = await gameplay.start_challenge(db_session, sid, 10, "lockpick", cors["c7"].id, "game")
    assert again.challenge_id


async def test_cheating_presses_fail(db_session, world):
    d, rooms, cors, sid = await _party_run(db_session, world)
    await _lock(db_session, cors["c7"].id, difficulty=12)
    started = await gameplay.start_challenge(db_session, sid, 11, "lockpick", cors["c7"].id, "game")
    # Solved, but claimed to have taken far longer than has passed.
    late = [t + 60000 for t in _solve(started.params)]
    started.params["time_limit_ms"] = 10 ** 9
    result = await gameplay.finish_challenge(db_session, sid, 11, started.challenge_id, late)
    assert not result.passed


async def test_a_plain_roll_decides_at_once(db_session, world, monkeypatch):
    d, rooms, cors, sid = await _party_run(db_session, world)
    await _lock(db_session, cors["c7"].id, difficulty=12)
    world.characters[11]["stats"] = {"agility": 12}
    monkeypatch.setattr(challenges.random, "randint", lambda a, b: 0)
    started = await gameplay.start_challenge(db_session, sid, 11, "lockpick", cors["c7"].id, "roll")
    # A warrior: 12 - the off-class penalty falls short of 12.
    assert started.off_class and not started.result.passed
    assert started.result.rolled == 12 - challenges.OFF_CLASS_PENALTY
    world.characters[11]["class_id"] = challenges.CLASS_ROGUE
    started = await gameplay.start_challenge(db_session, sid, 11, "lockpick", cors["c7"].id, "roll")
    assert started.result.passed and started.result.rolled == 12


async def test_the_fallen_and_strangers_cannot_try(db_session, world):
    d, rooms, cors, sid = await _party_run(db_session, world)
    await _lock(db_session, cors["c7"].id, difficulty=12)
    s = await reload_session(db_session, sid)
    next(m for m in s.members if m.character_id == 11).status = "dead"
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await gameplay.start_challenge(db_session, sid, 11, "lockpick", cors["c7"].id, "game")
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        await gameplay.start_challenge(db_session, sid, 99, "lockpick", cors["c7"].id, "game")
    assert exc.value.status_code == 403


def test_a_press_just_after_the_pin_left_the_window_still_counts():
    pin = {"freq": 0.5, "phase": 0.0, "center": 0.0, "width": 0.2}
    params = {"pins": [pin], "strains": 0, "time_limit_ms": 20000}
    # The tip leaves the window (|sin| > 0.2) a little after ~64 ms; 100 ms is within the grace, 200 ms is not.
    assert not challenges.in_window(pin, 200) and challenges.in_window(pin, 100)
    assert challenges.lockpick_verdict(params, [100]) == (True, "open")
    assert challenges.lockpick_verdict(params, [200]) == (False, "broke")


def test_agility_slows_the_pins():
    clumsy = challenges.lockpick_params(5, 15, False, random.Random(6))
    usual = challenges.lockpick_params(15, 15, False, random.Random(6))
    deft = challenges.lockpick_params(30, 15, False, random.Random(6))
    freqs = [[p["freq"] for p in params["pins"]] for params in (clumsy, usual, deft)]
    assert all(c > u > d for c, u, d in zip(*freqs))
    # Slowed by at most 30%, sped up by at most 30%.
    assert all(abs(d - u * 0.7) < 0.002 and abs(c - u * 1.2) < 0.002 for c, u, d in zip(*freqs))

