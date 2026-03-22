"""
Tests for Russian error messages in battle-service (FEAT-062, Task #4).

Verifies that:
1. _ensure_not_on_cooldown raises HTTPException with Russian message + cooldown count
2. _pay_skill_costs raises HTTPException with Russian resource names
3. Error messages do NOT contain raw English text or internal IDs
"""

import sys
import os
from unittest.mock import MagicMock, AsyncMock

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Environment & module-level patches (same approach as test_battle_fixes.py)
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
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

# Configure redis_state mock (required for main import)
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

# Configure mongo_helpers
mongo_mock = sys.modules["mongo_helpers"]
mongo_mock.save_snapshot = AsyncMock()
mongo_mock.load_snapshot = AsyncMock(return_value=None)

# Configure inventory_client
inv_mock = sys.modules["inventory_client"]
inv_mock.get_fast_slots = AsyncMock(return_value=[])

# Configure character_client
char_mock = sys.modules["character_client"]
char_mock.get_character_profile = AsyncMock(return_value={
    "character_name": "Test",
    "character_photo": "",
})

# Now import the functions under test
from main import _ensure_not_on_cooldown, _pay_skill_costs, app  # noqa: E402

# Clear startup handlers to avoid real connections
app.router.on_startup.clear()

from fastapi import HTTPException  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_participant_state(
    energy: int = 100,
    mana: int = 100,
    stamina: int = 100,
    cooldowns: dict | None = None,
):
    return {
        "energy": energy,
        "mana": mana,
        "stamina": stamina,
        "cooldowns": cooldowns or {},
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tests for _ensure_not_on_cooldown
# ──────────────────────────────────────────────────────────────────────────────

class TestEnsureNotOnCooldown:
    """Tests for _ensure_not_on_cooldown() Russian error messages."""

    def test_raises_on_cooldown_with_russian_message(self):
        """Error message must contain 'перезарядке' when skill is on cooldown."""
        state = {
            "participants": {
                "1": _make_participant_state(cooldowns={"42": 3}),
            }
        }
        with pytest.raises(HTTPException) as exc_info:
            _ensure_not_on_cooldown(state, pid=1, rank_ids=[42])

        assert exc_info.value.status_code == 400
        assert "перезарядке" in exc_info.value.detail

    def test_cooldown_message_contains_remaining_turns(self):
        """Error message must include the number of remaining cooldown turns."""
        state = {
            "participants": {
                "1": _make_participant_state(cooldowns={"99": 5}),
            }
        }
        with pytest.raises(HTTPException) as exc_info:
            _ensure_not_on_cooldown(state, pid=1, rank_ids=[99])

        assert "5" in exc_info.value.detail

    def test_cooldown_message_no_english(self):
        """Error message must NOT contain English words like 'cooldown' or 'Rank'."""
        state = {
            "participants": {
                "1": _make_participant_state(cooldowns={"10": 2}),
            }
        }
        with pytest.raises(HTTPException) as exc_info:
            _ensure_not_on_cooldown(state, pid=1, rank_ids=[10])

        detail = exc_info.value.detail.lower()
        assert "cooldown" not in detail
        assert "rank" not in detail

    def test_cooldown_message_no_raw_rank_id(self):
        """Error message should not expose the raw rank_id to users."""
        rank_id = 777
        state = {
            "participants": {
                "1": _make_participant_state(cooldowns={str(rank_id): 1}),
            }
        }
        with pytest.raises(HTTPException) as exc_info:
            _ensure_not_on_cooldown(state, pid=1, rank_ids=[rank_id])

        # The rank_id 777 should not appear in the message
        # (remaining turns = 1, which is fine)
        detail = exc_info.value.detail
        assert str(rank_id) not in detail

    def test_no_error_when_not_on_cooldown(self):
        """No exception when cooldown is 0 or absent."""
        state = {
            "participants": {
                "1": _make_participant_state(cooldowns={"42": 0}),
            }
        }
        # Should not raise
        _ensure_not_on_cooldown(state, pid=1, rank_ids=[42])

    def test_no_error_when_no_cooldowns(self):
        """No exception when skill has no cooldown entry at all."""
        state = {
            "participants": {
                "1": _make_participant_state(cooldowns={}),
            }
        }
        _ensure_not_on_cooldown(state, pid=1, rank_ids=[42])


# ──────────────────────────────────────────────────────────────────────────────
# Tests for _pay_skill_costs
# ──────────────────────────────────────────────────────────────────────────────

class TestPaySkillCosts:
    """Tests for _pay_skill_costs() Russian error messages."""

    @pytest.mark.asyncio
    async def test_insufficient_energy_russian_message(self):
        """Error for insufficient energy must use Russian resource name."""
        state = {
            "participants": {
                "1": _make_participant_state(energy=5, mana=100, stamina=100),
            }
        }
        ranks = [{"cost_energy": 20, "cost_mana": 0, "cost_stamina": 0}]

        with pytest.raises(HTTPException) as exc_info:
            await _pay_skill_costs(state, pid=1, ranks=ranks)

        assert exc_info.value.status_code == 400
        assert "энергии" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_insufficient_mana_russian_message(self):
        """Error for insufficient mana must use Russian resource name."""
        state = {
            "participants": {
                "1": _make_participant_state(energy=100, mana=3, stamina=100),
            }
        }
        ranks = [{"cost_energy": 0, "cost_mana": 50, "cost_stamina": 0}]

        with pytest.raises(HTTPException) as exc_info:
            await _pay_skill_costs(state, pid=1, ranks=ranks)

        assert exc_info.value.status_code == 400
        assert "маны" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_insufficient_stamina_russian_message(self):
        """Error for insufficient stamina must use Russian resource name."""
        state = {
            "participants": {
                "1": _make_participant_state(energy=100, mana=100, stamina=2),
            }
        }
        ranks = [{"cost_energy": 0, "cost_mana": 0, "cost_stamina": 10}]

        with pytest.raises(HTTPException) as exc_info:
            await _pay_skill_costs(state, pid=1, ranks=ranks)

        assert exc_info.value.status_code == 400
        assert "выносливости" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_cost_message_contains_required_and_current(self):
        """Error message must include both the required and current amounts."""
        state = {
            "participants": {
                "1": _make_participant_state(energy=100, mana=7, stamina=100),
            }
        }
        ranks = [{"cost_energy": 0, "cost_mana": 30, "cost_stamina": 0}]

        with pytest.raises(HTTPException) as exc_info:
            await _pay_skill_costs(state, pid=1, ranks=ranks)

        detail = exc_info.value.detail
        # Must contain "нужно 30" and "есть 7"
        assert "30" in detail
        assert "7" in detail

    @pytest.mark.asyncio
    async def test_cost_message_no_english(self):
        """Error message must NOT contain English resource names."""
        state = {
            "participants": {
                "1": _make_participant_state(energy=0, mana=100, stamina=100),
            }
        }
        ranks = [{"cost_energy": 10, "cost_mana": 0, "cost_stamina": 0}]

        with pytest.raises(HTTPException) as exc_info:
            await _pay_skill_costs(state, pid=1, ranks=ranks)

        detail = exc_info.value.detail.lower()
        assert "not enough" not in detail
        assert "energy" not in detail
        assert "mana" not in detail
        assert "stamina" not in detail

    @pytest.mark.asyncio
    async def test_cost_message_uses_nedostatochno(self):
        """Error message must start with 'Недостаточно'."""
        state = {
            "participants": {
                "1": _make_participant_state(energy=100, mana=0, stamina=100),
            }
        }
        ranks = [{"cost_energy": 0, "cost_mana": 15, "cost_stamina": 0}]

        with pytest.raises(HTTPException) as exc_info:
            await _pay_skill_costs(state, pid=1, ranks=ranks)

        assert exc_info.value.detail.startswith("Недостаточно")

    @pytest.mark.asyncio
    async def test_successful_cost_deduction(self):
        """When resources are sufficient, costs are deducted and spend dict returned."""
        state = {
            "participants": {
                "1": _make_participant_state(energy=50, mana=50, stamina=50),
            }
        }
        ranks = [{"cost_energy": 10, "cost_mana": 20, "cost_stamina": 5}]

        spend = await _pay_skill_costs(state, pid=1, ranks=ranks)

        assert spend == {"energy": 10, "mana": 20, "stamina": 5}
        pstate = state["participants"]["1"]
        assert pstate["energy"] == 40
        assert pstate["mana"] == 30
        assert pstate["stamina"] == 45

    @pytest.mark.asyncio
    async def test_multiple_ranks_cumulative_cost(self):
        """Costs from multiple ranks should be summed before checking."""
        state = {
            "participants": {
                "1": _make_participant_state(energy=15, mana=100, stamina=100),
            }
        }
        ranks = [
            {"cost_energy": 8, "cost_mana": 0, "cost_stamina": 0},
            {"cost_energy": 8, "cost_mana": 0, "cost_stamina": 0},
        ]
        # Total energy needed = 16, have = 15 → should fail
        with pytest.raises(HTTPException) as exc_info:
            await _pay_skill_costs(state, pid=1, ranks=ranks)

        assert exc_info.value.status_code == 400
        assert "энергии" in exc_info.value.detail
