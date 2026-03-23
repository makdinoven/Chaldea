"""
Tests for admin battle monitor endpoints (FEAT-067, Task #3).

Covers:
1.  GET  /battles/admin/active          — returns active battles with participants
2.  GET  /battles/admin/active          — filters by battle_type
3.  GET  /battles/admin/active          — pagination works
4.  GET  /battles/admin/active          — returns 403 for non-admin
5.  GET  /battles/admin/{id}/state      — returns battle state
6.  GET  /battles/admin/{id}/state      — returns 404 for non-existent battle
7.  GET  /battles/admin/{id}/state      — handles expired Redis gracefully
8.  POST /battles/admin/{id}/force-finish — finishes active battle
9.  POST /battles/admin/{id}/force-finish — returns 400 for already finished
10. POST /battles/admin/{id}/force-finish — returns 404 for non-existent
11. POST /battles/admin/{id}/force-finish — returns 403 for non-admin
12. POST /battles/admin/{id}/force-finish — does NOT write BattleHistory
"""

import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Environment & module-level patches (same approach as test_battle_history.py)
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

# Configure redis_state mock
redis_state_mock = sys.modules["redis_state"]
redis_state_mock.ZSET_DEADLINES = "battle:deadlines"
redis_state_mock.KEY_BATTLE_TURNS = "battle:{id}:turns"
redis_state_mock.init_battle_state = AsyncMock()
redis_state_mock.load_state = AsyncMock(return_value=None)
redis_state_mock.save_state = AsyncMock()
redis_state_mock.get_redis_client = AsyncMock(return_value=AsyncMock())
redis_state_mock.cache_snapshot = AsyncMock()
redis_state_mock.get_cached_snapshot = AsyncMock(return_value=None)
redis_state_mock.state_key = MagicMock(side_effect=lambda bid: f"battle:{bid}:state")

# Configure tasks mock
tasks_mock = sys.modules["tasks"]
tasks_mock.save_log = MagicMock()
tasks_mock.save_log.delay = MagicMock()

# Configure battle_engine mock
engine_mock = sys.modules["battle_engine"]
engine_mock.decrement_cooldowns = MagicMock()
engine_mock.set_cooldown = MagicMock()
engine_mock.fetch_full_attributes = AsyncMock(return_value={})
engine_mock.apply_flat_modifiers = MagicMock(return_value={})
engine_mock.fetch_main_weapon = AsyncMock(return_value={})
engine_mock.compute_damage_with_rolls = AsyncMock(return_value=(0, {}))

# Configure buffs mock
buffs_mock = sys.modules["buffs"]
buffs_mock.decrement_durations = MagicMock()
buffs_mock.aggregate_modifiers = MagicMock(return_value={})
buffs_mock.apply_new_effects = MagicMock()
buffs_mock.build_percent_damage_buffs = MagicMock(return_value={})
buffs_mock.build_percent_resist_buffs = MagicMock(return_value={})

# Configure skills_client mock
skills_mock = sys.modules["skills_client"]
skills_mock.character_has_rank = AsyncMock(return_value=True)
skills_mock.get_rank = AsyncMock(return_value={})
skills_mock.get_item = AsyncMock(return_value={})
skills_mock.character_ranks = AsyncMock(return_value=[])

# Configure mongo_helpers mock
mongo_mock = sys.modules["mongo_helpers"]
mongo_mock.save_snapshot = AsyncMock()
mongo_mock.load_snapshot = AsyncMock(return_value=None)

# Configure rabbitmq_publisher mock
rmq_mock = sys.modules["rabbitmq_publisher"]
rmq_mock.publish_notification = AsyncMock()

# Configure inventory_client mock
inv_mock = sys.modules["inventory_client"]
inv_mock.get_fast_slots = AsyncMock(return_value=[])

# Configure character_client mock
char_mock = sys.modules["character_client"]
char_mock.get_character_profile = AsyncMock(return_value={
    "character_name": "Test",
    "character_photo": "",
})

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


ADMIN_USER = {"id": 1, "username": "admin", "role": "admin", "permissions": ["battles:manage"]}
REGULAR_USER = {"id": 2, "username": "player", "role": "user", "permissions": []}

NOW = datetime(2026, 3, 23, 12, 0, 0)


def _row(*values):
    """Create a mock row that supports index access."""
    row = MagicMock()
    row.__getitem__ = lambda self, i: values[i]
    row.__len__ = lambda self: len(values)
    return row


def _result_with_rows(rows):
    result = MagicMock()
    result.fetchall.return_value = rows
    result.fetchone.return_value = rows[0] if rows else None
    return result


def _result_scalar(value):
    result = MagicMock()
    result.scalar.return_value = value
    result.fetchone.return_value = _row(value)
    return result


# A mock battle object for get_battle return
def _make_battle(battle_id=1, status="in_progress", battle_type="pve", created_at=None):
    battle = MagicMock()
    battle.id = battle_id
    # Use MagicMock with .value to mimic enum
    battle.status = MagicMock()
    battle.status.value = status
    battle.battle_type = MagicMock()
    battle.battle_type.value = battle_type
    battle.created_at = created_at or NOW
    return battle


# Sample battle state (Redis)
SAMPLE_REDIS_STATE = {
    "turn_number": 3,
    "deadline_at": "2026-03-23T14:00:00",
    "next_actor": 1,
    "first_actor": 1,
    "turn_order": [1, 2],
    "total_turns": 3,
    "last_turn": 2,
    "participants": {
        "1": {
            "character_id": 10,
            "team": 0,
            "hp": 80,
            "mana": 50,
            "energy": 100,
            "stamina": 90,
            "max_hp": 100,
            "max_mana": 60,
            "max_energy": 100,
            "max_stamina": 100,
            "cooldowns": {},
            "fast_slots": [],
        },
        "2": {
            "character_id": 20,
            "team": 1,
            "hp": 60,
            "mana": 30,
            "energy": 80,
            "stamina": 70,
            "max_hp": 100,
            "max_mana": 50,
            "max_energy": 100,
            "max_stamina": 100,
            "cooldowns": {},
            "fast_slots": [],
        },
    },
    "active_effects": {},
}


# ===========================================================================
# Test 1: GET /battles/admin/active — returns active battles with participants
# ===========================================================================
class TestAdminListActiveBattles:
    """GET /battles/admin/active returns active battles with participants."""

    @patch("auth_http.requests.get")
    def test_returns_active_battles_with_participants(self, mock_auth_get):
        mock_auth_get.return_value = _mock_response(200, ADMIN_USER)

        call_count = [0]

        async def side_effect(query, params=None):
            call_count[0] += 1
            query_str = str(query)

            # Count query
            if "COUNT(*)" in query_str:
                return _result_scalar(1)

            # Battle list query
            if "SELECT b.id" in query_str:
                return _result_with_rows([
                    _row(1, "in_progress", "pve", NOW, NOW),
                ])

            # Participants query
            if "battle_participants" in query_str:
                return _result_with_rows([
                    _row(1, 101, 10, 0, "Артас", 5, False),
                    _row(1, 102, 20, 1, "Гоблин", 3, True),
                ])

            return _result_with_rows([])

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/admin/active",
                    headers={"Authorization": "Bearer admin-token"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["battles"]) == 1

        battle = data["battles"][0]
        assert battle["id"] == 1
        assert battle["status"] == "in_progress"
        assert battle["battle_type"] == "pve"
        assert len(battle["participants"]) == 2

        p0 = battle["participants"][0]
        assert p0["participant_id"] == 101
        assert p0["character_name"] == "Артас"
        assert p0["level"] == 5
        assert p0["is_npc"] is False

        p1 = battle["participants"][1]
        assert p1["character_name"] == "Гоблин"
        assert p1["is_npc"] is True


# ===========================================================================
# Test 2: GET /battles/admin/active — filters by battle_type
# ===========================================================================
class TestAdminListFilterByType:
    """GET /battles/admin/active filters by battle_type."""

    @patch("auth_http.requests.get")
    def test_filters_by_battle_type(self, mock_auth_get):
        mock_auth_get.return_value = _mock_response(200, ADMIN_USER)

        captured_params = {}

        async def side_effect(query, params=None):
            query_str = str(query)

            if "COUNT(*)" in query_str:
                if params:
                    captured_params.update(params)
                return _result_scalar(2)

            if "SELECT b.id" in query_str:
                return _result_with_rows([])

            return _result_with_rows([])

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/admin/active?battle_type=pvp_training",
                    headers={"Authorization": "Bearer admin-token"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        # Verify filter parameter was passed to query
        assert captured_params.get("bt") == "pvp_training"


# ===========================================================================
# Test 3: GET /battles/admin/active — pagination works
# ===========================================================================
class TestAdminListPagination:
    """GET /battles/admin/active pagination works correctly."""

    @patch("auth_http.requests.get")
    def test_pagination_params(self, mock_auth_get):
        mock_auth_get.return_value = _mock_response(200, ADMIN_USER)

        captured_params = {}

        async def side_effect(query, params=None):
            query_str = str(query)

            if "COUNT(*)" in query_str:
                return _result_scalar(30)

            if "SELECT b.id" in query_str:
                if params:
                    captured_params.update(params)
                return _result_with_rows([])

            return _result_with_rows([])

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/admin/active?page=2&per_page=10",
                    headers={"Authorization": "Bearer admin-token"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["per_page"] == 10
        assert data["total"] == 30
        # OFFSET should be (page-1)*per_page = 10
        assert captured_params.get("off") == 10
        assert captured_params.get("lim") == 10


# ===========================================================================
# Test 4: GET /battles/admin/active — 403 for non-admin
# ===========================================================================
class TestAdminListForbidden:
    """GET /battles/admin/active returns 403 for non-admin user."""

    @patch("auth_http.requests.get")
    def test_non_admin_gets_403(self, mock_auth_get):
        mock_auth_get.return_value = _mock_response(200, REGULAR_USER)

        with TestClient(app) as client:
            response = client.get(
                "/battles/admin/active",
                headers={"Authorization": "Bearer user-token"},
            )

        assert response.status_code == 403

    def test_unauthenticated_gets_401(self):
        with TestClient(app) as client:
            response = client.get("/battles/admin/active")
        assert response.status_code == 401


# ===========================================================================
# Test 5: GET /battles/admin/{id}/state — returns battle state
# ===========================================================================
class TestAdminGetBattleState:
    """GET /battles/admin/{id}/state returns full battle state."""

    @patch("main.get_cached_snapshot", new_callable=AsyncMock)
    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_returns_state_with_redis(
        self, mock_auth_get, mock_get_battle, mock_load_state,
        mock_get_redis, mock_get_snapshot,
    ):
        mock_auth_get.return_value = _mock_response(200, ADMIN_USER)
        mock_get_battle.return_value = _make_battle(battle_id=1)
        mock_load_state.return_value = SAMPLE_REDIS_STATE
        mock_get_redis.return_value = AsyncMock()
        mock_get_snapshot.return_value = [
            {"participant_id": 1, "character_id": 10, "name": "Артас", "avatar": None, "attributes": {}},
            {"participant_id": 2, "character_id": 20, "name": "Гоблин", "avatar": None, "attributes": {}},
        ]

        mock_db = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/admin/1/state",
                    headers={"Authorization": "Bearer admin-token"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()

        assert data["has_redis_state"] is True
        assert data["battle"]["id"] == 1
        assert data["battle"]["status"] == "in_progress"

        # Runtime should contain participant data
        assert data["runtime"] is not None
        assert data["runtime"]["turn_number"] == 3
        assert "1" in data["runtime"]["participants"]
        assert data["runtime"]["participants"]["1"]["hp"] == 80
        assert data["runtime"]["participants"]["1"]["max_hp"] == 100

        # Snapshot should be present
        assert data["snapshot"] is not None
        assert len(data["snapshot"]) == 2


# ===========================================================================
# Test 6: GET /battles/admin/{id}/state — 404 for non-existent battle
# ===========================================================================
class TestAdminStateNotFound:
    """GET /battles/admin/{id}/state returns 404 for non-existent battle."""

    @patch("main.get_battle", new_callable=AsyncMock, return_value=None)
    @patch("auth_http.requests.get")
    def test_returns_404(self, mock_auth_get, mock_get_battle):
        mock_auth_get.return_value = _mock_response(200, ADMIN_USER)

        mock_db = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/admin/99999/state",
                    headers={"Authorization": "Bearer admin-token"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404
        assert "не найден" in response.json()["detail"].lower() or "найден" in response.json()["detail"]


# ===========================================================================
# Test 7: GET /battles/admin/{id}/state — handles expired Redis gracefully
# ===========================================================================
class TestAdminStateExpiredRedis:
    """GET /battles/admin/{id}/state returns graceful response when Redis state expired."""

    @patch("main.load_snapshot", new_callable=AsyncMock, return_value=None)
    @patch("main.get_cached_snapshot", new_callable=AsyncMock, return_value=None)
    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock, return_value=None)
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_expired_redis_returns_null_runtime(
        self, mock_auth_get, mock_get_battle, mock_load_state,
        mock_get_redis, mock_get_snapshot, mock_load_snapshot,
    ):
        mock_auth_get.return_value = _mock_response(200, ADMIN_USER)
        mock_get_battle.return_value = _make_battle(battle_id=5)
        mock_get_redis.return_value = AsyncMock()

        mock_db = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/admin/5/state",
                    headers={"Authorization": "Bearer admin-token"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["has_redis_state"] is False
        assert data["runtime"] is None
        assert data["battle"]["id"] == 5


# ===========================================================================
# Test 8: POST /battles/admin/{id}/force-finish — finishes active battle
# ===========================================================================
class TestAdminForceFinish:
    """POST /battles/admin/{id}/force-finish finishes an active battle."""

    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.finish_battle", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_finishes_active_battle(
        self, mock_auth_get, mock_get_battle, mock_load_state,
        mock_finish, mock_get_redis,
    ):
        mock_auth_get.return_value = _mock_response(200, ADMIN_USER)
        mock_get_battle.return_value = _make_battle(battle_id=1, status="in_progress")
        mock_load_state.return_value = SAMPLE_REDIS_STATE

        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/battles/admin/1/force-finish",
                    headers={"Authorization": "Bearer admin-token"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["battle_id"] == 1
        assert "завершён" in data["message"]

        # Verify finish_battle was called
        mock_finish.assert_called_once()

        # Verify Redis cleanup was performed
        mock_redis.delete.assert_called()
        mock_redis.publish.assert_called_once()


# ===========================================================================
# Test 9: POST /battles/admin/{id}/force-finish — 400 for already finished
# ===========================================================================
class TestAdminForceFinishAlreadyDone:
    """POST /battles/admin/{id}/force-finish returns 400 for already finished battle."""

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_already_finished_returns_400(self, mock_auth_get, mock_get_battle):
        mock_auth_get.return_value = _mock_response(200, ADMIN_USER)
        mock_get_battle.return_value = _make_battle(battle_id=2, status="finished")

        mock_db = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/battles/admin/2/force-finish",
                    headers={"Authorization": "Bearer admin-token"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 400
        assert "завершён" in response.json()["detail"]

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_forfeit_returns_400(self, mock_auth_get, mock_get_battle):
        mock_auth_get.return_value = _mock_response(200, ADMIN_USER)
        mock_get_battle.return_value = _make_battle(battle_id=3, status="forfeit")

        mock_db = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/battles/admin/3/force-finish",
                    headers={"Authorization": "Bearer admin-token"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 400


# ===========================================================================
# Test 10: POST /battles/admin/{id}/force-finish — 404 for non-existent
# ===========================================================================
class TestAdminForceFinishNotFound:
    """POST /battles/admin/{id}/force-finish returns 404 for non-existent battle."""

    @patch("main.get_battle", new_callable=AsyncMock, return_value=None)
    @patch("auth_http.requests.get")
    def test_returns_404(self, mock_auth_get, mock_get_battle):
        mock_auth_get.return_value = _mock_response(200, ADMIN_USER)

        mock_db = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/battles/admin/99999/force-finish",
                    headers={"Authorization": "Bearer admin-token"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404


# ===========================================================================
# Test 11: POST /battles/admin/{id}/force-finish — 403 for non-admin
# ===========================================================================
class TestAdminForceFinishForbidden:
    """POST /battles/admin/{id}/force-finish returns 403 for non-admin user."""

    @patch("auth_http.requests.get")
    def test_non_admin_gets_403(self, mock_auth_get):
        mock_auth_get.return_value = _mock_response(200, REGULAR_USER)

        with TestClient(app) as client:
            response = client.post(
                "/battles/admin/1/force-finish",
                headers={"Authorization": "Bearer user-token"},
            )

        assert response.status_code == 403

    def test_unauthenticated_gets_401(self):
        with TestClient(app) as client:
            response = client.post("/battles/admin/1/force-finish")
        assert response.status_code == 401


# ===========================================================================
# Test 12: POST /battles/admin/{id}/force-finish — does NOT write BattleHistory
# ===========================================================================
class TestAdminForceFinishNoBattleHistory:
    """Force-finish does NOT write BattleHistory records."""

    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.finish_battle", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_no_history_written(
        self, mock_auth_get, mock_get_battle, mock_load_state,
        mock_finish, mock_get_redis,
    ):
        mock_auth_get.return_value = _mock_response(200, ADMIN_USER)
        mock_get_battle.return_value = _make_battle(battle_id=7, status="in_progress")
        mock_load_state.return_value = SAMPLE_REDIS_STATE

        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/battles/admin/7/force-finish",
                    headers={"Authorization": "Bearer admin-token"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200

        # Verify that no BattleHistory was written.
        # The force-finish endpoint uses db.execute for resource sync and
        # finish_battle for status change. It should NOT insert into
        # battle_history. Check that db.execute calls do NOT contain
        # "battle_history" or "INSERT INTO battle_history".
        for call_args in mock_db.execute.call_args_list:
            query_str = str(call_args[0][0]) if call_args[0] else ""
            assert "battle_history" not in query_str.lower(), \
                "Force-finish should NOT write BattleHistory records"
