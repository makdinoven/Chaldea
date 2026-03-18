"""
Tests for endpoint authentication in battle-service.

Covers:
- B1: POST /battles/          — ownership (at least one character belongs to user)
- B2: POST /battles/{bid}/action — ownership (participant's character belongs to user)
- B3: GET  /battles/{bid}/state  — ownership (user has character in battle)

The battle-service is complex (Redis, Mongo, Celery), so we focus on:
- 401 tests (no token) — straightforward
- 403 tests where ownership check is the first gate after auth

Uses dependency overrides and module-level patches to avoid real connections.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# Patch heavy external modules BEFORE importing main
# These modules try to connect to Redis/Mongo/Celery on import
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("aioredis", MagicMock())
sys.modules.setdefault("celery", MagicMock())

# Patch redis_state, mongo_helpers, tasks, etc. before main import
import database  # noqa: E402

database.engine = MagicMock()

# Mock all external client modules to prevent actual connections
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
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

# Ensure redis_state has the required constants/functions
redis_state_mock = sys.modules["redis_state"]
redis_state_mock.ZSET_DEADLINES = "battle:deadlines"
redis_state_mock.KEY_BATTLE_TURNS = "battle:{id}:turns"
redis_state_mock.init_battle_state = AsyncMock()
redis_state_mock.load_state = AsyncMock(return_value=None)
redis_state_mock.save_state = AsyncMock()
redis_state_mock.get_redis_client = AsyncMock(return_value=MagicMock())
redis_state_mock.cache_snapshot = AsyncMock()
redis_state_mock.get_cached_snapshot = AsyncMock(return_value=None)

# Ensure tasks has save_log
tasks_mock = sys.modules["tasks"]
tasks_mock.save_log = MagicMock()
tasks_mock.save_log.delay = MagicMock()

# Ensure battle_engine has the required functions
engine_mock = sys.modules["battle_engine"]
engine_mock.decrement_cooldowns = MagicMock()
engine_mock.set_cooldown = MagicMock()
engine_mock.fetch_full_attributes = AsyncMock(return_value={})
engine_mock.apply_flat_modifiers = MagicMock(return_value={})
engine_mock.fetch_main_weapon = AsyncMock(return_value={})
engine_mock.compute_damage_with_rolls = AsyncMock(return_value=(0, {}))

# Ensure buffs has the required functions
buffs_mock = sys.modules["buffs"]
buffs_mock.decrement_durations = MagicMock()
buffs_mock.aggregate_modifiers = MagicMock(return_value={})
buffs_mock.apply_new_effects = MagicMock()
buffs_mock.build_percent_damage_buffs = MagicMock(return_value={})
buffs_mock.build_percent_resist_buffs = MagicMock(return_value={})

# Ensure skills_client has the required functions
skills_mock = sys.modules["skills_client"]
skills_mock.character_has_rank = AsyncMock(return_value=True)
skills_mock.get_rank = AsyncMock(return_value={})
skills_mock.get_item = AsyncMock(return_value={})
skills_mock.character_ranks = AsyncMock(return_value=[])

# Ensure mongo_helpers
mongo_mock = sys.modules["mongo_helpers"]
mongo_mock.save_snapshot = AsyncMock()
mongo_mock.load_snapshot = AsyncMock(return_value=None)

# Now import main safely
from main import app  # noqa: E402
from database import get_db  # noqa: E402

# Clear startup handlers to avoid connection attempts
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


CREATE_BATTLE_PAYLOAD = {
    "players": [
        {"character_id": 1, "team": 0},
        {"character_id": 2, "team": 1},
    ]
}

ACTION_PAYLOAD = {
    "participant_id": 1,
    "skills": {
        "attack_rank_id": 1,
        "defense_rank_id": None,
        "support_rank_id": None,
        "item_id": None,
    },
}


def _make_mock_db(char_owner_map: dict = None):
    """Return an async mock DB session.

    *char_owner_map* maps character_id -> user_id for the ownership query.
    """
    mock_db = AsyncMock()

    async def _execute(query, params=None):
        result = MagicMock()
        if char_owner_map and params and "cid" in params:
            cid = params["cid"]
            uid = char_owner_map.get(cid)
            if uid is not None:
                result.fetchone.return_value = (uid,)
            else:
                result.fetchone.return_value = None
        else:
            result.fetchone.return_value = None
        return result

    mock_db.execute = AsyncMock(side_effect=_execute)
    return mock_db


# ═══════════════════════════════════════════════════════════════════════════
# B1: POST /battles/ — at least one character must belong to user
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateBattleAuth:
    """Auth tests for POST /battles/."""

    def test_missing_token_returns_401(self):
        with TestClient(app) as client:
            response = client.post("/battles/", json=CREATE_BATTLE_PAYLOAD)
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get):
        mock_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.post(
                "/battles/",
                json=CREATE_BATTLE_PAYLOAD,
                headers={"Authorization": "Bearer bad-token"},
            )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_no_owned_character_returns_403(self, mock_auth_get):
        """User does not own any character in the battle -> 403."""
        mock_auth_get.return_value = _mock_response(
            200, {"id": 99, "username": "hacker", "role": "user", "permissions": []}
        )
        # Characters 1 and 2 belong to user_id=1 and user_id=2
        mock_db = _make_mock_db({1: 1, 2: 2})

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/battles/",
                    json=CREATE_BATTLE_PAYLOAD,
                    headers={"Authorization": "Bearer fake-token"},
                )
            assert response.status_code == 403
        finally:
            app.dependency_overrides.pop(get_db, None)


# ═══════════════════════════════════════════════════════════════════════════
# B2: POST /battles/{bid}/action — participant's character must belong to user
# ═══════════════════════════════════════════════════════════════════════════


class TestBattleActionAuth:
    """Auth tests for POST /battles/{bid}/action."""

    def test_missing_token_returns_401(self):
        with TestClient(app) as client:
            response = client.post("/battles/1/action", json=ACTION_PAYLOAD)
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get):
        mock_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.post(
                "/battles/1/action",
                json=ACTION_PAYLOAD,
                headers={"Authorization": "Bearer bad-token"},
            )
        assert response.status_code == 401

    @patch("main.load_state", new_callable=AsyncMock, return_value=None)
    @patch("auth_http.requests.get")
    def test_no_battle_state_returns_404(self, mock_auth_get, mock_load_state):
        """Battle state not in Redis -> 404 (after auth passes)."""
        mock_auth_get.return_value = _mock_response(
            200, {"id": 5, "username": "user", "role": "user", "permissions": []}
        )

        mock_db = AsyncMock()

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/battles/999/action",
                    json=ACTION_PAYLOAD,
                    headers={"Authorization": "Bearer fake-token"},
                )
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_db, None)

    @patch("main.load_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_wrong_owner_returns_403(self, mock_auth_get, mock_load_state):
        """Participant's character does not belong to user -> 403."""
        mock_auth_get.return_value = _mock_response(
            200, {"id": 99, "username": "hacker", "role": "user", "permissions": []}
        )
        # Battle state has participant 1 with character_id=10
        battle_state = {
            "turn_number": 1,
            "next_actor": 1,
            "first_actor": 1,
            "turn_order": [1, 2],
            "total_turns": 0,
            "last_turn": None,
            "deadline_at": "2026-01-01T00:00:00",
            "participants": {
                "1": {"character_id": 10, "hp": 100, "mana": 50, "energy": 50,
                       "stamina": 50, "cooldowns": {}, "fast_slots": []},
                "2": {"character_id": 20, "hp": 100, "mana": 50, "energy": 50,
                       "stamina": 50, "cooldowns": {}, "fast_slots": []},
            },
            "active_effects": {},
        }
        mock_load_state.return_value = battle_state

        # Character 10 belongs to user_id=1 (not 99)
        mock_db = _make_mock_db({10: 1, 20: 2})

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/battles/1/action",
                    json=ACTION_PAYLOAD,
                    headers={"Authorization": "Bearer fake-token"},
                )
            assert response.status_code == 403
        finally:
            app.dependency_overrides.pop(get_db, None)


# ═══════════════════════════════════════════════════════════════════════════
# B3: GET /battles/{bid}/state — user must have character in battle
# ═══════════════════════════════════════════════════════════════════════════


class TestBattleStateAuth:
    """Auth tests for GET /battles/{bid}/state."""

    def test_missing_token_returns_401(self):
        with TestClient(app) as client:
            response = client.get("/battles/1/state")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get):
        mock_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.get(
                "/battles/1/state",
                headers={"Authorization": "Bearer bad-token"},
            )
        assert response.status_code == 401

    @patch("main.load_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_not_participant_returns_403(self, mock_auth_get, mock_load_state):
        """User has no character in the battle -> 403."""
        mock_auth_get.return_value = _mock_response(
            200, {"id": 99, "username": "outsider", "role": "user", "permissions": []}
        )
        battle_state = {
            "turn_number": 1,
            "next_actor": 1,
            "first_actor": 1,
            "turn_order": [1, 2],
            "total_turns": 0,
            "last_turn": None,
            "deadline_at": "2026-01-01T00:00:00",
            "participants": {
                "1": {"character_id": 10, "hp": 100, "mana": 50, "energy": 50,
                       "stamina": 50, "cooldowns": {}, "fast_slots": []},
                "2": {"character_id": 20, "hp": 100, "mana": 50, "energy": 50,
                       "stamina": 50, "cooldowns": {}, "fast_slots": []},
            },
            "active_effects": {},
        }
        mock_load_state.return_value = battle_state

        # Neither character belongs to user 99
        mock_db = _make_mock_db({10: 1, 20: 2})

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/1/state",
                    headers={"Authorization": "Bearer fake-token"},
                )
            assert response.status_code == 403
        finally:
            app.dependency_overrides.pop(get_db, None)
