"""
Tests for rewards inclusion in battle state endpoints (FEAT-071, Task 6).

After the fix:
- get_state() and get_state_internal() include state.get("rewards") in runtime response
- When rewards are present in Redis state, they appear in the response
- When rewards are absent, rewards is null/None

Covers:
- Internal state endpoint includes rewards when present
- Internal state endpoint returns rewards=null when absent
- Authenticated state endpoint includes rewards when present
- Authenticated state endpoint returns rewards=null when absent
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

from unittest.mock import patch, MagicMock, AsyncMock

# Patch heavy external modules BEFORE importing main
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("aioredis", MagicMock())
sys.modules.setdefault("celery", MagicMock())

import database  # noqa: E402

database.engine = MagicMock()

# Mock all external client modules
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

# Ensure redis_state has required constants/functions
redis_state_mock = sys.modules["redis_state"]
redis_state_mock.ZSET_DEADLINES = "battle:deadlines"
redis_state_mock.KEY_BATTLE_TURNS = "battle:{id}:turns"
redis_state_mock.state_key = MagicMock(return_value="battle:1:state")
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

# Ensure inventory_client
inv_mock = sys.modules["inventory_client"]
inv_mock.get_fast_slots = AsyncMock(return_value=[])

# Ensure character_client
char_mock = sys.modules["character_client"]
char_mock.get_character_profile = AsyncMock(return_value={
    "character_name": "Test",
    "character_photo": "/test.jpg",
})

# Now import main safely
from main import app  # noqa: E402

# Clear startup handlers to avoid connection attempts
app.router.on_startup.clear()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_redis_state(rewards=None):
    """Create a Redis battle state dict."""
    state = {
        "turn_number": 5,
        "next_actor": 1,
        "first_actor": 1,
        "turn_order": [1, 2],
        "total_turns": 5,
        "last_turn": None,
        "deadline_at": "2026-01-01T00:00:00",
        "participants": {
            "1": {
                "character_id": 10, "hp": 100, "mana": 50, "energy": 50,
                "stamina": 50, "team": 0, "cooldowns": {}, "fast_slots": [],
                "max_hp": 100, "max_mana": 50, "max_energy": 50, "max_stamina": 50,
            },
            "2": {
                "character_id": 20, "hp": 0, "mana": 50, "energy": 50,
                "stamina": 50, "team": 1, "cooldowns": {}, "fast_slots": [],
                "max_hp": 100, "max_mana": 50, "max_energy": 50, "max_stamina": 50,
            },
        },
        "active_effects": {},
    }
    if rewards is not None:
        state["rewards"] = rewards
    return state


SAMPLE_REWARDS = {
    "xp": 50,
    "gold": 10,
    "items": [
        {"item_id": 100, "item_name": "Волчья шкура", "quantity": 2},
    ],
}

MOCK_SNAPSHOT = [
    {
        "participant_id": 1, "character_id": 10,
        "name": "Player", "avatar": "/p.jpg",
        "attributes": {
            "max_health": 100, "max_mana": 50,
            "max_energy": 50, "max_stamina": 50,
        },
        "skills": [], "fast_slots": [],
    },
    {
        "participant_id": 2, "character_id": 20,
        "name": "Mob", "avatar": "/m.jpg",
        "attributes": {
            "max_health": 100, "max_mana": 50,
            "max_energy": 50, "max_stamina": 50,
        },
        "skills": [], "fast_slots": [],
    },
]


def _mock_auth_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Internal state endpoint — /internal/{battle_id}/state
# ═══════════════════════════════════════════════════════════════════════════

class TestInternalStateRewards:
    """Tests for rewards in the internal state endpoint."""

    @patch("main.load_snapshot", new_callable=AsyncMock)
    @patch("main.get_cached_snapshot", new_callable=AsyncMock)
    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    def test_state_includes_rewards_when_present(
        self, mock_load, mock_redis, mock_cached_snap, mock_load_snap
    ):
        """Internal state endpoint includes rewards when present in Redis state."""
        mock_load.return_value = _make_redis_state(rewards=SAMPLE_REWARDS)
        mock_redis.return_value = MagicMock()
        mock_cached_snap.return_value = MOCK_SNAPSHOT
        mock_load_snap.return_value = {"participants": MOCK_SNAPSHOT}

        with TestClient(app) as client:
            response = client.get("/battles/internal/1/state")

        assert response.status_code == 200
        data = response.json()
        assert "runtime" in data
        assert data["runtime"]["rewards"] == SAMPLE_REWARDS

    @patch("main.load_snapshot", new_callable=AsyncMock)
    @patch("main.get_cached_snapshot", new_callable=AsyncMock)
    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    def test_state_returns_rewards_null_when_absent(
        self, mock_load, mock_redis, mock_cached_snap, mock_load_snap
    ):
        """Internal state endpoint returns rewards=null when not present in Redis state."""
        mock_load.return_value = _make_redis_state(rewards=None)  # no rewards key
        mock_redis.return_value = MagicMock()
        mock_cached_snap.return_value = MOCK_SNAPSHOT
        mock_load_snap.return_value = {"participants": MOCK_SNAPSHOT}

        with TestClient(app) as client:
            response = client.get("/battles/internal/1/state")

        assert response.status_code == 200
        data = response.json()
        assert "runtime" in data
        assert data["runtime"]["rewards"] is None

    @patch("main.load_state", new_callable=AsyncMock)
    def test_state_returns_404_when_no_state(self, mock_load):
        """Internal state endpoint returns 404 when state is not in Redis."""
        mock_load.return_value = None

        with TestClient(app) as client:
            response = client.get("/battles/internal/999/state")

        assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Authenticated state endpoint — /{battle_id}/state
# ═══════════════════════════════════════════════════════════════════════════

class TestAuthenticatedStateRewards:
    """Tests for rewards in the authenticated state endpoint."""

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.load_snapshot", new_callable=AsyncMock)
    @patch("main.get_cached_snapshot", new_callable=AsyncMock)
    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_state_includes_rewards_when_present(
        self, mock_auth, mock_load, mock_redis, mock_cached_snap,
        mock_load_snap, mock_get_battle
    ):
        """Authenticated state endpoint includes rewards when present."""
        mock_auth.return_value = _mock_auth_response(
            200, {"id": 1, "username": "player", "role": "user", "permissions": []}
        )
        mock_load.return_value = _make_redis_state(rewards=SAMPLE_REWARDS)
        mock_redis.return_value = MagicMock()
        mock_cached_snap.return_value = MOCK_SNAPSHOT
        mock_load_snap.return_value = {"participants": MOCK_SNAPSHOT}
        mock_battle = MagicMock()
        mock_battle.is_paused = False
        mock_get_battle.return_value = mock_battle

        # Mock the DB session for ownership check
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone = MagicMock(return_value=(1,))  # user_id=1 owns character
        mock_db.execute = AsyncMock(return_value=mock_result)

        from database import get_db

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db

        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/1/state",
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            data = response.json()
            assert "runtime" in data
            assert data["runtime"]["rewards"] == SAMPLE_REWARDS
        finally:
            app.dependency_overrides.pop(get_db, None)

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.load_snapshot", new_callable=AsyncMock)
    @patch("main.get_cached_snapshot", new_callable=AsyncMock)
    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_state_returns_rewards_null_when_absent(
        self, mock_auth, mock_load, mock_redis, mock_cached_snap,
        mock_load_snap, mock_get_battle
    ):
        """Authenticated state endpoint returns rewards=null when absent."""
        mock_auth.return_value = _mock_auth_response(
            200, {"id": 1, "username": "player", "role": "user", "permissions": []}
        )
        mock_load.return_value = _make_redis_state(rewards=None)
        mock_redis.return_value = MagicMock()
        mock_cached_snap.return_value = MOCK_SNAPSHOT
        mock_load_snap.return_value = {"participants": MOCK_SNAPSHOT}
        mock_battle = MagicMock()
        mock_battle.is_paused = False
        mock_get_battle.return_value = mock_battle

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone = MagicMock(return_value=(1,))
        mock_db.execute = AsyncMock(return_value=mock_result)

        from database import get_db

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db

        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/1/state",
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            data = response.json()
            assert "runtime" in data
            assert data["runtime"]["rewards"] is None
        finally:
            app.dependency_overrides.pop(get_db, None)
