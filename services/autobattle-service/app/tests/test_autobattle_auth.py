"""
Tests for auth changes in autobattle-service (FEAT-071, Task 6).

After the fix:
- /register, /unregister, /mode use get_current_user_via_http (JWT only, no permission check)
- /register validates ownership: user must own the character behind participant_id
- /unregister validates OWNER mapping: user can only unregister their own pids
- /mode works for any authenticated user

Covers:
- Regular player can /register with own participant_id -> 200
- Regular player /register with someone else's participant_id -> 403
- /unregister works for own pids, rejects others'
- /mode works for any authenticated user
- Missing/invalid token -> 401
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# Mock aioredis before importing main
aioredis_mock = MagicMock()
aioredis_mock.from_url = AsyncMock(return_value=MagicMock())
sys.modules["aioredis"] = aioredis_mock

# Mock strategy module
strategy_mock = MagicMock()
sys.modules["strategy"] = strategy_mock

# Mock clients module to control battle state and character owner responses
clients_mock = MagicMock()
clients_mock.get_battle_state = AsyncMock(return_value={})
clients_mock.post_battle_action = AsyncMock(return_value={})
clients_mock.get_character_owner = AsyncMock(return_value=None)
sys.modules["clients"] = clients_mock

from main import app, ALLOWED, OWNER, PID_BATTLE  # noqa: E402

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


BATTLE_STATE_WITH_PARTICIPANTS = {
    "runtime": {
        "current_actor": 10,
        "participants": {
            "10": {"character_id": 100, "hp": 50, "mana": 20, "energy": 30, "stamina": 40, "cooldowns": {}, "fast_slots": []},
            "20": {"character_id": 200, "hp": 60, "mana": 25, "energy": 35, "stamina": 45, "cooldowns": {}, "fast_slots": []},
        },
        "turn_order": [10, 20],
        "turn_number": 1,
        "active_effects": {},
    },
    "snapshot": [
        {"participant_id": 10, "character_id": 100, "attributes": {"max_health": 100, "max_mana": 50, "max_energy": 50, "max_stamina": 50}, "skills": [], "fast_slots": []},
        {"participant_id": 20, "character_id": 200, "attributes": {"max_health": 100, "max_mana": 50, "max_energy": 50, "max_stamina": 50}, "skills": [], "fast_slots": []},
    ],
}


def _cleanup():
    """Reset in-memory state between tests."""
    ALLOWED.clear()
    OWNER.clear()
    PID_BATTLE.clear()


# ═══════════════════════════════════════════════════════════════════════════
# /register — auth + ownership tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRegisterAuth:
    """Auth + ownership tests for POST /register after FEAT-071 fix."""

    def setup_method(self):
        _cleanup()

    def test_missing_token_returns_401(self):
        with TestClient(app) as client:
            response = client.post("/register", json={"participant_id": 10, "battle_id": 5})
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get):
        mock_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.post(
                "/register",
                json={"participant_id": 10, "battle_id": 5},
                headers={"Authorization": "Bearer bad-token"},
            )
        assert response.status_code == 401

    @patch("main.get_character_owner", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_regular_player_own_participant_returns_200(
        self, mock_auth, mock_state, mock_owner
    ):
        """Regular player (no special permissions) can register their own participant."""
        mock_auth.return_value = _mock_response(
            200, {"id": 1, "username": "player", "role": "user", "permissions": []}
        )
        mock_state.return_value = BATTLE_STATE_WITH_PARTICIPANTS
        mock_owner.return_value = 1  # character_id 100 belongs to user 1

        with TestClient(app) as client:
            response = client.post(
                "/register",
                json={"participant_id": 10, "battle_id": 5},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert 10 in ALLOWED
        assert OWNER[10] == 1

    @patch("main.get_character_owner", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_regular_player_other_participant_returns_403(
        self, mock_auth, mock_state, mock_owner
    ):
        """Regular player cannot register someone else's participant."""
        mock_auth.return_value = _mock_response(
            200, {"id": 1, "username": "player", "role": "user", "permissions": []}
        )
        mock_state.return_value = BATTLE_STATE_WITH_PARTICIPANTS
        mock_owner.return_value = 999  # character_id 200 belongs to user 999, not user 1

        with TestClient(app) as client:
            response = client.post(
                "/register",
                json={"participant_id": 20, "battle_id": 5},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code == 403
        assert 20 not in ALLOWED

    @patch("main.get_character_owner", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_participant_not_found_in_battle_returns_403(
        self, mock_auth, mock_state, mock_owner
    ):
        """Registering a participant_id not present in the battle -> 403."""
        mock_auth.return_value = _mock_response(
            200, {"id": 1, "username": "player", "role": "user", "permissions": []}
        )
        mock_state.return_value = BATTLE_STATE_WITH_PARTICIPANTS
        # participant_id 999 does not exist in the battle state

        with TestClient(app) as client:
            response = client.post(
                "/register",
                json={"participant_id": 999, "battle_id": 5},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code == 403

    @patch("main.get_character_owner", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_character_not_found_returns_404(
        self, mock_auth, mock_state, mock_owner
    ):
        """If character-service returns None for character owner -> 404."""
        mock_auth.return_value = _mock_response(
            200, {"id": 1, "username": "player", "role": "user", "permissions": []}
        )
        mock_state.return_value = BATTLE_STATE_WITH_PARTICIPANTS
        mock_owner.return_value = None  # character not found

        with TestClient(app) as client:
            response = client.post(
                "/register",
                json={"participant_id": 10, "battle_id": 5},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code == 404

    @patch("auth_http.requests.get")
    def test_register_without_battle_id_skips_ownership(self, mock_auth):
        """When battle_id=0, ownership validation is skipped."""
        mock_auth.return_value = _mock_response(
            200, {"id": 1, "username": "player", "role": "user", "permissions": []}
        )
        with TestClient(app) as client:
            response = client.post(
                "/register",
                json={"participant_id": 10, "battle_id": 0},
                headers={"Authorization": "Bearer fake-token"},
            )
        # Should succeed (no ownership check when battle_id=0)
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# /unregister — auth + owner validation tests
# ═══════════════════════════════════════════════════════════════════════════

class TestUnregisterAuth:
    """Auth + ownership tests for POST /unregister after FEAT-071 fix."""

    def setup_method(self):
        _cleanup()

    def test_missing_token_returns_401(self):
        with TestClient(app) as client:
            response = client.post("/unregister", json={"participant_id": 10})
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_regular_player_can_unregister_own_pid(self, mock_auth):
        """Player can unregister a pid they previously registered."""
        mock_auth.return_value = _mock_response(
            200, {"id": 1, "username": "player", "role": "user", "permissions": []}
        )
        # Pre-populate state: pid 10 registered by user 1
        ALLOWED.add(10)
        OWNER[10] = 1

        with TestClient(app) as client:
            response = client.post(
                "/unregister",
                json={"participant_id": 10},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code == 200
        assert 10 not in ALLOWED
        assert 10 not in OWNER

    @patch("auth_http.requests.get")
    def test_regular_player_cannot_unregister_others_pid(self, mock_auth):
        """Player cannot unregister a pid registered by someone else."""
        mock_auth.return_value = _mock_response(
            200, {"id": 1, "username": "player", "role": "user", "permissions": []}
        )
        # Pre-populate state: pid 20 registered by user 999
        ALLOWED.add(20)
        OWNER[20] = 999

        with TestClient(app) as client:
            response = client.post(
                "/unregister",
                json={"participant_id": 20},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code == 403
        assert 20 in ALLOWED  # Should NOT be removed

    @patch("auth_http.requests.get")
    def test_unregister_unowned_pid_succeeds(self, mock_auth):
        """Unregistering a pid not in OWNER mapping succeeds (no owner tracking = no restriction)."""
        mock_auth.return_value = _mock_response(
            200, {"id": 1, "username": "player", "role": "user", "permissions": []}
        )
        ALLOWED.add(30)
        # No OWNER entry for pid 30

        with TestClient(app) as client:
            response = client.post(
                "/unregister",
                json={"participant_id": 30},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code == 200
        assert 30 not in ALLOWED


# ═══════════════════════════════════════════════════════════════════════════
# /mode — auth tests (any authenticated user)
# ═══════════════════════════════════════════════════════════════════════════

class TestSetModeAuth:
    """Auth tests for POST /mode after FEAT-071 fix."""

    def test_missing_token_returns_401(self):
        with TestClient(app) as client:
            response = client.post("/mode", json={"mode": "attack"})
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get):
        mock_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.post(
                "/mode",
                json={"mode": "attack"},
                headers={"Authorization": "Bearer bad-token"},
            )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_regular_player_can_set_mode(self, mock_auth):
        """Regular player with no special permissions can set mode."""
        mock_auth.return_value = _mock_response(
            200, {"id": 2, "username": "player", "role": "user", "permissions": []}
        )
        with TestClient(app) as client:
            response = client.post(
                "/mode",
                json={"mode": "attack"},
                headers={"Authorization": "Bearer fake-token"},
            )
        # Should NOT be 401 or 403 — mode is open to all authenticated users
        assert response.status_code not in (401, 403)

    @patch("auth_http.requests.get")
    def test_admin_can_set_mode(self, mock_auth):
        """Admin user can set mode."""
        mock_auth.return_value = _mock_response(
            200, {"id": 1, "username": "admin", "role": "admin", "permissions": ["battles:manage"]}
        )
        with TestClient(app) as client:
            response = client.post(
                "/mode",
                json={"mode": "defense"},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code not in (401, 403)

    @patch("main.strategy.set_mode", side_effect=ValueError("unknown mode invalid_mode_xyz"))
    @patch("auth_http.requests.get")
    def test_invalid_mode_returns_400(self, mock_auth, mock_set_mode):
        """Invalid mode value returns 400."""
        mock_auth.return_value = _mock_response(
            200, {"id": 1, "username": "admin", "role": "admin", "permissions": []}
        )
        with TestClient(app) as client:
            response = client.post(
                "/mode",
                json={"mode": "invalid_mode_xyz"},
                headers={"Authorization": "Bearer fake-token"},
            )
        # Strategy.set_mode raises ValueError for invalid mode -> 400
        assert response.status_code == 400
