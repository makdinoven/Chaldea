"""FEAT-190 (Task #6) — subclass passives wave 2, end to end.

Every action test drives the REAL ``POST /battles/{id}/action`` endpoint
(``_make_action_core``) with the REAL buffs engine, the REAL damage formula and
the REAL ``passives`` module ``main`` imported — through the FEAT-189 harness
(``test_passives_wave1_integration._run``, itself on the FEAT-188 harness of
``test_subclass_passives.py``). Only the log-shape check is swapped for the
wave-2 contract (§3.5) and the character-ownership check is stubbed so any
participant can act.

Randomness is pinned, never sampled: ``passives.roll_pct`` / ``passives.pick``
on ``main.passives``; ``main.roll_dodge`` / ``main.roll_chance``; the engine's
``roll_crit`` / ``roll_chance``.

Covered (feature file §4 Task 6):
  * shields absorb skill hits, scrolls, item effect rows, extra hits, DoT
    ticks and negative HP doses (``_absorb_fn`` wired in step 9.4a);
    ``absorbed`` / ``shield_left`` on strikes, ``shield_absorb`` procs for
    effect / DoT damage; ``total_damage_*`` keep counting the engine damage;
  * the ``shield`` field in every runtime payload: ``get_state_internal``,
    ``GET /state``, spectate, preview, admin, ``_build_runtime`` (+ the WS
    publish of a real action);
  * Paladin vow: direct hit (+ cleanse of the newest enemy-owned non-hard
    effect), mid-attack protection of the next entry, DoT tick, effect damage,
    40% → 0 never, once per battle;
  * Auromancer tide: skill heal, ally heal (cap), HoT tick, potion; expiry
    after 3 of HIS turns (not other turns); vanishes on his death;
  * Guardian reflect: shape/stats, attacker shield absorbs it, own shield part
    counts, Guardian vs Guardian = one reflect, kills the attacker mid-AoE →
    AoE stops and the extra hit is skipped, extra hits reflect, DoT doesn't,
    a Guardian killed by the hit still reflects (overkill excluded);
  * lifesteal before reflect (a 5-HP Berserk hitting a Guardian survives),
    Priest 10% / holy 15%, only from HP removed (not the shield part),
    scrolls lifesteal, DoT doesn't, Berserk exactly at 25% doesn't;
  * Necromancer: HP payment (``hp_paid``, contribution, mana 0), the
    ≥1-HP boundary, Russian 400 with the state unsaved, dead (reflect) → no
    charge, kill heal;
  * Bard: stacks across turns, group/solo, the rows really raise damage,
    removal on death at 9.5 AND on a ``handle_expired_turn`` drop-out;
  * Etheriad: curse on the enemy he hit (and it lowers resists), ward first,
    might when the enemy is already cursed / nothing landed, silent when
    stunned;
  * Trickster redirect: the attacker's ally takes ×0.5, no dodge roll, no
    passives of either side, no ``passive_key``, ally shield absorbs, no ally
    → plain deceit, extra hits never redirect, scrolls redirect, an ally
    killed by it is no kill;
  * deferred procs follow their own ``apply_effects`` event;
  * regression guard: a passive-less battle (AoE + scroll + effect rows +
    DoT + HoT) produces byte-identical events and state to the pre-FEAT-190
    call shapes;
  * the reported leftover: an attacker killed by a reflect in the scroll
    step still lands its attack skill's effect rows (documented, see
    ``TestDeadAttackerLeftover``).
"""

import copy
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests import test_passives_wave1_integration as W1
from tests.test_passives_wave1_integration import (  # noqa: F401 — harness setup
    ATT, CHAR, DEF, FOURTH, P, RAW, THIRD,
    _battle, _contrib, _duel, _eff, _p, _pl, _skill, _trio,
)
from tests.test_subclass_passives import (
    REAL_BUFFS, SCROLL, _damage_row, _mock_response, app, get_db, main,
    real_redis_state,
)

PALADIN = P.PASSIVE_PALADIN
GUARD = P.PASSIVE_GUARDIAN
BARD = P.PASSIVE_BARD
NECRO = P.PASSIVE_NECROMANCER
ETH = P.PASSIVE_ETHERIAD
AUROM = P.PASSIVE_AUROMANCER
PRIEST = P.PASSIVE_PRIEST
BERSERK = P.PASSIVE_BERSERKER_RAGE
TRICK = P.PASSIVE_TRICKSTER
MECHANIC = P.PASSIVE_MECHANIC

WAVE2_CONTRIB_KINDS = {"lifesteal", "reflect", "redirect", "blood_price"}
PROC_FIELDS = W1.PROC_FIELDS | {"shield", "mode", "targets"}
CONTRIB_KINDS = W1.CONTRIB_KINDS | WAVE2_CONTRIB_KINDS
WAVE2_EVENT_KEYS = ("absorbed", "shield_left", "reflected", "redirected",
                    "deceived_by", "hp_paid")


# ══════════════════════════════════════════════════════════════════════════════
# Harness
# ══════════════════════════════════════════════════════════════════════════════

def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _assert_shapes(ev):
    """The wave-2 log contract (§3.5) on top of FEAT-189's."""
    if ev["event"] == "passive_proc":
        assert set(ev) <= PROC_FIELDS, ev
        assert {"who", "key", "kind"} <= set(ev), ev
        if ev["kind"] == "shield_absorb":
            assert ev["key"] == P.SHIELD_PROC_KEY, ev
        else:
            assert ev["key"] in P.IMPLEMENTED_PASSIVES, ev
        for f in ("value", "stacks", "shield"):
            if f in ev:
                assert _is_int(ev[f]), (f, ev)
        if "targets" in ev:
            assert all(_is_int(t) for t in ev["targets"]), ev
    for c in ev.get("passives") or []:
        assert set(c) <= W1.CONTRIB_FIELDS, ev
        assert c["kind"] in CONTRIB_KINDS, ev
        assert c["key"] in P.IMPLEMENTED_PASSIVES, ev
        if c["kind"] in WAVE2_CONTRIB_KINDS:
            assert _is_int(c["value"]), ev
    for f in ("absorbed", "shield_left", "hp_paid"):
        if f in ev:
            assert _is_int(ev[f]), (f, ev)
    if ev.get("reflected"):
        assert ev["event"] == "damage" and isinstance(ev["final"], float), ev
        assert "critical" not in ev and "dodged" not in ev, ev
        assert [c["kind"] for c in ev["passives"]] == ["reflect"], ev
    if ev.get("redirected"):
        assert _is_int(ev["deceived_by"]), ev
        assert [c["kind"] for c in ev["passives"]] == ["redirect"], ev
        assert "passive_key" not in ev and "passive_pct" not in ev, ev
    if "extra_hit" in ev:
        assert ev["extra_hit"] in ("splash", "chain", "echo")
        assert isinstance(ev["extra_mult"], float)


def _run(state, payload, *, extra=None, **kw):
    """W1._run (the real /action) with the wave-2 shape check, ownership
    stubbed (any participant may act) and the `save_state` mock exposed."""
    save = AsyncMock()
    ex = {"main.verify_character_ownership": AsyncMock(), "main.save_state": save}
    ex.update(extra or {})
    with patch.object(W1, "_assert_shapes", _assert_shapes):
        r = W1._run(state, payload, extra=ex, **kw)
    r.save = save
    return r


def _turn(state, actor):
    st = copy.deepcopy(state)
    st["next_actor"] = actor
    return st


def _sh(amount, owner, key=PALADIN, turns=None, fresh=False, cap=None):
    return {"key": key, "owner": owner, "amount": float(amount),
            "cap": float(cap if cap is not None else amount),
            "turns_left": turns, "fresh": fresh}


def _shields(pid, *entries):
    return {"passive_state": {"shields": list(entries)}}


def _row(name, attr, mag, owner, duration=2, **kw):
    """An active_effects row as it sits in Redis (already normalized)."""
    return {"name": name, "attribute": attr, "magnitude": mag,
            "duration": duration, "owner_id": owner, **kw}


def _heal(side, mag, duration=1, name="Лечение"):
    return _eff(name, side=side, duration=duration, attr="hp", mag=mag)


def _kinds(r):
    return [(e["event"], e.get("kind")) for e in r.events]


def _idx(r, pred):
    for i, e in enumerate(r.events):
        if pred(e):
            return i
    raise AssertionError("event not found")


def _procs(r, kind):
    return [e for e in r.procs if e["kind"] == kind]


def _reflects(r):
    return [e for e in r.dmg if e.get("reflected")]


def _shield(r, pid):
    return P.shield_total(r.state["participants"][str(pid)])


def _effects_named(state, pid, name):
    return [e for e in state.get("active_effects", {}).get(str(pid), [])
            if e.get("name") == name]


def _defeated(r):
    return [e["who"] for e in r.of("participant_defeated")]


def _pick_first():
    return patch.object(P, "pick", MagicMock(side_effect=lambda seq: list(seq)[0]))


def _scroll(**over):
    return dict(SCROLL, **over)


# ══════════════════════════════════════════════════════════════════════════════
# Shields — every HP-loss site
# ══════════════════════════════════════════════════════════════════════════════

class TestShieldsAbsorb:

    def test_skill_hit_partially_absorbed(self):
        st = _duel(de=_shields(DEF, _sh(30, DEF)))
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        ev, = r.dmg
        assert ev["final"] == RAW
        assert ev["absorbed"] == 30 and ev["shield_left"] == 0
        assert "passives" not in ev
        assert r.hp(DEF) == pytest.approx(1000 - (RAW - 30))
        assert r.ps(DEF)["shields"] == []
        # E21: stats keep counting the engine damage (incl. the shield part)
        assert r.state["participants"][str(ATT)]["total_damage_dealt"] == 45
        assert r.state["participants"][str(DEF)]["total_damage_received"] == 45

    def test_skill_hit_fully_absorbed(self):
        st = _duel(de=_shields(DEF, _sh(100, DEF)))
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        ev, = r.dmg
        assert ev["absorbed"] == 45 and ev["shield_left"] == 55
        assert r.hp(DEF) == 1000
        assert _shield(r, DEF) == 55

    def test_timed_shield_is_eaten_before_the_permanent_one(self):
        st = _duel(de=_shields(DEF, _sh(100, DEF), _sh(30, THIRD, key=AUROM, turns=2)))
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert r.dmg[0]["absorbed"] == 45
        assert [(s["key"], s["amount"]) for s in r.ps(DEF)["shields"]] == [(PALADIN, 85.0)]

    def test_scroll_hit_absorbed(self):
        st = _duel(att={"fast_slots": [_scroll()]}, de=_shields(DEF, _sh(500, DEF)))
        r = _run(st, _pl(item=50))
        ev, = r.dmg
        assert ev["source_kind"] == "item"
        assert ev["absorbed"] == int(round(ev["final"])) > 0
        assert ev["shield_left"] == int(round(500 - ev["final"]))
        assert r.hp(DEF) == 1000

    def test_item_effect_row_damage_absorbed_with_a_proc_after_its_event(self):
        acid = {"effect_name": "Кислота", "attribute_key": "hp", "magnitude": 20,
                "duration": 1, "target_side": "enemy", "chance": 100}
        st = _duel(att={"fast_slots": [_scroll(damage_entries=[], effects=[acid])]},
                   de=_shields(DEF, _sh(30, DEF)))
        r = _run(st, _pl(item=50))
        assert r.hp(DEF) == 1000
        proc, = _procs(r, "shield_absorb")
        assert proc == {"event": "passive_proc", "who": DEF, "key": "shield",
                        "kind": "shield_absorb", "value": 20, "shield": 10}
        i_eff = _idx(r, lambda e: e["event"] == "apply_effects" and e["who"] == DEF)
        i_proc = _idx(r, lambda e: e.get("kind") == "shield_absorb")
        i_spend = _idx(r, lambda e: e["event"] == "resource_spend")
        assert i_eff < i_proc < i_spend

    def test_attack_effect_row_damage_absorbed(self):
        sk = _skill(entries=[], effects=[_eff("Кислота", attr="hp", mag=20, duration=1)])
        r = _run(_duel(de=_shields(DEF, _sh(5, DEF))), _pl(attack=1), skills={1: sk})
        assert r.hp(DEF) == 985
        assert _procs(r, "shield_absorb")[0]["value"] == 5

    def test_extra_hit_absorbed(self):
        st = _trio(MECHANIC, third=_shields(THIRD, _sh(100, THIRD)))
        with W1._rolls(True), patch.object(P, "pick", lambda seq: seq[-1]):
            r = _run(st, _pl(attack=1), skills={1: _skill()})
        prim, splash = r.dmg
        assert "absorbed" not in prim
        assert splash["extra_hit"] == "splash" and splash["target"] == THIRD
        assert splash["absorbed"] == 18 and splash["shield_left"] == 82
        assert r.hp(THIRD) == 1000

    def test_dot_tick_absorbed_in_step_9_4a(self):
        st = _duel(de=_shields(DEF, _sh(30, DEF)))
        st["active_effects"] = {str(DEF): [_row("Bleeding", "bleeding", 50, ATT)]}
        r = _run(st, _pl())
        tick, = r.of("effect_tick")
        assert tick["amount"] == 20 and tick["target"] == DEF
        proc, = _procs(r, "shield_absorb")
        assert proc["who"] == DEF and proc["value"] == 30 and proc["shield"] == 0
        assert r.events.index(tick) < r.events.index(proc)
        assert r.hp(DEF) == 980
        # the DoT owner is credited with the HP actually lost (unchanged rule)
        assert r.state["participants"][str(ATT)]["total_damage_dealt"] == 20

    def test_negative_hp_dose_absorbed_and_the_stored_dose_kept(self):
        st = _duel(de=_shields(DEF, _sh(15, DEF)))
        st["active_effects"] = {str(DEF): [_row("Яд", "hp", -20, ATT, duration=3)]}
        r = _run(st, _pl())
        tick, = r.of("effect_tick")
        assert tick["amount"] == 5
        assert _procs(r, "shield_absorb")[0]["value"] == 15
        dose, = _effects_named(r.state, DEF, "Яд")
        assert dose["magnitude"] == -20          # never reduced by the shield
        assert r.hp(DEF) == 995

    def test_dead_holder_shield_does_nothing(self):
        # a tick on a corpse is skipped anyway; a shield on a 0-HP holder
        # never absorbs (and on_deaths cleared it at its death)
        st = _trio(third={"hp": 0, "defeated": True, **_shields(THIRD, _sh(50, THIRD))})
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert not _procs(r, "shield_absorb")


# ══════════════════════════════════════════════════════════════════════════════
# `shield` in every runtime payload (E20)
# ══════════════════════════════════════════════════════════════════════════════

def _payload_state():
    st = _battle({ATT: _p(ATT, 0), DEF: _p(DEF, 1, **_shields(
        DEF, _sh(12.4, DEF), _sh(7.3, ATT, key=AUROM, turns=2)))})
    st["participants"][str(ATT)].pop("passive_state")   # old state: no key at all
    st["location_id"] = 7
    return st


def _battle_record():
    return SimpleNamespace(
        id=1, status=main.BattleStatus.in_progress, battle_type="pve",
        is_paused=False, pause_reason=None, location_id=7, created_at=None,
    )


class _FakeDB:
    """Answers the handful of raw-SQL reads the state endpoints make."""

    async def execute(self, query, params=None):
        sql = str(query)
        res = MagicMock()
        if "FROM characters WHERE id" in sql:
            res.fetchone.return_value = (5,) if params["cid"] == CHAR[ATT] else (6,)
        elif "FROM characters WHERE user_id" in sql:
            res.fetchall.return_value = [(CHAR[ATT], 7)]
        elif "Locations" in sql:
            res.fetchone.return_value = ("Тестовая поляна",)
        else:
            res.fetchone.return_value = None
            res.fetchall.return_value = []
        return res

    async def commit(self):
        return None


def _get(url, state, user=None):
    user = user or {"id": 5, "username": "player", "role": "user", "permissions": []}
    db = _FakeDB()

    async def _fake_get_db():
        yield db

    patches = [
        patch("main.load_state", AsyncMock(return_value=state)),
        patch("main.get_redis_client", AsyncMock(return_value=AsyncMock())),
        patch("main.get_cached_snapshot", AsyncMock(return_value=[
            {"participant_id": ATT, "name": "А"}, {"participant_id": DEF, "name": "Б"}])),
        patch("main.get_battle", AsyncMock(return_value=_battle_record())),
        patch("auth_http.requests.get", MagicMock(return_value=_mock_response(200, user))),
    ]
    for p in patches:
        p.start()
    try:
        app.dependency_overrides[get_db] = _fake_get_db
        with TestClient(app) as client:
            resp = client.get(url, headers={"Authorization": "Bearer fake-token"})
    finally:
        app.dependency_overrides.pop(get_db, None)
        for p in reversed(patches):
            p.stop()
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestShieldInRuntimePayloads:

    @staticmethod
    def _check(parts):
        assert parts[str(DEF)]["shield"] == 20      # round(12.4 + 7.3)
        assert parts[str(ATT)]["shield"] == 0       # pre-FEAT-189 state

    def test_build_runtime_ws(self):
        self._check(main._build_runtime(_payload_state())["participants"])

    @pytest.mark.asyncio
    async def test_get_state_internal(self):
        st = _payload_state()
        with patch("main.load_state", AsyncMock(return_value=st)), \
                patch("main.get_redis_client", AsyncMock(return_value=AsyncMock())), \
                patch("main.get_cached_snapshot", AsyncMock(return_value=[])):
            out = await main.get_state_internal(1)
        self._check(out["runtime"]["participants"])

    def test_get_state(self):
        self._check(_get("/battles/1/state", _payload_state())["runtime"]["participants"])

    def test_spectate(self):
        self._check(_get("/battles/1/spectate", _payload_state())["runtime"]["participants"])

    def test_admin_state(self):
        admin = {"id": 1, "username": "admin", "role": "admin",
                 "permissions": ["battles:manage"]}
        out = _get("/battles/admin/1/state", _payload_state(), user=admin)
        self._check(out["runtime"]["participants"])

    @pytest.mark.asyncio
    async def test_preview_builder_puts_the_shield_in(self):
        # the dict main builds carries it (E20) …
        st = _payload_state()
        with patch("main.load_state", AsyncMock(return_value=st)), \
                patch("main.get_redis_client", AsyncMock(return_value=AsyncMock())), \
                patch("main.get_cached_snapshot", AsyncMock(return_value=[])), \
                patch("main.get_battle", AsyncMock(return_value=_battle_record())):
            out = await main.get_battle_preview(1, _FakeDB(), SimpleNamespace(id=5))
        by_pid = {p["participant_id"]: p for p in out["participants"]}
        assert by_pid[str(DEF)]["shield"] == 20 and by_pid[str(ATT)]["shield"] == 0

    def test_preview_response_reaches_the_client_with_the_shield(self):
        """… but `GET /preview` serializes through `BattlePreviewOut`, whose
        `BattlePreviewParticipant` has no `shield` field: pydantic v1 drops
        unknown keys, so the client never receives it. FAILS until
        `shield: int = 0` is added to `schemas.BattlePreviewParticipant`
        (E20: the field must be in all 6 builders' OUTPUT)."""
        out = _get("/battles/1/preview", _payload_state())
        by_pid = {p["participant_id"]: p for p in out["participants"]}
        assert by_pid[str(DEF)].get("shield") == 20, by_pid[str(DEF)]
        assert by_pid[str(ATT)].get("shield") == 0

    def test_ws_publish_of_a_real_action_carries_the_shield(self):
        redis = AsyncMock()
        st = _duel(de=_shields(DEF, _sh(100, DEF)))
        _run(st, _pl(attack=1), skills={1: _skill()},
             extra={"main.get_redis_client": AsyncMock(return_value=redis),
                    "main.get_cached_snapshot": AsyncMock(return_value=None),
                    "main.load_snapshot": AsyncMock(return_value=None),
                    "main.utc_now": real_redis_state.utc_now,
                    "main.deadline_epoch": real_redis_state.deadline_epoch})
        published = [json.loads(c.args[1]) for c in redis.publish.call_args_list
                     if c.args[0].endswith(":state_update")]
        assert published, redis.publish.call_args_list
        parts = published[-1]["data"]["runtime"]["participants"]
        assert parts[str(DEF)]["shield"] == 55 and parts[str(ATT)]["shield"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# Paladin «Священный обет»
# ══════════════════════════════════════════════════════════════════════════════

class TestPaladinVow:

    def _effects(self):
        return [
            _row("Weakness", "strength", -5, ATT, duration=3),       # enemy, removable
            _row("Stun", "stun", 0, ATT, duration=2),                 # enemy, hard control
            _row("Сила", "strength", 5, DEF, duration=3),             # own buff
        ]

    def test_direct_hit_vow_shield_and_cleanse_of_the_newest_enemy_effect(self):
        st = _duel(def_key=PALADIN, de={"hp": 300})
        st["active_effects"] = {str(DEF): self._effects()}
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        hit, = r.dmg
        vow, = _procs(r, "vow")
        assert vow == {"event": "passive_proc", "who": DEF, "key": PALADIN,
                       "kind": "vow", "value": 200, "shield": 200, "effects": ["Weakness"]}
        assert r.events.index(vow) == r.events.index(hit) + 1
        assert r.hp(DEF) == 255
        assert r.ps(DEF)["vow_used"] is True
        names = [e["name"] for e in r.state["active_effects"][str(DEF)]]
        assert "Weakness" not in names and "Stun" in names and "Сила" in names
        assert _shield(r, DEF) == 200

    def test_vow_mid_attack_protects_against_the_next_entry(self):
        sk = _skill(entries=[_damage_row(), _damage_row()])
        r = _run(_duel(def_key=PALADIN, de={"hp": 300}), _pl(attack=1), skills={1: sk})
        first, second = r.dmg
        assert "absorbed" not in first
        assert second["absorbed"] == 45 and second["shield_left"] == 155
        assert _kinds(r).index(("passive_proc", "vow")) == r.events.index(first) + 1
        assert r.hp(DEF) == 255

    def test_vow_from_a_dot_tick(self):
        st = _duel(def_key=PALADIN, de={"hp": 320})
        st["active_effects"] = {str(DEF): [_row("Bleeding", "bleeding", 50, ATT)]}
        r = _run(st, _pl())
        tick, = r.of("effect_tick")
        vow, = _procs(r, "vow")
        assert r.events.index(tick) < r.events.index(vow)
        # the enemy's Bleeding is the newest removable negative row → cleansed
        assert vow["effects"] == ["Bleeding"]
        assert not _effects_named(r.state, DEF, "Bleeding")
        assert r.hp(DEF) == 270 and _shield(r, DEF) == 200

    def test_vow_from_effect_damage_follows_its_apply_effects_event(self):
        sk = _skill(entries=[], effects=[_eff("Кислота", attr="hp", mag=50, duration=1)])
        r = _run(_duel(def_key=PALADIN, de={"hp": 320}), _pl(attack=1), skills={1: sk})
        i_eff = _idx(r, lambda e: e["event"] == "apply_effects" and e["who"] == DEF)
        i_vow = _idx(r, lambda e: e.get("kind") == "vow")
        i_spend = _idx(r, lambda e: e["event"] == "resource_spend")
        assert i_eff < i_vow < i_spend
        assert r.hp(DEF) == 270

    def test_40_percent_to_zero_never_triggers(self):
        st = _trio(de={"passive_key": PALADIN, "hp": 40, "max_hp": 100})
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert r.hp(DEF) < 0 and DEF in _defeated(r)
        assert not _procs(r, "vow")
        assert "vow_used" not in (r.ps(DEF) or {})

    def test_only_once_per_battle(self):
        st = _duel(def_key=PALADIN, de={"hp": 300, "passive_state": {"vow_used": True}})
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert not _procs(r, "vow") and _shield(r, DEF) == 0

    def test_old_state_without_passive_state(self):
        st = _duel(def_key=PALADIN, de={"hp": 300})
        st["participants"][str(DEF)].pop("passive_state")
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert _procs(r, "vow") and r.ps(DEF)["vow_used"] is True


# ══════════════════════════════════════════════════════════════════════════════
# Auromancer «Прилив»
# ══════════════════════════════════════════════════════════════════════════════

def _aurom_group(**att):
    return _battle({ATT: _p(ATT, 0, AUROM, **att), FOURTH: _p(FOURTH, 0), DEF: _p(DEF, 1)})


class TestAuromancerTide:

    def test_skill_self_heal_overflow_becomes_a_tide_after_its_event(self):
        sk = _skill(entries=[], effects=[_heal("self", 50)], sid=2)
        r = _run(_duel(AUROM, att={"hp": 980}), _pl(support=2), skills={2: sk})
        assert r.hp(ATT) == 1000
        tide, = _procs(r, "tide")
        assert tide == {"event": "passive_proc", "who": ATT, "key": AUROM, "kind": "tide",
                        "target": ATT, "value": 30, "shield": 30}
        i_eff = _idx(r, lambda e: e["event"] == "apply_effects" and e.get("kind") == "support")
        assert i_eff < r.events.index(tide) < _idx(r, lambda e: e["event"] == "resource_spend")
        # fresh flag cleared at the end of the creating turn, 3 turns left
        assert r.ps(ATT)["shields"] == [{"key": AUROM, "owner": ATT, "amount": 30.0,
                                         "cap": 200.0, "turns_left": 3, "fresh": False}]

    def test_ally_heal_capped_at_20_percent_of_the_target(self):
        sk = _skill(entries=[], effects=[_heal("ally", 500)])
        payload = dict(_pl(attack=1), ally_target_id=FOURTH)
        r = _run(_aurom_group(), payload, skills={1: sk})
        tide, = _procs(r, "tide")
        assert tide["target"] == FOURTH and tide["value"] == 200 and tide["shield"] == 200
        assert _shield(r, FOURTH) == 200 and _shield(r, ATT) == 0

    def test_hot_tick_overflow(self):
        st = _aurom_group()
        st["active_effects"] = {str(FOURTH): [_row("Регенерация", "hp", 40, ATT)]}
        r = _run(st, _pl())
        assert not r.of("resource_tick")            # full HP: nothing applied
        tide, = _procs(r, "tide")
        assert tide["target"] == FOURTH and tide["value"] == 40
        assert _effects_named(r.state, FOURTH, "Регенерация")[0]["magnitude"] == 40

    def test_potion_overflow(self):
        st = _duel(AUROM, att={"hp": 950, "fast_slots": [_scroll(health_recovery=100,
                                                                damage_entries=[])]})
        r = _run(st, _pl(item=50))
        assert r.hp(ATT) == 1000
        tide, = _procs(r, "tide")
        assert tide["target"] == ATT and tide["value"] == 50

    def test_non_auromancer_heals_make_no_shield(self):
        st = _duel(att={"hp": 950, "fast_slots": [_scroll(health_recovery=100,
                                                         damage_entries=[])]})
        r = _run(st, _pl(item=50))
        assert not r.procs and "shields" not in (r.ps(ATT) or {})

    def test_expires_after_three_of_his_own_turns(self):
        st = _aurom_group(hp=950, fast_slots=[_scroll(health_recovery=100, damage_entries=[])])
        r = _run(st, _pl(item=50))
        assert _shield(r, ATT) == 50
        assert r.ps(ATT)["shields"][0]["turns_left"] == 3
        # someone else's turn does not tick his shield
        r = _run(_turn(r.state, DEF), _pl(actor=DEF, target=ATT))
        assert r.ps(ATT)["shields"][0]["turns_left"] == 3
        left = []
        for _ in range(3):
            r = _run(_turn(r.state, ATT), _pl())
            left.append(_shield(r, ATT))
        assert left == [50, 50, 0]
        assert main._build_runtime(r.state)["participants"][str(ATT)]["shield"] == 0

    def test_vanishes_with_the_auromancer(self):
        st = _aurom_group(hp=10)
        st["participants"][str(FOURTH)]["passive_state"] = {
            "shields": [_sh(40, ATT, key=AUROM, turns=3)]}
        r = _run(_turn(st, DEF), _pl(attack=1, actor=DEF, target=ATT), skills={1: _skill()})
        assert ATT in _defeated(r)
        assert _shield(r, FOURTH) == 0


# ══════════════════════════════════════════════════════════════════════════════
# Guardian «Возмездие»
# ══════════════════════════════════════════════════════════════════════════════

class TestGuardianReflect:

    def test_reflect_event_and_stats(self):
        r = _run(_duel(def_key=GUARD), _pl(attack=1), skills={1: _skill()})
        hit, refl = r.dmg
        assert hit["target"] == DEF and "passives" not in hit
        assert refl == {"event": "damage", "source": DEF, "target": ATT, "final": 6.75,
                        "damage_type": "physical", "reflected": True, "absorbed": 0,
                        "passives": [{"key": GUARD, "kind": "reflect", "value": 7,
                                      "owner": DEF}]}
        assert r.hp(ATT) == pytest.approx(1000 - 6.75)
        assert r.state["participants"][str(DEF)]["total_damage_dealt"] == 7
        assert r.state["participants"][str(ATT)]["total_damage_received"] == 7

    def test_attacker_shield_absorbs_the_reflect(self):
        st = _duel(def_key=GUARD, att=_shields(ATT, _sh(5, ATT)))
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        refl, = _reflects(r)
        assert refl["absorbed"] == 5 and refl["shield_left"] == 0
        assert r.hp(ATT) == pytest.approx(1000 - 1.75)

    def test_guardian_own_shield_part_counts(self):
        st = _duel(def_key=GUARD, de=_shields(DEF, _sh(20, DEF)))
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert r.dmg[0]["absorbed"] == 20
        assert _reflects(r)[0]["final"] == 6.75

    def test_guardian_vs_guardian_one_reflect(self):
        r = _run(_duel(GUARD, GUARD), _pl(attack=1), skills={1: _skill()})
        assert len(_reflects(r)) == 1 and len(r.dmg) == 2
        assert r.hp(ATT) == pytest.approx(1000 - 6.75) and r.hp(DEF) == 955

    def test_reflect_kills_attacker_mid_aoe_aoe_stops_no_extra_hit(self):
        st = _battle({ATT: _p(ATT, 0, MECHANIC, hp=5), FOURTH: _p(FOURTH, 0),
                      DEF: _p(DEF, 1, GUARD), THIRD: _p(THIRD, 1)})
        aoe = _skill(entries=[dict(_damage_row(), aoe_shape="all")])
        with W1._rolls(True), patch.object(P, "pick", lambda seq: seq[-1]):
            r = _run(st, _pl(attack=1), skills={1: aoe})
        hit, refl = r.dmg
        assert hit["target"] == DEF and refl["reflected"] and refl["target"] == ATT
        assert r.hp(ATT) == pytest.approx(5 - 6.75)
        assert r.hp(THIRD) == 1000 and len(r.spy.calls) == 1
        assert not [e for e in r.events if "extra_hit" in e]
        assert _defeated(r) == [ATT]
        assert not r.procs                          # own team: no kill, no passive procs

    def test_extra_hit_is_reflected(self):
        st = _trio(MECHANIC, third={"passive_key": GUARD})
        with W1._rolls(True), patch.object(P, "pick", lambda seq: seq[-1]):
            r = _run(st, _pl(attack=1), skills={1: _skill()})
        splash = next(e for e in r.dmg if e.get("extra_hit"))
        refl, = _reflects(r)
        assert r.events.index(refl) == r.events.index(splash) + 1
        assert refl["source"] == THIRD and refl["final"] == pytest.approx(RAW * 0.4 * 0.15)

    def test_dot_is_not_reflected(self):
        st = _duel(def_key=GUARD)
        st["active_effects"] = {str(DEF): [_row("Bleeding", "bleeding", 50, ATT)]}
        r = _run(st, _pl())
        assert r.of("effect_tick") and not _reflects(r)
        assert r.hp(ATT) == 1000

    def test_guardian_killed_by_the_hit_still_reflects_without_overkill(self):
        st = _trio(de={"passive_key": GUARD, "hp": 20})
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        refl, = _reflects(r)
        assert refl["final"] == 3.0                 # 15% of the 20 HP it had
        assert DEF in _defeated(r)

    def test_old_state_guardian_without_passive_state(self):
        st = _duel(def_key=GUARD)
        st["participants"][str(DEF)].pop("passive_state")
        st["participants"][str(ATT)].pop("passive_state")
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert len(_reflects(r)) == 1


# ══════════════════════════════════════════════════════════════════════════════
# Lifesteal — Berserk «Ярость» < 25%, Priest «Вера»
# ══════════════════════════════════════════════════════════════════════════════

class TestLifesteal:

    def test_low_hp_berserk_heals_first_then_takes_the_reflect_and_survives(self):
        r = _run(_duel(BERSERK, GUARD, att={"hp": 5}), _pl(attack=1), skills={1: _skill()})
        hit, refl = r.dmg
        dealt = RAW * 1.36                          # rage capped at +36%
        assert hit["final"] == pytest.approx(dealt)
        steal, = _contrib(hit, BERSERK, "lifesteal")
        assert steal == {"key": BERSERK, "kind": "lifesteal",
                         "value": int(round(dealt * 0.15)), "owner": ATT}
        assert refl["reflected"] and refl["final"] == pytest.approx(round(dealt * 0.15, 2))
        assert [c["kind"] for c in refl["passives"]] == ["reflect"]   # no heal from it
        assert r.hp(ATT) == pytest.approx(5.0)
        assert ATT not in _defeated(r)

    def test_berserk_at_exactly_25_percent_has_no_lifesteal(self):
        r = _run(_duel(BERSERK, att={"hp": 250}), _pl(attack=1), skills={1: _skill()})
        assert not _contrib(r.dmg[0], BERSERK, "lifesteal")
        assert r.hp(ATT) == 250

    def test_priest_heals_only_from_hp_removed_not_the_shield_part(self):
        st = _duel(PRIEST, att={"hp": 500}, de=_shields(DEF, _sh(25, DEF)))
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        ev, = r.dmg
        assert ev["absorbed"] == 25
        assert _contrib(ev, PRIEST, "lifesteal") == [
            {"key": PRIEST, "kind": "lifesteal", "value": 2, "owner": ATT}]
        assert r.hp(ATT) == pytest.approx(502)

    @pytest.mark.parametrize("dtype,pct", [("physical", 10), ("sainting", 15)])
    def test_priest_10_or_holy_15(self, dtype, pct):
        r = _run(_duel(PRIEST, att={"hp": 500}), _pl(attack=1), skills={1: _skill(dtype)})
        ev, = r.dmg
        assert ev["damage_type"] == dtype
        assert r.hp(ATT) == pytest.approx(500 + ev["final"] * pct / 100)
        assert _contrib(ev, PRIEST, "lifesteal")[0]["value"] == int(round(ev["final"] * pct / 100))

    def test_priest_at_full_hp_logs_nothing(self):
        r = _run(_duel(PRIEST), _pl(attack=1), skills={1: _skill()})
        assert "passives" not in r.dmg[0]

    def test_scroll_lifesteals(self):
        st = _duel(PRIEST, att={"hp": 500, "fast_slots": [_scroll()]})
        r = _run(st, _pl(item=50))
        ev, = r.dmg
        assert ev["source_kind"] == "item"
        assert _contrib(ev, PRIEST, "lifesteal")
        assert r.hp(ATT) == pytest.approx(500 + ev["final"] * 0.10)

    def test_dot_does_not_lifesteal(self):
        st = _duel(PRIEST, att={"hp": 500})
        st["active_effects"] = {str(DEF): [_row("Bleeding", "bleeding", 50, ATT)]}
        r = _run(st, _pl())
        assert r.of("effect_tick") and r.hp(ATT) == 500


# ══════════════════════════════════════════════════════════════════════════════
# Necromancer «Плата кровью»
# ══════════════════════════════════════════════════════════════════════════════

def _costly(cost=10, sid=2):
    return _skill(entries=[], cost_mana=cost, sid=sid)


class TestNecromancer:

    def test_shortfall_paid_with_hp(self):
        r = _run(_duel(NECRO, att={"mana": 4}), _pl(support=2), skills={2: _costly()})
        spend, = r.of("resource_spend")
        assert spend == {"event": "resource_spend", "who": ATT, "energy": 0, "mana": 4,
                         "stamina": 0, "hp_paid": 9,
                         "passives": [{"key": NECRO, "kind": "blood_price", "value": 9,
                                       "owner": ATT}]}
        att = r.state["participants"][str(ATT)]
        assert att["mana"] == 0 and att["hp"] == 991
        assert r.save.called

    def test_payment_may_leave_exactly_one_hp(self):
        r = _run(_duel(NECRO, att={"mana": 0, "hp": 16}), _pl(support=2), skills={2: _costly()})
        assert r.of("resource_spend")[0]["hp_paid"] == 15 and r.hp(ATT) == 1

    @pytest.mark.parametrize("hp,shown", [(15.9, "15.9"), (1, "1")])
    def test_unaffordable_is_a_russian_400_and_nothing_saved(self, hp, shown):
        st = _duel(NECRO, att={"mana": 0, "hp": hp})
        r = _run(st, _pl(support=2), skills={2: _costly()}, expect=400)
        assert r.resp.json()["detail"] == (
            "Недостаточно маны: нужно 10, есть 0. Доплатить здоровьем нельзя: "
            f"нужно 15 HP, есть {shown} (должно остаться хотя бы 1)")
        assert not r.save.called

    def test_non_necromancer_keeps_the_old_400(self):
        r = _run(_duel(att={"mana": 0}), _pl(support=2), skills={2: _costly()}, expect=400)
        assert r.resp.json()["detail"] == "Недостаточно маны: нужно 10, есть 0"

    def test_enough_mana_no_hp_paid(self):
        r = _run(_duel(NECRO, att={"mana": 50}), _pl(support=2), skills={2: _costly()})
        assert r.of("resource_spend")[0] == {"event": "resource_spend", "who": ATT,
                                             "energy": 0, "mana": 10, "stamina": 0}

    def test_killed_by_reflect_before_paying_is_not_charged(self):
        st = _battle({ATT: _p(ATT, 0, NECRO, hp=5, mana=0), FOURTH: _p(FOURTH, 0),
                      DEF: _p(DEF, 1, GUARD)})
        r = _run(st, _pl(attack=1), skills={1: _skill(cost_mana=10)})
        spend, = r.of("resource_spend")
        assert spend == {"event": "resource_spend", "who": ATT, "energy": 0, "mana": 0,
                         "stamina": 0}
        assert r.hp(ATT) == pytest.approx(5 - 6.75)
        assert ATT in _defeated(r)

    def test_kill_heals_10_percent(self):
        r = _run(_trio(NECRO, att={"hp": 500}, de={"hp": 10}), _pl(attack=1),
                 skills={1: _skill()})
        heal, = _procs(r, "kill_heal")
        assert heal == {"event": "passive_proc", "who": ATT, "key": NECRO,
                        "kind": "kill_heal", "target": DEF, "value": 100}
        assert r.events.index(heal) > _idx(r, lambda e: e["event"] == "participant_defeated")
        att = r.state["participants"][str(ATT)]
        assert att["hp"] == 600 and att["max_hp"] == 1000


# ══════════════════════════════════════════════════════════════════════════════
# Bard «Ритм»
# ══════════════════════════════════════════════════════════════════════════════

INSP = P.INSPIRATION_EFFECT_NAME


def _bard_group(bard=ATT, **bard_over):
    parts = {ATT: _p(ATT, 0), FOURTH: _p(FOURTH, 0), DEF: _p(DEF, 1)}
    parts[bard] = _p(bard, 0, BARD, **bard_over)
    return _battle(parts, actor=bard)


def _insp(state, pid):
    return _effects_named(state, pid, INSP)


async def _expire(state, pid):
    """handle_expired_turn on `pid` (deadline already past) — returns the
    events handed to save_log and the outcome."""
    rs = real_redis_state      # real time helpers (main's may be MagicMocks)
    state["next_actor"] = pid
    state["deadline_at"] = (rs.utc_now() - timedelta(hours=2)).isoformat()
    battle = SimpleNamespace(status=main.BattleStatus.in_progress, is_paused=False)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
    save_log = MagicMock()
    patches = [
        patch("main.get_battle", AsyncMock(return_value=battle)),
        patch("main.load_state", AsyncMock(return_value=state)),
        patch("main.save_state", AsyncMock()),
        patch("main.get_redis_client", AsyncMock(return_value=AsyncMock())),
        patch("main.get_cached_snapshot", AsyncMock(return_value=None)),
        patch("main.load_snapshot", AsyncMock(return_value=None)),
        patch("main.save_log", save_log),
        patch("main._notify_timeout_dropout", AsyncMock()),
        patch("main._finalize_battle", AsyncMock(return_value=None)),
        patch("main.utc_now", rs.utc_now),
        patch("main.parse_deadline", rs.parse_deadline),
        patch("main.deadline_epoch", rs.deadline_epoch),
    ]
    for p in patches:
        p.start()
    try:
        outcome = await main.handle_expired_turn(db, 1, pid)
    finally:
        for p in reversed(patches):
            p.stop()
    return outcome, save_log.delay.call_args[0][2]


class TestBard:

    def test_group_stack_rows_on_self_and_allies(self):
        r = _run(_bard_group(), _pl())
        proc, = _procs(r, "inspiration")
        assert proc == {"event": "passive_proc", "who": ATT, "key": BARD,
                        "kind": "inspiration", "stacks": 1, "value": 3, "mode": "group",
                        "targets": [ATT, FOURTH]}
        for pid in (ATT, FOURTH):
            row, = _insp(r.state, pid)
            assert row["attribute"] == "percent_damage" and row["magnitude"] == 3
            assert row["source"] == P.SOURCE_BARD and row["owner_id"] == ATT
            assert row["duration"] == 2
        assert not _insp(r.state, DEF)

    def test_stacks_grow_across_turns_and_raise_damage(self):
        r1 = _run(_bard_group(), _pl())
        # the ally's attack already gets +3%
        r2 = _run(_turn(r1.state, FOURTH), _pl(attack=1, actor=FOURTH), skills={1: _skill()})
        assert r2.spy.calls[0]["percent_buffs"]["all"] == 3
        assert r2.dmg[0]["final"] == pytest.approx(RAW * 1.03)
        # the Bard's next turn: 2 stacks, rows refreshed in place (one each)
        r3 = _run(_turn(r2.state, ATT), _pl(attack=1), skills={1: _skill()})
        assert r3.spy.calls[0]["percent_buffs"]["all"] == 3     # rows at attack time
        assert _procs(r3, "inspiration")[0]["stacks"] == 2
        for pid in (ATT, FOURTH):
            row, = _insp(r3.state, pid)
            assert row["magnitude"] == 6

    def test_solo_mode(self):
        r = _run(_duel(BARD), _pl())
        proc, = _procs(r, "inspiration")
        assert (proc["mode"], proc["value"], proc["targets"]) == ("solo", 5, [ATT])

    def test_removed_when_the_bard_dies_at_9_5(self):
        r1 = _run(_bard_group(bard=FOURTH, hp=10), _pl(actor=FOURTH))
        assert _insp(r1.state, ATT) and _insp(r1.state, FOURTH)
        r2 = _run(_turn(r1.state, DEF), _pl(attack=1, actor=DEF, target=FOURTH),
                  skills={1: _skill()})
        end, = _procs(r2, "inspiration_end")
        assert end == {"event": "passive_proc", "who": FOURTH, "key": BARD,
                       "kind": "inspiration_end", "targets": [ATT, FOURTH]}
        assert r2.events.index(end) > _idx(r2, lambda e: e["event"] == "participant_defeated")
        assert not _insp(r2.state, ATT) and not _insp(r2.state, FOURTH)
        assert r2.ps(FOURTH)["bard_stacks"] == 0

    @pytest.mark.asyncio
    async def test_removed_on_a_timeout_drop_out(self):
        r1 = _run(_bard_group(), _pl())
        st = copy.deepcopy(r1.state)
        outcome, events = await _expire(st, ATT)
        assert outcome != "already_out"
        assert {"event": "participant_defeated", "who": ATT, "hp": 0} in events
        assert {"event": "passive_proc", "who": ATT, "key": BARD,
                "kind": "inspiration_end", "targets": [ATT, FOURTH]} in events
        assert not _insp(st, ATT) and not _insp(st, FOURTH)


# ══════════════════════════════════════════════════════════════════════════════
# Etheriad «Шёпот духов»
# ══════════════════════════════════════════════════════════════════════════════

def _eth_group(fourth=None, **att):
    return _battle({ATT: _p(ATT, 0, ETH, **att), FOURTH: _p(FOURTH, 0, **(fourth or {})),
                    DEF: _p(DEF, 1), THIRD: _p(THIRD, 1)})


class TestEtheriad:

    def test_curse_on_the_enemy_he_hit_and_it_lowers_resists(self):
        with _pick_first() as pk:
            r = _run(_eth_group(), _pl(attack=1), skills={1: _skill()})
        proc, = _procs(r, "spirit_whisper")
        assert proc == {"event": "passive_proc", "who": ATT, "key": ETH,
                        "kind": "spirit_whisper", "target": DEF, "mode": "curse", "value": -8}
        assert [list(c.args[0]) for c in pk.call_args_list] == [[DEF]]   # only who he hit
        row, = _effects_named(r.state, DEF, P.SPIRIT_CURSE_NAME)
        assert row["attribute"] == "percent_resist_all" and row["magnitude"] == -8
        assert row["source"] == P.SOURCE_ETHERIAD and row["owner_id"] == ATT
        assert not _effects_named(r.state, THIRD, P.SPIRIT_CURSE_NAME)
        # next hit on DEF: −8% resists; DEF already cursed → might on the ally
        with _pick_first():
            r2 = _run(_turn(r.state, ATT), _pl(attack=1), skills={1: _skill()})
        assert r2.spy.calls[0]["percent_resists"]["all"] == -8
        assert r2.dmg[0]["final"] == pytest.approx(RAW * 1.08)
        proc2, = _procs(r2, "spirit_whisper")
        assert (proc2["mode"], proc2["target"], proc2["value"]) == ("might", FOURTH, 8)

    def test_might_raises_the_allys_damage(self):
        st = _eth_group()
        st["active_effects"] = {str(DEF): [_row(P.SPIRIT_CURSE_NAME, "percent_resist_all",
                                                -8, ATT, source=P.SOURCE_ETHERIAD)]}
        with _pick_first():
            r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert _procs(r, "spirit_whisper")[0]["mode"] == "might"
        r2 = _run(_turn(r.state, FOURTH), _pl(attack=1, actor=FOURTH, target=THIRD),
                  skills={1: _skill()})
        assert r2.spy.calls[0]["percent_buffs"]["all"] == 8

    def test_ward_on_a_beaten_ally_comes_first(self):
        pick = MagicMock()
        with patch.object(P, "pick", pick):
            r = _run(_eth_group(fourth={"hp": 400}), _pl(attack=1), skills={1: _skill()})
        proc, = _procs(r, "spirit_whisper")
        assert (proc["mode"], proc["target"], proc["value"]) == ("ward", FOURTH, 8)
        assert not pick.called
        row, = _effects_named(r.state, FOURTH, P.SPIRIT_WARD_NAME)
        assert row["magnitude"] == 8

    def test_alone_and_nothing_landed_might_on_self(self):
        with _pick_first():
            r = _run(_duel(ETH), _pl(attack=1), skills={1: _skill()}, dodge=True)
        proc, = _procs(r, "spirit_whisper")
        assert (proc["mode"], proc["target"]) == ("might", ATT)

    def test_silent_on_a_stunned_turn(self):
        st = _eth_group()
        st["active_effects"] = {str(ATT): [_row("Stun", "stun", 0, DEF, duration=1)]}
        r = _run(st, _pl(attack=1), skills={1: _skill()})
        assert r.of("control_skip") and not _procs(r, "spirit_whisper")


# ══════════════════════════════════════════════════════════════════════════════
# Trickster «Обман» — redirect
# ══════════════════════════════════════════════════════════════════════════════

def _trick_group(att_key=None, att=None, fourth=None):
    return _battle({ATT: _p(ATT, 0, att_key, **(att or {})),
                    FOURTH: _p(FOURTH, 0, **(fourth or {})),
                    DEF: _p(DEF, 1, TRICK)})


class TestTricksterRedirect:

    def _go(self, st, payload=None, skills=None, **kw):
        with W1._rolls(True), _pick_first() as pk:
            r = _run(st, payload or _pl(attack=1),
                     skills=skills if skills is not None else {1: _skill()},
                     dodge=lambda *_: False, **kw)
        r.pick = pk
        return r

    def test_ally_takes_half_without_a_dodge_roll(self):
        r = self._go(_trick_group())
        miss, red = r.dmg
        assert miss == {"event": "damage", "source": ATT, "target": DEF, "dodged": True,
                        "final": 0, "deceived": True,
                        "passives": [{"key": TRICK, "kind": "deceit", "owner": DEF}]}
        assert red["source"] == ATT and red["target"] == FOURTH
        assert red["final"] == pytest.approx(RAW * 0.5)
        assert red["redirected"] is True and red["deceived_by"] == DEF
        assert "aoe_falloff" not in red             # the 50% is not AoE falloff
        assert red["passives"] == [{"key": TRICK, "kind": "redirect", "value": 50, "owner": DEF}]
        assert r.hp(FOURTH) == pytest.approx(1000 - RAW * 0.5) and r.hp(DEF) == 1000
        assert r.dodge.call_count == 1              # only the Trickster's roll
        assert [list(c.args[0]) for c in r.pick.call_args_list] == [[FOURTH]]

    def test_redirected_blow_is_not_damage_dealt_by_the_attacker(self):
        r = self._go(_trick_group())
        parts = r.state["participants"]
        assert parts[str(ATT)].get("total_damage_dealt", 0) == 0
        assert parts[str(FOURTH)]["total_damage_received"] == round(RAW * 0.5)

    def test_no_attacker_passives_on_the_redirected_blow(self):
        st = _trick_group(BERSERK, att={"hp": 200})
        r = self._go(st)
        red = next(e for e in r.dmg if e.get("redirected"))
        assert r.spy.calls[0]["percent_buffs"].get("all", 0) == 0   # no rage
        assert red["final"] == pytest.approx(RAW * 0.5)
        assert "passive_key" not in red
        assert r.hp(ATT) == 200                                    # no lifesteal

    def test_no_target_passives_but_the_shield_absorbs(self):
        st = _trick_group(fourth={"passive_key": GUARD, **_shields(FOURTH, _sh(10, FOURTH))})
        r = self._go(st)
        red = next(e for e in r.dmg if e.get("redirected"))
        assert red["absorbed"] == 10 and red["shield_left"] == 0
        assert not _reflects(r) and r.hp(ATT) == 1000
        st = _trick_group(fourth={"passive_key": PALADIN, "hp": 300})
        r = self._go(st)
        assert r.hp(FOURTH) == pytest.approx(300 - RAW * 0.5)
        assert not _procs(r, "vow") and "vow_used" not in r.ps(FOURTH)

    def test_no_ally_plain_deceit(self):
        pick = MagicMock()
        with W1._rolls(True), patch.object(P, "pick", pick):
            r = _run(_duel(def_key=TRICK), _pl(attack=1), skills={1: _skill()})
        assert len(r.dmg) == 1 and r.dmg[0]["deceived"] is True
        assert r.spy.calls == [] and not pick.called

    def test_extra_hits_never_redirect(self):
        st = _battle({ATT: _p(ATT, 0, MECHANIC), FOURTH: _p(FOURTH, 0),
                      DEF: _p(DEF, 1), THIRD: _p(THIRD, 1, TRICK)})
        picks = []

        def _pick(seq):
            picks.append(list(seq))
            return list(seq)[-1]

        with W1._rolls(True), patch.object(P, "pick", _pick):
            r = _run(st, _pl(attack=1), skills={1: _skill()})
        splash = next(e for e in r.dmg if e.get("extra_hit"))
        assert splash["target"] == THIRD and splash["deceived"] is True
        assert splash["final"] == 0
        assert not [e for e in r.dmg if e.get("redirected")]
        assert [FOURTH] not in picks and r.hp(FOURTH) == 1000

    def test_scroll_is_redirected_too(self):
        st = _trick_group(att={"fast_slots": [_scroll()]})
        r = self._go(st, _pl(item=50), skills={})
        miss, red = r.dmg
        assert miss["deceived"] and red["redirected"] and red["source_kind"] == "item"
        assert red["target"] == FOURTH and r.hp(FOURTH) < 1000

    def test_ally_killed_by_a_redirect_is_no_kill(self):
        st = _trick_group(NECRO, att={"hp": 500}, fourth={"hp": 10})
        r = self._go(st)
        assert FOURTH in _defeated(r)
        assert not _procs(r, "kill_heal") and r.hp(ATT) == 500


# ══════════════════════════════════════════════════════════════════════════════
# Regression guard — passive-less battles are byte-identical
# ══════════════════════════════════════════════════════════════════════════════

def _old_land_hit(state, attacker_pid, target_pid, dealt, damage_type, direct=True):
    """The pre-FEAT-190 HP change of `_strike`: `hp -= dealt`, nothing else."""
    state["participants"][str(target_pid)]["hp"] -= dealt
    return {"absorbed": 0.0, "shield_left": 0, "hp_removed": 0.0,
            "contributions": [], "post_events": []}


def _drop_callbacks(fn):
    def _wrapped(*a, absorb_fn=None, overheal_fn=None, **kw):
        return fn(*a, **kw)
    return _wrapped


class TestPassiveLessBattleIsByteIdentical:

    def _scenario(self):
        st = _battle({ATT: _p(ATT, 0, hp=900), FOURTH: _p(FOURTH, 0, hp=700),
                      DEF: _p(DEF, 1), THIRD: _p(THIRD, 1, hp=30)})
        acid = {"effect_name": "Кислота", "attribute_key": "hp", "magnitude": 10,
                "duration": 1, "target_side": "enemy", "chance": 100}
        balm = {"effect_name": "Бальзам", "attribute_key": "hp", "magnitude": 20,
                "duration": 1, "target_side": "self", "chance": 100}
        st["participants"][str(ATT)]["fast_slots"] = [_scroll(effects=[acid, balm])]
        st["active_effects"] = {
            str(DEF): [_row("Bleeding", "bleeding", 30, ATT)],
            str(ATT): [_row("Регенерация", "hp", 40, ATT)],
            str(THIRD): [_row("Яд", "hp", -15, ATT, duration=3)],
        }
        sk = _skill(entries=[dict(_damage_row(), aoe_shape="all")],
                    effects=[_eff("Burn", mag=5), _heal("all_allies", 30),
                             _eff("Сила", side="self", attr="strength", mag=3)])
        return st, _pl(attack=1, item=50), {1: sk}

    def _snap(self, r):
        st = copy.deepcopy(r.state)
        st.pop("deadline_at", None)
        return (json.dumps(r.events, sort_keys=True, ensure_ascii=False),
                json.dumps(st, sort_keys=True, ensure_ascii=False))

    def test_same_events_and_state_as_the_old_call_shapes(self):
        st, payload, skills = self._scenario()
        roll, pick = MagicMock(return_value=True), MagicMock()
        with patch.object(P, "roll_pct", roll), patch.object(P, "pick", pick):
            new = _run(copy.deepcopy(st), payload, skills=skills)
        assert not roll.called and not pick.called
        old_patches = {
            "main.apply_new_effects": _drop_callbacks(REAL_BUFFS["apply_new_effects"]),
            "main.tick_periodic_effects": _drop_callbacks(REAL_BUFFS["tick_periodic_effects"]),
        }
        with patch.object(P, "land_hit", _old_land_hit), \
                patch.object(P, "end_of_action", lambda *a, **k: ([], [])), \
                patch.object(P, "on_deaths", lambda *a, **k: []), \
                patch.object(P, "check_vows", lambda *a, **k: []), \
                patch.object(P, "on_heal", lambda *a, **k: []), \
                patch.object(P, "tick_shields", lambda *a, **k: None), \
                patch.object(P, "blood_price", lambda *a, **k: None):
            old = _run(copy.deepcopy(st), payload, skills=skills, extra=old_patches)
        # the scenario really exercised every site
        kinds = {e["event"] for e in new.events}
        assert {"damage", "effect_tick", "resource_tick", "apply_effects",
                "item_use", "participant_defeated"} <= kinds, kinds
        assert self._snap(new) == self._snap(old)
        for ev in new.events:
            for k in WAVE2_EVENT_KEYS:
                assert k not in ev, (k, ev)
            assert ev["event"] != "passive_proc", ev
        for pd in new.state["participants"].values():
            assert not set(pd.get("passive_state") or {}) & {
                "shields", "vow_used", "bard_stacks", "bard_mode"}


# ══════════════════════════════════════════════════════════════════════════════
# Leftover from the dev report — attacker killed in the scroll step
# ══════════════════════════════════════════════════════════════════════════════

class TestDeadAttackerLeftover:

    def test_dead_attacker_lands_no_attack_effects(self):
        """The attacker (5 HP) uses a scroll AND an attack skill on a Guardian.
        The scroll's reflect kills him in the item step (E10). PM rule: a dead
        attacker does nothing further — the attack skill's damage AND its
        effect rows (9.0 self, 9.0b enemy, 9.0c/d allies, 9.0e all enemies)
        are skipped. Costs / cooldown of the chosen skill are still charged."""
        st = _battle({ATT: _p(ATT, 0, hp=5, fast_slots=[_scroll()]), FOURTH: _p(FOURTH, 0),
                      DEF: _p(DEF, 1, GUARD), THIRD: _p(THIRD, 1)})
        sk = _skill(effects=[_eff("Weakness", attr="strength", mag=4, duration=3),
                             _eff("Сила", side="self", attr="strength", mag=3)])
        r = _run(st, _pl(attack=1, item=50), skills={1: sk})
        scroll_hit, refl = r.dmg                   # no attack-skill damage event
        assert scroll_hit["source_kind"] == "item" and refl["reflected"]
        assert r.hp(ATT) <= 0 and ATT in _defeated(r)
        atk_effects = [e for e in r.events
                       if e["event"] == "apply_effects" and e.get("kind") == "attack"]
        assert atk_effects == []
        assert not _effects_named(r.state, DEF, "Weakness")
        assert not _effects_named(r.state, ATT, "Сила")
        assert len(r.spy.calls) == 1               # only the scroll was computed
        # the action was taken: the payment is still logged
        assert any(e["event"] == "resource_spend" and e["who"] == ATT for e in r.events)
