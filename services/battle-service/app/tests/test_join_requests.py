"""
Tests for battle join request endpoints (FEAT-069).

Covers:
- POST /battles/{id}/join-request — submit a join request
  - Happy path (201)
  - Duplicate request (same character, same battle) → 400
  - Character not at the same location → 403
  - Character already in a battle → 400
  - Invalid team (not 0 or 1) → 400
  - Battle not active → 404
  - Character already a participant → 400
  - Character not owned by user → 403
  - Battle without location_id → 400

- Pause/resume:
  - Battle gets paused when first join request is created
  - Action rejected while battle is paused → 400

- GET /battles/{id}/join-requests — list join requests for a battle

- Admin endpoints:
  - GET /battles/admin/join-requests — returns pending requests (admin)
  - POST /battles/admin/join-requests/{id}/approve — participant added
  - POST /battles/admin/join-requests/{id}/reject — request rejected
  - Non-admin gets 403 on admin endpoints
  - Auto-reject pending requests when battle finishes
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta

import pytest

# Patch heavy external modules BEFORE importing main
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("aioredis", MagicMock())
sys.modules.setdefault("celery", MagicMock())

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
redis_state_mock.state_key = MagicMock(return_value="battle:1:state")

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
from auth_http import get_current_user_via_http, require_permission, UserRead  # noqa: E402

# Clear startup handlers to avoid connection attempts
app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _row(*values):
    """Create a mock row that supports index access."""
    row = MagicMock()
    row.__getitem__ = lambda self, i: values[i]
    row.__len__ = lambda self: len(values)
    return row


def _result_with_row(row_data):
    """Create a mock result that returns a single row."""
    result = MagicMock()
    result.fetchone.return_value = row_data
    return result


def _result_empty():
    """Create a mock result that returns None."""
    result = MagicMock()
    result.fetchone.return_value = None
    return result


def _result_with_rows(rows):
    """Create a mock result that returns multiple rows."""
    result = MagicMock()
    result.fetchall.return_value = rows
    result.fetchone.return_value = rows[0] if rows else None
    return result


def _result_scalar(value):
    """Create a mock result that returns a scalar."""
    result = MagicMock()
    result.scalar.return_value = value
    result.fetchone.return_value = _row(value)
    return result


def _make_user(user_id=1, username="testuser", role="user", permissions=None):
    return UserRead(
        id=user_id,
        username=username,
        role=role,
        permissions=permissions or [],
    )


def _make_admin(user_id=99, username="admin"):
    return UserRead(
        id=user_id,
        username=username,
        role="admin",
        permissions=["battles:manage"],
    )


def _make_battle(
    battle_id=1, status="in_progress", battle_type="pve",
    location_id=100, is_paused=False, created_at=None,
):
    """Create a mock Battle ORM object."""
    battle = MagicMock()
    battle.id = battle_id
    battle.status = MagicMock()
    battle.status.value = status
    battle.battle_type = MagicMock()
    battle.battle_type.value = battle_type
    battle.location_id = location_id
    battle.is_paused = is_paused
    battle.created_at = created_at or datetime(2026, 3, 23, 12, 0, 0)
    return battle


def _get_client_with_mocks(user, mock_db, permission_override=None):
    """Create a TestClient with auth and DB overridden."""
    def override_auth():
        return user

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_current_user_via_http] = override_auth
    app.dependency_overrides[get_db] = override_get_db

    # Override require_permission if needed (for admin endpoints)
    if permission_override is not None:
        # For admin: override the require_permission("battles:manage") dependency
        perm_dep = require_permission("battles:manage")
        if permission_override:
            app.dependency_overrides[perm_dep] = override_auth
        # For non-admin: we don't override — the default will check permissions

    return TestClient(app)


JOIN_REQUEST_PAYLOAD = {
    "character_id": 10,
    "team": 0,
}


# ═══════════════════════════════════════════════════════════════════════════
# Tests: POST /battles/{id}/join-request — Create join request
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateJoinRequest:
    """Tests for POST /battles/{battle_id}/join-request."""

    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    @patch("main.get_active_battle_for_character", new_callable=AsyncMock)
    @patch("main.pause_battle", new_callable=AsyncMock)
    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_create_join_request_happy_path(
        self, mock_publish, mock_pause, mock_active, mock_verify, mock_get_battle,
    ):
        """Successfully creates a join request -> 201."""
        user = _make_user(user_id=10)
        battle = _make_battle(battle_id=1, location_id=100, is_paused=False)
        mock_get_battle.return_value = battle
        mock_verify.return_value = None
        mock_active.return_value = None  # Not in any battle

        mock_db = AsyncMock()

        # character location query
        char_loc_result = _result_with_row(_row(100))  # same location
        # participant check
        part_result = _result_empty()  # not a participant
        # existing join request check
        existing_result = _result_empty()  # no existing request
        # participants for notification
        participants_result = _result_with_rows([_row(10)])

        call_count = [0]
        async def execute_side_effect(query, params=None):
            call_count[0] += 1
            query_str = str(query)
            if "current_location_id" in query_str:
                return char_loc_result
            if "battle_participants" in query_str and "SELECT id" in query_str.upper():
                return part_result
            if "battle_join_requests" in query_str and "SELECT" in query_str.upper():
                return existing_result
            if "DISTINCT c.user_id" in query_str:
                return participants_result
            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        added_objects = []
        def mock_add(obj):
            obj.id = 999
            obj.battle_id = 1
            obj.character_id = 10
            obj.team = 0
            obj.status = MagicMock()
            obj.status.value = "pending"
            obj.created_at = datetime.utcnow()
            added_objects.append(obj)
        mock_db.add = mock_add

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/1/join-request", json=JOIN_REQUEST_PAYLOAD)

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 999
        assert data["battle_id"] == 1
        assert data["character_id"] == 10
        assert data["team"] == 0
        assert data["status"] == "pending"

        # Battle should have been paused
        mock_pause.assert_called_once_with(mock_db, 1)

    @patch("main.get_battle", new_callable=AsyncMock)
    def test_invalid_team_returns_400(self, mock_get_battle):
        """Invalid team (not 0 or 1) -> 400."""
        user = _make_user(user_id=10)
        mock_db = AsyncMock()

        client = _get_client_with_mocks(user, mock_db)
        response = client.post(
            "/battles/1/join-request",
            json={"character_id": 10, "team": 5},
        )

        assert response.status_code == 400
        assert "0 или 1" in response.json()["detail"]

    @patch("main.get_battle", new_callable=AsyncMock)
    def test_battle_not_found_returns_404(self, mock_get_battle):
        """Battle does not exist -> 404."""
        user = _make_user(user_id=10)
        mock_get_battle.return_value = None

        mock_db = AsyncMock()

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/999/join-request", json=JOIN_REQUEST_PAYLOAD)

        assert response.status_code == 404
        assert "не найден" in response.json()["detail"]

    @patch("main.get_battle", new_callable=AsyncMock)
    def test_battle_not_active_returns_404(self, mock_get_battle):
        """Battle is finished -> 404 'not active'."""
        user = _make_user(user_id=10)
        battle = _make_battle(status="finished")
        mock_get_battle.return_value = battle

        mock_db = AsyncMock()

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/1/join-request", json=JOIN_REQUEST_PAYLOAD)

        assert response.status_code == 404
        assert "не активен" in response.json()["detail"]

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    def test_character_not_at_same_location_returns_403(
        self, mock_verify, mock_get_battle,
    ):
        """Character at different location -> 403."""
        user = _make_user(user_id=10)
        battle = _make_battle(location_id=100)
        mock_get_battle.return_value = battle
        mock_verify.return_value = None

        mock_db = AsyncMock()

        # Character is at location 200, battle at 100
        async def execute_side_effect(query, params=None):
            query_str = str(query)
            if "current_location_id" in query_str:
                return _result_with_row(_row(200))  # different location
            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/1/join-request", json=JOIN_REQUEST_PAYLOAD)

        assert response.status_code == 403
        assert "локации" in response.json()["detail"]

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    @patch("main.get_active_battle_for_character", new_callable=AsyncMock)
    def test_character_already_in_battle_returns_400(
        self, mock_active, mock_verify, mock_get_battle,
    ):
        """Character is in another active battle -> 400."""
        user = _make_user(user_id=10)
        battle = _make_battle(location_id=100)
        mock_get_battle.return_value = battle
        mock_verify.return_value = None
        mock_active.return_value = 42  # Already in battle 42

        mock_db = AsyncMock()
        async def execute_side_effect(query, params=None):
            query_str = str(query)
            if "current_location_id" in query_str:
                return _result_with_row(_row(100))
            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/1/join-request", json=JOIN_REQUEST_PAYLOAD)

        assert response.status_code == 400
        assert "уже участвует" in response.json()["detail"]

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    @patch("main.get_active_battle_for_character", new_callable=AsyncMock)
    def test_character_already_a_participant_returns_400(
        self, mock_active, mock_verify, mock_get_battle,
    ):
        """Character is already a participant in this battle -> 400."""
        user = _make_user(user_id=10)
        battle = _make_battle(location_id=100)
        mock_get_battle.return_value = battle
        mock_verify.return_value = None
        mock_active.return_value = None

        mock_db = AsyncMock()
        async def execute_side_effect(query, params=None):
            query_str = str(query)
            if "current_location_id" in query_str:
                return _result_with_row(_row(100))
            if "battle_participants" in query_str:
                return _result_with_row(_row(1))  # already a participant
            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/1/join-request", json=JOIN_REQUEST_PAYLOAD)

        assert response.status_code == 400
        assert "уже является участником" in response.json()["detail"]

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    @patch("main.get_active_battle_for_character", new_callable=AsyncMock)
    def test_duplicate_join_request_returns_400(
        self, mock_active, mock_verify, mock_get_battle,
    ):
        """Duplicate request (same character, same battle) -> 400."""
        user = _make_user(user_id=10)
        battle = _make_battle(location_id=100)
        mock_get_battle.return_value = battle
        mock_verify.return_value = None
        mock_active.return_value = None

        mock_db = AsyncMock()
        async def execute_side_effect(query, params=None):
            query_str = str(query)
            if "current_location_id" in query_str:
                return _result_with_row(_row(100))
            if "battle_participants" in query_str:
                return _result_empty()  # not a participant
            if "battle_join_requests" in query_str:
                return _result_with_row(_row(123, "pending"))  # existing request
            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/1/join-request", json=JOIN_REQUEST_PAYLOAD)

        assert response.status_code == 400
        assert "уже подана" in response.json()["detail"]

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    def test_battle_without_location_returns_400(
        self, mock_verify, mock_get_battle,
    ):
        """Battle without location_id -> 400."""
        user = _make_user(user_id=10)
        battle = _make_battle(location_id=None)
        mock_get_battle.return_value = battle
        mock_verify.return_value = None

        mock_db = AsyncMock()

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/1/join-request", json=JOIN_REQUEST_PAYLOAD)

        assert response.status_code == 400
        assert "локации" in response.json()["detail"]

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    def test_character_not_owned_by_user_returns_403(
        self, mock_verify, mock_get_battle,
    ):
        """Character does not belong to the user -> 403."""
        from fastapi import HTTPException
        user = _make_user(user_id=999)
        battle = _make_battle(location_id=100)
        mock_get_battle.return_value = battle
        mock_verify.side_effect = HTTPException(
            status_code=403,
            detail="Вы можете управлять только своими персонажами",
        )

        mock_db = AsyncMock()

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/1/join-request", json=JOIN_REQUEST_PAYLOAD)

        assert response.status_code == 403
        assert "своими персонажами" in response.json()["detail"]

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    @patch("main.get_active_battle_for_character", new_callable=AsyncMock)
    @patch("main.pause_battle", new_callable=AsyncMock)
    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_battle_paused_when_first_join_request_created(
        self, mock_publish, mock_pause, mock_active, mock_verify, mock_get_battle,
    ):
        """Battle gets paused when first join request is created (is_paused=False initially)."""
        user = _make_user(user_id=10)
        battle = _make_battle(location_id=100, is_paused=False)
        mock_get_battle.return_value = battle
        mock_verify.return_value = None
        mock_active.return_value = None

        mock_db = AsyncMock()
        async def execute_side_effect(query, params=None):
            query_str = str(query)
            if "current_location_id" in query_str:
                return _result_with_row(_row(100))
            if "battle_participants" in query_str and "SELECT id" in query_str.upper():
                return _result_empty()
            if "battle_join_requests" in query_str and "SELECT" in query_str.upper():
                return _result_empty()
            if "DISTINCT c.user_id" in query_str:
                return _result_with_rows([_row(10)])
            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        def mock_add(obj):
            obj.id = 999
            obj.battle_id = 1
            obj.character_id = 10
            obj.team = 0
            obj.status = MagicMock()
            obj.status.value = "pending"
            obj.created_at = datetime.utcnow()
        mock_db.add = mock_add

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/1/join-request", json=JOIN_REQUEST_PAYLOAD)

        assert response.status_code == 201
        mock_pause.assert_called_once_with(mock_db, 1)

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.verify_character_ownership", new_callable=AsyncMock)
    @patch("main.get_active_battle_for_character", new_callable=AsyncMock)
    @patch("main.pause_battle", new_callable=AsyncMock)
    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_battle_not_paused_again_if_already_paused(
        self, mock_publish, mock_pause, mock_active, mock_verify, mock_get_battle,
    ):
        """Battle is already paused -> pause_battle not called again."""
        user = _make_user(user_id=10)
        battle = _make_battle(location_id=100, is_paused=True)
        mock_get_battle.return_value = battle
        mock_verify.return_value = None
        mock_active.return_value = None

        mock_db = AsyncMock()
        async def execute_side_effect(query, params=None):
            query_str = str(query)
            if "current_location_id" in query_str:
                return _result_with_row(_row(100))
            if "battle_participants" in query_str and "SELECT id" in query_str.upper():
                return _result_empty()
            if "battle_join_requests" in query_str and "SELECT" in query_str.upper():
                return _result_empty()
            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        def mock_add(obj):
            obj.id = 1000
            obj.battle_id = 1
            obj.character_id = 10
            obj.team = 0
            obj.status = MagicMock()
            obj.status.value = "pending"
            obj.created_at = datetime.utcnow()
        mock_db.add = mock_add

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/1/join-request", json=JOIN_REQUEST_PAYLOAD)

        assert response.status_code == 201
        mock_pause.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Action rejected while battle is paused
# ═══════════════════════════════════════════════════════════════════════════


class TestActionRejectedWhilePaused:
    """Tests that actions are rejected while a battle is paused."""

    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    def test_action_rejected_when_battle_paused(self, mock_load_state, mock_get_battle):
        """Attempting an action while battle is paused -> 400."""
        user = _make_user(user_id=10)
        battle = _make_battle(status="in_progress")
        mock_get_battle.return_value = battle

        # Redis state with paused=True
        mock_load_state.return_value = {
            "paused": True,
            "turn_number": 1,
            "deadline_at": "2026-03-23T14:00:00",
            "next_actor": 1,
            "first_actor": 1,
            "turn_order": [1, 2],
            "total_turns": 1,
            "last_turn": None,
            "participants": {
                "1": {
                    "character_id": 10,
                    "team": 0,
                    "hp": 100,
                    "mana": 50,
                    "energy": 100,
                    "stamina": 100,
                    "max_hp": 100,
                    "max_mana": 50,
                    "max_energy": 100,
                    "max_stamina": 100,
                    "cooldowns": {},
                    "fast_slots": [],
                },
            },
        }

        mock_db = AsyncMock()

        client = _get_client_with_mocks(user, mock_db)
        response = client.post(
            "/battles/1/action",
            json={"participant_id": 1, "action_type": "attack", "target_id": 2},
        )

        assert response.status_code == 400
        assert "приостановлен" in response.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════
# Tests: GET /battles/{id}/join-requests — List join requests
# ═══════════════════════════════════════════════════════════════════════════


class TestListJoinRequests:
    """Tests for GET /battles/{battle_id}/join-requests."""

    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_list_join_requests_returns_items(self):
        """List join requests for a battle with character info."""
        user = _make_user(user_id=10)
        mock_db = AsyncMock()

        now = datetime(2026, 3, 23, 12, 0, 0)
        rows = [
            _row(1, 10, "Воин", 5, "avatar.png", 0, "pending", now),
            _row(2, 20, "Маг", 3, None, 1, "approved", now),
        ]
        mock_db.execute = AsyncMock(return_value=_result_with_rows(rows))

        client = _get_client_with_mocks(user, mock_db)
        response = client.get("/battles/1/join-requests")

        assert response.status_code == 200
        data = response.json()
        assert len(data["requests"]) == 2
        assert data["requests"][0]["character_name"] == "Воин"
        assert data["requests"][1]["team"] == 1

    def test_list_join_requests_empty(self):
        """No join requests for a battle."""
        user = _make_user(user_id=10)
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_result_with_rows([]))

        client = _get_client_with_mocks(user, mock_db)
        response = client.get("/battles/1/join-requests")

        assert response.status_code == 200
        assert response.json()["requests"] == []


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Admin endpoints — GET, approve, reject
# ═══════════════════════════════════════════════════════════════════════════


class TestAdminJoinRequests:
    """Tests for admin join request endpoints."""

    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _setup_admin_client(self, mock_db, admin=True):
        """Create a client with admin or regular user overrides."""
        if admin:
            user = _make_admin()
        else:
            user = _make_user(user_id=2, username="player", role="user")

        def override_auth():
            return user

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_current_user_via_http] = override_auth
        app.dependency_overrides[get_db] = override_get_db

        # Override the require_permission dependency for admin endpoints
        perm_checker = require_permission("battles:manage")
        if admin:
            app.dependency_overrides[perm_checker] = override_auth
        else:
            # For non-admin, let the default check run (will fail with 403)
            pass

        return TestClient(app)

    def test_admin_list_pending_requests(self):
        """GET /battles/admin/join-requests returns pending requests for admin."""
        mock_db = AsyncMock()

        now = datetime(2026, 3, 23, 12, 0, 0)
        # Count query
        count_result = _result_scalar(2)
        # Data rows: id, battle_id, character_id, character_name, character_level,
        #            team, status, created_at, battle_type, participants_count
        data_rows = [
            _row(1, 10, 100, "Воин", 5, 0, "pending", now, "pve", 2),
            _row(2, 10, 200, "Маг", 3, 1, "pending", now, "pve", 2),
        ]
        data_result = _result_with_rows(data_rows)

        call_count = [0]
        async def execute_side_effect(query, params=None):
            call_count[0] += 1
            query_str = str(query)
            if "COUNT" in query_str:
                return count_result
            return data_result

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        client = self._setup_admin_client(mock_db, admin=True)
        response = client.get("/battles/admin/join-requests?status=pending")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["requests"]) == 2
        assert data["requests"][0]["character_name"] == "Воин"
        assert data["requests"][1]["team"] == 1

    @patch("auth_http.requests.get")
    def test_non_admin_gets_403_on_list(self, mock_auth_get):
        """Non-admin user gets 403 on admin join-requests list."""
        mock_auth_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "id": 2, "username": "player", "role": "user", "permissions": [],
            }),
        )
        mock_db = AsyncMock()

        # Do NOT override require_permission so it checks actual permissions
        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        # Don't override auth — let it call the real function which we mock via requests.get

        client = TestClient(app)
        response = client.get(
            "/battles/admin/join-requests",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 403

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.build_participant_info", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.save_state", new_callable=AsyncMock)
    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.get_cached_snapshot", new_callable=AsyncMock)
    @patch("main.resume_battle_if_ready", new_callable=AsyncMock)
    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_approve_join_request(
        self, mock_publish, mock_resume, mock_get_snapshot,
        mock_get_redis, mock_save_state, mock_load_state,
        mock_build_info, mock_get_battle,
    ):
        """POST /admin/join-requests/{id}/approve -> participant added."""
        mock_db = AsyncMock()

        # 1. Load request: id=1, battle_id=10, character_id=100, user_id=50, team=0, status=pending
        req_row = _row(1, 10, 100, 50, 0, "pending")
        # 2. Update request (no return needed)
        # 3. BattleParticipant add
        battle = _make_battle(battle_id=10, status="in_progress")
        mock_get_battle.return_value = battle

        call_count = [0]
        async def execute_side_effect(query, params=None):
            call_count[0] += 1
            query_str = str(query)
            if "battle_join_requests" in query_str and "SELECT" in query_str.upper() and "UPDATE" not in query_str.upper():
                return _result_with_row(req_row)
            if "UPDATE" in query_str.upper() and "battle_join_requests" in query_str:
                return _result_empty()
            if "is_npc" in query_str:
                return _result_with_row(_row(0))  # Not NPC
            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        added_objects = []
        def mock_add(obj):
            obj.id = 500
            added_objects.append(obj)
        mock_db.add = mock_add

        mock_build_info.return_value = {
            "participant_id": 500,
            "character_id": 100,
            "name": "Воин",
            "avatar": "",
            "attributes": {
                "current_health": 100, "current_mana": 50,
                "current_energy": 100, "current_stamina": 100,
                "max_health": 100, "max_mana": 50,
                "max_energy": 100, "max_stamina": 100,
            },
            "skills": [],
            "fast_slots": [],
        }

        mock_load_state.return_value = {
            "turn_number": 1,
            "deadline_at": "2026-03-23T14:00:00",
            "next_actor": 1,
            "first_actor": 1,
            "turn_order": [1, 2],
            "participants": {
                "1": {"character_id": 10, "team": 0, "hp": 100},
                "2": {"character_id": 20, "team": 1, "hp": 80},
            },
        }
        mock_get_redis.return_value = AsyncMock()
        mock_get_snapshot.return_value = None
        mock_resume.return_value = True

        client = self._setup_admin_client(mock_db, admin=True)
        response = client.post("/battles/admin/join-requests/1/approve")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["request_id"] == 1
        assert "одобрена" in data["message"]

        # Verify build_participant_info was called
        mock_build_info.assert_called_once_with(100, 500)

        # Verify resume was checked
        mock_resume.assert_called_once_with(mock_db, 10)

    @patch("main.resume_battle_if_ready", new_callable=AsyncMock)
    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_reject_join_request(self, mock_publish, mock_resume):
        """POST /admin/join-requests/{id}/reject -> request rejected."""
        mock_db = AsyncMock()

        # Load request: id=1, battle_id=10, user_id=50, status=pending
        req_row = _row(1, 10, 50, "pending")

        call_count = [0]
        async def execute_side_effect(query, params=None):
            call_count[0] += 1
            query_str = str(query)
            if "battle_join_requests" in query_str and "SELECT" in query_str.upper() and "UPDATE" not in query_str.upper():
                return _result_with_row(req_row)
            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db.commit = AsyncMock()

        mock_resume.return_value = True

        client = self._setup_admin_client(mock_db, admin=True)
        response = client.post("/battles/admin/join-requests/1/reject")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["request_id"] == 1
        assert "отклонена" in data["message"]

        # Verify notification sent to requester
        mock_publish.assert_called()

        # Verify resume was checked
        mock_resume.assert_called_once_with(mock_db, 10)

    def test_approve_request_not_found(self):
        """Approve non-existent request -> 404."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_result_empty())

        client = self._setup_admin_client(mock_db, admin=True)
        response = client.post("/battles/admin/join-requests/999/approve")

        assert response.status_code == 404
        assert "не найдена" in response.json()["detail"]

    def test_reject_request_not_found(self):
        """Reject non-existent request -> 404."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_result_empty())

        client = self._setup_admin_client(mock_db, admin=True)
        response = client.post("/battles/admin/join-requests/999/reject")

        assert response.status_code == 404
        assert "не найдена" in response.json()["detail"]

    def test_approve_already_processed_request(self):
        """Approve already-processed request -> 400."""
        mock_db = AsyncMock()

        # Request with status "approved"
        req_row = _row(1, 10, 100, 50, 0, "approved")
        mock_db.execute = AsyncMock(return_value=_result_with_row(req_row))

        client = self._setup_admin_client(mock_db, admin=True)
        response = client.post("/battles/admin/join-requests/1/approve")

        assert response.status_code == 400
        assert "уже рассмотрена" in response.json()["detail"]

    def test_reject_already_processed_request(self):
        """Reject already-processed request -> 400."""
        mock_db = AsyncMock()

        # Request with status "rejected"
        req_row = _row(1, 10, 50, "rejected")
        mock_db.execute = AsyncMock(return_value=_result_with_row(req_row))

        client = self._setup_admin_client(mock_db, admin=True)
        response = client.post("/battles/admin/join-requests/1/reject")

        assert response.status_code == 400
        assert "уже рассмотрена" in response.json()["detail"]

    @patch("auth_http.requests.get")
    def test_non_admin_gets_403_on_approve(self, mock_auth_get):
        """Non-admin user gets 403 on approve endpoint."""
        mock_auth_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "id": 2, "username": "player", "role": "user", "permissions": [],
            }),
        )
        mock_db = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        client = TestClient(app)
        response = client.post(
            "/battles/admin/join-requests/1/approve",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_non_admin_gets_403_on_reject(self, mock_auth_get):
        """Non-admin user gets 403 on reject endpoint."""
        mock_auth_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "id": 2, "username": "player", "role": "user", "permissions": [],
            }),
        )
        mock_db = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        client = TestClient(app)
        response = client.post(
            "/battles/admin/join-requests/1/reject",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Auto-reject pending requests when battle finishes
# ═══════════════════════════════════════════════════════════════════════════


class TestAutoRejectOnBattleFinish:
    """Tests for auto-rejecting pending join requests when a battle finishes."""

    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main._auto_reject_pending_join_requests", new_callable=AsyncMock)
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.save_state", new_callable=AsyncMock)
    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_auto_reject_called_on_force_finish(
        self, mock_publish, mock_redis, mock_save_state,
        mock_load_state, mock_get_battle, mock_auto_reject,
    ):
        """When admin force-finishes a battle, pending join requests are auto-rejected."""
        admin = _make_admin()
        battle = _make_battle(battle_id=1, status="in_progress")
        mock_get_battle.return_value = battle

        mock_load_state.return_value = {
            "turn_number": 1,
            "deadline_at": "2026-03-23T14:00:00",
            "next_actor": 1,
            "first_actor": 1,
            "turn_order": [1, 2],
            "total_turns": 1,
            "last_turn": None,
            "participants": {
                "1": {
                    "character_id": 10, "team": 0,
                    "hp": 100, "mana": 50, "energy": 100, "stamina": 100,
                    "max_hp": 100, "max_mana": 50, "max_energy": 100, "max_stamina": 100,
                    "cooldowns": {}, "fast_slots": [],
                },
                "2": {
                    "character_id": 20, "team": 1,
                    "hp": 80, "mana": 40, "energy": 90, "stamina": 80,
                    "max_hp": 100, "max_mana": 50, "max_energy": 100, "max_stamina": 100,
                    "cooldowns": {}, "fast_slots": [],
                },
            },
        }

        mock_redis.return_value = AsyncMock()

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_result_empty())
        mock_db.commit = AsyncMock()

        def override_auth():
            return admin

        async def override_get_db():
            yield mock_db

        perm_dep = require_permission("battles:manage")
        app.dependency_overrides[get_current_user_via_http] = override_auth
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[perm_dep] = override_auth

        client = TestClient(app)
        response = client.post("/battles/admin/1/force-finish")

        # The endpoint may return various codes depending on internal state handling,
        # but _auto_reject should have been called
        mock_auto_reject.assert_called_once_with(mock_db, 1)
