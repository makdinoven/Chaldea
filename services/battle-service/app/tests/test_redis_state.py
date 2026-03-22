"""
Tests for Redis pubsub format fix in init_battle_state() (FEAT-060, Task #2).

Verifies that:
- init_battle_state() publishes str(first_actor_participant_id) (not json.dumps)
- The published message can be parsed as int() by the consumer
- The state is correctly saved to Redis
"""

import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

import pytest

# Set env vars before importing config
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Remove any mocked versions of redis_state left by other test files
# (e.g. test_battle_fixes.py injects MagicMock into sys.modules at module level)
for _mod in ("redis_state",):
    if _mod in sys.modules and isinstance(sys.modules[_mod], MagicMock):
        del sys.modules[_mod]

# Patch database engine before importing anything that touches it
import database  # noqa: E402
database.engine = MagicMock()

# Now import redis_state — it doesn't connect at import time (lazy singleton)
import redis_state  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_participants(pid1=1, pid2=2):
    """Build a minimal participants payload for init_battle_state()."""
    return [
        {
            "participant_id": pid1,
            "character_id": 10,
            "team": 0,
            "hp": 100, "mana": 50, "energy": 50, "stamina": 50,
            "max_hp": 100, "max_mana": 100, "max_energy": 100, "max_stamina": 100,
            "fast_slots": [],
        },
        {
            "participant_id": pid2,
            "character_id": 20,
            "team": 1,
            "hp": 80, "mana": 40, "energy": 40, "stamina": 40,
            "max_hp": 100, "max_mana": 100, "max_energy": 100, "max_stamina": 100,
            "fast_slots": [],
        },
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestInitBattleStatePubsub:
    """Verify init_battle_state publishes the correct format on your_turn channel."""

    @pytest.mark.asyncio
    async def test_publishes_participant_id_as_string(self):
        """The pubsub message should be str(first_actor_participant_id), not JSON."""
        mock_redis = AsyncMock()

        with patch.object(redis_state, "get_redis_client", return_value=mock_redis):
            await redis_state.init_battle_state(
                battle_id=42,
                participants_payload=_make_participants(pid1=7, pid2=8),
                first_actor_participant_id=7,
                deadline_at=datetime(2026, 1, 1, 12, 0, 0),
            )

        # Find the publish call
        publish_calls = [
            call for call in mock_redis.publish.call_args_list
            if "your_turn" in str(call)
        ]
        assert len(publish_calls) == 1, (
            f"Expected exactly 1 publish to your_turn, got {len(publish_calls)}"
        )

        channel, message = publish_calls[0].args
        assert channel == "battle:42:your_turn"
        assert message == "7", f"Expected '7', got {message!r}"

    @pytest.mark.asyncio
    async def test_published_message_parseable_as_int(self):
        """The published message must be parseable as int() by autobattle reader."""
        mock_redis = AsyncMock()

        with patch.object(redis_state, "get_redis_client", return_value=mock_redis):
            await redis_state.init_battle_state(
                battle_id=1,
                participants_payload=_make_participants(pid1=42, pid2=99),
                first_actor_participant_id=42,
                deadline_at=datetime(2026, 6, 15),
            )

        publish_calls = [
            call for call in mock_redis.publish.call_args_list
            if "your_turn" in str(call)
        ]
        _, message = publish_calls[0].args

        # This is exactly what autobattle's redis_reader() does:
        # pid = int(msg["data"])
        parsed = int(message)
        assert parsed == 42

    @pytest.mark.asyncio
    async def test_published_message_is_not_json_object(self):
        """The message must NOT be a JSON object (the old broken format)."""
        import json
        mock_redis = AsyncMock()

        with patch.object(redis_state, "get_redis_client", return_value=mock_redis):
            await redis_state.init_battle_state(
                battle_id=5,
                participants_payload=_make_participants(),
                first_actor_participant_id=1,
                deadline_at=datetime(2026, 1, 1),
            )

        publish_calls = [
            call for call in mock_redis.publish.call_args_list
            if "your_turn" in str(call)
        ]
        _, message = publish_calls[0].args

        # If it were JSON, json.loads would return a dict.
        # It should be a plain integer string.
        try:
            parsed = json.loads(message)
            # If it parses as JSON, it should be an int, not a dict
            assert not isinstance(parsed, dict), (
                "Message should not be a JSON object (full battle state)"
            )
        except (json.JSONDecodeError, TypeError):
            # Not valid JSON at all — that's fine, it's a plain string
            pass

    @pytest.mark.asyncio
    async def test_second_participant_as_first_actor(self):
        """When pid2 is first_actor, published message should be str(pid2)."""
        mock_redis = AsyncMock()

        with patch.object(redis_state, "get_redis_client", return_value=mock_redis):
            await redis_state.init_battle_state(
                battle_id=10,
                participants_payload=_make_participants(pid1=3, pid2=5),
                first_actor_participant_id=5,
                deadline_at=datetime(2026, 1, 1),
            )

        publish_calls = [
            call for call in mock_redis.publish.call_args_list
            if "your_turn" in str(call)
        ]
        _, message = publish_calls[0].args
        assert message == "5"
        assert int(message) == 5


class TestInitBattleStateStorage:
    """Verify init_battle_state correctly stores state and deadline in Redis."""

    @pytest.mark.asyncio
    async def test_state_saved_to_redis(self):
        """Battle state should be saved as JSON under the correct key."""
        import json
        mock_redis = AsyncMock()

        with patch.object(redis_state, "get_redis_client", return_value=mock_redis):
            await redis_state.init_battle_state(
                battle_id=42,
                participants_payload=_make_participants(),
                first_actor_participant_id=1,
                deadline_at=datetime(2026, 1, 1, 12, 0, 0),
            )

        # Verify redis.set was called with the state key
        set_calls = mock_redis.set.call_args_list
        assert len(set_calls) == 1

        key = set_calls[0].args[0]
        assert key == "battle:42:state"

        saved_json = set_calls[0].args[1]
        state = json.loads(saved_json)
        assert state["turn_number"] == 0
        assert state["next_actor"] == 1
        assert state["first_actor"] == 1
        assert "1" in state["participants"]
        assert "2" in state["participants"]

    @pytest.mark.asyncio
    async def test_deadline_added_to_zset(self):
        """First turn deadline should be added to the deadlines ZSET."""
        mock_redis = AsyncMock()
        deadline = datetime(2026, 1, 1, 12, 0, 0)

        with patch.object(redis_state, "get_redis_client", return_value=mock_redis):
            await redis_state.init_battle_state(
                battle_id=42,
                participants_payload=_make_participants(),
                first_actor_participant_id=1,
                deadline_at=deadline,
            )

        zadd_calls = mock_redis.zadd.call_args_list
        assert len(zadd_calls) == 1

        zset_key = zadd_calls[0].args[0]
        assert zset_key == "battle:deadlines"

        member_scores = zadd_calls[0].args[1]
        assert "42:1" in member_scores
        assert member_scores["42:1"] == deadline.timestamp()
