"""FEAT-190 (Task #5) — unit tests for subclass passives wave 2.

Pure tests of the wave-2 hooks of ``passives.py`` (H6 redirect, H13
Necromancer kill heal, H14–H25: shields, vow, lifesteal, reflect, heal /
«Прилив», «Плата кровью», Bard / Etheriad end-of-action, deaths cleanup,
``land_hit``) and of the two optional ``buffs.py`` callbacks
``absorb_fn`` / ``overheal_fn`` (exercised through the REAL buffs module with
closures wired the way main.py wires them).

Both modules are loaded from their files under PRIVATE names, so the
``MagicMock``s other test files park in ``sys.modules["buffs"]`` can't leak in
(the project's silent-failure pattern). Nothing here imports ``main`` — the
pipeline wiring is Task #6.

Randomness: wave 2 only uses ``passives.pick`` (Trickster redirect target,
Etheriad curse / might target). It is patched both ways; the ``no_rolls``
fixture turns any roll into an ``AssertionError`` to prove that participants
without the passive never consume one.
"""

import copy
import importlib.util
import json
import os
import re
from contextlib import contextmanager
from unittest.mock import patch

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def _load_private(module_name, filename):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(APP_DIR, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = _load_private("_feat190_passives", "passives.py")
B = _load_private("_feat190_buffs", "buffs.py")


# =============================================================================
# Helpers
# =============================================================================
def part(team, key=None, hp=100, max_hp=100, **kw):
    d = {"team": team, "hp": hp, "max_hp": max_hp, "passive_key": key}
    d.update(kw)
    return d


def battle(parts, **extra):
    s = {"participants": {str(k): v for k, v in parts.items()}}
    s.update(extra)
    return s


def P_(state, pid):
    return state["participants"][str(pid)]


def ps(state, pid):
    return P_(state, pid).get("passive_state")


def shields(state, pid):
    return (ps(state, pid) or {}).get("shields")


def give(state, pid, *entries):
    """Put raw shield entries on `pid`."""
    P_(state, pid).setdefault("passive_state", {})["shields"] = [dict(e) for e in entries]


def sh(amount, owner=1, key=P.PASSIVE_AUROMANCER, turns_left=3, cap=None, fresh=False):
    return {"key": key, "owner": owner, "amount": amount,
            "cap": amount if cap is None else cap, "turns_left": turns_left, "fresh": fresh}


def _boom(*_a, **_k):
    raise AssertionError("a passive roll was consumed")


@pytest.fixture
def no_rolls():
    with patch.object(P, "roll_pct", side_effect=_boom), \
            patch.object(P, "pick", side_effect=_boom), \
            patch.object(P, "_rng") as rng:
        rng.random.side_effect = _boom
        rng.choice.side_effect = _boom
        yield


@contextmanager
def picks(index=0):
    """pick → seq[index]; records every sequence it was offered."""
    seen = []

    def _pick(seq):
        items = list(seq)
        seen.append(items)
        return items[index] if items else None

    with patch.object(P, "pick", side_effect=_pick), \
            patch.object(P, "roll_pct", side_effect=_boom):
        yield seen


def dump(obj):
    """Exact serialisation — distinguishes 5 from 5.0 (byte-identical checks)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


# =============================================================================
# Guards / constants
# =============================================================================
class TestModuleGuards:
    def test_passives_imports_neither_buffs_nor_battle_engine(self):
        with open(os.path.join(APP_DIR, "passives.py"), encoding="utf-8") as fh:
            src = fh.read()
        assert not re.search(r"^\s*(import|from)\s+(buffs|battle_engine)\b", src, re.M)
        assert not re.search(r"^\s*from\s+\.\s*import\s+(buffs|battle_engine)", src, re.M)
        assert "buffs" not in vars(P) and "battle_engine" not in vars(P)

    def test_all_21_implemented(self):
        assert len(P.IMPLEMENTED_PASSIVES) == 21
        assert {
            "paladin_sacred_vow", "guardian_retribution", "bard_rhythm",
            "necromancer_blood_price", "etheriad_spirit_whisper", "auromancer_tide",
            "priest_faith",
        } <= P.IMPLEMENTED_PASSIVES

    def test_wave2_numbers(self):
        assert (P.VOW_HP_PCT, P.VOW_SHIELD_PCT) == (30, 20)
        assert P.RETRIBUTION_PCT == 15
        assert (P.RAGE_LIFESTEAL_HP_PCT, P.RAGE_LIFESTEAL_PCT) == (25, 15)
        assert (P.FAITH_LIFESTEAL_PCT, P.FAITH_HOLY_LIFESTEAL_PCT, P.HOLY_TYPE) == (10, 15, "sainting")
        assert (P.INSPIRATION_PCT, P.INSPIRATION_MAX_STACKS) == (3, 4)
        assert (P.INSPIRATION_SOLO_PCT, P.INSPIRATION_SOLO_MAX_STACKS) == (5, 3)
        assert P.INSPIRATION_DURATION == 2
        assert (P.BLOOD_HP_PER_MANA, P.BLOOD_MIN_HP_LEFT, P.NECRO_KILL_HEAL_PCT) == (1.5, 1, 10)
        assert (P.SPIRIT_ALLY_HP_PCT, P.SPIRIT_RESIST_PCT, P.SPIRIT_DAMAGE_PCT, P.SPIRIT_DURATION) == (50, 8, 8, 2)
        assert (P.TIDE_CAP_PCT, P.TIDE_TURNS) == (20, 3)
        assert P.REDIRECT_MULT == 0.5

    def test_passive_sources_match_buffs_normalize_source(self):
        assert P.SOURCE_BARD == B.normalize_source(("passive", P.PASSIVE_BARD))
        assert P.SOURCE_ETHERIAD == B.normalize_source(("passive", P.PASSIVE_ETHERIAD))


# =============================================================================
# H14 — shield_total
# =============================================================================
class TestShieldTotal:
    def test_old_state_is_zero_and_not_created(self):
        p = part(1)
        assert P.shield_total(p) == 0
        assert "passive_state" not in p

    @pytest.mark.parametrize("value", [None, "abc", 5, {"a": 1}])
    def test_garbage_is_zero(self, value):
        assert P.shield_total({"passive_state": {"shields": value}}) == 0
        assert P.shield_total({"passive_state": value}) == 0
        assert P.shield_total(value) == 0

    def test_sum_rounded_and_skips_garbage(self):
        p = {"passive_state": {"shields": [
            {"amount": 10.4}, {"amount": 0.4}, {"amount": "x"}, {"amount": -5}, "junk"]}}
        assert P.shield_total(p) == 11
        assert P.shield_total({"passive_state": {"shields": [{"amount": 0.4}]}}) == 0


# =============================================================================
# H15 — absorb
# =============================================================================
class TestAbsorb:
    def test_no_shields_passthrough_same_object(self):
        s = battle({1: part(1)})
        amt = 17
        rem, ab = P.absorb(s, 1, amt)
        assert rem is amt and ab == 0.0
        assert "passive_state" not in P_(s, 1)
        f = 12.5
        assert P.absorb(s, 1, f)[0] is f

    @pytest.mark.parametrize("amount", [0, -5])
    def test_non_positive_amount_untouched(self, amount):
        s = battle({1: part(1)})
        give(s, 1, sh(10))
        assert P.absorb(s, 1, amount) == (amount, 0.0)
        assert shields(s, 1)[0]["amount"] == 10

    def test_garbage_amount_never_raises(self):
        s = battle({1: part(1)})
        give(s, 1, sh(10))
        assert P.absorb(s, 1, "abc") == (0.0, 0.0)
        assert P.absorb(s, 1, None) == (0.0, 0.0)
        assert shields(s, 1)[0]["amount"] == 10

    def test_unknown_pid_passthrough(self):
        s = battle({1: part(1)})
        assert P.absorb(s, 99, 10) == (10, 0.0)

    def test_dead_holder_ignored(self):
        s = battle({1: part(1, hp=0)})
        give(s, 1, sh(10))
        assert P.absorb(s, 1, 6) == (6, 0.0)
        assert shields(s, 1)[0]["amount"] == 10

    def test_dropped_out_holder_ignored(self):
        s = battle({1: part(1, dropped_out=True)})
        give(s, 1, sh(10))
        assert P.absorb(s, 1, 6) == (6, 0.0)

    def test_partial_absorb(self):
        s = battle({1: part(1)})
        give(s, 1, sh(10))
        rem, ab = P.absorb(s, 1, 4)
        assert (rem, ab) == (0.0, 4)
        assert shields(s, 1)[0]["amount"] == 6

    def test_total_absorb_overflow_and_empty_entries_removed(self):
        s = battle({1: part(1)})
        give(s, 1, sh(5), sh(3, owner=2, key=P.PASSIVE_PALADIN, turns_left=None))
        rem, ab = P.absorb(s, 1, 20)
        assert (rem, ab) == (12, 8)
        assert shields(s, 1) == []

    def test_order_timed_shortest_first_then_permanent(self):
        s = battle({1: part(1)})
        give(s, 1,
             sh(10, owner=1, key=P.PASSIVE_PALADIN, turns_left=None),   # permanent
             sh(5, owner=2, turns_left=3),
             sh(4, owner=3, turns_left=1))
        rem, ab = P.absorb(s, 1, 6)
        assert (rem, ab) == (0.0, 6)
        left = {e["owner"]: e["amount"] for e in shields(s, 1)}
        # turns_left=1 drained (removed), turns_left=3 took 2, permanent untouched
        assert left == {1: 10, 2: 3}

    def test_permanent_used_only_after_timed(self):
        s = battle({1: part(1)})
        give(s, 1,
             sh(10, owner=1, key=P.PASSIVE_PALADIN, turns_left=None),
             sh(5, owner=2, turns_left=3))
        rem, ab = P.absorb(s, 1, 8)
        assert (rem, ab) == (0.0, 8)
        assert [(e["owner"], e["amount"]) for e in shields(s, 1)] == [(1, 7)]

    def test_tie_uses_list_order(self):
        s = battle({1: part(1)})
        give(s, 1, sh(5, owner=7, turns_left=2), sh(5, owner=8, turns_left=2))
        P.absorb(s, 1, 3)
        assert [(e["owner"], e["amount"]) for e in shields(s, 1)] == [(7, 2), (8, 5)]

    def test_garbage_entries_dropped(self):
        s = battle({1: part(1)})
        P_(s, 1)["passive_state"] = {"shields": ["junk", {"amount": "x"}, {"amount": 0},
                                                  sh(5, turns_left="garbage")]}
        rem, ab = P.absorb(s, 1, 2)
        assert (rem, ab) == (0.0, 2)
        assert len(shields(s, 1)) == 1 and shields(s, 1)[0]["amount"] == 3


# =============================================================================
# H16 — add_shield
# =============================================================================
class TestAddShield:
    def test_new_entry_capped(self):
        s = battle({1: part(1)})
        assert P.add_shield(s, 1, P.PASSIVE_AUROMANCER, 5, 50, 20, 3) == 20
        assert shields(s, 1) == [{"key": P.PASSIVE_AUROMANCER, "owner": 5, "amount": 20,
                                  "cap": 20.0, "turns_left": 3, "fresh": True}]

    def test_permanent_entry_not_fresh(self):
        s = battle({1: part(1)})
        P.add_shield(s, 1, P.PASSIVE_PALADIN, 1, 20, 20, None)
        assert shields(s, 1)[0]["fresh"] is False and shields(s, 1)[0]["turns_left"] is None

    def test_top_up_same_key_owner_to_cap_and_reset(self):
        s = battle({1: part(1)})
        give(s, 1, sh(15, owner=5, cap=20, turns_left=1, fresh=False))
        assert P.add_shield(s, 1, P.PASSIVE_AUROMANCER, 5, 10, 20, 3) == 5
        e, = shields(s, 1)
        assert (e["amount"], e["turns_left"], e["fresh"]) == (20, 3, True)

    def test_at_cap_gains_zero_but_resets_turns(self):
        s = battle({1: part(1)})
        give(s, 1, sh(20, owner=5, cap=20, turns_left=1, fresh=False))
        assert P.add_shield(s, 1, P.PASSIVE_AUROMANCER, 5, 10, 20, 3) == 0
        e, = shields(s, 1)
        assert (e["amount"], e["turns_left"], e["fresh"]) == (20, 3, True)

    def test_different_owner_or_key_stacks(self):
        s = battle({1: part(1)})
        P.add_shield(s, 1, P.PASSIVE_AUROMANCER, 5, 10, 20, 3)
        P.add_shield(s, 1, P.PASSIVE_AUROMANCER, 6, 10, 20, 3)
        P.add_shield(s, 1, P.PASSIVE_PALADIN, 1, 7, 7, None)
        assert len(shields(s, 1)) == 3
        assert P.shield_total(P_(s, 1)) == 27

    @pytest.mark.parametrize("amount,cap", [(0, 20), (-1, 20), (10, 0), ("x", 20), (10, None)])
    def test_bad_amount_or_cap_noop(self, amount, cap):
        s = battle({1: part(1)})
        assert P.add_shield(s, 1, P.PASSIVE_AUROMANCER, 5, amount, cap, 3) == 0.0
        assert "passive_state" not in P_(s, 1)

    def test_dead_or_unknown_target_noop(self):
        s = battle({1: part(1, hp=0)})
        assert P.add_shield(s, 1, P.PASSIVE_AUROMANCER, 5, 10, 20, 3) == 0.0
        assert P.add_shield(s, 9, P.PASSIVE_AUROMANCER, 5, 10, 20, 3) == 0.0
        assert "passive_state" not in P_(s, 1)


# =============================================================================
# H17 — tick_shields
# =============================================================================
class TestTickShields:
    def test_auromancer_shield_lives_three_owner_turns(self):
        s = battle({1: part(1, P.PASSIVE_AUROMANCER), 2: part(1)})
        P.add_shield(s, 2, P.PASSIVE_AUROMANCER, 1, 10, 20, P.TIDE_TURNS)
        P.tick_shields(s, 1)          # creation turn: fresh skipped
        assert shields(s, 2)[0]["turns_left"] == 3 and shields(s, 2)[0]["fresh"] is False
        P.tick_shields(s, 1)
        assert shields(s, 2)[0]["turns_left"] == 2
        P.tick_shields(s, 1)
        assert shields(s, 2)[0]["turns_left"] == 1
        P.tick_shields(s, 1)
        assert shields(s, 2) == []

    def test_only_owner_turn_ticks(self):
        s = battle({1: part(1), 2: part(1), 3: part(2)})
        give(s, 2, sh(10, owner=1, turns_left=2))
        P.tick_shields(s, 3)
        P.tick_shields(s, 2)
        assert shields(s, 2)[0]["turns_left"] == 2

    def test_paladin_permanent_never_ticks(self):
        s = battle({1: part(1)})
        give(s, 1, sh(10, owner=1, key=P.PASSIVE_PALADIN, turns_left=None))
        for _ in range(10):
            P.tick_shields(s, 1)
        assert shields(s, 1)[0]["amount"] == 10

    def test_never_creates_state(self):
        s = battle({1: part(1), 2: part(2)})
        P.tick_shields(s, 1)
        assert "passive_state" not in P_(s, 1) and "passive_state" not in P_(s, 2)

    @pytest.mark.parametrize("state", [None, [], {"participants": None},
                                       {"participants": {"1": "x", "2": {"passive_state": "x"}}}])
    def test_garbage(self, state):
        P.tick_shields(state, 1)


# =============================================================================
# shield_absorb_event / heal
# =============================================================================
class TestShieldAbsorbEventAndHeal:
    def test_event(self):
        s = battle({4: part(1)})
        give(s, 4, sh(6.4))
        ev = P.shield_absorb_event(s, 4, 3.6)
        assert ev == {"event": "passive_proc", "who": 4, "key": "shield",
                      "kind": "shield_absorb", "value": 4, "shield": 6}

    @pytest.mark.parametrize("v", [0, 0.4, -3, None, "x"])
    def test_no_event_for_zero(self, v):
        assert P.shield_absorb_event(battle({4: part(1)}), 4, v) is None

    def test_heal_clamps(self):
        p = part(1, hp=90)
        assert P.heal(p, 25) == 10 and p["hp"] == 100

    @pytest.mark.parametrize("kw", [dict(hp=0), dict(hp=-5), dict(hp=100), dict(dropped_out=True),
                                    dict(max_hp=0), dict(max_hp="x")])
    def test_heal_noop(self, kw):
        p = part(1, **{"hp": 50, **kw})
        before = dict(p)
        assert P.heal(p, 10) == 0.0
        assert p == before

    @pytest.mark.parametrize("amount", [0, -5, None, "x"])
    def test_heal_bad_amount(self, amount):
        p = part(1, hp=50)
        assert P.heal(p, amount) == 0.0 and p["hp"] == 50
        assert P.heal(None, 5) == 0.0


# =============================================================================
# H18 — Paladin vow
# =============================================================================
def _paladin_battle(hp=29, effects=None):
    s = battle({1: part(1, P.PASSIVE_PALADIN, hp=hp), 2: part(1), 3: part(2), 4: part(2)})
    if effects is not None:
        s["active_effects"] = {"1": effects}
    return s


def row(name, owner=None, attribute=None, **kw):
    r = {"name": name, "attribute": attribute or name.lower(), "magnitude": 5, "duration": 2}
    if owner is not None:
        r["owner_id"] = owner
    r.update(kw)
    return r


class TestVow:
    def test_below_30_triggers_once(self):
        s = _paladin_battle(hp=29)
        evs = P.check_vow(s, 1)
        assert evs == [{"event": "passive_proc", "who": 1, "key": P.PASSIVE_PALADIN,
                        "kind": "vow", "value": 20, "shield": 20}]
        assert ps(s, 1)["vow_used"] is True
        e, = shields(s, 1)
        assert (e["key"], e["owner"], e["amount"], e["turns_left"]) == (P.PASSIVE_PALADIN, 1, 20, None)
        P_(s, 1)["hp"] = 5
        assert P.check_vow(s, 1) == []
        assert P.shield_total(P_(s, 1)) == 20

    def test_shield_is_20pct_of_max(self):
        s = battle({1: part(1, P.PASSIVE_PALADIN, hp=50, max_hp=250)})
        assert P.check_vow(s, 1)[0]["value"] == 50

    @pytest.mark.parametrize("hp", [30, 31, 100, 0, -10])
    def test_no_trigger(self, hp):
        s = _paladin_battle(hp=hp)
        assert P.check_vow(s, 1) == []
        assert "passive_state" not in P_(s, 1)

    def test_dropped_out_no_trigger(self):
        s = _paladin_battle(hp=10)
        P_(s, 1)["dropped_out"] = True
        assert P.check_vow(s, 1) == []

    def test_non_paladin_nothing(self, no_rolls):
        s = battle({1: part(1, P.PASSIVE_GUARDIAN, hp=5), 2: part(1, hp=5)})
        assert P.check_vow(s, 1) == [] and P.check_vow(s, 2) == []
        assert "passive_state" not in P_(s, 1) and "passive_state" not in P_(s, 2)

    def test_cleanse_most_recent_enemy_row(self):
        effects = [row("Bleeding", owner=3), row("Weakness", owner=4),
                   row("Shield", owner=2), row("OldRow")]
        s = _paladin_battle(effects=effects)
        ev, = P.check_vow(s, 1)
        assert ev["effects"] == ["Weakness"]
        assert [r["name"] for r in s["active_effects"]["1"]] == ["Bleeding", "Shield", "OldRow"]

    def test_cleanse_skips_hard_control(self):
        effects = [row("Bleeding", owner=3), row("Poison", owner=3, attribute="periodic_damage"),
                   row("Stun", owner=4), row("Poison", owner=4, attribute="paralysis")]
        s = _paladin_battle(effects=effects)
        ev, = P.check_vow(s, 1)
        assert ev["effects"] == ["Poison"]
        names = [(r["name"], r["attribute"]) for r in s["active_effects"]["1"]]
        assert names == [("Bleeding", "bleeding"), ("Stun", "stun"), ("Poison", "paralysis")]

    def test_soft_control_is_removable(self):
        s = _paladin_battle(effects=[row("Knockdown", owner=3, attribute="attack")])
        assert P.check_vow(s, 1)[0]["effects"] == ["Knockdown"]

    def test_only_hard_control_or_own_rows_shield_only(self):
        effects = [row("Stun", owner=3), row("Poison", owner=4, attribute="paralysis"),
                   row("Buff", owner=2), row("Self", owner=1), row("Legacy"),
                   row("Ghost", owner=99)]
        s = _paladin_battle(effects=effects)
        before = copy.deepcopy(s["active_effects"])
        ev, = P.check_vow(s, 1)
        assert "effects" not in ev and ev["value"] == 20
        assert s["active_effects"] == before

    def test_raw_effect_name_rows(self):
        s = _paladin_battle(effects=[{"effect_name": "Curse", "owner_id": 3}])
        assert P.check_vow(s, 1)[0]["effects"] == ["Curse"]

    def test_no_active_effects(self):
        s = _paladin_battle()
        ev, = P.check_vow(s, 1)
        assert "effects" not in ev

    def test_snapshot_hp(self):
        s = battle({1: part(1, hp=50), 2: part(2, hp="x")})
        s["participants"]["bad"] = part(1)
        s["participants"]["3"] = "junk"
        assert P.snapshot_hp(s) == {1: 50, 2: 0.0}
        assert P.snapshot_hp(None) == {}

    def test_check_vows_only_for_hp_loss(self):
        s = _paladin_battle(hp=40)
        before = P.snapshot_hp(s)
        P_(s, 1)["hp"] = 20
        evs = P.check_vows(s, before)
        assert [e["kind"] for e in evs] == ["vow"]

    def test_check_vows_no_loss_no_trigger(self):
        s = _paladin_battle(hp=20)       # already low, but lost nothing now
        assert P.check_vows(s, P.snapshot_hp(s)) == []
        assert "passive_state" not in P_(s, 1)

    def test_check_vows_str_keys_and_garbage(self):
        s = _paladin_battle(hp=20)
        assert len(P.check_vows(s, {"1": 50})) == 1
        assert P.check_vows(s, None) == [] and P.check_vows(s, [1]) == []


# =============================================================================
# H19 — lifesteal
# =============================================================================
class TestLifesteal:
    def test_berserk_below_25(self):
        s = battle({1: part(1, P.PASSIVE_BERSERKER_RAGE, hp=24.9)})
        c = P.lifesteal(s, 1, 100, "physical")
        assert c == {"key": P.PASSIVE_BERSERKER_RAGE, "kind": "lifesteal", "value": 15, "owner": 1}
        assert P_(s, 1)["hp"] == pytest.approx(39.9)

    @pytest.mark.parametrize("hp", [25, 26, 100])
    def test_berserk_at_or_above_25_none(self, hp):
        s = battle({1: part(1, P.PASSIVE_BERSERKER_RAGE, hp=hp)})
        assert P.lifesteal(s, 1, 100, "physical") is None
        assert P_(s, 1)["hp"] == hp

    def test_priest_10pct(self):
        s = battle({1: part(1, P.PASSIVE_PRIEST, hp=50)})
        assert P.lifesteal(s, 1, 40, "fire")["value"] == 4
        assert P_(s, 1)["hp"] == 54

    @pytest.mark.parametrize("dtype", ["sainting", "Sainting", " sainting "])
    def test_priest_holy_15pct(self, dtype):
        s = battle({1: part(1, P.PASSIVE_PRIEST, hp=50)})
        assert P.lifesteal(s, 1, 40, dtype)["value"] == 6

    def test_capped_at_max_hp(self):
        s = battle({1: part(1, P.PASSIVE_PRIEST, hp=98)})
        assert P.lifesteal(s, 1, 100, "physical")["value"] == 2
        assert P_(s, 1)["hp"] == 100

    def test_full_hp_returns_none(self):
        s = battle({1: part(1, P.PASSIVE_PRIEST, hp=100)})
        assert P.lifesteal(s, 1, 100, "physical") is None

    def test_dead_attacker_none(self):
        s = battle({1: part(1, P.PASSIVE_PRIEST, hp=0), 2: part(1, P.PASSIVE_BERSERKER_RAGE, hp=-3)})
        assert P.lifesteal(s, 1, 100, "physical") is None
        assert P.lifesteal(s, 2, 100, "physical") is None
        assert P_(s, 1)["hp"] == 0

    @pytest.mark.parametrize("removed", [0, -5, None, "x"])
    def test_nothing_removed_none(self, removed):
        s = battle({1: part(1, P.PASSIVE_PRIEST, hp=50)})
        assert P.lifesteal(s, 1, removed, "physical") is None

    def test_rounded_value(self):
        s = battle({1: part(1, P.PASSIVE_PRIEST, hp=50)})
        assert P.lifesteal(s, 1, 37, "physical")["value"] == 4   # 3.7 → 4
        assert P_(s, 1)["hp"] == pytest.approx(53.7)

    def test_other_passives_none(self, no_rolls):
        s = battle({1: part(1, P.PASSIVE_GUARDIAN, hp=10), 2: part(1, hp=10)})
        assert P.lifesteal(s, 1, 100, "sainting") is None
        assert P.lifesteal(s, 2, 100, "sainting") is None
        assert P_(s, 1)["hp"] == 10 and "passive_state" not in P_(s, 2)


# =============================================================================
# H20 — retaliate
# =============================================================================
def _guard_battle(att_key=None, att_hp=100, guard_hp=100, same_team=False):
    return battle({1: part(1, att_key, hp=att_hp),
                   7: part(1 if same_team else 2, P.PASSIVE_GUARDIAN, hp=guard_hp)})


class TestRetaliate:
    def test_reflects_15pct(self):
        s = _guard_battle()
        ev, = P.retaliate(s, 7, 1, 40, "fire")
        assert ev == {"event": "damage", "source": 7, "target": 1, "final": 6.0,
                      "damage_type": "fire", "reflected": True, "absorbed": 0,
                      "passives": [{"key": P.PASSIVE_GUARDIAN, "kind": "reflect",
                                    "value": 6, "owner": 7}]}
        assert "critical" not in ev and "dodged" not in ev and "shield_left" not in ev
        assert P_(s, 1)["hp"] == 94
        assert P_(s, 7)["total_damage_dealt"] == 6
        assert P_(s, 1)["total_damage_received"] == 6

    def test_fractional_reflect(self):
        s = _guard_battle()
        ev, = P.retaliate(s, 7, 1, 33, None)
        assert ev["final"] == 4.95 and ev["damage_type"] == "physical"
        assert ev["passives"][0]["value"] == 5
        assert P_(s, 1)["hp"] == pytest.approx(95.05)

    def test_attacker_shield_absorbs(self):
        s = _guard_battle()
        give(s, 1, sh(4))
        ev, = P.retaliate(s, 7, 1, 40, "physical")
        assert ev["absorbed"] == 4 and ev["shield_left"] == 0
        assert P_(s, 1)["hp"] == 98
        # stats count the full reflect, absorbed part included
        assert P_(s, 1)["total_damage_received"] == 6

    def test_can_kill_unclamped(self):
        s = _guard_battle(att_hp=3)
        P.retaliate(s, 7, 1, 40, "physical")
        assert P_(s, 1)["hp"] == -3

    def test_attacker_paladin_vow_follows(self):
        s = _guard_battle(att_key=P.PASSIVE_PALADIN, att_hp=32)
        evs = P.retaliate(s, 7, 1, 40, "physical")
        assert [e["event"] for e in evs] == ["damage", "passive_proc"]
        assert evs[1]["kind"] == "vow" and evs[1]["who"] == 1
        assert P_(s, 1)["hp"] == 26

    def test_fires_when_guardian_killed_by_the_hit(self):
        s = _guard_battle(guard_hp=0)
        assert len(P.retaliate(s, 7, 1, 40, "physical")) == 1

    def test_same_team_nothing(self):
        s = _guard_battle(same_team=True)
        assert P.retaliate(s, 7, 1, 40, "physical") == []
        assert P_(s, 1)["hp"] == 100

    def test_self_nothing(self):
        s = _guard_battle()
        assert P.retaliate(s, 7, 7, 40, "physical") == []

    def test_not_guardian_nothing(self, no_rolls):
        s = battle({1: part(1), 7: part(2, P.PASSIVE_PALADIN)})
        assert P.retaliate(s, 7, 1, 40, "physical") == []
        assert "passive_state" not in P_(s, 1) and "total_damage_dealt" not in P_(s, 7)

    @pytest.mark.parametrize("taken", [0, -10, None, "x"])
    def test_zero_reflect_nothing(self, taken):
        s = _guard_battle()
        assert P.retaliate(s, 7, 1, taken, "physical") == []

    def test_dead_attacker_nothing(self):
        s = _guard_battle(att_hp=0)
        assert P.retaliate(s, 7, 1, 40, "physical") == []
        assert P_(s, 1)["hp"] == 0

    def test_unknown_attacker(self):
        s = _guard_battle()
        assert P.retaliate(s, 7, 99, 40, "physical") == []


# =============================================================================
# land_hit — fixed E7 order
# =============================================================================
class TestLandHit:
    def test_plain_hit_identical_to_old(self, no_rolls):
        s = battle({1: part(1), 2: part(2, hp=100)})
        out = P.land_hit(s, 1, 2, 30, "physical")
        assert P_(s, 2)["hp"] == 70 and type(P_(s, 2)["hp"]) is int
        assert out == {"absorbed": 0.0, "shield_left": 0, "hp_removed": 30.0,
                       "contributions": [], "post_events": []}
        assert "passive_state" not in P_(s, 1) and "passive_state" not in P_(s, 2)

    def test_float_damage(self):
        s = battle({1: part(1), 2: part(2, hp=100)})
        P.land_hit(s, 1, 2, 12.5, "physical")
        assert P_(s, 2)["hp"] == 87.5

    def test_shield_absorbs_before_hp(self):
        s = battle({1: part(1), 2: part(2, hp=100)})
        give(s, 2, sh(10))
        out = P.land_hit(s, 1, 2, 30, "physical")
        assert out["absorbed"] == 10 and out["hp_removed"] == 20 and out["shield_left"] == 0
        assert P_(s, 2)["hp"] == 80

    def test_shield_left_reported(self):
        s = battle({1: part(1), 2: part(2, hp=100)})
        give(s, 2, sh(50))
        out = P.land_hit(s, 1, 2, 30, "physical")
        assert out["shield_left"] == 20 and out["hp_removed"] == 0
        assert P_(s, 2)["hp"] == 100

    def test_overkill_excluded(self):
        s = battle({1: part(1), 2: part(2, hp=10)})
        out = P.land_hit(s, 1, 2, 30, "physical")
        assert out["hp_removed"] == 10 and P_(s, 2)["hp"] == -20

    def test_already_dead_target_removes_nothing(self):
        s = battle({1: part(1, P.PASSIVE_PRIEST, hp=50), 2: part(2, hp=0)})
        out = P.land_hit(s, 1, 2, 30, "physical")
        assert out["hp_removed"] == 0 and out["contributions"] == []

    def test_lifesteal_only_from_hp_removed(self):
        s = battle({1: part(1, P.PASSIVE_PRIEST, hp=50), 2: part(2, hp=100)})
        give(s, 2, sh(50))
        out = P.land_hit(s, 1, 2, 60, "physical")
        assert out["hp_removed"] == 10
        assert out["contributions"] == [{"key": P.PASSIVE_PRIEST, "kind": "lifesteal",
                                         "value": 1, "owner": 1}]
        assert P_(s, 1)["hp"] == 51

    def test_lifesteal_not_from_overkill(self):
        s = battle({1: part(1, P.PASSIVE_PRIEST, hp=50), 2: part(2, hp=10)})
        out = P.land_hit(s, 1, 2, 100, "physical")
        assert out["contributions"][0]["value"] == 1

    def test_target_vow_in_post_events_same_hit_not_absorbed(self):
        s = battle({1: part(1), 2: part(2, P.PASSIVE_PALADIN, hp=35)})
        out = P.land_hit(s, 1, 2, 10, "physical")
        assert P_(s, 2)["hp"] == 25           # this hit is not absorbed by its own vow
        assert [e["kind"] for e in out["post_events"]] == ["vow"]
        assert out["shield_left"] == 0        # computed before the vow (event = this strike)
        assert P.shield_total(P_(s, 2)) == 20

    def test_paladin_40_to_0_no_vow(self):
        s = battle({1: part(1), 2: part(2, P.PASSIVE_PALADIN, hp=40)})
        out = P.land_hit(s, 1, 2, 40, "physical")
        assert out["post_events"] == []

    def test_reflect_counts_absorbed_plus_removed(self):
        s = battle({1: part(1, hp=100), 7: part(2, P.PASSIVE_GUARDIAN, hp=100)})
        give(s, 7, sh(20))
        out = P.land_hit(s, 1, 7, 60, "physical")
        ev, = out["post_events"]
        assert ev["reflected"] is True and ev["final"] == 9.0      # 15% of 60
        assert P_(s, 1)["hp"] == 91

    def test_reflect_excludes_overkill(self):
        s = battle({1: part(1, hp=100), 7: part(2, P.PASSIVE_GUARDIAN, hp=20)})
        out = P.land_hit(s, 1, 7, 100, "physical")
        assert out["post_events"][0]["final"] == 3.0                # 15% of 20
        assert P_(s, 7)["hp"] == -80

    def test_berserk_heals_then_takes_reflect(self):
        """E8: lifesteal first — a 10-HP Berserk survives the reflect."""
        s = battle({1: part(1, P.PASSIVE_BERSERKER_RAGE, hp=10),
                    7: part(2, P.PASSIVE_GUARDIAN, hp=1000)})
        out = P.land_hit(s, 1, 7, 100, "physical")
        assert out["contributions"][0]["value"] == 15
        assert out["post_events"][0]["final"] == 15.0
        assert P_(s, 1)["hp"] == 10

    def test_guardian_vs_guardian_single_reflect(self):
        s = battle({1: part(1, P.PASSIVE_GUARDIAN, hp=100), 7: part(2, P.PASSIVE_GUARDIAN, hp=100)})
        out = P.land_hit(s, 1, 7, 40, "physical")
        refl = [e for e in out["post_events"] if e.get("reflected")]
        assert len(refl) == 1 and refl[0]["source"] == 7 and refl[0]["target"] == 1
        assert P_(s, 7)["hp"] == 60 and P_(s, 1)["hp"] == 94

    def test_reflect_then_attacker_vow_order(self):
        s = battle({1: part(1, P.PASSIVE_PALADIN, hp=32), 7: part(2, P.PASSIVE_GUARDIAN, hp=100)})
        out = P.land_hit(s, 1, 7, 40, "physical")
        assert [(e["event"], e.get("kind")) for e in out["post_events"]] == [
            ("damage", None), ("passive_proc", "vow")]

    def test_reflect_into_attacker_shield(self):
        s = battle({1: part(1, hp=100), 7: part(2, P.PASSIVE_GUARDIAN, hp=100)})
        give(s, 1, sh(100))
        out = P.land_hit(s, 1, 7, 40, "physical")
        ev = out["post_events"][0]
        assert ev["absorbed"] == 6 and ev["shield_left"] == 94 and P_(s, 1)["hp"] == 100

    def test_indirect_only_shield_and_hp(self, no_rolls):
        s = battle({1: part(1, P.PASSIVE_PRIEST, hp=50),
                    2: part(1, P.PASSIVE_PALADIN, hp=35),
                    7: part(1, P.PASSIVE_GUARDIAN, hp=100)})
        give(s, 7, sh(5))
        out2 = P.land_hit(s, 1, 2, 10, "sainting", direct=False)
        out7 = P.land_hit(s, 1, 7, 40, "sainting", direct=False)
        assert out2["post_events"] == [] and out2["contributions"] == []
        assert out7["post_events"] == [] and out7["contributions"] == []
        assert out7["absorbed"] == 5 and P_(s, 7)["hp"] == 65
        assert P_(s, 2)["hp"] == 25 and "vow_used" not in (ps(s, 2) or {})
        assert P_(s, 1)["hp"] == 50

    def test_unknown_target(self):
        s = battle({1: part(1)})
        assert P.land_hit(s, 1, 99, 10, "physical")["hp_removed"] == 0.0


# =============================================================================
# H22 — on_heal («Прилив»)
# =============================================================================
def _auro_battle(target_hp=100, target_max=200):
    return battle({1: part(1, P.PASSIVE_AUROMANCER), 2: part(1, hp=target_hp, max_hp=target_max),
                   3: part(2)})


class TestOnHeal:
    def test_overflow_becomes_tide(self):
        s = _auro_battle()
        evs = P.on_heal(s, 1, 2, 50, 20)
        assert evs == [{"event": "passive_proc", "who": 1, "key": P.PASSIVE_AUROMANCER,
                        "kind": "tide", "target": 2, "value": 30, "shield": 30}]
        e, = shields(s, 2)
        assert (e["owner"], e["amount"], e["cap"], e["turns_left"], e["fresh"]) == (1, 30, 40.0, 3, True)

    def test_capped_at_20pct_of_target_max(self):
        s = _auro_battle()
        assert P.on_heal(s, 1, 2, 500, 0)[0]["value"] == 40

    def test_top_up_and_turns_reset(self):
        s = _auro_battle()
        P.on_heal(s, 1, 2, 30, 0)
        P.tick_shields(s, 1)
        P.tick_shields(s, 1)
        assert shields(s, 2)[0]["turns_left"] == 2
        ev, = P.on_heal(s, 1, 2, 30, 0)
        assert ev["value"] == 10 and ev["shield"] == 40
        e, = shields(s, 2)
        assert (e["amount"], e["turns_left"], e["fresh"]) == (40, 3, True)

    def test_at_cap_no_event_but_turns_reset(self):
        s = _auro_battle()
        P.on_heal(s, 1, 2, 40, 0)
        P.tick_shields(s, 1)
        P.tick_shields(s, 1)
        assert P.on_heal(s, 1, 2, 30, 0) == []
        e, = shields(s, 2)
        assert (e["amount"], e["turns_left"]) == (40, 3)

    def test_self_heal_when_alone(self):
        s = battle({1: part(1, P.PASSIVE_AUROMANCER, hp=100, max_hp=100), 3: part(2)})
        assert P.on_heal(s, 1, 1, 15, 0)[0]["value"] == 15

    def test_two_auromancers_stack(self):
        s = battle({1: part(1, P.PASSIVE_AUROMANCER), 4: part(1, P.PASSIVE_AUROMANCER),
                    2: part(1, max_hp=200)})
        P.on_heal(s, 1, 2, 40, 0)
        P.on_heal(s, 4, 2, 40, 0)
        assert P.shield_total(P_(s, 2)) == 80 and len(shields(s, 2)) == 2

    def test_non_auromancer_healer_nothing(self, no_rolls):
        s = battle({1: part(1, P.PASSIVE_PRIEST), 2: part(1)})
        assert P.on_heal(s, 1, 2, 50, 0) == []
        assert "passive_state" not in P_(s, 2)

    @pytest.mark.parametrize("intended,applied", [(20, 20), (10, 20), (0, 0), ("x", 0), (None, None)])
    def test_no_overflow_nothing(self, intended, applied):
        s = _auro_battle()
        assert P.on_heal(s, 1, 2, intended, applied) == []
        assert "passive_state" not in P_(s, 2)

    def test_dead_target_nothing(self):
        s = _auro_battle(target_hp=0)
        assert P.on_heal(s, 1, 2, 50, 0) == []
        assert P.on_heal(s, 1, 99, 50, 0) == []


# =============================================================================
# H23 — blood price
# =============================================================================
class TestBloodPrice:
    @pytest.mark.parametrize("cost,mana,hp,hp_cost,ok", [
        (10, 0, 16, 15, True),
        (10, 0, 15.9, 15, False),
        (3, 2, 10, 2, True),
        (1, 0, 2, 2, False),
        (1, 0, 3, 2, True),
    ])
    def test_table(self, cost, mana, hp, hp_cost, ok):
        p = part(1, P.PASSIVE_NECROMANCER, hp=hp, mana=mana)
        before = dict(p)
        bp = P.blood_price(p, cost)
        assert bp == {"hp_cost": hp_cost, "mana_paid": mana, "affordable": ok, "waived": False}
        assert p == before            # never mutates

    @pytest.mark.parametrize("cost,mana", [(5, 5), (3, 10), (0, 0), (-1, 0), ("x", 0), (None, 0)])
    def test_enough_mana_or_no_cost_none(self, cost, mana):
        assert P.blood_price(part(1, P.PASSIVE_NECROMANCER, hp=1, mana=mana), cost) is None

    def test_non_necromancer_none(self):
        assert P.blood_price(part(1, P.PASSIVE_CASTER, hp=100, mana=0), 10) is None
        assert P.blood_price(part(1, hp=100, mana=0), 10) is None
        assert P.blood_price(None, 10) is None

    @pytest.mark.parametrize("hp", [0, -7])
    def test_dead_waived(self, hp):
        bp = P.blood_price(part(1, P.PASSIVE_NECROMANCER, hp=hp, mana=3), 10)
        assert bp == {"hp_cost": 0, "mana_paid": 3, "affordable": True, "waived": True}

    def test_garbage_mana_counts_as_zero(self):
        bp = P.blood_price(part(1, P.PASSIVE_NECROMANCER, hp=100, mana="x"), 2)
        assert bp["hp_cost"] == 3 and bp["mana_paid"] == 0

    @pytest.mark.parametrize("shortfall,hp", [(1, 2), (2, 3), (3, 5), (10, 15), (0.5, 1),
                                              (0, 0), (-1, 0), (None, 0), ("x", 0)])
    def test_blood_hp_cost(self, shortfall, hp):
        assert P.blood_hp_cost(shortfall) == hp

    def test_contribution(self):
        assert P.blood_price_contribution(15, 3) == {
            "key": P.PASSIVE_NECROMANCER, "kind": "blood_price", "value": 15, "owner": 3}


# =============================================================================
# H13 — Necromancer kill heal
# =============================================================================
class TestNecroKillHeal:
    def test_heal_per_victim(self):
        s = battle({1: part(1, P.PASSIVE_NECROMANCER, hp=50, max_hp=200), 5: part(2, hp=0),
                    6: part(2, hp=0)})
        evs, stacks = P.on_kills(s, 1, [5, 6, 5])
        assert stacks is None
        assert evs == [
            {"event": "passive_proc", "who": 1, "key": P.PASSIVE_NECROMANCER,
             "kind": "kill_heal", "target": 5, "value": 20},
            {"event": "passive_proc", "who": 1, "key": P.PASSIVE_NECROMANCER,
             "kind": "kill_heal", "target": 6, "value": 20},
        ]
        assert P_(s, 1)["hp"] == 90 and P_(s, 1)["max_hp"] == 200

    def test_capped_and_full_hp_silent(self):
        s = battle({1: part(1, P.PASSIVE_NECROMANCER, hp=195, max_hp=200), 5: part(2, hp=0),
                    6: part(2, hp=0)})
        evs, _ = P.on_kills(s, 1, [5, 6])
        assert [e["value"] for e in evs] == [5]
        assert P_(s, 1)["hp"] == 200

    def test_dead_necro_nothing(self):
        s = battle({1: part(1, P.PASSIVE_NECROMANCER, hp=0), 5: part(2, hp=0)})
        assert P.on_kills(s, 1, [5]) == ([], None)
        assert P_(s, 1)["hp"] == 0

    def test_teammate_victim_ignored(self):
        s = battle({1: part(1, P.PASSIVE_NECROMANCER, hp=50), 2: part(1, hp=0)})
        assert P.on_kills(s, 1, [2]) == ([], None)

    def test_works_outside_dungeon_and_never_persists(self):
        s = battle({1: part(1, P.PASSIVE_NECROMANCER, hp=50), 5: part(2, hp=0)},
                   dungeon_session_id=7)
        evs, stacks = P.on_kills(s, 1, [5])
        assert len(evs) == 1 and stacks is None
        assert "saber_kills" not in (ps(s, 1) or {})

    def test_saber_unchanged(self):
        s = battle({1: part(1, P.PASSIVE_SABER), 5: part(2, hp=0)}, dungeon_session_id=7)
        evs, stacks = P.on_kills(s, 1, [5])
        assert stacks == 1 and evs[0]["kind"] == "saber_kill"
        assert P_(s, 1)["hp"] == 100

    def test_neutral_killer(self, no_rolls):
        s = battle({1: part(1, hp=50), 5: part(2, hp=0)})
        assert P.on_kills(s, 1, [5]) == ([], None)
        assert P_(s, 1)["hp"] == 50 and "passive_state" not in P_(s, 1)


# =============================================================================
# H24 — Bard «Ритм»
# =============================================================================
def _bard_group():
    return battle({1: part(1, P.PASSIVE_BARD), 2: part(1), 3: part(1), 9: part(2)})


def _apps_by_target(apps):
    return {t: (rows, src, en) for t, rows, src, en in apps}


class TestBard:
    def test_group_first_stack(self, no_rolls):
        s = _bard_group()
        apps, evs = P.end_of_action(s, 1, False, [9])
        by = _apps_by_target(apps)
        assert set(by) == {1, 2, 3}
        rows, src, en = by[2]
        assert rows == [{"effect_name": "Вдохновение", "attribute_key": "percent_damage",
                         "magnitude": 3, "duration": 2}]
        assert src == ("passive", P.PASSIVE_BARD) and en is False
        ev, = evs
        assert (ev["kind"], ev["stacks"], ev["value"], ev["mode"]) == ("inspiration", 1, 3, "group")
        assert sorted(ev["targets"]) == [1, 2, 3]
        assert ps(s, 1)["bard_stacks"] == 1 and ps(s, 1)["bard_mode"] == "group"

    def test_group_cap_4(self):
        s = _bard_group()
        for _ in range(6):
            apps, evs = P.end_of_action(s, 1, False, [])
        assert evs[0]["stacks"] == 4 and evs[0]["value"] == 12
        assert all(rows[0]["magnitude"] == 12 for _, rows, _, _ in apps)

    def test_solo_5pct_cap_3(self):
        s = battle({1: part(1, P.PASSIVE_BARD), 2: part(1, hp=0), 3: part(1, dropped_out=True),
                    9: part(2)})
        apps, evs = P.end_of_action(s, 1, False, [])
        assert [t for t, *_ in apps] == [1] and evs[0]["value"] == 5 and evs[0]["mode"] == "solo"
        for _ in range(4):
            apps, evs = P.end_of_action(s, 1, False, [])
        assert evs[0]["stacks"] == 3 and evs[0]["value"] == 15 and evs[0]["targets"] == [1]

    def test_group_to_solo_clamps(self):
        s = battle({1: part(1, P.PASSIVE_BARD), 2: part(1), 9: part(2)})
        for _ in range(4):
            P.end_of_action(s, 1, False, [])
        assert ps(s, 1)["bard_stacks"] == 4
        P_(s, 2)["hp"] = 0                       # mode decided at application
        _, evs = P.end_of_action(s, 1, False, [])
        assert (evs[0]["stacks"], evs[0]["value"], evs[0]["mode"]) == (3, 15, "solo")
        P_(s, 2)["hp"] = 50                      # back to group: 3 → 4
        _, evs = P.end_of_action(s, 1, False, [])
        assert (evs[0]["stacks"], evs[0]["value"], evs[0]["mode"]) == (4, 12, "group")

    def test_skipped_turn_refreshes_without_stack(self):
        s = _bard_group()
        P.end_of_action(s, 1, False, [])
        P.end_of_action(s, 1, False, [])
        apps, evs = P.end_of_action(s, 1, True, [])
        assert evs[0]["stacks"] == 2 and len(apps) == 3
        assert ps(s, 1)["bard_stacks"] == 2

    def test_skipped_with_zero_stacks_nothing(self):
        s = _bard_group()
        assert P.end_of_action(s, 1, True, []) == ([], [])

    def test_dead_bard_nothing(self):
        s = _bard_group()
        P_(s, 1)["hp"] = 0
        assert P.end_of_action(s, 1, False, []) == ([], [])

    def test_garbage_stacks(self):
        s = _bard_group()
        P_(s, 1)["passive_state"] = {"bard_stacks": "x"}
        _, evs = P.end_of_action(s, 1, False, [])
        assert evs[0]["stacks"] == 1


# =============================================================================
# H24 — Etheriad «Шёпот духов»
# =============================================================================
def _eth(**hp):
    """Etheriad 1, allies 2/3, enemies 8/9; hp overrides as h2=…"""
    s = battle({1: part(1, P.PASSIVE_ETHERIAD), 2: part(1), 3: part(1), 8: part(2), 9: part(2)})
    for k, v in hp.items():
        P_(s, int(k[1:]))["hp"] = v
    return s


class TestEtheriad:
    def test_p1_most_beaten_ally_ward_no_roll(self, no_rolls):
        s = _eth(h2=40, h3=30)
        apps, evs = P.end_of_action(s, 1, False, [8])
        (t, rows, src, en), = apps
        assert t == 3 and en is False and src == ("passive", P.PASSIVE_ETHERIAD)
        assert rows == [{"effect_name": "Шёпот духов: стойкость", "attribute_key": "percent_resist_all",
                         "magnitude": 8, "duration": 2}]
        assert evs == [{"event": "passive_proc", "who": 1, "key": P.PASSIVE_ETHERIAD,
                        "kind": "spirit_whisper", "target": 3, "mode": "ward", "value": 8}]

    def test_p1_tie_lowest_pid(self, no_rolls):
        s = _eth(h2=30, h3=30)
        assert P.end_of_action(s, 1, False, [])[0][0][0] == 2

    def test_p1_exactly_50_not_low(self):
        s = _eth(h2=50, h3=50)
        with picks(0):
            apps, evs = P.end_of_action(s, 1, False, [8])
        assert evs[0]["mode"] == "curse"

    def test_p1_ignores_etheriad_himself_when_allies_exist(self):
        s = _eth(h1=10)
        with picks(0):
            _, evs = P.end_of_action(s, 1, False, [])
        assert evs[0]["mode"] == "might" and evs[0]["target"] in (2, 3)

    @pytest.mark.parametrize("idx", [0, 1])
    def test_p2_curse_landed_enemy(self, idx):
        s = _eth()
        with picks(idx) as seen:
            apps, evs = P.end_of_action(s, 1, False, [8, 9])
        assert sorted(seen[0]) == [8, 9]
        (t, rows, _, en), = apps
        assert t == seen[0][idx] and en is True
        assert rows[0]["effect_name"] == "Шёпот духов: уязвимость" and rows[0]["magnitude"] == -8
        assert rows[0]["attribute_key"] == "percent_resist_all"
        assert (evs[0]["mode"], evs[0]["value"]) == ("curse", -8)

    def test_p2_skips_already_cursed_and_dead_and_unlanded(self):
        s = _eth(h9=0)
        s["active_effects"] = {"8": [{"name": "Шёпот духов: уязвимость", "attribute": "percent_resist_all",
                                      "magnitude": -8, "duration": 2, "source": P.SOURCE_ETHERIAD,
                                      "owner_id": 1}]}
        with picks(0) as seen:
            _, evs = P.end_of_action(s, 1, False, [8, 9])
        # 8 cursed, 9 dead → nothing to curse → might on an ally
        assert evs[0]["mode"] == "might" and sorted(seen[0]) == [2, 3]

    def test_p2_same_name_from_other_source_not_a_curse(self):
        s = _eth()
        s["active_effects"] = {"8": [{"name": "Шёпот духов: уязвимость", "attribute": "percent_resist_all",
                                      "magnitude": -8, "duration": 2, "owner_id": 1}]}
        with picks(0):
            _, evs = P.end_of_action(s, 1, False, [8])
        assert evs[0]["mode"] == "curse" and evs[0]["target"] == 8

    def test_p3_might(self):
        s = _eth()
        with picks(1) as seen:
            apps, evs = P.end_of_action(s, 1, False, [])
        assert sorted(seen[0]) == [2, 3]
        (t, rows, _, en), = apps
        assert t == seen[0][1] and en is False
        assert rows[0]["attribute_key"] == "percent_damage" and rows[0]["magnitude"] == 8
        assert rows[0]["effect_name"] == "Шёпот духов: сила"

    def test_alone_ward_self(self, no_rolls):
        s = battle({1: part(1, P.PASSIVE_ETHERIAD, hp=40), 2: part(1, hp=0), 8: part(2)})
        apps, evs = P.end_of_action(s, 1, False, [])
        assert apps[0][0] == 1 and evs[0]["mode"] == "ward"

    def test_alone_might_self(self):
        s = battle({1: part(1, P.PASSIVE_ETHERIAD), 8: part(2)})
        with picks(0) as seen:
            apps, evs = P.end_of_action(s, 1, False, [])
        assert seen == [[1]] and apps[0][0] == 1 and evs[0]["mode"] == "might"

    def test_skipped_silent(self, no_rolls):
        s = _eth(h2=10)
        assert P.end_of_action(s, 1, True, [8]) == ([], [])

    def test_dead_etheriad_silent(self, no_rolls):
        s = _eth(h1=0)
        assert P.end_of_action(s, 1, False, [8]) == ([], [])


class TestEndOfActionNeutral:
    @pytest.mark.parametrize("key", [None, P.PASSIVE_GUARDIAN, P.PASSIVE_PRIEST, "unknown_key"])
    def test_others_nothing(self, key, no_rolls):
        s = battle({1: part(1, key), 2: part(1, hp=10), 8: part(2)})
        assert P.end_of_action(s, 1, False, [8]) == ([], [])
        assert "passive_state" not in P_(s, 1)


# =============================================================================
# Passive rows through the REAL buffs module
# =============================================================================
class TestPassiveRowsThroughBuffs:
    def _apply(self, s, actor, apps):
        for t, rows, src, en in apps:
            B.apply_new_effects(s, t, rows, is_enemy=en, owner_pid=actor, source=src)

    def test_bard_rows_refresh_in_place_and_count_as_damage(self):
        s = _bard_group()
        for _ in range(3):
            apps, _ = P.end_of_action(s, 1, False, [])
            self._apply(s, 1, apps)
        for pid in ("1", "2", "3"):
            lst = s["active_effects"][pid]
            assert len(lst) == 1
            assert lst[0]["magnitude"] == 9 and lst[0]["source"] == P.SOURCE_BARD
            assert B.build_percent_damage_buffs(B.aggregate_modifiers(lst)) == {"all": 9}

    def test_etheriad_curse_row_blocks_second_curse(self):
        s = _eth()
        with picks(0):
            apps, _ = P.end_of_action(s, 1, False, [8])
        self._apply(s, 1, apps)
        row_, = s["active_effects"]["8"]
        assert row_["magnitude"] == -8 and row_["source"] == P.SOURCE_ETHERIAD
        assert B.aggregate_modifiers([row_]) == {"percent_resist_all": -8}
        with picks(0):
            _, evs = P.end_of_action(s, 1, False, [8])
        assert evs[0]["mode"] == "might"

    def test_on_deaths_removes_applied_bard_rows(self):
        s = _bard_group()
        apps, _ = P.end_of_action(s, 1, False, [])
        self._apply(s, 1, apps)
        evs = P.on_deaths(s, [1])
        assert evs == [{"event": "passive_proc", "who": 1, "key": P.PASSIVE_BARD,
                        "kind": "inspiration_end", "targets": [1, 2, 3]}]
        assert all(lst == [] for lst in s["active_effects"].values())


# =============================================================================
# H25 — on_deaths
# =============================================================================
def _eff(name, owner, source=None):
    r = {"name": name, "attribute": "percent_damage", "magnitude": 3, "duration": 2, "owner_id": owner}
    if source:
        r["source"] = source
    return r


class TestOnDeaths:
    def _state(self):
        s = battle({1: part(1, P.PASSIVE_BARD), 2: part(1), 4: part(1, P.PASSIVE_BARD),
                    5: part(1, P.PASSIVE_ETHERIAD), 6: part(1, P.PASSIVE_AUROMANCER), 9: part(2)})
        P_(s, 1)["passive_state"] = {"bard_stacks": 3}
        s["active_effects"] = {
            "1": [_eff("Вдохновение", 1, P.SOURCE_BARD), _eff("Skill", 1)],
            "2": [_eff("Вдохновение", 1, P.SOURCE_BARD), _eff("Вдохновение", 4, P.SOURCE_BARD),
                  _eff("Шёпот духов: сила", 5, P.SOURCE_ETHERIAD)],
            "9": [_eff("Шёпот духов: уязвимость", 5, P.SOURCE_ETHERIAD), _eff("Item", 1, "item:3")],
        }
        give(s, 2, sh(10, owner=6), sh(20, owner=2, key=P.PASSIVE_PALADIN, turns_left=None))
        give(s, 6, sh(5, owner=6))
        return s

    def test_dead_bard(self):
        s = self._state()
        evs = P.on_deaths(s, [1])
        assert evs == [{"event": "passive_proc", "who": 1, "key": P.PASSIVE_BARD,
                        "kind": "inspiration_end", "targets": [1, 2]}]
        names = {k: [(r["name"], r["owner_id"]) for r in v] for k, v in s["active_effects"].items()}
        assert names == {"1": [("Skill", 1)],
                         "2": [("Вдохновение", 4), ("Шёпот духов: сила", 5)],
                         "9": [("Шёпот духов: уязвимость", 5), ("Item", 1)]}
        assert ps(s, 1)["bard_stacks"] == 0
        assert len(shields(s, 2)) == 2

    def test_dead_etheriad_rows_removed_no_event(self):
        s = self._state()
        assert P.on_deaths(s, [5]) == []
        assert [r["name"] for r in s["active_effects"]["9"]] == ["Item"]
        assert [r["owner_id"] for r in s["active_effects"]["2"]] == [1, 4]

    def test_dead_auromancer_shields_everywhere(self):
        s = self._state()
        P.on_deaths(s, [6])
        assert [e["owner"] for e in shields(s, 2)] == [2]
        assert shields(s, 6) == []

    def test_shields_on_dead_holder_removed(self):
        s = self._state()
        P.on_deaths(s, [2])
        assert shields(s, 2) == [] and len(shields(s, 6)) == 1

    def test_str_pids_and_multiple(self):
        s = self._state()
        evs = P.on_deaths(s, ["1", 4])
        assert [e["who"] for e in evs] == [1, 4]

    def test_dead_bard_without_rows_no_event(self):
        s = battle({1: part(1, P.PASSIVE_BARD), 2: part(1)})
        assert P.on_deaths(s, [1]) == []
        assert "passive_state" not in P_(s, 1)

    def test_neutral_deaths_change_nothing(self, no_rolls):
        s = self._state()
        before = copy.deepcopy(s)
        assert P.on_deaths(s, [9]) == []
        assert s == before

    @pytest.mark.parametrize("state,pids", [
        (None, [1]), ([], [1]), ({}, [1]), ({"participants": None, "active_effects": None}, [1]),
        ({"participants": {"1": "x"}, "active_effects": {"1": "x", "2": ["junk", None]}}, [1]),
        ({"participants": {}}, None), ({"participants": {}}, []), ({"participants": {}}, [None]),
    ])
    def test_garbage(self, state, pids):
        assert P.on_deaths(state, pids) == []


# =============================================================================
# H6 — Trickster redirect
# =============================================================================
class TestRedirect:
    def _state(self):
        # attacker 1 (team 1) with allies 2, 3 alive, 4 dead, 5 dropped; Trickster 7 (team 2)
        return battle({1: part(1), 2: part(1), 3: part(1), 4: part(1, hp=0),
                       5: part(1, dropped_out=True), 7: part(2, P.PASSIVE_TRICKSTER), 8: part(2)})

    @pytest.mark.parametrize("idx", [0, 1])
    def test_picks_living_teammate_of_attacker(self, idx):
        s = self._state()
        with picks(idx) as seen:
            r = P.deceit_redirect_target(s, 1, 7)
        assert sorted(seen[0]) == [2, 3] and r == seen[0][idx]

    def test_lone_attacker_none_no_roll(self, no_rolls):
        s = battle({1: part(1), 2: part(1, hp=0), 7: part(2, P.PASSIVE_TRICKSTER)})
        assert P.deceit_redirect_target(s, 1, 7) is None

    def test_non_trickster_none_no_roll(self, no_rolls):
        s = self._state()
        P_(s, 7)["passive_key"] = P.PASSIVE_GUARDIAN
        assert P.deceit_redirect_target(s, 1, 7) is None
        assert P.deceit_redirect_target(s, 1, 99) is None

    def test_contribution(self):
        assert P.redirect_contribution(7) == {"key": P.PASSIVE_TRICKSTER, "kind": "redirect",
                                              "value": 50, "owner": 7}


# =============================================================================
# buffs.py callbacks — through the REAL buffs module
# =============================================================================
def _bstate():
    return {
        "participants": {
            "1": {"team": 1, "hp": 50, "max_hp": 100, "mana": 10, "max_mana": 50,
                  "energy": 5, "max_energy": 50, "stamina": 5, "max_stamina": 50},
            "2": {"team": 2, "hp": 80, "max_hp": 100, "mana": 10, "max_mana": 50,
                  "energy": 5, "max_energy": 50, "stamina": 5, "max_stamina": 50},
        },
        "active_effects": {},
    }


def _closures(state, log=None):
    """main.py-shaped closures: absorb_fn → passives.absorb, overheal_fn → on_heal."""
    def absorb_fn(pid, amount):
        rem, ab = P.absorb(state, pid, amount)
        if log is not None:
            log.append(("absorb", pid, amount, ab))
        return rem

    def overheal_fn(pid, intended, applied, owner):
        if log is not None:
            log.append(("overheal", pid, intended, applied, owner))
        if log is not None:
            log.extend(P.on_heal(state, owner, pid, intended, applied))
        else:
            P.on_heal(state, owner, pid, intended, applied)

    return absorb_fn, overheal_fn


_ROWS_ENEMY = [
    {"effect_name": "Hit", "attribute_key": "hp", "magnitude": 7, "duration": 1},
    {"effect_name": "Drain", "attribute_key": "hp", "magnitude": 4, "duration": 3},
    {"effect_name": "ManaBurn", "attribute_key": "mana", "magnitude": 3, "duration": 1},
    {"effect_name": "Bleeding", "magnitude": 5, "duration": 3},
]
_ROWS_ALLY = [
    {"effect_name": "Heal", "attribute_key": "hp", "magnitude": 30, "duration": 1},
    {"effect_name": "Regen", "attribute_key": "hp", "magnitude": 10, "duration": 3},
    {"effect_name": "Focus", "attribute_key": "mana", "magnitude": 5, "duration": 2},
    {"effect_name": "Buff: all", "magnitude": 10, "duration": 2},
]


def _scenario(kwargs_for):
    """Applies enemy and ally rows, clears `fresh`, ticks both owners; returns
    the final state and the tick events. `kwargs_for(state)` → extra kwargs."""
    s = _bstate()
    B.apply_new_effects(s, 2, copy.deepcopy(_ROWS_ENEMY), is_enemy=True, owner_pid=1,
                        **kwargs_for(s))
    B.apply_new_effects(s, 1, copy.deepcopy(_ROWS_ALLY), owner_pid=1, **kwargs_for(s))
    for lst in s["active_effects"].values():
        for e in lst:
            e.pop("fresh", None)
    events = []
    for _ in range(2):
        events += B.tick_periodic_effects(s, 1, **kwargs_for(s))
    return s, events


class TestBuffsCallbacks:
    def test_defaults_byte_identical(self):
        base = _scenario(lambda s: {})
        explicit = _scenario(lambda s: {"absorb_fn": None, "overheal_fn": None})
        # wired closures but no shields / no Auromancer → identical as well
        wired = _scenario(lambda s: dict(zip(("absorb_fn", "overheal_fn"), _closures(s))))
        assert dump(base) == dump(explicit) == dump(wired)
        s, events = base
        assert s["participants"]["2"]["hp"] == 80 - 7 - 4 - 4 - 5 - 4 - 5
        assert all("passive_state" not in p for p in s["participants"].values())

    def test_instant_enemy_hp_row_absorbed(self):
        s = _bstate()
        give(s, 2, sh(4))
        a, o = _closures(s)
        B.apply_new_effects(s, 2, [{"effect_name": "Hit", "attribute_key": "hp",
                                    "magnitude": 10, "duration": 1}], is_enemy=True, owner_pid=1,
                            absorb_fn=a, overheal_fn=o)
        assert s["participants"]["2"]["hp"] == 74 and shields(s, 2) == []

    def test_absorb_fn_not_called_for_heals_or_other_resources(self):
        s = _bstate()
        log = []
        a, o = _closures(s, log)
        B.apply_new_effects(s, 2, [{"effect_name": "Burn", "attribute_key": "mana",
                                    "magnitude": 3, "duration": 1}], is_enemy=True,
                            owner_pid=1, absorb_fn=a, overheal_fn=o)
        B.apply_new_effects(s, 1, [{"effect_name": "Heal", "attribute_key": "hp",
                                    "magnitude": 5, "duration": 1}], owner_pid=1,
                            absorb_fn=a, overheal_fn=o)
        B.apply_new_effects(s, 1, [{"effect_name": "Mana", "attribute_key": "mana",
                                    "magnitude": 5, "duration": 1}], owner_pid=1,
                            absorb_fn=a, overheal_fn=o)
        assert [x for x in log if x[0] == "absorb"] == []
        assert [x[:2] for x in log if x[0] == "overheal"] == [("overheal", 1)]

    def test_dot_fully_absorbed(self):
        s = _bstate()
        give(s, 2, sh(10))
        a, o = _closures(s)
        B.apply_new_effects(s, 2, [{"effect_name": "Bleeding", "magnitude": 5, "duration": 3}],
                            is_enemy=True, owner_pid=1)
        s["active_effects"]["2"][0].pop("fresh")
        ev, = B.tick_periodic_effects(s, 1, absorb_fn=a, overheal_fn=o)
        assert ev["amount"] == 0 and s["participants"]["2"]["hp"] == 80
        assert shields(s, 2)[0]["amount"] == 5
        assert s["active_effects"]["2"][0]["magnitude"] == 5

    def test_dot_partially_absorbed(self):
        s = _bstate()
        give(s, 2, sh(3))
        a, o = _closures(s)
        B.apply_new_effects(s, 2, [{"effect_name": "Bleeding", "magnitude": 5, "duration": 3}],
                            is_enemy=True, owner_pid=1)
        s["active_effects"]["2"][0].pop("fresh")
        ev, = B.tick_periodic_effects(s, 1, absorb_fn=a, overheal_fn=o)
        assert ev["amount"] == 2 and s["participants"]["2"]["hp"] == 78
        assert s["participants"]["2"]["total_damage_received"] == 2
        assert shields(s, 2) == []

    def test_negative_hp_dose_stored_magnitude_never_absorbed(self):
        s = _bstate()
        give(s, 2, sh(15))
        a, o = _closures(s)
        B.apply_new_effects(s, 2, [{"effect_name": "Drain", "attribute_key": "hp",
                                    "magnitude": 10, "duration": 3}], is_enemy=True, owner_pid=1,
                            absorb_fn=a, overheal_fn=o)
        eff, = s["active_effects"]["2"]
        assert s["participants"]["2"]["hp"] == 80          # dose 1 fully absorbed
        assert eff["magnitude"] == -10                      # stored dose untouched
        eff.pop("fresh")
        ev, = B.tick_periodic_effects(s, 1, absorb_fn=a, overheal_fn=o)
        assert ev["amount"] == 5 and s["participants"]["2"]["hp"] == 75   # 5 left in shield
        assert eff["magnitude"] == -10
        ev, = B.tick_periodic_effects(s, 1, absorb_fn=a, overheal_fn=o)
        assert ev["amount"] == 10 and s["participants"]["2"]["hp"] == 65
        assert eff["magnitude"] == -10

    def test_hot_overheal_reported_incl_full_hp_early_return(self):
        s = _bstate()
        s["participants"]["1"]["passive_key"] = P.PASSIVE_AUROMANCER
        s["participants"]["3"] = {"team": 1, "hp": 990, "max_hp": 1000}
        log = []
        a, o = _closures(s, log)
        B.apply_new_effects(s, 3, [{"effect_name": "Regen", "attribute_key": "hp",
                                    "magnitude": 30, "duration": 3}], owner_pid=1,
                            absorb_fn=a, overheal_fn=o)
        assert ("overheal", 3, 30, 10, 1) in log
        assert P.shield_total(s["participants"]["3"]) == 20
        s["active_effects"]["3"][0].pop("fresh")
        events = B.tick_periodic_effects(s, 1, absorb_fn=a, overheal_fn=o)
        assert events == []                                  # full HP → no resource_tick
        assert ("overheal", 3, 30, 0, 1) in log              # reported before the early return
        assert P.shield_total(s["participants"]["3"]) == 50
        tides = [e for e in log if isinstance(e, dict)]
        assert [t["value"] for t in tides] == [20, 30]

    def test_overheal_not_called_for_dead_target(self):
        s = _bstate()
        log = []
        a, o = _closures(s, log)
        B.apply_new_effects(s, 1, [{"effect_name": "Regen", "attribute_key": "hp",
                                    "magnitude": 10, "duration": 3}], owner_pid=1,
                            absorb_fn=a, overheal_fn=o)
        log.clear()
        s["participants"]["1"]["hp"] = 0
        s["active_effects"]["1"][0].pop("fresh")
        assert B.tick_periodic_effects(s, 1, absorb_fn=a, overheal_fn=o) == []
        assert log == []

    def test_non_auromancer_overheal_creates_nothing(self):
        s = _bstate()
        s["participants"]["1"]["hp"] = 100
        a, o = _closures(s)
        B.apply_new_effects(s, 1, [{"effect_name": "Heal", "attribute_key": "hp",
                                    "magnitude": 30, "duration": 1}], owner_pid=1,
                            absorb_fn=a, overheal_fn=o)
        assert "passive_state" not in s["participants"]["1"]


# =============================================================================
# Neutral participants: no rolls, no state; garbage never raises
# =============================================================================
class TestNeutralAndGarbage:
    def test_neutral_battle_no_rolls_no_state(self, no_rolls):
        s = battle({1: part(1, hp=20), 2: part(1, hp=20), 3: part(2, hp=20), 4: part(2, hp=0)})
        s["active_effects"] = {"1": [_eff("X", 3)]}
        before = P.snapshot_hp(s)
        P_(s, 1)["hp"] = 10
        assert P.check_vows(s, before) == []
        for pid in (1, 2, 3):
            assert P.shield_total(P_(s, pid)) == 0
            assert P.absorb(s, pid, 5) == (5, 0.0)
            assert P.check_vow(s, pid) == []
            assert P.lifesteal(s, pid, 50, "sainting") is None
            assert P.end_of_action(s, pid, False, [3]) == ([], [])
            assert P.blood_price(P_(s, pid), 99) is None
            assert P.on_heal(s, pid, 2, 50, 0) == []
            assert P.on_kills(s, pid, [4]) == ([], None)
        assert P.retaliate(s, 3, 1, 50, "physical") == []
        assert P.deceit_redirect_target(s, 3, 1) is None
        out = P.land_hit(s, 3, 1, 4, "physical")
        assert out["post_events"] == [] and out["contributions"] == []
        P.tick_shields(s, 1)
        assert P.on_deaths(s, [4]) == []
        assert all("passive_state" not in p for p in s["participants"].values())

    @pytest.mark.parametrize("state", [
        None, [], "x", {}, {"participants": None}, {"participants": []},
        {"participants": {"1": None, "2": "x", "3": {"hp": "x", "passive_key": P.PASSIVE_PALADIN,
                                                     "passive_state": "garbage"}}},
        {"participants": {"1": {"team": 1, "hp": 10, "max_hp": "x", "passive_key": P.PASSIVE_BARD,
                                "passive_state": {"shields": "x", "bard_stacks": None}},
                          "2": {"hp": None, "passive_key": P.PASSIVE_ETHERIAD}},
         "active_effects": "garbage"},
    ])
    def test_hooks_never_raise(self, state):
        for pid in (1, 2, 3, "x", None):
            P.absorb(state, pid, 5)
            P.add_shield(state, pid, P.PASSIVE_AUROMANCER, 1, 5, 5, 3)
            P.check_vow(state, pid)
            P.lifesteal(state, pid, 5, None)
            P.retaliate(state, pid, 1, 5, None)
            P.land_hit(state, 1, pid, 5, None)
            P.on_heal(state, pid, 1, 5, 0)
            P.end_of_action(state, pid, False, None)
            P.end_of_action(state, pid, True, "garbage")
            P.deceit_redirect_target(state, 1, pid)
            P.on_kills(state, pid, [1, 2])
            P.shield_absorb_event(state, pid, 5)
            P.tick_shields(state, pid)
        P.snapshot_hp(state)
        P.check_vows(state, {1: 100, 2: 100, 3: 100})
        P.on_deaths(state, [1, 2, 3])
