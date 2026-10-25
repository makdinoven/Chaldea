"""FEAT-176: secret ways out — a hidden mechanism, an illusory wall, a cave-in."""

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

def test_runes_are_repeated_in_order_with_a_slip_allowed():
    params = challenges.runes_params(20, 12, False, random.Random(1))
    seq = params["sequence"]
    assert challenges.runes_verdict(params, seq) == (True, "open")
    wrong = (seq[0] + 1) % params["glyphs"]
    assert challenges.runes_verdict(params, [wrong] + seq) == (True, "open")  # one slip is forgiven
    assert challenges.runes_verdict(params, [wrong, wrong]) == (False, "broke")
    assert challenges.runes_verdict(params, seq[:-1]) == (False, "short")
    assert not challenges.runes_plausible(params, [99])


def test_runes_are_longer_for_someone_else_and_shorter_for_a_sharp_mind():
    mage = challenges.runes_params(12, 12, False, random.Random(2))
    other = challenges.runes_params(12, 12, True, random.Random(2))
    sharp = challenges.runes_params(30, 12, False, random.Random(2))
    assert len(other["sequence"]) == len(mage["sequence"]) + 2 and other["mistakes"] == 0
    assert len(sharp["sequence"]) == len(mage["sequence"]) - 1 or len(mage["sequence"]) == challenges.RUNES_MIN
    assert all(a != b for a, b in zip(mage["sequence"], mage["sequence"][1:]))


def test_the_mechanism_tells_how_far_and_runs_out_of_presses():
    public, hidden = challenges.mechanism_params(12, 12, False, random.Random(3))
    tx, ty = hidden["target"]
    away = (tx + 2) % public["cols"]
    distance, over = challenges.mechanism_probe(public, hidden, away, ty)
    assert distance == abs(away - tx) and over is None
    assert challenges.mechanism_probe(public, hidden, tx, ty) == (0, "open")

    public, hidden = challenges.mechanism_params(12, 12, True, random.Random(3))
    tx, ty = hidden["target"]
    for i in range(public["probes"]):
        _, over = challenges.mechanism_probe(public, hidden, (tx + 1) % public["cols"], ty)
    assert over == "broke"
    with pytest.raises(ValueError):
        challenges.mechanism_probe(public, hidden, 99, 0)


def test_the_cave_in_comes_down_on_a_bearing_stone():
    public, hidden = challenges.rubble_params(12, 12, False, random.Random(4))
    safe = [i for i, b in enumerate(hidden["bearing"]) if not b]
    bearing = [i for i, b in enumerate(hidden["bearing"]) if b]
    assert challenges.rubble_pull(public, hidden, bearing[0]) == (False, None)  # the brace holds
    for i in safe[:public["to_clear"] - 1]:
        assert challenges.rubble_pull(public, hidden, i) == (True, None)
    assert challenges.rubble_pull(public, hidden, safe[public["to_clear"] - 1]) == (True, "open")
    with pytest.raises(ValueError):
        challenges.rubble_pull(public, hidden, safe[0])  # already out

    public, hidden = challenges.rubble_params(12, 12, True, random.Random(4))
    bearing = [i for i, b in enumerate(hidden["bearing"]) if b]
    assert public["braces"] == 0
    assert challenges.rubble_pull(public, hidden, bearing[0]) == (False, "broke")


def test_cracks_mostly_tell_the_truth_to_a_strong_warrior():
    rng = random.Random(5)
    honest = total = 0
    for _ in range(200):
        public, hidden = challenges.rubble_params(30, 12, False, rng)
        for crack, bearing in zip(public["cracks"], hidden["bearing"]):
            honest += (crack >= 2) == bearing
            total += 1
    assert honest / total > 0.85


# ---------------------------------------------------------------- in the run

async def _secret(db, corridor_id, kind, **extra):
    c = (await db.execute(select(DungeonCorridor).where(DungeonCorridor.id == corridor_id))).scalar_one()
    c.passage_config = {"secret": {"kind": kind, **extra}}
    await db.commit()


async def _hidden(sid, cid):
    return (await session_state.get_challenge(sid, cid))["hidden"]


async def test_a_secret_way_is_hidden_until_found(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _secret(db_session, cors["c4"].id, "illusion", hint="Стена дрожит.")
    st = await enter_solo(db_session, d)
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    assert cors["c4"].id not in [e.corridor_id for e in state.current_room.exits]
    assert [(s.corridor_id, s.kind, s.hint) for s in state.current_room.secrets] == [(cors["c4"].id, "illusion", "Стена дрожит.")]
    assert cors["c4"].id not in [d_.corridor_id for d_ in state.seen_doors]
    with pytest.raises(HTTPException) as exc:
        await gameplay.move_to_room(db_session, st.session_id, 10, cors["c4"].id)
    assert exc.value.status_code == 400


async def test_the_illusion_dispelled_opens_the_way(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _secret(db_session, cors["c4"].id, "illusion", cost=3)
    world.characters[10]["class_id"] = challenges.CLASS_MAGE
    st = await enter_solo(db_session, d)
    sid = st.session_id
    started = await gameplay.start_challenge(db_session, sid, 10, "illusion", cors["c4"].id, "game")
    assert not started.off_class and started.stamina_consumed == 3
    ch = await session_state.get_challenge(sid, 10)
    ch["issued_at"] -= challenges.runes_min_ms(started.params) + 1000  # the runes have been shown
    await session_state.set_challenge(sid, 10, ch, 600)
    result = await gameplay.finish_challenge(db_session, sid, 10, started.challenge_id, started.params["sequence"])
    assert result.passed and "иллюзию" in result.message
    state = await gameplay.get_session_state(db_session, sid, 10)
    assert cors["c4"].id in [e.corridor_id for e in state.current_room.exits]
    assert state.current_room.secrets == []
    resp = await gameplay.move_to_room(db_session, sid, 10, cors["c4"].id)
    assert resp.new_room.id == rooms["treasure"].id


async def test_the_mechanism_is_found_stone_by_stone(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _secret(db_session, cors["c4"].id, "mechanism")
    st = await enter_solo(db_session, d)
    sid = st.session_id
    started = await gameplay.start_challenge(db_session, sid, 10, "mechanism", cors["c4"].id, "game")
    assert "target" not in started.params  # the lever stays on the server
    tx, ty = (await _hidden(sid, 10))["target"]
    other = ((tx + 1) % started.params["cols"], ty)
    step = await gameplay.step_challenge(db_session, sid, 10, started.challenge_id, x=other[0], y=other[1])
    assert step.distance == abs(other[0] - tx) and step.result is None
    step = await gameplay.step_challenge(db_session, sid, 10, started.challenge_id, x=tx, y=ty)
    assert step.distance == 0 and step.result.passed
    assert cors["c4"].id in ((await reload_session(db_session, sid)).unlocked_corridor_ids or [])


async def test_a_cave_in_hurts_whoever_brings_it_down(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _secret(db_session, cors["c4"].id, "rubble", fail_damage=25)
    st = await enter_solo(db_session, d)  # a warrior by default
    sid = st.session_id
    started = await gameplay.start_challenge(db_session, sid, 10, "rubble", cors["c4"].id, "game")
    hidden = await _hidden(sid, 10)
    bearing = [i for i, b in enumerate(hidden["bearing"]) if b]
    result = None
    for i in bearing[: started.params["braces"] + 1]:
        step = await gameplay.step_challenge(db_session, sid, 10, started.challenge_id, index=i)
        result = step.result or result
    assert result and not result.passed and "Урон: 25" in result.message
    assert world.characters[10]["hp"] == 75
    assert cors["c4"].id not in ((await reload_session(db_session, sid)).unlocked_corridor_ids or [])


async def test_giving_up_a_stepped_game_and_the_plain_roll(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    await _secret(db_session, cors["c4"].id, "mechanism", difficulty=10)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    started = await gameplay.start_challenge(db_session, sid, 10, "mechanism", cors["c4"].id, "game")
    result = await gameplay.finish_challenge(db_session, sid, 10, started.challenge_id, [])
    assert not result.passed and result.outcome == "short"

    world.characters[10]["stats"] = {"agility": 20}
    monkeypatch.setattr(challenges.random, "randint", lambda a, b: 0)
    rolled = await gameplay.start_challenge(db_session, sid, 10, "mechanism", cors["c4"].id, "roll")
    # A warrior: 20 - 6 still beats 10.
    assert rolled.off_class and rolled.result.passed and rolled.result.rolled == 14


async def test_only_the_secret_s_own_kind_and_room(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    await _secret(db_session, cors["c4"].id, "rubble")
    st = await enter_solo(db_session, d)
    sid = st.session_id
    with pytest.raises(HTTPException) as exc:
        await gameplay.start_challenge(db_session, sid, 10, "illusion", cors["c4"].id, "game")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        await gameplay.start_challenge(db_session, sid, 10, "rubble", cors["c2"].id, "game")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException):
        await gameplay.vote_route(db_session, sid, 10, cors["c4"].id, False)


def test_secret_shapes_are_validated():
    from schemas import validate_passage_config
    assert validate_passage_config({"secret": {"kind": "illusion", "difficulty": 14, "hint": "x"}})
    for bad in ({"secret": {"kind": "door"}}, {"secret": {"kind": "rubble", "cost": -1}},
                {"secret": {"kind": "rubble", "hint": "x" * 400}}):
        with pytest.raises(ValueError):
            validate_passage_config(bad)


def test_the_lower_stones_bear_the_pile_more_often():
    rng = random.Random(10)
    by_row = [0, 0, 0]
    for _ in range(600):
        _, hidden = challenges.rubble_params(12, 12, False, rng)
        assert sum(hidden["bearing"]) == challenges.RUBBLE_BEARING_BASE
        for r, row in enumerate(challenges.RUBBLE_ROWS):
            by_row[r] += sum(hidden["bearing"][i] for i in row) / len(row)
    # Per stone, the bottom row bears most and the top least.
    assert by_row[0] > by_row[1] > by_row[2]

