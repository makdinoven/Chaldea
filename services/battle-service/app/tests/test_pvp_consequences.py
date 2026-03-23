"""
Tests for PvP post-battle consequences in battle-service.

Covers:
- After pvp_training battle, loser HP is set to 1
- After pvp_attack battle, normal flow (no HP override)
- After PvE battle, no change to existing flow

These tests verify the post-battle hook in _make_action_core that handles
pvp_training consequences (setting loser HP to 1 via direct DB update).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, AsyncMock, call
from datetime import datetime, timedelta, timezone

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

# Ensure battle_engine
engine_mock = sys.modules["battle_engine"]
engine_mock.decrement_cooldowns = MagicMock()
engine_mock.set_cooldown = MagicMock()
engine_mock.fetch_full_attributes = AsyncMock(return_value={})
engine_mock.apply_flat_modifiers = MagicMock(return_value={})
engine_mock.fetch_main_weapon = AsyncMock(return_value={"damage_type": "physical", "base_damage": 10})
engine_mock.compute_damage_with_rolls = AsyncMock(return_value=(999, {}))  # lethal damage

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
    "damage_entries": [{"damage_type": "physical", "base_damage": 50}],
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

# Now import main safely
from main import app  # noqa: E402
from database import get_db  # noqa: E402
from auth_http import get_current_user_via_http, UserRead  # noqa: E402

# Clear startup handlers
app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_user(user_id=1):
    return UserRead(id=user_id, username="testuser", role="user", permissions=[])


def _row(*values):
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


def _build_battle_state(battle_type="pvp_training"):
    """Build a battle state where participant 1 (team 0) attacks participant 2 (team 1).
    Participant 2 has low HP so the attack will finish the battle."""
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


class TestPvpTrainingConsequences:
    """After pvp_training battle, loser HP is set to 1."""

    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main.finish_battle", new_callable=AsyncMock)
    @patch("main.write_turn", new_callable=AsyncMock)
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.character_has_rank", new_callable=AsyncMock, return_value=True)
    @patch("main.get_rank", new_callable=AsyncMock)
    @patch("main.compute_damage_with_rolls", new_callable=AsyncMock, return_value=(999, {}))
    def test_pvp_training_sets_loser_hp_to_1(
        self, mock_compute, mock_get_rank, mock_has_rank,
        mock_load_state, mock_get_battle, mock_write_turn, mock_finish_battle
    ):
        """After pvp_training finishes, loser's HP in character_attributes is set to 1."""
        mock_get_rank.return_value = {
            "id": 1, "skill_type": "attack", "damage_type": "physical",
            "base_damage": 50, "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
            "cooldown_turns": 0, "cooldown": 0, "effect_type": None,
            "damage_entries": [{"damage_type": "physical", "base_damage": 50}],
            "effects": [],
        }

        user = _make_user(user_id=1)
        battle_state = _build_battle_state("pvp_training")
        mock_load_state.return_value = battle_state

        # Mock battle record (not finished)
        mock_battle_record = MagicMock()
        mock_battle_record.status.value = "in_progress"
        mock_get_battle.return_value = mock_battle_record

        mock_write_turn.return_value = MagicMock(id=1)

        # Track DB execute calls to verify the HP update query
        execute_calls = []
        mock_db = AsyncMock()

        async def track_execute(query, params=None):
            query_str = str(query)
            execute_calls.append((query_str, params))

            # Ownership check: character 10 belongs to user 1
            if "user_id FROM characters" in query_str and params and params.get("cid") == 10:
                return _result_with_row(_row(1,))  # user_id = 1

            # Battle type check
            if "battle_type FROM battles" in query_str:
                return _result_with_row(_row("pvp_training",))

            # HP update (the consequence we're testing)
            if "UPDATE character_attributes" in query_str:
                return _result_empty()

            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=track_execute)
        mock_db.commit = AsyncMock()

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

        # The action should succeed (battle finishes)
        assert response.status_code == 200
        data = response.json()
        assert data["battle_finished"] is True

        # Verify the HP update query was executed for the loser (char 20)
        hp_update_calls = [
            (q, p) for q, p in execute_calls
            if "UPDATE character_attributes" in q and "current_health = 1" in q
        ]
        assert len(hp_update_calls) >= 1
        # The loser is character_id 20 (team 1, HP <= 0)
        assert any(p.get("cid") == 20 for _, p in hp_update_calls)

    @patch("main.finish_battle", new_callable=AsyncMock)
    @patch("main.write_turn", new_callable=AsyncMock)
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.character_has_rank", new_callable=AsyncMock, return_value=True)
    @patch("main.get_rank", new_callable=AsyncMock)
    @patch("main.compute_damage_with_rolls", new_callable=AsyncMock, return_value=(999, {}))
    def test_pvp_attack_no_hp_override(
        self, mock_compute, mock_get_rank, mock_has_rank,
        mock_load_state, mock_get_battle, mock_write_turn, mock_finish_battle
    ):
        """After pvp_attack finishes, no special HP override happens."""
        mock_get_rank.return_value = {
            "id": 1, "skill_type": "attack", "damage_type": "physical",
            "base_damage": 50, "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
            "cooldown_turns": 0, "cooldown": 0, "effect_type": None,
            "damage_entries": [{"damage_type": "physical", "base_damage": 50}],
            "effects": [],
        }

        user = _make_user(user_id=1)
        battle_state = _build_battle_state("pvp_attack")
        mock_load_state.return_value = battle_state

        mock_battle_record = MagicMock()
        mock_battle_record.status.value = "in_progress"
        mock_get_battle.return_value = mock_battle_record

        mock_write_turn.return_value = MagicMock(id=1)

        execute_calls = []
        mock_db = AsyncMock()

        async def track_execute(query, params=None):
            query_str = str(query)
            execute_calls.append((query_str, params))

            if "user_id FROM characters" in query_str and params and params.get("cid") == 10:
                return _result_with_row(_row(1,))

            # Battle type is pvp_attack, not pvp_training
            if "battle_type FROM battles" in query_str:
                return _result_with_row(_row("pvp_attack",))

            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=track_execute)
        mock_db.commit = AsyncMock()

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

        # Verify NO HP update to 1 was executed (pvp_attack does not set HP=1)
        hp_update_calls = [
            (q, p) for q, p in execute_calls
            if "UPDATE character_attributes" in q and "current_health = 1" in q
        ]
        assert len(hp_update_calls) == 0

    @patch("main.finish_battle", new_callable=AsyncMock)
    @patch("main.write_turn", new_callable=AsyncMock)
    @patch("main.get_battle", new_callable=AsyncMock)
    @patch("main.load_state", new_callable=AsyncMock)
    @patch("main.character_has_rank", new_callable=AsyncMock, return_value=True)
    @patch("main.get_rank", new_callable=AsyncMock)
    @patch("main.compute_damage_with_rolls", new_callable=AsyncMock, return_value=(999, {}))
    def test_pve_no_hp_override(
        self, mock_compute, mock_get_rank, mock_has_rank,
        mock_load_state, mock_get_battle, mock_write_turn, mock_finish_battle
    ):
        """After PvE battle finishes, no HP=1 override happens."""
        mock_get_rank.return_value = {
            "id": 1, "skill_type": "attack", "damage_type": "physical",
            "base_damage": 50, "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
            "cooldown_turns": 0, "cooldown": 0, "effect_type": None,
            "damage_entries": [{"damage_type": "physical", "base_damage": 50}],
            "effects": [],
        }

        user = _make_user(user_id=1)
        battle_state = _build_battle_state("pve")
        mock_load_state.return_value = battle_state

        mock_battle_record = MagicMock()
        mock_battle_record.status.value = "in_progress"
        mock_get_battle.return_value = mock_battle_record

        mock_write_turn.return_value = MagicMock(id=1)

        execute_calls = []
        mock_db = AsyncMock()

        async def track_execute(query, params=None):
            query_str = str(query)
            execute_calls.append((query_str, params))

            if "user_id FROM characters" in query_str and params and params.get("cid") == 10:
                return _result_with_row(_row(1,))

            # Battle type is pve
            if "battle_type FROM battles" in query_str:
                return _result_with_row(_row("pve",))

            return _result_empty()

        mock_db.execute = AsyncMock(side_effect=track_execute)
        mock_db.commit = AsyncMock()

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

        # Verify NO HP=1 update for PvE
        hp_update_calls = [
            (q, p) for q, p in execute_calls
            if "UPDATE character_attributes" in q and "current_health = 1" in q
        ]
        assert len(hp_update_calls) == 0
