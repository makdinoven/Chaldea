"""
Tests for weapon slot selection in battle-service (FEAT-117, Task 3).

Covers:
  1. fetch_weapons() — returns both weapon slots correctly
  2. fetch_weapons() — handles empty/missing slots
  3. fetch_main_weapon() — backward compatibility wrapper
  4. compute_damage_with_rolls() — weapon_mod from main_weapon
  5. compute_damage_with_rolls() — weapon_mod from additional_weapons
  6. Damage entry with specific weapon_slot + non-"all" damage_type
  7. Damage entry with missing weapon_slot defaults to main_weapon
  8. Damage entry with weapon_slot pointing to empty slot — weapon_mod = 0
"""

import sys
import os
import importlib
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Environment & module-level patches (same approach as test_class_damage_luck.py)
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
skills_mock.character_has_skill = AsyncMock(return_value=True)
skills_mock.get_resolved_skill = AsyncMock(return_value={})
skills_mock.get_item = AsyncMock(return_value={})
skills_mock.character_skills = AsyncMock(return_value=[])

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

# Ensure the real battle_engine module is loaded
if "battle_engine" in sys.modules:
    del sys.modules["battle_engine"]
_be_mod = importlib.import_module("battle_engine")
sys.modules["battle_engine"] = _be_mod

# Verify we got the real module
assert hasattr(_be_mod, "fetch_weapons"), \
    "battle_engine recovery failed: fetch_weapons not found"
assert hasattr(_be_mod, "fetch_main_weapon"), \
    "battle_engine recovery failed: fetch_main_weapon not found"
assert not isinstance(_be_mod.compute_damage_with_rolls, MagicMock), \
    "battle_engine recovery failed: compute_damage_with_rolls is still a mock"

# Save references to real functions
_REAL_fetch_weapons = _be_mod.fetch_weapons
_REAL_fetch_main_weapon = _be_mod.fetch_main_weapon
_REAL_compute_damage_with_rolls = _be_mod.compute_damage_with_rolls


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


def _simple_damage_entry(amount=10, damage_type="physical", chance=100, weapon_slot=None):
    entry = {"damage_type": damage_type, "amount": amount, "chance": chance}
    if weapon_slot is not None:
        entry["weapon_slot"] = weapon_slot
    return entry


def _mock_weapon(damage_modifier=10, primary_damage_type="physical"):
    return {
        "damage_modifier": damage_modifier,
        "primary_damage_type": primary_damage_type,
    }


def _restore_real_engine():
    """Restore real battle_engine functions."""
    _be_mod.fetch_weapons = _REAL_fetch_weapons
    _be_mod.fetch_main_weapon = _REAL_fetch_main_weapon
    _be_mod.compute_damage_with_rolls = _REAL_compute_damage_with_rolls
    sys.modules["battle_engine"] = _be_mod


def _make_equipment_response(main_weapon_item_id=None, additional_weapons_item_id=None):
    """Build a mock equipment response from inventory-service."""
    slots = []
    slots.append({"slot_type": "main_weapon", "item_id": main_weapon_item_id})
    slots.append({"slot_type": "additional_weapons", "item_id": additional_weapons_item_id})
    # Add some non-weapon slots for realism
    slots.append({"slot_type": "head", "item_id": None})
    slots.append({"slot_type": "body", "item_id": None})
    return slots


# ══════════════════════════════════════════════════════════════════════════════
# Test Group 1: fetch_weapons() — returns both weapon slots
# ══════════════════════════════════════════════════════════════════════════════


class TestFetchWeapons:
    """Verify fetch_weapons() returns correct data for both weapon slots."""

    @pytest.mark.asyncio
    async def test_returns_both_slots_when_populated(self):
        """Both main_weapon and additional_weapons are equipped."""
        _restore_real_engine()

        main_item = _mock_weapon(damage_modifier=15, primary_damage_type="physical")
        additional_item = _mock_weapon(damage_modifier=8, primary_damage_type="fire")
        equipment = _make_equipment_response(
            main_weapon_item_id=101,
            additional_weapons_item_id=202,
        )

        mock_responses = {
            "/inventory/42/equipment": equipment,
            "/inventory/items/101": main_item,
            "/inventory/items/202": additional_item,
        }

        async def mock_get(url, **kwargs):
            resp = MagicMock()
            for path, data in mock_responses.items():
                if path in url:
                    resp.json.return_value = data
                    resp.raise_for_status = MagicMock()
                    return resp
            raise ValueError(f"Unexpected URL: {url}")

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("battle_engine.httpx.AsyncClient", return_value=mock_client):
            result = await _REAL_fetch_weapons(42)

        assert result["main_weapon"] == main_item
        assert result["additional_weapons"] == additional_item

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_slots(self):
        """Both weapon slots are empty (item_id is None)."""
        _restore_real_engine()

        equipment = _make_equipment_response(
            main_weapon_item_id=None,
            additional_weapons_item_id=None,
        )

        async def mock_get(url, **kwargs):
            resp = MagicMock()
            for path, data in {"/inventory/42/equipment": equipment}.items():
                if path in url:
                    resp.json.return_value = data
                    resp.raise_for_status = MagicMock()
                    return resp
            raise ValueError(f"Unexpected URL: {url}")

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("battle_engine.httpx.AsyncClient", return_value=mock_client):
            result = await _REAL_fetch_weapons(42)

        assert result["main_weapon"] is None
        assert result["additional_weapons"] is None

    @pytest.mark.asyncio
    async def test_one_slot_empty_one_populated(self):
        """main_weapon occupied, additional_weapons empty."""
        _restore_real_engine()

        main_item = _mock_weapon(damage_modifier=12, primary_damage_type="ice")
        equipment = _make_equipment_response(
            main_weapon_item_id=101,
            additional_weapons_item_id=None,
        )

        mock_responses = {
            "/inventory/42/equipment": equipment,
            "/inventory/items/101": main_item,
        }

        async def mock_get(url, **kwargs):
            resp = MagicMock()
            for path, data in mock_responses.items():
                if path in url:
                    resp.json.return_value = data
                    resp.raise_for_status = MagicMock()
                    return resp
            raise ValueError(f"Unexpected URL: {url}")

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("battle_engine.httpx.AsyncClient", return_value=mock_client):
            result = await _REAL_fetch_weapons(42)

        assert result["main_weapon"] == main_item
        assert result["additional_weapons"] is None


# ══════════════════════════════════════════════════════════════════════════════
# Test Group 2: fetch_main_weapon() — backward compatibility
# ══════════════════════════════════════════════════════════════════════════════


class TestFetchMainWeaponCompat:
    """Verify fetch_main_weapon() is a thin wrapper that returns main_weapon."""

    @pytest.mark.asyncio
    async def test_returns_main_weapon_from_fetch_weapons(self):
        """fetch_main_weapon should return the same as fetch_weapons()['main_weapon']."""
        _restore_real_engine()

        main_item = _mock_weapon(damage_modifier=20, primary_damage_type="physical")
        equipment = _make_equipment_response(
            main_weapon_item_id=101,
            additional_weapons_item_id=202,
        )
        additional_item = _mock_weapon(damage_modifier=5, primary_damage_type="fire")

        mock_responses = {
            "/inventory/99/equipment": equipment,
            "/inventory/items/101": main_item,
            "/inventory/items/202": additional_item,
        }

        async def mock_get(url, **kwargs):
            resp = MagicMock()
            for path, data in mock_responses.items():
                if path in url:
                    resp.json.return_value = data
                    resp.raise_for_status = MagicMock()
                    return resp
            raise ValueError(f"Unexpected URL: {url}")

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("battle_engine.httpx.AsyncClient", return_value=mock_client):
            result = await _REAL_fetch_main_weapon(99)

        assert result == main_item

    @pytest.mark.asyncio
    async def test_returns_none_when_no_main_weapon(self):
        """fetch_main_weapon returns None when main_weapon slot is empty."""
        _restore_real_engine()

        equipment = _make_equipment_response(
            main_weapon_item_id=None,
            additional_weapons_item_id=None,
        )

        async def mock_get(url, **kwargs):
            resp = MagicMock()
            if "/equipment" in url:
                resp.json.return_value = equipment
                resp.raise_for_status = MagicMock()
                return resp
            raise ValueError(f"Unexpected URL: {url}")

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("battle_engine.httpx.AsyncClient", return_value=mock_client):
            result = await _REAL_fetch_main_weapon(99)

        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# Test Group 3: compute_damage_with_rolls — weapon modifier from each slot
# ══════════════════════════════════════════════════════════════════════════════


class TestComputeDamageWeaponSlot:
    """Verify compute_damage_with_rolls uses the correct weapon modifier."""

    @pytest.mark.asyncio
    async def test_main_weapon_damage_modifier(self):
        """Passing a main_weapon dict uses its damage_modifier."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(strength=10)
        defender = _base_defender_attrs()
        weapon = _mock_weapon(damage_modifier=15, primary_damage_type="physical")
        entry = _simple_damage_entry(amount=0, damage_type="physical")

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            final, log = await _REAL_compute_damage_with_rolls(
                entry, attacker, weapon, {}, defender, {}, class_id=1
            )

        # base = strength(10) + damage(5) + weapon(15) = 30
        assert log["base"] == 30
        assert final == 30.0

    @pytest.mark.asyncio
    async def test_additional_weapon_damage_modifier(self):
        """Passing an additional_weapons dict uses its damage_modifier."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(strength=10)
        defender = _base_defender_attrs()
        weapon = _mock_weapon(damage_modifier=7, primary_damage_type="fire")
        entry = _simple_damage_entry(amount=0, damage_type="physical")

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            final, log = await _REAL_compute_damage_with_rolls(
                entry, attacker, weapon, {}, defender, {}, class_id=1
            )

        # base = strength(10) + damage(5) + weapon(7) = 22
        assert log["base"] == 22
        assert final == 22.0

    @pytest.mark.asyncio
    async def test_fire_damage_type_with_main_weapon_modifier(self):
        """damage_type='fire' + weapon_slot='main_weapon': uses main weapon modifier
        but fire resistance applies (not weapon's primary_damage_type)."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(strength=10)
        defender = _base_defender_attrs()
        weapon = _mock_weapon(damage_modifier=10, primary_damage_type="physical")
        entry = _simple_damage_entry(amount=5, damage_type="fire")
        resists = {"fire": 20}  # 20% fire resistance

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            final, log = await _REAL_compute_damage_with_rolls(
                entry, attacker, weapon, {}, defender, resists, class_id=1
            )

        # base = strength(10) + damage(5) + weapon(10) = 25
        # raw = 25 + 5 = 30
        # damage_type = "fire" (from entry, NOT from weapon)
        # resist = 20% on fire => final = 30 * 0.8 = 24.0
        assert log["damage_type"] == "fire"
        assert log["base"] == 25
        assert final == 24.0

    @pytest.mark.asyncio
    async def test_weapon_none_empty_slot_gives_zero_mod(self):
        """When weapon is None (empty slot), weapon_mod = 0."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(strength=10)
        defender = _base_defender_attrs()
        entry = _simple_damage_entry(amount=5, damage_type="physical")

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            final, log = await _REAL_compute_damage_with_rolls(
                entry, attacker, None, {}, defender, {}, class_id=1
            )

        # base = strength(10) + damage(5) + weapon(0) = 15
        # raw = 15 + 5 = 20
        assert log["base"] == 15
        assert final == 20.0

    @pytest.mark.asyncio
    async def test_damage_type_all_with_weapon_uses_weapon_primary_type(self):
        """damage_type='all' uses the weapon's primary_damage_type."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(strength=10)
        defender = _base_defender_attrs()
        weapon = _mock_weapon(damage_modifier=5, primary_damage_type="fire")
        entry = _simple_damage_entry(amount=0, damage_type="all")

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            final, log = await _REAL_compute_damage_with_rolls(
                entry, attacker, weapon, {}, defender, {}, class_id=1
            )

        assert log["damage_type"] == "fire"

    @pytest.mark.asyncio
    async def test_damage_type_all_without_weapon_falls_back_to_physical(self):
        """damage_type='all' with weapon=None falls back to 'physical'."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(strength=10)
        defender = _base_defender_attrs()
        entry = _simple_damage_entry(amount=0, damage_type="all")

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            final, log = await _REAL_compute_damage_with_rolls(
                entry, attacker, None, {}, defender, {}, class_id=1
            )

        assert log["damage_type"] == "physical"


# ══════════════════════════════════════════════════════════════════════════════
# Test Group 4: Integration-style — weapon selection per damage_entry
# ══════════════════════════════════════════════════════════════════════════════


class TestWeaponSelectionPerDamageEntry:
    """Verify that each damage_entry can use a different weapon from its weapon_slot."""

    @pytest.mark.asyncio
    async def test_two_entries_use_different_weapons(self):
        """Two damage entries with different weapon_slots use different weapon modifiers."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(strength=10)
        defender = _base_defender_attrs()

        main_weapon = _mock_weapon(damage_modifier=10, primary_damage_type="physical")
        additional_weapon = _mock_weapon(damage_modifier=5, primary_damage_type="fire")
        weapons = {"main_weapon": main_weapon, "additional_weapons": additional_weapon}

        entry_main = _simple_damage_entry(amount=0, damage_type="physical", weapon_slot="main_weapon")
        entry_additional = _simple_damage_entry(amount=0, damage_type="physical", weapon_slot="additional_weapons")

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            # Simulate what main.py does: select weapon per entry
            weapon_main = weapons.get(entry_main.get("weapon_slot", "main_weapon"))
            final_main, log_main = await _REAL_compute_damage_with_rolls(
                entry_main, attacker, weapon_main, {}, defender, {}, class_id=1
            )

            weapon_additional = weapons.get(entry_additional.get("weapon_slot", "main_weapon"))
            final_additional, log_additional = await _REAL_compute_damage_with_rolls(
                entry_additional, attacker, weapon_additional, {}, defender, {}, class_id=1
            )

        # main: base = 10 + 5 + 10 = 25
        assert log_main["base"] == 25
        assert final_main == 25.0

        # additional: base = 10 + 5 + 5 = 20
        assert log_additional["base"] == 20
        assert final_additional == 20.0

    @pytest.mark.asyncio
    async def test_missing_weapon_slot_defaults_to_main(self):
        """Damage entry without weapon_slot key defaults to main_weapon (backward compat)."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(strength=10)
        defender = _base_defender_attrs()

        main_weapon = _mock_weapon(damage_modifier=10, primary_damage_type="physical")
        additional_weapon = _mock_weapon(damage_modifier=5, primary_damage_type="fire")
        weapons = {"main_weapon": main_weapon, "additional_weapons": additional_weapon}

        # Entry WITHOUT weapon_slot key (old data)
        entry = _simple_damage_entry(amount=0, damage_type="physical")
        assert "weapon_slot" not in entry

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            # Replicate main.py logic: dmg.get("weapon_slot", "main_weapon")
            weapon = weapons.get(entry.get("weapon_slot", "main_weapon"))
            final, log = await _REAL_compute_damage_with_rolls(
                entry, attacker, weapon, {}, defender, {}, class_id=1
            )

        # Should use main_weapon (modifier=10): base = 10 + 5 + 10 = 25
        assert log["base"] == 25
        assert final == 25.0

    @pytest.mark.asyncio
    async def test_weapon_slot_pointing_to_empty_slot(self):
        """Damage entry with weapon_slot='additional_weapons' but that slot is None."""
        _restore_real_engine()
        attacker = _base_attacker_attrs(strength=10)
        defender = _base_defender_attrs()

        main_weapon = _mock_weapon(damage_modifier=10, primary_damage_type="physical")
        weapons = {"main_weapon": main_weapon, "additional_weapons": None}

        entry = _simple_damage_entry(amount=5, damage_type="fire", weapon_slot="additional_weapons")

        with patch.object(_be_mod, "roll_dodge", return_value=False), \
             patch.object(_be_mod, "roll_chance", return_value=True), \
             patch.object(_be_mod, "roll_crit", return_value=False):
            weapon = weapons.get(entry.get("weapon_slot", "main_weapon"))
            assert weapon is None  # additional_weapons slot is empty
            final, log = await _REAL_compute_damage_with_rolls(
                entry, attacker, weapon, {}, defender, {}, class_id=1
            )

        # weapon_mod = 0 (no weapon): base = 10 + 5 + 0 = 15
        # raw = 15 + 5 = 20
        assert log["base"] == 15
        assert final == 20.0
