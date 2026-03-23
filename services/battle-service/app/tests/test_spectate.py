"""
Tests for battles-by-location and spectate endpoints (FEAT-069).

Covers:
1.  GET /battles/by-location/{location_id} — returns battles at the given location
2.  GET /battles/by-location/{location_id} — filters out finished battles
3.  GET /battles/by-location/{location_id} — returns empty list when no battles
4.  GET /battles/by-location/{location_id} — requires authentication (401)
5.  GET /battles/{battle_id}/spectate — returns state for user at same location (200)
6.  GET /battles/{battle_id}/spectate — returns 403 for user at different location
7.  GET /battles/{battle_id}/spectate — returns 404 for non-existent battle
8.  GET /battles/{battle_id}/spectate — returns 404 for finished battle
9.  GET /battles/{battle_id}/spectate — response includes is_paused and paused_reason
"""

import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Environment & module-level patches (same approach as test_admin_battles.py)
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

# Now import main safely
from main import app  # noqa: E402
from database import get_db  # noqa: E402

# Clear startup handlers to avoid connection attempts
app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402

NOW = datetime(2026, 3, 23, 12, 0, 0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _make_battle(
    battle_id=1, status="in_progress", battle_type="pve",
    location_id=100, is_paused=False, created_at=None,
):
    """Return a mock Battle ORM object."""
    battle = MagicMock()
    battle.id = battle_id
    battle.status = MagicMock()
    battle.status.value = status
    # Make enum comparison work: BattleStatus.pending / in_progress / finished
    # The endpoint checks `battle_record.status not in (BattleStatus.pending, ...)`
    # With MagicMock equality works by identity, so we need to match the enum values
    battle.status.__eq__ = lambda self, other: (
        self.value == (other.value if hasattr(other, "value") else other)
    )
    battle.status.__ne__ = lambda self, other: not battle.status.__eq__(other)
    battle.status.__hash__ = lambda self: hash(self.value)
    battle.battle_type = MagicMock()
    battle.battle_type.value = battle_type
    battle.location_id = location_id
    battle.is_paused = is_paused
    battle.created_at = created_at or NOW
    return battle


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
            "mana": 40,
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

SAMPLE_SNAPSHOT = [
    {"character_id": 10, "name": "Артас", "level": 5},
    {"character_id": 20, "name": "Моб", "level": 3},
]

AUTH_USER = {"id": 1, "username": "player", "role": "user", "permissions": []}
AUTH_HEADERS = {"Authorization": "Bearer fake-token"}


def _make_by_location_rows(battles_data):
    """Build fetchall() rows for the by-location query.

    battles_data: list of dicts with keys:
        bid, status, battle_type, is_paused, created_at,
        participant_id, character_id, team, character_name, level, is_npc
    """
    rows = []
    for d in battles_data:
        row = (
            d["bid"], d["status"], d["battle_type"],
            d["is_paused"], d.get("created_at", NOW),
            d["participant_id"], d["character_id"],
            d["team"], d["character_name"], d["level"], d["is_npc"],
        )
        rows.append(row)
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# GET /battles/by-location/{location_id}
# ═══════════════════════════════════════════════════════════════════════════


class TestGetBattlesByLocation:
    """Tests for GET /battles/by-location/{location_id}."""

    def test_missing_token_returns_401(self):
        """Endpoint requires authentication."""
        with TestClient(app) as client:
            response = client.get("/battles/by-location/100")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_auth_get):
        mock_auth_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.get(
                "/battles/by-location/100",
                headers=AUTH_HEADERS,
            )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_returns_battles_at_location(self, mock_auth_get):
        """Returns active battles with participants for a given location."""
        mock_auth_get.return_value = _mock_response(200, AUTH_USER)

        rows_data = [
            {
                "bid": 1, "status": "in_progress", "battle_type": "pve",
                "is_paused": False, "participant_id": 10,
                "character_id": 100, "team": 0,
                "character_name": "Артас", "level": 5, "is_npc": False,
            },
            {
                "bid": 1, "status": "in_progress", "battle_type": "pve",
                "is_paused": False, "participant_id": 11,
                "character_id": 200, "team": 1,
                "character_name": "Моб", "level": 3, "is_npc": True,
            },
        ]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = _make_by_location_rows(rows_data)
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/by-location/100",
                    headers=AUTH_HEADERS,
                )
            assert response.status_code == 200
            data = response.json()
            assert "battles" in data
            assert len(data["battles"]) == 1

            battle = data["battles"][0]
            assert battle["id"] == 1
            assert battle["status"] == "in_progress"
            assert battle["battle_type"] == "pve"
            assert battle["is_paused"] is False
            assert len(battle["participants"]) == 2

            p0 = battle["participants"][0]
            assert p0["character_name"] == "Артас"
            assert p0["is_npc"] is False

            p1 = battle["participants"][1]
            assert p1["character_name"] == "Моб"
            assert p1["is_npc"] is True
        finally:
            app.dependency_overrides.pop(get_db, None)

    @patch("auth_http.requests.get")
    def test_filters_out_finished_battles(self, mock_auth_get):
        """Only pending/in_progress battles returned — finished excluded by query."""
        mock_auth_get.return_value = _mock_response(200, AUTH_USER)

        # The SQL query itself filters by status IN ('pending', 'in_progress'),
        # so finished battles never appear in results.
        # We simulate the DB returning no rows (all battles at location are finished).
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/by-location/100",
                    headers=AUTH_HEADERS,
                )
            assert response.status_code == 200
            data = response.json()
            assert data["battles"] == []
        finally:
            app.dependency_overrides.pop(get_db, None)

    @patch("auth_http.requests.get")
    def test_returns_empty_list_when_no_battles(self, mock_auth_get):
        """No battles at location — returns empty list."""
        mock_auth_get.return_value = _mock_response(200, AUTH_USER)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/by-location/999",
                    headers=AUTH_HEADERS,
                )
            assert response.status_code == 200
            data = response.json()
            assert data["battles"] == []
        finally:
            app.dependency_overrides.pop(get_db, None)

    @patch("auth_http.requests.get")
    def test_multiple_battles_grouped_correctly(self, mock_auth_get):
        """Multiple battles at the same location are grouped correctly."""
        mock_auth_get.return_value = _mock_response(200, AUTH_USER)

        rows_data = [
            {
                "bid": 1, "status": "in_progress", "battle_type": "pve",
                "is_paused": False, "participant_id": 10,
                "character_id": 100, "team": 0,
                "character_name": "Герой", "level": 5, "is_npc": False,
            },
            {
                "bid": 1, "status": "in_progress", "battle_type": "pve",
                "is_paused": False, "participant_id": 11,
                "character_id": 200, "team": 1,
                "character_name": "Моб1", "level": 3, "is_npc": True,
            },
            {
                "bid": 2, "status": "pending", "battle_type": "pvp",
                "is_paused": True, "participant_id": 20,
                "character_id": 300, "team": 0,
                "character_name": "Игрок2", "level": 7, "is_npc": False,
            },
        ]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = _make_by_location_rows(rows_data)
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/by-location/100",
                    headers=AUTH_HEADERS,
                )
            assert response.status_code == 200
            data = response.json()
            assert len(data["battles"]) == 2

            # Battle 1 has 2 participants
            battle1 = next(b for b in data["battles"] if b["id"] == 1)
            assert len(battle1["participants"]) == 2
            assert battle1["is_paused"] is False

            # Battle 2 has 1 participant and is paused
            battle2 = next(b for b in data["battles"] if b["id"] == 2)
            assert len(battle2["participants"]) == 1
            assert battle2["is_paused"] is True
        finally:
            app.dependency_overrides.pop(get_db, None)


# ═══════════════════════════════════════════════════════════════════════════
# GET /battles/{battle_id}/spectate
# ═══════════════════════════════════════════════════════════════════════════


class TestSpectateBattle:
    """Tests for GET /battles/{battle_id}/spectate."""

    def test_missing_token_returns_401(self):
        """Endpoint requires authentication."""
        with TestClient(app) as client:
            response = client.get("/battles/1/spectate")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_auth_get):
        mock_auth_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.get(
                "/battles/1/spectate",
                headers=AUTH_HEADERS,
            )
        assert response.status_code == 401

    @patch("main.load_snapshot", new_callable=AsyncMock, return_value=None)
    @patch("main.get_cached_snapshot", new_callable=AsyncMock, return_value=None)
    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_returns_state_for_user_at_same_location(
        self, mock_auth_get, mock_get_battle, mock_load_state,
        mock_get_redis, mock_get_cached_snap, mock_load_snap,
    ):
        """User with character at same location as battle -> 200."""
        mock_auth_get.return_value = _mock_response(200, AUTH_USER)
        mock_get_battle.return_value = _make_battle(
            battle_id=1, status="in_progress", location_id=100,
        )
        mock_load_state.return_value = SAMPLE_REDIS_STATE
        mock_get_redis.return_value = AsyncMock()
        mock_get_cached_snap.return_value = SAMPLE_SNAPSHOT

        # Mock DB: user's character is at location 100
        mock_db = AsyncMock()
        char_result = MagicMock()
        # (id, current_location_id)
        char_result.fetchall.return_value = [(5, 100)]
        mock_db.execute = AsyncMock(return_value=char_result)

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/1/spectate",
                    headers=AUTH_HEADERS,
                )
            assert response.status_code == 200
            data = response.json()
            assert "snapshot" in data
            assert "runtime" in data

            runtime = data["runtime"]
            assert runtime["turn_number"] == 3
            assert "participants" in runtime
            assert "active_effects" in runtime
        finally:
            app.dependency_overrides.pop(get_db, None)

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_returns_403_for_user_at_different_location(
        self, mock_auth_get, mock_get_battle,
    ):
        """User with character NOT at the battle's location -> 403."""
        mock_auth_get.return_value = _mock_response(200, AUTH_USER)
        mock_get_battle.return_value = _make_battle(
            battle_id=1, status="in_progress", location_id=100,
        )

        # Mock DB: user's character is at location 200 (different)
        mock_db = AsyncMock()
        char_result = MagicMock()
        char_result.fetchall.return_value = [(5, 200)]
        mock_db.execute = AsyncMock(return_value=char_result)

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/1/spectate",
                    headers=AUTH_HEADERS,
                )
            assert response.status_code == 403
            assert "локации" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.pop(get_db, None)

    @patch("main.get_battle", new_callable=AsyncMock, return_value=None)
    @patch("auth_http.requests.get")
    def test_returns_404_for_nonexistent_battle(
        self, mock_auth_get, mock_get_battle,
    ):
        """Non-existent battle_id -> 404."""
        mock_auth_get.return_value = _mock_response(200, AUTH_USER)

        mock_db = AsyncMock()

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/9999/spectate",
                    headers=AUTH_HEADERS,
                )
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_db, None)

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_returns_404_for_finished_battle(
        self, mock_auth_get, mock_get_battle,
    ):
        """Finished battle -> 404 (not active)."""
        mock_auth_get.return_value = _mock_response(200, AUTH_USER)
        mock_get_battle.return_value = _make_battle(
            battle_id=1, status="finished", location_id=100,
        )

        mock_db = AsyncMock()

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/1/spectate",
                    headers=AUTH_HEADERS,
                )
            assert response.status_code == 404
            assert "не активен" in response.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_db, None)

    @patch("main.load_snapshot", new_callable=AsyncMock, return_value=None)
    @patch("main.get_cached_snapshot", new_callable=AsyncMock, return_value=None)
    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_response_includes_is_paused_false(
        self, mock_auth_get, mock_get_battle, mock_load_state,
        mock_get_redis, mock_get_cached_snap, mock_load_snap,
    ):
        """When battle is not paused, is_paused=false and paused_reason=null."""
        mock_auth_get.return_value = _mock_response(200, AUTH_USER)
        mock_get_battle.return_value = _make_battle(
            battle_id=1, status="in_progress", location_id=100,
            is_paused=False,
        )
        mock_load_state.return_value = SAMPLE_REDIS_STATE
        mock_get_redis.return_value = AsyncMock()
        mock_get_cached_snap.return_value = SAMPLE_SNAPSHOT

        mock_db = AsyncMock()
        char_result = MagicMock()
        char_result.fetchall.return_value = [(5, 100)]
        mock_db.execute = AsyncMock(return_value=char_result)

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/1/spectate",
                    headers=AUTH_HEADERS,
                )
            assert response.status_code == 200
            runtime = response.json()["runtime"]
            assert runtime["is_paused"] is False
            assert runtime["paused_reason"] is None
        finally:
            app.dependency_overrides.pop(get_db, None)

    @patch("main.load_snapshot", new_callable=AsyncMock, return_value=None)
    @patch("main.get_cached_snapshot", new_callable=AsyncMock, return_value=None)
    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_response_includes_is_paused_true(
        self, mock_auth_get, mock_get_battle, mock_load_state,
        mock_get_redis, mock_get_cached_snap, mock_load_snap,
    ):
        """When battle is paused, is_paused=true and paused_reason is set."""
        mock_auth_get.return_value = _mock_response(200, AUTH_USER)
        mock_get_battle.return_value = _make_battle(
            battle_id=1, status="in_progress", location_id=100,
            is_paused=True,
        )
        mock_load_state.return_value = SAMPLE_REDIS_STATE
        mock_get_redis.return_value = AsyncMock()
        mock_get_cached_snap.return_value = SAMPLE_SNAPSHOT

        mock_db = AsyncMock()
        char_result = MagicMock()
        char_result.fetchall.return_value = [(5, 100)]
        mock_db.execute = AsyncMock(return_value=char_result)

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/1/spectate",
                    headers=AUTH_HEADERS,
                )
            assert response.status_code == 200
            runtime = response.json()["runtime"]
            assert runtime["is_paused"] is True
            assert runtime["paused_reason"] is not None
            assert "заявк" in runtime["paused_reason"].lower()
        finally:
            app.dependency_overrides.pop(get_db, None)

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_returns_403_user_with_no_characters(
        self, mock_auth_get, mock_get_battle,
    ):
        """User with no characters at all -> 403."""
        mock_auth_get.return_value = _mock_response(200, AUTH_USER)
        mock_get_battle.return_value = _make_battle(
            battle_id=1, status="in_progress", location_id=100,
        )

        # No characters for this user
        mock_db = AsyncMock()
        char_result = MagicMock()
        char_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=char_result)

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/battles/1/spectate",
                    headers=AUTH_HEADERS,
                )
            assert response.status_code == 403
        finally:
            app.dependency_overrides.pop(get_db, None)
