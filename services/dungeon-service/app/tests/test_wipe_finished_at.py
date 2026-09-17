"""
FEAT-164 — a wiped dungeon session must get ``finished_at``.

character-attributes-service reads ``dungeon_sessions.started_at/finished_at``
as the "busy" interval that pauses passive regeneration. A wiped session
without ``finished_at`` collapses to a zero-length interval (regen would be
credited for the whole dungeon run), so the wipe path stamps it.
"""

import copy
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    r.scalars.return_value.all.return_value = [value] if value else []
    return r


def _wipe_battle_state():
    return {
        "runtime": {
            "participants": {
                "1": {"character_id": 200, "team": 1, "hp": 0},
                "2": {"character_id": 201, "team": 1, "hp": 0},
                "3": {"character_id": 300, "team": 2, "hp": 40},
            },
        },
    }


async def _run_wipe(mock_ss, mock_ws, mock_db, session, dungeon, redis_state):
    from gameplay import process_battle_completion

    dead_state = copy.deepcopy(redis_state)
    for info in dead_state["members"].values():
        info["status"] = "dead"
    mock_ss.get_session_state = AsyncMock(side_effect=[redis_state, dead_state])
    mock_ss.update_member_status = AsyncMock()
    mock_ss.update_session_state = AsyncMock()
    mock_ss.clear_active_battle = AsyncMock()
    mock_ws.broadcast_to_session = AsyncMock()

    member = MagicMock()
    results_seq = [_scalar_result(session), _scalar_result(dungeon)]

    def execute_side_effect(stmt, *a, **kw):
        if results_seq:
            return results_seq.pop(0)
        return _scalar_result(member)

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    return await process_battle_completion(mock_db, 100, 777, _wipe_battle_state())


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_wipe_sets_finished_at(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_dungeon, sample_redis_state,
):
    sample_session.started_at = datetime.utcnow() - timedelta(hours=1)
    sample_session.finished_at = None
    before = datetime.utcnow()

    results = await _run_wipe(mock_ss, mock_ws, mock_db, sample_session, sample_dungeon, sample_redis_state)

    assert results["wiped"] is True
    assert sample_session.status == "wiped"
    assert isinstance(sample_session.finished_at, datetime)
    assert sample_session.finished_at.tzinfo is None  # naive UTC like the rest
    assert before <= sample_session.finished_at <= datetime.utcnow()
    assert sample_session.finished_at > sample_session.started_at
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_wipe_keeps_existing_finished_at(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_dungeon, sample_redis_state,
):
    stamped = datetime(2026, 9, 17, 10, 0, 0)
    sample_session.finished_at = stamped

    results = await _run_wipe(mock_ss, mock_ws, mock_db, sample_session, sample_dungeon, sample_redis_state)

    assert results["wiped"] is True
    assert sample_session.finished_at == stamped


@pytest.mark.asyncio
@patch("gameplay.ws_manager")
@patch("gameplay.http_clients")
@patch("gameplay.session_state")
async def test_victory_does_not_set_finished_at(
    mock_ss, mock_http, mock_ws,
    mock_db, sample_session, sample_dungeon, sample_redis_state,
):
    from gameplay import process_battle_completion

    state = {"runtime": {"participants": {
        "1": {"character_id": 200, "team": 1, "hp": 10},
        "2": {"character_id": 300, "team": 2, "hp": 0},
    }}}
    sample_session.finished_at = None
    mock_ss.get_session_state = AsyncMock(return_value=sample_redis_state)
    mock_ss.clear_active_battle = AsyncMock()
    mock_ss.update_member_status = AsyncMock()
    mock_ws.broadcast_to_session = AsyncMock()
    room_obj = MagicMock()
    room_obj.is_boss_room = False
    seq = [_scalar_result(sample_session), _scalar_result(sample_dungeon),
           _scalar_result(MagicMock()), _scalar_result(room_obj)]
    mock_db.execute = AsyncMock(side_effect=lambda *a, **kw: seq.pop(0) if seq else _scalar_result(None))

    results = await process_battle_completion(mock_db, 100, 777, state)

    assert results.get("wiped") is not True
    assert sample_session.finished_at is None
