"""FEAT-143 combat fixes:

1. Dodge is a single roll for the whole attack — `compute_damage_with_rolls`
   can skip its internal dodge roll (`apply_dodge=False`) so the caller rolls it
   once and never logs "dodged" next to a landed hit.
2. A freshly-applied effect does NOT tick on the turn it was cast, so its
   remaining duration matches the log line that applied it.
"""

import sys
import os
import importlib
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Recover the REAL modules — other test files replace them with MagicMocks (or
# monkeypatch their functions) via sys.modules during collection.
for _mod in ("battle_engine", "buffs"):
    if _mod in sys.modules:
        del sys.modules[_mod]
battle_engine = importlib.import_module("battle_engine")
buffs = importlib.import_module("buffs")

# Save DIRECT references to the real functions. Other test files re-mock module
# attributes at collection time, so we call these saved refs (not the possibly
# re-mocked module attributes) at run time — same pattern as test_weapon_slot.
_REAL_compute = battle_engine.compute_damage_with_rolls
_REAL_decrement = buffs.decrement_durations
_REAL_apply = buffs.apply_new_effects
_REAL_tick = buffs.tick_periodic_effects
_REAL_aggregate = buffs.aggregate_modifiers
_REAL_control = buffs.evaluate_control

assert not isinstance(_REAL_compute, MagicMock)
assert not isinstance(_REAL_decrement, MagicMock)


def _attacker():
    return {
        "strength": 20, "damage": 0, "luck": 0,
        "critical_hit_chance": 0, "critical_damage": 100,
    }


# --- Dodge is per-attack ---------------------------------------------------

class TestApplyDodgeFlag:
    @pytest.mark.asyncio
    async def test_apply_dodge_false_skips_dodge_even_at_100(self):
        """With apply_dodge=False the entry lands regardless of dodge stat."""
        with patch.object(battle_engine, "roll_dodge", return_value=True):
            dealt, log = await _REAL_compute(
                damage_entry={"damage_type": "physical", "amount": 10, "chance": 100},
                attacker_attr=_attacker(),
                weapon=None,
                percent_buffs={},
                defender_attr={"dodge": 100},
                percent_resists={},
                class_id=1,
                apply_dodge=False,
            )
        assert dealt == 30  # (20 strength + 10 amount)
        assert "dodged" not in log

    @pytest.mark.asyncio
    async def test_apply_dodge_true_still_dodges(self):
        """Default behaviour (apply_dodge=True) still rolls and honours a dodge."""
        with patch.object(battle_engine, "roll_dodge", return_value=True):
            dealt, log = await _REAL_compute(
                damage_entry={"damage_type": "physical", "amount": 10, "chance": 100},
                attacker_attr=_attacker(),
                weapon=None,
                percent_buffs={},
                defender_attr={"dodge": 100},
                percent_resists={},
                class_id=1,
            )
        assert dealt == 0.0
        assert log["dodged"] is True


# --- Fresh effects don't tick on the cast turn -----------------------------

def _state_with_effect(fresh):
    eff = {
        "name": "Bleeding", "attribute": "bleeding",
        "magnitude": 20, "duration": 3, "owner_id": 1,
    }
    if fresh:
        eff["fresh"] = True
    return {"active_effects": {"2": [eff]}}


class TestEffectFreshness:
    def test_fresh_effect_not_ticked_on_cast_turn(self):
        state = _state_with_effect(fresh=True)
        # Owner (1) ends their casting turn — the fresh effect must NOT decrement.
        _REAL_decrement(state, participant_id=1)
        eff = state["active_effects"]["2"][0]
        assert eff["duration"] == 3
        assert not eff.get("fresh")  # flag cleared

    def test_effect_ticks_on_subsequent_owner_turns(self):
        state = _state_with_effect(fresh=True)
        _REAL_decrement(state, participant_id=1)  # cast turn — no tick
        _REAL_decrement(state, participant_id=1)  # next owner turn — tick
        assert state["active_effects"]["2"][0]["duration"] == 2

    def test_non_fresh_effect_ticks_immediately(self):
        state = _state_with_effect(fresh=False)
        _REAL_decrement(state, participant_id=1)
        assert state["active_effects"]["2"][0]["duration"] == 2

    def test_fresh_flag_added_on_apply(self):
        state = {"participants": {"2": {"hp": 100, "max_hp": 100}}, "active_effects": {}}
        rows = [{"effect_name": "Bleeding", "magnitude": 20, "duration": 3, "attribute_key": None}]
        _REAL_apply(state, pid=2, raw_effect_rows=rows, is_enemy=True, owner_pid=1)
        eff = state["active_effects"]["2"][0]
        assert eff.get("fresh") is True
        assert eff["duration"] == 3


# --- Periodic damage (DoT) -------------------------------------------------

def _dot_state(name, attribute, magnitude=20, hp=100, fresh=False, owner=1):
    eff = {"name": name, "attribute": attribute, "magnitude": magnitude,
           "duration": 3, "owner_id": owner}
    if fresh:
        eff["fresh"] = True
    return {"participants": {"2": {"hp": hp, "max_hp": 100}},
            "active_effects": {"2": [eff]}}


class TestPeriodicDamage:
    def test_bleeding_ticks_damage(self):
        state = _dot_state("Bleeding", "bleeding", magnitude=20)
        events = _REAL_tick(state, participant_id=1)
        assert state["participants"]["2"]["hp"] == 80
        assert len(events) == 1
        assert events[0]["event"] == "effect_tick"
        assert events[0]["amount"] == 20
        assert events[0]["target"] == 2

    def test_fresh_dot_does_not_tick(self):
        state = _dot_state("Bleeding", "bleeding", fresh=True)
        events = _REAL_tick(state, participant_id=1)
        assert state["participants"]["2"]["hp"] == 100
        assert events == []

    def test_periodic_poison_ticks_but_stat_poison_does_not(self):
        periodic = _dot_state("Poison", "periodic_damage")
        assert _REAL_tick(periodic, participant_id=1)[0]["amount"] == 20
        stat = _dot_state("Poison", "stat_reduction")
        assert _REAL_tick(stat, participant_id=1) == []

    def test_dot_does_not_overkill_below_zero(self):
        state = _dot_state("Bleeding", "bleeding", magnitude=50, hp=30)
        events = _REAL_tick(state, participant_id=1)
        assert state["participants"]["2"]["hp"] == 0
        assert events[0]["amount"] == 30  # only the HP that remained

    def test_only_owner_effects_tick(self):
        state = _dot_state("Bleeding", "bleeding", owner=1)
        # A different participant's turn — the effect owned by 1 must not tick.
        events = _REAL_tick(state, participant_id=99)
        assert state["participants"]["2"]["hp"] == 100
        assert events == []


# --- Complex modifiers (group A) -------------------------------------------

def _eff(name, attribute="", magnitude=20):
    return {"name": name, "attribute": attribute, "magnitude": magnitude}


class TestComplexModifiers:
    def test_freeze_reduces_all_resist(self):
        mods = _REAL_aggregate([_eff("Freeze", "freeze", 15)])
        assert mods["percent_resist_all"] == -15

    def test_armorbreak_reduces_physical_resists(self):
        mods = _REAL_aggregate([_eff("ArmorBreak", "armorbreak", 20)])
        for t in ("physical", "catting", "crushing", "piercing"):
            assert mods[f"percent_resist_{t}"] == -20

    def test_daze_reduces_outgoing_damage(self):
        mods = _REAL_aggregate([_eff("Daze", "daze", 10)])
        assert mods["percent_damage_all"] == -10

    def test_wet_reduces_magic_damage(self):
        mods = _REAL_aggregate([_eff("Wet", "wet", 30)])
        assert mods["percent_damage_magic"] == -30

    def test_holy_buffs_all_primary_attrs(self):
        mods = _REAL_aggregate([_eff("Holy", "holy", 5)])
        for a in ("strength", "agility", "intelligence", "endurance"):
            assert mods[a] == 5

    def test_curse_debuffs_all_primary_attrs(self):
        mods = _REAL_aggregate([_eff("Curse", "curse", 5)])
        for a in ("strength", "agility", "intelligence", "endurance"):
            assert mods[a] == -5

    def test_magnitude_sign_ignored_for_directional_effects(self):
        # Whether the author entered +20 or −20, ArmorBreak always reduces resist.
        assert _REAL_aggregate([_eff("Freeze", "freeze", -15)])["percent_resist_all"] == -15

    def test_plain_stat_modifier_passes_through(self):
        mods = _REAL_aggregate([_eff("StatModifier", "critical_hit_chance", 7)])
        assert mods["critical_hit_chance"] == 7

    def test_damage_buff_passes_through(self):
        mods = _REAL_aggregate([_eff("Buff: fire", "percent_damage_fire", 25)])
        assert mods["percent_damage_fire"] == 25


# --- Control effects (group B) ---------------------------------------------

class TestControlEffects:
    def test_stun_skips_whole_turn(self):
        skip, blocked = _REAL_control([_eff("Stun", "stun")])
        assert skip == "Stun"
        assert blocked == set()

    def test_poison_paralysis_skips_turn(self):
        skip, _ = _REAL_control([_eff("Poison", "paralysis")])
        assert skip == "Poison"

    def test_periodic_poison_is_not_control(self):
        skip, blocked = _REAL_control([_eff("Poison", "periodic_damage")])
        assert skip is None
        assert blocked == set()

    def test_knockdown_blocks_its_skill_type(self):
        skip, blocked = _REAL_control([_eff("Knockdown", "attack")])
        assert skip is None
        assert blocked == {"attack"}

    def test_windburn_blocks_support(self):
        _, blocked = _REAL_control([_eff("Windburn", "support")])
        assert blocked == {"support"}

    def test_no_control_effects(self):
        skip, blocked = _REAL_control([_eff("Bleeding", "bleeding"), _eff("Holy", "holy")])
        assert skip is None
        assert blocked == set()

    def test_multiple_blocks_accumulate(self):
        _, blocked = _REAL_control([_eff("Knockdown", "attack"), _eff("Windburn", "defense")])
        assert blocked == {"attack", "defense"}
