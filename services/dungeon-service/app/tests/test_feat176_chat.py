"""FEAT-176: the run's chat and log."""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import chat
import gameplay
import session_state
from models import DungeonCorridor
from dungeon_harness import (  # noqa: F401
    fake_redis, world, build_dungeon, enter_solo, reload_session,
)


async def _lines(sid):
    return await chat.history(sid)


async def test_members_talk_and_everyone_sees_it(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    entry = await gameplay.chat_say(db_session, sid, 10, "  Идём   в лавку!  ")
    assert entry.kind == "say" and entry.text == "Идём в лавку!" and entry.character_id == 10
    assert world.events_of("chat_message")[-1]["data"]["text"] == "Идём в лавку!"
    history = await gameplay.chat_history(db_session, sid, 10)
    assert history[-1].text == "Идём в лавку!"


async def test_chat_is_checked(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    sid = st.session_id
    for bad in ("   ", "я" * (chat.CHAT_MAX_LEN + 1)):
        with pytest.raises(HTTPException) as exc:
            await gameplay.chat_say(db_session, sid, 10, bad)
        assert exc.value.status_code == 400
    await gameplay.chat_say(db_session, sid, 10, "раз")
    with pytest.raises(HTTPException) as exc:
        await gameplay.chat_say(db_session, sid, 10, "два")
    assert exc.value.status_code == 429
    with pytest.raises(HTTPException):
        await gameplay.chat_say(db_session, sid, 11, "чужой")  # not in the run


async def test_the_log_tells_moves_and_traps_with_damage(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    c = (await db_session.execute(select(DungeonCorridor).where(DungeonCorridor.id == cors["c7"].id))).scalar_one()
    c.trap_chance = 1.0
    c.trap_config = {"stat_check": "agility", "difficulty": 99, "fail_damage": 7}
    await db_session.commit()
    st = await enter_solo(db_session, d)
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    texts = [(e["kind"], e["tone"], e["text"]) for e in await _lines(st.session_id)]
    move = next(i for i, (_, _, t) in enumerate(texts) if t.startswith("Отряд идёт из «Entrance» в «Rest»"))
    trap = next(i for i, (_, tone, t) in enumerate(texts) if tone == "bad" and "Ловушка" in t and "−7" in t)
    assert move < trap  # set off first, then the trap on the way
    assert "Урон: 7." not in texts[trap][2]  # who took how much, not the trap's total


async def test_the_log_tells_an_ambush_and_who_is_busy(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)
    c = (await db_session.execute(select(DungeonCorridor).where(DungeonCorridor.id == cors["c7"].id))).scalar_one()
    c.random_battle_chance = 1.0
    c.random_battle_mob_ids = [1]
    await db_session.commit()
    st = await enter_solo(db_session, d)
    await gameplay.start_challenge(db_session, st.session_id, 10, "shield", None, "roll")
    await gameplay.move_to_room(db_session, st.session_id, 10, cors["c7"].id)
    texts = [e["text"] for e in await _lines(st.session_id)]
    assert any("щит" in t for t in texts)
    assert any(t.startswith("По дороге в «Rest» на отряд напали!") and "−" in t for t in texts)


async def test_the_chat_keeps_the_newest_lines(db_session, world, monkeypatch):
    d, rooms, cors = await build_dungeon(db_session)
    st = await enter_solo(db_session, d)
    for i in range(chat.CHAT_KEEP + 5):
        await chat.log(st.session_id, f"строка {i}")
    lines = await _lines(st.session_id)
    assert len(lines) == chat.CHAT_KEEP and lines[-1]["text"] == f"строка {chat.CHAT_KEEP + 4}"


def test_the_log_listens_to_the_run():
    import ws_manager
    assert chat.from_event in ws_manager.listeners


async def test_the_state_gives_each_floor_s_frame(db_session, world):
    d, rooms, cors = await build_dungeon(db_session)  # entrance at (0, 0), battle at (100, 0): cells 0 and 1
    st = await enter_solo(db_session, d)
    state = await gameplay.get_session_state(db_session, st.session_id, 10)
    assert [(e.floor, e.min_col, e.max_col, e.min_row, e.max_row) for e in state.extents] == [(1, 0, 1, 0, 0)]

