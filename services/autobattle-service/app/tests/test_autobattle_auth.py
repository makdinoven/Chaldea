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

import main
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
    def test_unregister_unowned_pid_refused(self, mock_auth):
        """FEAT-212 (ISSUES.md): a pid registered internally (mob/NPC, no OWNER entry and
        no resolvable owner) can no longer be switched off by any player."""
        mock_auth.return_value = _mock_response(
            200, {"id": 1, "username": "player", "role": "user", "permissions": []}
        )
        ALLOWED.add(30)
        # No OWNER entry for pid 30, no known battle -> owner unresolvable

        with TestClient(app) as client:
            response = client.post(
                "/unregister",
                json={"participant_id": 30},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code == 403
        assert response.json()["detail"] == "Вы не можете отменить автобой чужого персонажа"
        assert 30 in ALLOWED


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

    @patch("main.strategy_for")
    @patch("auth_http.requests.get")
    def test_invalid_mode_returns_400(self, mock_auth, mock_strategy_for):
        """Invalid mode value returns 400."""
        mock_strategy_for.return_value.set_mode.side_effect = ValueError(
            "unknown mode invalid_mode_xyz"
        )
        # Режим настраивается только зарегистрированному участнику: незнакомый
        # pid отсекается раньше проверки самого режима (404).
        main.OWNER[10] = 1
        mock_auth.return_value = _mock_response(
            200, {"id": 1, "username": "admin", "role": "admin", "permissions": []}
        )
        with TestClient(app) as client:
            response = client.post(
                "/mode",
                json={"participant_id": 10, "mode": "invalid_mode_xyz"},
                headers={"Authorization": "Bearer fake-token"},
            )
        # Strategy.set_mode raises ValueError for invalid mode -> 400
        assert response.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# FEAT-212: owner rules for /unregister and /speed, escorts refused on /register
# ═══════════════════════════════════════════════════════════════════════════

from main import SPEED  # noqa: E402

PLAYER_1 = {"id": 1, "username": "player", "role": "user", "permissions": []}
MOB_PID, ESCORT_PID, OWN_PID = 40, 41, 42
MSG_UNREGISTER = "Вы не можете отменить автобой чужого персонажа"
MSG_SPEED = "Вы не можете менять скорость чужого автобоя"
MSG_ESCORT = "Охранникам каравана автобой недоступен — в налёте вы ходите сами"


def _raid_state(current_actor=99):
    return {
        "runtime": {
            "current_actor": current_actor,
            "participants": {
                str(MOB_PID): {"character_id": 900},
                str(ESCORT_PID): {"character_id": 300, "autobattle_forbidden": True},
                str(OWN_PID): {"character_id": 100, "autobattle_forbidden": False},
            },
        },
    }


async def _owner_of(character_id):
    # mob 900 has no owner; escort 300 and character 100 belong to user 1
    return {900: None, 300: 1, 100: 1}.get(character_id)


class TestFeat212OwnerRules:

    def setup_method(self):
        _cleanup()
        SPEED.clear()

    @staticmethod
    def _post(url, body):
        with TestClient(app) as client:
            return client.post(url, json=body, headers={"Authorization": "Bearer fake-token"})

    # ---- /unregister ------------------------------------------------------
    @patch("main.get_character_owner", side_effect=_owner_of)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_unregister_internal_mob_refused(self, mock_auth, mock_state, _owner):
        mock_auth.return_value = _mock_response(200, PLAYER_1)
        mock_state.return_value = _raid_state()
        ALLOWED.add(MOB_PID)
        PID_BATTLE[MOB_PID] = 5          # registered by battle-service, no OWNER entry
        r = self._post("/unregister", {"participant_id": MOB_PID})
        assert r.status_code == 403
        assert r.json()["detail"] == MSG_UNREGISTER
        assert MOB_PID in ALLOWED
        mock_state.assert_awaited_once_with(5)

    @patch("main.get_character_owner", new_callable=AsyncMock, return_value=999)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_unregister_foreign_character_resolved_by_battle_refused(self, mock_auth, mock_state, _owner):
        mock_auth.return_value = _mock_response(200, PLAYER_1)
        mock_state.return_value = _raid_state()
        ALLOWED.add(OWN_PID)
        PID_BATTLE[OWN_PID] = 5
        r = self._post("/unregister", {"participant_id": OWN_PID})
        assert r.status_code == 403
        assert OWN_PID in ALLOWED

    @patch("main.get_character_owner", side_effect=_owner_of)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_unregister_own_character_resolved_by_battle(self, mock_auth, mock_state, _owner):
        """No OWNER entry, but the battle says the character is mine."""
        mock_auth.return_value = _mock_response(200, PLAYER_1)
        mock_state.return_value = _raid_state()
        ALLOWED.add(OWN_PID)
        PID_BATTLE[OWN_PID] = 5
        r = self._post("/unregister", {"participant_id": OWN_PID})
        assert r.status_code == 200, r.text
        assert OWN_PID not in ALLOWED

    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_unregister_own_registry_entry_skips_the_lookup(self, mock_auth, mock_state):
        mock_auth.return_value = _mock_response(200, PLAYER_1)
        ALLOWED.add(OWN_PID)
        OWNER[OWN_PID] = 1
        PID_BATTLE[OWN_PID] = 5
        assert self._post("/unregister", {"participant_id": OWN_PID}).status_code == 200
        mock_state.assert_not_called()

    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_unregister_unknown_pid_is_a_silent_noop(self, mock_auth, mock_state):
        mock_auth.return_value = _mock_response(200, PLAYER_1)
        r = self._post("/unregister", {"participant_id": 12345})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        mock_state.assert_not_called()

    @patch("main.get_battle_state", new_callable=AsyncMock, side_effect=RuntimeError("404"))
    @patch("auth_http.requests.get")
    def test_unregister_unresolvable_owner_is_refused(self, mock_auth, _state):
        mock_auth.return_value = _mock_response(200, PLAYER_1)
        ALLOWED.add(OWN_PID)
        PID_BATTLE[OWN_PID] = 5
        assert self._post("/unregister", {"participant_id": OWN_PID}).status_code == 403
        assert OWN_PID in ALLOWED

    # ---- /speed -----------------------------------------------------------
    @patch("main.get_character_owner", side_effect=_owner_of)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_speed_of_an_internal_mob_refused(self, mock_auth, mock_state, _owner):
        mock_auth.return_value = _mock_response(200, PLAYER_1)
        mock_state.return_value = _raid_state()
        ALLOWED.add(MOB_PID)
        PID_BATTLE[MOB_PID] = 5
        SPEED[MOB_PID] = "fast"
        r = self._post("/speed", {"participant_id": MOB_PID, "speed": "slow"})
        assert r.status_code == 403
        assert r.json()["detail"] == MSG_SPEED
        assert SPEED[MOB_PID] == "fast"

    @patch("main.get_character_owner", side_effect=_owner_of)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_speed_of_own_character_resolved_by_battle(self, mock_auth, mock_state, _owner):
        mock_auth.return_value = _mock_response(200, PLAYER_1)
        mock_state.return_value = _raid_state()
        ALLOWED.add(OWN_PID)
        PID_BATTLE[OWN_PID] = 5
        r = self._post("/speed", {"participant_id": OWN_PID, "speed": "slow"})
        assert r.status_code == 200, r.text
        assert SPEED[OWN_PID] == "slow"

    @patch("auth_http.requests.get")
    def test_speed_of_a_foreign_registry_entry_refused(self, mock_auth):
        mock_auth.return_value = _mock_response(200, PLAYER_1)
        ALLOWED.add(OWN_PID)
        OWNER[OWN_PID] = 999
        r = self._post("/speed", {"participant_id": OWN_PID, "speed": "slow"})
        assert r.status_code == 403
        assert r.json()["detail"] == MSG_SPEED

    @patch("auth_http.requests.get")
    def test_speed_unregistered_stays_404(self, mock_auth):
        mock_auth.return_value = _mock_response(200, PLAYER_1)
        assert self._post("/speed", {"participant_id": 12345, "speed": "slow"}).status_code == 404

    # ---- /register: escorts ------------------------------------------------
    @patch("main.get_character_owner", side_effect=_owner_of)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_register_escort_refused(self, mock_auth, mock_state, _owner):
        mock_auth.return_value = _mock_response(200, PLAYER_1)
        mock_state.return_value = _raid_state()
        r = self._post("/register", {"participant_id": ESCORT_PID, "battle_id": 5})
        assert r.status_code == 403
        assert r.json()["detail"] == MSG_ESCORT
        assert ESCORT_PID not in ALLOWED and ESCORT_PID not in OWNER

    @patch("main.get_character_owner", side_effect=_owner_of)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_register_escort_with_zero_battle_id_falls_back_to_pid_battle(self, mock_auth, mock_state, _owner):
        mock_auth.return_value = _mock_response(200, PLAYER_1)
        mock_state.return_value = _raid_state()
        PID_BATTLE[ESCORT_PID] = 5      # known from your_turn
        r = self._post("/register", {"participant_id": ESCORT_PID, "battle_id": 0})
        assert r.status_code == 403
        assert r.json()["detail"] == MSG_ESCORT
        mock_state.assert_awaited_once_with(5)
        assert ESCORT_PID not in ALLOWED

    @patch("main.get_character_owner", new_callable=AsyncMock, return_value=999)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_register_zero_battle_id_keeps_the_ownership_check(self, mock_auth, mock_state, _owner):
        mock_auth.return_value = _mock_response(200, PLAYER_1)
        mock_state.return_value = _raid_state()
        PID_BATTLE[OWN_PID] = 5
        r = self._post("/register", {"participant_id": OWN_PID, "battle_id": 0})
        assert r.status_code == 403
        assert OWN_PID not in ALLOWED

    @patch("main.get_character_owner", side_effect=_owner_of)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_register_non_escort_in_the_same_raid_works(self, mock_auth, mock_state, _owner):
        mock_auth.return_value = _mock_response(200, PLAYER_1)
        mock_state.return_value = _raid_state()
        PID_BATTLE[OWN_PID] = 5
        r = self._post("/register", {"participant_id": OWN_PID, "battle_id": 0})
        assert r.status_code == 200, r.text
        assert OWNER[OWN_PID] == 1
        mock_state.assert_awaited_once_with(5)     # the fetched state is reused
