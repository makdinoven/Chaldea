"""
Tests for autobattle-service speed control (FEAT-074, Task #11).

Covers:
- POST /speed with valid auth — speed is set correctly
- POST /speed with invalid/missing JWT — returns 401
- POST /speed ownership check — user can only set speed for their own participant
- POST /speed with invalid speed value — returns 400
- POST /speed for unregistered participant — returns 404
- Slow mode delay — asyncio.sleep is called with correct delay when speed is "slow"
- Fast mode no delay — no sleep when speed is "fast"
- Default speed on register — speed is "fast" after registration
- Cleanup on battle finish — SPEED entries are removed in _cleanup_battle()
- Cleanup on unregister — SPEED entry is removed
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# Mock aioredis before importing main (it connects on startup)
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

# Mock clients module to avoid battle-service HTTP calls
clients_mock = MagicMock()
clients_mock.get_battle_state = AsyncMock(return_value={})
clients_mock.post_battle_action = AsyncMock(return_value={})
clients_mock.get_character_owner = AsyncMock(return_value=None)
sys.modules["clients"] = clients_mock

from main import (  # noqa: E402
    app, handle_turn, _cleanup_battle,
    ALLOWED, PID_BATTLE, OWNER, SPEED, LAST_STATS, HISTORY,
)
from config import settings  # noqa: E402

# Clear startup handlers to prevent Redis connection
app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _cleanup():
    """Reset in-memory state between tests."""
    ALLOWED.clear()
    PID_BATTLE.clear()
    OWNER.clear()
    SPEED.clear()
    LAST_STATS.clear()
    HISTORY.clear()


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


AUTH_HEADERS = {"Authorization": "Bearer fake-token"}
USER_1 = {"id": 1, "username": "player1", "role": "user", "permissions": []}
USER_2 = {"id": 2, "username": "player2", "role": "user", "permissions": []}


# ═══════════════════════════════════════════════════════════════════════════
# 1. POST /speed with valid auth — speed is set correctly
# ═══════════════════════════════════════════════════════════════════════════

class TestSetSpeedValid:
    """Tests for POST /speed with valid authentication and input."""

    def setup_method(self):
        _cleanup()

    @patch("auth_http.requests.get")
    def test_set_speed_slow(self, mock_auth):
        """Authenticated user can set speed to 'slow' for their own participant."""
        mock_auth.return_value = _mock_response(200, USER_1)
        ALLOWED.add(10)
        OWNER[10] = 1
        SPEED[10] = "fast"

        with TestClient(app) as client:
            response = client.post(
                "/speed",
                json={"participant_id": 10, "speed": "slow"},
                headers=AUTH_HEADERS,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["participant_id"] == 10
        assert data["speed"] == "slow"
        assert SPEED[10] == "slow"

    @patch("auth_http.requests.get")
    def test_set_speed_fast(self, mock_auth):
        """Authenticated user can set speed to 'fast' for their own participant."""
        mock_auth.return_value = _mock_response(200, USER_1)
        ALLOWED.add(10)
        OWNER[10] = 1
        SPEED[10] = "slow"

        with TestClient(app) as client:
            response = client.post(
                "/speed",
                json={"participant_id": 10, "speed": "fast"},
                headers=AUTH_HEADERS,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["speed"] == "fast"
        assert SPEED[10] == "fast"

    @patch("auth_http.requests.get")
    def test_set_speed_response_matches(self, mock_auth):
        """Response contains ok, participant_id, and speed fields."""
        mock_auth.return_value = _mock_response(200, USER_1)
        ALLOWED.add(10)
        OWNER[10] = 1

        with TestClient(app) as client:
            response = client.post(
                "/speed",
                json={"participant_id": 10, "speed": "slow"},
                headers=AUTH_HEADERS,
            )
        data = response.json()
        assert "ok" in data
        assert "participant_id" in data
        assert "speed" in data


# ═══════════════════════════════════════════════════════════════════════════
# 2. POST /speed with invalid/missing JWT — returns 401
# ═══════════════════════════════════════════════════════════════════════════

class TestSetSpeedAuth:
    """Tests for POST /speed authentication."""

    def setup_method(self):
        _cleanup()

    def test_missing_token_returns_401(self):
        """Request without Authorization header returns 401."""
        with TestClient(app) as client:
            response = client.post(
                "/speed",
                json={"participant_id": 10, "speed": "slow"},
            )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_auth):
        """Request with invalid token returns 401."""
        mock_auth.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.post(
                "/speed",
                json={"participant_id": 10, "speed": "slow"},
                headers={"Authorization": "Bearer bad-token"},
            )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_expired_token_returns_401(self, mock_auth):
        """Request with expired token returns 401."""
        mock_auth.return_value = _mock_response(401, {"detail": "Token expired"})
        with TestClient(app) as client:
            response = client.post(
                "/speed",
                json={"participant_id": 10, "speed": "slow"},
                headers={"Authorization": "Bearer expired-token"},
            )
        assert response.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 3. POST /speed ownership check
# ═══════════════════════════════════════════════════════════════════════════

class TestSetSpeedOwnership:
    """Tests for POST /speed ownership validation."""

    def setup_method(self):
        _cleanup()

    @patch("auth_http.requests.get")
    def test_cannot_set_speed_for_others_participant(self, mock_auth):
        """User cannot set speed for a participant owned by another user."""
        mock_auth.return_value = _mock_response(200, USER_1)
        ALLOWED.add(20)
        OWNER[20] = 999  # owned by user 999, not user 1

        with TestClient(app) as client:
            response = client.post(
                "/speed",
                json={"participant_id": 20, "speed": "slow"},
                headers=AUTH_HEADERS,
            )
        assert response.status_code == 403
        # Speed should not have changed
        assert SPEED.get(20) != "slow"

    @patch("auth_http.requests.get")
    def test_can_set_speed_for_own_participant(self, mock_auth):
        """User can set speed for their own participant."""
        mock_auth.return_value = _mock_response(200, USER_2)
        ALLOWED.add(20)
        OWNER[20] = 2

        with TestClient(app) as client:
            response = client.post(
                "/speed",
                json={"participant_id": 20, "speed": "slow"},
                headers=AUTH_HEADERS,
            )
        assert response.status_code == 200
        assert SPEED[20] == "slow"

    @patch("auth_http.requests.get")
    def test_no_owner_entry_allows_speed_set(self, mock_auth):
        """If participant has no OWNER entry, any authenticated user can set speed."""
        mock_auth.return_value = _mock_response(200, USER_1)
        ALLOWED.add(30)
        # No OWNER entry for pid 30

        with TestClient(app) as client:
            response = client.post(
                "/speed",
                json={"participant_id": 30, "speed": "slow"},
                headers=AUTH_HEADERS,
            )
        assert response.status_code == 200
        assert SPEED[30] == "slow"


# ═══════════════════════════════════════════════════════════════════════════
# 4. POST /speed with invalid speed value — returns 400
# ═══════════════════════════════════════════════════════════════════════════

class TestSetSpeedInvalidValue:
    """Tests for POST /speed with invalid speed values."""

    def setup_method(self):
        _cleanup()

    @patch("auth_http.requests.get")
    def test_invalid_speed_value_returns_400(self, mock_auth):
        """Speed value other than 'fast' or 'slow' returns 400."""
        mock_auth.return_value = _mock_response(200, USER_1)
        ALLOWED.add(10)
        OWNER[10] = 1

        with TestClient(app) as client:
            response = client.post(
                "/speed",
                json={"participant_id": 10, "speed": "turbo"},
                headers=AUTH_HEADERS,
            )
        assert response.status_code == 400

    @patch("auth_http.requests.get")
    def test_empty_speed_value_returns_400(self, mock_auth):
        """Empty speed string returns 400."""
        mock_auth.return_value = _mock_response(200, USER_1)
        ALLOWED.add(10)
        OWNER[10] = 1

        with TestClient(app) as client:
            response = client.post(
                "/speed",
                json={"participant_id": 10, "speed": ""},
                headers=AUTH_HEADERS,
            )
        assert response.status_code == 400

    @patch("auth_http.requests.get")
    def test_numeric_speed_value_returns_400(self, mock_auth):
        """Numeric speed value returns 400."""
        mock_auth.return_value = _mock_response(200, USER_1)
        ALLOWED.add(10)
        OWNER[10] = 1

        with TestClient(app) as client:
            response = client.post(
                "/speed",
                json={"participant_id": 10, "speed": "123"},
                headers=AUTH_HEADERS,
            )
        assert response.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# 5. POST /speed for unregistered participant — returns 404
# ═══════════════════════════════════════════════════════════════════════════

class TestSetSpeedUnregistered:
    """Tests for POST /speed with unregistered participant."""

    def setup_method(self):
        _cleanup()

    @patch("auth_http.requests.get")
    def test_unregistered_participant_returns_404(self, mock_auth):
        """Setting speed for a participant not in ALLOWED returns 404."""
        mock_auth.return_value = _mock_response(200, USER_1)
        # pid 10 is NOT in ALLOWED

        with TestClient(app) as client:
            response = client.post(
                "/speed",
                json={"participant_id": 10, "speed": "slow"},
                headers=AUTH_HEADERS,
            )
        assert response.status_code == 404

    @patch("auth_http.requests.get")
    def test_unregistered_participant_error_message(self, mock_auth):
        """Error detail mentions participant not registered."""
        mock_auth.return_value = _mock_response(200, USER_1)

        with TestClient(app) as client:
            response = client.post(
                "/speed",
                json={"participant_id": 999, "speed": "slow"},
                headers=AUTH_HEADERS,
            )
        assert response.status_code == 404
        assert "зарегистрирован" in response.json()["detail"].lower() or \
               "не зарегистрирован" in response.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════
# 6. Slow mode delay — asyncio.sleep called with correct delay
# ═══════════════════════════════════════════════════════════════════════════

class TestSlowModeDelay:
    """Tests that slow mode triggers asyncio.sleep with correct delay."""

    def setup_method(self):
        _cleanup()

    @pytest.mark.asyncio
    @patch("main.strategy.select_actions", return_value=({"skill_id": 1}, None))
    @patch("main.build_features", return_value={"hp_ratio": 0.5, "mana_ratio": 0.4})
    @patch("main.asyncio.sleep", new_callable=AsyncMock)
    @patch("main.post_battle_action", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    async def test_slow_mode_calls_sleep_with_configured_delay(
        self, mock_state, mock_action, mock_sleep, mock_features, mock_strategy
    ):
        """When speed is 'slow', asyncio.sleep is called with AUTOBATTLE_SLOW_DELAY."""
        ctx = _make_battle_ctx(current_actor=10)
        mock_state.return_value = ctx
        mock_action.return_value = _make_action_response()

        ALLOWED.add(10)
        PID_BATTLE[10] = 1
        SPEED[10] = "slow"

        await handle_turn(1, 10)

        # First sleep call should be the slow delay
        mock_sleep.assert_any_call(settings.AUTOBATTLE_SLOW_DELAY)

    @pytest.mark.asyncio
    @patch("main.strategy.select_actions", return_value=({"skill_id": 1}, None))
    @patch("main.build_features", return_value={"hp_ratio": 0.5, "mana_ratio": 0.4})
    @patch("main.asyncio.sleep", new_callable=AsyncMock)
    @patch("main.post_battle_action", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    async def test_slow_mode_delay_value_is_3_seconds(
        self, mock_state, mock_action, mock_sleep, mock_features, mock_strategy
    ):
        """Default AUTOBATTLE_SLOW_DELAY is 3.0 seconds."""
        ctx = _make_battle_ctx(current_actor=10)
        mock_state.return_value = ctx
        mock_action.return_value = _make_action_response()

        ALLOWED.add(10)
        PID_BATTLE[10] = 1
        SPEED[10] = "slow"

        await handle_turn(1, 10)

        # Verify the delay value matches config
        assert settings.AUTOBATTLE_SLOW_DELAY == 3.0
        mock_sleep.assert_any_call(3.0)


# ═══════════════════════════════════════════════════════════════════════════
# 7. Fast mode no delay
# ═══════════════════════════════════════════════════════════════════════════

class TestFastModeNoDelay:
    """Tests that fast mode does not trigger asyncio.sleep for delay."""

    def setup_method(self):
        _cleanup()

    @pytest.mark.asyncio
    @patch("main.strategy.select_actions", return_value=({"skill_id": 1}, None))
    @patch("main.build_features", return_value={"hp_ratio": 0.5, "mana_ratio": 0.4})
    @patch("main.asyncio.sleep", new_callable=AsyncMock)
    @patch("main.post_battle_action", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    async def test_fast_mode_no_slow_delay_sleep(
        self, mock_state, mock_action, mock_sleep, mock_features, mock_strategy
    ):
        """When speed is 'fast', asyncio.sleep is NOT called with AUTOBATTLE_SLOW_DELAY."""
        ctx = _make_battle_ctx(current_actor=10)
        mock_state.return_value = ctx
        mock_action.return_value = _make_action_response()

        ALLOWED.add(10)
        PID_BATTLE[10] = 1
        SPEED[10] = "fast"

        await handle_turn(1, 10)

        # asyncio.sleep should NOT have been called with slow delay
        for call in mock_sleep.call_args_list:
            assert call.args[0] != settings.AUTOBATTLE_SLOW_DELAY

    @pytest.mark.asyncio
    @patch("main.strategy.select_actions", return_value=({"skill_id": 1}, None))
    @patch("main.build_features", return_value={"hp_ratio": 0.5, "mana_ratio": 0.4})
    @patch("main.asyncio.sleep", new_callable=AsyncMock)
    @patch("main.post_battle_action", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    async def test_no_speed_entry_no_delay(
        self, mock_state, mock_action, mock_sleep, mock_features, mock_strategy
    ):
        """When SPEED dict has no entry for pid, no slow delay is applied."""
        ctx = _make_battle_ctx(current_actor=10)
        mock_state.return_value = ctx
        mock_action.return_value = _make_action_response()

        ALLOWED.add(10)
        PID_BATTLE[10] = 1
        # No SPEED entry for pid 10

        await handle_turn(1, 10)

        # asyncio.sleep should NOT have been called with slow delay
        for call in mock_sleep.call_args_list:
            assert call.args[0] != settings.AUTOBATTLE_SLOW_DELAY


# ═══════════════════════════════════════════════════════════════════════════
# 8. Default speed on register
# ═══════════════════════════════════════════════════════════════════════════

class TestDefaultSpeedOnRegister:
    """Tests that default speed is 'fast' after registration."""

    def setup_method(self):
        _cleanup()

    @patch("auth_http.requests.get")
    def test_register_sets_default_speed_fast(self, mock_auth):
        """After /register, SPEED[pid] is set to 'fast'."""
        mock_auth.return_value = _mock_response(200, USER_1)

        with TestClient(app) as client:
            response = client.post(
                "/register",
                json={"participant_id": 10, "battle_id": 0},
                headers=AUTH_HEADERS,
            )
        assert response.status_code == 200
        assert SPEED[10] == "fast"

    @patch("main.get_character_owner", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_register_with_battle_id_sets_default_speed_fast(
        self, mock_auth, mock_state, mock_owner
    ):
        """After /register with battle_id, SPEED[pid] is set to 'fast'."""
        mock_auth.return_value = _mock_response(200, USER_1)
        mock_state.return_value = _make_battle_ctx(current_actor=20)  # not our turn
        mock_owner.return_value = 1  # user 1 owns character 100

        with TestClient(app) as client:
            response = client.post(
                "/register",
                json={"participant_id": 10, "battle_id": 5},
                headers=AUTH_HEADERS,
            )
        assert response.status_code == 200
        assert SPEED[10] == "fast"

    def test_internal_register_does_not_set_speed(self):
        """Internal register (for mobs) does NOT set SPEED entry."""
        with TestClient(app) as client:
            response = client.post(
                "/internal/register",
                json={"participant_id": 50, "battle_id": 0},
            )
        assert response.status_code == 200
        # Internal register is for mobs — no SPEED entry
        assert 50 not in SPEED


# ═══════════════════════════════════════════════════════════════════════════
# 9. Cleanup on battle finish — SPEED entries are removed
# ═══════════════════════════════════════════════════════════════════════════

class TestCleanupBattleSpeed:
    """Tests that SPEED entries are cleaned up when battle finishes."""

    def setup_method(self):
        _cleanup()

    def test_cleanup_battle_removes_speed_entries(self):
        """_cleanup_battle removes SPEED entries for all pids in the battle."""
        ALLOWED.update({10, 20, 30})
        PID_BATTLE[10] = 1
        PID_BATTLE[20] = 1
        PID_BATTLE[30] = 2  # different battle
        SPEED[10] = "slow"
        SPEED[20] = "fast"
        SPEED[30] = "slow"

        _cleanup_battle(1)

        assert 10 not in SPEED
        assert 20 not in SPEED
        # Pid for battle 2 untouched
        assert SPEED[30] == "slow"

    def test_cleanup_battle_removes_speed_and_owner(self):
        """_cleanup_battle removes both SPEED and OWNER entries."""
        ALLOWED.update({10, 20})
        PID_BATTLE[10] = 1
        PID_BATTLE[20] = 1
        OWNER[10] = 1
        OWNER[20] = 2
        SPEED[10] = "fast"
        SPEED[20] = "slow"

        _cleanup_battle(1)

        assert 10 not in SPEED
        assert 20 not in SPEED
        assert 10 not in OWNER
        assert 20 not in OWNER
        assert 10 not in ALLOWED
        assert 20 not in ALLOWED

    @pytest.mark.asyncio
    @patch("main.strategy.select_actions", return_value=({"skill_id": 1}, None))
    @patch("main.build_features", return_value={"hp_ratio": 0.5, "mana_ratio": 0.4})
    @patch("main.post_battle_action", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    async def test_handle_turn_battle_finished_cleans_speed(
        self, mock_state, mock_action, mock_features, mock_strategy
    ):
        """When battle finishes via handle_turn, SPEED is cleaned up."""
        ctx = _make_battle_ctx(current_actor=10)
        mock_state.return_value = ctx
        mock_action.return_value = _make_action_response(battle_finished=True)

        ALLOWED.update({10, 20})
        PID_BATTLE[10] = 1
        PID_BATTLE[20] = 1
        SPEED[10] = "slow"
        SPEED[20] = "fast"

        await handle_turn(1, 10)

        assert 10 not in SPEED
        assert 20 not in SPEED


# ═══════════════════════════════════════════════════════════════════════════
# 10. Cleanup on unregister — SPEED entry is removed
# ═══════════════════════════════════════════════════════════════════════════

class TestUnregisterCleansSpeed:
    """Tests that SPEED entry is removed when participant is unregistered."""

    def setup_method(self):
        _cleanup()

    @patch("auth_http.requests.get")
    def test_unregister_removes_speed_entry(self, mock_auth):
        """POST /unregister removes the SPEED entry for the participant."""
        mock_auth.return_value = _mock_response(200, USER_1)
        ALLOWED.add(10)
        OWNER[10] = 1
        SPEED[10] = "slow"

        with TestClient(app) as client:
            response = client.post(
                "/unregister",
                json={"participant_id": 10},
                headers=AUTH_HEADERS,
            )
        assert response.status_code == 200
        assert 10 not in SPEED
        assert 10 not in ALLOWED
        assert 10 not in OWNER

    @patch("auth_http.requests.get")
    def test_unregister_does_not_affect_other_speeds(self, mock_auth):
        """Unregistering one participant does not affect another's speed."""
        mock_auth.return_value = _mock_response(200, USER_1)
        ALLOWED.update({10, 20})
        OWNER[10] = 1
        OWNER[20] = 1
        SPEED[10] = "slow"
        SPEED[20] = "fast"

        with TestClient(app) as client:
            response = client.post(
                "/unregister",
                json={"participant_id": 10},
                headers=AUTH_HEADERS,
            )
        assert response.status_code == 200
        assert 10 not in SPEED
        # pid 20 should be untouched
        assert SPEED[20] == "fast"
        assert 20 in ALLOWED
