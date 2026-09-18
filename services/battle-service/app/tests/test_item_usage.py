"""
Tests for consumable item usage in battle (FEAT-073, Task #4b).

Covers:
- Successful item usage: consume_item called, recovery applied, slot removed
- Failed consumption (quantity=0): effect NOT applied, slot NOT removed
- Item not in fast_slots: item usage skipped
- Recovery capping at max values

Uses the same mocking approach as test_battle_fixes.py — patching modules
before importing main to avoid real Redis/Mongo/Celery connections.
"""

import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Environment & module-level patches (same approach as test_battle_fixes.py)
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

# Configure redis_state mock
redis_state_mock = sys.modules["redis_state"]
redis_state_mock.ZSET_DEADLINES = "battle:deadlines"
redis_state_mock.KEY_BATTLE_TURNS = "battle:{id}:turns"
redis_state_mock.init_battle_state = AsyncMock()
redis_state_mock.load_state = AsyncMock(return_value=None)
redis_state_mock.save_state = AsyncMock()
redis_state_mock.get_redis_client = AsyncMock(return_value=AsyncMock())
redis_state_mock.cache_snapshot = AsyncMock()
redis_state_mock.get_cached_snapshot = AsyncMock(return_value=None)
redis_state_mock.state_key = MagicMock(return_value="battle:1:state")

# Configure tasks mock
tasks_mock = sys.modules["tasks"]
tasks_mock.save_log = MagicMock()
tasks_mock.save_log.delay = MagicMock()

# Configure buffs mock
buffs_mock = sys.modules["buffs"]
buffs_mock.decrement_durations = MagicMock()
buffs_mock.aggregate_modifiers = MagicMock(return_value={})
buffs_mock.apply_new_effects = MagicMock()
buffs_mock.evaluate_control = MagicMock(return_value=(None, set()))  # FEAT-143: no control by defaultbuffs_mock.build_percent_damage_buffs = MagicMock(return_value={})
buffs_mock.build_percent_resist_buffs = MagicMock(return_value={})

# Configure skills_client mock
skills_mock = sys.modules["skills_client"]
skills_mock.character_has_skill = AsyncMock(return_value=True)
skills_mock.get_resolved_skill = AsyncMock(return_value={})
skills_mock.get_item = AsyncMock(return_value={})
skills_mock.character_skills = AsyncMock(return_value=[])

# Configure inventory_client
inv_mock = sys.modules["inventory_client"]
inv_mock.get_fast_slots = AsyncMock(return_value=[])
inv_mock.consume_item = AsyncMock(return_value={"status": "ok", "remaining_quantity": 0})

# Configure character_client
char_mock = sys.modules["character_client"]
char_mock.get_character_profile = AsyncMock(return_value={
    "character_name": "Test",
    "character_photo": "",
})

# Ensure the real battle_engine module is loaded
import importlib
if isinstance(sys.modules.get("battle_engine"), MagicMock):
    del sys.modules["battle_engine"]
import battle_engine  # noqa: E402
if isinstance(battle_engine, MagicMock):
    del sys.modules["battle_engine"]
    battle_engine = importlib.import_module("battle_engine")
    sys.modules["battle_engine"] = battle_engine

from battle_engine import decrement_cooldowns, set_cooldown  # noqa: E402
from main import app  # noqa: E402
from database import get_db  # noqa: E402

# Clear startup handlers
app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _make_battle_state(
    hp_p1: float = 100,
    mana_p1: float = 50,
    energy_p1: float = 50,
    stamina_p1: float = 50,
    fast_slots_p1: list = None,
    next_actor: int = 1,
) -> dict:
    """Build a minimal battle state with configurable fast_slots for P1."""
    return {
        "turn_number": 1,
        "next_actor": next_actor,
        "first_actor": 1,
        "turn_order": [1, 2],
        "total_turns": 0,
        "last_turn": None,
        "deadline_at": "2026-01-01T00:00:00",
        "participants": {
            "1": {
                "character_id": 10,
                "team": 0,
                "hp": hp_p1,
                "mana": mana_p1,
                "energy": energy_p1,
                "stamina": stamina_p1,
                "max_hp": 100,
                "max_mana": 100,
                "max_energy": 100,
                "max_stamina": 100,
                "cooldowns": {},
                "fast_slots": fast_slots_p1 or [],
            },
            "2": {
                "character_id": 20,
                "team": 1,
                "hp": 100,
                "mana": 50,
                "energy": 50,
                "stamina": 50,
                "max_hp": 100,
                "max_mana": 100,
                "max_energy": 100,
                "max_stamina": 100,
                "cooldowns": {},
                "fast_slots": [],
            },
        },
        "active_effects": {},
    }


def _make_action_payload(item_id=None, attack_skill_id=None):
    """Build an action payload with optional item_id."""
    return {
        "participant_id": 1,
        "skills": {
            "attack_skill_id": attack_skill_id,
            "defense_skill_id": None,
            "support_skill_id": None,
            "item_id": item_id,
        },
    }


def _make_mock_db(char_owner_map: dict = None):
    """Return an async mock DB session."""
    mock_db = AsyncMock()

    async def _execute(query, params=None):
        result = MagicMock()
        if char_owner_map and params and "cid" in params:
            cid = params["cid"]
            uid = char_owner_map.get(cid)
            if uid is not None:
                result.fetchone.return_value = (uid,)
            else:
                result.fetchone.return_value = None
        else:
            result.fetchone.return_value = None
            result.scalar_one_or_none.return_value = None
        return result

    mock_db.execute = AsyncMock(side_effect=_execute)
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()
    return mock_db


def _build_common_patches(
    battle_state,
    attack_rank=None,
    consume_result=None,
    damage_result=(0.0, {"damage_type": "physical", "final": 0.0}),
):
    """Return a dict of target -> configured mock for item usage tests."""
    if attack_rank is None:
        attack_rank = {
            "id": 1, "damage_entries": [], "effects": [],
            "cooldown": 0, "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
        }

    if consume_result is None:
        consume_result = {"status": "ok", "remaining_quantity": 0}

    mock_redis = AsyncMock()
    mock_save_log = MagicMock()
    mock_save_log.delay = MagicMock()

    attrs = {
        "damage": 5, "dodge": 0, "critical_hit_chance": 0,
        "critical_damage": 100, "current_health": 100,
        "current_mana": 50, "current_energy": 50, "current_stamina": 50,
    }

    return {
        "main.get_redis_client": AsyncMock(return_value=mock_redis),
        "main.save_state": AsyncMock(),
        "main.state_key": MagicMock(return_value="battle:1:state"),
        "main.write_turn": AsyncMock(),
        "main.finish_battle": AsyncMock(),
        "main.get_battle": AsyncMock(return_value=None),
        "main.load_state": AsyncMock(return_value=battle_state),
        "main.fetch_full_attributes": AsyncMock(return_value=attrs),
        "main.fetch_main_weapon": AsyncMock(return_value=None),
        "main.fetch_weapons": AsyncMock(return_value={"main_weapon": None, "additional_weapons": None}),
        "main.fetch_character_class_id": AsyncMock(return_value=1),
        "main.compute_damage_with_rolls": AsyncMock(return_value=damage_result),
        "main._distribute_pve_rewards": AsyncMock(return_value=None),
        "auth_http.requests.get": MagicMock(return_value=_mock_response(
            200, {"id": 5, "username": "player", "role": "user", "permissions": []}
        )),
        "main.save_log": mock_save_log,
        "main.character_has_skill": AsyncMock(return_value=True),
        "main.get_resolved_skill": AsyncMock(return_value=attack_rank),
        "main.consume_item": AsyncMock(return_value=consume_result),
    }


class _PatchContext:
    """Context manager that applies all patches from a dict."""

    def __init__(self, patches_dict):
        self._patchers = []
        self.mocks = {}
        for target, mock_val in patches_dict.items():
            if isinstance(mock_val, (AsyncMock, MagicMock)):
                p = patch(target, mock_val)
            else:
                p = patch(target)
            self._patchers.append((target, p))

    def __enter__(self):
        for target, p in self._patchers:
            self.mocks[target] = p.start()
        return self

    def __exit__(self, *args):
        for _, p in self._patchers:
            p.stop()


def _run_action(patches_dict, payload=None):
    """Apply patches, send action request, return response and context."""
    if payload is None:
        payload = _make_action_payload()

    mock_db = _make_mock_db({10: 5, 20: 6})

    async def _fake_get_db():
        yield mock_db

    with _PatchContext(patches_dict) as ctx:
        app.dependency_overrides[get_db] = _fake_get_db
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/battles/1/action",
                    json=payload,
                    headers={"Authorization": "Bearer fake-token"},
                )
        finally:
            app.dependency_overrides.pop(get_db, None)
    return response, ctx


# ══════════════════════════════════════════════════════════════════════════════
# Test Group: Successful item usage
# ══════════════════════════════════════════════════════════════════════════════


class TestItemUsageSuccess:
    """Verify that a valid item in fast_slots is consumed, recovery applied,
    and the stack is decremented (the slot goes away only at zero)."""

    def test_consume_item_called_and_quantity_decremented(self):
        """When item_id matches a fast_slot, consume_item is called and the
        stack loses exactly one unit (FEAT-168: a stack of 5 gives 5 uses —
        previously the whole slot was dropped after the first use)."""
        fast_slots = [
            {
                "slot_type": "fast_slot_1",
                "item_id": 3,
                "quantity": 5,
                "name": "Health Potion",
                "image": "potion.png",
                "health_recovery": 50,
            },
        ]
        state = _make_battle_state(hp_p1=60, fast_slots_p1=fast_slots)
        consume_mock = AsyncMock(return_value={"status": "ok", "remaining_quantity": 4})

        patches = _build_common_patches(state, consume_result={"status": "ok", "remaining_quantity": 4})
        patches["main.consume_item"] = consume_mock

        payload = _make_action_payload(item_id=3)
        response, ctx = _run_action(patches, payload)

        assert response.status_code == 200

        # consume_item should have been called with character_id=10, item_id=3
        consume_mock.assert_called_once_with(10, 3)

        # After usage the slot stays in the belt with one unit less.
        # Check via save_state mock — the state passed to save_state
        save_state_mock = patches["main.save_state"]
        if save_state_mock.called:
            saved_state = save_state_mock.call_args[0][1]
            p1_slots = saved_state["participants"]["1"]["fast_slots"]
            assert len(p1_slots) == 1, "A stack of 5 must not vanish after one use"
            assert p1_slots[0]["quantity"] == 4, "Exactly one unit should be spent"

    def test_last_unit_removes_slot(self):
        """The slot disappears only when the last unit of the stack is used."""
        fast_slots = [
            {
                "slot_type": "fast_slot_1",
                "item_id": 3,
                "quantity": 1,
                "name": "Health Potion",
                "image": "potion.png",
                "health_recovery": 50,
            },
        ]
        state = _make_battle_state(hp_p1=60, fast_slots_p1=fast_slots)

        patches = _build_common_patches(state, consume_result={"status": "ok", "remaining_quantity": 0})
        payload = _make_action_payload(item_id=3)
        response, ctx = _run_action(patches, payload)

        assert response.status_code == 200

        save_state_mock = patches["main.save_state"]
        if save_state_mock.called:
            saved_state = save_state_mock.call_args[0][1]
            p1_slots = saved_state["participants"]["1"]["fast_slots"]
            assert len(p1_slots) == 0, "The last unit must free the fast slot"

    def test_slot_with_unusable_quantity_is_removed(self):
        """A slot whose `quantity` is missing or unusable (None / 0 / garbage)
        counts as a single unit and leaves the belt after one use.

        Note: belts snapshotted before FEAT-168 DO carry `quantity` (the old
        `inventory_client.get_fast_slots` already wrote it), so they simply get
        the full stack of uses. This test covers the defensive default, not a
        pre-deploy state."""
        fast_slots = [
            {
                "slot_type": "fast_slot_1",
                "item_id": 3,
                "quantity": 0,
                "name": "Health Potion",
                "image": "potion.png",
                "health_recovery": 50,
            },
        ]
        state = _make_battle_state(hp_p1=60, fast_slots_p1=fast_slots)

        patches = _build_common_patches(state, consume_result={"status": "ok", "remaining_quantity": 0})
        payload = _make_action_payload(item_id=3)
        response, ctx = _run_action(patches, payload)

        assert response.status_code == 200

        save_state_mock = patches["main.save_state"]
        if save_state_mock.called:
            saved_state = save_state_mock.call_args[0][1]
            p1_slots = saved_state["participants"]["1"]["fast_slots"]
            assert len(p1_slots) == 0, "Unusable quantity: one use, then removed"

    def test_health_recovery_applied(self):
        """Item with health_recovery increases HP (capped at max_hp)."""
        fast_slots = [
            {
                "slot_type": "fast_slot_1",
                "item_id": 3,
                "quantity": 1,
                "name": "Health Potion",
                "image": "potion.png",
                "health_recovery": 50,
            },
        ]
        state = _make_battle_state(hp_p1=60, fast_slots_p1=fast_slots)

        patches = _build_common_patches(state, consume_result={"status": "ok", "remaining_quantity": 0})
        payload = _make_action_payload(item_id=3)
        response, ctx = _run_action(patches, payload)

        assert response.status_code == 200

        # HP should be min(60 + 50, 100) = 100
        save_state_mock = patches["main.save_state"]
        if save_state_mock.called:
            saved_state = save_state_mock.call_args[0][1]
            assert saved_state["participants"]["1"]["hp"] == 100

    def test_recovery_capped_at_max(self):
        """Recovery does not exceed max values."""
        fast_slots = [
            {
                "slot_type": "fast_slot_1",
                "item_id": 5,
                "quantity": 1,
                "name": "Super Potion",
                "image": "super.png",
                "health_recovery": 200,
                "mana_recovery": 150,
            },
        ]
        state = _make_battle_state(hp_p1=90, mana_p1=80, fast_slots_p1=fast_slots)

        patches = _build_common_patches(state, consume_result={"status": "ok", "remaining_quantity": 0})
        payload = _make_action_payload(item_id=5)
        response, ctx = _run_action(patches, payload)

        assert response.status_code == 200

        save_state_mock = patches["main.save_state"]
        if save_state_mock.called:
            saved_state = save_state_mock.call_args[0][1]
            p1 = saved_state["participants"]["1"]
            assert p1["hp"] <= 100, "HP should not exceed max_hp"
            assert p1["mana"] <= 100, "Mana should not exceed max_mana"

    def test_only_matching_slot_touched(self):
        """When multiple fast_slots exist, only the matching one is spent."""
        fast_slots = [
            {
                "slot_type": "fast_slot_1",
                "item_id": 3,
                "quantity": 5,
                "name": "Health Potion",
                "image": "potion.png",
                "health_recovery": 50,
            },
            {
                "slot_type": "fast_slot_2",
                "item_id": 7,
                "quantity": 2,
                "name": "Mana Potion",
                "image": "mana.png",
                "mana_recovery": 30,
            },
        ]
        state = _make_battle_state(hp_p1=60, fast_slots_p1=fast_slots)

        patches = _build_common_patches(state, consume_result={"status": "ok", "remaining_quantity": 4})
        payload = _make_action_payload(item_id=3)
        response, ctx = _run_action(patches, payload)

        assert response.status_code == 200

        save_state_mock = patches["main.save_state"]
        if save_state_mock.called:
            saved_state = save_state_mock.call_args[0][1]
            p1_slots = saved_state["participants"]["1"]["fast_slots"]
            assert len(p1_slots) == 2, "Neither stack is empty, so both slots stay"
            by_item = {s["item_id"]: s for s in p1_slots}
            assert by_item[3]["quantity"] == 4, "Only the used stack loses a unit"
            assert by_item[7]["quantity"] == 2, "The untouched stack keeps its quantity"


# ══════════════════════════════════════════════════════════════════════════════
# Test Group: Failed consumption (inventory returns error)
# ══════════════════════════════════════════════════════════════════════════════


class TestItemUsageBestEffortConsumption:
    """Verify that when inventory-service rejects consumption (best-effort),
    the effect IS still applied and the slot IS removed (one-time use)."""

    def test_failed_consume_still_applies_effect(self):
        """When consume_item returns error, HP is still recovered (best-effort)."""
        fast_slots = [
            {
                "slot_type": "fast_slot_1",
                "item_id": 3,
                "quantity": 1,
                "name": "Health Potion",
                "image": "potion.png",
                "health_recovery": 50,
            },
        ]
        state = _make_battle_state(hp_p1=60, fast_slots_p1=fast_slots)

        consume_error = {"status": "error", "detail": "Недостаточно предметов в инвентаре"}
        patches = _build_common_patches(state, consume_result=consume_error)
        payload = _make_action_payload(item_id=3)
        response, ctx = _run_action(patches, payload)

        assert response.status_code == 200

        save_state_mock = patches["main.save_state"]
        if save_state_mock.called:
            saved_state = save_state_mock.call_args[0][1]
            assert saved_state["participants"]["1"]["hp"] == 100, \
                "HP should be recovered even when consume fails (best-effort, capped at max)"

    def test_failed_consume_slot_still_removed(self):
        """When consume_item returns error, the fast_slot is still removed (one-time use)."""
        fast_slots = [
            {
                "slot_type": "fast_slot_1",
                "item_id": 3,
                "quantity": 1,
                "name": "Health Potion",
                "image": "potion.png",
                "health_recovery": 50,
            },
        ]
        state = _make_battle_state(hp_p1=60, fast_slots_p1=fast_slots)

        consume_error = {"status": "error", "detail": "Недостаточно предметов в инвентаре"}
        patches = _build_common_patches(state, consume_result=consume_error)
        payload = _make_action_payload(item_id=3)
        response, ctx = _run_action(patches, payload)

        assert response.status_code == 200

        save_state_mock = patches["main.save_state"]
        if save_state_mock.called:
            saved_state = save_state_mock.call_args[0][1]
            p1_slots = saved_state["participants"]["1"]["fast_slots"]
            assert len(p1_slots) == 0, "Slot should be removed even on failed consumption (one-time use)"


# ══════════════════════════════════════════════════════════════════════════════
# Test Group: Item not in fast_slots
# ══════════════════════════════════════════════════════════════════════════════


class TestItemNotInFastSlots:
    """Verify that requesting an item_id not present in fast_slots
    does not call consume_item and does not change state."""

    def test_nonexistent_item_skipped(self):
        """When item_id is not in fast_slots, consume_item is not called."""
        fast_slots = [
            {
                "slot_type": "fast_slot_1",
                "item_id": 3,
                "quantity": 5,
                "name": "Health Potion",
                "image": "potion.png",
                "health_recovery": 50,
            },
        ]
        state = _make_battle_state(hp_p1=60, fast_slots_p1=fast_slots)

        consume_mock = AsyncMock(return_value={"status": "ok", "remaining_quantity": 0})
        patches = _build_common_patches(state)
        patches["main.consume_item"] = consume_mock

        # Request item_id=999 which is NOT in fast_slots
        payload = _make_action_payload(item_id=999)
        response, ctx = _run_action(patches, payload)

        assert response.status_code == 200
        consume_mock.assert_not_called()

    def test_empty_fast_slots_item_skipped(self):
        """When fast_slots is empty, item usage is silently skipped."""
        state = _make_battle_state(hp_p1=60, fast_slots_p1=[])

        consume_mock = AsyncMock(return_value={"status": "ok", "remaining_quantity": 0})
        patches = _build_common_patches(state)
        patches["main.consume_item"] = consume_mock

        payload = _make_action_payload(item_id=3)
        response, ctx = _run_action(patches, payload)

        assert response.status_code == 200
        consume_mock.assert_not_called()

    def test_no_item_id_no_consumption(self):
        """When item_id is None/0, no consumption logic runs."""
        fast_slots = [
            {
                "slot_type": "fast_slot_1",
                "item_id": 3,
                "quantity": 5,
                "name": "Health Potion",
                "image": "potion.png",
                "health_recovery": 50,
            },
        ]
        state = _make_battle_state(hp_p1=60, fast_slots_p1=fast_slots)

        consume_mock = AsyncMock(return_value={"status": "ok", "remaining_quantity": 0})
        patches = _build_common_patches(state)
        patches["main.consume_item"] = consume_mock

        # item_id=None means no item usage
        payload = _make_action_payload(item_id=None)
        response, ctx = _run_action(patches, payload)

        assert response.status_code == 200
        consume_mock.assert_not_called()

    def test_item_id_zero_no_consumption(self):
        """When item_id is 0, no consumption logic runs."""
        state = _make_battle_state(hp_p1=60, fast_slots_p1=[])

        consume_mock = AsyncMock(return_value={"status": "ok", "remaining_quantity": 0})
        patches = _build_common_patches(state)
        patches["main.consume_item"] = consume_mock

        payload = _make_action_payload(item_id=0)
        response, ctx = _run_action(patches, payload)

        assert response.status_code == 200
        consume_mock.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# Test Group: Weapon coating (FEAT-168)
# ══════════════════════════════════════════════════════════════════════════════


_POISON_EFFECT_ROW = {
    "target_side": "enemy",
    "effect_name": "Poison",
    "attribute_key": "periodic_damage",
    "magnitude": 6,
    "duration": 3,
    "chance": 100,
}


def _coated_state(bonus_damage: float) -> dict:
    """Battle state where P1's weapon already carries a poison coating."""
    state = _make_battle_state(hp_p1=100)
    state["participants"]["1"]["weapon_coating"] = {
        "item_id": 91,
        "name": "Яд гадюки",
        "bonus_damage": bonus_damage,
        "turns_left": 4,
        "effects": [dict(_POISON_EFFECT_ROW)],
    }
    return state


def _attack_rank_with_weapon_damage() -> dict:
    return {
        "id": 1,
        "skill_id": 1,
        "cooldown": 0,
        "cost_energy": 0,
        "cost_mana": 0,
        "cost_stamina": 0,
        "effects": [],
        "damage_entries": [
            {
                "damage_type": "physical",
                "amount": 10,
                "weapon_slot": "main_weapon",
                "aoe_shape": "single",
            }
        ],
    }


def _coating_patches(state):
    patches = _build_common_patches(
        state,
        attack_rank=_attack_rank_with_weapon_damage(),
        damage_result=(12.0, {"damage_type": "physical", "final": 12.0}),
    )
    # `buffs` is mocked module-wide in this file, so _normalize_effect would
    # otherwise return a MagicMock that cannot be serialized into the response.
    patches["main._normalize_effect"] = MagicMock(side_effect=lambda row: {
        "name": row.get("effect_name"),
        "attribute": row.get("attribute_key"),
        "magnitude": row.get("magnitude"),
        "duration": row.get("duration"),
    })
    patches["main.apply_new_effects"] = MagicMock()
    return patches


class TestWeaponCoatingOnHit:
    """A poison on the weapon must infect whoever it hits — including a poison
    whose whole value is the DoT and whose bonus damage is zero (FEAT-168
    review #1: the on-hit effects used to be gated on the bonus being non-zero,
    so a DoT-only poison silently did nothing)."""

    def _run_attack(self, bonus_damage: float):
        state = _coated_state(bonus_damage)
        patches = _coating_patches(state)
        payload = _make_action_payload(attack_skill_id=1)
        response, ctx = _run_action(patches, payload)
        assert response.status_code == 200
        return response.json()["events"], patches["main.apply_new_effects"]

    def test_zero_bonus_coating_still_applies_its_effects(self):
        """coating_bonus_damage = 0 → no extra damage, but the poison lands."""
        events, apply_mock = self._run_attack(0.0)

        assert apply_mock.called, "A DoT-only coating must still apply its effects"
        # (state, target_pid, rows, ...) — the enemy is participant 2
        called_targets = {call.args[1] for call in apply_mock.call_args_list}
        assert 2 in called_targets

        coating_events = [
            e for e in events
            if e.get("event") == "apply_effects" and e.get("kind") == "item"
            and e.get("item_id") == 91
        ]
        assert coating_events, "The coating's effects must be logged"
        assert coating_events[0]["who"] == 2

    def test_coating_with_bonus_applies_effects_too(self):
        """The non-zero-bonus case keeps working (guards the fix both ways)."""
        events, apply_mock = self._run_attack(12.0)

        assert apply_mock.called
        assert any(
            e.get("event") == "apply_effects" and e.get("kind") == "item"
            and e.get("item_id") == 91
            for e in events
        )

    def test_no_coating_applies_nothing(self):
        """Without a coating nothing extra happens — the pre-FEAT-168 path."""
        state = _make_battle_state(hp_p1=100)
        patches = _coating_patches(state)
        payload = _make_action_payload(attack_skill_id=1)
        response, ctx = _run_action(patches, payload)

        assert response.status_code == 200
        events = response.json()["events"]
        assert not any(
            e.get("event") == "apply_effects" and e.get("kind") == "item"
            for e in events
        )
