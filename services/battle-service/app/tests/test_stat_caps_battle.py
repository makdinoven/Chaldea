"""
FEAT-195 — soft/hard stat caps in battle-service.

Covers:
  * compute_damage_with_rolls: base = eff(main attribute) + damage bonus
    (+ weapon) for 80 / 150 / 250, per class, with a buff crossing 200;
  * the hit roll gets +0.1 * eff(luck); the crit roll is the stored
    critical_hit_chance only (luck is no longer counted twice);
  * luck_proc_bonus helper;
  * buffs.aggregate_modifiers(effects, base_attributes): derived deltas are
    per_point * (eff(base + Δ) - eff(base)) across 100/200, luck now moves
    dodge/crit/res_effects, stacked effects are capped on their SUM,
    `_is_stat_down` (no base) still works by sign;
  * redis_state.compute_initiative via eff;
  * `attacker_luck_bonus` in a real `_make_action_core` turn uses the BUFFED
    luck (the effect-proc chance handed to `_filter_effects_by_chance`);
  * stat_caps.py is byte-identical to the canonical copy.

The engine modules are loaded as PRIVATE instances straight from disk: other
suites in this directory replace `buffs` / `battle_engine` / `redis_state` in
`sys.modules` with MagicMocks during collection.
"""

import hashlib
import importlib.util
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, APP_DIR)

import stat_caps  # noqa: E402  (pure module, never mocked)
from stat_caps import effective_stat  # noqa: E402


def _load_private(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP_DIR, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


engine = _load_private("_feat195_battle_engine", "battle_engine.py")
buffs = _load_private("_feat195_buffs", "buffs.py")
redis_state = _load_private("_feat195_redis_state", "redis_state.py")

for _fn in (engine.compute_damage_with_rolls, buffs.aggregate_modifiers,
            redis_state.compute_initiative):
    assert not isinstance(_fn, MagicMock)

PHYS = ("res_physical", "res_catting", "res_crushing", "res_piercing")
MAG = ("res_magic", "res_fire", "res_ice", "res_watering",
       "res_electricity", "res_wind", "res_sainting", "res_damning")


def _attacker(**over):
    a = {"strength": 0, "agility": 0, "intelligence": 0, "luck": 0, "damage": 0,
         "critical_hit_chance": 20.0, "critical_damage": 150}
    a.update(over)
    return a


DEFENDER = {"dodge": 0.0}


def _entry(amount=0, chance=100, damage_type="physical"):
    return {"damage_type": damage_type, "amount": amount, "chance": chance}


async def _hit(attacker, *, class_id=1, weapon=None, entry=None, crit=False, chance=True):
    """Deterministic hit: no dodge, hit roll result `chance`, crit `crit`.
    Returns (damage, log, recorded hit chances, recorded crit chances)."""
    hit_chances, crit_chances = [], []

    def _roll_chance(pct):
        hit_chances.append(pct)
        return chance

    def _roll_crit(pct):
        crit_chances.append(pct)
        return crit

    with patch.object(engine, "roll_dodge", return_value=False), \
            patch.object(engine, "roll_chance", side_effect=_roll_chance), \
            patch.object(engine, "roll_crit", side_effect=_roll_crit):
        dmg, log = await engine.compute_damage_with_rolls(
            damage_entry=entry or _entry(),
            attacker_attr=attacker, weapon=weapon, percent_buffs={},
            defender_attr=DEFENDER, percent_resists={}, class_id=class_id,
        )
    return dmg, log, hit_chances, crit_chances


# ===========================================================================
# Damage base
# ===========================================================================

class TestDamageBase:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value, expected", [(80, 80.0), (150, 125.0), (250, 162.5),
                                                 (530, 232.5), (0, 0.0)])
    async def test_main_attribute_capped(self, value, expected):
        dmg, log, _, _ = await _hit(_attacker(strength=value))
        assert log["base"] == pytest.approx(expected)
        assert dmg == pytest.approx(expected)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("class_id, key", [(1, "strength"), (2, "agility"), (3, "intelligence")])
    async def test_class_main_attribute(self, class_id, key):
        attacker = _attacker(strength=10, agility=10, intelligence=10)
        attacker[key] = 250
        _, log, _, _ = await _hit(attacker, class_id=class_id)
        assert log["base"] == pytest.approx(162.5)

    @pytest.mark.asyncio
    async def test_unknown_class_falls_back_to_strength(self):
        _, log, _, _ = await _hit(_attacker(strength=150, agility=999), class_id=99)
        assert log["base"] == pytest.approx(125.0)

    @pytest.mark.asyncio
    async def test_damage_bonus_and_weapon_are_not_capped(self):
        weapon = {"effective_damage": 300, "primary_damage_type": "physical"}
        _, log, _, _ = await _hit(_attacker(strength=250, damage=400), weapon=weapon,
                                  entry=_entry(amount=10))
        assert log["base"] == pytest.approx(162.5 + 400 + 300)
        assert log["after_buffs"] == pytest.approx(162.5 + 400 + 300 + 10)

    @pytest.mark.asyncio
    async def test_buff_crossing_200_is_capped_on_the_sum(self):
        """The caller hands the BUFFED attributes: base 180 + buff 50 = 230."""
        base = _attacker(strength=180)
        mods = buffs.aggregate_modifiers(
            [{"name": "StatModifier", "attribute": "strength", "magnitude": 50}],
            base_attributes=base,
        )
        buffed = engine.apply_flat_modifiers(base, mods)
        _, log, _, _ = await _hit(buffed)
        assert log["base"] == pytest.approx(157.5)  # eff(230); linear would be 230

    @pytest.mark.asyncio
    async def test_negative_main_attribute_floors_at_zero(self):
        dmg, log, _, _ = await _hit(_attacker(strength=-30))
        assert log["base"] == 0
        assert dmg == 0


# ===========================================================================
# Luck: hit roll yes, crit roll no
# ===========================================================================

class TestLuck:

    @pytest.mark.parametrize("luck, bonus", [(0, 0.0), (50, 5.0), (100, 10.0), (150, 12.5),
                                             (250, 16.25), (530, 23.25), (-20, -2.0)])
    def test_luck_proc_bonus(self, luck, bonus):
        assert engine.luck_proc_bonus({"luck": luck}) == pytest.approx(bonus)

    @pytest.mark.parametrize("attrs", [{}, None, {"luck": None}, {"luck": "много"}])
    def test_luck_proc_bonus_garbage(self, attrs):
        assert engine.luck_proc_bonus(attrs) == 0.0

    def test_constant(self):
        assert engine.LUCK_PROC_PER_POINT == 0.1

    @pytest.mark.asyncio
    async def test_hit_roll_gets_eff_luck(self):
        _, _, hits, _ = await _hit(_attacker(luck=250), entry=_entry(chance=50))
        assert hits == [pytest.approx(66.25)]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("luck", [0, 50, 300])
    async def test_crit_roll_is_stored_crit_only(self, luck):
        _, _, _, crits = await _hit(_attacker(luck=luck, critical_hit_chance=37.5))
        assert crits == [pytest.approx(37.5)]

    @pytest.mark.asyncio
    async def test_crit_multiplier_still_applies(self):
        dmg, log, _, _ = await _hit(_attacker(strength=100, critical_damage=150), crit=True)
        assert log["critical"] is True
        assert dmg == pytest.approx(150.0)

    @pytest.mark.asyncio
    async def test_missed_hit_skips_crit_roll(self):
        dmg, log, _, crits = await _hit(_attacker(strength=100), chance=False)
        assert dmg == 0.0 and log["hit_chance_failed"] is True
        assert crits == []


# ===========================================================================
# aggregate_modifiers
# ===========================================================================

def _stat(attr, magnitude, name="StatModifier"):
    return {"name": name, "attribute": attr, "magnitude": magnitude}


class TestAggregateModifiers:

    def test_strength_buff_crossing_200(self):
        """+50 strength at 180: 0.1 * (eff(230) - eff(180)) = 0.1 * 17.5 = 1.75."""
        mods = buffs.aggregate_modifiers([_stat("strength", 50)], base_attributes={"strength": 180})
        assert mods["strength"] == 50
        for key in PHYS:
            assert mods[key] == pytest.approx(1.75)
        for key in MAG:
            assert key not in mods

    def test_without_base_is_linear(self):
        mods = buffs.aggregate_modifiers([_stat("strength", 50)])
        for key in PHYS:
            assert mods[key] == pytest.approx(5.0)

    def test_below_soft_cap_same_as_linear(self):
        with_base = buffs.aggregate_modifiers([_stat("intelligence", 20)],
                                              base_attributes={"intelligence": 30})
        linear = buffs.aggregate_modifiers([_stat("intelligence", 20)])
        assert with_base == pytest.approx(linear)

    def test_debuff_crossing_200_down(self):
        mods = buffs.aggregate_modifiers([_stat("strength", -50)], base_attributes={"strength": 230})
        assert mods["res_physical"] == pytest.approx(-1.75)

    def test_buff_then_debuff_symmetry(self):
        up = buffs.aggregate_modifiers([_stat("agility", 70)], base_attributes={"agility": 150})
        down = buffs.aggregate_modifiers([_stat("agility", -70)], base_attributes={"agility": 220})
        assert up["dodge"] == pytest.approx(-down["dodge"])
        assert up["dodge"] == pytest.approx(0.1 * (155 - 125))

    def test_luck_now_propagates(self):
        """+100 luck at 150: eff 125 -> 162.5 => +3.75 to dodge, crit, res_effects."""
        mods = buffs.aggregate_modifiers([_stat("luck", 100)], base_attributes={"luck": 150})
        assert mods["luck"] == 100
        assert mods["dodge"] == pytest.approx(3.75)
        assert mods["critical_hit_chance"] == pytest.approx(3.75)
        assert mods["res_effects"] == pytest.approx(3.75)

    def test_luck_and_agility_both_feed_dodge(self):
        mods = buffs.aggregate_modifiers(
            [_stat("luck", 10), _stat("agility", 10), _stat("dodge", 2.0)],
            base_attributes={"luck": 0, "agility": 0},
        )
        assert mods["dodge"] == pytest.approx(2.0 + 1.0 + 1.0)

    def test_endurance_res_effects(self):
        mods = buffs.aggregate_modifiers([_stat("endurance", 100)],
                                         base_attributes={"endurance": 100})
        assert mods["res_effects"] == pytest.approx(0.2 * 50)

    def test_stacked_effects_are_capped_on_their_sum(self):
        base = {"strength": 180}
        two = buffs.aggregate_modifiers([_stat("strength", 25), _stat("strength", 25)],
                                        base_attributes=base)
        one = buffs.aggregate_modifiers([_stat("strength", 50)], base_attributes=base)
        assert two == pytest.approx(one)

    def test_missing_or_none_base_value_counts_as_zero(self):
        mods = buffs.aggregate_modifiers([_stat("strength", 150)], base_attributes={"strength": None})
        assert mods["res_physical"] == pytest.approx(12.5)
        mods = buffs.aggregate_modifiers([_stat("strength", 150)], base_attributes={})
        assert mods["res_physical"] == pytest.approx(12.5)

    def test_flat_derived_buff_not_scaled(self):
        mods = buffs.aggregate_modifiers([_stat("res_physical", 10)],
                                         base_attributes={"strength": 500})
        assert mods == {"res_physical": 10}

    def test_charisma_buff_has_no_derived(self):
        mods = buffs.aggregate_modifiers([_stat("charisma", 50)], base_attributes={"charisma": 300})
        assert mods == {"charisma": 50}

    @pytest.mark.parametrize("magnitude, down", [(-10, True), (10, False)])
    def test_is_stat_down_by_sign_for_luck(self, magnitude, down):
        assert buffs._is_stat_down(_stat("luck", magnitude)) is down

    def test_is_stat_down_unchanged_for_strength(self):
        assert buffs._is_stat_down(_stat("strength", -5)) is True
        assert buffs._is_stat_down(_stat("strength", 5)) is False


# ===========================================================================
# Initiative
# ===========================================================================

class TestInitiative:

    @pytest.mark.parametrize("attrs, expected", [
        ({"agility": 300}, 175.0),
        ({"agility": 50, "strength": 40, "intelligence": 20}, 95.0),
        ({"strength": 250, "intelligence": 250}, 243.75),
        ({"agility": 150, "strength": 150}, 125.0 + 93.75),
        ({"agility": None, "strength": None}, 0.0),
        ({}, 0.0),
        ({"agility": 100, "luck": 999, "endurance": 999, "charisma": 999}, 100.0),
    ])
    def test_initiative(self, attrs, expected):
        assert redis_state.compute_initiative(attrs) == pytest.approx(expected)

    def test_capped_rogue_vs_uncapped_warrior_order(self):
        """agi 300 (eff 175) vs str 200 + int 100 (0.75 * 250 = 187.5): the warrior goes first."""
        rogue = redis_state.compute_initiative({"agility": 300})
        warrior = redis_state.compute_initiative({"strength": 200, "intelligence": 100})
        assert warrior > rogue


# ===========================================================================
# stat_caps copy
# ===========================================================================

class TestStatCapsCopy:

    def test_identical_to_canonical(self):
        canonical = os.path.normpath(os.path.join(
            APP_DIR, "..", "..", "character-attributes-service", "app", "stat_caps.py"))
        if not os.path.exists(canonical):
            msg = f"canonical stat_caps.py not found at {canonical} (needs a full checkout)"
            if os.environ.get("CI"):
                pytest.fail(msg)
            pytest.skip(msg)
        mine = os.path.join(APP_DIR, "stat_caps.py")
        digest = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()  # noqa: E731
        assert digest(mine) == digest(canonical)

    def test_values(self):
        assert [effective_stat(x) for x in (0, 100, 150, 200, 250, 530, -10)] == \
            [0, 100, 125, 150, 162.5, 232.5, -10]
        assert stat_caps.effective_delta(180, 230) == 17.5


# ===========================================================================
# attacker_luck_bonus in a real turn uses the BUFFED luck
# ===========================================================================

class TestAttackerLuckBonusInTurn:
    """Runs POST /battles/1/action through the FEAT-168 real-engine harness and
    records the luck bonus `_make_action_core` hands to the effect-proc roll."""

    def _run(self, base_luck, buff):
        harness = pytest.importorskip("tests.test_item_effects")
        import main

        attrs = dict(harness.ATTRS, luck=base_luck)
        effects = {}
        if buff:
            effects[str(harness.ATTACKER_PID)] = [{
                "name": "StatModifier", "attribute": "luck", "magnitude": buff,
                "duration": 3, "owner_id": harness.ATTACKER_PID,
            }]
        state = harness._state(active_effects=effects)
        skill = harness._attack_skill(
            damage_entries=[harness._damage_row(amount=5)],
            effects=[harness._effect_row("StatModifier", attribute_key="strength",
                                         magnitude=-1, duration=2, chance=40,
                                         target_side="enemy")],
        )
        seen = []
        real_filter = main._filter_effects_by_chance

        def _spy(effects_, luck_bonus, *args, **kwargs):
            seen.append(luck_bonus)
            return real_filter(effects_, luck_bonus, *args, **kwargs)

        # The harness reads its module-level ATTRS when it patches
        # main.fetch_full_attributes, so swapping ATTRS gives the attacker luck.
        with patch.object(harness, "ATTRS", attrs), \
                patch("main._filter_effects_by_chance", side_effect=_spy):
            resp, *_ = harness._run_turn(
                state, payload=harness._payload(attack_skill_id=1, target_id=harness.DEFENDER_PID),
                attack_skill=skill,
            )
        assert resp.status_code == 200, resp.text
        assert seen, "the effect-proc roll was never reached"
        return seen

    def test_buffed_luck_crossing_200(self):
        seen = self._run(base_luck=150, buff=100)  # 250 -> 0.1 * 162.5
        assert all(v == pytest.approx(16.25) for v in seen)

    def test_unbuffed_luck(self):
        seen = self._run(base_luck=150, buff=0)
        assert all(v == pytest.approx(12.5) for v in seen)
