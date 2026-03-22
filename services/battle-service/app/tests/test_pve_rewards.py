"""
Tests for PvE reward distribution and mob AI auto-registration (Tasks #19, #21).

Covers:
1. _distribute_pve_rewards:
   - XP and gold awarded to winner via character-service
   - Loot table rolled correctly (mocked random for deterministic tests)
   - Items added to winner's inventory
   - Active mob status updated to 'dead'
   - Rewards included in response
   - Returns None for non-PvE battles (no mobs)
   - Multiple defeated mobs aggregate rewards

2. Mob AI auto-registration:
   - When PvE battle is created with NPC participant, autobattle-service /internal/register is called
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
from main import app, _distribute_pve_rewards  # noqa: E402
from schemas import BattleRewards, BattleRewardItem  # noqa: E402

# Clear startup handlers to avoid connection attempts
app.router.on_startup.clear()

import pytest  # noqa: E402
import httpx as real_httpx  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_httpx_response(status_code: int, json_data: dict = None):
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = str(json_data)
    return resp


def _make_battle_state(
    participants: dict = None,
    winner_team: int = 0,
):
    """Create a battle state dict for testing."""
    if participants is None:
        participants = {
            "1": {
                "character_id": 10,
                "hp": 100,
                "mana": 50,
                "energy": 50,
                "stamina": 50,
                "team": 0,
                "cooldowns": {},
                "fast_slots": [],
            },
            "2": {
                "character_id": 20,
                "hp": 0,  # defeated
                "mana": 50,
                "energy": 50,
                "stamina": 50,
                "team": 1,
                "cooldowns": {},
                "fast_slots": [],
            },
        }
    return {
        "turn_number": 5,
        "next_actor": 1,
        "first_actor": 1,
        "turn_order": [1, 2],
        "total_turns": 5,
        "last_turn": None,
        "deadline_at": "2026-01-01T00:00:00",
        "participants": participants,
        "active_effects": {},
    }


MOB_REWARD_DATA = {
    "xp_reward": 50,
    "gold_reward": 10,
    "loot_table": [
        {"item_id": 100, "drop_chance": 50.0, "min_quantity": 1, "max_quantity": 3},
        {"item_id": 200, "drop_chance": 10.0, "min_quantity": 1, "max_quantity": 1},
    ],
    "template_name": "Волк",
    "tier": "normal",
}


# ═══════════════════════════════════════════════════════════════════════════
# Tests: _distribute_pve_rewards
# ═══════════════════════════════════════════════════════════════════════════


class TestDistributePveRewards:
    """Tests for the _distribute_pve_rewards function."""

    @pytest.mark.asyncio
    @patch("main.httpx.AsyncClient")
    async def test_xp_and_gold_awarded_to_winner(self, mock_client_cls):
        """XP and gold from defeated mob are sent to character-service."""
        battle_state = _make_battle_state()
        turn_events = []

        # Mock httpx responses
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        # First call: mob-reward-data (mob character 20)
        # Second call: update mob status to dead
        # Third call: add_rewards (winner character 10)
        # Fourth+: add items
        call_responses = [
            _mock_httpx_response(200, MOB_REWARD_DATA),  # mob-reward-data
            _mock_httpx_response(200, {"ok": True}),      # update mob status
            _mock_httpx_response(200, {"ok": True, "new_balance": 110, "new_xp": 250}),  # add_rewards
            _mock_httpx_response(200, {}),  # add item 1
            _mock_httpx_response(200, {}),  # add item 2 (if dropped)
        ]
        mock_client.get = AsyncMock(side_effect=[call_responses[0]])
        mock_client.put = AsyncMock(side_effect=[call_responses[1]])
        mock_client.post = AsyncMock(side_effect=call_responses[2:])

        # Mock random so both items drop
        with patch("main.random.random", return_value=0.05), \
             patch("main.random.randint", return_value=2):
            rewards = await _distribute_pve_rewards(battle_state, 0, turn_events)

        assert rewards is not None
        assert rewards.xp == 50
        assert rewards.gold == 10

        # Verify add_rewards was called
        post_calls = mock_client.post.call_args_list
        assert len(post_calls) >= 1
        # First post call should be add_rewards
        first_post = post_calls[0]
        assert "/add_rewards" in str(first_post)

    @pytest.mark.asyncio
    @patch("main.httpx.AsyncClient")
    async def test_loot_table_rolled_correctly_all_drop(self, mock_client_cls):
        """When random roll < drop_chance, items are added to inventory."""
        battle_state = _make_battle_state()
        turn_events = []

        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_client.get = AsyncMock(return_value=_mock_httpx_response(200, MOB_REWARD_DATA))
        mock_client.put = AsyncMock(return_value=_mock_httpx_response(200, {"ok": True}))
        mock_client.post = AsyncMock(return_value=_mock_httpx_response(200, {}))

        # random() returns 0.01 (1%) — below both 50% and 10% thresholds
        # randint returns 2 for quantity
        with patch("main.random.random", return_value=0.01), \
             patch("main.random.randint", return_value=2):
            rewards = await _distribute_pve_rewards(battle_state, 0, turn_events)

        assert rewards is not None
        assert len(rewards.items) == 2
        item_ids = {i.item_id for i in rewards.items}
        assert item_ids == {100, 200}
        for item in rewards.items:
            assert item.quantity == 2

    @pytest.mark.asyncio
    @patch("main.httpx.AsyncClient")
    async def test_loot_table_no_drops(self, mock_client_cls):
        """When random roll > all drop_chances, no items drop."""
        battle_state = _make_battle_state()
        turn_events = []

        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_client.get = AsyncMock(return_value=_mock_httpx_response(200, MOB_REWARD_DATA))
        mock_client.put = AsyncMock(return_value=_mock_httpx_response(200, {"ok": True}))
        mock_client.post = AsyncMock(return_value=_mock_httpx_response(200, {}))

        # random() returns 0.99 (99%) — above both 50% and 10% thresholds
        with patch("main.random.random", return_value=0.99):
            rewards = await _distribute_pve_rewards(battle_state, 0, turn_events)

        assert rewards is not None
        assert rewards.xp == 50
        assert rewards.gold == 10
        assert len(rewards.items) == 0

    @pytest.mark.asyncio
    @patch("main.httpx.AsyncClient")
    async def test_loot_table_partial_drops(self, mock_client_cls):
        """Only items with roll < drop_chance are dropped."""
        battle_state = _make_battle_state()
        turn_events = []

        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_client.get = AsyncMock(return_value=_mock_httpx_response(200, MOB_REWARD_DATA))
        mock_client.put = AsyncMock(return_value=_mock_httpx_response(200, {"ok": True}))
        mock_client.post = AsyncMock(return_value=_mock_httpx_response(200, {}))

        # random() returns 0.20 (20%) — below 50% but above 10%
        # So item_id=100 (50% chance) drops, item_id=200 (10% chance) does not
        with patch("main.random.random", return_value=0.20), \
             patch("main.random.randint", return_value=1):
            rewards = await _distribute_pve_rewards(battle_state, 0, turn_events)

        assert rewards is not None
        assert len(rewards.items) == 1
        assert rewards.items[0].item_id == 100
        assert rewards.items[0].quantity == 1

    @pytest.mark.asyncio
    @patch("main.httpx.AsyncClient")
    async def test_mob_status_updated_to_dead(self, mock_client_cls):
        """Active mob status is updated to 'dead' via character-service."""
        battle_state = _make_battle_state()
        turn_events = []

        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_client.get = AsyncMock(return_value=_mock_httpx_response(200, MOB_REWARD_DATA))
        mock_client.put = AsyncMock(return_value=_mock_httpx_response(200, {"ok": True}))
        mock_client.post = AsyncMock(return_value=_mock_httpx_response(200, {}))

        with patch("main.random.random", return_value=0.99):
            await _distribute_pve_rewards(battle_state, 0, turn_events)

        # Verify PUT to active-mob-status was called with status "dead"
        put_calls = mock_client.put.call_args_list
        assert len(put_calls) == 1
        call_args = put_calls[0]
        assert "active-mob-status/20" in str(call_args)
        assert call_args.kwargs.get("json", {}).get("status") == "dead" or \
               (len(call_args.args) > 1 or "dead" in str(call_args))

    @pytest.mark.asyncio
    @patch("main.httpx.AsyncClient")
    async def test_rewards_in_turn_events(self, mock_client_cls):
        """Rewards are appended to turn_events."""
        battle_state = _make_battle_state()
        turn_events = []

        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_client.get = AsyncMock(return_value=_mock_httpx_response(200, MOB_REWARD_DATA))
        mock_client.put = AsyncMock(return_value=_mock_httpx_response(200, {"ok": True}))
        mock_client.post = AsyncMock(return_value=_mock_httpx_response(200, {}))

        with patch("main.random.random", return_value=0.99):
            await _distribute_pve_rewards(battle_state, 0, turn_events)

        # Check that pve_rewards event was added
        reward_events = [e for e in turn_events if e.get("event") == "pve_rewards"]
        assert len(reward_events) == 1
        assert reward_events[0]["xp"] == 50
        assert reward_events[0]["gold"] == 10

    @pytest.mark.asyncio
    @patch("main.httpx.AsyncClient")
    async def test_returns_none_for_pvp_battle(self, mock_client_cls):
        """Returns None when no defeated participant is a mob (PvP battle)."""
        battle_state = _make_battle_state()
        turn_events = []

        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        # mob-reward-data returns 404 (not a mob)
        mock_client.get = AsyncMock(return_value=_mock_httpx_response(404))

        rewards = await _distribute_pve_rewards(battle_state, 0, turn_events)

        assert rewards is None

    @pytest.mark.asyncio
    @patch("main.httpx.AsyncClient")
    async def test_multiple_defeated_mobs_aggregate(self, mock_client_cls):
        """Rewards from multiple defeated mobs are aggregated."""
        participants = {
            "1": {
                "character_id": 10, "hp": 100, "mana": 50, "energy": 50,
                "stamina": 50, "team": 0, "cooldowns": {}, "fast_slots": [],
            },
            "2": {
                "character_id": 20, "hp": 0, "mana": 50, "energy": 50,
                "stamina": 50, "team": 1, "cooldowns": {}, "fast_slots": [],
            },
            "3": {
                "character_id": 30, "hp": 0, "mana": 50, "energy": 50,
                "stamina": 50, "team": 1, "cooldowns": {}, "fast_slots": [],
            },
        }
        battle_state = _make_battle_state(participants=participants)
        turn_events = []

        mob_data_1 = {
            "xp_reward": 50, "gold_reward": 10,
            "loot_table": [], "template_name": "Волк", "tier": "normal",
        }
        mob_data_2 = {
            "xp_reward": 100, "gold_reward": 30,
            "loot_table": [], "template_name": "Тролль", "tier": "elite",
        }

        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        # Two mob-reward-data calls return different data
        mock_client.get = AsyncMock(side_effect=[
            _mock_httpx_response(200, mob_data_1),
            _mock_httpx_response(200, mob_data_2),
        ])
        mock_client.put = AsyncMock(return_value=_mock_httpx_response(200, {"ok": True}))
        mock_client.post = AsyncMock(return_value=_mock_httpx_response(200, {}))

        rewards = await _distribute_pve_rewards(battle_state, 0, turn_events)

        assert rewards is not None
        assert rewards.xp == 150  # 50 + 100
        assert rewards.gold == 40  # 10 + 30

    @pytest.mark.asyncio
    @patch("main.httpx.AsyncClient")
    async def test_no_winners_alive_returns_none(self, mock_client_cls):
        """Returns None if no winner characters are alive (edge case)."""
        participants = {
            "1": {
                "character_id": 10, "hp": 0, "mana": 50, "energy": 50,
                "stamina": 50, "team": 0, "cooldowns": {}, "fast_slots": [],
            },
            "2": {
                "character_id": 20, "hp": 0, "mana": 50, "energy": 50,
                "stamina": 50, "team": 1, "cooldowns": {}, "fast_slots": [],
            },
        }
        battle_state = _make_battle_state(participants=participants)
        turn_events = []

        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_client.get = AsyncMock(return_value=_mock_httpx_response(200, MOB_REWARD_DATA))

        rewards = await _distribute_pve_rewards(battle_state, 0, turn_events)

        # Winner team 0 has no alive characters
        assert rewards is None


# ═══════════════════════════════════════════════════════════════════════════
# Tests: Mob AI auto-registration
# ═══════════════════════════════════════════════════════════════════════════


class TestMobAIAutoRegistration:
    """Tests for NPC/mob auto-registration with autobattle-service during battle creation."""

    @patch("main.httpx.AsyncClient")
    @patch("main.save_snapshot", new_callable=AsyncMock)
    @patch("main.cache_snapshot", new_callable=AsyncMock)
    @patch("main.init_battle_state", new_callable=AsyncMock)
    @patch("main.get_redis_client", new_callable=AsyncMock)
    @patch("main.create_battle", new_callable=AsyncMock)
    @patch("main.build_participant_info", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_npc_participant_registered_with_autobattle(
        self,
        mock_auth_get,
        mock_build_info,
        mock_create_battle,
        mock_redis_client,
        mock_init_state,
        mock_cache_snap,
        mock_save_snap,
        mock_httpx_cls,
    ):
        """When a battle includes an NPC participant, it is auto-registered with autobattle-service."""
        from fastapi.testclient import TestClient
        from database import get_db

        # Auth mock
        mock_auth_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "id": 1, "username": "player", "role": "user", "permissions": [],
            }),
        )

        # Mock battle creation
        mock_battle = MagicMock()
        mock_battle.id = 1
        mock_battle.status = "active"

        mock_participant_1 = MagicMock()
        mock_participant_1.id = 1
        mock_participant_1.character_id = 10
        mock_participant_1.team = 0

        mock_participant_2 = MagicMock()
        mock_participant_2.id = 2
        mock_participant_2.character_id = 20
        mock_participant_2.team = 1

        mock_create_battle.return_value = (mock_battle, [mock_participant_1, mock_participant_2])

        # Mock build_participant_info to return valid snapshot data
        def _mock_build(char_id, pid):
            return {
                "participant_id": pid,
                "character_id": char_id,
                "name": "Test",
                "avatar": "/test.jpg",
                "attributes": {
                    "current_health": 100, "current_mana": 50,
                    "current_energy": 50, "current_stamina": 50,
                    "max_health": 100, "max_mana": 50,
                    "max_energy": 50, "max_stamina": 50,
                },
                "skills": [],
                "fast_slots": [],
            }
        mock_build_info.side_effect = _mock_build

        # Redis mock
        mock_rds = AsyncMock()
        mock_rds.zadd = AsyncMock()
        mock_redis_client.return_value = mock_rds

        # Mock httpx client for NPC registration
        mock_client = AsyncMock()
        mock_httpx_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_httpx_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_client.post = AsyncMock(return_value=_mock_httpx_response(200, {"ok": True}))

        # DB mock that returns user_id for ownership check and is_npc for NPC check
        mock_db = AsyncMock()
        call_count = 0

        async def _mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            query_str = str(query)
            if "user_id" in query_str:
                # Ownership check — character 10 belongs to user 1
                if params and params.get("cid") == 10:
                    result.fetchone = MagicMock(return_value=(1,))
                else:
                    result.fetchone = MagicMock(return_value=(999,))
            elif "is_npc" in query_str:
                # NPC check
                if params and params.get("cid") == 20:
                    result.fetchone = MagicMock(return_value=(True,))
                else:
                    result.fetchone = MagicMock(return_value=(False,))
            else:
                result.fetchone = MagicMock(return_value=None)
            return result

        mock_db.execute = AsyncMock(side_effect=_mock_execute)

        async def _fake_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _fake_get_db

        try:
            with TestClient(app) as client:
                response = client.post(
                    "/battles/",
                    json={
                        "players": [
                            {"character_id": 10, "team": 0},
                            {"character_id": 20, "team": 1},
                        ]
                    },
                    headers={"Authorization": "Bearer fake-token"},
                )
                # Battle creation should succeed
                assert response.status_code == 201

                # Verify that httpx.AsyncClient.post was called for autobattle registration
                post_calls = mock_client.post.call_args_list
                register_calls = [
                    c for c in post_calls
                    if "/internal/register" in str(c)
                ]
                assert len(register_calls) == 1, (
                    f"Expected 1 autobattle registration call, got {len(register_calls)}. "
                    f"All post calls: {post_calls}"
                )
        finally:
            app.dependency_overrides.pop(get_db, None)
