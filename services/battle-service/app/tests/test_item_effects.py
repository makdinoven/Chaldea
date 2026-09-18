"""FEAT-168, task #11 — the in-battle item step against the REAL effect engine.

`test_item_usage.py` replaces the whole `buffs` module with a `MagicMock`
(`:34-45`), so item + effect interaction was literally untestable there. This
module runs the same `_make_action_core` turn but wires the **real** `buffs`
functions back into `main` (plus a real `_normalize_effect`, real
`aggregate_modifiers` and the real cleanse/refresh logic), and asserts the state
that actually lands in Redis and the events that actually reach the frontend.

Covered:
  * buff potion  — effect record in the state (source/owner/duration/fresh) AND
    the buff reaching the same turn's attack (the anti-silent-failure guard:
    this test fails the moment an item's effects stop reaching the engine)
  * damage scroll — the normal damage formula, `source_kind: "item"`, HP and the
    cumulative damage counters
  * cleanse       — selectors, `magnitude` as a limit, and a Stun that survives
    `selector="all"` (engine rule, not an item setting)
  * weapon coating — bonus folded into weapon damage entries (and NOT into
    `no_weapon` ones), effects on the targets that were actually hit, the turn of
    application already counts, duration tick, expiry event, and a second coating
    refused via `item_rejected` without consuming the item or losing the turn
  * stack bookkeeping — quantity−1, slot popped at zero, legacy slot without
    `quantity` behaves as before
  * the `item_use` payload keys, exactly as `BattlePageBar.formatBattleEvent`
    reads them
  * a full-skip control nullifying the item
  * a pre-deploy-shaped Redis state (no `quantity`, no `effects`, no
    `damage_entries`, no `consumable_action`, no `weapon_coating`, effect records
    without `owner_id`/`fresh`/`source`) completing a whole turn unchanged
"""

import importlib
import importlib.util
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("aioredis", MagicMock())
sys.modules.setdefault("celery", MagicMock())

import database  # noqa: E402

database.engine = MagicMock()

for _mod_name in [
    "redis_state", "mongo_client", "mongo_helpers", "tasks",
    "inventory_client", "character_client", "skills_client",
]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

_redis_state_mock = sys.modules["redis_state"]
_redis_state_mock.ZSET_DEADLINES = "battle:deadlines"
_redis_state_mock.KEY_BATTLE_TURNS = "battle:{id}:turns"
_redis_state_mock.init_battle_state = AsyncMock()
_redis_state_mock.load_state = AsyncMock(return_value=None)
_redis_state_mock.save_state = AsyncMock()
_redis_state_mock.get_redis_client = AsyncMock(return_value=AsyncMock())
_redis_state_mock.cache_snapshot = AsyncMock()
_redis_state_mock.get_cached_snapshot = AsyncMock(return_value=None)
_redis_state_mock.state_key = MagicMock(return_value="battle:1:state")

_tasks_mock = sys.modules["tasks"]
_tasks_mock.save_log = MagicMock()
_tasks_mock.save_log.delay = MagicMock()

_skills_mock = sys.modules["skills_client"]
_skills_mock.character_has_skill = AsyncMock(return_value=True)
_skills_mock.get_resolved_skill = AsyncMock(return_value={})
_skills_mock.get_item = AsyncMock(return_value={})
_skills_mock.character_skills = AsyncMock(return_value=[])

_inv_mock = sys.modules["inventory_client"]
_inv_mock.get_fast_slots = AsyncMock(return_value=[])
_inv_mock.consume_item = AsyncMock(return_value={"status": "ok", "remaining_quantity": 0})

_char_mock = sys.modules["character_client"]
_char_mock.get_character_profile = AsyncMock(
    return_value={"character_name": "Test", "character_photo": ""}
)

# ── Recover the REAL engine modules. Other test files swap them for MagicMocks
# during collection; `main` binds the names at import time, so the tests below
# patch `main.<name>` with these saved real callables.
if "battle_engine" in sys.modules:
    del sys.modules["battle_engine"]
battle_engine = importlib.import_module("battle_engine")
sys.modules["battle_engine"] = battle_engine

# `buffs` is loaded as a PRIVATE instance, straight from the file and NOT
# registered in `sys.modules`: `test_item_usage.py` overwrites the attributes of
# whatever `buffs` it finds there (`:64-70`), which would silently neuter these
# tests (a mocked `evaluate_control` makes every Stun cleansable). The private
# instance is immune, and `sys.modules["buffs"]` is left as the other modules
# expect it.
_BUFFS_PATH = os.path.join(os.path.dirname(__file__), "..", "buffs.py")
_buffs_spec = importlib.util.spec_from_file_location("buffs_under_test", _BUFFS_PATH)
buffs = importlib.util.module_from_spec(_buffs_spec)
_buffs_spec.loader.exec_module(buffs)

REAL_BUFFS = {
    "apply_new_effects": buffs.apply_new_effects,
    "remove_effects": buffs.remove_effects,
    "decrement_durations": buffs.decrement_durations,
    "tick_periodic_effects": buffs.tick_periodic_effects,
    "aggregate_modifiers": buffs.aggregate_modifiers,
    "build_percent_damage_buffs": buffs.build_percent_damage_buffs,
    "build_percent_resist_buffs": buffs.build_percent_resist_buffs,
    "evaluate_control": buffs.evaluate_control,
    "first_cycle_limit_skills": buffs.first_cycle_limit_skills,
    "_normalize_effect": buffs._normalize_effect,
}
for _name, _fn in REAL_BUFFS.items():
    assert not isinstance(_fn, MagicMock), f"buffs recovery failed for {_name}"

_REAL_compute_damage_with_rolls = battle_engine.compute_damage_with_rolls
_REAL_apply_flat_modifiers = battle_engine.apply_flat_modifiers
assert not isinstance(_REAL_compute_damage_with_rolls, MagicMock)

from main import app  # noqa: E402
from database import get_db  # noqa: E402
from schemas import SkillSelection  # noqa: E402

app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ──────────────────────────────────────────────────────────────────────────────

ATTACKER_PID = 1
DEFENDER_PID = 2
ATTACKER_CHAR = 10
DEFENDER_CHAR = 20

ATTRS = {
    "strength": 20, "agility": 10, "intelligence": 5, "endurance": 0, "luck": 0,
    "charisma": 1, "damage": 5, "dodge": 0,
    "critical_hit_chance": 0, "critical_damage": 100,
    "current_health": 100, "current_mana": 50,
    "current_energy": 50, "current_stamina": 50,
}


def _mock_response(status_code: int, json_data: dict | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _participant(character_id, team, **over):
    part = {
        "character_id": character_id,
        "team": team,
        "hp": 100, "mana": 50, "energy": 50, "stamina": 50,
        "max_hp": 100, "max_mana": 100, "max_energy": 100, "max_stamina": 100,
        "cooldowns": {},
        "fast_slots": [],
        "equipment_durability": {},
        "total_damage_dealt": 0,
        "total_damage_received": 0,
    }
    part.update(over)
    return part


def _state(*, fast_slots=None, active_effects=None, attacker_over=None,
           defender_over=None, first_cycle=False):
    attacker = _participant(ATTACKER_CHAR, 0, fast_slots=fast_slots or [])
    attacker.update(attacker_over or {})
    defender = _participant(DEFENDER_CHAR, 1)
    defender.update(defender_over or {})
    return {
        "turn_number": 3,
        "next_actor": ATTACKER_PID,
        "first_actor": ATTACKER_PID,
        "initiator_acted_once": True,
        "first_cycle": first_cycle,
        "turn_order": [ATTACKER_PID, DEFENDER_PID],
        "total_turns": 2,
        "last_turn": None,
        "deadline_at": "2026-01-01T00:00:00",
        "participants": {str(ATTACKER_PID): attacker, str(DEFENDER_PID): defender},
        "active_effects": active_effects or {},
    }


def _slot(item_id=42, **over):
    """A fast slot exactly as inventory-service serialises it after FEAT-168."""
    slot = {
        "slot_type": "fast_slot_1",
        "item_id": item_id,
        "quantity": 3,
        "name": "Зелье силы",
        "image": "potion.png",
        "health_recovery": 0,
        "mana_recovery": 0,
        "energy_recovery": 0,
        "stamina_recovery": 0,
        "consumable_action": None,
        "coating_turns": None,
        "coating_bonus_damage": None,
        "effects": [],
        "damage_entries": [],
    }
    slot.update(over)
    return slot


def _effect_row(effect_name, *, attribute_key=None, magnitude=0, duration=1,
                chance=100, target_side="self"):
    return {
        "target_side": target_side, "effect_name": effect_name,
        "chance": chance, "duration": duration, "magnitude": magnitude,
        "attribute_key": attribute_key,
    }


def _damage_row(*, amount=20, damage_type="fire", weapon_slot="no_weapon",
                target_side="enemy", **over):
    row = {
        "damage_type": damage_type, "amount": amount, "chance": 100,
        "weapon_slot": weapon_slot, "target_side": target_side,
        "aoe_shape": "single", "aoe_falloff": 50, "aoe_max_targets": 3,
    }
    row.update(over)
    return row


def _attack_skill(damage_entries=None, effects=None):
    return {
        "id": 1, "name": "Удар",
        "damage_entries": damage_entries if damage_entries is not None else [],
        "effects": effects or [],
        "cooldown": 0, "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
    }


def _payload(item_id=None, attack_skill_id=None, target_id=None, ally_target_id=None):
    body = {
        "participant_id": ATTACKER_PID,
        "skills": {
            "attack_skill_id": attack_skill_id,
            "defense_skill_id": None,
            "support_skill_id": None,
            "item_id": item_id,
        },
    }
    if target_id is not None:
        body["target_id"] = target_id
    if ally_target_id is not None:
        body["ally_target_id"] = ally_target_id
    return body


def _mock_db():
    db = AsyncMock()
    owners = {ATTACKER_CHAR: 5, DEFENDER_CHAR: 6}

    async def _execute(query, params=None):
        result = MagicMock()
        if params and "cid" in params:
            result.fetchone.return_value = (owners.get(params["cid"]),) \
                if params["cid"] in owners else None
        else:
            result.fetchone.return_value = None
            result.scalar_one_or_none.return_value = None
        return result

    db.execute = AsyncMock(side_effect=_execute)
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


class _DamageSpy:
    """Wraps the REAL `compute_damage_with_rolls`, recording every entry it is
    handed. `calls` is what lets the coating tests prove the bonus was folded
    into the entry *before* the formula, not bolted on afterwards."""

    def __init__(self):
        self.calls = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return await _REAL_compute_damage_with_rolls(**kwargs)

    def entries(self):
        return [c["damage_entry"] for c in self.calls]

    def attacker_attrs(self):
        return [c["attacker_attr"] for c in self.calls]


def _run_turn(state, *, payload=None, attack_skill=None, consume_result=None,
              damage_spy=None, dodge=False, chance=True):
    """Run one POST /battles/1/action with the REAL buffs engine wired in.

    Returns (response, damage_spy, consume_mock, saved_state).
    """
    payload = payload or _payload()
    attack_skill = attack_skill or _attack_skill()
    damage_spy = damage_spy or _DamageSpy()
    consume_mock = AsyncMock(
        return_value=consume_result or {"status": "ok", "remaining_quantity": 0}
    )
    save_state_mock = AsyncMock()

    patches = {
        # ── infrastructure
        "main.get_redis_client": AsyncMock(return_value=AsyncMock()),
        "main.save_state": save_state_mock,
        "main.state_key": MagicMock(return_value="battle:1:state"),
        "main.write_turn": AsyncMock(),
        "main.finish_battle": AsyncMock(),
        "main.get_battle": AsyncMock(return_value=None),
        "main.load_state": AsyncMock(return_value=state),
        "main.save_log": MagicMock(delay=MagicMock()),
        "main._distribute_pve_rewards": AsyncMock(return_value=None),
        "auth_http.requests.get": MagicMock(return_value=_mock_response(
            200, {"id": 5, "username": "player", "role": "user", "permissions": []}
        )),
        # ── character / inventory / skills
        "main.fetch_full_attributes": AsyncMock(return_value=dict(ATTRS)),
        "main.fetch_main_weapon": AsyncMock(return_value=None),
        "main.fetch_weapons": AsyncMock(
            return_value={"main_weapon": None, "additional_weapons": None}),
        "main.fetch_character_class_id": AsyncMock(return_value=1),
        "main.character_has_skill": AsyncMock(return_value=True),
        "main.get_resolved_skill": AsyncMock(return_value=attack_skill),
        "main.consume_item": consume_mock,
        # ── determinism
        "main.roll_chance": MagicMock(return_value=chance),
        "main.roll_dodge": MagicMock(return_value=dodge),
        "main.compute_damage_with_rolls": damage_spy,
        # ── THE POINT OF THIS MODULE: the real effect engine
        **{f"main.{name}": fn for name, fn in REAL_BUFFS.items()},
        "main.apply_flat_modifiers": _REAL_apply_flat_modifiers,
    }

    patchers = [patch(target, value) for target, value in patches.items()]
    db = _mock_db()

    async def _fake_get_db():
        yield db

    for p in patchers:
        p.start()
    try:
        app.dependency_overrides[get_db] = _fake_get_db
        with TestClient(app) as client:
            response = client.post(
                "/battles/1/action", json=payload,
                headers={"Authorization": "Bearer fake-token"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        for p in reversed(patchers):
            p.stop()

    saved = save_state_mock.call_args[0][1] if save_state_mock.called else state
    return response, damage_spy, consume_mock, saved


def _events(response, name):
    return [e for e in response.json()["events"] if e["event"] == name]


def _one(response, name):
    found = _events(response, name)
    assert len(found) == 1, f"expected exactly one {name}, got {len(found)}"
    return found[0]


def _effects_of(state, pid):
    return state.get("active_effects", {}).get(str(pid), [])


# ══════════════════════════════════════════════════════════════════════════════
# A buff potion really reaches the engine — and the same turn's attack
# ══════════════════════════════════════════════════════════════════════════════

class TestBuffPotion:

    POTION = _slot(
        item_id=42, name="Зелье силы", quantity=3,
        effects=[_effect_row("StatModifier", attribute_key="strength",
                             magnitude=5, duration=3, target_side="self")],
    )

    def test_effect_record_lands_in_the_state(self):
        state = _state(fast_slots=[dict(self.POTION)])
        resp, _, _, saved = _run_turn(state, payload=_payload(item_id=42))
        assert resp.status_code == 200

        eff, = _effects_of(saved, ATTACKER_PID)
        assert eff["name"] == "StatModifier"
        assert eff["attribute"] == "strength"
        assert eff["magnitude"] == 5
        assert eff["duration"] == 3, "a fresh effect must not tick on its cast turn"
        assert eff["owner_id"] == ATTACKER_PID
        assert eff["source"] == "item:42", \
            "the item source is what makes a re-drink refresh instead of stack"

    def test_the_buff_reaches_the_same_turn_attack(self):
        """ANTI-SILENT-FAILURE GUARD. The item step runs before the attack step,
        so a strength potion must already be inside the attacker's attributes
        when the attack damage is computed. If the item's effect rows ever stop
        reaching `apply_new_effects`, this assertion is what breaks."""
        state = _state(fast_slots=[dict(self.POTION)])
        resp, spy, _, _ = _run_turn(
            state,
            payload=_payload(item_id=42, attack_skill_id=1, target_id=DEFENDER_PID),
            attack_skill=_attack_skill([_damage_row(amount=10, damage_type="physical",
                                                    weapon_slot="no_weapon")]),
        )
        assert resp.status_code == 200
        assert spy.calls, "the attack must have been computed"
        assert spy.attacker_attrs()[0]["strength"] == ATTRS["strength"] + 5

    def test_apply_effects_event_is_tagged_as_an_item(self):
        state = _state(fast_slots=[dict(self.POTION)])
        resp, _, _, _ = _run_turn(state, payload=_payload(item_id=42))
        ev = _one(resp, "apply_effects")
        assert ev["kind"] == "item"
        assert ev["who"] == ATTACKER_PID
        assert ev["item_id"] == 42
        assert ev["item_name"] == "Зелье силы"
        assert ev["effects"][0]["attribute"] == "strength"

    def test_drinking_the_same_potion_twice_refreshes_instead_of_stacking(self):
        """Turn 1 applies it; turn 2 re-applies with the same source key."""
        state = _state(fast_slots=[dict(self.POTION)])
        _, _, _, saved = _run_turn(state, payload=_payload(item_id=42))
        saved["next_actor"] = ATTACKER_PID
        resp, _, _, saved2 = _run_turn(saved, payload=_payload(item_id=42))
        assert resp.status_code == 200
        effects = _effects_of(saved2, ATTACKER_PID)
        assert len(effects) == 1, "the same item must refresh its own record"
        assert effects[0]["magnitude"] == 5
        # Turn 1 left it at 3 (fresh, no tick). Turn 2 refreshes to max(3, 3) = 3
        # at the item step and the end-of-turn tick then takes it to 2 — i.e. the
        # durations were extended, not summed to 6.
        assert effects[0]["duration"] == 2

    def test_instant_heal_row_is_clamped_and_not_stored(self):
        potion = _slot(item_id=43, name="Свиток лечения",
                       effects=[_effect_row("Heal", attribute_key="hp",
                                            magnitude=60, target_side="self")])
        state = _state(fast_slots=[potion],
                       attacker_over={"hp": 70, "fast_slots": [potion]})
        resp, _, _, saved = _run_turn(state, payload=_payload(item_id=43))
        assert resp.status_code == 200
        assert saved["participants"][str(ATTACKER_PID)]["hp"] == 100
        assert _effects_of(saved, ATTACKER_PID) == []

    def test_enemy_effect_row_lands_on_the_target_with_the_caster_as_owner(self):
        flask = _slot(item_id=44, name="Колба яда",
                      effects=[_effect_row("Poison", attribute_key="periodic_damage",
                                           magnitude=6, duration=3,
                                           target_side="enemy")])
        state = _state(fast_slots=[flask])
        resp, _, _, saved = _run_turn(
            state, payload=_payload(item_id=44, target_id=DEFENDER_PID))
        assert resp.status_code == 200
        eff, = _effects_of(saved, DEFENDER_PID)
        assert eff["name"] == "Poison"
        assert eff["attribute"] == "periodic_damage"
        assert eff["owner_id"] == ATTACKER_PID, \
            "a DoT ticks on its caster's turn, so the caster must own it"

    def test_an_effect_that_fails_its_chance_roll_is_not_applied(self):
        state = _state(fast_slots=[dict(self.POTION)])
        resp, _, _, saved = _run_turn(state, payload=_payload(item_id=42), chance=False)
        assert resp.status_code == 200
        assert _effects_of(saved, ATTACKER_PID) == []
        assert _events(resp, "apply_effects") == []
        assert _one(resp, "item_use")["effects"] == []


# ══════════════════════════════════════════════════════════════════════════════
# Damage scroll — the ordinary damage formula
# ══════════════════════════════════════════════════════════════════════════════

class TestDamageScroll:

    SCROLL = _slot(item_id=50, name="Свиток огня", quantity=2,
                   damage_entries=[_damage_row(amount=20, damage_type="fire",
                                               weapon_slot="no_weapon")])

    def test_damage_is_dealt_through_the_real_formula(self):
        state = _state(fast_slots=[dict(self.SCROLL)])
        resp, spy, _, saved = _run_turn(
            state, payload=_payload(item_id=50, target_id=DEFENDER_PID))
        assert resp.status_code == 200
        assert spy.entries()[0]["damage_type"] == "fire"
        assert spy.calls[0]["weapon"] is None, "no_weapon rows go through unarmed math"
        assert saved["participants"][str(DEFENDER_PID)]["hp"] < 100

    def test_damage_event_is_tagged_as_an_item(self):
        state = _state(fast_slots=[dict(self.SCROLL)])
        resp, _, _, _ = _run_turn(
            state, payload=_payload(item_id=50, target_id=DEFENDER_PID))
        ev = _one(resp, "damage")
        assert ev["source"] == ATTACKER_PID
        assert ev["target"] == DEFENDER_PID
        assert ev["source_kind"] == "item"
        assert ev["item_id"] == 50
        assert ev["item_name"] == "Свиток огня"
        assert ev["final"] > 0

    def test_cumulative_damage_counters_are_updated(self):
        state = _state(fast_slots=[dict(self.SCROLL)])
        resp, _, _, saved = _run_turn(
            state, payload=_payload(item_id=50, target_id=DEFENDER_PID))
        dealt = _one(resp, "item_use")["damage"]
        assert dealt > 0
        assert saved["participants"][str(ATTACKER_PID)]["total_damage_dealt"] == dealt
        assert saved["participants"][str(DEFENDER_PID)]["total_damage_received"] == dealt

    def test_a_dodge_is_logged_once_and_deals_nothing(self):
        state = _state(fast_slots=[dict(self.SCROLL)])
        resp, _, _, saved = _run_turn(
            state, payload=_payload(item_id=50, target_id=DEFENDER_PID), dodge=True)
        ev = _one(resp, "damage")
        assert ev["dodged"] is True
        assert ev["final"] == 0
        assert ev["source_kind"] == "item"
        assert saved["participants"][str(DEFENDER_PID)]["hp"] == 100


# ══════════════════════════════════════════════════════════════════════════════
# Cleanse — including the unremovable full-skip control
# ══════════════════════════════════════════════════════════════════════════════

def _antidote(item_id=60, selector="debuff", limit=0, target_side="self"):
    return _slot(item_id=item_id, name="Противоядие", quantity=1,
                 consumable_action="cleanse",
                 effects=[_effect_row("Cleanse", attribute_key=selector,
                                      magnitude=limit, target_side=target_side)])


def _afflicted_effects():
    return {
        str(ATTACKER_PID): [
            {"name": "Bleeding", "attribute": "bleeding", "magnitude": 5,
             "duration": 3, "owner_id": DEFENDER_PID},
            {"name": "Curse", "attribute": "curse", "magnitude": 4,
             "duration": 2, "owner_id": DEFENDER_PID},
            {"name": "Stun", "attribute": "stun", "magnitude": 1,
             "duration": 5, "owner_id": DEFENDER_PID},
        ]
    }


class TestCleanse:

    def test_debuff_selector_strips_the_enemy_effects(self):
        # The actor is stunned in the fixture, so cleanse it from the ally slot
        # of a healthy actor instead: here the actor is the one afflicted, but
        # without the Stun.
        effects = {str(ATTACKER_PID): _afflicted_effects()[str(ATTACKER_PID)][:2]}
        state = _state(fast_slots=[_antidote()], active_effects=effects)
        resp, _, _, saved = _run_turn(state, payload=_payload(item_id=60))
        assert resp.status_code == 200
        assert _effects_of(saved, ATTACKER_PID) == []

    def test_effects_removed_event_carries_what_the_log_renders(self):
        effects = {str(ATTACKER_PID): _afflicted_effects()[str(ATTACKER_PID)][:2]}
        state = _state(fast_slots=[_antidote()], active_effects=effects)
        resp, _, _, _ = _run_turn(state, payload=_payload(item_id=60))
        ev = _one(resp, "effects_removed")
        assert ev["who"] == ATTACKER_PID
        assert ev["target"] == ATTACKER_PID
        assert ev["source"] == ATTACKER_PID
        assert ev["item_id"] == 60
        assert ev["item_name"] == "Противоядие"
        assert sorted(e["name"] for e in ev["removed"]) == ["Bleeding", "Curse"]

    def test_magnitude_acts_as_a_removal_limit(self):
        effects = {str(ATTACKER_PID): _afflicted_effects()[str(ATTACKER_PID)][:2]}
        state = _state(fast_slots=[_antidote(limit=1)], active_effects=effects)
        resp, _, _, saved = _run_turn(state, payload=_payload(item_id=60))
        assert len(_one(resp, "effects_removed")["removed"]) == 1
        assert len(_effects_of(saved, ATTACKER_PID)) == 1

    def test_periodic_damage_selector_leaves_the_stat_debuff(self):
        effects = {str(ATTACKER_PID): _afflicted_effects()[str(ATTACKER_PID)][:2]}
        state = _state(fast_slots=[_antidote(selector="periodic_damage")],
                       active_effects=effects)
        resp, _, _, saved = _run_turn(state, payload=_payload(item_id=60))
        assert [e["name"] for e in _one(resp, "effects_removed")["removed"]] == ["Bleeding"]
        assert [e["name"] for e in _effects_of(saved, ATTACKER_PID)] == ["Curse"]

    def test_a_stun_is_never_cleansed_not_even_by_all(self):
        """Engine rule (§3.2): a full skip-turn control is unremovable whatever
        the admin configures. The actor is stunned here, so the whole turn is
        skipped — but the important half is that the Stun is still in the state
        after a `selector="all"` antidote would have run."""
        state = _state(fast_slots=[_antidote(selector="all")],
                       active_effects=_afflicted_effects())
        resp, _, consume, saved = _run_turn(state, payload=_payload(item_id=60))
        assert resp.status_code == 200
        assert any(e["name"] == "Stun" for e in _effects_of(saved, ATTACKER_PID))

    def test_a_stun_on_the_enemy_survives_an_enemy_targeted_cleanse(self):
        """The unremovable rule is about the effect, not about who cleanses:
        cleansing an enemy with `all` still cannot free them from a Stun."""
        item = _antidote(item_id=61, selector="all", target_side="enemy")
        state = _state(
            fast_slots=[item],
            active_effects={str(DEFENDER_PID): [
                {"name": "Bleeding", "attribute": "bleeding", "magnitude": 5,
                 "duration": 3, "owner_id": ATTACKER_PID},
                {"name": "Stun", "attribute": "stun", "magnitude": 1,
                 "duration": 4, "owner_id": ATTACKER_PID},
            ]},
        )
        resp, _, _, saved = _run_turn(
            state, payload=_payload(item_id=61, target_id=DEFENDER_PID))
        assert resp.status_code == 200
        assert [e["name"] for e in _effects_of(saved, DEFENDER_PID)] == ["Stun"]

    def test_a_cleanse_that_removes_nothing_emits_no_event(self):
        state = _state(fast_slots=[_antidote()])
        resp, _, _, _ = _run_turn(state, payload=_payload(item_id=60))
        assert _events(resp, "effects_removed") == []
        assert _one(resp, "item_use")["removed"] == []


# ══════════════════════════════════════════════════════════════════════════════
# Weapon coating (poison)
# ══════════════════════════════════════════════════════════════════════════════

POISON = _slot(
    item_id=91, name="Яд гадюки", quantity=2,
    consumable_action="weapon_coating", coating_turns=4, coating_bonus_damage=12,
    effects=[_effect_row("Poison", attribute_key="periodic_damage",
                         magnitude=6, duration=3, target_side="enemy")],
)


def _coated(turns_left=4, bonus=12.0, effects=None, item_id=91):
    return {
        "item_id": item_id, "name": "Яд гадюки", "bonus_damage": bonus,
        "turns_left": turns_left,
        "effects": effects if effects is not None else [
            _effect_row("Poison", attribute_key="periodic_damage",
                        magnitude=6, duration=3, target_side="enemy")
        ],
    }


class TestWeaponCoatingApplication:

    def test_coating_is_stored_on_the_participant(self):
        state = _state(fast_slots=[dict(POISON)])
        resp, _, _, saved = _run_turn(state, payload=_payload(item_id=91))
        assert resp.status_code == 200
        coating = saved["participants"][str(ATTACKER_PID)]["weapon_coating"]
        assert coating["item_id"] == 91
        assert coating["name"] == "Яд гадюки"
        assert coating["bonus_damage"] == 12.0
        assert coating["turns_left"] == 3, \
            "the application turn counts — 4 turns, one of them spent applying"
        assert coating["effects"][0]["effect_name"] == "Poison"

    def test_coating_applied_event_payload(self):
        state = _state(fast_slots=[dict(POISON)])
        resp, _, _, _ = _run_turn(state, payload=_payload(item_id=91))
        ev = _one(resp, "weapon_coating_applied")
        assert ev["who"] == ATTACKER_PID
        assert ev["item_id"] == 91
        assert ev["item_name"] == "Яд гадюки"
        assert ev["turns"] == 4
        assert ev["bonus_damage"] == 12.0

    def test_the_enemy_rows_do_not_fire_on_the_application_turn(self):
        """A coating's enemy rows are what the *blade* inflicts on a hit — they
        must not be thrown at the target the moment the vial is opened."""
        state = _state(fast_slots=[dict(POISON)])
        resp, _, _, saved = _run_turn(
            state, payload=_payload(item_id=91, target_id=DEFENDER_PID))
        assert _effects_of(saved, DEFENDER_PID) == []

    def test_a_coating_without_turns_is_not_applied(self):
        broken = _slot(item_id=92, name="Плохой яд", quantity=1,
                       consumable_action="weapon_coating", coating_turns=0,
                       coating_bonus_damage=5)
        state = _state(fast_slots=[broken])
        resp, _, _, saved = _run_turn(state, payload=_payload(item_id=92))
        assert resp.status_code == 200
        assert "weapon_coating" not in saved["participants"][str(ATTACKER_PID)]
        assert _events(resp, "weapon_coating_applied") == []


class TestWeaponCoatingDamage:

    def test_bonus_is_folded_into_the_weapon_damage_entry(self):
        state = _state(attacker_over={"weapon_coating": _coated(turns_left=4)})
        resp, spy, _, _ = _run_turn(
            state,
            payload=_payload(attack_skill_id=1, target_id=DEFENDER_PID),
            attack_skill=_attack_skill([_damage_row(amount=10, damage_type="physical",
                                                    weapon_slot="main_weapon")]),
        )
        assert resp.status_code == 200
        assert spy.entries()[0]["amount"] == 22, \
            "the bonus must ride inside `amount` so it passes through buffs/crit/resist"

    def test_bonus_is_not_added_to_a_no_weapon_entry(self):
        state = _state(attacker_over={"weapon_coating": _coated(turns_left=4)})
        resp, spy, _, _ = _run_turn(
            state,
            payload=_payload(attack_skill_id=1, target_id=DEFENDER_PID),
            attack_skill=_attack_skill([_damage_row(amount=10, damage_type="fire",
                                                    weapon_slot="no_weapon")]),
        )
        assert resp.status_code == 200
        assert spy.entries()[0]["amount"] == 10

    def test_coating_effects_land_on_the_target_that_was_hit(self):
        state = _state(attacker_over={"weapon_coating": _coated(turns_left=4)})
        resp, _, _, saved = _run_turn(
            state,
            payload=_payload(attack_skill_id=1, target_id=DEFENDER_PID),
            attack_skill=_attack_skill([_damage_row(amount=10, damage_type="physical",
                                                    weapon_slot="main_weapon")]),
        )
        eff, = _effects_of(saved, DEFENDER_PID)
        assert eff["name"] == "Poison"
        assert eff["attribute"] == "periodic_damage"
        assert eff["magnitude"] == 6
        assert eff["owner_id"] == ATTACKER_PID
        assert eff["source"] == "item:91", \
            "repeat hits must refresh the poison, not stack a new one per swing"

    def test_coating_effects_do_not_land_when_the_target_dodged(self):
        state = _state(attacker_over={"weapon_coating": _coated(turns_left=4)})
        resp, _, _, saved = _run_turn(
            state,
            payload=_payload(attack_skill_id=1, target_id=DEFENDER_PID),
            attack_skill=_attack_skill([_damage_row(amount=10, damage_type="physical",
                                                    weapon_slot="main_weapon")]),
            dodge=True,
        )
        assert _effects_of(saved, DEFENDER_PID) == []

    def test_a_coating_applied_this_turn_already_boosts_this_turn_attack(self):
        """The item step (8) runs before the attack step (9)."""
        state = _state(fast_slots=[dict(POISON)])
        resp, spy, _, _ = _run_turn(
            state,
            payload=_payload(item_id=91, attack_skill_id=1, target_id=DEFENDER_PID),
            attack_skill=_attack_skill([_damage_row(amount=10, damage_type="physical",
                                                    weapon_slot="main_weapon")]),
        )
        assert resp.status_code == 200
        assert spy.entries()[0]["amount"] == 22

    def test_an_uncoated_weapon_gets_no_bonus(self):
        state = _state()
        resp, spy, _, _ = _run_turn(
            state,
            payload=_payload(attack_skill_id=1, target_id=DEFENDER_PID),
            attack_skill=_attack_skill([_damage_row(amount=10, damage_type="physical",
                                                    weapon_slot="main_weapon")]),
        )
        assert spy.entries()[0]["amount"] == 10


class TestWeaponCoatingLifecycle:

    def test_turns_left_decrements_on_the_owner_turn(self):
        state = _state(attacker_over={"weapon_coating": _coated(turns_left=3)})
        resp, _, _, saved = _run_turn(state)
        assert saved["participants"][str(ATTACKER_PID)]["weapon_coating"]["turns_left"] == 2

    def test_coating_expires_and_reports_it(self):
        state = _state(attacker_over={"weapon_coating": _coated(turns_left=1)})
        resp, _, _, saved = _run_turn(state)
        assert "weapon_coating" not in saved["participants"][str(ATTACKER_PID)]
        ev = _one(resp, "weapon_coating_expired")
        assert ev["who"] == ATTACKER_PID
        assert ev["item_id"] == 91
        assert ev["item_name"] == "Яд гадюки"

    def test_an_expired_coating_stops_boosting_damage(self):
        state = _state(attacker_over={"weapon_coating": _coated(turns_left=0)})
        resp, spy, _, _ = _run_turn(
            state,
            payload=_payload(attack_skill_id=1, target_id=DEFENDER_PID),
            attack_skill=_attack_skill([_damage_row(amount=10, damage_type="physical",
                                                    weapon_slot="main_weapon")]),
        )
        assert spy.entries()[0]["amount"] == 10


class TestSecondCoatingIsRejected:

    def test_item_rejected_event_and_no_consumption(self):
        slot = dict(POISON, item_id=93, name="Яд кобры", quantity=2)
        state = _state(fast_slots=[slot],
                       attacker_over={"weapon_coating": _coated(turns_left=3)})
        state["participants"][str(ATTACKER_PID)]["fast_slots"] = [slot]
        resp, _, consume, saved = _run_turn(state, payload=_payload(item_id=93))

        assert resp.status_code == 200, "a refused coating must NOT cost the player the turn"
        ev = _one(resp, "item_rejected")
        assert ev["who"] == ATTACKER_PID
        assert ev["item_id"] == 93
        assert ev["item_name"] == "Яд кобры"
        assert ev["reason"] == "coating_active"
        assert ev["active_coating"] == "Яд гадюки"
        assert ev["turns_left"] == 3

        consume.assert_not_called()
        slots = saved["participants"][str(ATTACKER_PID)]["fast_slots"]
        assert len(slots) == 1 and slots[0]["quantity"] == 2, \
            "the refused item must stay in the belt untouched"
        assert _events(resp, "item_use") == []

    def test_the_rest_of_the_turn_still_resolves(self):
        slot = dict(POISON, item_id=93, name="Яд кобры", quantity=2)
        state = _state(fast_slots=[slot],
                       attacker_over={"weapon_coating": _coated(turns_left=3)})
        state["participants"][str(ATTACKER_PID)]["fast_slots"] = [slot]
        resp, spy, _, saved = _run_turn(
            state,
            payload=_payload(item_id=93, attack_skill_id=1, target_id=DEFENDER_PID),
            attack_skill=_attack_skill([_damage_row(amount=10, damage_type="physical",
                                                    weapon_slot="main_weapon")]),
        )
        assert resp.status_code == 200
        assert _one(resp, "item_rejected")
        assert spy.calls, "the attack must still have been resolved"
        assert saved["participants"][str(DEFENDER_PID)]["hp"] < 100
        assert saved["participants"][str(ATTACKER_PID)]["weapon_coating"]["name"] \
            == "Яд гадюки", "the original coating stays"

    def test_an_expired_coating_no_longer_blocks_a_new_one(self):
        slot = dict(POISON, item_id=93, name="Яд кобры", quantity=1)
        state = _state(fast_slots=[slot],
                       attacker_over={"weapon_coating": _coated(turns_left=0)})
        state["participants"][str(ATTACKER_PID)]["fast_slots"] = [slot]
        resp, _, consume, saved = _run_turn(state, payload=_payload(item_id=93))
        assert _events(resp, "item_rejected") == []
        assert _one(resp, "weapon_coating_applied")["item_id"] == 93
        consume.assert_called_once_with(ATTACKER_CHAR, 93)
        assert saved["participants"][str(ATTACKER_PID)]["weapon_coating"]["item_id"] == 93


# ══════════════════════════════════════════════════════════════════════════════
# Stack bookkeeping and the item_use payload
# ══════════════════════════════════════════════════════════════════════════════

class TestStackBookkeeping:

    def test_quantity_is_decremented_by_one(self):
        potion = _slot(item_id=42, quantity=5, health_recovery=10,
                       effects=[_effect_row("StatModifier", attribute_key="agility",
                                            magnitude=3, duration=2)])
        state = _state(fast_slots=[potion], attacker_over={"hp": 50})
        state["participants"][str(ATTACKER_PID)]["fast_slots"] = [potion]
        resp, _, _, saved = _run_turn(state, payload=_payload(item_id=42))
        slots = saved["participants"][str(ATTACKER_PID)]["fast_slots"]
        assert len(slots) == 1
        assert slots[0]["quantity"] == 4
        assert _one(resp, "item_use")["quantity_left"] == 4

    def test_the_last_unit_frees_the_slot(self):
        potion = _slot(item_id=42, quantity=1, health_recovery=10)
        state = _state(fast_slots=[potion], attacker_over={"hp": 50})
        state["participants"][str(ATTACKER_PID)]["fast_slots"] = [potion]
        resp, _, _, saved = _run_turn(state, payload=_payload(item_id=42))
        assert saved["participants"][str(ATTACKER_PID)]["fast_slots"] == []
        assert _one(resp, "item_use")["quantity_left"] == 0

    def test_a_legacy_slot_without_quantity_behaves_as_before(self):
        """A belt snapshotted before FEAT-168 has no `quantity` key: one use,
        then the slot goes — exactly today's behaviour."""
        legacy = {"slot_type": "fast_slot_1", "item_id": 42,
                  "name": "Зелье", "image": "p.png", "health_recovery": 30}
        state = _state(attacker_over={"hp": 50, "fast_slots": [legacy]})
        resp, _, _, saved = _run_turn(state, payload=_payload(item_id=42))
        assert resp.status_code == 200
        assert saved["participants"][str(ATTACKER_PID)]["fast_slots"] == []
        assert saved["participants"][str(ATTACKER_PID)]["hp"] == 80

    def test_only_the_used_slot_is_touched(self):
        a = _slot(item_id=42, quantity=2, health_recovery=10)
        b = _slot(item_id=43, quantity=7, slot_type="fast_slot_2", mana_recovery=10)
        state = _state(attacker_over={"hp": 50, "fast_slots": [a, b]})
        resp, _, _, saved = _run_turn(state, payload=_payload(item_id=43))
        slots = {s["item_id"]: s for s in
                 saved["participants"][str(ATTACKER_PID)]["fast_slots"]}
        assert slots[42]["quantity"] == 2
        assert slots[43]["quantity"] == 6


class TestItemUsePayload:
    """The keys the battle log actually reads (`BattlePageBar.tsx` —
    `formatBattleEvent`, the `item_use` branch and its `BattleEvent` interface)."""

    EXPECTED_KEYS = {
        "event", "who", "item_id", "item_name", "recovery", "action",
        "effects", "removed", "damage", "quantity_left",
    }

    def test_payload_keys_are_exactly_what_the_frontend_reads(self):
        potion = _slot(item_id=42, quantity=2, health_recovery=10,
                       effects=[_effect_row("StatModifier", attribute_key="strength",
                                            magnitude=5, duration=3)])
        state = _state(attacker_over={"hp": 50, "fast_slots": [potion]})
        resp, _, _, _ = _run_turn(state, payload=_payload(item_id=42))
        ev = _one(resp, "item_use")
        assert set(ev) == self.EXPECTED_KEYS

    def test_recovery_includes_stamina(self):
        """ISSUES #6: stamina was applied by the engine but never logged."""
        potion = _slot(item_id=42, quantity=1, health_recovery=10, mana_recovery=5,
                       energy_recovery=4, stamina_recovery=3)
        state = _state(attacker_over={"hp": 50, "mana": 10, "energy": 10,
                                      "stamina": 10, "fast_slots": [potion]})
        resp, _, _, saved = _run_turn(state, payload=_payload(item_id=42))
        ev = _one(resp, "item_use")
        assert ev["recovery"] == {"health": 10, "mana": 5, "energy": 4, "stamina": 3}
        part = saved["participants"][str(ATTACKER_PID)]
        assert (part["hp"], part["mana"], part["energy"], part["stamina"]) == \
            (60, 15, 14, 13)

    def test_action_field_names_the_consumable_kind(self):
        state = _state(fast_slots=[dict(POISON)])
        resp, _, _, _ = _run_turn(state, payload=_payload(item_id=91))
        assert _one(resp, "item_use")["action"] == "weapon_coating"

    def test_action_defaults_to_instant_for_a_plain_potion(self):
        potion = _slot(item_id=42, quantity=1, health_recovery=10)
        state = _state(attacker_over={"hp": 50, "fast_slots": [potion]})
        resp, _, _, _ = _run_turn(state, payload=_payload(item_id=42))
        assert _one(resp, "item_use")["action"] == "instant"


# ══════════════════════════════════════════════════════════════════════════════
# Turn rules
# ══════════════════════════════════════════════════════════════════════════════

class TestTurnRules:

    def test_only_one_item_channel_exists_per_turn(self):
        """§3.4: the per-turn limit of one item is structural — a turn is one
        POST carrying one `item_id`. A second item channel would break it."""
        item_fields = [name for name in SkillSelection.__fields__ if "item" in name]
        assert item_fields == ["item_id"]

    def test_a_full_skip_control_nullifies_the_item(self):
        potion = _slot(item_id=42, quantity=3, health_recovery=30)
        state = _state(
            attacker_over={"hp": 50, "fast_slots": [potion]},
            active_effects={str(ATTACKER_PID): [
                {"name": "Stun", "attribute": "stun", "magnitude": 1,
                 "duration": 3, "owner_id": DEFENDER_PID}
            ]},
        )
        resp, _, consume, saved = _run_turn(state, payload=_payload(item_id=42))
        assert resp.status_code == 200
        assert _events(resp, "item_use") == []
        consume.assert_not_called()
        part = saved["participants"][str(ATTACKER_PID)]
        assert part["hp"] == 50, "a stunned player must not drink"
        assert part["fast_slots"][0]["quantity"] == 3

    def test_an_unknown_item_id_is_skipped_without_failing_the_turn(self):
        potion = _slot(item_id=42, quantity=1, health_recovery=30)
        state = _state(attacker_over={"hp": 50, "fast_slots": [potion]})
        resp, _, consume, saved = _run_turn(state, payload=_payload(item_id=999))
        assert resp.status_code == 200
        assert _events(resp, "item_use") == []
        consume.assert_not_called()
        assert saved["participants"][str(ATTACKER_PID)]["fast_slots"][0]["quantity"] == 1

    def test_a_failed_consume_still_applies_the_effect(self):
        """Deliberate "best effort" semantics, unchanged by FEAT-168."""
        potion = _slot(item_id=42, quantity=1,
                       effects=[_effect_row("StatModifier", attribute_key="strength",
                                            magnitude=5, duration=3)])
        state = _state(attacker_over={"fast_slots": [potion]})
        resp, _, _, saved = _run_turn(
            state, payload=_payload(item_id=42),
            consume_result={"status": "error", "detail": "not enough"},
        )
        assert resp.status_code == 200
        assert _effects_of(saved, ATTACKER_PID)[0]["magnitude"] == 5


# ══════════════════════════════════════════════════════════════════════════════
# The §3.0 compatibility contract: a pre-deploy Redis state completes a turn
# ══════════════════════════════════════════════════════════════════════════════

class TestPreDeployState:
    """Battle state lives in Redis for up to 48 h. A battle started before this
    deploy has NONE of the new keys — no `quantity`, no `effects`, no
    `damage_entries`, no `consumable_action`, no `coating_*`, no `weapon_coating`
    on the participant, and effect records without `owner_id` / `fresh` /
    `source`. This test fails the moment any new key is read without a default.
    """

    NEW_KEYS = ("consumable_action", "coating_turns", "coating_bonus_damage",
                "effects", "damage_entries", "quantity")

    def _legacy_state(self):
        legacy_slot = {
            "slot_type": "fast_slot_1", "item_id": 42,
            "name": "Зелье здоровья", "image": "potion.png",
            "health_recovery": 40, "mana_recovery": 0,
            "energy_recovery": 0, "stamina_recovery": 0,
        }
        legacy_participant = {
            "character_id": ATTACKER_CHAR, "team": 0,
            "hp": 40, "mana": 20, "energy": 30, "stamina": 30,
            "max_hp": 100, "max_mana": 100, "max_energy": 100, "max_stamina": 100,
            "cooldowns": {}, "fast_slots": [legacy_slot],
        }
        legacy_defender = dict(legacy_participant,
                               character_id=DEFENDER_CHAR, team=1, hp=100,
                               fast_slots=[])
        return {
            "turn_number": 2,
            "next_actor": ATTACKER_PID,
            "first_actor": ATTACKER_PID,
            "initiator_acted_once": True,
            "turn_order": [ATTACKER_PID, DEFENDER_PID],
            "total_turns": 1,
            "last_turn": None,
            "deadline_at": "2026-01-01T00:00:00",
            "participants": {str(ATTACKER_PID): legacy_participant,
                             str(DEFENDER_PID): legacy_defender},
            # Pre-FEAT-143 effect records: no owner_id, no fresh, no source.
            "active_effects": {str(DEFENDER_PID): [
                {"name": "Bleeding", "attribute": "bleeding",
                 "magnitude": 5, "duration": 2}
            ]},
        }

    def test_a_whole_turn_completes_and_behaves_exactly_as_before(self):
        state = self._legacy_state()
        resp, _, consume, saved = _run_turn(
            state,
            payload=_payload(item_id=42, attack_skill_id=1, target_id=DEFENDER_PID),
            attack_skill=_attack_skill([_damage_row(amount=10, damage_type="physical",
                                                    weapon_slot="main_weapon")]),
        )
        assert resp.status_code == 200, resp.text
        part = saved["participants"][str(ATTACKER_PID)]
        assert part["hp"] == 80, "recovery from the cached slot fields, as before"
        assert part["fast_slots"] == [], "one use, then the slot goes (legacy rule)"
        consume.assert_called_once_with(ATTACKER_CHAR, 42)

    def test_no_new_participant_key_is_invented_for_a_legacy_battle(self):
        state = self._legacy_state()
        _, _, _, saved = _run_turn(state, payload=_payload(item_id=42))
        assert "weapon_coating" not in saved["participants"][str(ATTACKER_PID)]

    def test_the_legacy_item_use_event_still_carries_the_new_fields_safely(self):
        state = self._legacy_state()
        resp, _, _, _ = _run_turn(state, payload=_payload(item_id=42))
        ev = _one(resp, "item_use")
        assert ev["recovery"] == {"health": 40}
        assert ev["action"] == "instant"
        assert ev["effects"] == [] and ev["removed"] == [] and ev["damage"] == 0
        assert ev["quantity_left"] == 0

    def test_a_legacy_effect_record_still_ticks_and_decays(self):
        state = self._legacy_state()
        state["active_effects"][str(DEFENDER_PID)][0]["owner_id"] = ATTACKER_PID
        resp, _, _, saved = _run_turn(state, payload=_payload(item_id=42))
        assert resp.status_code == 200
        tick = _events(resp, "effect_tick")
        assert tick and tick[0]["amount"] == 5
        assert _effects_of(saved, DEFENDER_PID)[0]["duration"] == 1

    def test_no_new_slot_key_is_required_to_read_a_legacy_slot(self):
        """Guard on the contract itself: the fixture must genuinely be missing
        every new key, otherwise this whole class proves nothing."""
        slot = self._legacy_state()["participants"][str(ATTACKER_PID)]["fast_slots"][0]
        for key in self.NEW_KEYS:
            assert key not in slot
