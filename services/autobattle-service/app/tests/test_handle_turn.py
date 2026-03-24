"""
Tests for handle_turn retry logic and cleanup in autobattle-service (FEAT-071, Task 6).

Covers:
- handle_turn retries on httpx failure (mock httpx to fail then succeed)
- handle_turn stops retry if it's no longer our turn
- After battle_finished=true, ALLOWED/PID_BATTLE/OWNER/LAST_STATS/HISTORY are cleaned up
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, AsyncMock
from collections import defaultdict, deque

import pytest

# Mock aioredis before importing main
aioredis_mock = MagicMock()
aioredis_mock.from_url = AsyncMock(return_value=MagicMock())
sys.modules["aioredis"] = aioredis_mock

# Mock strategy module with a working Strategy
strategy_mod = MagicMock()
_strategy_instance = MagicMock()
_strategy_instance.mode = "attack"
_strategy_instance.select_actions = MagicMock(return_value=({"skill_id": 1}, None))
strategy_mod.Strategy = MagicMock(return_value=_strategy_instance)
sys.modules["strategy"] = strategy_mod

# Mock clients module
clients_mock = MagicMock()
clients_mock.get_battle_state = AsyncMock(return_value={})
clients_mock.post_battle_action = AsyncMock(return_value={})
clients_mock.get_character_owner = AsyncMock(return_value=None)
sys.modules["clients"] = clients_mock

from main import (  # noqa: E402
    app, handle_turn, _cleanup_battle,
    ALLOWED, PID_BATTLE, OWNER, LAST_STATS, HISTORY,
    MAX_RETRIES,
)

# Clear startup handlers
app.router.on_startup.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_battle_ctx(current_actor: int = 10, turn_number: int = 1):
    """Create a battle state context dict for testing."""
    return {
        "runtime": {
            "current_actor": current_actor,
            "participants": {
                "10": {
                    "character_id": 100, "hp": 50, "mana": 20, "energy": 30,
                    "stamina": 40, "cooldowns": {}, "fast_slots": [],
                },
                "20": {
                    "character_id": 200, "hp": 60, "mana": 25, "energy": 35,
                    "stamina": 45, "cooldowns": {}, "fast_slots": [],
                },
            },
            "turn_order": [10, 20],
            "turn_number": turn_number,
            "active_effects": {"10": [], "20": []},
        },
        "snapshot": [
            {
                "participant_id": 10, "character_id": 100,
                "attributes": {
                    "max_health": 100, "max_mana": 50,
                    "max_energy": 50, "max_stamina": 50,
                },
                "skills": [], "fast_slots": [],
            },
            {
                "participant_id": 20, "character_id": 200,
                "attributes": {
                    "max_health": 100, "max_mana": 50,
                    "max_energy": 50, "max_stamina": 50,
                },
                "skills": [], "fast_slots": [],
            },
        ],
    }


def _make_action_response(battle_finished: bool = False, turn_number: int = 1):
    """Create a mock action response."""
    return {
        "turn_number": turn_number,
        "events": [{"event": "damage", "source": 10, "final": 15}],
        "battle_finished": battle_finished,
        "winner_team": 0 if battle_finished else None,
    }


def _cleanup():
    """Reset in-memory state between tests."""
    ALLOWED.clear()
    PID_BATTLE.clear()
    OWNER.clear()
    LAST_STATS.clear()
    HISTORY.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Retry logic
# ═══════════════════════════════════════════════════════════════════════════

class TestHandleTurnRetry:
    """Tests for retry logic in handle_turn."""

    def setup_method(self):
        _cleanup()

    @pytest.mark.asyncio
    @patch("main.build_features", return_value={"hp_ratio": 0.5, "mana_ratio": 0.4})
    @patch("main.asyncio.sleep", new_callable=AsyncMock)
    @patch("main.post_battle_action", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    async def test_retries_on_httpx_failure_then_succeeds(
        self, mock_state, mock_action, mock_sleep, mock_features
    ):
        """handle_turn retries when post_battle_action raises, then succeeds."""
        ctx = _make_battle_ctx(current_actor=10)
        mock_state.return_value = ctx

        # First call raises, second succeeds
        mock_action.side_effect = [
            Exception("Connection refused"),
            _make_action_response(),
        ]

        ALLOWED.add(10)
        PID_BATTLE[10] = 1

        await handle_turn(1, 10)

        # Should have called action twice (1 failure + 1 success)
        assert mock_action.call_count == 2
        # Should have slept once (exponential backoff: 2s)
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(2)

    @pytest.mark.asyncio
    @patch("main.build_features", return_value={"hp_ratio": 0.5, "mana_ratio": 0.4})
    @patch("main.asyncio.sleep", new_callable=AsyncMock)
    @patch("main.post_battle_action", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    async def test_gives_up_after_max_retries(
        self, mock_state, mock_action, mock_sleep, mock_features
    ):
        """handle_turn gives up after MAX_RETRIES+1 attempts."""
        ctx = _make_battle_ctx(current_actor=10)
        mock_state.return_value = ctx

        # All calls fail
        mock_action.side_effect = Exception("Connection refused")

        ALLOWED.add(10)
        PID_BATTLE[10] = 1

        await handle_turn(1, 10)

        # Should have tried MAX_RETRIES + 1 times
        assert mock_action.call_count == MAX_RETRIES + 1
        # Should have slept MAX_RETRIES times (2s, 4s, 8s)
        assert mock_sleep.call_count == MAX_RETRIES

    @pytest.mark.asyncio
    @patch("main.build_features", return_value={"hp_ratio": 0.5, "mana_ratio": 0.4})
    @patch("main.asyncio.sleep", new_callable=AsyncMock)
    @patch("main.post_battle_action", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    async def test_stops_retry_if_not_our_turn(
        self, mock_state, mock_action, mock_sleep, mock_features
    ):
        """On retry, if current_actor changed (not our turn), stop immediately."""
        ctx_our_turn = _make_battle_ctx(current_actor=10)
        ctx_not_our_turn = _make_battle_ctx(current_actor=20)  # someone else's turn

        # First call: our turn but action fails; second call: not our turn anymore
        mock_state.side_effect = [ctx_our_turn, ctx_not_our_turn]
        mock_action.side_effect = Exception("Timeout")

        ALLOWED.add(10)
        PID_BATTLE[10] = 1

        await handle_turn(1, 10)

        # Action called once (first attempt), then state shows not our turn -> return
        assert mock_action.call_count == 1
        # get_battle_state called twice (initial + retry)
        assert mock_state.call_count == 2

    @pytest.mark.asyncio
    @patch("main.build_features", return_value={"hp_ratio": 0.5, "mana_ratio": 0.4})
    @patch("main.asyncio.sleep", new_callable=AsyncMock)
    @patch("main.post_battle_action", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    async def test_exponential_backoff_delays(
        self, mock_state, mock_action, mock_sleep, mock_features
    ):
        """Retry delays follow exponential backoff: 2s, 4s, 8s."""
        ctx = _make_battle_ctx(current_actor=10)
        mock_state.return_value = ctx
        mock_action.side_effect = Exception("Error")

        ALLOWED.add(10)
        PID_BATTLE[10] = 1

        await handle_turn(1, 10)

        # Verify backoff delays
        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_calls == [2, 4, 8]


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Cleanup on battle finish
# ═══════════════════════════════════════════════════════════════════════════

class TestCleanupOnBattleFinish:
    """Tests for _cleanup_battle and cleanup triggered by battle_finished=true."""

    def setup_method(self):
        _cleanup()

    def test_cleanup_battle_removes_all_pids(self):
        """_cleanup_battle removes all pids for a battle from ALLOWED, PID_BATTLE, OWNER."""
        ALLOWED.update({10, 20, 30})
        PID_BATTLE[10] = 1
        PID_BATTLE[20] = 1
        PID_BATTLE[30] = 2  # different battle
        OWNER[10] = 1
        OWNER[20] = 2

        _cleanup_battle(1)

        # Pids for battle 1 removed
        assert 10 not in ALLOWED
        assert 20 not in ALLOWED
        assert 10 not in PID_BATTLE
        assert 20 not in PID_BATTLE
        assert 10 not in OWNER
        assert 20 not in OWNER

        # Pid for battle 2 untouched
        assert 30 in ALLOWED
        assert PID_BATTLE[30] == 2

    def test_cleanup_battle_removes_last_stats(self):
        """_cleanup_battle removes LAST_STATS entries for the battle."""
        LAST_STATS[(1, 10)] = {"hp": 50, "mana": 30, "energy": 20, "stamina": 20}
        LAST_STATS[(1, 20)] = {"hp": 60, "mana": 30, "energy": 20, "stamina": 20}
        LAST_STATS[(2, 30)] = {"hp": 70, "mana": 30, "energy": 20, "stamina": 20}  # different battle

        PID_BATTLE[10] = 1
        PID_BATTLE[20] = 1

        _cleanup_battle(1)

        assert (1, 10) not in LAST_STATS
        assert (1, 20) not in LAST_STATS
        assert (2, 30) in LAST_STATS  # untouched

    def test_cleanup_battle_removes_history(self):
        """_cleanup_battle removes HISTORY entries for the battle."""
        HISTORY[(1, 10)].append({"dps": 15})
        HISTORY[(1, 20)].append({"dps": 20})
        HISTORY[(2, 30)].append({"dps": 25})  # different battle

        PID_BATTLE[10] = 1
        PID_BATTLE[20] = 1

        _cleanup_battle(1)

        assert (1, 10) not in HISTORY
        assert (1, 20) not in HISTORY
        assert (2, 30) in HISTORY  # untouched

    @pytest.mark.asyncio
    @patch("main.build_features", return_value={"hp_ratio": 0.5, "mana_ratio": 0.4})
    @patch("main.post_battle_action", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    async def test_handle_turn_triggers_cleanup_on_battle_finished(
        self, mock_state, mock_action, mock_features
    ):
        """When post_battle_action returns battle_finished=true, cleanup is triggered."""
        ctx = _make_battle_ctx(current_actor=10)
        mock_state.return_value = ctx
        mock_action.return_value = _make_action_response(battle_finished=True)

        # Set up state to be cleaned
        ALLOWED.update({10, 20})
        PID_BATTLE[10] = 1
        PID_BATTLE[20] = 1
        OWNER[10] = 1
        OWNER[20] = 2
        LAST_STATS[(1, 10)] = {"hp": 50, "mana": 30, "energy": 20, "stamina": 20}
        HISTORY[(1, 10)].append({"dps": 15})

        await handle_turn(1, 10)

        # All state for battle 1 should be cleaned
        assert 10 not in ALLOWED
        assert 20 not in ALLOWED
        assert 10 not in PID_BATTLE
        assert 20 not in PID_BATTLE
        assert 10 not in OWNER
        assert 20 not in OWNER
        assert (1, 10) not in LAST_STATS
        assert (1, 10) not in HISTORY

    @pytest.mark.asyncio
    @patch("main.build_features", return_value={"hp_ratio": 0.5, "mana_ratio": 0.4})
    @patch("main.post_battle_action", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    async def test_handle_turn_no_cleanup_when_battle_continues(
        self, mock_state, mock_action, mock_features
    ):
        """When battle is not finished, no cleanup occurs."""
        ctx = _make_battle_ctx(current_actor=10)
        mock_state.return_value = ctx
        mock_action.return_value = _make_action_response(battle_finished=False)

        ALLOWED.update({10, 20})
        PID_BATTLE[10] = 1
        PID_BATTLE[20] = 1
        OWNER[10] = 1

        await handle_turn(1, 10)

        # State should NOT be cleaned
        assert 10 in ALLOWED
        assert 20 in ALLOWED
        assert PID_BATTLE[10] == 1
        assert OWNER[10] == 1
