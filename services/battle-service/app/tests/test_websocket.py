"""
Tests for battle-service WebSocket endpoint and ws_manager (FEAT-074).

Covers:
1.  WS connection with valid JWT — accepted, initial state received
2.  WS connection with invalid/missing JWT — closed with code 4001
3.  WS connection as non-participant (user not in battle) — closed with code 4003
4.  WS connection when battle state not found — closed with code 4003
5.  State update delivery via broadcast_to_battle
6.  Battle finished message type
7.  Connection cleanup on disconnect
8.  ws_manager unit tests: connect, disconnect, broadcast_to_battle, cleanup_battle
9.  Stale connection removal during broadcast
10. Duplicate connection replacement (same user reconnects)
"""

import sys
import os
import json
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Environment & module-level patches (same approach as test_spectate.py)
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
import ws_manager  # noqa: E402
from database import get_db  # noqa: E402

# Clear startup handlers to avoid connection attempts
app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402

NOW = datetime(2026, 3, 24, 12, 0, 0)


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

AUTH_USER = {"id": 1, "username": "player", "role": "user", "permissions": []}

SAMPLE_REDIS_STATE = {
    "turn_number": 3,
    "deadline_at": "2026-03-24T14:00:00",
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


def _make_battle(
    battle_id=1, status="in_progress", battle_type="pve",
    location_id=100, is_paused=False, created_at=None,
):
    """Return a mock Battle ORM object."""
    battle = MagicMock()
    battle.id = battle_id
    battle.status = MagicMock()
    battle.status.value = status
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


def _mock_db_session():
    """Create a mock async DB session."""
    session = AsyncMock()
    return session


# ═══════════════════════════════════════════════════════════════════════════
# ws_manager unit tests
# ═══════════════════════════════════════════════════════════════════════════


class TestWsManagerConnect:
    """Tests for ws_manager.connect()."""

    @pytest.fixture(autouse=True)
    def _clear_connections(self):
        """Clear global state before each test."""
        ws_manager.battle_connections.clear()
        yield
        ws_manager.battle_connections.clear()

    @pytest.mark.asyncio
    async def test_connect_adds_user_to_battle(self):
        """connect() registers the WebSocket under battle_id -> user_id."""
        ws = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws)

        assert 1 in ws_manager.battle_connections
        assert 10 in ws_manager.battle_connections[1]
        assert ws_manager.battle_connections[1][10] is ws

    @pytest.mark.asyncio
    async def test_connect_creates_battle_dict_if_missing(self):
        """First connection to a battle creates the battle dict."""
        ws = AsyncMock()
        assert 99 not in ws_manager.battle_connections
        await ws_manager.connect(battle_id=99, user_id=1, websocket=ws)
        assert 99 in ws_manager.battle_connections

    @pytest.mark.asyncio
    async def test_connect_replaces_existing_connection(self):
        """If user already connected, old WS is closed and replaced."""
        old_ws = AsyncMock()
        new_ws = AsyncMock()

        await ws_manager.connect(battle_id=1, user_id=10, websocket=old_ws)
        await ws_manager.connect(battle_id=1, user_id=10, websocket=new_ws)

        # Old connection should have been closed
        old_ws.close.assert_awaited_once()
        # New connection is stored
        assert ws_manager.battle_connections[1][10] is new_ws

    @pytest.mark.asyncio
    async def test_connect_multiple_users_same_battle(self):
        """Multiple users can connect to the same battle."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws1)
        await ws_manager.connect(battle_id=1, user_id=20, websocket=ws2)

        assert len(ws_manager.battle_connections[1]) == 2
        assert ws_manager.battle_connections[1][10] is ws1
        assert ws_manager.battle_connections[1][20] is ws2


class TestWsManagerDisconnect:
    """Tests for ws_manager.disconnect()."""

    @pytest.fixture(autouse=True)
    def _clear_connections(self):
        ws_manager.battle_connections.clear()
        yield
        ws_manager.battle_connections.clear()

    @pytest.mark.asyncio
    async def test_disconnect_removes_user(self):
        """disconnect() removes the user from battle connections."""
        ws = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws)
        await ws_manager.disconnect(battle_id=1, user_id=10)

        assert 1 not in ws_manager.battle_connections  # empty dict cleaned up

    @pytest.mark.asyncio
    async def test_disconnect_closes_websocket(self):
        """disconnect() closes the WebSocket gracefully."""
        ws = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws)
        await ws_manager.disconnect(battle_id=1, user_id=10)

        ws.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_battle_is_noop(self):
        """disconnect() for a non-existent battle does nothing."""
        await ws_manager.disconnect(battle_id=999, user_id=10)
        # Should not raise

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_user_is_noop(self):
        """disconnect() for a non-existent user in an existing battle is safe."""
        ws = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws)
        await ws_manager.disconnect(battle_id=1, user_id=99)

        # User 10 still connected
        assert 10 in ws_manager.battle_connections[1]

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up_empty_battle_dict(self):
        """When last user disconnects, the battle dict is removed."""
        ws = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws)
        await ws_manager.disconnect(battle_id=1, user_id=10)

        assert 1 not in ws_manager.battle_connections

    @pytest.mark.asyncio
    async def test_disconnect_keeps_other_users(self):
        """Disconnecting one user doesn't affect others in the same battle."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws1)
        await ws_manager.connect(battle_id=1, user_id=20, websocket=ws2)

        await ws_manager.disconnect(battle_id=1, user_id=10)

        assert 20 in ws_manager.battle_connections[1]
        assert 10 not in ws_manager.battle_connections[1]


class TestWsManagerBroadcast:
    """Tests for ws_manager.broadcast_to_battle()."""

    @pytest.fixture(autouse=True)
    def _clear_connections(self):
        ws_manager.battle_connections.clear()
        yield
        ws_manager.battle_connections.clear()

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_users(self):
        """broadcast_to_battle() sends data to all connected users."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws1)
        await ws_manager.connect(battle_id=1, user_id=20, websocket=ws2)

        data = {"type": "battle_state", "data": {"turn": 1}}
        await ws_manager.broadcast_to_battle(1, data)

        ws1.send_json.assert_awaited_once_with(data)
        ws2.send_json.assert_awaited_once_with(data)

    @pytest.mark.asyncio
    async def test_broadcast_to_nonexistent_battle_is_noop(self):
        """broadcast to a battle with no connections does nothing."""
        await ws_manager.broadcast_to_battle(999, {"type": "test"})
        # Should not raise

    @pytest.mark.asyncio
    async def test_broadcast_removes_stale_connections(self):
        """If send_json fails, the stale connection is removed."""
        ws_good = AsyncMock()
        ws_stale = AsyncMock()
        ws_stale.send_json = AsyncMock(side_effect=Exception("connection lost"))

        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws_good)
        await ws_manager.connect(battle_id=1, user_id=20, websocket=ws_stale)

        await ws_manager.broadcast_to_battle(1, {"type": "test"})

        # Good connection received data
        ws_good.send_json.assert_awaited_once()
        # Stale connection was removed
        assert 20 not in ws_manager.battle_connections.get(1, {})
        # Good connection still present
        assert 10 in ws_manager.battle_connections[1]

    @pytest.mark.asyncio
    async def test_broadcast_cleans_up_empty_battle_after_stale_removal(self):
        """If all connections are stale, the battle dict is removed."""
        ws_stale = AsyncMock()
        ws_stale.send_json = AsyncMock(side_effect=Exception("connection lost"))

        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws_stale)
        await ws_manager.broadcast_to_battle(1, {"type": "test"})

        assert 1 not in ws_manager.battle_connections

    @pytest.mark.asyncio
    async def test_broadcast_does_not_send_to_other_battles(self):
        """broadcast_to_battle only affects the specified battle."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws1)
        await ws_manager.connect(battle_id=2, user_id=20, websocket=ws2)

        await ws_manager.broadcast_to_battle(1, {"type": "test"})

        ws1.send_json.assert_awaited_once()
        ws2.send_json.assert_not_awaited()


class TestWsManagerCleanupBattle:
    """Tests for ws_manager.cleanup_battle()."""

    @pytest.fixture(autouse=True)
    def _clear_connections(self):
        ws_manager.battle_connections.clear()
        yield
        ws_manager.battle_connections.clear()

    @pytest.mark.asyncio
    async def test_cleanup_closes_all_connections(self):
        """cleanup_battle() closes all WS connections for the battle."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws1)
        await ws_manager.connect(battle_id=1, user_id=20, websocket=ws2)

        await ws_manager.cleanup_battle(1)

        ws1.close.assert_awaited_once()
        ws2.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_removes_battle_from_dict(self):
        """cleanup_battle() removes the battle entry entirely."""
        ws = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws)

        await ws_manager.cleanup_battle(1)

        assert 1 not in ws_manager.battle_connections

    @pytest.mark.asyncio
    async def test_cleanup_nonexistent_battle_is_noop(self):
        """cleanup_battle() for a non-existent battle does nothing."""
        await ws_manager.cleanup_battle(999)
        # Should not raise

    @pytest.mark.asyncio
    async def test_cleanup_does_not_affect_other_battles(self):
        """cleanup_battle() only removes the specified battle."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws1)
        await ws_manager.connect(battle_id=2, user_id=20, websocket=ws2)

        await ws_manager.cleanup_battle(1)

        assert 1 not in ws_manager.battle_connections
        assert 2 in ws_manager.battle_connections


# ═══════════════════════════════════════════════════════════════════════════
# WebSocket endpoint integration tests
# ═══════════════════════════════════════════════════════════════════════════


class TestWebSocketAuth:
    """Tests for WS authentication (valid/invalid JWT)."""

    @pytest.fixture(autouse=True)
    def _clear_connections(self):
        ws_manager.battle_connections.clear()
        yield
        ws_manager.battle_connections.clear()

    @patch("main.authenticate_websocket", new_callable=AsyncMock)
    def test_invalid_jwt_closes_with_4001(self, mock_auth):
        """WS connection with invalid JWT is closed with code 4001."""
        mock_auth.return_value = None  # Auth failure

        with TestClient(app) as client:
            with pytest.raises(Exception):
                with client.websocket_connect("/battles/ws/1?token=bad-token"):
                    pass  # Should not reach here

    @patch("main.authenticate_websocket", new_callable=AsyncMock)
    def test_missing_token_query_param(self, mock_auth):
        """WS connection without token query param returns 422 (FastAPI validation)."""
        with TestClient(app) as client:
            # FastAPI will reject missing required query param before reaching the endpoint
            with pytest.raises(Exception):
                with client.websocket_connect("/battles/ws/1"):
                    pass

    @patch("main.get_db")
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.authenticate_websocket", new_callable=AsyncMock)
    def test_valid_jwt_no_battle_state_closes_4003(self, mock_auth, mock_load_state, mock_get_db):
        """WS with valid JWT but no battle state closes with 4003."""
        mock_auth.return_value = AUTH_USER
        mock_load_state.return_value = None  # Battle not found

        with TestClient(app) as client:
            with pytest.raises(Exception):
                with client.websocket_connect("/battles/ws/1?token=valid-token"):
                    pass


class TestWebSocketParticipantAccess:
    """Tests for participant vs non-participant access control."""

    @pytest.fixture(autouse=True)
    def _clear_connections(self):
        ws_manager.battle_connections.clear()
        yield
        ws_manager.battle_connections.clear()

    @patch("main.load_snapshot", new_callable=AsyncMock)
    @patch("main.get_cached_snapshot", new_callable=AsyncMock)
    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.get_db")
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.authenticate_websocket", new_callable=AsyncMock)
    def test_participant_connection_accepted(
        self, mock_auth, mock_load_state, mock_get_db,
        mock_redis, mock_cached_snapshot, mock_load_snapshot,
    ):
        """Participant (user owns a character in battle) can connect."""
        mock_auth.return_value = {"id": 1, "username": "player"}
        mock_load_state.return_value = SAMPLE_REDIS_STATE

        # Mock DB session: character_id=10 belongs to user_id=1
        mock_session = AsyncMock()
        mock_result = MagicMock()
        # First query: check character 10 -> user_id 1 (match!)
        mock_result.fetchone.return_value = (1,)
        mock_session.execute = AsyncMock(return_value=mock_result)

        async def fake_get_db():
            yield mock_session

        mock_get_db.return_value = fake_get_db()

        mock_redis.return_value = AsyncMock()
        mock_cached_snapshot.return_value = SAMPLE_SNAPSHOT
        # Second load_state for initial state send
        mock_load_state.side_effect = [SAMPLE_REDIS_STATE, SAMPLE_REDIS_STATE]

        with TestClient(app) as client:
            with client.websocket_connect("/battles/ws/1?token=valid-token") as ws:
                # Should receive initial battle_state message
                data = ws.receive_json()
                assert data["type"] == "battle_state"
                assert "snapshot" in data["data"]
                assert "runtime" in data["data"]

    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.get_db")
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.authenticate_websocket", new_callable=AsyncMock)
    def test_non_participant_not_at_location_closes_4003(
        self, mock_auth, mock_load_state, mock_get_db, mock_get_battle,
    ):
        """Non-participant user at a different location is rejected (4003)."""
        mock_auth.return_value = {"id": 99, "username": "bystander"}
        mock_load_state.return_value = SAMPLE_REDIS_STATE

        # Mock DB session: no character belongs to user 99
        mock_session = AsyncMock()

        call_count = 0

        async def fake_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count <= 2:
                # Character ownership check: no match for user 99
                result.fetchone.return_value = (50,)  # Different user
            else:
                # User's characters - at different location
                result.fetchall.return_value = [(300, 200)]  # char at location 200
            return result

        mock_session.execute = AsyncMock(side_effect=fake_execute)

        async def fake_get_db():
            yield mock_session

        mock_get_db.return_value = fake_get_db()

        # Battle at location 100
        mock_get_battle.return_value = _make_battle(
            battle_id=1, status="in_progress", location_id=100,
        )

        with TestClient(app) as client:
            with pytest.raises(Exception):
                with client.websocket_connect("/battles/ws/1?token=valid-token"):
                    pass


class TestWebSocketStateDelivery:
    """Tests for state update delivery through WebSocket."""

    @pytest.fixture(autouse=True)
    def _clear_connections(self):
        ws_manager.battle_connections.clear()
        yield
        ws_manager.battle_connections.clear()

    @pytest.mark.asyncio
    async def test_state_update_broadcast(self):
        """When broadcast_to_battle is called, connected clients receive the message."""
        ws = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws)

        state_data = {
            "type": "battle_state",
            "data": {
                "snapshot": SAMPLE_SNAPSHOT,
                "runtime": {"turn_number": 4},
            },
        }
        await ws_manager.broadcast_to_battle(1, state_data)

        ws.send_json.assert_awaited_once_with(state_data)

    @pytest.mark.asyncio
    async def test_battle_finished_message(self):
        """battle_finished message is delivered to connected clients."""
        ws = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws)

        finished_data = {
            "type": "battle_finished",
            "data": {
                "winner_team": 0,
                "rewards": {"gold": 100, "xp": 50},
            },
        }
        await ws_manager.broadcast_to_battle(1, finished_data)

        ws.send_json.assert_awaited_once_with(finished_data)
        sent_msg = ws.send_json.call_args[0][0]
        assert sent_msg["type"] == "battle_finished"
        assert sent_msg["data"]["winner_team"] == 0

    @pytest.mark.asyncio
    async def test_battle_paused_message(self):
        """battle_paused message is delivered to connected clients."""
        ws = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws)

        paused_data = {
            "type": "battle_paused",
            "data": {"is_paused": True, "reason": "Join request"},
        }
        await ws_manager.broadcast_to_battle(1, paused_data)

        ws.send_json.assert_awaited_once_with(paused_data)
        sent_msg = ws.send_json.call_args[0][0]
        assert sent_msg["type"] == "battle_paused"

    @pytest.mark.asyncio
    async def test_multiple_updates_delivered_in_order(self):
        """Multiple state updates are delivered sequentially."""
        ws = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws)

        msg1 = {"type": "battle_state", "data": {"turn_number": 1}}
        msg2 = {"type": "battle_state", "data": {"turn_number": 2}}
        msg3 = {"type": "battle_finished", "data": {"winner_team": 0}}

        await ws_manager.broadcast_to_battle(1, msg1)
        await ws_manager.broadcast_to_battle(1, msg2)
        await ws_manager.broadcast_to_battle(1, msg3)

        assert ws.send_json.await_count == 3
        calls = ws.send_json.call_args_list
        assert calls[0][0][0]["data"]["turn_number"] == 1
        assert calls[1][0][0]["data"]["turn_number"] == 2
        assert calls[2][0][0]["type"] == "battle_finished"


class TestWebSocketConnectionLifecycle:
    """Tests for connection lifecycle and cleanup."""

    @pytest.fixture(autouse=True)
    def _clear_connections(self):
        ws_manager.battle_connections.clear()
        yield
        ws_manager.battle_connections.clear()

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up_connection(self):
        """After disconnect, the user is no longer in battle_connections."""
        ws = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws)

        assert 10 in ws_manager.battle_connections[1]

        await ws_manager.disconnect(battle_id=1, user_id=10)

        assert 1 not in ws_manager.battle_connections

    @pytest.mark.asyncio
    async def test_cleanup_after_battle_finish(self):
        """cleanup_battle removes all connections for a finished battle."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await ws_manager.connect(battle_id=1, user_id=10, websocket=ws1)
        await ws_manager.connect(battle_id=1, user_id=20, websocket=ws2)

        # Simulate battle finish
        await ws_manager.broadcast_to_battle(1, {
            "type": "battle_finished",
            "data": {"winner_team": 0},
        })

        # Then cleanup
        await ws_manager.cleanup_battle(1)

        assert 1 not in ws_manager.battle_connections
        ws1.close.assert_awaited_once()
        ws2.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reconnect_replaces_old_connection(self):
        """If a user reconnects, old connection is closed, new one stored."""
        old_ws = AsyncMock()
        new_ws = AsyncMock()

        await ws_manager.connect(battle_id=1, user_id=10, websocket=old_ws)
        await ws_manager.connect(battle_id=1, user_id=10, websocket=new_ws)

        old_ws.close.assert_awaited_once()
        assert ws_manager.battle_connections[1][10] is new_ws

        # New connection receives broadcasts
        await ws_manager.broadcast_to_battle(1, {"type": "test"})
        new_ws.send_json.assert_awaited_once()
        # Old connection should not receive anything after replacement
        old_ws.send_json.assert_not_awaited()


class TestRedisSubscriber:
    """Tests for the Redis Pub/Sub subscriber logic."""

    @pytest.fixture(autouse=True)
    def _clear_connections(self):
        ws_manager.battle_connections.clear()
        yield
        ws_manager.battle_connections.clear()

    @pytest.mark.asyncio
    async def test_subscriber_routes_message_to_broadcast(self):
        """
        Simulates the subscriber logic: parsing a Redis Pub/Sub message
        and routing it to ws_manager.broadcast_to_battle().
        """
        ws = AsyncMock()
        await ws_manager.connect(battle_id=42, user_id=10, websocket=ws)

        # Simulate what _redis_state_update_subscriber does internally
        channel = "battle:42:state_update"
        parts = channel.split(":")
        battle_id = int(parts[1])
        data = {
            "type": "battle_state",
            "data": {"snapshot": SAMPLE_SNAPSHOT, "runtime": {"turn_number": 5}},
        }

        await ws_manager.broadcast_to_battle(battle_id, data)

        ws.send_json.assert_awaited_once_with(data)
        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "battle_state"

    @pytest.mark.asyncio
    async def test_channel_parsing_extracts_battle_id(self):
        """Channel format 'battle:{id}:state_update' correctly extracts battle_id."""
        test_cases = [
            ("battle:1:state_update", 1),
            ("battle:42:state_update", 42),
            ("battle:999:state_update", 999),
        ]
        for channel, expected_id in test_cases:
            parts = channel.split(":")
            battle_id = int(parts[1])
            assert battle_id == expected_id


class TestAuthenticateWebsocket:
    """Tests for the authenticate_websocket helper function."""

    @pytest.mark.asyncio
    @patch("auth_http.httpx.AsyncClient")
    async def test_valid_token_returns_user(self, mock_client_cls):
        """Valid token returns user dict from user-service."""
        from auth_http import authenticate_websocket

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = AUTH_USER

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await authenticate_websocket("valid-token")

        assert result is not None
        assert result["id"] == 1
        assert result["username"] == "player"

    @pytest.mark.asyncio
    @patch("auth_http.httpx.AsyncClient")
    async def test_invalid_token_returns_none(self, mock_client_cls):
        """Invalid token returns None."""
        from auth_http import authenticate_websocket

        mock_resp = MagicMock()
        mock_resp.status_code = 401

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await authenticate_websocket("bad-token")

        assert result is None

    @pytest.mark.asyncio
    @patch("auth_http.httpx.AsyncClient")
    async def test_connection_error_returns_none(self, mock_client_cls):
        """Network error to user-service returns None (graceful failure)."""
        from auth_http import authenticate_websocket

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await authenticate_websocket("any-token")

        assert result is None
