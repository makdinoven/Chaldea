"""
Tests for PvP invitation endpoints in battle-service.

Covers:
- POST /battles/pvp/invite — create invitation (happy path, validations)
- POST /battles/pvp/invite/{id}/respond — accept/decline
- DELETE /battles/pvp/invite/{id} — cancel
- Duplicate prevention, wrong user, location checks, in-battle checks
- Self-invitation blocked
- Invitation expiry handling
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

# Ensure redis_state has the required constants/functions
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

# Ensure rabbitmq_publisher
rmq_mock = sys.modules["rabbitmq_publisher"]
rmq_mock.publish_notification = AsyncMock()

# Now import main safely
from main import app  # noqa: E402
from database import get_db  # noqa: E402
from auth_http import get_current_user_via_http, UserRead  # noqa: E402

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


def _make_user(user_id=1, username="testuser", role="user"):
    return UserRead(id=user_id, username=username, role=role, permissions=[])


def _make_mock_db(execute_side_effects=None):
    """Return an async mock DB session with configurable execute side effects."""
    mock_db = AsyncMock()
    if execute_side_effects:
        mock_db.execute = AsyncMock(side_effect=execute_side_effects)
    return mock_db


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


# ---------------------------------------------------------------------------
# Character info mock helper
# ---------------------------------------------------------------------------
# _get_character_info queries:
#   SELECT id, user_id, current_location_id, level FROM characters WHERE id = :cid
# _get_character_name queries:
#   SELECT name FROM characters WHERE id = :cid
# get_active_battle_for_character queries:
#   SELECT b.id FROM battles b JOIN battle_participants bp ...
# Duplicate check:
#   SELECT id FROM pvp_invitations WHERE ...

CHAR_1 = _row(1, 10, 100, 5)  # id=1, user_id=10, location=100, level=5
CHAR_2 = _row(2, 20, 100, 5)  # id=2, user_id=20, location=100, level=5
CHAR_1_DIFF_LOC = _row(1, 10, 200, 5)  # same char, different location
CHAR_NAME_1 = _row("Воин",)
CHAR_NAME_2 = _row("Маг",)


def _build_invite_execute_side_effects(
    initiator_char=CHAR_1,
    target_char=CHAR_2,
    initiator_name=CHAR_NAME_1,
    active_battle_initiator=None,
    active_battle_target=None,
    duplicate_invitation=None,
):
    """Build a list of execute side effects for the invite endpoint."""
    call_count = [0]

    async def side_effect(query, params=None):
        call_count[0] += 1
        query_str = str(query) if not isinstance(query, str) else query

        # _get_character_info for initiator
        if "user_id, current_location_id, level" in query_str and params and params.get("cid") == 1:
            return _result_with_row(initiator_char)
        # _get_character_info for target
        if "user_id, current_location_id, level" in query_str and params and params.get("cid") == 2:
            return _result_with_row(target_char)
        # get_active_battle_for_character for initiator
        if "battles" in query_str and "battle_participants" in query_str and params and params.get("cid") == 1:
            if active_battle_initiator:
                return _result_with_row(_row(active_battle_initiator))
            return _result_empty()
        # get_active_battle_for_character for target
        if "battles" in query_str and "battle_participants" in query_str and params and params.get("cid") == 2:
            if active_battle_target:
                return _result_with_row(_row(active_battle_target))
            return _result_empty()
        # Duplicate invitation check
        if "pvp_invitations" in query_str and "SELECT" in query_str.upper() and "pending" in query_str:
            if duplicate_invitation:
                return _result_with_row(_row(duplicate_invitation))
            return _result_empty()
        # _get_character_name
        if "name" in query_str and "characters" in query_str and "user_id" not in query_str and "battles" not in query_str:
            return _result_with_row(initiator_name)
        # Default
        return _result_empty()

    return side_effect


# Mock PvpInvitation object for db.add + commit + refresh
class MockPvpInvitation:
    def __init__(self, **kwargs):
        self.id = 999
        self.initiator_character_id = kwargs.get("initiator_character_id", 1)
        self.target_character_id = kwargs.get("target_character_id", 2)
        self.battle_type = kwargs.get("battle_type", "pvp_training")
        self.status = MagicMock()
        self.status.value = "pending"
        self.expires_at = kwargs.get("expires_at", datetime.utcnow() + timedelta(hours=3))


INVITE_PAYLOAD = {
    "initiator_character_id": 1,
    "target_character_id": 2,
    "battle_type": "pvp_training",
}


def _get_client_with_mocks(user, mock_db):
    """Create a TestClient with auth and DB overridden."""
    def override_auth():
        return user

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_current_user_via_http] = override_auth
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# Tests: POST /battles/pvp/invite — Create invitation
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateInvitation:
    """Tests for POST /battles/pvp/invite."""

    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("auth_http.requests.get")
    def test_missing_token_returns_401(self, mock_get):
        mock_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.post(
                "/battles/pvp/invite",
                json=INVITE_PAYLOAD,
            )
        assert response.status_code == 401

    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_create_invitation_happy_path(self, mock_publish):
        user = _make_user(user_id=10)
        side_effect = _build_invite_execute_side_effects()
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        # Mock the add/commit/refresh cycle
        added_objects = []
        def mock_add(obj):
            obj.id = 999
            obj.status = MagicMock()
            obj.status.value = "pending"
            obj.expires_at = datetime.utcnow() + timedelta(hours=3)
            added_objects.append(obj)
        mock_db.add = mock_add
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/pvp/invite", json=INVITE_PAYLOAD)

        assert response.status_code == 201
        data = response.json()
        assert data["invitation_id"] == 999
        assert data["status"] == "pending"
        assert data["battle_type"] == "pvp_training"

    def test_self_invitation_blocked(self):
        user = _make_user(user_id=10)
        mock_db = AsyncMock()

        client = _get_client_with_mocks(user, mock_db)
        payload = {
            "initiator_character_id": 1,
            "target_character_id": 1,
            "battle_type": "pvp_training",
        }
        response = client.post("/battles/pvp/invite", json=payload)

        assert response.status_code == 400
        assert "самого себя" in response.json()["detail"]

    def test_invalid_battle_type(self):
        user = _make_user(user_id=10)
        mock_db = AsyncMock()

        client = _get_client_with_mocks(user, mock_db)
        payload = {
            "initiator_character_id": 1,
            "target_character_id": 2,
            "battle_type": "invalid_type",
        }
        response = client.post("/battles/pvp/invite", json=payload)

        assert response.status_code == 400
        assert "Недопустимый тип боя" in response.json()["detail"]

    def test_wrong_user_gets_403(self):
        """User does not own the initiator character -> 403."""
        user = _make_user(user_id=999)  # Not the owner of char 1 (user_id=10)
        side_effect = _build_invite_execute_side_effects()
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/pvp/invite", json=INVITE_PAYLOAD)

        assert response.status_code == 403
        assert "своего персонажа" in response.json()["detail"]

    def test_target_not_found(self):
        """Target character does not exist -> 404."""
        user = _make_user(user_id=10)
        side_effect = _build_invite_execute_side_effects(target_char=None)
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/pvp/invite", json=INVITE_PAYLOAD)

        assert response.status_code == 404
        assert "Целевой персонаж" in response.json()["detail"]

    def test_different_locations_blocked(self):
        """Characters at different locations -> 400."""
        user = _make_user(user_id=10)
        char_2_diff_loc = _row(2, 20, 200, 5)  # location 200 vs char1's 100
        side_effect = _build_invite_execute_side_effects(target_char=char_2_diff_loc)
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/pvp/invite", json=INVITE_PAYLOAD)

        assert response.status_code == 400
        assert "одной локации" in response.json()["detail"]

    def test_initiator_already_in_battle(self):
        """Initiator character is in an active battle -> 400."""
        user = _make_user(user_id=10)
        side_effect = _build_invite_execute_side_effects(active_battle_initiator=42)
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/pvp/invite", json=INVITE_PAYLOAD)

        assert response.status_code == 400
        assert "уже в бою" in response.json()["detail"]

    def test_target_already_in_battle(self):
        """Target character is in an active battle -> 400."""
        user = _make_user(user_id=10)
        side_effect = _build_invite_execute_side_effects(active_battle_target=42)
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/pvp/invite", json=INVITE_PAYLOAD)

        assert response.status_code == 400
        assert "уже в бою" in response.json()["detail"]

    def test_duplicate_invitation_prevention(self):
        """Duplicate pending invitation -> 409."""
        user = _make_user(user_id=10)
        side_effect = _build_invite_execute_side_effects(duplicate_invitation=123)
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/pvp/invite", json=INVITE_PAYLOAD)

        assert response.status_code == 409
        assert "активное приглашение" in response.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════
# Tests: POST /battles/pvp/invite/{id}/respond — Accept/Decline
# ═══════════════════════════════════════════════════════════════════════════


class TestRespondToInvitation:
    """Tests for POST /battles/pvp/invite/{id}/respond."""

    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _make_invitation_row(self, status="pending", expired=False):
        """Build a mock pvp_invitations row.
        Columns: id, initiator_character_id, target_character_id, location_id,
                 battle_type, status, created_at, expires_at
        """
        expires = datetime.utcnow() + (timedelta(hours=-1) if expired else timedelta(hours=3))
        return _row(
            1,                    # id
            1,                    # initiator_character_id
            2,                    # target_character_id
            100,                  # location_id
            "pvp_training",       # battle_type
            status,               # status
            datetime.utcnow(),    # created_at
            expires,              # expires_at
        )

    def _build_respond_side_effects(self, invitation_row, initiator_char=CHAR_1, target_char=CHAR_2):
        """Build execute side effects for the respond endpoint."""
        call_count = [0]

        async def side_effect(query, params=None):
            call_count[0] += 1
            query_str = str(query) if not isinstance(query, str) else query

            # Fetch invitation
            if "pvp_invitations" in query_str and "SELECT" in query_str.upper():
                if "UPDATE" in query_str.upper():
                    return _result_empty()
                return _result_with_row(invitation_row)
            # UPDATE invitation status
            if "UPDATE" in query_str.upper() and "pvp_invitations" in query_str:
                return _result_empty()
            # _get_character_info for target
            if "user_id, current_location_id, level" in query_str and params and params.get("cid") == 2:
                return _result_with_row(target_char)
            # _get_character_info for initiator
            if "user_id, current_location_id, level" in query_str and params and params.get("cid") == 1:
                return _result_with_row(initiator_char)
            # _get_character_name
            if "character_name" in query_str:
                return _result_with_row(CHAR_NAME_1)
            # get_active_battle_for_character
            if "battles" in query_str and "battle_participants" in query_str:
                return _result_empty()
            return _result_empty()

        return side_effect

    def test_decline_invitation(self):
        """Declining an invitation sets status to 'declined'."""
        user = _make_user(user_id=20)  # Target character's owner
        invitation_row = self._make_invitation_row()
        side_effect = self._build_respond_side_effects(invitation_row)
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)
        mock_db.commit = AsyncMock()

        client = _get_client_with_mocks(user, mock_db)
        response = client.post(
            "/battles/pvp/invite/1/respond",
            json={"action": "decline"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "declined"
        assert data["invitation_id"] == 1

    @patch("main.build_participant_info", new_callable=AsyncMock)
    @patch("main.create_battle", new_callable=AsyncMock)
    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_accept_invitation_creates_battle(self, mock_publish, mock_create_battle, mock_build_info):
        """Accepting an invitation creates a battle."""
        user = _make_user(user_id=20)  # Target character's owner

        # Mock create_battle to return battle + participants
        mock_battle = MagicMock()
        mock_battle.id = 42
        mock_p1 = MagicMock()
        mock_p1.id = 100
        mock_p1.character_id = 1
        mock_p1.team = 0
        mock_p2 = MagicMock()
        mock_p2.id = 101
        mock_p2.character_id = 2
        mock_p2.team = 1
        mock_create_battle.return_value = (mock_battle, [mock_p1, mock_p2])

        mock_build_info.return_value = {
            "participant_id": 100,
            "character_id": 1,
            "name": "Test",
            "avatar": "",
            "attributes": {
                "current_health": 100, "current_mana": 50,
                "current_energy": 50, "current_stamina": 50,
                "max_health": 100, "max_mana": 50,
                "max_energy": 50, "max_stamina": 50,
            },
            "skills": [],
            "fast_slots": [],
        }

        invitation_row = self._make_invitation_row()
        side_effect = self._build_respond_side_effects(invitation_row)
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)
        mock_db.commit = AsyncMock()

        # Mock Redis
        mock_rds = AsyncMock()
        redis_state_mock.get_redis_client = AsyncMock(return_value=mock_rds)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post(
            "/battles/pvp/invite/1/respond",
            json={"action": "accept"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["battle_id"] == 42
        assert data["battle_url"] == "/battle/42"

    def test_invitation_not_found(self):
        """Non-existent invitation -> 404."""
        user = _make_user(user_id=20)
        mock_db = _make_mock_db()

        async def side_effect(query, params=None):
            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post(
            "/battles/pvp/invite/999/respond",
            json={"action": "accept"},
        )

        assert response.status_code == 404
        assert "Приглашение не найдено" in response.json()["detail"]

    def test_already_processed_invitation(self):
        """Invitation already accepted/declined -> 400."""
        user = _make_user(user_id=20)
        invitation_row = self._make_invitation_row(status="accepted")
        mock_db = _make_mock_db()

        async def side_effect(query, params=None):
            query_str = str(query)
            if "pvp_invitations" in query_str:
                return _result_with_row(invitation_row)
            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post(
            "/battles/pvp/invite/1/respond",
            json={"action": "accept"},
        )

        assert response.status_code == 400
        assert "уже было обработано" in response.json()["detail"]

    def test_expired_invitation(self):
        """Expired invitation -> 400."""
        user = _make_user(user_id=20)
        invitation_row = self._make_invitation_row(expired=True)
        mock_db = _make_mock_db()

        async def side_effect(query, params=None):
            query_str = str(query)
            if "pvp_invitations" in query_str and "UPDATE" not in query_str.upper():
                return _result_with_row(invitation_row)
            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=side_effect)
        mock_db.commit = AsyncMock()

        client = _get_client_with_mocks(user, mock_db)
        response = client.post(
            "/battles/pvp/invite/1/respond",
            json={"action": "accept"},
        )

        assert response.status_code == 400
        assert "истекло" in response.json()["detail"]

    def test_wrong_user_responds_403(self):
        """User who is not the target -> 403."""
        user = _make_user(user_id=999)  # Not the target character's owner
        invitation_row = self._make_invitation_row()

        async def side_effect(query, params=None):
            query_str = str(query)
            if "pvp_invitations" in query_str and "UPDATE" not in query_str.upper():
                return _result_with_row(invitation_row)
            # _get_character_info for target (char 2 belongs to user 20, not 999)
            if "user_id, current_location_id, level" in query_str and params and params.get("cid") == 2:
                return _result_with_row(CHAR_2)
            return _result_empty()

        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post(
            "/battles/pvp/invite/1/respond",
            json={"action": "accept"},
        )

        assert response.status_code == 403
        assert "другому игроку" in response.json()["detail"]

    def test_invalid_action(self):
        """Invalid action (not accept/decline) -> 400."""
        user = _make_user(user_id=20)
        mock_db = AsyncMock()

        client = _get_client_with_mocks(user, mock_db)
        response = client.post(
            "/battles/pvp/invite/1/respond",
            json={"action": "maybe"},
        )

        assert response.status_code == 400
        assert "accept" in response.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════
# Tests: DELETE /battles/pvp/invite/{id} — Cancel invitation
# ═══════════════════════════════════════════════════════════════════════════


class TestCancelInvitation:
    """Tests for DELETE /battles/pvp/invite/{id}."""

    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_cancel_invitation_happy_path(self):
        """Initiator cancels own pending invitation."""
        user = _make_user(user_id=10)  # Owner of char 1

        async def side_effect(query, params=None):
            query_str = str(query)
            # SELECT invitation
            if "pvp_invitations" in query_str and "SELECT" in query_str.upper() and "UPDATE" not in query_str.upper():
                return _result_with_row(_row(1, 1, "pending"))  # id=1, initiator_char=1, status=pending
            # _get_character_info for initiator char
            if "user_id, current_location_id, level" in query_str:
                return _result_with_row(CHAR_1)
            # UPDATE
            return _result_empty()

        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)
        mock_db.commit = AsyncMock()

        client = _get_client_with_mocks(user, mock_db)
        response = client.delete("/battles/pvp/invite/1")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"
        assert data["invitation_id"] == 1

    def test_cancel_not_found(self):
        """Non-existent invitation -> 404."""
        user = _make_user(user_id=10)

        async def side_effect(query, params=None):
            return _result_empty()

        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.delete("/battles/pvp/invite/999")

        assert response.status_code == 404
        assert "Приглашение не найдено" in response.json()["detail"]

    def test_cancel_already_processed(self):
        """Already processed invitation -> 400."""
        user = _make_user(user_id=10)

        async def side_effect(query, params=None):
            query_str = str(query)
            if "pvp_invitations" in query_str and "SELECT" in query_str.upper():
                return _result_with_row(_row(1, 1, "accepted"))  # already accepted
            return _result_empty()

        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.delete("/battles/pvp/invite/1")

        assert response.status_code == 400
        assert "уже было обработано" in response.json()["detail"]

    def test_cancel_wrong_user_gets_403(self):
        """Non-owner tries to cancel -> 403."""
        user = _make_user(user_id=999)  # Not the owner of char 1

        async def side_effect(query, params=None):
            query_str = str(query)
            if "pvp_invitations" in query_str and "SELECT" in query_str.upper():
                return _result_with_row(_row(1, 1, "pending"))
            if "user_id, current_location_id, level" in query_str:
                return _result_with_row(CHAR_1)  # char 1 belongs to user 10
            return _result_empty()

        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.delete("/battles/pvp/invite/1")

        assert response.status_code == 403
        assert "свои приглашения" in response.json()["detail"]
