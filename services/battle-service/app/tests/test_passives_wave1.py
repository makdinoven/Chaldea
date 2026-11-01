"""FEAT-189 (Task #6) — unit tests for subclass passives wave 1.

Pure tests of ``passives.py`` (hooks H0–H13 for the 13 wave-1 passives) and
of the three new optional kwargs of ``battle_engine.compute_damage_with_rolls``
(``force_crit``, ``crit_damage_bonus``, ``resist_ignore``).

Both modules are loaded from their files under PRIVATE names, so the
``MagicMock``s other test files park in ``sys.modules["battle_engine"]`` /
``sys.modules["buffs"]`` can't leak in (the project's silent-failure pattern).
Nothing here imports ``main`` — the pipeline wiring is Task #7.

Randomness: ``passives.roll_pct`` / ``passives.pick`` are the only random
sources of the module; every chance passive is pinned in BOTH directions by
patching them. The ``no_rolls`` fixture turns any roll into an
``AssertionError`` — used to prove that participants without the passive never
consume a roll.
"""

import importlib.util
import os
import re
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def _load_private(module_name, filename):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(APP_DIR, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = _load_private("_feat189_passives", "passives.py")
E = _load_private("_feat189_battle_engine", "battle_engine.py")
assert not isinstance(E.compute_damage_with_rolls, MagicMock)


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


def landed(dtype="physical", crit=False, final=5.0):
    return {"damage_type": dtype, "dodged": False, "hit_chance_failed": False,
            "critical": crit, "final": final}


DODGED = {"damage_type": "physical", "dodged": True}
HIT_FAILED = {"damage_type": "physical", "dodged": False, "hit_chance_failed": True}


def ps(state, pid):
    return state["participants"][str(pid)].get("passive_state")


def one_attack(state, attacker, primary, types=("physical",), strikes=None):
    """begin → record strikes [(target, dmg, log, attrs)] → finish."""
    actx = P.begin_attack(state, attacker, primary, list(types))
    for tgt, dmg, log, attrs in (strikes or []):
        P.record_strike(actx, tgt, dmg, log, target_attrs=attrs)
    events = P.finish_attack(actx, state)
    return actx, events


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
def rolls(result, pick_index=0):
    """roll_pct → `result` (bool or list of bools); pick → seq[pick_index]."""
    side = list(result) if isinstance(result, (list, tuple)) else None
    with patch.object(P, "roll_pct", **({"side_effect": side} if side is not None
                                       else {"return_value": result})) as rp, \
            patch.object(P, "pick", side_effect=lambda seq: list(seq)[pick_index]) as pk:
        yield rp, pk


# =============================================================================
# Guards / H0 helpers
# =============================================================================
class TestModuleGuards:
    def test_passives_imports_neither_buffs_nor_battle_engine(self):
        with open(os.path.join(APP_DIR, "passives.py"), encoding="utf-8") as fh:
            src = fh.read()
        assert not re.search(r"^\s*(import|from)\s+(buffs|battle_engine)\b", src, re.M)
        assert not re.search(r"^\s*from\s+\.\s*import\s+(buffs|battle_engine)", src, re.M)
        assert "buffs" not in vars(P) and "battle_engine" not in vars(P)

    def test_implemented_set_is_all_21(self):
        # FEAT-190: wave 2 made the remaining 7 live — every registry passive
        # now has an effect in battle (registry parity: test_subclass_passives).
        assert P.IMPLEMENTED_PASSIVES == frozenset({
            # FEAT-188 + wave 1 (FEAT-189)
            "berserker_rage", "inquisitor_heresy_seal", "saber_monster_hunter",
            "gladiator_arena", "agent_weak_spot", "lancer_pin", "mechanic_shrapnel",
            "archer_first_blood", "assassin_from_shadow", "trickster_deceit",
            "monk_harmony", "salamander_kindling", "caster_pure_energy",
            "sparkmage_chain_lightning",
            # wave 2 (FEAT-190)
            "paladin_sacred_vow", "guardian_retribution", "bard_rhythm",
            "necromancer_blood_price", "etheriad_spirit_whisper", "auromancer_tide",
            "priest_faith",
        })
        assert len(P.IMPLEMENTED_PASSIVES) == 21

    def test_type_sets_match_buffs_copies(self):
        buffs = _load_private("_feat189_buffs", "buffs.py")
        assert P.PHYSICAL_TYPES == frozenset(buffs._PHYSICAL_TYPES)
        assert P.RESOURCE_ATTRS == frozenset(buffs.RESOURCE_ATTRS)
        assert set(P.NON_PHYSICAL_TYPES) == {
            "magic", "fire", "ice", "watering", "electricity", "wind", "sainting", "damning"}


class TestRollGates:
    @pytest.mark.parametrize("pct", [0, -5, None, "abc", float("nan"), float("-inf")])
    def test_roll_pct_never_true_without_consuming(self, pct):
        with patch.object(P, "_rng") as rng:
            rng.random.side_effect = _boom
            assert P.roll_pct(pct) is False

    @pytest.mark.parametrize("pct", [100, 150, "100"])
    def test_roll_pct_always_true_without_consuming(self, pct):
        with patch.object(P, "_rng") as rng:
            rng.random.side_effect = _boom
            assert P.roll_pct(pct) is True

    def test_roll_pct_uses_module_rng(self):
        with patch.object(P, "_rng") as rng:
            rng.random.return_value = 0.299
            assert P.roll_pct(30) is True
            rng.random.return_value = 0.30
            assert P.roll_pct(30) is False

    def test_pick(self):
        assert P.pick([]) is None and P.pick(None) is None
        with patch.object(P, "_rng") as rng:
            rng.choice.side_effect = lambda items: items[-1]
            assert P.pick((4, 5, 6)) == 6

    def test_pstate_lazy_and_reader_doesnt_create(self):
        p = {"team": 0}
        assert P._ps_read(p) == {} and "passive_state" not in p
        assert P.pstate(p) is p["passive_state"]
        p2 = {"passive_state": "garbage"}
        assert P.pstate(p2) == {} and p2["passive_state"] == {}
        assert P.pstate(None) == {}


class TestControlKind:
    @pytest.mark.parametrize("row,kind", [
        ({"effect_name": "Stun", "duration": 1}, "hard"),
        ({"name": "Stun", "attribute": "stun"}, "hard"),
        ({"effect_name": "Poison", "attribute_key": "paralysis"}, "hard"),
        ({"name": "Poison", "attribute": "paralysis"}, "hard"),
        ({"effect_name": "Poison", "attribute_key": "hp"}, None),
        ({"effect_name": "Knockdown", "attribute_key": "random"}, "soft"),
        ({"name": "Knockdown", "attribute": "dodge"}, "soft"),
        ({"effect_name": "Windburn", "attribute_key": "random"}, "soft"),
        ({"effect_name": "Bleeding"}, None),
        ({"effect_name": "Burn"}, None),
        ({}, None), (None, None), ("Stun", None),
    ])
    def test_classification(self, row, kind):
        assert P.control_kind(row) == kind


class TestResolveEntryType:
    MAGIC_WEAPONS = {"main_weapon": {"primary_damage_type": "magic"},
                     "additional_weapons": {"primary_damage_type": "fire"}}

    def test_explicit_type_passthrough(self):
        assert P.resolve_entry_type({"damage_type": "ice"}, self.MAGIC_WEAPONS) == "ice"

    def test_all_resolves_to_main_weapon(self):
        assert P.resolve_entry_type({"damage_type": "all"}, self.MAGIC_WEAPONS) == "magic"

    def test_all_respects_weapon_slot(self):
        assert P.resolve_entry_type(
            {"damage_type": "all", "weapon_slot": "additional_weapons"}, self.MAGIC_WEAPONS) == "fire"

    def test_all_unarmed_or_no_weapon_slot_is_physical(self):
        assert P.resolve_entry_type({"damage_type": "all"}, None) == "physical"
        assert P.resolve_entry_type({"damage_type": "all", "weapon_slot": "no_weapon"},
                                    self.MAGIC_WEAPONS) == "physical"
        # items default to no_weapon
        assert P.resolve_entry_type({"damage_type": "all"}, self.MAGIC_WEAPONS,
                                    default_slot="no_weapon") == "physical"

    def test_garbage(self):
        assert P.resolve_entry_type(None, None) == "physical"
        assert P.resolve_entry_type({}, None) == "physical"


# =============================================================================
# Neutral participants / old states
# =============================================================================
ALL_HOOKS_ROW = {"effect_name": "Knockdown", "attribute_key": "random", "duration": 2}


def _run_every_hook(state, a, b, types=("physical",)):
    """Drives every hook once with `a` attacking `b` (both passive-less)."""
    P.on_turn_start(state, a, False)
    P.on_turn_start(state, a, True)
    actx = P.begin_attack(state, a, b, list(types))
    m = P.target_damage_mods(actx, state, b, types[0], True)
    d, c = P.defender_resist_mods(state, b, a)
    sd = P.stat_deltas(state, a), P.stat_deltas(state, b)
    dec = P.roll_deceit(state, b)
    dodge_ev = P.on_dodged(state, b)
    P.record_strike(actx, b, {"damage_type": types[0]}, landed(types[0], crit=True),
                    target_attrs={"dodge": 10, "critical_hit_chance": 10})
    fin = P.finish_attack(actx, state)
    plan = P.plan_extra_hit(actx, state)
    pa, pb = state["participants"][str(a)], state["participants"][str(b)]
    bonus = P.effect_chance_bonus_pp(pa, ALL_HOOKS_ROW)
    ws = P.weak_spot_reroll(pa, ALL_HOOKS_ROW, 30), P.weak_spot_bonus_pp(pa, ALL_HOOKS_ROW)
    adj_rows, adj_c = P.adjust_outgoing_enemy_rows(pa, [dict(ALL_HOOKS_ROW)], a)
    kept, imm = P.filter_incoming_control(pb, [dict(ALL_HOOKS_ROW)], b)
    mana = P.mana_cost(pa, 15)
    kills = P.on_kills(state, a, [b])
    return dict(actx=actx, mods=m, deltas=d, dcontribs=c, stat=sd, deceit=dec,
                dodge_ev=dodge_ev, fin=fin, plan=plan, bonus=bonus, ws=ws,
                adj=(adj_rows, adj_c), filt=(kept, imm), mana=mana, kills=kills)


class TestNeutralParticipants:
    def _assert_neutral(self, r):
        assert r["actx"]["pct"] == 0 and r["actx"]["contributions"] == []
        assert r["mods"] == {"pct_by_type": {}, "force_crit": False, "crit_damage_bonus": 0,
                             "resist_ignore": None, "contributions": []}
        assert r["deltas"] == {} and r["dcontribs"] == []
        assert r["stat"] == ({}, {})
        assert r["deceit"] is False and r["dodge_ev"] == [] and r["fin"] == []
        assert r["plan"] is None and r["bonus"] == 0 and r["ws"] == (False, 0)
        assert r["adj"] == ([ALL_HOOKS_ROW], []) and r["filt"] == ([ALL_HOOKS_ROW], [])
        assert r["mana"] == 15 and r["kills"] == ([], None)

    def test_no_passive_no_state_no_rolls(self, no_rolls):
        s = battle({1: part(0, is_npc=False), 2: part(1, is_npc=False)}, dungeon_session_id=9)
        self._assert_neutral(_run_every_hook(s, 1, 2))
        assert all("passive_state" not in p for p in s["participants"].values())

    def test_old_state_without_new_keys(self, no_rolls):
        # pre-FEAT-188/189: no passive_key, is_npc, passive_state, max_hp, dungeon id
        s = {"participants": {"1": {"team": 0, "hp": 50}, "2": {"team": 1, "hp": 50}}}
        self._assert_neutral(_run_every_hook(s, 1, 2))
        assert all("passive_state" not in p for p in s["participants"].values())

    def test_unknown_passive_key_is_neutral(self, no_rolls):
        s = battle({1: part(0, "paladin_future"), 2: part(1, "necromancer_future")})
        self._assert_neutral(_run_every_hook(s, 1, 2))
        assert all("passive_state" not in p for p in s["participants"].values())

    def test_only_write_for_a_neutral_caster_is_the_used_magic_mark(self, no_rolls):
        # By design (D-§3.4: used_magic is kept for ANY participant — that's
        # what the Inquisitor reads). Nothing else is created for neutrals.
        s = battle({1: part(0), 2: part(1)})
        _run_every_hook(s, 1, 2, types=("fire",))
        assert ps(s, 1) == {"used_magic": True}
        assert "passive_state" not in s["participants"]["2"]

    def test_neutral_attacker_in_battle_full_of_owners_consumes_no_roll(self, no_rolls):
        s = battle({
            1: part(0),
            2: part(1, P.PASSIVE_TRICKSTER), 3: part(1, P.PASSIVE_MECHANIC),
            4: part(1, P.PASSIVE_SPARKMAGE), 5: part(1, P.PASSIVE_AGENT),
        })
        actx = P.begin_attack(s, 1, 3, ["electricity"])
        for t in (3, 4, 5):
            P.record_strike(actx, t, {"damage_type": "electricity"}, landed("electricity", crit=True))
        P.finish_attack(actx, s)
        assert P.plan_extra_hit(actx, s) is None
        assert P.roll_deceit(s, 3) is False  # target isn't the Trickster

    def test_garbage_values_dont_raise(self, no_rolls):
        s = battle({
            1: part(0, P.PASSIVE_GLADIATOR, hp=None, max_hp="x",
                    passive_state={"own_turns": "lots", "heresy_stacks": -4, "saber_pvp": None,
                                   "stolen": "x", "lancer_gain": [1]}),
            2: part(1, P.PASSIVE_SABER, hp="abc", passive_state={"saber_kills": "nan", "saber_pvp": -2,
                                                               "heresy_stacks": "9"}),
            "bad": "not a dict",
        })
        actx = P.begin_attack(s, 1, 2, [None, "physical"])
        assert actx["pct"] == 0
        P.target_damage_mods(actx, s, 2, None, True)
        P.defender_resist_mods(s, 2, 1)
        P.defender_resist_mods(s, 1, 2)
        P.stat_deltas(s, 1)
        P.apply_stat_deltas(None, {"dodge": "x"})
        P.record_strike(actx, 2, None, None)
        P.record_strike(None, 2, None, {})
        P.finish_attack(actx, s)
        P.finish_attack(None, s)
        P.plan_extra_hit(None, s)
        P.target_damage_mods(None, s, 2, "fire", True)
        P.on_kills(None, 1, None)
        P.begin_attack(None, 1, 2, None)
        P.begin_attack(s, 99, 2, ["fire"])
        P.adjust_outgoing_enemy_rows({"passive_key": P.PASSIVE_TRICKSTER}, [None, "x", {"duration": "x"}])
        P.filter_incoming_control({"passive_key": P.PASSIVE_MONK}, None, 1)
        assert P.mana_cost({"passive_key": P.PASSIVE_CASTER}, None) is None
        assert P.mana_cost({"passive_key": P.PASSIVE_CASTER}, "abc") == "abc"
        assert P.mana_cost({"passive_key": P.PASSIVE_CASTER}, -5) == -5


class TestRageUnchanged:
    def test_rage_still_only_via_feat188_path(self, no_rolls):
        s = battle({1: part(0, P.PASSIVE_BERSERKER_RAGE, hp=40), 2: part(1)})
        assert P.passive_damage_bonus(s["participants"]["1"]) == (24, P.PASSIVE_BERSERKER_RAGE)
        actx = P.begin_attack(s, 1, 2, ["physical"])
        assert actx["pct"] == 0 and actx["contributions"] == []
        assert P.target_damage_mods(actx, s, 2, "physical", True)["pct_by_type"] == {}

    @pytest.mark.parametrize("key", sorted(P.IMPLEMENTED_PASSIVES - {P.PASSIVE_BERSERKER_RAGE}))
    def test_wave1_keys_have_no_feat188_damage_bonus(self, key):
        assert P.passive_damage_bonus(part(0, key, hp=1)) == (0, None)


# =============================================================================
# Инквизитор — Печать ереси
# =============================================================================
class TestInquisitor:
    @pytest.mark.parametrize("t", P.NON_PHYSICAL_TYPES)
    def test_non_physical_attack_marks_used_magic(self, t):
        s = battle({1: part(0), 2: part(1)})
        P.begin_attack(s, 1, 2, ["physical", t])
        assert ps(s, 1)["used_magic"] is True

    @pytest.mark.parametrize("types", [["physical"], ["catting", "crushing", "piercing"], []])
    def test_physical_attack_doesnt_mark(self, types):
        s = battle({1: part(0), 2: part(1)})
        P.begin_attack(s, 1, 2, types)
        assert "passive_state" not in s["participants"]["1"]

    def test_all_entry_resolved_to_magic_weapon_marks(self):
        s = battle({1: part(0), 2: part(1)})
        t = P.resolve_entry_type({"damage_type": "all"}, {"main_weapon": {"primary_damage_type": "sainting"}})
        P.begin_attack(s, 1, 2, [t], source_kind="item")
        assert ps(s, 1)["used_magic"] is True

    def _inq_battle(self):
        return battle({1: part(0, P.PASSIVE_INQUISITOR), 2: part(1, passive_state={"used_magic": True}),
                       3: part(1), 4: part(0)})

    def test_hit_on_magic_user_adds_stack_once_per_attack(self):
        s = self._inq_battle()
        _, ev = one_attack(s, 1, 2, strikes=[(2, {}, landed(), None), (2, {}, landed(), None)])
        assert ps(s, 2)["heresy_stacks"] == 1
        assert ev == [{"event": "passive_proc", "who": 1, "key": P.PASSIVE_INQUISITOR,
                       "kind": "heresy_stack", "target": 2, "stacks": 1, "value": -3}]

    def test_zero_damage_hit_still_counts(self):
        s = self._inq_battle()
        one_attack(s, 1, 2, strikes=[(2, {}, landed(final=0), None)])
        assert ps(s, 2)["heresy_stacks"] == 1

    @pytest.mark.parametrize("log", [DODGED, HIT_FAILED])
    def test_dodged_or_missed_is_not_a_hit(self, log):
        s = self._inq_battle()
        _, ev = one_attack(s, 1, 2, strikes=[(2, {}, log, None)])
        assert ev == [] and "heresy_stacks" not in ps(s, 2)

    def test_target_that_never_used_magic_gets_nothing(self):
        s = self._inq_battle()
        _, ev = one_attack(s, 1, 3, strikes=[(3, {}, landed(), None)])
        assert ev == [] and "passive_state" not in s["participants"]["3"]

    def test_target_marked_later_in_battle(self):
        s = self._inq_battle()
        one_attack(s, 1, 3, strikes=[(3, {}, landed(), None)])
        P.begin_attack(s, 3, 1, ["damning"])
        one_attack(s, 1, 3, strikes=[(3, {}, landed(), None)])
        assert ps(s, 3)["heresy_stacks"] == 1

    def test_stack_cap_5(self):
        s = self._inq_battle()
        evs = []
        for _ in range(7):
            evs += one_attack(s, 1, 2, strikes=[(2, {}, landed(), None)])[1]
        assert ps(s, 2)["heresy_stacks"] == 5 and len(evs) == 5
        d, _ = P.defender_resist_mods(s, 2, 1)
        assert d["magic"] == -15

    def test_non_inquisitor_doesnt_stack(self):
        s = battle({1: part(0), 2: part(1, passive_state={"used_magic": True})})
        one_attack(s, 1, 2, strikes=[(2, {}, landed(), None)])
        assert "heresy_stacks" not in ps(s, 2)

    def test_resist_delta_on_every_non_physical_type_for_any_attacker(self):
        s = self._inq_battle()
        ps(s, 2)["heresy_stacks"] = 3
        for attacker in (1, 4, 3, None):   # Inquisitor, his ally, the target's ally, unknown
            d, c = P.defender_resist_mods(s, 2, attacker)
            assert d == {t: -9 for t in P.NON_PHYSICAL_TYPES}
            assert "physical" not in d and "all" not in d
            assert c == [{"key": P.PASSIVE_INQUISITOR, "kind": "resist_pct", "value": -9}]

    @pytest.mark.parametrize("dtype,kept", [
        ("physical", False), ("piercing", False), ("Physical", False), (None, False),
        ("magic", True), ("Fire", True), ("damning", True),
    ])
    def test_heresy_contribution_only_on_non_physical_hits(self, dtype, kept):
        heresy = {"key": P.PASSIVE_INQUISITOR, "kind": "resist_pct", "value": -6}
        saber = {"key": P.PASSIVE_SABER, "kind": "resist_pct", "value": 2, "owner": 2}
        out = P.defender_contribs_for_type([heresy, saber], dtype)
        assert out == ([heresy, saber] if kept else [saber])
        assert P.defender_contribs_for_type(None, "magic") == []

    @pytest.mark.parametrize("raw,expected", [(99, -15), ("2", -6), (-3, None), ("abc", None), (0, None)])
    def test_stored_stack_values_are_clamped(self, raw, expected):
        s = battle({1: part(0), 2: part(1, passive_state={"heresy_stacks": raw})})
        d, _ = P.defender_resist_mods(s, 2, 1)
        assert d.get("magic") == expected


# =============================================================================
# Сейбер — Охотник на чудовищ + Несгибаемость
# =============================================================================
class TestSaber:
    def test_plus_15_vs_any_npc(self):
        s = battle({1: part(0, P.PASSIVE_SABER), 2: part(1, is_npc=True)})
        actx = P.begin_attack(s, 1, 2, ["physical"])
        m = P.target_damage_mods(actx, s, 2, "fire", True)
        assert m["pct_by_type"] == {"all": 15}
        assert m["contributions"] == [{"key": P.PASSIVE_SABER, "kind": "damage_pct", "value": 15, "owner": 1}]

    @pytest.mark.parametrize("flag", [False, None, "true", 1, "missing"])
    def test_no_bonus_vs_player_or_unknown(self, flag):
        target = part(1) if flag == "missing" else part(1, is_npc=flag)
        s = battle({1: part(0, P.PASSIVE_SABER), 2: target})
        actx = P.begin_attack(s, 1, 2, ["physical"])
        assert P.target_damage_mods(actx, s, 2, "physical", True)["pct_by_type"] == {}

    def test_kill_stacks_only_in_dungeon(self):
        s = battle({1: part(0, P.PASSIVE_SABER), 2: part(1, is_npc=True)})
        assert P.on_kills(s, 1, [2]) == ([], None)
        assert "passive_state" not in s["participants"]["1"]

    def test_kill_stacks_persist_value_and_raise_damage_immediately(self):
        s = battle({1: part(0, P.PASSIVE_SABER), 2: part(1, is_npc=True), 3: part(1, is_npc=True)},
                   dungeon_session_id=42)
        ev, n = P.on_kills(s, 1, [2, 3, 2])     # duplicate counted once
        assert n == 2 and ps(s, 1)["saber_kills"] == 2
        assert [e["kind"] for e in ev] == ["saber_kill", "saber_kill"]
        assert ev[1] == {"event": "passive_proc", "who": 1, "key": P.PASSIVE_SABER, "kind": "saber_kill",
                         "target": 3, "stacks": 2, "value": 4}
        actx = P.begin_attack(s, 1, 2, ["physical"])
        assert actx["pct"] == 4
        assert actx["contributions"] == [{"key": P.PASSIVE_SABER, "kind": "damage_pct", "value": 4, "owner": 1}]

    def test_kill_stacks_cap_5_is_plus_10(self):
        s = battle({1: part(0, P.PASSIVE_SABER, passive_state={"saber_kills": 4})},
                   dungeon_session_id=1)
        ev, n = P.on_kills(s, 1, [7, 8, 9])
        assert n == 5 and len(ev) == 1
        assert P.on_kills(s, 1, [10]) == ([], None)
        assert P.begin_attack(s, 1, 7, [])["pct"] == 10

    def test_seeded_garbage_stack_is_capped(self):
        s = battle({1: part(0, P.PASSIVE_SABER, passive_state={"saber_kills": 50}), 2: part(1)})
        assert P.begin_attack(s, 1, 2, [])["pct"] == 10

    def test_kill_of_ally_or_by_non_saber_doesnt_count(self):
        s = battle({1: part(0, P.PASSIVE_SABER), 2: part(0), 3: part(1)}, dungeon_session_id=1)
        assert P.on_kills(s, 1, [2]) == ([], None)
        assert P.on_kills(s, 3, [1]) == ([], None)

    def test_pvp_resolve_stack_from_player_attacker(self):
        s = battle({1: part(0, P.PASSIVE_SABER, is_npc=False), 2: part(1, is_npc=False)})
        _, ev = one_attack(s, 2, 1, strikes=[(1, {}, landed(final=0), None), (1, {}, landed(), None)])
        assert ps(s, 1)["saber_pvp"] == 1
        assert ev == [{"event": "passive_proc", "who": 1, "key": P.PASSIVE_SABER,
                       "kind": "saber_resolve", "stacks": 1, "value": 2}]
        assert P.defender_resist_mods(s, 1, 2) == (
            {"all": 2}, [{"key": P.PASSIVE_SABER, "kind": "resist_pct", "value": 2, "owner": 1}])

    def test_pvp_resolve_cap_3(self):
        s = battle({1: part(0, P.PASSIVE_SABER, is_npc=False), 2: part(1, is_npc=False)})
        for _ in range(5):
            one_attack(s, 2, 1, strikes=[(1, {}, landed(), None)])
        assert ps(s, 1)["saber_pvp"] == 3
        assert P.defender_resist_mods(s, 1, 2)[0] == {"all": 6}

    @pytest.mark.parametrize("attacker_flag", [True, None, "missing"])
    def test_no_resolve_from_npc_or_unknown_attacker(self, attacker_flag):
        att = part(1) if attacker_flag == "missing" else part(1, is_npc=attacker_flag)
        s = battle({1: part(0, P.PASSIVE_SABER, is_npc=False), 2: att})
        one_attack(s, 2, 1, strikes=[(1, {}, landed(), None)])
        assert "passive_state" not in s["participants"]["1"]

    def test_no_resolve_on_dodge(self):
        s = battle({1: part(0, P.PASSIVE_SABER, is_npc=False), 2: part(1, is_npc=False)})
        one_attack(s, 2, 1, strikes=[(1, {}, DODGED, None)])
        assert "passive_state" not in s["participants"]["1"]


# =============================================================================
# Гладиатор — Арена
# =============================================================================
class TestGladiator:
    @pytest.mark.parametrize("enemies,allies,dmg,res", [
        (1, 0, 0, 0),   # 1v1 → not outnumbered (ramp, 0 turns)
        (2, 0, 8, 4),
        (4, 0, 24, 12),
        (6, 0, 24, 12),  # surplus capped at 3
        (3, 1, 8, 4),    # 3 enemies vs 2 incl. self
        (2, 1, 0, 0),
    ])
    def test_arena_by_surplus(self, enemies, allies, dmg, res):
        parts = {1: part(0, P.PASSIVE_GLADIATOR)}
        pid = 2
        for _ in range(allies):
            parts[pid] = part(0); pid += 1
        first_enemy = pid
        for _ in range(enemies):
            parts[pid] = part(1); pid += 1
        s = battle(parts)
        actx = P.begin_attack(s, 1, first_enemy, ["physical"])
        assert actx["pct"] == dmg
        d, _ = P.defender_resist_mods(s, 1, first_enemy)
        assert d == ({"all": res} if res else {})

    def test_dead_and_dropped_enemies_dont_count(self):
        s = battle({1: part(0, P.PASSIVE_GLADIATOR), 2: part(1), 3: part(1, hp=0),
                    4: part(1, dropped_out=True)})
        assert P.begin_attack(s, 1, 2, [])["pct"] == 0

    def test_mode_is_decided_per_hit(self):
        s = battle({1: part(0, P.PASSIVE_GLADIATOR, passive_state={"own_turns": 2}), 2: part(1)})
        assert P.begin_attack(s, 1, 2, [])["pct"] == 6          # ramp
        s["participants"]["3"] = part(1)                         # joiner
        actx = P.begin_attack(s, 1, 2, [])
        assert actx["pct"] == 8                                  # arena, ramp ignored
        assert actx["contributions"] == [{"key": P.PASSIVE_GLADIATOR, "kind": "damage_pct",
                                          "value": 8, "owner": 1}]
        s["participants"]["3"]["hp"] = 0
        assert P.begin_attack(s, 1, 2, [])["pct"] == 6          # back to ramp

    def test_ramp_plus_3_per_own_turn_cap_15(self):
        s = battle({1: part(0, P.PASSIVE_GLADIATOR), 2: part(1)})
        got = []
        for _ in range(7):
            P.on_turn_start(s, 1, False)
            got.append(P.begin_attack(s, 1, 2, [])["pct"])
        assert got == [3, 6, 9, 12, 15, 15, 15]

    def test_zero_ramp_has_no_contribution(self):
        s = battle({1: part(0, P.PASSIVE_GLADIATOR), 2: part(1)})
        actx = P.begin_attack(s, 1, 2, [])
        assert actx["pct"] == 0 and actx["contributions"] == []

    def test_stun_skipped_turn_doesnt_count(self):
        s = battle({1: part(0, P.PASSIVE_GLADIATOR), 2: part(1)})
        P.on_turn_start(s, 1, True)
        assert "passive_state" not in s["participants"]["1"]
        P.on_turn_start(s, 1, False)
        P.on_turn_start(s, 1, True)
        assert ps(s, 1)["own_turns"] == 1

    def test_non_gladiator_turns_not_tracked(self):
        s = battle({1: part(0, P.PASSIVE_SABER), 2: part(1)})
        P.on_turn_start(s, 1, False)
        assert "passive_state" not in s["participants"]["1"]


# =============================================================================
# Агент — Слабое место
# =============================================================================
AGENT = {"passive_key": P.PASSIVE_AGENT}
BLEED = {"effect_name": "Bleeding", "duration": 2}
STUN = {"effect_name": "Stun", "duration": 1}
PARALYSIS = {"effect_name": "Poison", "attribute_key": "paralysis", "duration": 1}


class TestAgent:
    @pytest.mark.parametrize("row,p,bonus,q", [
        (BLEED, 0, 20, 20),
        (BLEED, 50, 20, 40),
        (BLEED, 80, 20, 100),
        (BLEED, 95, 20, 100),
        (STUN, 0, 10, 10),
        (STUN, 50, 10, 20),
        (PARALYSIS, 60, 10, 25),
        ({"effect_name": "Knockdown", "attribute_key": "random"}, 30, 20, 20 / 70 * 100),
    ])
    def test_conditional_reroll_makes_total_min_100_p_plus_bonus(self, row, p, bonus, q):
        with rolls(True) as (rp, _):
            assert P.weak_spot_reroll(AGENT, row, p) is True
        got_q = rp.call_args[0][0]
        assert got_q == pytest.approx(q)
        total = p + (100 - p) * got_q / 100
        assert total == pytest.approx(min(100, p + bonus))

    def test_reroll_can_fail(self):
        with rolls(False):
            assert P.weak_spot_reroll(AGENT, BLEED, 10) is False

    def test_already_certain_row_no_roll(self, no_rolls):
        assert P.weak_spot_reroll(AGENT, BLEED, 100) is False
        assert P.weak_spot_reroll(AGENT, BLEED, 130) is False

    def test_garbage_failed_chance_treated_as_zero(self):
        with rolls(True) as (rp, _):
            P.weak_spot_reroll(AGENT, BLEED, None)
        assert rp.call_args[0][0] == pytest.approx(20)

    def test_non_agent_no_reroll_no_roll(self, no_rolls):
        for caster in ({}, {"passive_key": P.PASSIVE_MONK}, None):
            assert P.weak_spot_reroll(caster, BLEED, 10) is False
            assert P.weak_spot_bonus_pp(caster, BLEED) == 0

    def test_direct_bonus_for_coating(self):
        assert P.weak_spot_bonus_pp(AGENT, BLEED) == 20
        assert P.weak_spot_bonus_pp(AGENT, STUN) == 10
        assert P.weak_spot_bonus_pp(AGENT, PARALYSIS) == 10

    def test_only_critted_landed_targets_qualify(self):
        s = battle({1: part(0, P.PASSIVE_AGENT), 2: part(1), 3: part(1), 4: part(1)})
        actx = P.begin_attack(s, 1, 2, ["physical"])
        P.record_strike(actx, 2, {}, landed(crit=True))
        P.record_strike(actx, 3, {}, landed(crit=False))
        P.record_strike(actx, 4, {}, DODGED)
        assert P.critted_targets(actx) == [2]
        assert sorted(P.landed_targets(actx)) == [2, 3]

    def test_weak_spot_event(self):
        assert P.weak_spot_event(1, 2, ["Bleeding"]) == {
            "event": "passive_proc", "who": 1, "key": P.PASSIVE_AGENT, "kind": "weak_spot",
            "target": 2, "effects": ["Bleeding"]}


# =============================================================================
# Лансер — Пригвоздить
# =============================================================================
class TestLancer:
    def _b(self):
        return battle({1: part(0, P.PASSIVE_LANCER), 2: part(1), 3: part(1)})

    def test_steals_both_stats(self):
        s = self._b()
        _, ev = one_attack(s, 1, 2, strikes=[(2, {}, landed(final=0), {"dodge": 10, "critical_hit_chance": 30})])
        assert ev == [{"event": "passive_proc", "who": 1, "key": P.PASSIVE_LANCER, "kind": "pin",
                       "target": 2, "stacks": 1, "stolen": {"dodge": 2, "critical_hit_chance": 2}}]
        assert P.stat_deltas(s, 1) == {"dodge": 2, "critical_hit_chance": 2}
        assert P.stat_deltas(s, 2) == {"dodge": -2, "critical_hit_chance": -2}
        assert P.apply_stat_deltas({"dodge": 10, "critical_hit_chance": 30, "strength": 5},
                                   P.stat_deltas(s, 2)) == {"dodge": 8, "critical_hit_chance": 28, "strength": 5}

    def test_partial_steal_never_more_than_target_has(self):
        s = self._b()
        _, ev = one_attack(s, 1, 2, strikes=[(2, {}, landed(), {"dodge": 0.5, "critical_hit_chance": 0})])
        assert ev[0]["stolen"] == {"dodge": 0.5}
        assert P.stat_deltas(s, 1) == {"dodge": 0.5}

    def test_nothing_to_steal_is_not_a_stack(self):
        s = self._b()
        _, ev = one_attack(s, 1, 2, strikes=[(2, {}, landed(), {"dodge": 0, "critical_hit_chance": -3})])
        assert ev == [] and "passive_state" not in s["participants"]["2"]

    def test_target_never_below_zero(self):
        out = P.apply_stat_deltas({"dodge": 1.0, "critical_hit_chance": -2}, {"dodge": -2, "critical_hit_chance": -2})
        assert out == {"dodge": 0.0, "critical_hit_chance": -2}
        assert P.apply_stat_deltas({}, {"dodge": -2}) == {"dodge": 0.0}

    def test_attrs_are_copied(self):
        attrs = {"dodge": 5}
        P.apply_stat_deltas(attrs, {"dodge": -2})
        assert attrs == {"dodge": 5}

    def test_cap_5_stacks(self):
        s = self._b()
        for i in range(8):
            one_attack(s, 1, 2 + i % 2, strikes=[(2 + i % 2, {}, landed(), {"dodge": 50, "critical_hit_chance": 50})])
        assert ps(s, 1)["lancer_stacks"] == 5
        assert P.stat_deltas(s, 1) == {"dodge": 10, "critical_hit_chance": 10}

    def test_aoe_steals_per_target_until_cap(self):
        s = self._b()
        ps_ = P.pstate(s["participants"]["1"])
        ps_["lancer_stacks"] = 4
        _, ev = one_attack(s, 1, 2, strikes=[(2, {}, landed(), {"dodge": 9}), (3, {}, landed(), {"dodge": 9})])
        assert len(ev) == 1 and ps_["lancer_stacks"] == 5

    @pytest.mark.parametrize("log", [DODGED, HIT_FAILED])
    def test_no_steal_without_hit(self, log):
        s = self._b()
        _, ev = one_attack(s, 1, 2, strikes=[(2, {}, log, {"dodge": 9, "critical_hit_chance": 9})])
        assert ev == [] and "passive_state" not in s["participants"]["1"]

    def test_unknown_target_attrs_assume_full_steal(self):
        s = self._b()
        _, ev = one_attack(s, 1, 2, strikes=[(2, {}, landed(), None)])
        assert ev[0]["stolen"] == {"dodge": 2, "critical_hit_chance": 2}

    def test_gain_only_counts_for_a_lancer(self):
        s = battle({1: part(0, passive_state={"lancer_gain": {"dodge": 10}})})
        assert P.stat_deltas(s, 1) == {}


# =============================================================================
# Механик — Шрапнель
# =============================================================================
class TestMechanic:
    def test_splash_on_random_other_living_enemy(self):
        s = battle({1: part(0, P.PASSIVE_MECHANIC), 2: part(1), 3: part(1, hp=0), 4: part(1),
                    5: part(1, dropped_out=True), 6: part(0)})
        with rolls(True, pick_index=0) as (rp, pk):
            actx = P.begin_attack(s, 1, 2, ["physical"])
            assert actx["duel_bonus"] == 0 and rp.call_count == 0   # others alive → no duel roll
            trig = {"damage_type": "physical", "amount": 7}
            P.record_strike(actx, 2, {"damage_type": "physical", "amount": 1}, DODGED)
            P.record_strike(actx, 2, trig, landed())
            P.finish_attack(actx, s)
            plan = P.plan_extra_hit(actx, s)
        assert rp.call_args[0][0] == 30
        assert list(pk.call_args[0][0]) == [4]
        assert plan == {"target_pid": 4, "entry": trig, "mult": 0.4, "kind": "splash",
                        "contribution": {"key": P.PASSIVE_MECHANIC, "kind": "extra_hit", "value": 40, "owner": 1}}

    def test_splash_roll_fails(self):
        s = battle({1: part(0, P.PASSIVE_MECHANIC), 2: part(1), 3: part(1)})
        with rolls(False):
            actx = P.begin_attack(s, 1, 2, [])
            P.record_strike(actx, 2, {}, landed())
            assert P.plan_extra_hit(actx, s) is None

    @pytest.mark.parametrize("log", [DODGED, HIT_FAILED])
    def test_no_landed_hit_no_splash_no_roll(self, log):
        s = battle({1: part(0, P.PASSIVE_MECHANIC), 2: part(1), 3: part(1)})
        with patch.object(P, "roll_pct", side_effect=_boom):
            actx = P.begin_attack(s, 1, 2, [])
            P.record_strike(actx, 2, {}, log)
            assert P.plan_extra_hit(actx, s) is None

    def test_once_per_attack(self):
        s = battle({1: part(0, P.PASSIVE_MECHANIC), 2: part(1), 3: part(1)})
        with rolls(True):
            actx = P.begin_attack(s, 1, 2, [])
            P.record_strike(actx, 2, {}, landed())
            P.record_strike(actx, 3, {}, landed())    # AoE: second landed target
            assert P.plan_extra_hit(actx, s) is not None
            assert P.plan_extra_hit(actx, s) is None

    def test_extra_hit_records_nothing(self):
        s = battle({1: part(0, P.PASSIVE_MECHANIC), 2: part(1), 3: part(1)})
        actx = P.begin_attack(s, 1, 2, [])
        P.record_strike(actx, 3, {}, landed(crit=True), is_extra=True)
        assert actx["hits"] == {}
        assert P.finish_attack(actx, s) == []

    def test_duel_bonus_decided_at_begin(self):
        s = battle({1: part(0, P.PASSIVE_MECHANIC), 2: part(1), 3: part(1, hp=0)})
        with rolls(True) as (rp, _):
            actx = P.begin_attack(s, 1, 2, [])
        assert rp.call_args[0][0] == 30 and actx["duel_bonus"] == 35
        m = P.target_damage_mods(actx, s, 2, "physical", True)
        assert m["pct_by_type"] == {"all": 35}
        assert P.target_damage_mods(actx, s, 3, "physical", False)["pct_by_type"] == {}
        # no candidates at the end either → no splash, no further roll
        P.record_strike(actx, 2, {}, landed())
        with patch.object(P, "roll_pct", side_effect=_boom):
            assert P.plan_extra_hit(actx, s) is None

    def test_duel_roll_fails(self):
        s = battle({1: part(0, P.PASSIVE_MECHANIC), 2: part(1)})
        with rolls(False):
            actx = P.begin_attack(s, 1, 2, [])
        assert actx["duel_bonus"] == 0
        assert P.target_damage_mods(actx, s, 2, "physical", True)["pct_by_type"] == {}

    def test_joiner_switches_duel_to_splash(self):
        s = battle({1: part(0, P.PASSIVE_MECHANIC), 2: part(1)})
        with rolls(True):
            assert P.begin_attack(s, 1, 2, [])["duel_bonus"] == 35
            s["participants"]["3"] = part(1)
            actx = P.begin_attack(s, 1, 2, [])
            assert actx["duel_bonus"] == 0
            P.record_strike(actx, 2, {}, landed())
            assert P.plan_extra_hit(actx, s)["target_pid"] == 3

    def test_splash_candidate_that_died_meanwhile_excluded(self):
        s = battle({1: part(0, P.PASSIVE_MECHANIC), 2: part(1), 3: part(1)})
        with rolls(True):
            actx = P.begin_attack(s, 1, 2, [])
            P.record_strike(actx, 3, {}, landed())
            s["participants"]["3"]["hp"] = 0          # AoE killed the only other enemy
            assert P.plan_extra_hit(actx, s) is None


# =============================================================================
# Арчер — Первая кровь
# =============================================================================
class TestArcher:
    def test_first_landed_hit_per_target(self):
        s = battle({1: part(0, P.PASSIVE_ARCHER), 2: part(1), 3: part(1)})
        actx = P.begin_attack(s, 1, 2, ["physical"])
        m = P.target_damage_mods(actx, s, 2, "physical", True)
        assert m["force_crit"] is True and m["crit_damage_bonus"] == 50
        assert m["contributions"] == [{"key": P.PASSIVE_ARCHER, "kind": "forced_crit", "value": 50, "owner": 1}]
        P.record_strike(actx, 2, {}, landed(crit=True))
        # second entry of the SAME attack is still forced
        assert P.target_damage_mods(actx, s, 2, "physical", True)["force_crit"] is True
        P.finish_attack(actx, s)
        actx = P.begin_attack(s, 1, 2, ["physical"])
        assert P.target_damage_mods(actx, s, 2, "physical", True)["force_crit"] is False
        # another target still has its first blood
        assert P.target_damage_mods(actx, s, 3, "physical", False)["force_crit"] is True

    @pytest.mark.parametrize("log", [DODGED, HIT_FAILED])
    def test_not_consumed_without_landing(self, log):
        s = battle({1: part(0, P.PASSIVE_ARCHER), 2: part(1)})
        one_attack(s, 1, 2, strikes=[(2, {}, log, None)])
        actx = P.begin_attack(s, 1, 2, [])
        assert P.target_damage_mods(actx, s, 2, "physical", True)["force_crit"] is True

    def test_aoe_first_blood_on_each_target(self):
        s = battle({1: part(0, P.PASSIVE_ARCHER), 2: part(1), 3: part(1)})
        one_attack(s, 1, 2, strikes=[(2, {}, landed(), None), (3, {}, landed(), None)])
        assert sorted(ps(s, 1)["first_blood_done"]) == [2, 3]

    def test_non_archer_no_forced_crit(self):
        s = battle({1: part(0), 2: part(1)})
        actx = P.begin_attack(s, 1, 2, [])
        assert P.target_damage_mods(actx, s, 2, "physical", True)["force_crit"] is False


# =============================================================================
# Ассасин — Из тени + Добивание
# =============================================================================
class TestAssassin:
    def test_dodge_readies_shadow_once(self):
        s = battle({1: part(0, P.PASSIVE_ASSASSIN), 2: part(1)})
        assert P.on_dodged(s, 1) == [{"event": "passive_proc", "who": 1, "key": P.PASSIVE_ASSASSIN,
                                      "kind": "shadow_ready"}]
        assert P.on_dodged(s, 1) == []
        assert ps(s, 1)["shadow_ready"] is True

    def test_non_assassin_dodge_nothing(self):
        s = battle({1: part(0, P.PASSIVE_TRICKSTER), 2: part(1)})
        assert P.on_dodged(s, 1) == [] and "passive_state" not in s["participants"]["1"]

    def test_shadow_forces_crit_for_whole_attack_and_is_consumed_regardless(self):
        s = battle({1: part(0, P.PASSIVE_ASSASSIN), 2: part(1), 3: part(1)})
        P.on_dodged(s, 1)
        actx = P.begin_attack(s, 1, 2, ["physical"])
        assert ps(s, 1)["shadow_ready"] is False         # consumed at begin
        for tgt in (2, 3):
            m = P.target_damage_mods(actx, s, tgt, "physical", tgt == 2)
            assert m["force_crit"] is True and m["crit_damage_bonus"] == 25
            assert {"key": P.PASSIVE_ASSASSIN, "kind": "forced_crit", "value": 25, "owner": 1} in m["contributions"]
        P.record_strike(actx, 2, {}, DODGED)              # the attack missed — still gone
        P.finish_attack(actx, s)
        actx = P.begin_attack(s, 1, 2, ["physical"])
        assert P.target_damage_mods(actx, s, 2, "physical", True)["force_crit"] is False

    def test_no_shadow_no_forced_crit(self):
        s = battle({1: part(0, P.PASSIVE_ASSASSIN), 2: part(1)})
        actx = P.begin_attack(s, 1, 2, [])
        m = P.target_damage_mods(actx, s, 2, "physical", True)
        assert m["force_crit"] is False and m["crit_damage_bonus"] == 0

    @pytest.mark.parametrize("hp,max_hp,bonus", [
        (29.9, 100, 20), (0.5, 100, 20), (30, 100, None), (31, 100, None),
        (14, 50, 20), (15, 50, None), (10, 0, None), (10, None, None),
    ])
    def test_execute_below_30pct(self, hp, max_hp, bonus):
        s = battle({1: part(0, P.PASSIVE_ASSASSIN), 2: part(1, hp=hp, max_hp=max_hp)})
        actx = P.begin_attack(s, 1, 2, [])
        assert P.target_damage_mods(actx, s, 2, "physical", True)["pct_by_type"].get("all") == bonus

    def test_shadow_and_execute_stack(self):
        s = battle({1: part(0, P.PASSIVE_ASSASSIN, passive_state={"shadow_ready": True}), 2: part(1, hp=10)})
        actx = P.begin_attack(s, 1, 2, [])
        m = P.target_damage_mods(actx, s, 2, "physical", True)
        assert m["pct_by_type"] == {"all": 20} and m["force_crit"] and m["crit_damage_bonus"] == 25


# =============================================================================
# Фокусник — Обман (часть 1)
# =============================================================================
TRICKSTER = {"passive_key": P.PASSIVE_TRICKSTER}


class TestTrickster:
    def test_deceit_10pct_gate_both_ways(self):
        s = battle({1: part(0), 2: part(1, P.PASSIVE_TRICKSTER)})
        with rolls(True) as (rp, _):
            assert P.roll_deceit(s, 2) is True
        assert rp.call_args[0][0] == 10
        with rolls(False):
            assert P.roll_deceit(s, 2) is False

    def test_deceit_only_for_trickster_target(self, no_rolls):
        s = battle({1: part(0, P.PASSIVE_TRICKSTER), 2: part(1, P.PASSIVE_ASSASSIN)})
        assert P.roll_deceit(s, 2) is False
        assert P.roll_deceit(s, 99) is False
        assert "passive_state" not in s["participants"]["2"]   # deceit never readies a shadow

    def test_redirect_returns_a_live_ally_of_the_attacker(self):
        # FEAT-190 E19 (the FEAT-189 seam returned None): candidates = the
        # attacker's LIVING teammates without the attacker himself.
        s = battle({1: part(0), 2: part(1, P.PASSIVE_TRICKSTER), 3: part(0),
                    4: part(0, hp=0), 5: part(1)})
        with rolls(True) as (_, pk):
            assert P.deceit_redirect_target(s, 1, 2) == 3
        assert [list(c[0][0]) for c in pk.call_args_list] == [[3]]

    def test_redirect_without_an_ally_is_none_and_rolls_nothing(self, no_rolls):
        s = battle({1: part(0), 2: part(1, P.PASSIVE_TRICKSTER), 3: part(0, hp=0)})
        assert P.deceit_redirect_target(s, 1, 2) is None
        # and only a Trickster target redirects
        s = battle({1: part(0), 2: part(1), 3: part(0)})
        assert P.deceit_redirect_target(s, 1, 2) is None

    def test_deceit_contribution(self):
        assert P.deceit_contribution(2) == {"key": P.PASSIVE_TRICKSTER, "kind": "deceit", "owner": 2}

    def test_debuffs_plus_one_turn_except_hard_control_and_instant_resources(self):
        rows = [
            {"effect_name": "Bleeding", "duration": 2},
            {"effect_name": "Stun", "duration": 1},
            {"effect_name": "Poison", "attribute_key": "paralysis", "duration": 2},
            {"name": "Poison", "attribute": "paralysis", "duration": 2},
            {"effect_name": "Knockdown", "attribute_key": "random", "duration": 1},
            {"effect_name": "Poison", "attribute_key": "hp", "duration": 3},   # DoT → bumped
            {"effect_name": "hp", "attribute_key": "hp", "duration": 1},       # instant hit
            {"name": "Mana", "attribute": "mana", "duration": 0},
            {"effect_name": "Weakness", "attribute_key": "strength", "duration": 0},
        ]
        snapshot = [dict(r) for r in rows]
        out, c = P.adjust_outgoing_enemy_rows(TRICKSTER, rows, 2)
        assert [r["duration"] for r in out] == [3, 1, 2, 2, 2, 4, 1, 0, 0]
        assert rows == snapshot                                    # inputs untouched
        assert c == [{"key": P.PASSIVE_TRICKSTER, "kind": "duration_plus", "value": 1, "owner": 2}]

    def test_nothing_bumped_no_contribution(self):
        out, c = P.adjust_outgoing_enemy_rows(TRICKSTER, [dict(STUN)], 2)
        assert out == [STUN] and c == []

    def test_others_unchanged(self, no_rolls):
        rows = [{"effect_name": "Bleeding", "duration": 2}]
        for caster in ({}, None, {"passive_key": P.PASSIVE_MONK}):
            out, c = P.adjust_outgoing_enemy_rows(caster, rows, 1)
            assert out == rows and out[0] is not rows[0] and c == []


# =============================================================================
# Монах — Гармония
# =============================================================================
MONK = {"passive_key": P.PASSIVE_MONK}


class TestMonk:
    @pytest.mark.parametrize("row,bonus", [
        ({"effect_name": "Knockdown", "attribute_key": "random"}, 10),
        ({"effect_name": "Windburn", "attribute_key": "random"}, 10),
        ({"name": "Knockdown", "attribute": "dodge"}, 10),
        (STUN, 5),
        (PARALYSIS, 5),
        ({"effect_name": "Poison", "attribute_key": "hp"}, 0),
        (BLEED, 0),
    ])
    def test_control_chance_bonus(self, row, bonus):
        assert P.effect_chance_bonus_pp(MONK, row) == bonus
        assert P.effect_chance_bonus_pp({"passive_key": P.PASSIVE_AGENT}, row) == 0
        assert P.effect_chance_bonus_pp({}, row) == 0

    def test_first_control_blocked_incl_random_knockdown(self):
        monk = dict(MONK)        # old state: no passive_state yet
        rows = [dict(BLEED), {"effect_name": "Knockdown", "attribute_key": "random", "duration": 1},
                {"effect_name": "Windburn", "attribute_key": "random", "duration": 1}]
        kept, ev = P.filter_incoming_control(monk, rows, 5)
        assert kept == [rows[0], rows[2]]                         # only the FIRST control dropped
        assert ev == [{"event": "passive_proc", "who": 5, "key": P.PASSIVE_MONK,
                       "kind": "control_immune", "effects": ["Knockdown"]}]
        assert monk["passive_state"]["control_immunity_used"] is True
        kept, ev = P.filter_incoming_control(monk, [dict(STUN)], 5)
        assert kept == [STUN] and ev == []                        # second control lands

    def test_hard_control_first(self):
        monk = dict(MONK)
        kept, ev = P.filter_incoming_control(monk, [{"name": "Poison", "attribute": "paralysis"}], 5)
        assert kept == [] and ev[0]["effects"] == ["Poison"]

    def test_non_control_batch_keeps_immunity(self):
        monk = dict(MONK)
        kept, ev = P.filter_incoming_control(monk, [dict(BLEED)], 5)
        assert kept == [BLEED] and ev == [] and "passive_state" not in monk

    def test_non_monk_passthrough(self):
        rows = [dict(STUN)]
        assert P.filter_incoming_control({}, rows, 5) == (rows, [])
        assert P.filter_incoming_control(None, rows, 5) == (rows, [])


# =============================================================================
# Саламандр — Разгорание
# =============================================================================
SALAMANDER = {"passive_key": P.PASSIVE_SALAMANDER}


class TestSalamander:
    def _fire(self, s, primary, types=("fire",), log_type="fire", log=None):
        actx = P.begin_attack(s, 1, primary, list(types))
        m = P.target_damage_mods(actx, s, primary, log_type, True)
        P.record_strike(actx, primary, {"damage_type": log_type}, log or landed(log_type))
        P.finish_attack(actx, s)
        return m

    def test_consecutive_fire_hits_stack_cap_5(self):
        s = battle({1: part(0, P.PASSIVE_SALAMANDER), 2: part(1)})
        got = [self._fire(s, 2)["pct_by_type"].get("fire", 0) for _ in range(8)]
        assert got == [0, 6, 12, 18, 24, 30, 30, 30]
        assert ps(s, 1)["kindling_stacks"] == 5

    def test_bonus_only_on_fire_entries_vs_kindling_target(self):
        s = battle({1: part(0, P.PASSIVE_SALAMANDER, passive_state={"kindling_target": 2,
                                                                  "kindling_stacks": 2}),
                    2: part(1), 3: part(1)})
        actx = P.begin_attack(s, 1, 2, ["fire", "magic"])
        assert P.target_damage_mods(actx, s, 2, "fire", True)["pct_by_type"] == {"fire": 12}
        assert P.target_damage_mods(actx, s, 2, "magic", True)["pct_by_type"] == {}
        assert P.target_damage_mods(actx, s, 3, "fire", False)["pct_by_type"] == {}

    def test_reset_on_target_switch(self):
        s = battle({1: part(0, P.PASSIVE_SALAMANDER), 2: part(1), 3: part(1)})
        for _ in range(3):
            self._fire(s, 2)
        m = self._fire(s, 3)
        assert m["pct_by_type"] == {}
        assert ps(s, 1)["kindling_target"] == 3 and ps(s, 1)["kindling_stacks"] == 1

    def test_reset_on_non_fire_attack(self):
        s = battle({1: part(0, P.PASSIVE_SALAMANDER), 2: part(1)})
        for _ in range(3):
            self._fire(s, 2)
        self._fire(s, 2, types=("ice",), log_type="ice")
        assert ps(s, 1)["kindling_stacks"] == 0 and ps(s, 1)["kindling_target"] is None
        assert self._fire(s, 2)["pct_by_type"] == {}

    def test_missed_fire_attack_doesnt_add(self):
        s = battle({1: part(0, P.PASSIVE_SALAMANDER), 2: part(1)})
        self._fire(s, 2)
        self._fire(s, 2, log=DODGED)
        assert ps(s, 1)["kindling_stacks"] == 1

    def test_burn_plus_one_only(self):
        rows = [{"effect_name": "Burn", "duration": 2}, {"name": "Burn", "attribute": "hp", "duration": 3},
                {"effect_name": "Bleeding", "duration": 2}, dict(STUN), dict(PARALYSIS)]
        out, c = P.adjust_outgoing_enemy_rows(SALAMANDER, rows, 1)
        assert [r["duration"] for r in out] == [3, 4, 2, 1, 1]
        assert c == [{"key": P.PASSIVE_SALAMANDER, "kind": "duration_plus", "value": 1, "owner": 1}]
        out, c = P.adjust_outgoing_enemy_rows(SALAMANDER, [dict(BLEED)], 1)
        assert out == [BLEED] and c == []

    def test_non_salamander_doesnt_stack(self):
        s = battle({1: part(0), 2: part(1)})
        self._fire(s, 2)
        assert ps(s, 1) == {"used_magic": True}


# =============================================================================
# Кастер — Чистая энергия
# =============================================================================
CASTER = {"passive_key": P.PASSIVE_CASTER}


class TestCaster:
    def test_resist_ignore_magic_only(self):
        s = battle({1: part(0, P.PASSIVE_CASTER), 2: part(1)})
        actx = P.begin_attack(s, 1, 2, ["magic"])
        m = P.target_damage_mods(actx, s, 2, "magic", True)
        assert m["resist_ignore"] == {"magic": 0.25}
        assert m["contributions"] == [{"key": P.PASSIVE_CASTER, "kind": "resist_ignore", "value": 25, "owner": 1}]
        m = P.target_damage_mods(actx, s, 2, "fire", True)
        assert m["resist_ignore"] == {"magic": 0.25}     # engine applies only to resolved `magic`
        assert m["contributions"] == []

    @pytest.mark.parametrize("log,kept", [
        ({"resist_ignored_pct": 2.5}, True), ({"resist_ignored_pct": 0}, False),
        ({}, False), (None, False), ({"resist_ignored_pct": "abc"}, False),
    ])
    def test_pure_energy_logged_only_when_something_was_ignored(self, log, kept):
        pure = {"key": P.PASSIVE_CASTER, "kind": "resist_ignore", "value": 25, "owner": 1}
        other = {"key": P.PASSIVE_SABER, "kind": "damage_pct", "value": 15, "owner": 1}
        out = P.attacker_contribs_for_log([pure, other], log)
        assert out == ([pure, other] if kept else [other])
        assert P.attacker_contribs_for_log(None, log) == []

    def test_non_caster_no_ignore(self):
        s = battle({1: part(0, P.PASSIVE_SPARKMAGE), 2: part(1)})
        actx = P.begin_attack(s, 1, 2, ["magic"])
        assert P.target_damage_mods(actx, s, 2, "magic", True)["resist_ignore"] is None

    @pytest.mark.parametrize("raw,eff", [(0, 0), (1, 1), (5, 5), (10, 9), (15, 14), (25, 23),
                                         (20, 18), (100, 90), (35, 32)])
    def test_mana_formula(self, raw, eff):
        assert P.mana_cost(CASTER, raw) == eff
        assert P.mana_cost(CASTER, raw) == (raw * 90 + 50) // 100

    def test_mana_non_caster(self):
        for p in ({}, None, {"passive_key": P.PASSIVE_SPARKMAGE}):
            assert P.mana_cost(p, 15) == 15

    def test_mana_contribution(self):
        assert P.mana_discount_contribution(1, 3) == {"key": P.PASSIVE_CASTER, "kind": "mana_discount",
                                                       "value": 1, "owner": 3}


# =============================================================================
# Искромаг — Цепная молния
# =============================================================================
class TestSparkmage:
    @pytest.mark.parametrize("dtype", ["electricity", "wind"])
    def test_chain_to_other_enemy(self, dtype):
        s = battle({1: part(0, P.PASSIVE_SPARKMAGE), 2: part(1), 3: part(1), 4: part(1, hp=0)})
        trig = {"damage_type": dtype, "amount": 3}
        with rolls(True) as (rp, pk):
            actx = P.begin_attack(s, 1, 2, ["physical", dtype])
            P.record_strike(actx, 2, {"damage_type": "physical"}, landed("physical"))
            P.record_strike(actx, 2, trig, landed(dtype))
            plan = P.plan_extra_hit(actx, s)
        assert rp.call_args[0][0] == 25 and list(pk.call_args[0][0]) == [3]
        assert plan["target_pid"] == 3 and plan["entry"] is trig and plan["mult"] == 0.5
        assert plan["kind"] == "chain" and plan["contribution"]["value"] == 50

    def test_chain_roll_fails(self):
        s = battle({1: part(0, P.PASSIVE_SPARKMAGE), 2: part(1), 3: part(1)})
        with rolls(False):
            actx = P.begin_attack(s, 1, 2, ["wind"])
            P.record_strike(actx, 2, {}, landed("wind"))
            assert P.plan_extra_hit(actx, s) is None

    def test_echo_on_same_target_when_alone(self):
        s = battle({1: part(0, P.PASSIVE_SPARKMAGE), 2: part(1)})
        with rolls(True) as (rp, _):
            actx = P.begin_attack(s, 1, 2, ["electricity"])
            P.record_strike(actx, 2, {"damage_type": "electricity"}, landed("electricity"))
            plan = P.plan_extra_hit(actx, s)
        assert rp.call_args[0][0] == 25
        assert plan["kind"] == "echo" and plan["target_pid"] == 2 and plan["mult"] == 0.4
        assert plan["contribution"]["value"] == 40

    def test_echo_roll_fails(self):
        s = battle({1: part(0, P.PASSIVE_SPARKMAGE), 2: part(1)})
        with rolls(False):
            actx = P.begin_attack(s, 1, 2, ["electricity"])
            P.record_strike(actx, 2, {}, landed("electricity"))
            assert P.plan_extra_hit(actx, s) is None

    def test_primary_dead_and_no_others_nothing(self):
        s = battle({1: part(0, P.PASSIVE_SPARKMAGE), 2: part(1)})
        with patch.object(P, "roll_pct", side_effect=_boom):
            actx = P.begin_attack(s, 1, 2, ["electricity"])
            P.record_strike(actx, 2, {}, landed("electricity"))
            s["participants"]["2"]["hp"] = 0
            assert P.plan_extra_hit(actx, s) is None

    @pytest.mark.parametrize("log", [landed("fire"), landed("magic"), DODGED,
                                     {"damage_type": "electricity", "hit_chance_failed": True}])
    def test_needs_landed_electricity_or_wind(self, log):
        s = battle({1: part(0, P.PASSIVE_SPARKMAGE), 2: part(1), 3: part(1)})
        with patch.object(P, "roll_pct", side_effect=_boom):
            actx = P.begin_attack(s, 1, 2, ["electricity"])
            P.record_strike(actx, 2, {"damage_type": "electricity"}, log)
            assert P.plan_extra_hit(actx, s) is None

    def test_once_per_attack_and_extra_doesnt_retrigger(self):
        s = battle({1: part(0, P.PASSIVE_SPARKMAGE), 2: part(1), 3: part(1)})
        with rolls(True) as (rp, _):
            actx = P.begin_attack(s, 1, 2, ["wind"])
            P.record_strike(actx, 2, {}, landed("wind"))
            P.record_strike(actx, 3, {}, landed("wind"))          # AoE
            assert P.plan_extra_hit(actx, s) is not None
            P.record_strike(actx, 3, {}, landed("wind"), is_extra=True)
            assert P.plan_extra_hit(actx, s) is None
        assert rp.call_count == 1


# =============================================================================
# battle_engine.compute_damage_with_rolls — FEAT-189 kwargs
# =============================================================================
ATTACKER = {"strength": 100, "critical_hit_chance": 0, "critical_damage": 125}
DEFENDER = {"dodge": 0}


def _entry(t="magic", amount=0, chance=100):
    return {"damage_type": t, "amount": amount, "chance": chance}


@contextmanager
def engine_rolls(hit=True, crit=False, dodge=False):
    with patch.object(E, "roll_chance", return_value=hit), \
            patch.object(E, "roll_crit", return_value=crit) as rc, \
            patch.object(E, "roll_dodge", return_value=dodge):
        yield rc


class TestEngineKwargs:
    async def test_defaults_unchanged(self):
        with engine_rolls():
            a = await E.compute_damage_with_rolls(_entry(), ATTACKER, None, {}, DEFENDER, {"magic": 40})
            b = await E.compute_damage_with_rolls(_entry(), ATTACKER, None, {}, DEFENDER, {"magic": 40},
                                                  force_crit=False, crit_damage_bonus=0, resist_ignore=None)
        assert a == b
        f, log = a
        assert f == pytest.approx(60)
        assert "forced_crit" not in log and "resist_ignored_pct" not in log
        assert log["critical"] is False and log["resist_pct"] == 40

    async def test_natural_crit_default_mult(self):
        with engine_rolls(crit=True):
            f, log = await E.compute_damage_with_rolls(_entry(), ATTACKER, None, {}, DEFENDER, {})
        assert f == pytest.approx(125) and log["crit_mul"] == 1.25 and "forced_crit" not in log

    async def test_force_crit_skips_crit_roll(self):
        with engine_rolls(crit=False) as rc:
            f, log = await E.compute_damage_with_rolls(_entry(), ATTACKER, None, {}, DEFENDER, {},
                                                       force_crit=True)
        rc.assert_not_called()
        assert f == pytest.approx(125) and log["critical"] is True and log["forced_crit"] is True

    async def test_force_crit_without_hit_is_a_miss(self):
        with engine_rolls(hit=False):
            f, log = await E.compute_damage_with_rolls(_entry(), ATTACKER, None, {}, DEFENDER, {},
                                                       force_crit=True, crit_damage_bonus=50)
        assert f == 0 and log["hit_chance_failed"] is True
        assert "critical" not in log and "forced_crit" not in log

    async def test_force_crit_on_dodge_is_dodged(self):
        with engine_rolls(dodge=True):
            f, log = await E.compute_damage_with_rolls(_entry(), ATTACKER, None, {}, DEFENDER, {},
                                                       apply_dodge=True, force_crit=True)
        assert f == 0 and log["dodged"] is True and "forced_crit" not in log

    async def test_crit_damage_bonus_50_is_x175(self):
        with engine_rolls():
            f, log = await E.compute_damage_with_rolls(_entry(), ATTACKER, None, {}, DEFENDER, {},
                                                       force_crit=True, crit_damage_bonus=50)
        assert log["crit_mul"] == pytest.approx(1.75) and f == pytest.approx(175)

    async def test_crit_damage_bonus_also_on_natural_crit_and_none_without_crit(self):
        with engine_rolls(crit=True):
            f, _ = await E.compute_damage_with_rolls(_entry(), ATTACKER, None, {}, DEFENDER, {},
                                                     crit_damage_bonus=25)
        assert f == pytest.approx(150)
        with engine_rolls(crit=False):
            f, log = await E.compute_damage_with_rolls(_entry(), ATTACKER, None, {}, DEFENDER, {},
                                                       crit_damage_bonus=50)
        assert f == pytest.approx(100) and log["critical"] is False

    async def test_resist_ignore_positive_magic(self):
        with engine_rolls():
            f, log = await E.compute_damage_with_rolls(_entry(), ATTACKER, None, {}, DEFENDER,
                                                       {"all": 20, "magic": 20},
                                                       resist_ignore={"magic": 0.25})
        assert log["resist_ignored_pct"] == 10 and log["resist_pct"] == 30
        assert f == pytest.approx(70)

    async def test_vulnerability_not_reduced(self):
        with engine_rolls():
            f, log = await E.compute_damage_with_rolls(_entry(), ATTACKER, None, {}, DEFENDER,
                                                       {"magic": -20}, resist_ignore={"magic": 0.25})
        assert f == pytest.approx(120) and "resist_ignored_pct" not in log

    async def test_ignore_only_for_listed_resolved_type(self):
        with engine_rolls():
            f, log = await E.compute_damage_with_rolls(_entry("fire"), ATTACKER, None, {}, DEFENDER,
                                                       {"fire": 40}, resist_ignore={"magic": 0.25})
        assert f == pytest.approx(60) and "resist_ignored_pct" not in log

    async def test_all_entry_resolved_to_magic_weapon_gets_ignore(self):
        weapon = {"primary_damage_type": "magic", "effective_damage": 0}
        with engine_rolls():
            f, log = await E.compute_damage_with_rolls(_entry("all"), ATTACKER, weapon, {}, DEFENDER,
                                                       {"magic": 40}, resist_ignore={"magic": 0.25})
        assert log["damage_type"] == "magic" and log["resist_ignored_pct"] == 10
        assert f == pytest.approx(70)

    async def test_ignore_fraction_clamped(self):
        with engine_rolls():
            f, log = await E.compute_damage_with_rolls(_entry(), ATTACKER, None, {}, DEFENDER,
                                                       {"magic": 40}, resist_ignore={"magic": 3})
        assert f == pytest.approx(100) and log["resist_ignored_pct"] == 40

    async def test_full_passive_combo(self):
        """Smoke case from T2: forced crit +50 with 25% of 40 magic resist ignored."""
        with engine_rolls():
            f, log = await E.compute_damage_with_rolls(_entry(), ATTACKER, None, {}, DEFENDER,
                                                       {"magic": 40}, apply_dodge=False, force_crit=True,
                                                       crit_damage_bonus=50, resist_ignore={"magic": 0.25})
        assert log["forced_crit"] is True and log["resist_ignored_pct"] == 10
        assert f == pytest.approx(175 * 0.7)
