"""
FEAT-167 — weapon damage is counted exactly once, and the game really has three
different damage numbers.

This file is the regression net for the bug the feature fixes (a weapon's damage
was added both through `character_attributes.damage` and again from the item
template in the engine) and for the model that replaced it:

    base                = <class main attribute> + attrs["damage"]   (no weapon)
    Основной урон       = base + effective_damage(main_weapon)
    Дополнительный урон = base + effective_damage(additional_weapons)
    Урон без оружия     = base

Covered here:
  1. the three values are genuinely DIFFERENT numbers, built from one real
     `fetch_weapons()` call over a real inventory-service payload shape;
  2. the engine never reads the item template's `damage_modifier` any more
     (source-level guard — a re-introduced term breaks the test even if the
     arithmetic happens to agree on some fixture);
  3. `main.py`'s per-entry weapon selection still maps `no_weapon` -> unarmed
     and an unknown/missing slot -> main hand (source-level guard);
  4. a sharpened / gemmed weapon contributes its *effective* value, not the
     template one; a broken weapon contributes 0 but keeps its damage type;
  5. NPCs/mobs go through the very same formula (parity, no separate path);
  6. parity with the frontend profile helper
     (`ProfilePage/StatsTab/damage.ts`) — the profile and the battle log must
     never disagree.
"""

import re
import sys
import os
import importlib
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Environment & module-level patches (same approach as test_weapon_slot.py)
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

# Ensure the real battle_engine module is loaded (other test files replace it
# with a MagicMock during collection).
if "battle_engine" in sys.modules:
    del sys.modules["battle_engine"]
_be_mod = importlib.import_module("battle_engine")
sys.modules["battle_engine"] = _be_mod

assert not isinstance(_be_mod.compute_damage_with_rolls, MagicMock), \
    "battle_engine recovery failed: compute_damage_with_rolls is still a mock"

_REAL_compute_damage_with_rolls = _be_mod.compute_damage_with_rolls
_REAL_fetch_weapons = _be_mod.fetch_weapons

_APP_DIR = os.path.join(os.path.dirname(__file__), "..")
_ENGINE_SOURCE_PATH = os.path.join(_APP_DIR, "battle_engine.py")
_MAIN_SOURCE_PATH = os.path.join(_APP_DIR, "main.py")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _restore_real_engine():
    _be_mod.compute_damage_with_rolls = _REAL_compute_damage_with_rolls
    _be_mod.fetch_weapons = _REAL_fetch_weapons
    sys.modules["battle_engine"] = _be_mod


def _attacker(**overrides):
    """Attacker attributes. `damage` is the BASE — post-FEAT-167 it never
    contains any weapon's damage."""
    attrs = {
        "strength": 35,
        "agility": 10,
        "intelligence": 10,
        "damage": 0,
        "dodge": 0,
        "critical_hit_chance": 0,
        "critical_damage": 125,
        "luck": 0,
    }
    attrs.update(overrides)
    return attrs


def _defender(**overrides):
    attrs = {"dodge": 0, "damage": 0, "critical_hit_chance": 0, "critical_damage": 100}
    attrs.update(overrides)
    return attrs


def _entry(amount=0, damage_type="physical", chance=100, weapon_slot=None):
    entry = {"damage_type": damage_type, "amount": amount, "chance": chance}
    if weapon_slot is not None:
        entry["weapon_slot"] = weapon_slot
    return entry


async def _base_of(attacker, weapon, entry=None, class_id=1):
    """Run the real engine with all rolls pinned and return log["base"]."""
    _restore_real_engine()
    with patch.object(_be_mod, "roll_dodge", return_value=False), \
         patch.object(_be_mod, "roll_chance", return_value=True), \
         patch.object(_be_mod, "roll_crit", return_value=False):
        final, log = await _REAL_compute_damage_with_rolls(
            entry or _entry(), attacker, weapon, {}, _defender(), {}, class_id=class_id
        )
    return final, log


def _equipment_payload(
    main_item_id=101, main_effective=10.0,
    additional_item_id=202, additional_effective=4.0,
):
    """A `GET /inventory/{cid}/equipment` response in the shape inventory-service
    returns it after FEAT-167 (real field names, `effective_damage` per slot)."""
    return [
        {
            "id": 1, "character_id": 7, "slot_type": "main_weapon",
            "item_id": main_item_id, "is_enabled": True,
            "enhancement_points_spent": 0, "enhancement_bonuses": None,
            "socketed_gems": None, "current_durability": None,
            "effective_damage": main_effective,
        },
        {
            "id": 2, "character_id": 7, "slot_type": "additional_weapons",
            "item_id": additional_item_id, "is_enabled": True,
            "enhancement_points_spent": 0, "enhancement_bonuses": None,
            "socketed_gems": None, "current_durability": None,
            "effective_damage": additional_effective,
        },
        {"id": 3, "character_id": 7, "slot_type": "head", "item_id": None,
         "effective_damage": 0.0},
        {"id": 4, "character_id": 7, "slot_type": "body", "item_id": None,
         "effective_damage": 0.0},
    ]


def _patch_inventory(equipment, items):
    """Patch `battle_engine.httpx.AsyncClient` to serve the given equipment
    payload and item templates."""
    async def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "/equipment" in url:
            resp.json.return_value = equipment
            return resp
        for item_id, template in items.items():
            if f"/inventory/items/{item_id}" in url:
                resp.json.return_value = template
                return resp
        raise ValueError(f"Unexpected URL: {url}")

    mock_client = AsyncMock()
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return patch("battle_engine.httpx.AsyncClient", return_value=mock_client)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Three genuinely different numbers, end to end from the inventory payload
# ══════════════════════════════════════════════════════════════════════════════


class TestThreeDamageValues:

    @pytest.mark.asyncio
    async def test_main_offhand_and_unarmed_are_three_different_numbers(self):
        """The user's «Арлекино» case: base 35, a +10 sword in the main hand and
        a +4 dagger in the off hand → 45 / 39 / 35. Three distinct values."""
        _restore_real_engine()
        equipment = _equipment_payload(main_effective=10.0, additional_effective=4.0)
        items = {
            101: {"damage_modifier": 10, "primary_damage_type": "crushing"},
            202: {"damage_modifier": 4, "primary_damage_type": "catting"},
        }

        with _patch_inventory(equipment, items):
            weapons = await _REAL_fetch_weapons(7)

        attacker = _attacker(strength=35, damage=0)

        main_final, main_log = await _base_of(attacker, weapons["main_weapon"])
        off_final, off_log = await _base_of(attacker, weapons["additional_weapons"])
        unarmed_final, unarmed_log = await _base_of(attacker, None)

        assert main_log["base"] == 45
        assert off_log["base"] == 39
        assert unarmed_log["base"] == 35
        # the three values must not collapse into one another
        assert len({main_log["base"], off_log["base"], unarmed_log["base"]}) == 3
        assert main_final == 45.0 and off_final == 39.0 and unarmed_final == 35.0

    @pytest.mark.asyncio
    async def test_weapon_damage_counted_exactly_once(self):
        """main − unarmed is EXACTLY the weapon's effective damage: not twice it
        (the original bug) and not zero (an over-correction)."""
        _restore_real_engine()
        attacker = _attacker(strength=35, damage=0)
        weapon = {"effective_damage": 10.0, "primary_damage_type": "physical"}

        with_weapon, _ = await _base_of(attacker, weapon)
        without, _ = await _base_of(attacker, None)

        assert with_weapon - without == 10.0
        # the historical wrong answer was 55 (35 + 10 + 10)
        assert with_weapon != 55.0

    @pytest.mark.asyncio
    async def test_empty_off_hand_equals_unarmed(self):
        """An empty off hand contributes nothing — «Доп. урон» == «Без оружия»."""
        _restore_real_engine()
        equipment = _equipment_payload(
            additional_item_id=None, additional_effective=0.0
        )
        items = {101: {"damage_modifier": 10, "primary_damage_type": "crushing"}}

        with _patch_inventory(equipment, items):
            weapons = await _REAL_fetch_weapons(7)

        assert weapons["additional_weapons"] is None
        attacker = _attacker(strength=35, damage=0)
        off, _ = await _base_of(attacker, weapons["additional_weapons"])
        unarmed, _ = await _base_of(attacker, None)
        assert off == unarmed == 35.0


# ══════════════════════════════════════════════════════════════════════════════
# 2. Source-level guards — the silent-failure net
# ══════════════════════════════════════════════════════════════════════════════


class TestNoDoubleCountGuards:

    def test_engine_source_never_reads_template_damage_modifier(self):
        """battle-service must not read `damage_modifier` anywhere: that field is
        the item TEMPLATE value, and summing it is exactly the double-count bug.
        Only `effective_damage` (computed by inventory-service) is allowed."""
        with open(_ENGINE_SOURCE_PATH, encoding="utf-8") as fh:
            source = fh.read()
        code = "\n".join(
            line.split("#", 1)[0] for line in source.splitlines()
        )
        assert "damage_modifier" not in code, (
            "battle_engine.py reads `damage_modifier` again — weapon damage is "
            "being counted from the item template, which is the FEAT-167 bug"
        )

    def test_engine_source_has_no_second_damage_formula(self):
        """The dead twin `compute_single_damage_entry` carried a second copy of
        the wrong formula; it was deleted and must not come back."""
        with open(_ENGINE_SOURCE_PATH, encoding="utf-8") as fh:
            source = fh.read()
        assert "compute_single_damage_entry" not in source
        assert not hasattr(_be_mod, "compute_single_damage_entry")
        # exactly one place computes the damage base
        assert source.count('attacker_attr.get("damage"') == 1

    def test_main_still_maps_no_weapon_to_unarmed(self):
        """`main.py` resolves `weapon_slot` per damage entry: `no_weapon` -> None
        (unarmed) and a missing slot -> `main_weapon`. If that selection is lost,
        the three values silently collapse into one."""
        with open(_MAIN_SOURCE_PATH, encoding="utf-8") as fh:
            source = fh.read()
        assert re.search(
            r'if\s+dmg\.get\("weapon_slot"\)\s*==\s*"no_weapon"', source
        ), "main.py no longer maps weapon_slot == 'no_weapon' to unarmed damage"
        assert re.search(
            r'attacker_weapons\.get\(dmg\.get\("weapon_slot",\s*"main_weapon"\)\)',
            source,
        ), "main.py no longer defaults a missing weapon_slot to the main hand"

    @pytest.mark.asyncio
    async def test_attribute_leak_would_be_visible(self):
        """Explicit statement of the invariant: `attrs["damage"]` is BASE-ONLY.
        If inventory-service ever folds a weapon's damage back into the attribute
        (the bug this feature removed at the source), the engine's main-hand base
        exceeds the agreed value — this test is what notices."""
        _restore_real_engine()
        weapon = {"effective_damage": 10.0, "primary_damage_type": "physical"}

        clean, _ = await _base_of(_attacker(strength=35, damage=0), weapon)
        # simulate the leak: the weapon's 10 also sits in the attribute
        leaked, _ = await _base_of(_attacker(strength=35, damage=10), weapon)

        assert clean == 45.0
        assert leaked == 55.0, "sanity: the leak is what produced 55 instead of 45"
        assert leaked != clean


# ══════════════════════════════════════════════════════════════════════════════
# 3. Item state: sharpening, gems, broken weapons
# ══════════════════════════════════════════════════════════════════════════════


class TestWeaponItemState:

    @pytest.mark.asyncio
    async def test_sharpened_and_gemmed_weapon_uses_effective_value(self):
        """A staff with template 500, +5 sharpening and a +12 gem arrives as
        `effective_damage = 517`; the engine must use 517, never the template."""
        _restore_real_engine()
        equipment = _equipment_payload(main_effective=517.0)
        equipment[0]["enhancement_bonuses"] = '{"damage_modifier": 5}'
        equipment[0]["socketed_gems"] = "[404, null]"
        items = {
            101: {"damage_modifier": 500, "primary_damage_type": "magic"},
            202: {"damage_modifier": 4, "primary_damage_type": "catting"},
        }

        with _patch_inventory(equipment, items):
            weapons = await _REAL_fetch_weapons(7)

        assert weapons["main_weapon"]["effective_damage"] == 517.0
        attacker = _attacker(strength=35, damage=0)
        final, log = await _base_of(attacker, weapons["main_weapon"])
        assert log["base"] == 552  # 35 + 0 + 517
        assert final == 552.0

    @pytest.mark.asyncio
    async def test_broken_weapon_adds_nothing_but_keeps_damage_type(self):
        """A broken weapon (durability 0) has `effective_damage = 0.0` but still
        occupies the slot, so `damage_type == "all"` still resolves through its
        `primary_damage_type` and «Осн. урон» equals «Без оружия»."""
        _restore_real_engine()
        equipment = _equipment_payload(main_effective=0.0)
        equipment[0]["current_durability"] = 0
        items = {
            101: {"damage_modifier": 25, "primary_damage_type": "piercing",
                  "max_durability": 60},
            202: {"damage_modifier": 4, "primary_damage_type": "catting"},
        }

        with _patch_inventory(equipment, items):
            weapons = await _REAL_fetch_weapons(7)

        broken = weapons["main_weapon"]
        assert broken is not None, "a broken weapon still occupies its slot"
        assert broken["effective_damage"] == 0.0

        attacker = _attacker(strength=35, damage=0)
        final, log = await _base_of(attacker, broken, _entry(damage_type="all"))
        unarmed, _ = await _base_of(attacker, None, _entry(damage_type="all"))

        assert log["base"] == 35  # template 25 is NOT added
        assert final == unarmed == 35.0
        assert log["damage_type"] == "piercing"  # type survives the breakage

    @pytest.mark.asyncio
    async def test_missing_effective_damage_field_is_zero_not_a_crash(self):
        """Defensive: an older/partial equipment payload without
        `effective_damage` must degrade to 0, never raise."""
        _restore_real_engine()
        weapon = {"primary_damage_type": "physical"}
        final, log = await _base_of(_attacker(strength=35, damage=0), weapon)
        assert log["base"] == 35
        assert final == 35.0


# ══════════════════════════════════════════════════════════════════════════════
# 4. NPC / mob parity
# ══════════════════════════════════════════════════════════════════════════════


class TestNpcParity:

    @pytest.mark.asyncio
    async def test_npc_with_weapon_uses_the_same_formula(self):
        """NPC gear is equipped through the same inventory path and mobs attack
        through the same `compute_damage_with_rolls`, so identical inputs must
        produce identical numbers — there is no separate NPC damage path."""
        _restore_real_engine()
        weapon = {"effective_damage": 12.0, "primary_damage_type": "crushing"}
        player_attrs = _attacker(strength=30, damage=3)
        npc_attrs = _attacker(strength=30, damage=3)

        player_final, player_log = await _base_of(player_attrs, weapon)
        npc_final, npc_log = await _base_of(npc_attrs, weapon)

        assert player_log["base"] == npc_log["base"] == 45  # 30 + 3 + 12
        assert player_final == npc_final

    @pytest.mark.asyncio
    async def test_npc_broken_weapon_also_contributes_zero(self):
        _restore_real_engine()
        broken = {"effective_damage": 0.0, "primary_damage_type": "crushing"}
        npc_attrs = _attacker(strength=30, damage=3)
        final, log = await _base_of(npc_attrs, broken)
        assert log["base"] == 33
        assert final == 33.0


# ══════════════════════════════════════════════════════════════════════════════
# 5. Parity with the frontend profile helper (StatsTab/damage.ts)
# ══════════════════════════════════════════════════════════════════════════════

# Mirror of `computeDamageValues` from
# `services/frontend/app-chaldea/src/components/ProfilePage/StatsTab/damage.ts`.
# It is deliberately a literal transcription: the point of these tests is that
# the profile and the engine agree, and the formula lives in two languages
# (see the feature's §3.1.5 — char-attrs must not call inventory-service).
_CLASS_MAIN_ATTRIBUTE_TS = {1: "strength", 2: "agility", 3: "intelligence"}


def _profile_damage_values(attributes, class_id, equipment):
    main_attr_key = _CLASS_MAIN_ATTRIBUTE_TS.get(class_id) or "strength"
    base = float(attributes.get(main_attr_key) or 0) + float(attributes.get("damage") or 0)

    def weapon_damage(slot_type):
        slot = next((s for s in equipment if s["slot_type"] == slot_type), None)
        return float((slot or {}).get("effective_damage") or 0)

    return {
        "base": base,
        "main": base + weapon_damage("main_weapon"),
        "additional": base + weapon_damage("additional_weapons"),
        "unarmed": base,
    }


class TestProfileParity:

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "class_id, attrs_overrides, main_eff, add_eff",
        [
            (1, {"strength": 35, "damage": 0}, 10.0, 4.0),       # the Арлекино case
            (2, {"agility": 22, "damage": 7}, 3.5, 0.0),         # rogue, fractional
            (3, {"intelligence": 40, "damage": 12}, 517.0, 6.0),  # sharpened staff
            (1, {"strength": 18, "damage": 5}, 0.0, 0.0),        # bare hands
        ],
    )
    async def test_engine_base_equals_profile_value(
        self, class_id, attrs_overrides, main_eff, add_eff
    ):
        """For every slot the engine's `log["base"]` must equal the number the
        profile card shows. A drift here is a user-visible lie."""
        _restore_real_engine()
        attacker = _attacker(**attrs_overrides)
        equipment = _equipment_payload(
            main_effective=main_eff, additional_effective=add_eff
        )
        expected = _profile_damage_values(attacker, class_id, equipment)

        main_weapon = {"effective_damage": main_eff, "primary_damage_type": "physical"}
        off_weapon = {"effective_damage": add_eff, "primary_damage_type": "physical"}

        _, main_log = await _base_of(attacker, main_weapon, class_id=class_id)
        _, off_log = await _base_of(attacker, off_weapon, class_id=class_id)
        _, unarmed_log = await _base_of(attacker, None, class_id=class_id)

        assert main_log["base"] == expected["main"]
        assert off_log["base"] == expected["additional"]
        assert unarmed_log["base"] == expected["unarmed"]
        assert unarmed_log["base"] == expected["base"]

    @pytest.mark.asyncio
    async def test_profile_helper_would_disagree_with_a_third_term(self):
        """Sanity check on the parity test itself: the pre-FEAT-167 profile
        formula (base + attribute + template modifier) gives 55, the engine gives
        45 — so the assertions above genuinely pin the fix, not a tautology."""
        _restore_real_engine()
        attacker = _attacker(strength=35, damage=0)
        weapon = {"effective_damage": 10.0, "damage_modifier": 10,
                  "primary_damage_type": "physical"}
        _, log = await _base_of(attacker, weapon)
        old_profile_value = (
            attacker["strength"] + attacker["damage"]
            + weapon["effective_damage"] + weapon["damage_modifier"]
        )
        assert log["base"] == 45
        assert old_profile_value == 55
