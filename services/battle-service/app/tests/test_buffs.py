"""FEAT-168, task #10 — the first dedicated unit tests for `buffs.py`.

`buffs.py` is the whole in-battle effect engine (FEAT-143/146/168) and until now
had **no** test module of its own: `test_dodge_and_freshness.py` touched only the
`fresh` flag, and `test_item_usage.py` replaces the module with a `MagicMock`
outright. Everything here calls the REAL module, with no Redis and no HTTP — the
functions are pure over a plain state dict.

Covered:
  * `_normalize_effect` — attribute_key, aliases, `Buff:`/`Resist:` names, plain names
  * `normalize_source` / `_effect_identity`
  * `apply_new_effects` — instant clamping, enemy inversion, ownership, `fresh`
  * the FEAT-168 stacking rule: SKILL effects (`source=None`) stack independently,
    ITEM effects (`source=("item", id)`) refresh their own record in place
  * `tick_periodic_effects`, `decrement_durations`, `evaluate_control`,
    `first_cycle_limit_skills`, `aggregate_modifiers`, `_expand_complex_effect`,
    `build_percent_*_buffs`
  * `remove_effects` — every selector, `limit`, and the hard engine rule that a
    full skip-turn control is NEVER removed, not even by `selector="all"`
  * legacy state entries written before FEAT-143/168 (no `source`, no `owner_id`,
    no `fresh`)
"""

import importlib.util
import os
import sys
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load a PRIVATE instance of the real module, straight from the file and NOT
# registered in `sys.modules`. `test_item_usage.py` replaces `buffs` with a
# MagicMock (`:34-45`) and, when it finds the real module already imported,
# overwrites its attributes in place — which would silently defeat these tests
# (a mocked `evaluate_control` makes every Stun removable). A private instance is
# immune to that and leaves `sys.modules["buffs"]` exactly as the other modules
# expect it.
_BUFFS_PATH = os.path.join(os.path.dirname(__file__), "..", "buffs.py")
_spec = importlib.util.spec_from_file_location("buffs_under_test", _BUFFS_PATH)
buffs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(buffs)

# Direct references: other modules may re-mock the attributes after collection.
_normalize_effect = buffs._normalize_effect
normalize_source = buffs.normalize_source
_effect_identity = buffs._effect_identity
apply_new_effects = buffs.apply_new_effects
tick_periodic_effects = buffs.tick_periodic_effects
decrement_durations = buffs.decrement_durations
evaluate_control = buffs.evaluate_control
first_cycle_limit_skills = buffs.first_cycle_limit_skills
aggregate_modifiers = buffs.aggregate_modifiers
build_percent_damage_buffs = buffs.build_percent_damage_buffs
build_percent_resist_buffs = buffs.build_percent_resist_buffs
remove_effects = buffs.remove_effects
is_unremovable = buffs.is_unremovable

assert not isinstance(apply_new_effects, MagicMock), "buffs recovery failed"
assert not isinstance(remove_effects, MagicMock), "buffs recovery failed"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _state(**overrides) -> dict:
    """Two participants, full bars, empty effect map."""
    def _part(cid):
        return {
            "character_id": cid, "team": 0,
            "hp": 100, "mana": 50, "energy": 50, "stamina": 50,
            "max_hp": 100, "max_mana": 100, "max_energy": 100, "max_stamina": 100,
            "total_damage_received": 0,
        }
    state = {
        "participants": {"1": _part(10), "2": dict(_part(20), team=1)},
        "active_effects": {},
    }
    state.update(overrides)
    return state


def _row(effect_name, *, attribute_key=None, magnitude=0, duration=1,
         chance=100, target_side="self") -> dict:
    """A raw effect row exactly as skills-service / inventory-service produce it."""
    return {
        "target_side": target_side,
        "effect_name": effect_name,
        "chance": chance,
        "duration": duration,
        "magnitude": magnitude,
        "attribute_key": attribute_key,
    }


def _effects_of(state, pid):
    return state.get("active_effects", {}).get(str(pid), [])


# ══════════════════════════════════════════════════════════════════════════════
# _normalize_effect
# ══════════════════════════════════════════════════════════════════════════════

class TestNormalizeEffect:
    def test_attribute_key_wins_over_name(self):
        eff = _normalize_effect(_row("StatModifier", attribute_key="strength",
                                     magnitude=5, duration=3))
        assert eff == {"name": "StatModifier", "attribute": "strength",
                       "magnitude": 5, "duration": 3}

    def test_crit_chance_alias_is_expanded(self):
        eff = _normalize_effect(_row("StatModifier", attribute_key="crit_chance",
                                     magnitude=7))
        assert eff["attribute"] == "critical_hit_chance"

    def test_buff_all_maps_to_percent_damage(self):
        assert _normalize_effect(_row("Buff:all", magnitude=20))["attribute"] == "percent_damage"

    def test_buff_subtype_maps_to_percent_damage_subtype(self):
        assert _normalize_effect(_row("Buff:fire", magnitude=20))["attribute"] == "percent_damage_fire"

    def test_resist_maps_to_percent_resist(self):
        assert _normalize_effect(_row("Resist:all", magnitude=15))["attribute"] == "percent_resist_all"

    def test_plain_name_is_slugified(self):
        assert _normalize_effect(_row("Armor Break", magnitude=10))["attribute"] == "armor_break"

    def test_unknown_prefix_falls_back_to_slug(self):
        assert _normalize_effect(_row("Weird:thing"))["attribute"] == "weird:thing"


# ══════════════════════════════════════════════════════════════════════════════
# normalize_source / _effect_identity
# ══════════════════════════════════════════════════════════════════════════════

class TestNormalizeSource:
    def test_none_stays_none(self):
        assert normalize_source(None) is None

    def test_tuple_becomes_string(self):
        assert normalize_source(("item", 42)) == "item:42"

    def test_list_becomes_the_same_string_as_the_tuple(self):
        """Redis round-trips JSON, so a tuple comes back as a list — both must
        normalize to the same key or a refresh would silently stop merging."""
        assert normalize_source(["item", 42]) == normalize_source(("item", 42))

    def test_kind_is_lowercased(self):
        assert normalize_source(("ITEM", 7)) == "item:7"

    def test_ready_string_passes_through(self):
        assert normalize_source("item:42") == "item:42"

    def test_blank_string_is_none(self):
        assert normalize_source("   ") is None

    def test_empty_part_is_none(self):
        assert normalize_source(("item", "")) is None

    def test_wrong_arity_raises(self):
        with pytest.raises(ValueError):
            normalize_source(("item", 1, 2))

    def test_wrong_type_raises(self):
        with pytest.raises(TypeError):
            normalize_source(42)


class TestEffectIdentity:
    def test_no_source_means_no_identity(self):
        """Skill effects have no source ⇒ they can never merge."""
        assert _effect_identity({"name": "Bleeding", "attribute": "bleeding"}, 1) is None

    def test_identity_includes_source_name_attribute_owner(self):
        eff = {"source": "item:42", "name": "Poison", "attribute": "periodic_damage",
               "owner_id": 1}
        assert _effect_identity(eff, 2) == ("item:42", "poison", "periodic_damage", 1)

    def test_owner_defaults_to_the_list_owner_for_legacy_records(self):
        eff = {"source": "item:42", "name": "Poison", "attribute": "periodic_damage"}
        assert _effect_identity(eff, 2)[3] == 2


# ══════════════════════════════════════════════════════════════════════════════
# apply_new_effects — instant values
# ══════════════════════════════════════════════════════════════════════════════

class TestApplyInstantValues:
    def test_hp_is_restored_and_clamped_to_max(self):
        state = _state()
        state["participants"]["1"]["hp"] = 80
        apply_new_effects(state, 1, [_row("Heal", attribute_key="hp", magnitude=50)])
        assert state["participants"]["1"]["hp"] == 100
        assert _effects_of(state, 1) == [], "instant values must not become active effects"

    def test_hp_never_goes_below_zero(self):
        state = _state()
        state["participants"]["1"]["hp"] = 10
        apply_new_effects(state, 1, [_row("Hit", attribute_key="hp", magnitude=-999)])
        assert state["participants"]["1"]["hp"] == 0

    def test_positive_instant_on_an_enemy_is_inverted_into_damage(self):
        """A heal row aimed at an enemy must hurt, not heal (is_enemy=True)."""
        state = _state()
        apply_new_effects(state, 2, [_row("Splash", attribute_key="hp", magnitude=30,
                                          target_side="enemy")], is_enemy=True)
        assert state["participants"]["2"]["hp"] == 70

    def test_negative_instant_on_an_enemy_is_not_double_inverted(self):
        state = _state()
        apply_new_effects(state, 2, [_row("Splash", attribute_key="hp", magnitude=-30,
                                          target_side="enemy")], is_enemy=True)
        assert state["participants"]["2"]["hp"] == 70

    @pytest.mark.parametrize("attribute", ["mana", "energy", "stamina"])
    def test_other_resources_are_clamped_too(self, attribute):
        state = _state()
        apply_new_effects(state, 1, [_row("Refill", attribute_key=attribute, magnitude=999)])
        assert state["participants"]["1"][attribute] == 100


# ══════════════════════════════════════════════════════════════════════════════
# apply_new_effects — durable effects, ownership, freshness
# ══════════════════════════════════════════════════════════════════════════════

class TestApplyDurableEffects:
    def test_effect_is_appended_with_owner_and_fresh(self):
        state = _state()
        apply_new_effects(state, 2, [_row("Bleeding", magnitude=5, duration=3,
                                          target_side="enemy")],
                          is_enemy=True, owner_pid=1)
        eff, = _effects_of(state, 2)
        assert eff["name"] == "Bleeding"
        assert eff["attribute"] == "bleeding"
        assert eff["magnitude"] == 5
        assert eff["duration"] == 3
        assert eff["owner_id"] == 1
        assert eff["fresh"] is True
        assert "source" not in eff, "a skill effect carries no source"

    def test_owner_defaults_to_the_target_when_not_given(self):
        state = _state()
        apply_new_effects(state, 2, [_row("Bleeding", magnitude=5, duration=3)])
        assert _effects_of(state, 2)[0]["owner_id"] == 2

    def test_active_effects_map_is_created_on_demand(self):
        state = {"participants": _state()["participants"]}
        apply_new_effects(state, 1, [_row("Holy", magnitude=3, duration=2)])
        assert state["active_effects"]["1"][0]["name"] == "Holy"

    def test_item_effect_stores_the_normalized_source(self):
        state = _state()
        apply_new_effects(state, 1, [_row("StatModifier", attribute_key="strength",
                                          magnitude=5, duration=3)],
                          owner_pid=1, source=("item", 42))
        assert _effects_of(state, 1)[0]["source"] == "item:42"


# ══════════════════════════════════════════════════════════════════════════════
# FEAT-168 stacking rule — skills stack, items refresh
# ══════════════════════════════════════════════════════════════════════════════

class TestSkillEffectsStackIndependently:
    """§3.6 Addendum 2 (user decision): a 2-turn/5 bleed and a 3-turn/10 bleed
    applied by skills must tick side by side as two independent records."""

    def test_two_bleeds_from_skills_are_two_records(self):
        state = _state()
        apply_new_effects(state, 2, [_row("Bleeding", magnitude=5, duration=2)],
                          is_enemy=True, owner_pid=1)
        apply_new_effects(state, 2, [_row("Bleeding", magnitude=10, duration=3)],
                          is_enemy=True, owner_pid=1)
        effects = _effects_of(state, 2)
        assert len(effects) == 2
        assert sorted((e["magnitude"], e["duration"]) for e in effects) == [(5, 2), (10, 3)]

    def test_both_bleeds_tick_separately_in_the_same_turn(self):
        state = _state()
        apply_new_effects(state, 2, [_row("Bleeding", magnitude=5, duration=2)],
                          is_enemy=True, owner_pid=1)
        apply_new_effects(state, 2, [_row("Bleeding", magnitude=10, duration=3)],
                          is_enemy=True, owner_pid=1)
        decrement_durations(state, 1)          # cast turn — clears `fresh`
        events = tick_periodic_effects(state, 1)
        assert len(events) == 2, "each bleed must tick on its own"
        assert sorted(e["amount"] for e in events) == [5, 10]
        assert state["participants"]["2"]["hp"] == 100 - 15

    def test_stacked_magnitudes_are_summed_by_aggregate_modifiers(self):
        state = _state()
        for _ in range(3):
            apply_new_effects(state, 1, [_row("StatModifier", attribute_key="strength",
                                              magnitude=5, duration=3)], owner_pid=1)
        assert aggregate_modifiers(_effects_of(state, 1)) == {"strength": 15}


class TestItemEffectsRefreshInPlace:
    """§3.6 Addendum 1+2: re-using the SAME item refreshes its own record —
    duration = max(old, new), magnitude = new, `fresh` NOT reset."""

    def _apply(self, state, *, item_id=42, magnitude=5, duration=3, pid=1):
        apply_new_effects(state, pid, [_row("StatModifier", attribute_key="strength",
                                            magnitude=magnitude, duration=duration)],
                          owner_pid=1, source=("item", item_id))

    def test_same_item_twice_is_one_record(self):
        state = _state()
        self._apply(state, magnitude=5, duration=3)
        self._apply(state, magnitude=7, duration=2)
        assert len(_effects_of(state, 1)) == 1

    def test_duration_is_the_max_not_the_sum(self):
        state = _state()
        self._apply(state, duration=3)
        self._apply(state, duration=2)
        assert _effects_of(state, 1)[0]["duration"] == 3
        self._apply(state, duration=6)
        assert _effects_of(state, 1)[0]["duration"] == 6

    def test_magnitude_is_the_new_value_not_the_sum(self):
        state = _state()
        self._apply(state, magnitude=5)
        self._apply(state, magnitude=7)
        assert _effects_of(state, 1)[0]["magnitude"] == 7

    def test_refresh_does_not_reset_fresh(self):
        """Addendum 1: re-setting `fresh` would cost a topped-up poison one tick
        of damage. `fresh` is written only for a genuinely new record."""
        state = _state()
        apply_new_effects(state, 2, [_row("Poison", attribute_key="periodic_damage",
                                          magnitude=6, duration=3)],
                          is_enemy=True, owner_pid=1, source=("item", 91))
        decrement_durations(state, 1)                       # cast turn clears `fresh`
        assert not _effects_of(state, 2)[0].get("fresh")
        apply_new_effects(state, 2, [_row("Poison", attribute_key="periodic_damage",
                                          magnitude=8, duration=3)],
                          is_enemy=True, owner_pid=1, source=("item", 91))
        assert not _effects_of(state, 2)[0].get("fresh"), \
            "a refreshed DoT must keep ticking, not skip a turn"
        events = tick_periodic_effects(state, 1)
        assert [e["amount"] for e in events] == [8]

    def test_two_casters_of_the_same_item_keep_separate_records(self):
        """`owner_id` is part of the merge key, so two players throwing the same
        flask at the same victim each get their own record, ticking on their own
        turns."""
        state = _state()
        apply_new_effects(state, 2, [_row("Bleeding", magnitude=5, duration=2)],
                          is_enemy=True, owner_pid=1, source=("item", 42))
        apply_new_effects(state, 2, [_row("Bleeding", magnitude=9, duration=2)],
                          is_enemy=True, owner_pid=3, source=("item", 42))
        effects = _effects_of(state, 2)
        assert len(effects) == 2
        assert sorted(e["owner_id"] for e in effects) == [1, 3]

    def test_a_different_item_gets_its_own_record(self):
        state = _state()
        self._apply(state, item_id=42, magnitude=5)
        self._apply(state, item_id=43, magnitude=9)
        effects = _effects_of(state, 1)
        assert len(effects) == 2
        assert {e["source"] for e in effects} == {"item:42", "item:43"}

    def test_an_identically_named_skill_effect_is_never_touched(self):
        state = _state()
        apply_new_effects(state, 1, [_row("StatModifier", attribute_key="strength",
                                          magnitude=100, duration=9)], owner_pid=1)
        self._apply(state, magnitude=5, duration=3)
        self._apply(state, magnitude=6, duration=3)
        effects = _effects_of(state, 1)
        assert len(effects) == 2
        skill_eff = next(e for e in effects if "source" not in e)
        assert (skill_eff["magnitude"], skill_eff["duration"]) == (100, 9)

    def test_the_same_item_on_a_different_owner_does_not_merge(self):
        state = _state()
        apply_new_effects(state, 1, [_row("StatModifier", attribute_key="strength",
                                          magnitude=5, duration=3)],
                          owner_pid=1, source=("item", 42))
        apply_new_effects(state, 1, [_row("StatModifier", attribute_key="strength",
                                          magnitude=5, duration=3)],
                          owner_pid=2, source=("item", 42))
        assert len(_effects_of(state, 1)) == 2

    def test_a_list_source_from_redis_still_merges(self):
        """The state is JSON in Redis: a tuple comes back as a list."""
        state = _state()
        apply_new_effects(state, 1, [_row("StatModifier", attribute_key="strength",
                                          magnitude=5, duration=3)],
                          owner_pid=1, source=("item", 42))
        apply_new_effects(state, 1, [_row("StatModifier", attribute_key="strength",
                                          magnitude=8, duration=3)],
                          owner_pid=1, source=["item", 42])
        assert len(_effects_of(state, 1)) == 1
        assert _effects_of(state, 1)[0]["magnitude"] == 8


# ══════════════════════════════════════════════════════════════════════════════
# tick_periodic_effects
# ══════════════════════════════════════════════════════════════════════════════

class TestTickPeriodicEffects:
    def _bleed(self, state, *, name="Bleeding", attribute_key=None, magnitude=7,
               duration=3, owner=1, target=2):
        apply_new_effects(state, target,
                          [_row(name, attribute_key=attribute_key,
                                magnitude=magnitude, duration=duration)],
                          is_enemy=True, owner_pid=owner)

    def test_fresh_effect_does_not_tick_on_the_cast_turn(self):
        state = _state()
        self._bleed(state)
        assert tick_periodic_effects(state, 1) == []
        assert state["participants"]["2"]["hp"] == 100

    def test_bleed_ticks_on_the_owner_turn(self):
        state = _state()
        self._bleed(state, magnitude=7)
        decrement_durations(state, 1)
        events = tick_periodic_effects(state, 1)
        assert events[0]["event"] == "effect_tick"
        assert events[0]["target"] == 2
        assert events[0]["source"] == 1
        assert events[0]["amount"] == 7
        assert state["participants"]["2"]["hp"] == 93
        assert state["participants"]["2"]["total_damage_received"] == 7

    def test_dot_does_not_tick_on_the_victim_turn(self):
        """Ownership model: a DoT decays and ticks on its CASTER's turn."""
        state = _state()
        self._bleed(state)
        decrement_durations(state, 1)
        assert tick_periodic_effects(state, 2) == []
        assert state["participants"]["2"]["hp"] == 100

    def test_burn_is_periodic_damage(self):
        state = _state()
        self._bleed(state, name="Burn", magnitude=4)
        decrement_durations(state, 1)
        assert tick_periodic_effects(state, 1)[0]["amount"] == 4

    def test_poison_ticks_only_with_the_periodic_damage_subtype(self):
        state = _state()
        self._bleed(state, name="Poison", attribute_key="periodic_damage", magnitude=6)
        decrement_durations(state, 1)
        assert tick_periodic_effects(state, 1)[0]["amount"] == 6

    def test_paralysis_poison_deals_no_periodic_damage(self):
        state = _state()
        self._bleed(state, name="Poison", attribute_key="paralysis", magnitude=6)
        decrement_durations(state, 1)
        assert tick_periodic_effects(state, 1) == []

    def test_stat_effects_never_tick(self):
        state = _state()
        self._bleed(state, name="StatModifier", attribute_key="strength", magnitude=5)
        decrement_durations(state, 1)
        assert tick_periodic_effects(state, 1) == []

    def test_damage_is_clamped_at_zero_hp(self):
        state = _state()
        state["participants"]["2"]["hp"] = 3
        self._bleed(state, magnitude=50)
        decrement_durations(state, 1)
        events = tick_periodic_effects(state, 1)
        assert state["participants"]["2"]["hp"] == 0
        assert events[0]["amount"] == 3

    def test_a_corpse_does_not_tick(self):
        state = _state()
        self._bleed(state)
        decrement_durations(state, 1)
        state["participants"]["2"]["hp"] = 0
        assert tick_periodic_effects(state, 1) == []

    def test_zero_magnitude_produces_no_event(self):
        state = _state()
        self._bleed(state, magnitude=0)
        decrement_durations(state, 1)
        assert tick_periodic_effects(state, 1) == []

    def test_legacy_record_without_owner_or_fresh_ticks_for_its_list_owner(self):
        """Pre-FEAT-143 Redis state: no `owner_id`, no `fresh`."""
        state = _state()
        state["active_effects"]["2"] = [
            {"name": "Bleeding", "attribute": "bleeding", "magnitude": 6, "duration": 2}
        ]
        assert tick_periodic_effects(state, 1) == [], "owner defaults to the list owner"
        events = tick_periodic_effects(state, 2)
        assert events[0]["amount"] == 6


# ══════════════════════════════════════════════════════════════════════════════
# decrement_durations
# ══════════════════════════════════════════════════════════════════════════════

class TestDecrementDurations:
    def test_only_the_owners_effects_tick(self):
        state = _state()
        apply_new_effects(state, 2, [_row("Bleeding", magnitude=5, duration=3)],
                          is_enemy=True, owner_pid=1)
        decrement_durations(state, 1)   # cast turn — clears fresh
        decrement_durations(state, 2)   # victim's turn — must not tick
        assert _effects_of(state, 2)[0]["duration"] == 3
        decrement_durations(state, 1)
        assert _effects_of(state, 2)[0]["duration"] == 2

    def test_effect_is_dropped_at_zero(self):
        state = _state()
        apply_new_effects(state, 1, [_row("Holy", magnitude=3, duration=1)], owner_pid=1)
        decrement_durations(state, 1)   # cast turn
        decrement_durations(state, 1)   # 1 → 0, removed
        assert _effects_of(state, 1) == []

    def test_none_ticks_everyone(self):
        state = _state()
        state["active_effects"]["2"] = [
            {"name": "Bleeding", "attribute": "bleeding", "magnitude": 5, "duration": 3}
        ]
        decrement_durations(state)
        assert _effects_of(state, 2)[0]["duration"] == 2

    def test_legacy_record_without_fresh_ticks_immediately(self):
        state = _state()
        state["active_effects"]["1"] = [
            {"name": "Holy", "attribute": "holy", "magnitude": 3, "duration": 2}
        ]
        decrement_durations(state, 1)
        assert _effects_of(state, 1)[0]["duration"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# evaluate_control / first_cycle_limit_skills
# ══════════════════════════════════════════════════════════════════════════════

class TestEvaluateControl:
    def test_no_effects_means_no_control(self):
        assert evaluate_control([]) == (None, set())
        assert evaluate_control(None) == (None, set())

    def test_stun_is_a_full_skip(self):
        full, blocked = evaluate_control([{"name": "Stun", "attribute": "stun"}])
        assert full == "Stun"
        assert blocked == set()

    def test_poison_paralysis_is_a_full_skip(self):
        full, _ = evaluate_control([{"name": "Poison", "attribute": "paralysis"}])
        assert full == "Poison"

    def test_periodic_poison_is_not_a_control(self):
        full, blocked = evaluate_control(
            [{"name": "Poison", "attribute": "periodic_damage"}])
        assert full is None and blocked == set()

    @pytest.mark.parametrize("name", ["Knockdown", "Windburn"])
    @pytest.mark.parametrize("attr", ["attack", "defense", "support"])
    def test_partial_controls_block_one_skill_type(self, name, attr):
        full, blocked = evaluate_control([{"name": name, "attribute": attr}])
        assert full is None
        assert blocked == {attr}

    def test_knockdown_with_an_unknown_attribute_blocks_nothing(self):
        assert evaluate_control([{"name": "Knockdown", "attribute": "strength"}]) == (None, set())


class TestFirstCycleLimit:
    def test_attack_wins_over_the_rest(self):
        assert first_cycle_limit_skills(1, 2, 3) == (1, None, None)

    def test_defense_wins_when_no_attack(self):
        assert first_cycle_limit_skills(None, 2, 3) == (None, 2, None)

    def test_nothing_selected_stays_empty(self):
        assert first_cycle_limit_skills(None, None, None) == (None, None, None)


# ══════════════════════════════════════════════════════════════════════════════
# aggregate_modifiers / complex effects / percent builders
# ══════════════════════════════════════════════════════════════════════════════

class TestAggregateModifiers:
    def test_plain_attributes_are_summed(self):
        mods = aggregate_modifiers([
            {"name": "StatModifier", "attribute": "strength", "magnitude": 5},
            {"name": "StatModifier", "attribute": "strength", "magnitude": -2},
            {"name": "StatModifier", "attribute": "agility", "magnitude": 3},
        ])
        assert mods == {"strength": 3, "agility": 3}

    def test_armorbreak_lowers_every_physical_resist(self):
        mods = aggregate_modifiers([{"name": "ArmorBreak", "attribute": "armorbreak",
                                     "magnitude": 10}])
        assert mods == {"percent_resist_physical": -10, "percent_resist_catting": -10,
                        "percent_resist_crushing": -10, "percent_resist_piercing": -10}

    def test_holy_and_curse_are_mirror_images(self):
        holy = aggregate_modifiers([{"name": "Holy", "attribute": "holy", "magnitude": 4}])
        curse = aggregate_modifiers([{"name": "Curse", "attribute": "curse", "magnitude": 4}])
        assert holy == {"strength": 4, "agility": 4, "intelligence": 4, "endurance": 4}
        assert curse == {k: -v for k, v in holy.items()}

    def test_daze_lowers_outgoing_damage(self):
        assert aggregate_modifiers([{"name": "Daze", "attribute": "daze",
                                     "magnitude": 15}]) == {"percent_damage_all": -15}

    def test_negative_magnitude_is_still_a_debuff(self):
        """Complex effects take |magnitude| — direction is baked into the map."""
        assert aggregate_modifiers([{"name": "Freeze", "attribute": "freeze",
                                     "magnitude": -12}]) == {"percent_resist_all": -12}


class TestPercentBuilders:
    def test_damage_builder_splits_all_and_subtypes(self):
        out = build_percent_damage_buffs({"percent_damage": 10, "percent_damage_fire": 5,
                                          "strength": 3})
        assert out == {"all": 10, "fire": 5}

    def test_resist_builder_splits_all_and_subtypes(self):
        out = build_percent_resist_buffs({"percent_resist": 8, "percent_resist_fire": -4,
                                          "agility": 1})
        assert out == {"all": 8, "fire": -4}


# ══════════════════════════════════════════════════════════════════════════════
# remove_effects — selectors, limit, and the unremovable rule
# ══════════════════════════════════════════════════════════════════════════════

def _cleanse_state():
    """One victim (pid 1) carrying a representative mix of effects."""
    return {
        "participants": _state()["participants"],
        "active_effects": {
            "1": [
                {"name": "Bleeding", "attribute": "bleeding", "magnitude": 5,
                 "duration": 3, "owner_id": 2},
                {"name": "Curse", "attribute": "curse", "magnitude": 4,
                 "duration": 2, "owner_id": 2},
                {"name": "Knockdown", "attribute": "attack", "magnitude": 1,
                 "duration": 1, "owner_id": 2},
                {"name": "Stun", "attribute": "stun", "magnitude": 1,
                 "duration": 2, "owner_id": 2},
                {"name": "StatModifier", "attribute": "strength", "magnitude": 5,
                 "duration": 3, "owner_id": 1},
            ]
        },
    }


def _names(effects):
    return sorted(e["name"] for e in effects)


class TestIsUnremovable:
    def test_stun_is_unremovable(self):
        assert is_unremovable({"name": "Stun", "attribute": "stun"}) is True

    def test_paralysis_poison_is_unremovable(self):
        assert is_unremovable({"name": "Poison", "attribute": "paralysis"}) is True

    def test_periodic_poison_is_removable(self):
        assert is_unremovable({"name": "Poison", "attribute": "periodic_damage"}) is False

    def test_knockdown_is_removable(self):
        assert is_unremovable({"name": "Knockdown", "attribute": "attack"}) is False


class TestRemoveEffectsSelectors:
    def test_debuff_removes_everything_owned_by_someone_else(self):
        state = _cleanse_state()
        removed = remove_effects(state, 1, selector="debuff")
        assert _names(removed) == ["Bleeding", "Curse", "Knockdown"]
        assert _names(_effects_of(state, 1)) == ["StatModifier", "Stun"]

    def test_empty_selector_defaults_to_debuff(self):
        state = _cleanse_state()
        assert _names(remove_effects(state, 1, selector="")) == ["Bleeding", "Curse", "Knockdown"]

    def test_none_selector_defaults_to_debuff(self):
        state = _cleanse_state()
        assert _names(remove_effects(state, 1, selector=None)) == ["Bleeding", "Curse", "Knockdown"]

    def test_periodic_damage_removes_only_dots(self):
        state = _cleanse_state()
        state["active_effects"]["1"].append(
            {"name": "Poison", "attribute": "periodic_damage", "magnitude": 6,
             "duration": 3, "owner_id": 2})
        removed = remove_effects(state, 1, selector="periodic_damage")
        assert _names(removed) == ["Bleeding", "Poison"]

    def test_control_partial_removes_knockdown_but_not_stun(self):
        state = _cleanse_state()
        removed = remove_effects(state, 1, selector="control_partial")
        assert _names(removed) == ["Knockdown"]
        assert "Stun" in _names(_effects_of(state, 1))

    def test_stat_down_removes_only_negative_contributions(self):
        state = _cleanse_state()
        removed = remove_effects(state, 1, selector="stat_down")
        assert _names(removed) == ["Curse"]
        kept = _names(_effects_of(state, 1))
        assert "StatModifier" in kept, "a positive buff is not a stat_down"

    def test_stat_down_catches_a_negative_stat_modifier(self):
        state = _cleanse_state()
        state["active_effects"]["1"] = [
            {"name": "StatModifier", "attribute": "strength", "magnitude": -5,
             "duration": 3, "owner_id": 2}
        ]
        assert _names(remove_effects(state, 1, selector="stat_down")) == ["StatModifier"]

    def test_selector_by_effect_name_is_case_insensitive(self):
        state = _cleanse_state()
        assert _names(remove_effects(state, 1, selector="bleeding")) == ["Bleeding"]

    def test_selector_by_normalized_attribute_also_matches(self):
        state = _cleanse_state()
        assert _names(remove_effects(state, 1, selector="curse")) == ["Curse"]

    def test_unknown_selector_removes_nothing(self):
        state = _cleanse_state()
        assert remove_effects(state, 1, selector="nonexistent") == []
        assert len(_effects_of(state, 1)) == 5

    def test_all_removes_own_buffs_too(self):
        state = _cleanse_state()
        removed = remove_effects(state, 1, selector="all")
        assert _names(removed) == ["Bleeding", "Curse", "Knockdown", "StatModifier"]

    def test_empty_participant_returns_empty_list(self):
        state = _cleanse_state()
        assert remove_effects(state, 2, selector="all") == []

    def test_state_without_active_effects_is_safe(self):
        assert remove_effects({"participants": {}}, 1, selector="all") == []


class TestRemoveEffectsNeverRemovesFullSkipControl:
    """Engine rule, not an item setting (§3.2): a full skip-turn control can
    never be cleansed, whatever the admin configures — including `all`."""

    @pytest.mark.parametrize("selector", ["all", "debuff", "stun", "Stun",
                                          "control_partial", "stat_down",
                                          "periodic_damage", ""])
    def test_stun_survives_every_selector(self, selector):
        state = _cleanse_state()
        removed = remove_effects(state, 1, selector=selector)
        assert "Stun" not in _names(removed)
        assert "Stun" in _names(_effects_of(state, 1))

    @pytest.mark.parametrize("selector", ["all", "debuff", "poison"])
    def test_paralysis_poison_survives_every_selector(self, selector):
        state = _cleanse_state()
        state["active_effects"]["1"].append(
            {"name": "Poison", "attribute": "paralysis", "magnitude": 1,
             "duration": 2, "owner_id": 2})
        removed = remove_effects(state, 1, selector=selector)
        assert not any(e["attribute"] == "paralysis" for e in removed)
        assert any(e["attribute"] == "paralysis" for e in _effects_of(state, 1))

    def test_a_stun_still_stops_the_turn_after_a_full_cleanse(self):
        """End-to-end of the rule: cleanse everything, the actor is still stunned."""
        state = _cleanse_state()
        remove_effects(state, 1, selector="all")
        full_skip, _ = evaluate_control(_effects_of(state, 1))
        assert full_skip == "Stun"


class TestRemoveEffectsLimit:
    def test_limit_removes_the_oldest_matching_records_only(self):
        state = _cleanse_state()
        removed = remove_effects(state, 1, selector="debuff", limit=1)
        assert _names(removed) == ["Bleeding"]
        assert len(_effects_of(state, 1)) == 4

    def test_limit_zero_removes_all_matching(self):
        state = _cleanse_state()
        assert len(remove_effects(state, 1, selector="debuff", limit=0)) == 3

    def test_negative_limit_behaves_like_zero(self):
        state = _cleanse_state()
        assert len(remove_effects(state, 1, selector="debuff", limit=-3)) == 3

    def test_limit_larger_than_the_list_is_fine(self):
        state = _cleanse_state()
        assert len(remove_effects(state, 1, selector="debuff", limit=99)) == 3

    def test_an_unremovable_control_does_not_consume_the_limit(self):
        state = _cleanse_state()
        state["active_effects"]["1"].insert(
            0, {"name": "Stun", "attribute": "stun", "magnitude": 1,
                "duration": 2, "owner_id": 2})
        removed = remove_effects(state, 1, selector="debuff", limit=2)
        assert _names(removed) == ["Bleeding", "Curse"]


class TestRemoveEffectsLegacyRecords:
    """Records written before FEAT-143/168 carry no owner_id / fresh / source."""

    def _legacy(self):
        return {
            "participants": _state()["participants"],
            "active_effects": {
                "1": [
                    {"name": "Bleeding", "attribute": "bleeding",
                     "magnitude": 5, "duration": 3},
                    {"name": "Stun", "attribute": "stun",
                     "magnitude": 1, "duration": 2},
                ]
            },
        }

    def test_legacy_record_counts_as_self_owned_for_the_debuff_selector(self):
        state = self._legacy()
        assert remove_effects(state, 1, selector="debuff") == []

    def test_legacy_record_is_removable_by_name(self):
        state = self._legacy()
        assert _names(remove_effects(state, 1, selector="Bleeding")) == ["Bleeding"]

    def test_legacy_stun_is_still_unremovable_by_all(self):
        state = self._legacy()
        removed = remove_effects(state, 1, selector="all")
        assert _names(removed) == ["Bleeding"]
        assert _names(_effects_of(state, 1)) == ["Stun"]

    def test_record_without_an_attribute_does_not_crash_stat_down(self):
        state = {
            "participants": _state()["participants"],
            "active_effects": {"1": [{"name": "Curse", "magnitude": 4, "duration": 2}]},
        }
        assert _names(remove_effects(state, 1, selector="stat_down")) == ["Curse"]

    def test_list_is_left_untouched_when_nothing_matches(self):
        state = self._legacy()
        before = state["active_effects"]["1"]
        remove_effects(state, 1, selector="nonexistent")
        assert state["active_effects"]["1"] is before
