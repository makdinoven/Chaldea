"""
FEAT-168 §3.8 — the autobattle item picker values effect items.

Before this feature ``value(slot)`` looked only at resource recovery, so a
damage scroll, a buff potion, a weapon poison or an antidote scored exactly 0
and the autobattle could never pick one. The extended scoring must:

  * value damage rows, self/ally buffs, enemy debuffs and weapon coatings;
  * score a coating slot at 0 while the participant already carries an active
    ``weapon_coating`` (battle-service would reject it and the turn's single
    item would be wasted);
  * score a cleanse item only when the participant actually carries a
    *removable* effect — an unremovable full-skip control does not count;
  * keep a legacy recovery-only slot scoring **exactly** as it did before, and
    read every new key with a default so a pre-deploy battle snapshot is
    unaffected.

``value()`` is a closure inside ``_pick_best``, so it is exercised through the
picker: the chosen ``item_id`` (and ``None`` when nothing scores above 0).
"""

import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Other test modules inject a MagicMock for `strategy` into sys.modules.
if "strategy" in sys.modules and isinstance(sys.modules["strategy"], MagicMock):
    del sys.modules["strategy"]

import strategy as strategy_mod
from strategy import Strategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _avail(*slots):
    return {"skills": {}, "fast_slots": list(slots)}


def _feats(hp=1.0, mana=1.0, energy=1.0):
    return {"hp_ratio": hp, "mana_ratio": mana, "energy_ratio": energy}


def _actor(pid=1, weapon_coating=None, active_effects=None):
    return {
        "pid": pid,
        "weapon_coating": weapon_coating,
        "active_effects": active_effects or [],
    }


def _plain(item_id, quantity=1, **extra):
    """A slot with no recovery and no new keys — scores only the quantity bonus."""
    slot = {"item_id": item_id, "quantity": quantity}
    slot.update(extra)
    return slot


def _pick(slots, feats=None, actor=None):
    s = Strategy()
    result = s._pick_best({}, _avail(*slots), feats or _feats(), actor or _actor())
    return result["item_id"]


# ═══════════════════════════════════════════════════════════════════════════
# A) Effect items are now selectable at all
# ═══════════════════════════════════════════════════════════════════════════

class TestEffectItemsBeatPlainSlots:
    def test_damage_scroll_beats_a_plain_slot(self):
        scroll = _plain(10, quantity=1, damage_entries=[{"amount": 40, "chance": 100}])
        plain = _plain(20, quantity=5)
        assert _pick([plain, scroll]) == 10

    def test_damage_row_chance_is_ignored(self):
        """battle-service does NOT roll `chance` on item damage rows — the damage
        always applies, only dodge and resists matter (docs/services/
        battle-service.md). So the picker must not discount by chance either:
        a 25 %-chance 40-damage scroll (24.0) beats a 100 %-chance 20-damage
        one (12.0)."""
        risky = _plain(10, damage_entries=[{"amount": 40, "chance": 25}])   # 24.0
        safe = _plain(20, damage_entries=[{"amount": 20, "chance": 100}])   # 12.0
        assert _pick([risky, safe]) == 10

    def test_missing_chance_changes_nothing(self):
        no_chance = _plain(10, damage_entries=[{"amount": 30}])             # 18.0
        low = _plain(20, damage_entries=[{"amount": 10, "chance": 100}])    # 6.0
        assert _pick([low, no_chance]) == 10

    def test_buff_potion_beats_a_plain_slot(self):
        potion = _plain(10, effects=[{
            "effect_name": "Сила", "target_side": "self",
            "magnitude": 5, "duration": 3,
        }])
        plain = _plain(20, quantity=5)
        assert _pick([plain, potion]) == 10

    def test_buff_potion_is_selected_at_all(self):
        """Regression for the original bug: a pure buff item scored 0 → never picked."""
        potion = _plain(10, quantity=0, effects=[{
            "effect_name": "Сила", "target_side": "self",
            "magnitude": 5, "duration": 3,
        }])
        assert _pick([potion]) == 10

    def test_enemy_debuff_is_valued_lower_than_the_same_self_buff(self):
        buff = _plain(10, quantity=0, effects=[{
            "effect_name": "Сила", "target_side": "self",
            "magnitude": 10, "duration": 2,
        }])
        debuff = _plain(20, quantity=0, effects=[{
            "effect_name": "Слабость", "target_side": "enemy",
            "magnitude": -10, "duration": 2,
        }])
        assert strategy_mod.BUFF_WEIGHT > strategy_mod.DEBUFF_WEIGHT
        assert _pick([debuff, buff]) == 10

    def test_negative_magnitude_still_counts_as_value(self):
        """A debuff's magnitude is negative; its |value| is what matters."""
        debuff = _plain(10, quantity=0, effects=[{
            "effect_name": "Слабость", "target_side": "enemy",
            "magnitude": -20, "duration": 3,
        }])
        assert _pick([debuff]) == 10

    def test_instant_effect_counts_as_one_turn(self):
        instant = _plain(10, quantity=0, effects=[{
            "effect_name": "Сила", "target_side": "self",
            "magnitude": 10, "duration": 0,
        }])
        assert _pick([instant]) == 10

    def test_unknown_target_side_is_ignored(self):
        weird = _plain(10, quantity=0, effects=[{
            "effect_name": "Странность", "target_side": "weather",
            "magnitude": 99, "duration": 9,
        }])
        assert _pick([weird]) is None

    def test_garbage_rows_do_not_crash_the_picker(self):
        junk = _plain(10, quantity=1,
                      damage_entries=["not a dict", None],
                      effects=[42, None])
        assert _pick([junk]) == 10


# ═══════════════════════════════════════════════════════════════════════════
# B) Weapon coating
# ═══════════════════════════════════════════════════════════════════════════

class TestWeaponCoating:
    COATING = {
        "item_id": 10, "quantity": 1,
        "consumable_action": "weapon_coating",
        "coating_turns": 4, "coating_bonus_damage": 10,
    }

    def test_coating_is_valued_when_none_is_active(self):
        assert _pick([dict(self.COATING)]) == 10

    def test_coating_scores_zero_while_one_is_active(self):
        actor = _actor(weapon_coating={"name": "Яд гадюки", "turns_left": 2})
        assert _pick([dict(self.COATING)], actor=actor) is None

    def test_active_coating_makes_the_picker_prefer_anything_else(self):
        actor = _actor(weapon_coating={"name": "Яд гадюки", "turns_left": 2})
        plain = _plain(20, quantity=1)  # 0.01, tiny but > 0
        assert _pick([dict(self.COATING), plain], actor=actor) == 20

    def test_coating_action_is_matched_case_insensitively(self):
        slot = dict(self.COATING, consumable_action="Weapon_Coating")
        actor = _actor(weapon_coating={"name": "Яд"})
        assert _pick([slot], actor=actor) is None

    def test_zero_turn_coating_adds_nothing(self):
        slot = dict(self.COATING, quantity=0, coating_turns=0)
        assert _pick([slot]) is None

    def test_missing_coating_numbers_default_to_zero(self):
        slot = {"item_id": 10, "quantity": 0, "consumable_action": "weapon_coating"}
        assert _pick([slot]) is None


# ═══════════════════════════════════════════════════════════════════════════
# C) Cleanse / antidote
# ═══════════════════════════════════════════════════════════════════════════

class TestCleanseItems:
    def _antidote(self, item_id=10, selector="debuff", quantity=0):
        return {
            "item_id": item_id, "quantity": quantity,
            "effects": [{"effect_name": "Cleanse", "attribute_key": selector}],
        }

    def test_scores_zero_with_no_effects_at_all(self):
        assert _pick([self._antidote()], actor=_actor(active_effects=[])) is None

    def test_scores_above_zero_with_a_removable_debuff(self):
        actor = _actor(pid=1, active_effects=[{"name": "Кровотечение", "owner_id": 2}])
        assert _pick([self._antidote()], actor=actor) == 10

    def test_own_buff_is_not_a_removable_debuff(self):
        """`debuff` means "put on me by someone else" — my own buff does not count."""
        actor = _actor(pid=1, active_effects=[{"name": "Сила", "owner_id": 1}])
        assert _pick([self._antidote()], actor=actor) is None

    def test_unremovable_stun_alone_scores_zero(self):
        """A full-skip control cannot be cleansed — the antidote is worthless."""
        actor = _actor(pid=1, active_effects=[{"name": "Stun", "owner_id": 2}])
        assert _pick([self._antidote()], actor=actor) is None

    def test_unremovable_paralysis_poison_alone_scores_zero(self):
        actor = _actor(pid=1, active_effects=[
            {"name": "Poison", "attribute": "paralysis", "owner_id": 2},
        ])
        assert _pick([self._antidote()], actor=actor) is None

    def test_removable_effect_next_to_an_unremovable_one_still_counts(self):
        actor = _actor(pid=1, active_effects=[
            {"name": "Stun", "owner_id": 2},
            {"name": "Кровотечение", "owner_id": 2},
        ])
        assert _pick([self._antidote()], actor=actor) == 10

    def test_periodic_damage_selector_matches_bleeding(self):
        actor = _actor(pid=1, active_effects=[{"name": "Bleeding", "owner_id": 1}])
        assert _pick([self._antidote(selector="periodic_damage")], actor=actor) == 10

    def test_periodic_damage_selector_ignores_a_stat_debuff(self):
        actor = _actor(pid=1, active_effects=[
            {"name": "Слабость", "attribute": "strength", "magnitude": 5, "owner_id": 1},
        ])
        assert _pick([self._antidote(selector="periodic_damage")], actor=actor) is None

    def test_stat_down_selector_matches_a_complex_debuff_with_positive_magnitude(self):
        """Mirror of `buffs._is_stat_down`: complex effects are expanded by the
        engine using abs(magnitude), so Curse/Freeze/… are always a stat-down
        regardless of the sign stored on the record."""
        actor = _actor(pid=1, active_effects=[
            {"name": "Curse", "attribute": "curse", "magnitude": 5, "owner_id": 2},
        ])
        assert _pick([self._antidote(selector="stat_down")], actor=actor) == 10

    def test_stat_down_selector_ignores_a_complex_buff(self):
        actor = _actor(pid=1, active_effects=[
            {"name": "Holy", "attribute": "holy", "magnitude": 5, "owner_id": 1},
        ])
        assert _pick([self._antidote(selector="stat_down")], actor=actor) is None

    def test_stat_down_selector_matches_a_negative_magnitude(self):
        actor = _actor(pid=1, active_effects=[
            {"name": "Слабость", "attribute": "strength", "magnitude": -4, "owner_id": 1},
        ])
        assert _pick([self._antidote(selector="stat_down")], actor=actor) == 10

    def test_all_selector_matches_any_removable_effect(self):
        actor = _actor(pid=1, active_effects=[{"name": "Что угодно", "owner_id": 1}])
        assert _pick([self._antidote(selector="all")], actor=actor) == 10

    def test_all_selector_still_ignores_an_unremovable_control(self):
        actor = _actor(pid=1, active_effects=[{"name": "Stun", "owner_id": 2}])
        assert _pick([self._antidote(selector="all")], actor=actor) is None

    def test_missing_selector_falls_back_to_debuff(self):
        actor = _actor(pid=1, active_effects=[{"name": "Кровотечение", "owner_id": 2}])
        slot = {"item_id": 10, "quantity": 0,
                "effects": [{"effect_name": "Cleanse"}]}
        assert _pick([slot], actor=actor) == 10
        assert strategy_mod.DEFAULT_CLEANSE_SELECTOR == "debuff"

    def test_cleanse_name_is_matched_case_insensitively(self):
        actor = _actor(pid=1, active_effects=[{"name": "Кровотечение", "owner_id": 2}])
        slot = {"item_id": 10, "quantity": 0,
                "effects": [{"effect_name": "cleanse", "attribute_key": "debuff"}]}
        assert _pick([slot], actor=actor) == 10

    def test_a_useful_antidote_beats_a_small_buff(self):
        actor = _actor(pid=1, active_effects=[{"name": "Кровотечение", "owner_id": 2}])
        small_buff = _plain(20, quantity=0, effects=[{
            "effect_name": "Сила", "target_side": "self",
            "magnitude": 2, "duration": 2,
        }])  # 0.6
        assert _pick([small_buff, self._antidote()], actor=actor) == 10


# ═══════════════════════════════════════════════════════════════════════════
# D) Regression — legacy recovery-only slots score exactly as before
# ═══════════════════════════════════════════════════════════════════════════

class TestLegacyRecoveryRegression:
    """The recovery part of the formula is unchanged in shape:

        v = need_hp * health_recovery + need_mana * mana_recovery
          + need_energy * energy_recovery + 0.01 * quantity

    with need_* = max(0, threshold - ratio) — the need grows as the resource
    runs LOW. (The original code had the subtraction the other way round, so
    the bot healed at full HP and never at 20 %; fixed in FEAT-168 together
    with the effect scoring.) These tests pin the value for a slot carrying
    none of the new keys.
    """

    LEGACY_BELT = {
        "item_id": 10, "quantity": 3,
        "health_recovery": 50, "mana_recovery": 10, "energy_recovery": 5,
    }

    def test_thresholds_are_unchanged(self):
        assert strategy_mod.HP_NEED_THRESHOLD == 0.7
        assert strategy_mod.MANA_NEED_THRESHOLD == 0.6
        assert strategy_mod.ENERGY_NEED_THRESHOLD == 0.6
        assert strategy_mod.QUANTITY_WEIGHT == 0.01

    def test_the_bigger_heal_wins_at_low_hp(self):
        """Two recovery belts, low HP: the bigger heal wins."""
        big = dict(self.LEGACY_BELT, item_id=10, quantity=3)
        small = {"item_id": 20, "quantity": 1,
                 "health_recovery": 10, "mana_recovery": 0, "energy_recovery": 0}
        feats = _feats(hp=0.2, mana=0.3, energy=0.3)
        # need = 0.5 / 0.3 / 0.3 ⇒ big = 29.53, small = 5.01
        assert _pick([small, big], feats=feats) == 10

    def test_a_full_resource_belt_is_only_worth_its_quantity_bonus(self):
        """At full HP/mana/energy nothing is needed, so recovery adds nothing."""
        belt = dict(self.LEGACY_BELT)           # 0.01 * 3 = 0.03
        richer = _plain(20, quantity=5)         # 0.05
        assert _pick([belt, richer], feats=_feats(hp=1.0, mana=1.0, energy=1.0)) == 20

    def test_legacy_belt_score_is_pinned_exactly(self):
        """Sandwich the recovery score between two quantity-only competitors.

        feats hp=0.5/mana=0.2/energy=0.2 ⇒ need = 0.2 / 0.4 / 0.4
        score = 0.2*50 + 0.4*10 + 0.4*5 + 0.01*3 = 16.03
        """
        feats = _feats(hp=0.5, mana=0.2, energy=0.2)
        belt = dict(self.LEGACY_BELT)

        just_below = _plain(20, quantity=1602)   # 16.02
        just_above = _plain(30, quantity=1604)   # 16.04

        assert _pick([just_below, belt], feats=feats) == 10
        assert _pick([belt, just_above], feats=feats) == 30

    def test_pre_deploy_slot_without_new_keys_scores_only_quantity(self):
        """A snapshot written before the deploy has no effects/damage/coating."""
        old_slot = {"item_id": 10, "quantity": 7}
        below = _plain(20, quantity=6)
        above = _plain(30, quantity=8)
        assert _pick([below, old_slot]) == 10
        assert _pick([old_slot, above]) == 30

    def test_pre_deploy_slot_with_zero_quantity_is_not_picked(self):
        assert _pick([{"item_id": 10, "quantity": 0}]) is None

    def test_none_values_do_not_crash_the_picker(self):
        slot = {"item_id": 10, "quantity": None,
                "health_recovery": None, "mana_recovery": None,
                "energy_recovery": None}
        assert _pick([slot]) is None

    def test_empty_fast_slots_returns_no_item(self):
        assert _pick([]) is None

    def test_pick_best_still_works_without_the_actor_argument(self):
        """Backwards compatibility: `actor` is optional."""
        s = Strategy()
        result = s._pick_best({}, _avail(_plain(10, quantity=5)), _feats())
        assert result["item_id"] == 10


# ═══════════════════════════════════════════════════════════════════════════
# E) _actor_state — defaults for pre-deploy runtime payloads
# ═══════════════════════════════════════════════════════════════════════════

class TestActorState:
    def test_reads_coating_and_effects(self):
        ctx = {"runtime": {
            "current_actor": 3,
            "participants": {"3": {"weapon_coating": {"name": "Яд"}}},
            "active_effects": {"3": [{"name": "Кровотечение"}]},
        }}
        state = Strategy._actor_state(ctx)
        assert state["pid"] == 3
        assert state["weapon_coating"] == {"name": "Яд"}
        assert state["active_effects"] == [{"name": "Кровотечение"}]

    def test_pre_deploy_runtime_has_no_coating_and_no_effects(self):
        ctx = {"runtime": {"current_actor": 3, "participants": {"3": {"hp": 50}}}}
        state = Strategy._actor_state(ctx)
        assert state["weapon_coating"] is None
        assert state["active_effects"] == []

    def test_missing_runtime_is_tolerated(self):
        state = Strategy._actor_state({})
        assert state == {"pid": 0, "weapon_coating": None, "active_effects": []}

    def test_non_numeric_actor_is_tolerated(self):
        state = Strategy._actor_state({"runtime": {"current_actor": "не число"}})
        assert state["pid"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# F) Weight constants are named (CLAUDE.md §6.3 — no magic numbers)
# ═══════════════════════════════════════════════════════════════════════════

class TestWeightConstants:
    def test_all_weights_exist_and_are_positive(self):
        for name in ("DAMAGE_WEIGHT", "BUFF_WEIGHT", "DEBUFF_WEIGHT",
                     "COATING_WEIGHT", "CLEANSE_WEIGHT", "QUANTITY_WEIGHT"):
            assert getattr(strategy_mod, name) > 0, name

    def test_healing_in_a_crisis_outranks_a_stockpiled_buff(self):
        """At 20 % HP a large heal (need 0.5 × 200 = 100) beats a buff (2.25)."""
        heal = {"item_id": 10, "quantity": 0, "health_recovery": 200}
        buff = _plain(20, quantity=0, effects=[{
            "effect_name": "Сила", "target_side": "self",
            "magnitude": 5, "duration": 3,
        }])
        assert _pick([buff, heal], feats=_feats(hp=0.2)) == 10

    def test_a_heal_at_full_hp_loses_to_a_buff(self):
        """The inverted-need bug: at full HP the bot used to drink the potion."""
        heal = {"item_id": 10, "quantity": 0, "health_recovery": 200}
        buff = _plain(20, quantity=0, effects=[{
            "effect_name": "Сила", "target_side": "self",
            "magnitude": 5, "duration": 3,
        }])
        assert _pick([heal, buff], feats=_feats(hp=1.0)) == 20
