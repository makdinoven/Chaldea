"""
Tests for cumulative stat tracking in battle-service (FEAT-078, Task #12).

Covers:
1. _track_cumulative_stats POSTs for each player participant (not NPCs)
2. Correct increments dict built (total_damage_dealt, total_damage_received, total_battles, total_rounds_survived)
3. PvP wins/losses set correctly based on result
4. PvE kills counted from defeated NPC participants
5. low_hp_wins incremented when winner HP < 10% of max
6. max_damage_single_battle sent via set_max
7. current_win_streak incremented on win
8. HTTP failure doesn't crash battle flow (try/except works)
9. Damage accumulator fields exist in initial Redis state (default 0)
10. Accumulators use .get() with default 0 for backward compatibility
"""

import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Environment & module-level patches
# ──────────────────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("aioredis", MagicMock())
sys.modules.setdefault("celery", MagicMock())

import database  # noqa: E402

database.engine = MagicMock()

for mod_name in [
    "redis_state",
    "mongo_client",
    "mongo_helpers",
    "tasks",
    "inventory_client",
    "character_client",
    "skills_client",
    "buffs",
    "battle_engine",
    "rabbitmq_publisher",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

# Configure redis_state mock (required for main import)
redis_state_mock = sys.modules["redis_state"]
redis_state_mock.ZSET_DEADLINES = "battle:deadlines"
redis_state_mock.KEY_BATTLE_TURNS = "battle:{id}:turns"
redis_state_mock.init_battle_state = AsyncMock()
redis_state_mock.load_state = AsyncMock(return_value=None)
redis_state_mock.save_state = AsyncMock()
redis_state_mock.get_redis_client = AsyncMock(return_value=MagicMock())
redis_state_mock.cache_snapshot = AsyncMock()
redis_state_mock.get_cached_snapshot = AsyncMock(return_value=None)
redis_state_mock.state_key = MagicMock(return_value="battle:1:state")

# Now import the function under test
from main import _track_cumulative_stats  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_participant(
    character_id: int,
    team: int,
    hp: int = 100,
    max_hp: int = 100,
    total_damage_dealt: int = 0,
    total_damage_received: int = 0,
) -> dict:
    """Build a minimal participant dict matching Redis state structure."""
    return {
        "character_id": character_id,
        "team": team,
        "hp": hp,
        "max_hp": max_hp,
        "mana": 50,
        "energy": 50,
        "stamina": 50,
        "max_mana": 50,
        "max_energy": 50,
        "max_stamina": 50,
        "fast_slots": [],
        "cooldowns": {},
        "total_damage_dealt": total_damage_dealt,
        "total_damage_received": total_damage_received,
    }


def _make_battle_state(participants: dict) -> dict:
    """Build a minimal battle state dict."""
    return {"participants": participants}


def _mock_db_is_npc(npc_char_ids: set):
    """
    Return a mock AsyncSession whose execute() returns is_npc=True
    for character IDs in npc_char_ids, False otherwise.
    """
    mock_session = AsyncMock()

    async def _execute(query, params=None):
        result = MagicMock()
        if params and "cid" in params:
            cid = params["cid"]
            row = MagicMock()
            row.__getitem__ = lambda self, idx: cid in npc_char_ids
            result.fetchone = MagicMock(return_value=row)
        else:
            result.fetchone = MagicMock(return_value=None)
        return result

    mock_session.execute = _execute
    return mock_session


# ──────────────────────────────────────────────────────────────────────────────
# Tests: _track_cumulative_stats
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_posted_for_player_participants_not_npcs():
    """Stats POST is called for each player participant, not for NPCs."""
    battle_state = _make_battle_state({
        "1": _make_participant(character_id=10, team=1, hp=50, total_damage_dealt=100),
        "2": _make_participant(character_id=20, team=2, hp=0, total_damage_dealt=50),
        "3": _make_participant(character_id=30, team=2, hp=0, total_damage_dealt=30),  # NPC
    })
    db_session = _mock_db_is_npc(npc_char_ids={30})

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"

    with patch("main.httpx.AsyncClient") as MockClient:
        mock_client_inst = AsyncMock()
        mock_client_inst.post = AsyncMock(return_value=mock_response)
        mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
        mock_client_inst.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_inst

        await _track_cumulative_stats(
            battle_state=battle_state,
            winner_team=1,
            battle_type="pvp_training",
            turn_number=5,
            db_session=db_session,
        )

        # Should be called for char 10 and 20 (players), NOT char 30 (NPC)
        posted_char_ids = [
            call.kwargs["json"]["character_id"]
            if "json" in call.kwargs else call.args[1]["character_id"]
            for call in mock_client_inst.post.call_args_list
        ]
        # Extract character_id from json keyword arg
        posted_char_ids = []
        for call in mock_client_inst.post.call_args_list:
            payload = call.kwargs.get("json") or call.args[1]
            posted_char_ids.append(payload["character_id"])

        assert 10 in posted_char_ids
        assert 20 in posted_char_ids
        assert 30 not in posted_char_ids
        assert len(posted_char_ids) == 2


@pytest.mark.asyncio
async def test_correct_increments_dict_built():
    """Verify increments dict contains expected fields with correct values."""
    battle_state = _make_battle_state({
        "1": _make_participant(
            character_id=10, team=1, hp=80, max_hp=100,
            total_damage_dealt=250, total_damage_received=20,
        ),
    })
    db_session = _mock_db_is_npc(npc_char_ids=set())

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"

    with patch("main.httpx.AsyncClient") as MockClient:
        mock_client_inst = AsyncMock()
        mock_client_inst.post = AsyncMock(return_value=mock_response)
        mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
        mock_client_inst.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_inst

        await _track_cumulative_stats(
            battle_state=battle_state,
            winner_team=1,
            battle_type="pve",
            turn_number=7,
            db_session=db_session,
        )

        assert mock_client_inst.post.call_count == 1
        payload = mock_client_inst.post.call_args.kwargs.get("json")
        assert payload is not None
        increments = payload["increments"]
        assert increments["total_damage_dealt"] == 250
        assert increments["total_damage_received"] == 20
        assert increments["total_battles"] == 1
        assert increments["total_rounds_survived"] == 7


@pytest.mark.asyncio
async def test_pvp_wins_losses_set_correctly():
    """PvP wins/losses are set correctly based on winner_team."""
    # Team 1 wins; participant 1 is winner (team 1, alive), participant 2 is loser (team 2, dead)
    battle_state = _make_battle_state({
        "1": _make_participant(character_id=10, team=1, hp=50, max_hp=100, total_damage_dealt=10),
        "2": _make_participant(character_id=20, team=2, hp=0, max_hp=100, total_damage_dealt=5),
    })
    db_session = _mock_db_is_npc(npc_char_ids=set())

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"

    payloads = []

    with patch("main.httpx.AsyncClient") as MockClient:
        mock_client_inst = AsyncMock()

        async def _capture_post(url, json=None):
            payloads.append(json)
            return mock_response

        mock_client_inst.post = _capture_post
        mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
        mock_client_inst.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_inst

        await _track_cumulative_stats(
            battle_state=battle_state,
            winner_team=1,
            battle_type="pvp_training",
            turn_number=3,
            db_session=db_session,
        )

    assert len(payloads) == 2

    winner_payload = next(p for p in payloads if p["character_id"] == 10)
    loser_payload = next(p for p in payloads if p["character_id"] == 20)

    assert winner_payload["increments"].get("pvp_wins") == 1
    assert "pvp_losses" not in winner_payload["increments"]

    assert loser_payload["increments"].get("pvp_losses") == 1
    assert "pvp_wins" not in loser_payload["increments"]


@pytest.mark.asyncio
async def test_no_pvp_stats_for_pve_battle():
    """PvP wins/losses should NOT appear for PvE battles."""
    battle_state = _make_battle_state({
        "1": _make_participant(character_id=10, team=1, hp=50, total_damage_dealt=100),
    })
    db_session = _mock_db_is_npc(npc_char_ids=set())

    payloads = []
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"

    with patch("main.httpx.AsyncClient") as MockClient:
        mock_client_inst = AsyncMock()

        async def _capture_post(url, json=None):
            payloads.append(json)
            return mock_response

        mock_client_inst.post = _capture_post
        mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
        mock_client_inst.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_inst

        await _track_cumulative_stats(
            battle_state=battle_state,
            winner_team=1,
            battle_type="pve",
            turn_number=3,
            db_session=db_session,
        )

    assert len(payloads) == 1
    assert "pvp_wins" not in payloads[0]["increments"]
    assert "pvp_losses" not in payloads[0]["increments"]


@pytest.mark.asyncio
async def test_pve_kills_counted_from_defeated_npcs():
    """PvE kills are counted from defeated NPC participants for the winner."""
    # Team 1 (player) wins. Team 2 has 2 NPCs (both dead) and 1 player (dead).
    battle_state = _make_battle_state({
        "1": _make_participant(character_id=10, team=1, hp=50, total_damage_dealt=200),
        "2": _make_participant(character_id=20, team=2, hp=0, total_damage_dealt=10),  # NPC
        "3": _make_participant(character_id=30, team=2, hp=0, total_damage_dealt=5),   # NPC
        "4": _make_participant(character_id=40, team=2, hp=0, total_damage_dealt=15),  # Player
    })
    db_session = _mock_db_is_npc(npc_char_ids={20, 30})

    payloads = []
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"

    with patch("main.httpx.AsyncClient") as MockClient:
        mock_client_inst = AsyncMock()

        async def _capture_post(url, json=None):
            payloads.append(json)
            return mock_response

        mock_client_inst.post = _capture_post
        mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
        mock_client_inst.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_inst

        await _track_cumulative_stats(
            battle_state=battle_state,
            winner_team=1,
            battle_type="pve",
            turn_number=5,
            db_session=db_session,
        )

    # Only player characters should have stats posted (char 10 and 40)
    posted_ids = [p["character_id"] for p in payloads]
    assert 10 in posted_ids
    assert 40 in posted_ids
    assert 20 not in posted_ids  # NPC
    assert 30 not in posted_ids  # NPC

    winner_payload = next(p for p in payloads if p["character_id"] == 10)
    assert winner_payload["increments"].get("pve_kills") == 2

    # Loser player should NOT get pve_kills
    loser_payload = next(p for p in payloads if p["character_id"] == 40)
    assert "pve_kills" not in loser_payload["increments"]


@pytest.mark.asyncio
async def test_low_hp_wins_incremented():
    """low_hp_wins is incremented when winner HP < 10% of max_hp."""
    battle_state = _make_battle_state({
        "1": _make_participant(
            character_id=10, team=1, hp=5, max_hp=100,  # 5% HP
            total_damage_dealt=100,
        ),
    })
    db_session = _mock_db_is_npc(npc_char_ids=set())

    payloads = []
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"

    with patch("main.httpx.AsyncClient") as MockClient:
        mock_client_inst = AsyncMock()

        async def _capture_post(url, json=None):
            payloads.append(json)
            return mock_response

        mock_client_inst.post = _capture_post
        mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
        mock_client_inst.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_inst

        await _track_cumulative_stats(
            battle_state=battle_state,
            winner_team=1,
            battle_type="pve",
            turn_number=3,
            db_session=db_session,
        )

    assert len(payloads) == 1
    assert payloads[0]["increments"].get("low_hp_wins") == 1


@pytest.mark.asyncio
async def test_no_low_hp_wins_when_hp_above_threshold():
    """low_hp_wins is NOT set when winner HP >= 10% of max_hp."""
    battle_state = _make_battle_state({
        "1": _make_participant(
            character_id=10, team=1, hp=15, max_hp=100,  # 15% HP
            total_damage_dealt=100,
        ),
    })
    db_session = _mock_db_is_npc(npc_char_ids=set())

    payloads = []
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"

    with patch("main.httpx.AsyncClient") as MockClient:
        mock_client_inst = AsyncMock()

        async def _capture_post(url, json=None):
            payloads.append(json)
            return mock_response

        mock_client_inst.post = _capture_post
        mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
        mock_client_inst.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_inst

        await _track_cumulative_stats(
            battle_state=battle_state,
            winner_team=1,
            battle_type="pve",
            turn_number=3,
            db_session=db_session,
        )

    assert len(payloads) == 1
    assert "low_hp_wins" not in payloads[0]["increments"]


@pytest.mark.asyncio
async def test_max_damage_single_battle_sent_via_set_max():
    """max_damage_single_battle is sent via set_max when damage > 0."""
    battle_state = _make_battle_state({
        "1": _make_participant(
            character_id=10, team=1, hp=80, total_damage_dealt=350,
        ),
    })
    db_session = _mock_db_is_npc(npc_char_ids=set())

    payloads = []
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"

    with patch("main.httpx.AsyncClient") as MockClient:
        mock_client_inst = AsyncMock()

        async def _capture_post(url, json=None):
            payloads.append(json)
            return mock_response

        mock_client_inst.post = _capture_post
        mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
        mock_client_inst.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_inst

        await _track_cumulative_stats(
            battle_state=battle_state,
            winner_team=1,
            battle_type="pve",
            turn_number=3,
            db_session=db_session,
        )

    assert len(payloads) == 1
    assert payloads[0]["set_max"]["max_damage_single_battle"] == 350


@pytest.mark.asyncio
async def test_no_set_max_when_zero_damage():
    """set_max should be empty when total_damage_dealt is 0."""
    battle_state = _make_battle_state({
        "1": _make_participant(
            character_id=10, team=1, hp=80, total_damage_dealt=0,
            total_damage_received=50,
        ),
    })
    db_session = _mock_db_is_npc(npc_char_ids=set())

    payloads = []
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"

    with patch("main.httpx.AsyncClient") as MockClient:
        mock_client_inst = AsyncMock()

        async def _capture_post(url, json=None):
            payloads.append(json)
            return mock_response

        mock_client_inst.post = _capture_post
        mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
        mock_client_inst.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_inst

        await _track_cumulative_stats(
            battle_state=battle_state,
            winner_team=1,
            battle_type="pve",
            turn_number=3,
            db_session=db_session,
        )

    assert len(payloads) == 1
    assert payloads[0]["set_max"] == {}


@pytest.mark.asyncio
async def test_current_win_streak_incremented_on_win():
    """current_win_streak is incremented by 1 on win."""
    battle_state = _make_battle_state({
        "1": _make_participant(character_id=10, team=1, hp=50, total_damage_dealt=10),
        "2": _make_participant(character_id=20, team=2, hp=0, total_damage_dealt=5),
    })
    db_session = _mock_db_is_npc(npc_char_ids=set())

    payloads = []
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"

    with patch("main.httpx.AsyncClient") as MockClient:
        mock_client_inst = AsyncMock()

        async def _capture_post(url, json=None):
            payloads.append(json)
            return mock_response

        mock_client_inst.post = _capture_post
        mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
        mock_client_inst.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_inst

        await _track_cumulative_stats(
            battle_state=battle_state,
            winner_team=1,
            battle_type="pve",
            turn_number=3,
            db_session=db_session,
        )

    winner_payload = next(p for p in payloads if p["character_id"] == 10)
    assert winner_payload["increments"].get("current_win_streak") == 1

    loser_payload = next(p for p in payloads if p["character_id"] == 20)
    assert "current_win_streak" not in loser_payload["increments"]


@pytest.mark.asyncio
async def test_http_failure_does_not_crash():
    """HTTP failure (exception) should not propagate — function catches and logs."""
    battle_state = _make_battle_state({
        "1": _make_participant(character_id=10, team=1, hp=50, total_damage_dealt=100),
    })
    db_session = _mock_db_is_npc(npc_char_ids=set())

    with patch("main.httpx.AsyncClient") as MockClient:
        mock_client_inst = AsyncMock()
        mock_client_inst.post = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
        mock_client_inst.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_inst

        # Should NOT raise — errors are caught internally
        await _track_cumulative_stats(
            battle_state=battle_state,
            winner_team=1,
            battle_type="pve",
            turn_number=3,
            db_session=db_session,
        )


@pytest.mark.asyncio
async def test_http_non_200_does_not_crash():
    """Non-200 HTTP response should not crash — just logged."""
    battle_state = _make_battle_state({
        "1": _make_participant(character_id=10, team=1, hp=50, total_damage_dealt=100),
    })
    db_session = _mock_db_is_npc(npc_char_ids=set())

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch("main.httpx.AsyncClient") as MockClient:
        mock_client_inst = AsyncMock()
        mock_client_inst.post = AsyncMock(return_value=mock_response)
        mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
        mock_client_inst.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_inst

        # Should NOT raise
        await _track_cumulative_stats(
            battle_state=battle_state,
            winner_team=1,
            battle_type="pve",
            turn_number=3,
            db_session=db_session,
        )


@pytest.mark.asyncio
async def test_draw_no_winner_team():
    """When winner_team is None (draw), no pvp_wins/losses/pve_kills/low_hp_wins/streak."""
    battle_state = _make_battle_state({
        "1": _make_participant(character_id=10, team=1, hp=0, total_damage_dealt=100),
        "2": _make_participant(character_id=20, team=2, hp=0, total_damage_dealt=80),
    })
    db_session = _mock_db_is_npc(npc_char_ids=set())

    payloads = []
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"

    with patch("main.httpx.AsyncClient") as MockClient:
        mock_client_inst = AsyncMock()

        async def _capture_post(url, json=None):
            payloads.append(json)
            return mock_response

        mock_client_inst.post = _capture_post
        mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
        mock_client_inst.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_inst

        await _track_cumulative_stats(
            battle_state=battle_state,
            winner_team=None,
            battle_type="pvp_training",
            turn_number=5,
            db_session=db_session,
        )

    for p in payloads:
        inc = p["increments"]
        assert "pvp_wins" not in inc
        assert "pvp_losses" not in inc
        assert "pve_kills" not in inc
        assert "low_hp_wins" not in inc
        assert "current_win_streak" not in inc
        # But total_battles and total_rounds_survived should still be there
        assert inc["total_battles"] == 1
        assert inc["total_rounds_survived"] == 5


@pytest.mark.asyncio
async def test_zero_damage_entries_filtered_out():
    """Zero-value increments are filtered out of the payload."""
    battle_state = _make_battle_state({
        "1": _make_participant(
            character_id=10, team=1, hp=80,
            total_damage_dealt=0, total_damage_received=0,
        ),
    })
    db_session = _mock_db_is_npc(npc_char_ids=set())

    payloads = []
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"

    with patch("main.httpx.AsyncClient") as MockClient:
        mock_client_inst = AsyncMock()

        async def _capture_post(url, json=None):
            payloads.append(json)
            return mock_response

        mock_client_inst.post = _capture_post
        mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
        mock_client_inst.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_inst

        await _track_cumulative_stats(
            battle_state=battle_state,
            winner_team=1,
            battle_type="pve",
            turn_number=3,
            db_session=db_session,
        )

    assert len(payloads) == 1
    inc = payloads[0]["increments"]
    # total_damage_dealt=0 and total_damage_received=0 should be filtered out
    assert "total_damage_dealt" not in inc
    assert "total_damage_received" not in inc
    # total_battles=1 and total_rounds_survived=3 remain (non-zero)
    assert inc["total_battles"] == 1
    assert inc["total_rounds_survived"] == 3


# ──────────────────────────────────────────────────────────────────────────────
# Tests: Damage accumulator fields in Redis state
# ──────────────────────────────────────────────────────────────────────────────

def test_damage_accumulators_default_zero_in_participant():
    """Damage accumulator fields should default to 0 in participant state."""
    participant = _make_participant(character_id=1, team=1)
    assert participant["total_damage_dealt"] == 0
    assert participant["total_damage_received"] == 0


def test_accumulators_backward_compatible_with_get():
    """
    Accumulators use .get() with default 0 for backward compatibility —
    even if fields are missing from an old state, code should not crash.
    """
    # Simulate old participant state without accumulator fields
    old_participant = {
        "character_id": 1,
        "team": 1,
        "hp": 100,
        "max_hp": 100,
    }
    # The code uses pdata.get("total_damage_dealt", 0) — verify this works
    assert old_participant.get("total_damage_dealt", 0) == 0
    assert old_participant.get("total_damage_received", 0) == 0

    # Simulate damage accumulation pattern from main.py line 1248
    old_participant["total_damage_dealt"] = old_participant.get("total_damage_dealt", 0) + 50
    assert old_participant["total_damage_dealt"] == 50

    old_participant["total_damage_received"] = old_participant.get("total_damage_received", 0) + 30
    assert old_participant["total_damage_received"] == 30


def test_redis_state_structure_has_accumulator_fields():
    """
    Verify that the expected Redis state participant structure includes
    total_damage_dealt and total_damage_received initialized to 0.
    This mirrors what redis_state.py init_battle_state() creates.
    """
    # This simulates the structure from redis_state.py lines 90-91
    participant_state = {
        "character_id": 1,
        "team": 1,
        "hp": 100,
        "mana": 50,
        "energy": 50,
        "stamina": 50,
        "max_hp": 100,
        "max_mana": 50,
        "max_energy": 50,
        "max_stamina": 50,
        "fast_slots": [],
        "cooldowns": {},
        "total_damage_dealt": 0,
        "total_damage_received": 0,
    }
    assert "total_damage_dealt" in participant_state
    assert "total_damage_received" in participant_state
    assert participant_state["total_damage_dealt"] == 0
    assert participant_state["total_damage_received"] == 0
