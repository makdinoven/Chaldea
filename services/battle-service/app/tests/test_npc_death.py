"""
Tests for post-battle NPC death hook (FEAT-064).

Covers:
- Post-battle hook marks defeated NPC as dead (mock HTTP call to character-service)
- Post-battle hook does NOT affect mobs (npc_role='mob')
- Post-battle hook does NOT affect player characters (is_npc=False)

These tests verify the NPC death block in _make_action_core that runs after
battle finishes and calls PUT /characters/internal/npc-status/{id}.
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
from datetime import datetime, timedelta, timezone

import pytest

# Patch heavy external modules BEFORE importing main
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("aioredis", MagicMock())
sys.modules.setdefault("celery", MagicMock())

import database  # noqa: E402

database.engine = MagicMock()

# Mock all external client modules to prevent actual connections.
# NOTE: battle_engine is intentionally NOT mocked here — it has no side effects
# on import and its functions are patched on `main` via @patch decorators in tests.
# Mocking it in sys.modules would poison test_battle_fixes.py which imports the
# real decrement_cooldowns/set_cooldown functions.
for mod_name in [
    "redis_state",
    "mongo_client",
    "mongo_helpers",
    "tasks",
    "inventory_client",
    "character_client",
    "skills_client",
    "buffs",
    "rabbitmq_publisher",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

# Ensure redis_state
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

# Ensure tasks
tasks_mock = sys.modules["tasks"]
tasks_mock.save_log = MagicMock()
tasks_mock.save_log.delay = MagicMock()

# Ensure buffs
buffs_mock = sys.modules["buffs"]
buffs_mock.decrement_durations = MagicMock()
buffs_mock.aggregate_modifiers = MagicMock(return_value={})
buffs_mock.apply_new_effects = MagicMock()
buffs_mock.build_percent_damage_buffs = MagicMock(return_value={})
buffs_mock.build_percent_resist_buffs = MagicMock(return_value={})

# Ensure skills_client
skills_mock = sys.modules["skills_client"]
skills_mock.character_has_rank = AsyncMock(return_value=True)
skills_mock.get_rank = AsyncMock(return_value={
    "id": 1, "skill_type": "attack", "damage_type": "physical",
    "base_damage": 50, "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
    "cooldown_turns": 0, "cooldown": 0, "effect_type": None,
    "damage_entries": [{"damage_type": "physical", "amount": 50, "chance": 100}],
    "effects": [],
})
skills_mock.get_item = AsyncMock(return_value={})
skills_mock.character_ranks = AsyncMock(return_value=[])

# Ensure mongo_helpers
mongo_mock = sys.modules["mongo_helpers"]
mongo_mock.save_snapshot = AsyncMock()
mongo_mock.load_snapshot = AsyncMock(return_value=None)

# Ensure rabbitmq_publisher
rmq_mock = sys.modules["rabbitmq_publisher"]
rmq_mock.publish_notification = AsyncMock()

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
from database import get_db  # noqa: E402
from auth_http import get_current_user_via_http, UserRead  # noqa: E402

# Clear startup handlers to avoid connection attempts
app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(user_id=1):
    return UserRead(id=user_id, username="testuser", role="user", permissions=[])


def _row(*values):
    """Create a mock row that supports both index access and attribute access."""
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


def _build_battle_state():
    """Build a battle state where participant 1 (team 0) kills participant 2 (team 1)."""
    moscow_tz = timezone(timedelta(hours=3))
    deadline = datetime.now(timezone.utc).astimezone(moscow_tz) + timedelta(hours=24)
    return {
        "turn_number": 1,
        "next_actor": 1,
        "first_actor": 1,
        "turn_order": [1, 2],
        "total_turns": 0,
        "last_turn": None,
        "deadline_at": deadline.isoformat(),
        "participants": {
            "1": {
                "character_id": 10,
                "team": 0,
                "hp": 100,
                "mana": 50,
                "energy": 50,
                "stamina": 50,
                "max_hp": 100,
                "max_mana": 50,
                "max_energy": 50,
                "max_stamina": 50,
                "cooldowns": {},
                "fast_slots": [],
            },
            "2": {
                "character_id": 20,
                "team": 1,
                "hp": 1,  # Low HP — will die from attack
                "mana": 50,
                "energy": 50,
                "stamina": 50,
                "max_hp": 100,
                "max_mana": 50,
                "max_energy": 50,
                "max_stamina": 50,
                "cooldowns": {},
                "fast_slots": [],
            },
        },
        "active_effects": {},
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNpcDeathHook:
    """Post-battle NPC death hook tests."""

    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main.httpx.AsyncClient")
    @patch("main.finish_battle", new_callable=AsyncMock)
    @patch("main.write_turn", new_callable=AsyncMock)
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.compute_damage_with_rolls", new_callable=AsyncMock)
    @patch("main.fetch_character_class_id", new_callable=AsyncMock, return_value=1)
    @patch("main.fetch_main_weapon", new_callable=AsyncMock)
    @patch("main.fetch_full_attributes", new_callable=AsyncMock)
    @patch("main.apply_flat_modifiers", MagicMock(return_value={}))
    @patch("main.decrement_cooldowns", MagicMock())
    @patch("main.set_cooldown", MagicMock())
    @patch("main.decrement_durations", MagicMock())
    @patch("main.aggregate_modifiers", MagicMock(return_value={}))
    @patch("main.apply_new_effects", MagicMock())
    @patch("main.build_percent_damage_buffs", MagicMock(return_value={}))
    @patch("main.build_percent_resist_buffs", MagicMock(return_value={}))
    @patch("main.character_has_rank", new_callable=AsyncMock)
    @patch("main.get_rank", new_callable=AsyncMock)
    @patch("main.save_state", new_callable=AsyncMock)
    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.save_log", MagicMock())
    def test_npc_marked_dead_after_defeat(
        self,
        mock_get_redis, mock_save_state,
        mock_get_rank, mock_has_rank,
        mock_fetch_attrs, mock_fetch_weapon, mock_fetch_class_id, mock_compute_damage,
        mock_load_state, mock_get_battle, mock_write_turn,
        mock_finish_battle, mock_httpx_client,
    ):
        """When an NPC (is_npc=True, npc_role != 'mob') is defeated,
        the hook should call PUT /internal/npc-status/{id} with status=dead."""
        # Configure battle_engine / skills mocks
        mock_fetch_attrs.return_value = {
            "damage": 5, "dodge": 0, "critical_hit_chance": 0,
            "critical_damage": 100, "current_health": 100,
            "current_mana": 50, "current_energy": 50, "current_stamina": 50,
        }
        mock_fetch_weapon.return_value = {"damage_type": "physical", "base_damage": 10}
        mock_compute_damage.return_value = (999, {"damage_type": "physical", "final": 999})
        mock_has_rank.return_value = True
        mock_get_rank.return_value = {
            "id": 1, "damage_entries": [{"damage_type": "physical", "amount": 50, "chance": 100}],
            "effects": [], "cooldown": 0,
            "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
        }
        mock_get_redis.return_value = AsyncMock()

        user = _make_user(user_id=1)
        battle_state = _build_battle_state()
        mock_load_state.return_value = battle_state

        mock_battle_record = MagicMock()
        mock_battle_record.status.value = "in_progress"
        mock_get_battle.return_value = mock_battle_record

        mock_write_turn.return_value = MagicMock(id=1)

        # Track HTTP calls made by the NPC death hook
        httpx_put_calls = []

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "status": "dead"}
        mock_response.text = '{"ok": true}'

        async_client_instance = AsyncMock()
        async_client_instance.put = AsyncMock(return_value=mock_response)
        async_client_instance.get = AsyncMock(return_value=mock_response)

        # Track put calls
        original_put = async_client_instance.put

        async def tracked_put(*args, **kwargs):
            httpx_put_calls.append((args, kwargs))
            return mock_response

        async_client_instance.put = AsyncMock(side_effect=tracked_put)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=async_client_instance)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_client.return_value = mock_ctx

        execute_calls = []
        mock_db = AsyncMock()

        async def track_execute(query, params=None):
            query_str = str(query)
            execute_calls.append((query_str, params))

            # Ownership check: character 10 belongs to user 1
            if "user_id FROM characters" in query_str and params and params.get("cid") == 10:
                return _result_with_row(_row(1,))

            # Battle type check — PvE battle
            if "battle_type FROM battles" in query_str:
                return _result_with_row(_row("pve",))

            # NPC check: character 20 IS an NPC (is_npc=1, npc_role='merchant')
            if "is_npc, npc_role FROM characters" in query_str and params and params.get("cid") == 20:
                return _result_with_row(_row(1, "merchant"))

            # Mob reward data check — return empty (not a mob)
            if "mob_reward" in query_str.lower() or "active_mob" in query_str.lower():
                return _result_empty()

            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=track_execute)
        mock_db.commit = AsyncMock()

        # Create a proper context manager for db_session.begin()
        mock_begin_ctx = AsyncMock()
        mock_begin_ctx.__aenter__ = AsyncMock(return_value=None)
        mock_begin_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.begin = MagicMock(return_value=mock_begin_ctx)

        def override_auth():
            return user

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_current_user_via_http] = override_auth
        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as client:
            response = client.post(
                "/battles/1/action",
                json=ACTION_PAYLOAD,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["battle_finished"] is True

        # Verify that the NPC check query was executed for defeated char 20
        npc_check_calls = [
            (q, p) for q, p in execute_calls
            if "is_npc" in q and "npc_role" in q and p and p.get("cid") == 20
        ]
        assert len(npc_check_calls) >= 1, "Should have checked if defeated char 20 is an NPC"

        # Verify HTTP PUT was called to mark NPC as dead
        # Filter for npc-status calls specifically (exclude active-mob-status from PvE rewards)
        npc_status_puts = [
            (a, k) for a, k in httpx_put_calls
            if "npc-status" in (a[0] if a else k.get("url", ""))
        ]
        assert len(npc_status_puts) >= 1, "Should have called PUT to mark NPC as dead"
        put_args, put_kwargs = npc_status_puts[0]
        put_url = put_args[0] if put_args else put_kwargs.get("url", "")
        assert "internal/npc-status/20" in put_url
        put_json = put_kwargs.get("json", {})
        assert put_json.get("status") == "dead"

    @patch("main.httpx.AsyncClient")
    @patch("main.finish_battle", new_callable=AsyncMock)
    @patch("main.write_turn", new_callable=AsyncMock)
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.compute_damage_with_rolls", new_callable=AsyncMock)
    @patch("main.fetch_character_class_id", new_callable=AsyncMock, return_value=1)
    @patch("main.fetch_main_weapon", new_callable=AsyncMock)
    @patch("main.fetch_full_attributes", new_callable=AsyncMock)
    @patch("main.apply_flat_modifiers", MagicMock(return_value={}))
    @patch("main.decrement_cooldowns", MagicMock())
    @patch("main.set_cooldown", MagicMock())
    @patch("main.decrement_durations", MagicMock())
    @patch("main.aggregate_modifiers", MagicMock(return_value={}))
    @patch("main.apply_new_effects", MagicMock())
    @patch("main.build_percent_damage_buffs", MagicMock(return_value={}))
    @patch("main.build_percent_resist_buffs", MagicMock(return_value={}))
    @patch("main.character_has_rank", new_callable=AsyncMock)
    @patch("main.get_rank", new_callable=AsyncMock)
    @patch("main.save_state", new_callable=AsyncMock)
    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.save_log", MagicMock())
    def test_mob_not_affected_by_npc_death_hook(
        self,
        mock_get_redis, mock_save_state,
        mock_get_rank, mock_has_rank,
        mock_fetch_attrs, mock_fetch_weapon, mock_fetch_class_id, mock_compute_damage,
        mock_load_state, mock_get_battle, mock_write_turn,
        mock_finish_battle, mock_httpx_client,
    ):
        """When a mob (npc_role='mob') is defeated, the NPC death hook should
        NOT fire — mob death is handled by the PvE reward system instead."""
        # Configure battle_engine / skills mocks
        mock_fetch_attrs.return_value = {
            "damage": 5, "dodge": 0, "critical_hit_chance": 0,
            "critical_damage": 100, "current_health": 100,
            "current_mana": 50, "current_energy": 50, "current_stamina": 50,
        }
        mock_fetch_weapon.return_value = {"damage_type": "physical", "base_damage": 10}
        mock_compute_damage.return_value = (999, {"damage_type": "physical", "final": 999})
        mock_has_rank.return_value = True
        mock_get_rank.return_value = {
            "id": 1, "damage_entries": [{"damage_type": "physical", "amount": 50, "chance": 100}],
            "effects": [], "cooldown": 0,
            "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
        }
        mock_get_redis.return_value = AsyncMock()

        user = _make_user(user_id=1)
        battle_state = _build_battle_state()
        mock_load_state.return_value = battle_state

        mock_battle_record = MagicMock()
        mock_battle_record.status.value = "in_progress"
        mock_get_battle.return_value = mock_battle_record

        mock_write_turn.return_value = MagicMock(id=1)

        httpx_put_calls = []

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.text = '{}'

        async_client_instance = AsyncMock()

        async def tracked_put(*args, **kwargs):
            httpx_put_calls.append((args, kwargs))
            return mock_response

        async_client_instance.put = AsyncMock(side_effect=tracked_put)
        async_client_instance.get = AsyncMock(return_value=mock_response)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=async_client_instance)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_client.return_value = mock_ctx

        mock_db = AsyncMock()

        async def track_execute(query, params=None):
            query_str = str(query)

            if "user_id FROM characters" in query_str and params and params.get("cid") == 10:
                return _result_with_row(_row(1,))

            if "battle_type FROM battles" in query_str:
                return _result_with_row(_row("pve",))

            # NPC check: character 20 is a mob (query filters npc_role != 'mob')
            # So the query returns NULL — no row found
            if "is_npc, npc_role FROM characters" in query_str and params and params.get("cid") == 20:
                return _result_empty()

            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=track_execute)
        mock_db.commit = AsyncMock()

        mock_begin_ctx = AsyncMock()
        mock_begin_ctx.__aenter__ = AsyncMock(return_value=None)
        mock_begin_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.begin = MagicMock(return_value=mock_begin_ctx)

        def override_auth():
            return user

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_current_user_via_http] = override_auth
        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as client:
            response = client.post(
                "/battles/1/action",
                json=ACTION_PAYLOAD,
            )

        assert response.status_code == 200

        # Filter httpx PUT calls for npc-status endpoint specifically
        npc_status_puts = [
            (a, k) for a, k in httpx_put_calls
            if "npc-status" in (a[0] if a else k.get("url", ""))
        ]
        assert len(npc_status_puts) == 0, (
            "NPC death hook should NOT fire for mobs (npc_role='mob')"
        )

    @patch("main.httpx.AsyncClient")
    @patch("main.finish_battle", new_callable=AsyncMock)
    @patch("main.write_turn", new_callable=AsyncMock)
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.compute_damage_with_rolls", new_callable=AsyncMock)
    @patch("main.fetch_character_class_id", new_callable=AsyncMock, return_value=1)
    @patch("main.fetch_main_weapon", new_callable=AsyncMock)
    @patch("main.fetch_full_attributes", new_callable=AsyncMock)
    @patch("main.apply_flat_modifiers", MagicMock(return_value={}))
    @patch("main.decrement_cooldowns", MagicMock())
    @patch("main.set_cooldown", MagicMock())
    @patch("main.decrement_durations", MagicMock())
    @patch("main.aggregate_modifiers", MagicMock(return_value={}))
    @patch("main.apply_new_effects", MagicMock())
    @patch("main.build_percent_damage_buffs", MagicMock(return_value={}))
    @patch("main.build_percent_resist_buffs", MagicMock(return_value={}))
    @patch("main.character_has_rank", new_callable=AsyncMock)
    @patch("main.get_rank", new_callable=AsyncMock)
    @patch("main.save_state", new_callable=AsyncMock)
    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.save_log", MagicMock())
    def test_player_not_affected_by_npc_death_hook(
        self,
        mock_get_redis, mock_save_state,
        mock_get_rank, mock_has_rank,
        mock_fetch_attrs, mock_fetch_weapon, mock_fetch_class_id, mock_compute_damage,
        mock_load_state, mock_get_battle, mock_write_turn,
        mock_finish_battle, mock_httpx_client,
    ):
        """When a player character (is_npc=False) is defeated, the NPC death
        hook should NOT fire."""
        # Configure battle_engine / skills mocks
        mock_fetch_attrs.return_value = {
            "damage": 5, "dodge": 0, "critical_hit_chance": 0,
            "critical_damage": 100, "current_health": 100,
            "current_mana": 50, "current_energy": 50, "current_stamina": 50,
        }
        mock_fetch_weapon.return_value = {"damage_type": "physical", "base_damage": 10}
        mock_compute_damage.return_value = (999, {"damage_type": "physical", "final": 999})
        mock_has_rank.return_value = True
        mock_get_rank.return_value = {
            "id": 1, "damage_entries": [{"damage_type": "physical", "amount": 50, "chance": 100}],
            "effects": [], "cooldown": 0,
            "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
        }
        mock_get_redis.return_value = AsyncMock()

        user = _make_user(user_id=1)
        battle_state = _build_battle_state()
        mock_load_state.return_value = battle_state

        mock_battle_record = MagicMock()
        mock_battle_record.status.value = "in_progress"
        mock_get_battle.return_value = mock_battle_record

        mock_write_turn.return_value = MagicMock(id=1)

        httpx_put_calls = []

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.text = '{}'

        async_client_instance = AsyncMock()

        async def tracked_put(*args, **kwargs):
            httpx_put_calls.append((args, kwargs))
            return mock_response

        async_client_instance.put = AsyncMock(side_effect=tracked_put)
        async_client_instance.get = AsyncMock(return_value=mock_response)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=async_client_instance)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_client.return_value = mock_ctx

        mock_db = AsyncMock()

        async def track_execute(query, params=None):
            query_str = str(query)

            if "user_id FROM characters" in query_str and params and params.get("cid") == 10:
                return _result_with_row(_row(1,))

            if "battle_type FROM battles" in query_str:
                return _result_with_row(_row("pvp_attack",))

            # NPC check: character 20 is a player (is_npc=0) — query returns no rows
            if "is_npc, npc_role FROM characters" in query_str and params and params.get("cid") == 20:
                return _result_empty()

            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=track_execute)
        mock_db.commit = AsyncMock()

        mock_begin_ctx = AsyncMock()
        mock_begin_ctx.__aenter__ = AsyncMock(return_value=None)
        mock_begin_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.begin = MagicMock(return_value=mock_begin_ctx)

        def override_auth():
            return user

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_current_user_via_http] = override_auth
        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as client:
            response = client.post(
                "/battles/1/action",
                json=ACTION_PAYLOAD,
            )

        assert response.status_code == 200

        # No NPC-status calls should be made for player characters
        npc_status_puts = [
            (a, k) for a, k in httpx_put_calls
            if "npc-status" in (a[0] if a else k.get("url", ""))
        ]
        assert len(npc_status_puts) == 0, (
            "NPC death hook should NOT fire for player characters"
        )
