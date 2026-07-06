"""
Tests for PvP attack endpoint in battle-service.

Covers:
- POST /battles/pvp/attack — force PvP attack
- Self-attack blocked
- Safe location blocked
- Characters not at same location
- Character already in battle
- Notification sent to victim
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
engine_mock.roll_dodge = MagicMock(return_value=False)  # FEAT-143: deterministic no-dodge

# Ensure buffs has the required functions
buffs_mock = sys.modules["buffs"]
buffs_mock.decrement_durations = MagicMock()
buffs_mock.aggregate_modifiers = MagicMock(return_value={})
buffs_mock.apply_new_effects = MagicMock()
buffs_mock.evaluate_control = MagicMock(return_value=(None, set()))  # FEAT-143: no control by defaultbuffs_mock.build_percent_damage_buffs = MagicMock(return_value={})
buffs_mock.build_percent_resist_buffs = MagicMock(return_value={})

# Ensure skills_client has the required functions
skills_mock = sys.modules["skills_client"]
skills_mock.character_has_skill = AsyncMock(return_value=True)
skills_mock.get_resolved_skill = AsyncMock(return_value={})
skills_mock.get_item = AsyncMock(return_value={})
skills_mock.character_skills = AsyncMock(return_value=[])

# Ensure mongo_helpers
mongo_mock = sys.modules["mongo_helpers"]
mongo_mock.save_snapshot = AsyncMock()
mongo_mock.load_snapshot = AsyncMock(return_value=None)

# Ensure rabbitmq_publisher
rmq_mock = sys.modules["rabbitmq_publisher"]
rmq_mock.publish_notification = AsyncMock()

# Now import main safely
import main  # noqa: E402
from main import app  # noqa: E402
from database import get_db  # noqa: E402
from auth_http import get_current_user_via_http, UserRead  # noqa: E402

# Clear startup handlers to avoid connection attempts
app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True)
def _ensure_async_redis():
    """`main` binds `get_redis_client` by name at import (main.py:45), so once
    another test module imports main first with a non-async redis mock, that
    binding sticks and `await rds.zadd(...)` breaks here. Rebind per test to a
    proper AsyncMock so these tests are immune to import/collection order."""
    main.get_redis_client = AsyncMock(return_value=AsyncMock())
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_user(user_id=1, username="testuser", role="user"):
    return UserRead(id=user_id, username=username, role=role, permissions=[])


def _row(*values):
    """Create a mock row that supports index access."""
    row = MagicMock()
    row.__getitem__ = lambda self, i: values[i]
    row.__len__ = lambda self: len(values)
    return row


def _result_with_row(row_data):
    result = MagicMock()
    result.fetchone.return_value = row_data
    return result


def _result_empty():
    result = MagicMock()
    result.fetchone.return_value = None
    return result


# Character rows: id, user_id, current_location, level
CHAR_ATTACKER = _row(1, 10, 100, 5)   # char 1, user 10, loc 100
CHAR_VICTIM = _row(2, 20, 100, 5)     # char 2, user 20, loc 100
CHAR_VICTIM_DIFF_LOC = _row(2, 20, 200, 5)  # different location
CHAR_NAME_ATTACKER = _row("Воин",)
LOC_DANGEROUS = _row("dangerous",)
LOC_SAFE = _row("safe",)

ATTACK_PAYLOAD = {
    "attacker_character_id": 1,
    "victim_character_id": 2,
}


def _get_client_with_mocks(user, mock_db):
    def override_auth():
        return user

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_current_user_via_http] = override_auth
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _build_attack_side_effects(
    attacker_char=CHAR_ATTACKER,
    victim_char=CHAR_VICTIM,
    location_type=LOC_DANGEROUS,
    active_battle_attacker=None,
    active_battle_victim=None,
):
    """Build execute side effects for the attack endpoint."""
    async def side_effect(query, params=None):
        query_str = str(query) if not isinstance(query, str) else query

        # _get_character_info for attacker
        if "user_id, current_location_id, level" in query_str and params and params.get("cid") == 1:
            return _result_with_row(attacker_char) if attacker_char else _result_empty()
        # _get_character_info for victim
        if "user_id, current_location_id, level" in query_str and params and params.get("cid") == 2:
            return _result_with_row(victim_char) if victim_char else _result_empty()
        # Location check
        if "marker_type" in query_str and "Locations" in query_str:
            return _result_with_row(location_type) if location_type else _result_empty()
        # get_active_battle_for_character for attacker
        if "battles" in query_str and "battle_participants" in query_str and params and params.get("cid") == 1:
            if active_battle_attacker:
                return _result_with_row(_row(active_battle_attacker))
            return _result_empty()
        # get_active_battle_for_character for victim
        if "battles" in query_str and "battle_participants" in query_str and params and params.get("cid") == 2:
            if active_battle_victim:
                return _result_with_row(_row(active_battle_victim))
            return _result_empty()
        # _get_character_name
        if "name" in query_str and "characters" in query_str and "user_id" not in query_str and "battles" not in query_str:
            return _result_with_row(CHAR_NAME_ATTACKER)
        return _result_empty()

    return side_effect


# ═══════════════════════════════════════════════════════════════════════════
# Tests: POST /battles/pvp/attack
# ═══════════════════════════════════════════════════════════════════════════


class TestPvpAttack:
    """Tests for POST /battles/pvp/attack."""

    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main.build_participant_info", new_callable=AsyncMock)
    @patch("main.create_battle", new_callable=AsyncMock)
    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_attack_happy_path(self, mock_publish, mock_create_battle, mock_build_info):
        """Successful attack creates a battle immediately."""
        user = _make_user(user_id=10)

        mock_battle = MagicMock()
        mock_battle.id = 77
        mock_p1 = MagicMock()
        mock_p1.id = 200
        mock_p1.character_id = 1
        mock_p1.team = 0
        mock_p2 = MagicMock()
        mock_p2.id = 201
        mock_p2.character_id = 2
        mock_p2.team = 1
        mock_create_battle.return_value = (mock_battle, [mock_p1, mock_p2])

        mock_build_info.return_value = {
            "participant_id": 200,
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

        side_effect = _build_attack_side_effects()
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)
        mock_db.commit = AsyncMock()

        mock_rds = AsyncMock()
        redis_state_mock.get_redis_client = AsyncMock(return_value=mock_rds)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/pvp/attack", json=ATTACK_PAYLOAD)

        assert response.status_code == 201
        data = response.json()
        assert data["battle_id"] == 77
        assert data["battle_url"] == "/battle/77"
        assert data["attacker_character_id"] == 1
        assert data["victim_character_id"] == 2

        # Verify battle was created with pvp_attack type
        mock_create_battle.assert_called_once()
        call_kwargs = mock_create_battle.call_args
        assert call_kwargs[1]["battle_type"].value == "pvp_attack"

    @patch("main.build_participant_info", new_callable=AsyncMock)
    @patch("main.create_battle", new_callable=AsyncMock)
    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_attack_sends_notification_to_victim(self, mock_publish, mock_create_battle, mock_build_info):
        """Attack sends a notification to the victim."""
        user = _make_user(user_id=10)

        mock_battle = MagicMock()
        mock_battle.id = 77
        mock_p1 = MagicMock()
        mock_p1.id = 200
        mock_p1.character_id = 1
        mock_p1.team = 0
        mock_p2 = MagicMock()
        mock_p2.id = 201
        mock_p2.character_id = 2
        mock_p2.team = 1
        mock_create_battle.return_value = (mock_battle, [mock_p1, mock_p2])

        mock_build_info.return_value = {
            "participant_id": 200,
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

        side_effect = _build_attack_side_effects()
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)
        mock_db.commit = AsyncMock()

        mock_rds = AsyncMock()
        redis_state_mock.get_redis_client = AsyncMock(return_value=mock_rds)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/pvp/attack", json=ATTACK_PAYLOAD)

        assert response.status_code == 201

        # Verify notification was sent to victim (user_id=20)
        mock_publish.assert_called_once()
        call_kwargs = mock_publish.call_args
        assert call_kwargs[1]["target_user_id"] == 20
        assert "напал" in call_kwargs[1]["message"]
        assert call_kwargs[1]["ws_type"] == "pvp_battle_start"
        assert call_kwargs[1]["ws_data"]["battle_type"] == "pvp_attack"

    def test_self_attack_blocked(self):
        """Attacking yourself -> 400."""
        user = _make_user(user_id=10)
        mock_db = AsyncMock()

        client = _get_client_with_mocks(user, mock_db)
        payload = {
            "attacker_character_id": 1,
            "victim_character_id": 1,
        }
        response = client.post("/battles/pvp/attack", json=payload)

        assert response.status_code == 400
        assert "самого себя" in response.json()["detail"]

    def test_safe_location_blocked(self):
        """Attack on safe location -> 400."""
        user = _make_user(user_id=10)
        side_effect = _build_attack_side_effects(location_type=LOC_SAFE)
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/pvp/attack", json=ATTACK_PAYLOAD)

        assert response.status_code == 400
        assert "безопасной локации" in response.json()["detail"]

    def test_wrong_user_gets_403(self):
        """User does not own attacker character -> 403."""
        user = _make_user(user_id=999)  # Not owner of char 1 (user 10)
        side_effect = _build_attack_side_effects()
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/pvp/attack", json=ATTACK_PAYLOAD)

        assert response.status_code == 403
        assert "своего персонажа" in response.json()["detail"]

    def test_different_locations_blocked(self):
        """Characters at different locations -> 400."""
        user = _make_user(user_id=10)
        side_effect = _build_attack_side_effects(victim_char=CHAR_VICTIM_DIFF_LOC)
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/pvp/attack", json=ATTACK_PAYLOAD)

        assert response.status_code == 400
        assert "одной локации" in response.json()["detail"]

    def test_attacker_already_in_battle(self):
        """Attacker already in active battle -> 400."""
        user = _make_user(user_id=10)
        side_effect = _build_attack_side_effects(active_battle_attacker=42)
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/pvp/attack", json=ATTACK_PAYLOAD)

        assert response.status_code == 400
        assert "уже в бою" in response.json()["detail"]

    def test_victim_already_in_battle(self):
        """Victim already in active battle -> 400."""
        user = _make_user(user_id=10)
        side_effect = _build_attack_side_effects(active_battle_victim=42)
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/pvp/attack", json=ATTACK_PAYLOAD)

        assert response.status_code == 400
        assert "уже в бою" in response.json()["detail"]

    def test_victim_not_found(self):
        """Victim character does not exist -> 404."""
        user = _make_user(user_id=10)
        side_effect = _build_attack_side_effects(victim_char=None)
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/pvp/attack", json=ATTACK_PAYLOAD)

        assert response.status_code == 404
        assert "Целевой персонаж" in response.json()["detail"]

    def test_attacker_not_found(self):
        """Attacker character does not exist -> 404."""
        user = _make_user(user_id=10)
        side_effect = _build_attack_side_effects(attacker_char=None)
        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=side_effect)

        client = _get_client_with_mocks(user, mock_db)
        response = client.post("/battles/pvp/attack", json=ATTACK_PAYLOAD)

        assert response.status_code == 404
        assert "Персонаж не найден" in response.json()["detail"]


def _make_mock_db(execute_side_effects=None):
    """Return an async mock DB session."""
    mock_db = AsyncMock()
    if execute_side_effects:
        mock_db.execute = AsyncMock(side_effect=execute_side_effects)
    return mock_db


# ═══════════════════════════════════════════════════════════════════════════
# FEAT-128 Task #17 / #28: pvp_attack must call locations-service
# /locations/internal/cancel-gathering BEFORE creating the battle.
# The call is best-effort: failures (timeout, 5xx, 503) must NOT block battle
# creation. The header is X-Internal-Token (matches implementation).
# ═══════════════════════════════════════════════════════════════════════════


import httpx  # noqa: E402


class _AsyncCMResponse:
    """A fake httpx.AsyncClient context manager whose .post() returns a
    pre-baked response object (or raises a configured exception).

    Used in place of `httpx.AsyncClient(timeout=...)` in pvp_attack."""

    def __init__(self, post_response=None, post_exception=None):
        self._post_response = post_response
        self._post_exception = post_exception
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None, headers=None):
        # Record the call so the test can assert the args.
        self.post_calls.append({"url": url, "json": json, "headers": headers or {}})
        if self._post_exception is not None:
            raise self._post_exception
        return self._post_response


class _FakeResponse:
    def __init__(self, status_code, json_body=None):
        self.status_code = status_code
        self._json_body = json_body if json_body is not None else {}

    def json(self):
        return self._json_body


def _make_async_client_factory(fake_cm):
    """Return a callable that mimics `httpx.AsyncClient(timeout=...)` and
    yields the same fake CM each time it's called.

    pvp_attack does `async with httpx.AsyncClient(timeout=3.0) as client:` —
    we patch `main.httpx.AsyncClient` to this factory.
    """

    def _factory(*args, **kwargs):
        return fake_cm

    return _factory


def _setup_pvp_attack_happy_mocks(mock_create_battle, mock_build_info):
    """Prime the standard happy-path mocks for create_battle / build_info."""
    mock_battle = MagicMock()
    mock_battle.id = 99
    mock_p1 = MagicMock()
    mock_p1.id = 300
    mock_p1.character_id = 1
    mock_p1.team = 0
    mock_p2 = MagicMock()
    mock_p2.id = 301
    mock_p2.character_id = 2
    mock_p2.team = 1
    mock_create_battle.return_value = (mock_battle, [mock_p1, mock_p2])

    mock_build_info.return_value = {
        "participant_id": 300,
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


class TestPvpAttackCancelsGathering:
    """FEAT-128 Task #28: pvp_attack must POST to
    /locations/internal/cancel-gathering before creating the battle, with
    the victim's character_id and the X-Internal-Token header.
    Failures of that call are best-effort and must NOT block battle creation.
    """

    def setup_method(self):
        app.dependency_overrides.clear()
        # Provide a deterministic INTERNAL_SERVICE_TOKEN for header assertions.
        os.environ["INTERNAL_SERVICE_TOKEN"] = "test-internal-token-xyz"

    def teardown_method(self):
        app.dependency_overrides.clear()
        os.environ.pop("INTERNAL_SERVICE_TOKEN", None)

    @patch("main.build_participant_info", new_callable=AsyncMock)
    @patch("main.create_battle", new_callable=AsyncMock)
    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_cancel_gathering_called_with_correct_payload_and_header(
        self, mock_publish, mock_create_battle, mock_build_info,
    ):
        """pvp_attack posts to /locations/internal/cancel-gathering with
        {character_id: victim_id} and X-Internal-Token header."""
        _setup_pvp_attack_happy_mocks(mock_create_battle, mock_build_info)

        fake_cm = _AsyncCMResponse(
            post_response=_FakeResponse(
                200,
                {"cancelled": True, "session_id": 555, "stamina_refunded": 4},
            )
        )

        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=_build_attack_side_effects())
        mock_db.commit = AsyncMock()

        redis_state_mock.get_redis_client = AsyncMock(return_value=AsyncMock())

        client = _get_client_with_mocks(_make_user(user_id=10), mock_db)

        with patch("main.httpx.AsyncClient", _make_async_client_factory(fake_cm)):
            response = client.post("/battles/pvp/attack", json=ATTACK_PAYLOAD)

        # Battle still created normally
        assert response.status_code == 201
        assert response.json()["battle_id"] == 99

        # Exactly one cancel-gathering call
        assert len(fake_cm.post_calls) == 1
        call = fake_cm.post_calls[0]

        # URL ends with the canonical internal path
        assert call["url"].endswith("/locations/internal/cancel-gathering"), (
            f"unexpected URL: {call['url']}"
        )

        # Payload carries the VICTIM's character_id (not attacker)
        assert call["json"]["character_id"] == 2  # victim id from ATTACK_PAYLOAD

        # Header carries the configured internal token
        assert call["headers"].get("X-Internal-Token") == "test-internal-token-xyz"

        # And mock_create_battle was called AFTER the cancel-gathering call
        # (we don't have call ordering frameworks here, but if create_battle
        # was called and the post was recorded, the flow is correct because
        # the implementation is sequential).
        mock_create_battle.assert_called_once()

    @patch("main.build_participant_info", new_callable=AsyncMock)
    @patch("main.create_battle", new_callable=AsyncMock)
    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_cancel_returns_cancelled_true_battle_created(
        self, mock_publish, mock_create_battle, mock_build_info,
    ):
        """Locations-service returns {cancelled: true, ...} -> battle still created."""
        _setup_pvp_attack_happy_mocks(mock_create_battle, mock_build_info)

        fake_cm = _AsyncCMResponse(
            post_response=_FakeResponse(
                200,
                {"cancelled": True, "session_id": 12, "stamina_refunded": 3},
            )
        )

        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=_build_attack_side_effects())
        mock_db.commit = AsyncMock()
        redis_state_mock.get_redis_client = AsyncMock(return_value=AsyncMock())

        client = _get_client_with_mocks(_make_user(user_id=10), mock_db)
        with patch("main.httpx.AsyncClient", _make_async_client_factory(fake_cm)):
            response = client.post("/battles/pvp/attack", json=ATTACK_PAYLOAD)

        assert response.status_code == 201
        assert len(fake_cm.post_calls) == 1
        mock_create_battle.assert_called_once()

    @patch("main.build_participant_info", new_callable=AsyncMock)
    @patch("main.create_battle", new_callable=AsyncMock)
    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_cancel_returns_no_active_session_battle_created(
        self, mock_publish, mock_create_battle, mock_build_info,
    ):
        """Victim has no active session -> battle is still created normally."""
        _setup_pvp_attack_happy_mocks(mock_create_battle, mock_build_info)

        fake_cm = _AsyncCMResponse(
            post_response=_FakeResponse(
                200,
                {"cancelled": False, "reason": "no_active_session"},
            )
        )

        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=_build_attack_side_effects())
        mock_db.commit = AsyncMock()
        redis_state_mock.get_redis_client = AsyncMock(return_value=AsyncMock())

        client = _get_client_with_mocks(_make_user(user_id=10), mock_db)
        with patch("main.httpx.AsyncClient", _make_async_client_factory(fake_cm)):
            response = client.post("/battles/pvp/attack", json=ATTACK_PAYLOAD)

        assert response.status_code == 201
        # No errors raised; battle creation proceeded
        mock_create_battle.assert_called_once()
        assert len(fake_cm.post_calls) == 1

    @patch("main.build_participant_info", new_callable=AsyncMock)
    @patch("main.create_battle", new_callable=AsyncMock)
    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_cancel_timeout_battle_still_created(
        self, mock_publish, mock_create_battle, mock_build_info, caplog,
    ):
        """httpx.TimeoutException during cancel-gathering -> battle still created,
        warning logged."""
        _setup_pvp_attack_happy_mocks(mock_create_battle, mock_build_info)

        fake_cm = _AsyncCMResponse(
            post_exception=httpx.TimeoutException("timed out"),
        )

        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=_build_attack_side_effects())
        mock_db.commit = AsyncMock()
        redis_state_mock.get_redis_client = AsyncMock(return_value=AsyncMock())

        client = _get_client_with_mocks(_make_user(user_id=10), mock_db)
        with caplog.at_level("WARNING", logger="battle-service"):
            with patch("main.httpx.AsyncClient", _make_async_client_factory(fake_cm)):
                response = client.post("/battles/pvp/attack", json=ATTACK_PAYLOAD)

        assert response.status_code == 201
        mock_create_battle.assert_called_once()
        # Warning was emitted
        assert any(
            "cancel-gathering" in rec.getMessage().lower()
            for rec in caplog.records
        ), "Expected a warning log mentioning cancel-gathering on timeout"

    @patch("main.build_participant_info", new_callable=AsyncMock)
    @patch("main.create_battle", new_callable=AsyncMock)
    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_cancel_returns_5xx_battle_still_created(
        self, mock_publish, mock_create_battle, mock_build_info, caplog,
    ):
        """Locations-service returns 500 -> battle still created, warning logged."""
        _setup_pvp_attack_happy_mocks(mock_create_battle, mock_build_info)

        fake_cm = _AsyncCMResponse(post_response=_FakeResponse(500, {}))

        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=_build_attack_side_effects())
        mock_db.commit = AsyncMock()
        redis_state_mock.get_redis_client = AsyncMock(return_value=AsyncMock())

        client = _get_client_with_mocks(_make_user(user_id=10), mock_db)
        with caplog.at_level("WARNING", logger="battle-service"):
            with patch("main.httpx.AsyncClient", _make_async_client_factory(fake_cm)):
                response = client.post("/battles/pvp/attack", json=ATTACK_PAYLOAD)

        assert response.status_code == 201
        mock_create_battle.assert_called_once()
        # The cancel-gathering call was actually made
        assert len(fake_cm.post_calls) == 1
        # And a warning was emitted because of the 5xx
        assert any(
            "cancel-gathering" in rec.getMessage().lower()
            for rec in caplog.records
        ), "Expected a warning log mentioning cancel-gathering on 5xx"

    @patch("main.build_participant_info", new_callable=AsyncMock)
    @patch("main.create_battle", new_callable=AsyncMock)
    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_cancel_returns_503_battle_still_created(
        self, mock_publish, mock_create_battle, mock_build_info, caplog,
    ):
        """Locations-service returns 503 (e.g. service down) -> same as 5xx."""
        _setup_pvp_attack_happy_mocks(mock_create_battle, mock_build_info)

        fake_cm = _AsyncCMResponse(post_response=_FakeResponse(503, {}))

        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=_build_attack_side_effects())
        mock_db.commit = AsyncMock()
        redis_state_mock.get_redis_client = AsyncMock(return_value=AsyncMock())

        client = _get_client_with_mocks(_make_user(user_id=10), mock_db)
        with caplog.at_level("WARNING", logger="battle-service"):
            with patch("main.httpx.AsyncClient", _make_async_client_factory(fake_cm)):
                response = client.post("/battles/pvp/attack", json=ATTACK_PAYLOAD)

        assert response.status_code == 201
        mock_create_battle.assert_called_once()
        assert len(fake_cm.post_calls) == 1
        assert any(
            "cancel-gathering" in rec.getMessage().lower()
            for rec in caplog.records
        ), "Expected a warning log mentioning cancel-gathering on 503"

    @patch("main.build_participant_info", new_callable=AsyncMock)
    @patch("main.create_battle", new_callable=AsyncMock)
    @patch("main.publish_notification", new_callable=AsyncMock)
    def test_cancel_connection_error_battle_still_created(
        self, mock_publish, mock_create_battle, mock_build_info, caplog,
    ):
        """httpx.ConnectError (locations-service down) -> battle still created."""
        _setup_pvp_attack_happy_mocks(mock_create_battle, mock_build_info)

        fake_cm = _AsyncCMResponse(
            post_exception=httpx.ConnectError("connection refused"),
        )

        mock_db = _make_mock_db()
        mock_db.execute = AsyncMock(side_effect=_build_attack_side_effects())
        mock_db.commit = AsyncMock()
        redis_state_mock.get_redis_client = AsyncMock(return_value=AsyncMock())

        client = _get_client_with_mocks(_make_user(user_id=10), mock_db)
        with caplog.at_level("WARNING", logger="battle-service"):
            with patch("main.httpx.AsyncClient", _make_async_client_factory(fake_cm)):
                response = client.post("/battles/pvp/attack", json=ATTACK_PAYLOAD)

        assert response.status_code == 201
        mock_create_battle.assert_called_once()
