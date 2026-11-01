"""FEAT-189 (Task #7) — subclass passives wave 1, end to end.

Every test here drives the REAL ``POST /battles/{id}/action`` endpoint
(``_make_action_core``) with the REAL buffs engine, the REAL damage formula
(``battle_engine.compute_damage_with_rolls`` behind a spy) and the REAL
``passives`` module that ``main`` imported. The harness (module-level
``sys.modules`` stubs, private copies of ``buffs`` / ``redis_state``) is the
FEAT-188 one from ``test_subclass_passives.py``.

Randomness is pinned, never sampled:
  * passive chances — ``patch.object(P, "roll_pct" / "pick")`` on the module
    ``main`` actually calls (``main.passives``);
  * effect rolls — ``main.roll_chance``; dodge — ``main.roll_dodge``;
  * the engine's hit / crit rolls — ``battle_engine.roll_chance / roll_crit``.

Covered (feature file §4 Task 7):
  * regression guard: passive-less fighters → same events / engine kwargs as
    before, no passive roll consumed, no ``passives`` key, ``passive_state``
    untouched (except the by-design ``used_magic`` mark); unknown keys are
    inert; since FEAT-190 no registry passive is left unimplemented (wave-2
    effects: test_passives_wave2_integration.py);
  * Saber: +15 vs NPC, kill by a DoT tick credited to the DoT owner, run stacks
    written via ``set_saber_run_stacks`` and effective in the same battle,
    PvP «Несгибаемость», seed via ``_saber_seed`` / ``_assemble_battle``;
  * Trickster «Обман»: ``dodged + deceived`` event, never Assassin's shadow;
    durations +1 (not stun) on the skill and the item path;
  * Assassin shadow from a real dodge → forced crit +25 on the next attack;
  * Mechanic / Sparkmage extra hits: once per attack, live other enemy at hit
    time, own dodge roll, no recursion, joiner enables splash, dead primary →
    no echo;
  * Monk: +pp to control, immunity on every ``_land_enemy_effects`` site
    (attack, attack all-enemies, support, defense, item row, weapon coating);
  * Agent: post-damage re-roll on crit (attack rows + coating), nothing
    without a crit, primary effects still land on a dodge;
  * Caster: discount in ``_pay_skill_costs`` (affords 10 mana with 9),
    ``resource_spend`` shape, non-Casters keep the 3-key dict, resist ignore;
  * Gladiator: ramp skips a stunned turn, arena surplus on both sides;
  * Inquisitor: stacks via own hits, an ally's non-physical hit benefits, a
    scroll marks «магия»;
  * Lancer: the steal shows in the attacker's NEXT attack;
  * Archer / Salamander through the real path;
  * log shapes the frontend reads (``passives`` kinds, ``passive_proc`` fields,
    ``extra_hit`` / ``extra_mult``);
  * Redis plumbing: ``init_battle_state`` keys, Saber run-key helpers.
"""

import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_subclass_passives import (  # noqa: F401 — harness + sys.modules setup
    ATTACK_SKILL,
    INFO_ATTRS,
    NO_ATTACK,
    REAL_BUFFS,
    SCROLL,
    TURN_ATTRS,
    _DamageSpy,
    _REAL_apply_flat_modifiers,
    _REAL_passive_damage_bonus,
    _damage_row,
    _mock_db,
    _mock_response,
    _participant,
    _registry,
    app,
    battle_engine,
    get_db,
    main,
    real_redis_state,
)
from fastapi.testclient import TestClient

# The module `main` really calls — patch THIS one (the harness file's
# `passives` is a private copy and patching it would change nothing here).
P = main.passives
assert not isinstance(P, MagicMock)
assert P.__file__.replace("\\", "/").endswith("/passives.py")

ATT, DEF, THIRD, FOURTH = 1, 2, 3, 4
CHAR = {ATT: 10, DEF: 20, THIRD: 30, FOURTH: 40}

# TURN_ATTRS: strength 20 + damage 5 = base 25; entry amount 20 → raw 45.
RAW = 45.0

PROC_FIELDS = {"event", "who", "key", "kind", "target", "value", "stacks", "stolen", "effects"}
CONTRIB_FIELDS = {"key", "kind", "value", "owner"}
CONTRIB_KINDS = {
    "damage_pct", "resist_pct", "forced_crit", "resist_ignore", "extra_hit",
    "deceit", "duration_plus", "mana_discount",
}
ENGINE_KWARGS_OLD = {
    "damage_entry", "attacker_attr", "weapon", "percent_buffs",
    "defender_attr", "percent_resists", "class_id", "apply_dodge",
}


# ══════════════════════════════════════════════════════════════════════════════
# Builders
# ══════════════════════════════════════════════════════════════════════════════

def _p(pid, team, key=None, **over):
    """A post-FEAT-189 participant (is_npc / passive_state present)."""
    base = dict(passive_key=key, is_npc=False, passive_state={}, hp=1000, max_hp=1000)
    base.update(over)
    return _participant(CHAR[pid], team, **base)


def _battle(parts, actor=ATT, **extra):
    st = {
        "turn_number": 3, "next_actor": actor, "first_actor": actor,
        "initiator_acted_once": True, "first_cycle": False,
        "turn_order": list(parts), "total_turns": 2, "last_turn": None,
        "deadline_at": "2026-01-01T00:00:00",
        "participants": {str(k): v for k, v in parts.items()},
        "active_effects": {},
    }
    st.update(extra)
    return st


def _duel(att_key=None, def_key=None, att=None, de=None, **extra):
    return _battle({ATT: _p(ATT, 0, att_key, **(att or {})),
                    DEF: _p(DEF, 1, def_key, **(de or {}))}, **extra)


def _trio(att_key=None, att=None, de=None, third=None, **extra):
    """Attacker vs two enemies."""
    return _battle({ATT: _p(ATT, 0, att_key, **(att or {})),
                    DEF: _p(DEF, 1, **(de or {})),
                    THIRD: _p(THIRD, 1, **(third or {}))}, **extra)


def _skill(dtype="physical", effects=(), cost_mana=0, entries=None, slot="no_weapon", sid=1):
    return dict(
        ATTACK_SKILL, id=sid, skill_id=sid,
        damage_entries=entries if entries is not None
        else [_damage_row(damage_type=dtype, weapon_slot=slot)],
        effects=[dict(e) for e in effects], cost_mana=cost_mana,
    )


def _eff(name, side="enemy", duration=2, chance=100, attr=None, mag=5):
    return {"effect_name": name, "attribute_key": attr, "magnitude": mag,
            "duration": duration, "chance": chance, "target_side": side}


def _pl(attack=None, defense=None, support=None, item=None, target=DEF, actor=ATT):
    return {
        "participant_id": actor, "target_id": target,
        "skills": {"attack_skill_id": attack, "defense_skill_id": defense,
                   "support_skill_id": support, "item_id": item},
    }


class _Result(SimpleNamespace):
    def of(self, event):
        return [e for e in self.events if e["event"] == event]

    @property
    def dmg(self):
        return self.of("damage")

    @property
    def procs(self):
        return self.of("passive_proc")

    def ps(self, pid):
        return self.state["participants"][str(pid)].get("passive_state")

    def hp(self, pid):
        return self.state["participants"][str(pid)]["hp"]


def _run(state, payload, skills=None, attrs=None, crit=False, dodge=False,
         effect_roll=True, extra=None, expect=200):
    """One real action. `skills` = {skill_id: resolved rank}; `attrs` =
    {character_id: overrides of TURN_ATTRS}; `dodge` / `effect_roll` = bool,
    list (side_effect) or callable; `extra` = more patches (target → value)."""
    spy = _DamageSpy()
    save_state = AsyncMock()
    setter = AsyncMock(return_value=None)
    getter = AsyncMock(return_value=0)
    skills = skills or {}
    attrs = attrs or {}

    async def _fetch(cid):
        return {**TURN_ATTRS, **attrs.get(cid, {})}

    async def _resolved(sid, *_a, **_k):
        return skills.get(sid, NO_ATTACK)

    def _as_mock(v):
        if isinstance(v, list):
            return MagicMock(side_effect=v)
        if callable(v):
            return MagicMock(side_effect=v)
        return MagicMock(return_value=v)

    dodge_mock = _as_mock(dodge)
    roll_chance_mock = _as_mock(effect_roll)
    patches = {
        "main.get_redis_client": AsyncMock(return_value=AsyncMock()),
        "main.save_state": save_state,
        "main.state_key": MagicMock(return_value="battle:1:state"),
        "main.write_turn": AsyncMock(),
        "main.finish_battle": AsyncMock(),
        "main._finalize_battle": AsyncMock(return_value=None),
        "main.get_battle": AsyncMock(return_value=None),
        "main.load_state": AsyncMock(return_value=state),
        "main.save_log": MagicMock(delay=MagicMock()),
        "main._distribute_pve_rewards": AsyncMock(return_value=None),
        "auth_http.requests.get": MagicMock(return_value=_mock_response(
            200, {"id": 5, "username": "player", "role": "user", "permissions": []})),
        "main.fetch_full_attributes": AsyncMock(side_effect=_fetch),
        "main.fetch_main_weapon": AsyncMock(return_value=None),
        "main.fetch_weapons": AsyncMock(
            return_value={"main_weapon": None, "additional_weapons": None}),
        "main.fetch_character_class_id": AsyncMock(return_value=1),
        "main.character_has_skill": AsyncMock(return_value=True),
        "main.get_resolved_skill": AsyncMock(side_effect=_resolved),
        "main.consume_item": AsyncMock(return_value={"status": "ok", "remaining_quantity": 1}),
        "main.roll_chance": roll_chance_mock,
        "main.roll_dodge": dodge_mock,
        "main.compute_damage_with_rolls": spy,
        "main.passive_damage_bonus": _REAL_passive_damage_bonus,
        **{f"main.{name}": fn for name, fn in REAL_BUFFS.items()},
        "main.apply_flat_modifiers": _REAL_apply_flat_modifiers,
        "main.set_saber_run_stacks": setter,
        "main.get_saber_run_stacks": getter,
    }
    patches.update(extra or {})
    patchers = [patch(t, v) for t, v in patches.items()]
    patchers.append(patch.object(battle_engine, "roll_crit", return_value=crit))
    patchers.append(patch.object(battle_engine, "roll_chance", return_value=True))
    db = _mock_db()

    async def _fake_get_db():
        yield db

    for p in patchers:
        p.start()
    try:
        app.dependency_overrides[get_db] = _fake_get_db
        with TestClient(app) as client:
            response = client.post("/battles/1/action", json=payload,
                                   headers={"Authorization": "Bearer fake-token"})
    finally:
        app.dependency_overrides.pop(get_db, None)
        for p in reversed(patchers):
            p.stop()
    assert response.status_code == expect, response.text
    events = response.json().get("events", []) if expect == 200 else []
    for ev in events:
        _assert_shapes(ev)
    return _Result(resp=response, events=events, spy=spy, state=state,
                   setter=setter, getter=getter, dodge=dodge_mock,
                   roll_chance=roll_chance_mock)


def _assert_shapes(ev):
    """The log contract the frontend renders (§3.5)."""
    if ev["event"] == "passive_proc":
        assert set(ev) <= PROC_FIELDS, ev
        assert {"who", "key", "kind"} <= set(ev), ev
    for c in ev.get("passives") or []:
        assert set(c) <= CONTRIB_FIELDS, ev
        assert c["kind"] in CONTRIB_KINDS, ev
        assert c["key"] in P.IMPLEMENTED_PASSIVES, ev
    if "extra_hit" in ev:
        assert ev["extra_hit"] in ("splash", "chain", "echo")
        assert isinstance(ev["extra_mult"], float)


def _next_turn(state, actor=ATT):
    st = copy.deepcopy(state)
    st["next_actor"] = actor
    return st


def _rolls(value=True):
    return patch.object(P, "roll_pct", MagicMock(return_value=value))


def _contrib(ev, key, kind=None):
    return [c for c in ev.get("passives") or []
            if c["key"] == key and (kind is None or c["kind"] == kind)]


# ══════════════════════════════════════════════════════════════════════════════
# Regression guard — fighters without passives
# ══════════════════════════════════════════════════════════════════════════════

class TestNoPassivesRegression:

    def _guarded(self, state, payload, **kw):
        roll, pick = MagicMock(return_value=True), MagicMock(return_value=None)
        with patch.object(P, "roll_pct", roll), patch.object(P, "pick", pick):
            r = _run(state, payload, **kw)
        assert not roll.called and not pick.called, "a passive roll was consumed"
        for ev in r.events:
            assert "passives" not in ev
            for k in ("forced_crit", "resist_ignored_pct", "extra_hit", "extra_mult",
                      "deceived", "mana_discount", "passive_key", "passive_pct"):
                assert k not in ev, (k, ev)
        assert not r.procs
        for call in r.spy.calls:
            assert set(call) == ENGINE_KWARGS_OLD, set(call) ^ ENGINE_KWARGS_OLD
        return r

    def test_physical_attack_events_are_the_old_ones(self):
        st = _duel(att={"mana": 50})
        r = self._guarded(st, _pl(attack=1), skills={1: _skill()})
        assert r.dmg == [{
            "event": "damage", "source": ATT, "target": DEF,
            "damage_type": "physical", "base": 25, "entry": 20, "buff_pct": 0,
            "after_buffs": RAW, "hit_chance_failed": False, "critical": False,
            "resist_pct": 0, "final": RAW,
        }]
        spend, = r.of("resource_spend")
        assert spend == {"event": "resource_spend", "who": ATT,
                         "energy": 0, "mana": 0, "stamina": 0}
        assert r.hp(DEF) == 1000 - RAW
        # physical: nobody's passive_state changes
        assert r.ps(ATT) == {} and r.ps(DEF) == {}

    def test_magic_attack_only_marks_used_magic(self):
        r = self._guarded(_duel(), _pl(attack=1), skills={1: _skill("magic")})
        assert r.ps(ATT) == {"used_magic": True}   # by design (Inquisitor's mark)
        assert r.ps(DEF) == {}

    def test_old_state_without_feat189_keys(self):
        st = _duel()
        for pd in st["participants"].values():
            pd.pop("is_npc")
            pd.pop("passive_state")
            pd.pop("passive_key")
        r = self._guarded(st, _pl(attack=1), skills={1: _skill()})
        assert r.dmg[0]["final"] == RAW
        assert all("passive_state" not in pd for pd in r.state["participants"].values())

    def test_dodge_event_unchanged(self):
        r = self._guarded(_duel(), _pl(attack=1), skills={1: _skill()}, dodge=True)
        assert r.dmg == [{"event": "damage", "source": ATT, "target": DEF,
                          "dodged": True, "final": 0}]
        assert r.spy.calls == []

    def test_effects_event_unchanged(self):
        r = self._guarded(_duel(), _pl(attack=1),
                          skills={1: _skill(effects=[_eff("Burn"), _eff("Stun", duration=1)])})
        ev, = r.of("apply_effects")
        assert set(ev) == {"event", "who", "kind", "effects"}
        assert [e["duration"] for e in ev["effects"]] == [2, 1]

    def test_aoe_and_scroll_unchanged(self):
        aoe = _skill(entries=[dict(_damage_row(), aoe_shape="all")])
        r = self._guarded(_trio(), _pl(attack=1), skills={1: aoe})
        assert sorted(e["target"] for e in r.dmg) == [DEF, THIRD]
        st = _duel(att={"fast_slots": [dict(SCROLL)]})
        r = self._guarded(st, _pl(item=50))
        assert r.dmg[0]["source_kind"] == "item"

    @pytest.mark.parametrize("key", [
        "no_such_passive", "warrior_knight", "rogue_bard", "mage_necromancer",
    ])
    def test_unknown_key_is_inert_too(self, key):
        # any key outside IMPLEMENTED_PASSIVES (garbage / subclass ids, not
        # passive keys) behaves like "no passive". Since FEAT-190 every
        # registry passive is implemented (checked below).
        st = _duel(att_key=key, def_key=key)
        self._guarded(st, _pl(attack=1), skills={1: _skill("magic")})


def _not_implemented_keys():
    try:
        reg = _registry()
    except BaseException:   # pytest.skip outcome when the registry is absent
        return []
    return sorted(s.passive.key for s in reg.SUBCLASSES if not s.passive.implemented)


class TestNoRegistryPassiveLeftUnimplemented:
    """FEAT-189 pinned «the 7 not-implemented registry passives do nothing
    through the pipeline». FEAT-190 (wave 2) implemented them: the registry
    has no `implemented=False` passive left and every registry key is live in
    battle. Their effects through `/action` are pinned in
    test_passives_wave2_integration.py."""

    def test_there_are_none(self):
        reg = _registry()
        assert _not_implemented_keys() == []
        keys = {s.passive.key for s in reg.SUBCLASSES}
        assert len(keys) == 21
        assert keys == set(P.IMPLEMENTED_PASSIVES)


# ══════════════════════════════════════════════════════════════════════════════
# Saber
# ══════════════════════════════════════════════════════════════════════════════

SABER = "saber_monster_hunter"


class TestSaber:

    def test_plus_15_vs_npc_only(self):
        r = _run(_duel(SABER, de={"is_npc": True}), _pl(attack=1), skills={1: _skill()})
        assert r.spy.calls[0]["percent_buffs"]["all"] == 15
        ev, = r.dmg
        assert ev["final"] == pytest.approx(RAW * 1.15)
        assert ev["passives"] == [{"key": SABER, "kind": "damage_pct", "value": 15, "owner": ATT}]

    @pytest.mark.parametrize("de", [{"is_npc": False}, {}])
    def test_nothing_vs_player_or_old_state(self, de):
        st = _duel(SABER, de=de)
        if not de:
            st["participants"][str(DEF)].pop("is_npc")
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert r.spy.calls[0]["percent_buffs"].get("all", 0) == 0
        assert "passives" not in r.dmg[0]

    def _dot_kill_state(self, session=77):
        st = _trio(SABER, de={"hp": 5, "is_npc": True}, third={"is_npc": True},
                   dungeon_session_id=session)
        st["active_effects"] = {str(DEF): [{
            "name": "Bleeding", "attribute": "bleeding", "magnitude": 50,
            "duration": 2, "owner_id": ATT,
        }]}
        return st

    def test_kill_by_dot_tick_is_credited_and_persisted(self):
        # The Saber attacks THIRD; DEF dies from the Saber's own Bleeding tick.
        r = _run(self._dot_kill_state(), _pl(attack=1, target=THIRD), skills={1: _skill()})
        tick, = r.of("effect_tick")
        assert tick["target"] == DEF and tick["source"] == ATT
        assert r.hp(DEF) <= 0
        proc, = r.procs
        assert proc == {"event": "passive_proc", "who": ATT, "key": SABER,
                        "kind": "saber_kill", "target": DEF, "stacks": 1, "value": 2}
        assert r.ps(ATT)["saber_kills"] == 1
        r.setter.assert_awaited_once_with(77, CHAR[ATT], 1)

    def test_kill_stack_raises_damage_in_the_same_battle(self):
        r1 = _run(self._dot_kill_state(), _pl(attack=1, target=THIRD), skills={1: _skill()})
        st2 = _next_turn(r1.state)
        st2["participants"][str(THIRD)]["is_npc"] = False   # isolate the kill stack
        r2 = _run(st2, _pl(attack=1, target=THIRD), skills={1: _skill()})
        assert r2.spy.calls[0]["percent_buffs"]["all"] == 2
        assert r2.dmg[0]["passives"] == [
            {"key": SABER, "kind": "damage_pct", "value": 2, "owner": ATT}]

    def test_direct_kill_counts_and_stacks_cap(self):
        st = _trio(SABER, de={"hp": 1, "is_npc": True}, dungeon_session_id=9,
                   att={"passive_state": {"saber_kills": 4}})
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert [p["stacks"] for p in r.procs] == [5]
        r.setter.assert_awaited_once_with(9, CHAR[ATT], 5)
        st = _trio(SABER, de={"hp": 1, "is_npc": True}, dungeon_session_id=9,
                   att={"passive_state": {"saber_kills": 5}})
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert not r.procs and not r.setter.called

    def test_no_dungeon_no_kill_stacks(self):
        r = _run(self._dot_kill_state(session=None), _pl(attack=1, target=THIRD),
                 skills={1: _skill()})
        assert r.hp(DEF) <= 0
        assert not r.procs and not r.setter.called
        assert "saber_kills" not in r.ps(ATT)

    def test_non_saber_kill_in_dungeon_writes_nothing(self):
        st = self._dot_kill_state()
        st["participants"][str(ATT)]["passive_key"] = None
        r = _run(st, _pl(attack=1, target=THIRD), skills={1: _skill()})
        assert r.hp(DEF) <= 0 and not r.procs and not r.setter.called

    def test_pvp_resolve_stack_from_player_hits_then_resists(self):
        st = _duel(def_key=SABER)
        r1 = _run(st, _pl(attack=1), skills={1: _skill()})
        proc, = r1.procs
        assert proc == {"event": "passive_proc", "who": DEF, "key": SABER,
                        "kind": "saber_resolve", "stacks": 1, "value": 2}
        r2 = _run(_next_turn(r1.state), _pl(attack=1), skills={1: _skill()})
        assert r2.spy.calls[0]["percent_resists"]["all"] == 2
        assert _contrib(r2.dmg[0], SABER, "resist_pct") == [
            {"key": SABER, "kind": "resist_pct", "value": 2, "owner": DEF}]
        assert r2.ps(DEF)["saber_pvp"] == 2

    def test_no_resolve_from_npc_or_old_state_attacker(self):
        r = _run(_duel(def_key=SABER, att={"is_npc": True}), _pl(attack=1), skills={1: _skill()})
        assert not r.procs
        st = _duel(def_key=SABER)
        st["participants"][str(ATT)].pop("is_npc")
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert not r.procs


class TestSaberSeed:

    @pytest.mark.asyncio
    async def test_seed_reads_the_run_key_for_a_saber(self):
        snap = {"character_id": 10, "passive": {"key": SABER}}
        with patch.object(main, "get_saber_run_stacks", AsyncMock(return_value=3)) as g:
            assert await main._saber_seed(snap, 77) == {"saber_kills": 3}
        g.assert_awaited_once_with(77, 10)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("snap, session", [
        ({"character_id": 10, "passive": {"key": SABER}}, None),
        ({"character_id": 10, "passive": {"key": "archer_first_blood"}}, 77),
        ({"character_id": 10, "passive": None}, 77),
        ({"character_id": 10}, 77),
    ])
    async def test_no_read_without_saber_or_dungeon(self, snap, session):
        with patch.object(main, "get_saber_run_stacks", AsyncMock(return_value=3)) as g:
            assert await main._saber_seed(snap, session) == {}
        assert not g.called

    @pytest.mark.asyncio
    async def test_zero_and_failure_give_empty_state(self):
        snap = {"character_id": 10, "passive": {"key": SABER}}
        with patch.object(main, "get_saber_run_stacks", AsyncMock(return_value=0)):
            assert await main._saber_seed(snap, 77) == {}
        with patch.object(main, "get_saber_run_stacks",
                          AsyncMock(side_effect=RuntimeError("redis down"))), \
                patch.object(main, "logger") as logger:
            assert await main._saber_seed(snap, 77) == {}
        logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_assemble_battle_seeds_redis_not_mongo(self):
        participants = [SimpleNamespace(id=11, character_id=101, team=0),
                        SimpleNamespace(id=12, character_id=102, team=1)]

        async def _info(char_id, pid):
            return {"participant_id": pid, "character_id": char_id,
                    "attributes": dict(INFO_ATTRS), "fast_slots": [],
                    "passive": {"key": SABER} if char_id == 101 else None,
                    "is_npc": False}

        async def _execute(query, params=None):
            res = MagicMock()
            res.fetchone.return_value = (1,) if (params or {}).get("cid") == 102 else (0,)
            return res

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=_execute)
        fake_rds = AsyncMock()
        save_snapshot = AsyncMock()
        getter = AsyncMock(return_value=4)
        httpx_client = MagicMock()
        httpx_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
            post=AsyncMock(return_value=MagicMock(status_code=200))))
        httpx_client.return_value.__aexit__ = AsyncMock(return_value=False)
        ps = [
            patch.object(main, "build_participant_info", AsyncMock(side_effect=_info)),
            patch.object(main, "create_battle",
                         AsyncMock(return_value=(SimpleNamespace(id=555), participants))),
            patch.object(main, "save_snapshot", save_snapshot),
            patch.object(main, "cache_snapshot", AsyncMock()),
            patch.object(main, "get_redis_client", AsyncMock(return_value=AsyncMock())),
            patch.object(main, "init_battle_state", real_redis_state.init_battle_state),
            patch.object(main, "compute_initiative", real_redis_state.compute_initiative),
            patch.object(main, "utc_now", real_redis_state.utc_now),
            patch.object(main, "get_saber_run_stacks", getter),
            patch.object(main.httpx, "AsyncClient", httpx_client),
            patch.object(real_redis_state, "get_redis_client", AsyncMock(return_value=fake_rds)),
        ]
        for p in ps:
            p.start()
        try:
            await main._assemble_battle(db, [101, 102], [0, 1], "pve", 7, dungeon_session_id=77)
        finally:
            for p in reversed(ps):
                p.stop()

        stored = json.loads(next(c.args[1] for c in fake_rds.set.call_args_list
                                 if "state" in str(c.args[0])))
        assert stored["dungeon_session_id"] == 77
        assert stored["participants"]["11"]["passive_state"] == {"saber_kills": 4}
        assert stored["participants"]["12"]["passive_state"] == {}
        assert stored["participants"]["11"]["is_npc"] is False
        assert stored["participants"]["12"]["is_npc"] is True    # DB truth
        getter.assert_awaited_once_with(77, 101)
        snap = save_snapshot.await_args.args[1]
        assert all("passive_state" not in s for s in snap)


# ══════════════════════════════════════════════════════════════════════════════
# Trickster «Обман» + Assassin «Из тени»
# ══════════════════════════════════════════════════════════════════════════════

TRICKSTER = "trickster_deceit"
ASSASSIN = "assassin_from_shadow"


class TestDeceit:

    def test_deceived_attack_does_not_pass(self):
        on_dodged = MagicMock(wraps=P.on_dodged)
        with _rolls(True), patch.object(P, "on_dodged", on_dodged):
            r = _run(_duel(def_key=TRICKSTER), _pl(attack=1), skills={1: _skill()})
        assert r.dmg == [{
            "event": "damage", "source": ATT, "target": DEF, "dodged": True, "final": 0,
            "deceived": True,
            "passives": [{"key": TRICKSTER, "kind": "deceit", "owner": DEF}],
        }]
        assert r.spy.calls == [] and r.hp(DEF) == 1000
        assert not on_dodged.called and not r.procs

    def test_deceit_is_never_a_real_dodge_for_the_shadow(self):
        """AoE on a Trickster and an Assassin: only the Trickster is deceived,
        the deceit produces no proc and nobody gets a shadow."""
        st = _battle({ATT: _p(ATT, 0), DEF: _p(DEF, 1, TRICKSTER), THIRD: _p(THIRD, 1, ASSASSIN)})
        aoe = _skill(entries=[dict(_damage_row(), aoe_shape="all")])
        with _rolls(True):
            r = _run(st, _pl(attack=1), skills={1: aoe})
        deceit = [e for e in r.dmg if e.get("deceived")]
        assert [e["target"] for e in deceit] == [DEF]
        assert not r.procs
        assert not (r.ps(THIRD) or {}).get("shadow_ready")

    def test_no_deceit_when_roll_fails(self):
        with _rolls(False):
            r = _run(_duel(def_key=TRICKSTER), _pl(attack=1), skills={1: _skill()})
        assert r.dmg[0]["final"] == RAW and "deceived" not in r.dmg[0]

    def test_no_deceit_roll_after_a_real_dodge(self):
        roll = MagicMock(return_value=True)
        with patch.object(P, "roll_pct", roll):
            r = _run(_duel(def_key=TRICKSTER), _pl(attack=1), skills={1: _skill()}, dodge=True)
        assert not roll.called
        assert r.dmg == [{"event": "damage", "source": ATT, "target": DEF,
                          "dodged": True, "final": 0}]

    def test_scroll_can_be_deceived(self):
        st = _duel(def_key=TRICKSTER, att={"fast_slots": [dict(SCROLL)]})
        with _rolls(True):
            r = _run(st, _pl(item=50))
        ev, = r.dmg
        assert ev["deceived"] is True and ev["dodged"] is True and ev["source_kind"] == "item"
        assert r.hp(DEF) == 1000


class TestAssassin:

    def test_real_dodge_sets_shadow_and_next_attack_is_forced_crit(self):
        r1 = _run(_duel(def_key=ASSASSIN), _pl(attack=1), skills={1: _skill()}, dodge=True)
        proc, = r1.procs
        assert proc == {"event": "passive_proc", "who": DEF, "key": ASSASSIN,
                        "kind": "shadow_ready"}
        assert r1.ps(DEF)["shadow_ready"] is True
        # the Assassin's own turn
        st2 = _next_turn(r1.state, actor=DEF)
        # DEF's character (20) belongs to user 6 in the harness DB fake
        as_user_6 = {"auth_http.requests.get": MagicMock(return_value=_mock_response(
            200, {"id": 6, "username": "p2", "role": "user", "permissions": []}))}
        r2 = _run(st2, _pl(attack=1, target=ATT, actor=DEF), skills={1: _skill()},
                  extra=as_user_6)
        call, = r2.spy.calls
        assert call["force_crit"] is True and call["crit_damage_bonus"] == 25
        ev, = r2.dmg
        assert ev["forced_crit"] is True and ev["critical"] is True
        assert ev["crit_mul"] == pytest.approx(1.25)   # critical_damage 100 + 25
        assert _contrib(ev, ASSASSIN, "forced_crit")[0]["value"] == 25
        assert r2.ps(DEF)["shadow_ready"] is False

    def test_attack_skill_without_damage_rows_keeps_the_shadow(self):
        # Review #1 note: a debuff-only attack skill must not consume the shadow.
        st = _duel(ASSASSIN, att={"passive_state": {"shadow_ready": True}})
        r = _run(st, _pl(attack=1),
                 skills={1: _skill(entries=[], effects=[_eff("Weakness", attr="strength")])})
        assert not r.spy.calls and not r.dmg
        assert r.ps(ATT)["shadow_ready"] is True
        # the next damaging attack is the one that spends it
        r2 = _run(_next_turn(r.state), _pl(attack=1), skills={1: _skill()})
        call, = r2.spy.calls
        assert call["force_crit"] is True and call["crit_damage_bonus"] == 25
        assert r2.ps(ATT)["shadow_ready"] is False

    def test_execute_below_30_percent(self):
        r = _run(_duel(ASSASSIN, de={"hp": 299}), _pl(attack=1), skills={1: _skill()})
        assert r.spy.calls[0]["percent_buffs"]["all"] == 20
        r = _run(_duel(ASSASSIN, de={"hp": 300}), _pl(attack=1), skills={1: _skill()})
        assert r.spy.calls[0]["percent_buffs"].get("all", 0) == 0


# ══════════════════════════════════════════════════════════════════════════════
# Extra hits — Mechanic «Шрапнель», Sparkmage «Цепная молния»
# ══════════════════════════════════════════════════════════════════════════════

MECHANIC = "mechanic_shrapnel"
SPARK = "sparkmage_chain_lightning"


def _extra(r):
    return [e for e in r.dmg if "extra_hit" in e]


class TestMechanic:

    def test_splash_on_other_live_enemy(self):
        roll = MagicMock(return_value=True)
        with patch.object(P, "roll_pct", roll), patch.object(P, "pick", lambda seq: seq[-1]):
            r = _run(_trio(MECHANIC), _pl(attack=1), skills={1: _skill()})
        prim, splash = r.dmg
        assert "extra_hit" not in prim and prim["target"] == DEF
        assert splash["target"] == THIRD
        assert splash["extra_hit"] == "splash" and splash["extra_mult"] == 0.4
        assert splash["final"] == pytest.approx(RAW * 0.4)
        assert splash["passives"] == [{"key": MECHANIC, "kind": "extra_hit",
                                       "value": 40, "owner": ATT}]
        assert r.hp(THIRD) == pytest.approx(1000 - RAW * 0.4)
        assert roll.call_count == 1          # one decision per attack
        assert len(r.spy.calls) == 2

    def test_splash_has_its_own_dodge_roll(self):
        with _rolls(True), patch.object(P, "pick", lambda seq: seq[-1]):
            r = _run(_trio(MECHANIC), _pl(attack=1), skills={1: _skill()},
                     dodge=[False, True])
        assert r.dodge.call_count == 2
        prim, splash = r.dmg
        assert prim["final"] == RAW
        assert splash == {"event": "damage", "source": ATT, "target": THIRD,
                          "dodged": True, "final": 0, "extra_hit": "splash",
                          "extra_mult": 0.4,
                          "passives": [{"key": MECHANIC, "kind": "extra_hit",
                                        "value": 40, "owner": ATT}]}
        assert r.hp(THIRD) == 1000

    def test_once_per_attack_even_with_many_entries_and_targets(self):
        sk = _skill(entries=[_damage_row(), _damage_row(amount=10)])
        st = _battle({ATT: _p(ATT, 0, MECHANIC), DEF: _p(DEF, 1),
                      THIRD: _p(THIRD, 1), FOURTH: _p(FOURTH, 1)})
        roll = MagicMock(return_value=True)
        with patch.object(P, "roll_pct", roll), patch.object(P, "pick", lambda seq: seq[0]):
            r = _run(st, _pl(attack=1), skills={1: sk})
        assert len(_extra(r)) == 1 and roll.call_count == 1
        assert _extra(r)[0]["target"] in (THIRD, FOURTH)
        # the extra hit replays the FIRST landed entry only
        assert _extra(r)[0]["entry"] == 20

    def test_dead_other_enemy_is_no_candidate_duel_bonus_instead(self):
        st = _trio(MECHANIC, third={"hp": 0, "defeated": True})
        with _rolls(True):
            r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert not _extra(r)
        assert r.spy.calls[0]["percent_buffs"]["all"] == 35
        assert r.dmg[0]["passives"] == [{"key": MECHANIC, "kind": "damage_pct",
                                         "value": 35, "owner": ATT}]
        assert r.hp(THIRD) == 0

    def test_duel_roll_failed_gives_nothing(self):
        with _rolls(False):
            r = _run(_duel(MECHANIC), _pl(attack=1), skills={1: _skill()})
        assert r.spy.calls[0]["percent_buffs"].get("all", 0) == 0 and not _extra(r)

    def test_no_splash_without_a_landed_hit(self):
        roll = MagicMock(return_value=True)
        with patch.object(P, "roll_pct", roll):
            r = _run(_trio(MECHANIC), _pl(attack=1), skills={1: _skill()}, dodge=True)
        assert not _extra(r) and not roll.called

    def test_primary_killed_splash_still_goes_to_the_live_one(self):
        with _rolls(True), patch.object(P, "pick", lambda seq: seq[0]):
            r = _run(_trio(MECHANIC, de={"hp": 1}), _pl(attack=1), skills={1: _skill()})
        ex, = _extra(r)
        assert ex["target"] == THIRD and r.hp(DEF) <= 0

    def test_mid_battle_joiner_enables_splash(self):
        with _rolls(True), patch.object(P, "pick", lambda seq: seq[0]):
            r1 = _run(_duel(MECHANIC), _pl(attack=1), skills={1: _skill()})
            assert not _extra(r1)
            assert _contrib(r1.dmg[0], MECHANIC, "damage_pct")[0]["value"] == 35
            st2 = _next_turn(r1.state)
            # exactly what admin_approve_join_request writes for a joiner
            st2["participants"][str(THIRD)] = _p(THIRD, 1)
            st2["turn_order"].append(THIRD)
            r2 = _run(st2, _pl(attack=1), skills={1: _skill()})
        ex, = _extra(r2)
        assert ex["target"] == THIRD and ex["extra_hit"] == "splash"
        assert not _contrib(r2.dmg[0], MECHANIC, "damage_pct")   # no duel bonus now

    def test_splash_does_not_trigger_on_hit_passives_or_chain(self):
        """The extra hit is from a Mechanic; even with rolls always True there
        is no second extra hit and nothing is recorded for the splashed one
        (e.g. a Saber hit by the splash gets no «Несгибаемость» stack)."""
        st = _trio(MECHANIC, third={"passive_key": SABER})
        with _rolls(True), patch.object(P, "pick", lambda seq: seq[-1]):
            r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert len(_extra(r)) == 1 and _extra(r)[0]["target"] == THIRD
        assert not r.procs
        assert "saber_pvp" not in (r.ps(THIRD) or {})

    def test_scroll_can_splash(self):
        st = _trio(MECHANIC, att={"fast_slots": [dict(SCROLL)]})
        with _rolls(True), patch.object(P, "pick", lambda seq: seq[0]):
            r = _run(st, _pl(item=50))
        ex, = _extra(r)
        assert ex["source_kind"] == "item" and ex["target"] == THIRD


class TestSparkmage:

    def test_chain_on_electricity(self):
        with _rolls(True), patch.object(P, "pick", lambda seq: seq[0]):
            r = _run(_trio(SPARK), _pl(attack=1), skills={1: _skill("electricity")})
        ex, = _extra(r)
        assert ex["extra_hit"] == "chain" and ex["extra_mult"] == 0.5
        assert ex["target"] == THIRD and ex["final"] == pytest.approx(RAW * 0.5)

    def test_physical_never_chains(self):
        roll = MagicMock(return_value=True)
        with patch.object(P, "roll_pct", roll):
            r = _run(_trio(SPARK), _pl(attack=1), skills={1: _skill()})
        assert not _extra(r) and not roll.called

    def test_echo_on_the_same_target_when_alone(self):
        with _rolls(True):
            r = _run(_duel(SPARK), _pl(attack=1), skills={1: _skill("wind")})
        prim, echo = r.dmg
        assert echo["target"] == DEF and echo["extra_hit"] == "echo"
        assert echo["extra_mult"] == 0.4
        assert echo["final"] == pytest.approx(RAW * 0.4)
        assert r.hp(DEF) == pytest.approx(1000 - RAW * 1.4)

    def test_dead_primary_gets_no_echo(self):
        roll = MagicMock(return_value=True)
        with patch.object(P, "roll_pct", roll):
            r = _run(_duel(SPARK, de={"hp": 1}), _pl(attack=1),
                     skills={1: _skill("electricity")})
        assert len(r.dmg) == 1 and not _extra(r)
        assert not roll.called
        assert r.of("participant_defeated")

    def test_chain_roll_failed(self):
        with _rolls(False):
            r = _run(_trio(SPARK), _pl(attack=1), skills={1: _skill("electricity")})
        assert not _extra(r)


# ══════════════════════════════════════════════════════════════════════════════
# Monk «Гармония»
# ══════════════════════════════════════════════════════════════════════════════

MONK = "monk_harmony"
KNOCK = _eff("Knockdown", attr="random", duration=1)
STUN = _eff("Stun", duration=1)


def _control_on(state, pid):
    names = {"stun", "knockdown", "windburn"}
    return [e for e in state["active_effects"].get(str(pid), [])
            if (e.get("name") or "").lower() in names]


def _monk_site(site):
    """(state, payload, skills) landing one control row on a Monk at `site`."""
    if site == "attack":
        return _duel(def_key=MONK), _pl(attack=1), {1: _skill(effects=[KNOCK, _eff("Burn")])}
    if site == "attack_all_enemies":
        row = dict(STUN, target_side="all_enemies")
        return _duel(def_key=MONK), _pl(attack=1), {1: _skill(effects=[row])}
    if site == "support":
        return _duel(def_key=MONK), _pl(support=2), {2: _skill(entries=[], effects=[STUN], sid=2)}
    if site == "defense":
        return _duel(def_key=MONK), _pl(defense=3), {3: _skill(entries=[], effects=[STUN], sid=3)}
    if site == "item":
        slot = dict(SCROLL, damage_entries=[], effects=[
            {"effect_name": "Stun", "target_side": "enemy", "chance": 100, "duration": 1}])
        return _duel(def_key=MONK, att={"fast_slots": [slot]}), _pl(item=50), {}
    if site == "coating":
        coating = {"turns_left": 3, "item_id": 60, "name": "Яд", "bonus_damage": 0,
                   "effects": [STUN]}
        return (_duel(def_key=MONK, att={"weapon_coating": coating}), _pl(attack=1),
                {1: _skill(slot="main_weapon")})
    raise AssertionError(site)


class TestMonk:

    @pytest.mark.parametrize("site", [
        "attack", "attack_all_enemies", "support", "defense", "item", "coating",
    ])
    def test_first_control_is_dropped_at_every_site(self, site):
        st, payload, skills = _monk_site(site)
        slots = copy.deepcopy(st["participants"][str(ATT)]["fast_slots"])
        r = _run(st, payload, skills=skills)
        imm = [p for p in r.procs if p["kind"] == "control_immune"]
        assert len(imm) == 1, r.events
        assert imm[0]["who"] == DEF and imm[0]["key"] == MONK
        assert imm[0]["effects"] in (["Stun"], ["Knockdown"])
        assert _control_on(r.state, DEF) == []
        assert r.ps(DEF)["control_immunity_used"] is True
        # the second control lands (same site, next turn)
        st2 = _next_turn(r.state)
        if site == "item":   # the first use spent the slot — hand a fresh one
            st2["participants"][str(ATT)]["fast_slots"] = slots
        r2 = _run(st2, payload, skills=skills)
        assert not [p for p in r2.procs if p["kind"] == "control_immune"]
        assert len(_control_on(r2.state, DEF)) == 1

    def test_rest_of_the_batch_lands(self):
        st, payload, skills = _monk_site("attack")
        r = _run(st, payload, skills=skills)
        ev, = r.of("apply_effects")
        assert [e["name"] for e in ev["effects"]] == ["Burn"]

    def test_monk_attacker_gets_control_bonus_pp(self):
        # roll passes only at >= 100: chance 90 + Monk +10 (soft) lands,
        # Stun 95 + 5 (hard) lands, a non-Monk lands neither.
        rows = [_eff("Knockdown", attr="random", duration=1, chance=90),
                _eff("Stun", duration=1, chance=95)]
        sure = (lambda chance: chance >= 100)
        r = _run(_duel(MONK), _pl(attack=1), skills={1: _skill(effects=rows)}, effect_roll=sure)
        assert len(_control_on(r.state, DEF)) == 2
        r = _run(_duel(), _pl(attack=1), skills={1: _skill(effects=rows)}, effect_roll=sure)
        assert _control_on(r.state, DEF) == []


# ══════════════════════════════════════════════════════════════════════════════
# Durations +1 — Trickster / Salamander
# ══════════════════════════════════════════════════════════════════════════════

SALAMANDER = "salamander_kindling"


def _durations(state, pid):
    return {e["name"]: e["duration"] for e in state["active_effects"].get(str(pid), [])}


class TestDurations:

    ROWS = [_eff("Burn", duration=2), _eff("Bleeding", duration=2), _eff("Stun", duration=1),
            _eff("Poison", attr="paralysis", duration=1)]

    def test_trickster_debuffs_plus_one_except_hard_control(self):
        r = _run(_duel(TRICKSTER), _pl(attack=1), skills={1: _skill(effects=self.ROWS)})
        assert _durations(r.state, DEF) == {"Burn": 3, "Bleeding": 3, "Stun": 1, "Poison": 1}
        ev, = r.of("apply_effects")
        assert [e["duration"] for e in ev["effects"]] == [3, 3, 1, 1]
        assert ev["passives"] == [{"key": TRICKSTER, "kind": "duration_plus",
                                   "value": 1, "owner": ATT}]

    def test_salamander_only_burn(self):
        r = _run(_duel(SALAMANDER), _pl(attack=1), skills={1: _skill("fire", effects=self.ROWS)})
        assert _durations(r.state, DEF) == {"Burn": 3, "Bleeding": 2, "Stun": 1, "Poison": 1}

    def test_plain_attacker_unchanged(self):
        r = _run(_duel(), _pl(attack=1), skills={1: _skill(effects=self.ROWS)})
        assert _durations(r.state, DEF) == {"Burn": 2, "Bleeding": 2, "Stun": 1, "Poison": 1}
        assert "passives" not in r.of("apply_effects")[0]

    def test_trickster_item_row(self):
        slot = dict(SCROLL, damage_entries=[], effects=[
            {"effect_name": "Bleeding", "target_side": "enemy", "chance": 100,
             "duration": 2, "magnitude": 3}])
        r = _run(_duel(TRICKSTER, att={"fast_slots": [slot]}), _pl(item=50))
        assert _durations(r.state, DEF) == {"Bleeding": 3}
        ev, = r.of("apply_effects")
        assert ev["effects"][0]["duration"] == 3
        assert ev["passives"][0]["kind"] == "duration_plus"


# ══════════════════════════════════════════════════════════════════════════════
# Agent «Слабое место»
# ══════════════════════════════════════════════════════════════════════════════

AGENT = "agent_weak_spot"


class TestAgent:

    def test_failed_effect_rerolled_on_crit(self):
        roll = MagicMock(return_value=True)
        with patch.object(P, "roll_pct", roll):
            r = _run(_duel(AGENT), _pl(attack=1),
                     skills={1: _skill(effects=[_eff("Burn", chance=50)])},
                     crit=True, effect_roll=False)
        assert not r.of("apply_effects")
        proc, = r.procs
        assert proc["kind"] == "weak_spot" and proc["who"] == ATT and proc["target"] == DEF
        assert [e["name"] for e in proc["effects"]] == ["Burn"]
        assert _durations(r.state, DEF) == {"Burn": 2}
        # conditional re-roll q = 20 / (100 − 50) × 100 = 40
        roll.assert_called_once_with(pytest.approx(40.0))
        # the re-roll happens after the damage
        kinds = [e["event"] for e in r.events]
        assert kinds.index("damage") < kinds.index("passive_proc")

    def test_hard_control_gets_ten(self):
        roll = MagicMock(return_value=True)
        with patch.object(P, "roll_pct", roll):
            _run(_duel(AGENT), _pl(attack=1),
                 skills={1: _skill(effects=[_eff("Stun", chance=50, duration=1)])},
                 crit=True, effect_roll=False)
        roll.assert_called_once_with(pytest.approx(20.0))

    def test_no_crit_no_reroll(self):
        roll = MagicMock(return_value=True)
        with patch.object(P, "roll_pct", roll):
            r = _run(_duel(AGENT), _pl(attack=1),
                     skills={1: _skill(effects=[_eff("Burn", chance=50)])},
                     crit=False, effect_roll=False)
        assert not roll.called and not r.procs and _durations(r.state, DEF) == {}

    def test_primary_effects_still_land_on_a_dodge(self):
        r = _run(_duel(AGENT), _pl(attack=1), skills={1: _skill(effects=[_eff("Burn")])},
                 dodge=True, crit=True)
        assert r.of("apply_effects") and _durations(r.state, DEF) == {"Burn": 2}
        assert not r.procs

    def test_non_agent_crit_no_reroll(self):
        roll = MagicMock(return_value=True)
        with patch.object(P, "roll_pct", roll):
            r = _run(_duel(), _pl(attack=1),
                     skills={1: _skill(effects=[_eff("Burn", chance=50)])},
                     crit=True, effect_roll=False)
        assert not roll.called and not r.procs

    @pytest.mark.parametrize("key, crit, chance, lands", [
        (AGENT, True, 80, True),      # 80 + 20 = 100
        (AGENT, True, 79, False),
        (AGENT, False, 80, False),    # no crit → no bonus
        (None, True, 80, False),
    ])
    def test_coating_bonus_on_critted_target(self, key, crit, chance, lands):
        coating = {"turns_left": 3, "item_id": 60, "name": "Яд", "bonus_damage": 0,
                   "effects": [_eff("Bleeding", chance=chance)]}
        r = _run(_duel(key, att={"weapon_coating": coating}), _pl(attack=1),
                 skills={1: _skill(slot="main_weapon")}, crit=crit,
                 effect_roll=lambda c: c >= 100)
        assert ("Bleeding" in _durations(r.state, DEF)) is lands


# ══════════════════════════════════════════════════════════════════════════════
# Caster «Чистая энергия»
# ══════════════════════════════════════════════════════════════════════════════

CASTER = "caster_pure_energy"


class TestCaster:

    def test_affords_10_mana_skill_with_9(self):
        r = _run(_duel(CASTER, att={"mana": 9}), _pl(attack=1),
                 skills={1: _skill("magic", cost_mana=10)})
        spend, = r.of("resource_spend")
        assert spend == {"event": "resource_spend", "who": ATT, "energy": 0, "mana": 9,
                         "stamina": 0, "mana_discount": 1,
                         "passives": [{"key": CASTER, "kind": "mana_discount",
                                       "value": 1, "owner": ATT}]}
        assert r.state["participants"][str(ATT)]["mana"] == 0

    def test_caster_insufficient_even_with_discount(self):
        r = _run(_duel(CASTER, att={"mana": 8}), _pl(attack=1),
                 skills={1: _skill("magic", cost_mana=10)}, expect=400)
        assert r.resp.json()["detail"] == "Недостаточно маны: нужно 9, есть 8"

    def test_non_caster_pays_full_and_keeps_three_keys(self):
        _run(_duel(att={"mana": 9}), _pl(attack=1),
             skills={1: _skill("magic", cost_mana=10)}, expect=400)
        r = _run(_duel(att={"mana": 10}), _pl(attack=1),
                 skills={1: _skill("magic", cost_mana=10)})
        spend, = r.of("resource_spend")
        assert spend == {"event": "resource_spend", "who": ATT,
                         "energy": 0, "mana": 10, "stamina": 0}

    def test_caster_without_mana_cost_has_no_discount_key(self):
        r = _run(_duel(CASTER), _pl(attack=1), skills={1: _skill("magic")})
        spend, = r.of("resource_spend")
        assert set(spend) == {"event", "who", "energy", "mana", "stamina"}

    def test_ignores_quarter_of_positive_magic_resist(self):
        r = _run(_duel(CASTER), _pl(attack=1), skills={1: _skill("magic")},
                 attrs={CHAR[DEF]: {"res_magic": 40}})
        call, = r.spy.calls
        assert call["resist_ignore"] == {"magic": 0.25}
        ev, = r.dmg
        assert ev["resist_ignored_pct"] == 10 and ev["resist_pct"] == 30
        assert ev["final"] == pytest.approx(RAW * 0.7)
        assert _contrib(ev, CASTER, "resist_ignore")[0]["value"] == 25

    def test_vulnerable_magic_resist_logs_no_pure_energy(self):
        # Review #1 Issue 1: nothing is ignored on a vulnerability → no
        # «Чистая энергия: пробивает 25% сопр.» in the log.
        r = _run(_duel(CASTER), _pl(attack=1), skills={1: _skill("magic")},
                 attrs={CHAR[DEF]: {"res_magic": -6.8}})
        call, = r.spy.calls
        assert call["resist_ignore"] == {"magic": 0.25}
        ev, = r.dmg
        assert ev["resist_pct"] < 0 and "resist_ignored_pct" not in ev
        assert not _contrib(ev, CASTER)

    def test_zero_magic_resist_logs_no_pure_energy(self):
        r = _run(_duel(CASTER), _pl(attack=1), skills={1: _skill("magic")})
        ev, = r.dmg
        assert ev["resist_pct"] == 0 and "resist_ignored_pct" not in ev
        assert not _contrib(ev, CASTER)
        assert "passives" not in ev

    def test_positive_magic_resist_logs_pure_energy_once(self):
        r = _run(_duel(CASTER), _pl(attack=1), skills={1: _skill("magic")},
                 attrs={CHAR[DEF]: {"res_magic": 8}})
        ev, = r.dmg
        assert ev["resist_ignored_pct"] == 2
        assert _contrib(ev, CASTER) == [
            {"key": CASTER, "kind": "resist_ignore", "value": 25, "owner": ATT}]

    def test_fire_is_not_pure_energy(self):
        r = _run(_duel(CASTER), _pl(attack=1), skills={1: _skill("fire")},
                 attrs={CHAR[DEF]: {"res_fire": 40}})
        ev, = r.dmg
        assert ev["resist_pct"] == 40 and "resist_ignored_pct" not in ev
        assert not _contrib(ev, CASTER)


# ══════════════════════════════════════════════════════════════════════════════
# Gladiator «Арена»
# ══════════════════════════════════════════════════════════════════════════════

GLADIATOR = "gladiator_arena"
STUN_ON_ACTOR = {"name": "Stun", "attribute": "stun", "magnitude": 0,
                 "duration": 1, "owner_id": DEF}


class TestGladiator:

    def test_ramp_counts_own_turns(self):
        st = _duel(GLADIATOR, att={"passive_state": {"own_turns": 2}})
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert r.ps(ATT)["own_turns"] == 3
        assert r.spy.calls[0]["percent_buffs"]["all"] == 9
        assert r.dmg[0]["passives"] == [{"key": GLADIATOR, "kind": "damage_pct",
                                         "value": 9, "owner": ATT}]

    def test_stunned_turn_not_counted(self):
        st = _duel(GLADIATOR, att={"passive_state": {"own_turns": 2}})
        st["active_effects"] = {str(ATT): [dict(STUN_ON_ACTOR)]}
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert r.of("control_skip") and not r.dmg
        assert r.ps(ATT)["own_turns"] == 2

    def test_outnumbered_attack_and_defence(self):
        r = _run(_trio(GLADIATOR), _pl(attack=1), skills={1: _skill()})
        assert r.spy.calls[0]["percent_buffs"]["all"] == 8
        # Gladiator defending while outnumbered (2 attackers vs 1): +4 all resists
        st = _battle({ATT: _p(ATT, 0), FOURTH: _p(FOURTH, 0), DEF: _p(DEF, 1, GLADIATOR)})
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert r.spy.calls[0]["percent_resists"]["all"] == 4
        assert _contrib(r.dmg[0], GLADIATOR, "resist_pct") == [
            {"key": GLADIATOR, "kind": "resist_pct", "value": 4, "owner": DEF}]


# ══════════════════════════════════════════════════════════════════════════════
# Inquisitor «Печать ереси»
# ══════════════════════════════════════════════════════════════════════════════

INQ = "inquisitor_heresy_seal"


class TestInquisitor:

    def test_stack_on_a_target_that_used_magic(self):
        r = _run(_duel(INQ, de={"passive_state": {"used_magic": True}}), _pl(attack=1),
                 skills={1: _skill()})
        proc, = r.procs
        assert proc == {"event": "passive_proc", "who": ATT, "key": INQ,
                        "kind": "heresy_stack", "target": DEF, "stacks": 1, "value": -3}
        assert r.ps(DEF)["heresy_stacks"] == 1

    def test_no_stack_on_a_target_without_magic(self):
        r = _run(_duel(INQ), _pl(attack=1), skills={1: _skill()})
        assert not r.procs and r.ps(DEF) == {}

    def test_ally_non_physical_damage_benefits(self):
        st = _battle({ATT: _p(ATT, 0), THIRD: _p(THIRD, 0, INQ),
                      DEF: _p(DEF, 1, passive_state={"used_magic": True, "heresy_stacks": 2})})
        r = _run(st, _pl(attack=1), skills={1: _skill("fire")},
                 attrs={CHAR[DEF]: {"res_fire": 10}})
        call, = r.spy.calls
        assert call["percent_resists"]["fire"] == 4      # 10 − 3×2
        ev, = r.dmg
        assert ev["resist_pct"] == 4
        assert _contrib(ev, INQ, "resist_pct") == [
            {"key": INQ, "kind": "resist_pct", "value": -6}]
        # the ally is no Inquisitor → no new stack
        assert r.ps(DEF)["heresy_stacks"] == 2

    def test_physical_damage_of_an_ally_is_untouched(self):
        st = _battle({ATT: _p(ATT, 0), THIRD: _p(THIRD, 0, INQ),
                      DEF: _p(DEF, 1, passive_state={"heresy_stacks": 2})})
        r = _run(st, _pl(attack=1), skills={1: _skill()},
                 attrs={CHAR[DEF]: {"res_physical": 10}})
        assert r.dmg[0]["resist_pct"] == 10

    def test_physical_hit_does_not_log_the_heresy_resist_cut(self):
        # QA T7 repro: nothing was cut on a physical blow → no «сопр. −6%».
        st = _battle({ATT: _p(ATT, 0), THIRD: _p(THIRD, 0, INQ),
                      DEF: _p(DEF, 1, passive_state={"heresy_stacks": 2})})
        r = _run(st, _pl(attack=1), skills={1: _skill()},
                 attrs={CHAR[DEF]: {"res_physical": 10}})
        assert r.dmg[0]["resist_pct"] == 10
        assert not _contrib(r.dmg[0], INQ)

    def test_non_physical_hit_still_logs_the_heresy_resist_cut(self):
        st = _battle({ATT: _p(ATT, 0), THIRD: _p(THIRD, 0, INQ),
                      DEF: _p(DEF, 1, passive_state={"heresy_stacks": 2})})
        r = _run(st, _pl(attack=1), skills={1: _skill("magic")},
                 attrs={CHAR[DEF]: {"res_magic": 10}})
        ev, = r.dmg
        assert ev["resist_pct"] == 4
        assert _contrib(ev, INQ) == [{"key": INQ, "kind": "resist_pct", "value": -6}]

    def test_a_scroll_marks_used_magic(self):
        r = _run(_duel(att={"fast_slots": [dict(SCROLL)]}), _pl(item=50))
        assert r.ps(ATT) == {"used_magic": True}


# ══════════════════════════════════════════════════════════════════════════════
# Lancer «Пригвоздить»
# ══════════════════════════════════════════════════════════════════════════════

LANCER = "lancer_pin"


class TestLancer:

    def test_steal_shows_in_the_next_attack(self):
        attrs = {CHAR[DEF]: {"dodge": 5, "critical_hit_chance": 1},
                 CHAR[ATT]: {"dodge": 0, "critical_hit_chance": 3}}
        r1 = _run(_duel(LANCER), _pl(attack=1), skills={1: _skill()}, attrs=attrs)
        proc, = r1.procs
        assert proc == {"event": "passive_proc", "who": ATT, "key": LANCER, "kind": "pin",
                        "target": DEF, "stacks": 1,
                        "stolen": {"dodge": 2, "critical_hit_chance": 1}}
        # this attack itself was not changed retroactively
        assert r1.spy.calls[0]["attacker_attr"]["critical_hit_chance"] == 3
        r1.dodge.assert_called_once_with(5)

        r2 = _run(_next_turn(r1.state), _pl(attack=1), skills={1: _skill()}, attrs=attrs)
        call, = r2.spy.calls
        assert call["attacker_attr"]["critical_hit_chance"] == 4
        assert call["attacker_attr"]["dodge"] == 2
        assert call["defender_attr"]["dodge"] == 3
        assert call["defender_attr"]["critical_hit_chance"] == 0
        r2.dodge.assert_called_once_with(3)
        assert r2.ps(ATT)["lancer_stacks"] == 2

    def test_nothing_to_steal_nothing_logged(self):
        r = _run(_duel(LANCER), _pl(attack=1), skills={1: _skill()})   # TURN_ATTRS: 0 / 0
        assert not r.procs and "lancer_stacks" not in r.ps(ATT)


# ══════════════════════════════════════════════════════════════════════════════
# Archer «Первая кровь», Salamander «Разгорание»
# ══════════════════════════════════════════════════════════════════════════════

ARCHER = "archer_first_blood"


class TestArcher:

    def test_first_hit_per_target_only(self):
        r1 = _run(_duel(ARCHER), _pl(attack=1), skills={1: _skill()})
        c1, = r1.spy.calls
        assert c1["force_crit"] is True and c1["crit_damage_bonus"] == 50
        ev, = r1.dmg
        assert ev["forced_crit"] is True and ev["crit_mul"] == pytest.approx(1.5)
        assert ev["passives"] == [{"key": ARCHER, "kind": "forced_crit",
                                   "value": 50, "owner": ATT}]
        r2 = _run(_next_turn(r1.state), _pl(attack=1), skills={1: _skill()})
        assert "force_crit" not in r2.spy.calls[0]
        assert "passives" not in r2.dmg[0]

    def test_dodge_does_not_consume_first_blood(self):
        r1 = _run(_duel(ARCHER), _pl(attack=1), skills={1: _skill()}, dodge=True)
        assert r1.ps(ATT).get("first_blood_done") in (None, [])
        r2 = _run(_next_turn(r1.state), _pl(attack=1), skills={1: _skill()})
        assert r2.spy.calls[0]["force_crit"] is True

    def test_scroll_first_blood(self):
        r = _run(_duel(ARCHER, att={"fast_slots": [dict(SCROLL)]}), _pl(item=50))
        assert r.dmg[0]["forced_crit"] is True


class TestSalamander:

    def test_consecutive_fire_hits_stack_then_reset(self):
        r1 = _run(_duel(SALAMANDER), _pl(attack=1), skills={1: _skill("fire")})
        assert r1.ps(ATT) == {"used_magic": True, "kindling_target": DEF, "kindling_stacks": 1}
        assert r1.spy.calls[0]["percent_buffs"].get("fire", 0) == 0
        r2 = _run(_next_turn(r1.state), _pl(attack=1), skills={1: _skill("fire")})
        assert r2.spy.calls[0]["percent_buffs"]["fire"] == 6
        assert r2.ps(ATT)["kindling_stacks"] == 2
        r3 = _run(_next_turn(r2.state), _pl(attack=1), skills={1: _skill()})
        assert r3.spy.calls[0]["percent_buffs"].get("fire", 0) == 0
        assert r3.ps(ATT)["kindling_stacks"] == 0

    def test_attack_skill_without_damage_rows_keeps_stacks(self):
        # Review #1 note: a debuff-only attack skill is not an attack for H2.
        st = _duel(SALAMANDER, att={"passive_state": {
            "kindling_target": DEF, "kindling_stacks": 2}})
        r = _run(st, _pl(attack=1),
                 skills={1: _skill(entries=[], effects=[_eff("Weakness", attr="strength")])})
        assert not r.spy.calls and not r.dmg
        assert r.ps(ATT) == {"kindling_target": DEF, "kindling_stacks": 2}
        # the next real fire hit still gets the 2 stacks
        r2 = _run(_next_turn(r.state), _pl(attack=1), skills={1: _skill("fire")})
        assert r2.spy.calls[0]["percent_buffs"]["fire"] == 12   # 6 × 2 stacks
        assert r2.ps(ATT)["kindling_stacks"] == 3


# ══════════════════════════════════════════════════════════════════════════════
# Redis plumbing
# ══════════════════════════════════════════════════════════════════════════════

class TestRedisPlumbing:

    async def _init(self, payload, **kw):
        fake = AsyncMock()
        with patch.object(real_redis_state, "get_redis_client", AsyncMock(return_value=fake)):
            await real_redis_state.init_battle_state(
                battle_id=9, participants_payload=payload,
                first_actor_participant_id=payload[0]["participant_id"],
                deadline_at=real_redis_state.utc_now(), location_id=1, **kw)
        call = next(c for c in fake.set.call_args_list if "state" in str(c.args[0]))
        return json.loads(call.args[1])

    @staticmethod
    def _payload(pid, **extra):
        p = {"participant_id": pid, "character_id": pid * 10, "team": pid % 2,
             "hp": 100, "mana": 50, "energy": 50, "stamina": 50, "max_hp": 100,
             "max_mana": 100, "max_energy": 100, "max_stamina": 100, "fast_slots": []}
        p.update(extra)
        return p

    @pytest.mark.asyncio
    async def test_new_keys_are_stored(self):
        seed = {"saber_kills": 2}
        st = await self._init([self._payload(1, is_npc=False, passive_state=seed),
                               self._payload(2, is_npc=True)], dungeon_session_id=77)
        assert st["dungeon_session_id"] == 77
        assert st["participants"]["1"]["passive_state"] == {"saber_kills": 2}
        assert st["participants"]["1"]["is_npc"] is False
        assert st["participants"]["2"] == {**st["participants"]["2"],
                                           "is_npc": True, "passive_state": {}}

    @pytest.mark.asyncio
    async def test_old_payloads_default(self):
        st = await self._init([self._payload(1)])
        assert st["dungeon_session_id"] is None
        assert st["participants"]["1"]["is_npc"] is False
        assert st["participants"]["1"]["passive_state"] == {}

    @pytest.mark.asyncio
    async def test_seed_is_copied_not_shared(self):
        seed = {"saber_kills": 2}
        payload = [self._payload(1, passive_state=seed)]
        await self._init(payload)
        assert payload[0]["passive_state"] is seed and seed == {"saber_kills": 2}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("raw, expected", [("3", 3), (None, 0), ("-2", 0), ("abc", 0)])
    async def test_get_saber_run_stacks(self, raw, expected):
        fake = AsyncMock()
        fake.get = AsyncMock(return_value=raw)
        with patch.object(real_redis_state, "get_redis_client", AsyncMock(return_value=fake)):
            assert await real_redis_state.get_saber_run_stacks(77, 10) == expected
        fake.get.assert_awaited_once_with("battle:passive:saber_run:77:10")

    @pytest.mark.asyncio
    async def test_get_soft_fails_on_redis_error(self):
        with patch.object(real_redis_state, "get_redis_client",
                          AsyncMock(side_effect=ConnectionError("down"))):
            assert await real_redis_state.get_saber_run_stacks(77, 10) == 0

    @pytest.mark.asyncio
    async def test_set_saber_run_stacks_with_ttl(self):
        fake = AsyncMock()
        with patch.object(real_redis_state, "get_redis_client", AsyncMock(return_value=fake)):
            await real_redis_state.set_saber_run_stacks(77, 10, 3)
        fake.set.assert_awaited_once_with("battle:passive:saber_run:77:10", 3,
                                          ex=14 * 24 * 3600)
        assert real_redis_state.SABER_RUN_STACKS_TTL_S == P.SABER_RUN_STACKS_TTL_S

    @pytest.mark.asyncio
    async def test_set_soft_fails_on_redis_error(self):
        fake = AsyncMock()
        fake.set = AsyncMock(side_effect=ConnectionError("down"))
        with patch.object(real_redis_state, "get_redis_client", AsyncMock(return_value=fake)):
            await real_redis_state.set_saber_run_stacks(77, 10, 3)   # no raise
