"""
Tests for battle-service class-aware damage + Luck procs (FEAT-075, Task 4.8).

Covers:
  1. compute_damage_with_rolls() with class_id (Warrior/Rogue/Mage/fallback)
  2. Luck bonus on hit chance, crit chance, and effect proc chance
  3. fetch_character_class_id() helper
  4. _filter_effects_by_chance() with luck bonus
"""

import sys
import os
import importlib
from unittest.mock import patch, MagicMock, AsyncMock

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

# Ensure the real battle_engine module is loaded (not a MagicMock from other
# test files that mock it during collection). We MUST use importlib to force
# a fresh load from disk, since `import` uses cached sys.modules entry.
if "battle_engine" in sys.modules:
    del sys.modules["battle_engine"]
_be_mod = importlib.import_module("battle_engine")
sys.modules["battle_engine"] = _be_mod

# Verify we got the real module
assert hasattr(_be_mod, "CLASS_MAIN_ATTRIBUTE"), \
    "battle_engine recovery failed: CLASS_MAIN_ATTRIBUTE not found"
assert not isinstance(_be_mod.compute_damage_with_rolls, MagicMock), \
    "battle_engine recovery failed: compute_damage_with_rolls is still a mock"

# Save references to the REAL functions before other test files can overwrite
# module attributes with mocks.
_REAL_compute_damage_with_rolls = _be_mod.compute_damage_with_rolls
_REAL_roll_dodge = _be_mod.roll_dodge
_REAL_roll_chance = _be_mod.roll_chance
_REAL_roll_crit = _be_mod.roll_crit
_REAL_CLASS_MAIN_ATTRIBUTE = _be_mod.CLASS_MAIN_ATTRIBUTE

# Import main after battle_engine is restored
from main import (  # noqa: E402
    fetch_character_class_id,
    _filter_effects_by_chance,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _base_attacker_attrs(**overrides):
    """Return a base attacker attributes dict with sensible defaults."""
    attrs = {
        "strength": 10,
        "agility": 10,
        "intelligence": 10,
        "damage": 5,
        "dodge": 0,
        "critical_hit_chance": 0,
        "critical_damage": 125,
        "luck": 0,
    }
    attrs.update(overrides)
    return attrs


def _base_defender_attrs(**overrides):
    """Return a base defender attributes dict."""
    attrs = {
        "dodge": 0,
        "damage": 0,
        "critical_hit_chance": 0,
        "critical_damage": 100,
    }
    attrs.update(overrides)
    return attrs


def _simple_damage_entry(amount=10, damage_type="physical", chance=100):
    return {"damage_type": damage_type, "amount": amount, "chance": chance}


def _restore_real_engine():
    """Restore real battle_engine functions on the module (other test files
    may have replaced them with mocks at module level)."""
    _be_mod.compute_damage_with_rolls = _REAL_compute_damage_with_rolls
    _be_mod.roll_dodge = _REAL_roll_dodge
    _be_mod.roll_chance = _REAL_roll_chance
    _be_mod.roll_crit = _REAL_roll_crit
    _be_mod.CLASS_MAIN_ATTRIBUTE = _REAL_CLASS_MAIN_ATTRIBUTE
    sys.modules["battle_engine"] = _be_mod


# ══════════════════════════════════════════════════════════════════════════════
# Test Group 1: CLASS_MAIN_ATTRIBUTE mapping
# ══════════════════════════════════════════════════════════════════════════════


class TestClassMainAttribute:
    """Verify the CLASS_MAIN_ATTRIBUTE constant maps class IDs correctly."""

    def test_warrior_maps_to_strength(self):
        assert _REAL_CLASS_MAIN_ATTRIBUTE[1] == "strength"

    def test_rogue_maps_to_agility(self):
        assert _REAL_CLASS_MAIN_ATTRIBUTE[2] == "agility"

    def test_mage_maps_to_intelligence(self):
        assert _REAL_CLASS_MAIN_ATTRIBUTE[3] == "intelligence"


# ══════════════════════════════════════════════════════════════════════════════
# Test Group 2: compute_damage_with_rolls with class_id
# ══════════════════════════════════════════════════════════════════════════════


class TestComputeDamageClassAware:
    """Verify that compute_damage_with_rolls uses the correct main attribute
    based on class_id for the base damage calculation."""

    @pytest.mark.asyncio
    async def test_warrior_uses_strength(self):
        """class_id=1 (Warrior) should use strength as base stat."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(strength=20, agility=5, intelligence=5)
        defender = _base_defender_attrs()
        entry = _simple_damage_entry(amount=0)

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            final, log = await _REAL_compute_damage_with_rolls(
                entry, attacker, None, {}, defender, {}, class_id=1
            )

        # base = strength(20) + damage(5) + weapon(0) = 25
        assert log["base"] == 25
        assert final == 25.0

    @pytest.mark.asyncio
    async def test_rogue_uses_agility(self):
        """class_id=2 (Rogue) should use agility as base stat."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(strength=5, agility=30, intelligence=5)
        defender = _base_defender_attrs()
        entry = _simple_damage_entry(amount=0)

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            final, log = await _REAL_compute_damage_with_rolls(
                entry, attacker, None, {}, defender, {}, class_id=2
            )

        # base = agility(30) + damage(5) = 35
        assert log["base"] == 35
        assert final == 35.0

    @pytest.mark.asyncio
    async def test_mage_uses_intelligence(self):
        """class_id=3 (Mage) should use intelligence as base stat."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(strength=5, agility=5, intelligence=40)
        defender = _base_defender_attrs()
        entry = _simple_damage_entry(amount=0)

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            final, log = await _REAL_compute_damage_with_rolls(
                entry, attacker, None, {}, defender, {}, class_id=3
            )

        # base = intelligence(40) + damage(5) = 45
        assert log["base"] == 45
        assert final == 45.0

    @pytest.mark.asyncio
    async def test_unknown_class_falls_back_to_strength(self):
        """Unknown class_id should fall back to strength."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(strength=15, agility=50, intelligence=50)
        defender = _base_defender_attrs()
        entry = _simple_damage_entry(amount=0)

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            final, log = await _REAL_compute_damage_with_rolls(
                entry, attacker, None, {}, defender, {}, class_id=99
            )

        # base = strength(15) + damage(5) = 20
        assert log["base"] == 20
        assert final == 20.0

    @pytest.mark.asyncio
    async def test_default_class_id_is_warrior(self):
        """When class_id is not specified, default (1=Warrior) uses strength."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(strength=15, agility=50, intelligence=50)
        defender = _base_defender_attrs()
        entry = _simple_damage_entry(amount=0)

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            final, log = await _REAL_compute_damage_with_rolls(
                entry, attacker, None, {}, defender, {}
            )

        assert log["base"] == 20
        assert final == 20.0

    @pytest.mark.asyncio
    async def test_class_damage_with_weapon(self):
        """Weapon damage modifier is added to class base stat."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(strength=10, agility=25, intelligence=5)
        defender = _base_defender_attrs()
        weapon = {"damage_modifier": 15, "primary_damage_type": "physical"}
        entry = _simple_damage_entry(amount=5)

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            final, log = await _REAL_compute_damage_with_rolls(
                entry, attacker, weapon, {}, defender, {}, class_id=2
            )

        # base = agility(25) + damage(5) + weapon(15) = 45
        # raw = 45 + amount(5) = 50
        assert log["base"] == 45
        assert final == 50.0

    @pytest.mark.asyncio
    async def test_class_damage_with_buffs_and_resists(self):
        """Buffs and resists apply correctly on top of class-based damage."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(strength=5, agility=5, intelligence=20)
        defender = _base_defender_attrs()
        entry = _simple_damage_entry(amount=0, damage_type="fire")
        buffs = {"fire": 20}  # +20% fire damage
        resists = {"fire": 10}  # -10% fire resist

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            final, log = await _REAL_compute_damage_with_rolls(
                entry, attacker, None, buffs, defender, resists, class_id=3
            )

        # base = intelligence(20) + damage(5) = 25
        # raw = 25 + 0 = 25, buff 20% => 30, resist 10% => 27
        assert log["base"] == 25
        assert log["buff_pct"] == 20
        assert log["after_buffs"] == 30.0
        assert final == 27.0


# ══════════════════════════════════════════════════════════════════════════════
# Test Group 3: Luck bonus on offensive procs
# ══════════════════════════════════════════════════════════════════════════════


class TestLuckBonusOnProcs:
    """Verify that luck adds +0.1% per point to hit chance and crit chance."""

    @pytest.mark.asyncio
    async def test_luck_improves_hit_chance(self):
        """With base chance 50% and 100 luck (+10%), total 60% hit chance.
        Patch roll_chance to check the actual chance value passed."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(luck=100)
        defender = _base_defender_attrs()
        entry = _simple_damage_entry(amount=5, chance=50)

        recorded_chances = []

        def _capture_roll_chance(chance_pct):
            recorded_chances.append(chance_pct)
            return True  # always hit

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", side_effect=_capture_roll_chance), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            await _REAL_compute_damage_with_rolls(
                entry, attacker, None, {}, defender, {}, class_id=1
            )

        # hit chance = 50 + (100 * 0.1) = 60
        assert len(recorded_chances) > 0
        assert recorded_chances[0] == pytest.approx(60.0)

    @pytest.mark.asyncio
    async def test_luck_improves_crit_chance(self):
        """Luck adds bonus to crit chance."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(critical_hit_chance=20, luck=50)
        defender = _base_defender_attrs()
        entry = _simple_damage_entry(amount=5, chance=100)

        recorded_crit_chances = []

        def _capture_roll_crit(chance_pct):
            recorded_crit_chances.append(chance_pct)
            return False  # no crit

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", side_effect=_capture_roll_crit):
            await _REAL_compute_damage_with_rolls(
                entry, attacker, None, {}, defender, {}, class_id=1
            )

        # crit chance = 20 + (50 * 0.1) = 25
        assert len(recorded_crit_chances) > 0
        assert recorded_crit_chances[0] == pytest.approx(25.0)

    @pytest.mark.asyncio
    async def test_zero_luck_no_bonus(self):
        """With 0 luck, no bonus is added."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(critical_hit_chance=20, luck=0)
        defender = _base_defender_attrs()
        entry = _simple_damage_entry(amount=5, chance=75)

        recorded_chances = []
        recorded_crits = []

        def _capture_chance(pct):
            recorded_chances.append(pct)
            return True

        def _capture_crit(pct):
            recorded_crits.append(pct)
            return False

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", side_effect=_capture_chance), \
             patch.object(_be_mod, "roll_crit", side_effect=_capture_crit):
            await _REAL_compute_damage_with_rolls(
                entry, attacker, None, {}, defender, {}, class_id=1
            )

        assert recorded_chances[0] == pytest.approx(75.0)
        assert recorded_crits[0] == pytest.approx(20.0)


# ══════════════════════════════════════════════════════════════════════════════
# Test Group 4: _filter_effects_by_chance with luck
# ══════════════════════════════════════════════════════════════════════════════


class TestFilterEffectsByChance:
    """Verify _filter_effects_by_chance applies luck bonus and filters correctly."""

    def test_effects_with_100_chance_always_proc(self):
        """Effects with chance >= 100 always pass, regardless of luck."""
        effects = [
            {"effect_name": "Buff:fire", "chance": 100},
            {"effect_name": "Buff:ice", "chance": 150},
        ]
        result = _filter_effects_by_chance(effects, luck_bonus=0.0)
        assert len(result) == 2

    def test_luck_bonus_pushes_effect_over_100(self):
        """An effect with chance=90 and luck_bonus=15 => 105 >= 100, always procs."""
        effects = [{"effect_name": "Buff:fire", "chance": 90}]
        result = _filter_effects_by_chance(effects, luck_bonus=15.0)
        # actual_chance = 90 + 15 = 105 >= 100 => always procs
        assert len(result) == 1

    def test_zero_chance_zero_luck_never_procs(self):
        """Effect with chance=0 and no luck bonus should never proc."""
        effects = [{"effect_name": "Buff:fire", "chance": 0}]
        with patch("main.roll_chance", return_value=False):
            result = _filter_effects_by_chance(effects, luck_bonus=0.0)
        assert len(result) == 0

    def test_luck_bonus_added_to_roll(self):
        """Verify the actual chance passed to roll_chance includes luck bonus."""
        effects = [{"effect_name": "Debuff:slow", "chance": 40}]
        recorded = []

        def _capture(pct):
            recorded.append(pct)
            return True

        with patch("main.roll_chance", side_effect=_capture):
            result = _filter_effects_by_chance(effects, luck_bonus=5.0)

        assert len(result) == 1
        assert recorded[0] == pytest.approx(45.0)

    def test_multiple_effects_filtered_independently(self):
        """Each effect is rolled independently."""
        effects = [
            {"effect_name": "Buff:str", "chance": 50},
            {"effect_name": "Buff:agi", "chance": 30},
            {"effect_name": "Buff:int", "chance": 100},
        ]
        call_count = [0]

        def _alternating(pct):
            call_count[0] += 1
            return call_count[0] % 2 == 1  # first True, second False

        with patch("main.roll_chance", side_effect=_alternating):
            result = _filter_effects_by_chance(effects, luck_bonus=0.0)

        # Buff:str (chance=50, roll True) => passes
        # Buff:agi (chance=30, roll False) => fails
        # Buff:int (chance=100, >= 100) => always passes (no roll)
        assert len(result) == 2
        assert result[0]["effect_name"] == "Buff:str"
        assert result[1]["effect_name"] == "Buff:int"

    def test_default_chance_is_100(self):
        """If an effect has no 'chance' field, default is 100 (always procs)."""
        effects = [{"effect_name": "Buff:fire"}]
        result = _filter_effects_by_chance(effects, luck_bonus=0.0)
        assert len(result) == 1


# ══════════════════════════════════════════════════════════════════════════════
# Test Group 5: fetch_character_class_id
# ══════════════════════════════════════════════════════════════════════════════


class TestFetchCharacterClassId:
    """Verify fetch_character_class_id returns correct class or default."""

    @pytest.mark.asyncio
    async def test_returns_class_id_from_db(self):
        """When character exists, returns its id_class."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (2,)  # Rogue
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await fetch_character_class_id(mock_db, character_id=42)
        assert result == 2

    @pytest.mark.asyncio
    async def test_returns_warrior_class_for_all_classes(self):
        """Test each class ID is returned correctly."""
        for class_id in [1, 2, 3]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.fetchone.return_value = (class_id,)
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await fetch_character_class_id(mock_db, character_id=1)
            assert result == class_id

    @pytest.mark.asyncio
    async def test_returns_default_when_not_found(self):
        """When character not in DB, returns 1 (Warrior default)."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await fetch_character_class_id(mock_db, character_id=99999)
        assert result == 1

    @pytest.mark.asyncio
    async def test_returns_default_when_class_is_none(self):
        """When character exists but id_class is NULL, returns 1."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (None,)
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await fetch_character_class_id(mock_db, character_id=5)
        assert result == 1

    @pytest.mark.asyncio
    async def test_returns_default_when_class_is_zero(self):
        """When character has id_class=0 (falsy), returns 1."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (0,)
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await fetch_character_class_id(mock_db, character_id=5)
        assert result == 1
