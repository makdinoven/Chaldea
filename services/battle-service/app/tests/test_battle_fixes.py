"""
Tests for battle bug fixes (FEAT-059, Tasks #1-#3):
  1. HP<=0 ends battle
  2. Cooldowns decrement correctly
  3. Enemy effects not duplicated

Uses the same mocking approach as test_endpoint_auth.py — patching modules
before importing main to avoid real Redis/Mongo/Celery connections.
"""

import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Environment & module-level patches (same approach as test_endpoint_auth.py)
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
buffs_mock.build_percent_damage_buffs = MagicMock(return_value={})
buffs_mock.build_percent_resist_buffs = MagicMock(return_value={})

# Configure skills_client mock
skills_mock = sys.modules["skills_client"]
skills_mock.character_has_rank = AsyncMock(return_value=True)
skills_mock.get_rank = AsyncMock(return_value={})
skills_mock.get_item = AsyncMock(return_value={})
skills_mock.character_ranks = AsyncMock(return_value=[])

# Configure mongo_helpers
mongo_mock = sys.modules["mongo_helpers"]
mongo_mock.save_snapshot = AsyncMock()
mongo_mock.load_snapshot = AsyncMock(return_value=None)

# Configure inventory_client
inv_mock = sys.modules["inventory_client"]
inv_mock.get_fast_slots = AsyncMock(return_value=[])

# Configure character_client
char_mock = sys.modules["character_client"]
char_mock.get_character_profile = AsyncMock(return_value={
    "character_name": "Test",
    "character_photo": "",
})

# Ensure the real battle_engine module is loaded (other test files may have
# replaced it with a MagicMock in sys.modules during collection).
import importlib
if isinstance(sys.modules.get("battle_engine"), MagicMock):
    # Remove the mock so importlib can load the real module
    del sys.modules["battle_engine"]
import battle_engine  # noqa: E402
if isinstance(battle_engine, MagicMock):
    # Fallback: force-reload the real module
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
    hp_p2: float = 100,
    next_actor: int = 1,
    cooldowns_p1: dict = None,
    cooldowns_p2: dict = None,
    active_effects: dict = None,
) -> dict:
    """Build a minimal battle state dict for two participants."""
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
                "mana": 50,
                "energy": 50,
                "stamina": 50,
                "max_hp": 100,
                "max_mana": 100,
                "max_energy": 100,
                "max_stamina": 100,
                "cooldowns": cooldowns_p1 or {},
                "fast_slots": [],
            },
            "2": {
                "character_id": 20,
                "team": 1,
                "hp": hp_p2,
                "mana": 50,
                "energy": 50,
                "stamina": 50,
                "max_hp": 100,
                "max_mana": 100,
                "max_energy": 100,
                "max_stamina": 100,
                "cooldowns": cooldowns_p2 or {},
                "fast_slots": [],
            },
        },
        "active_effects": active_effects or {},
    }


ACTION_PAYLOAD = {
    "participant_id": 1,
    "skills": {
        "attack_rank_id": 1,
        "defense_rank_id": None,
        "support_rank_id": None,
        "item_id": None,
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


# All patches that every action-endpoint test needs.
# main.py imports symbols directly, so we must patch them on "main.*".
_COMMON_PATCHES = [
    # Redis-related (imported from redis_state)
    ("main.get_redis_client", AsyncMock),
    ("main.save_state", AsyncMock),
    ("main.state_key", None),  # regular MagicMock
    # CRUD (imported from crud)
    ("main.write_turn", AsyncMock),
    ("main.finish_battle", AsyncMock),
    ("main.get_battle", AsyncMock),
    # State loader (imported from redis_state)
    ("main.load_state", AsyncMock),
    # Engine helpers (imported from battle_engine)
    ("main.fetch_full_attributes", AsyncMock),
    ("main.fetch_main_weapon", AsyncMock),
    ("main.fetch_character_class_id", AsyncMock),
    ("main.compute_damage_with_rolls", AsyncMock),
    # PvE rewards
    ("main._distribute_pve_rewards", AsyncMock),
    # Auth
    ("auth_http.requests.get", None),
    # Celery task
    ("main.save_log", None),
]


def _build_common_patches(
    battle_state,
    attack_rank,
    damage_result=(5.0, {"damage_type": "physical", "final": 5.0}),
    battle_finished_in_db=False,
):
    """Return a dict of target -> configured mock for a standard action test."""
    mock_redis = AsyncMock()

    mock_battle = None
    if battle_finished_in_db:
        mock_battle = MagicMock()
        mock_battle.status = MagicMock()
        mock_battle.status.value = "finished"

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
        "main.get_battle": AsyncMock(return_value=mock_battle),
        "main.load_state": AsyncMock(return_value=battle_state),
        "main.fetch_full_attributes": AsyncMock(return_value=attrs),
        "main.fetch_main_weapon": AsyncMock(return_value=None),
        "main.fetch_character_class_id": AsyncMock(return_value=1),
        "main.compute_damage_with_rolls": AsyncMock(return_value=damage_result),
        "main._distribute_pve_rewards": AsyncMock(return_value=None),
        "auth_http.requests.get": MagicMock(return_value=_mock_response(
            200, {"id": 5, "username": "player", "role": "user", "permissions": []}
        )),
        "main.save_log": mock_save_log,
        "main.character_has_rank": AsyncMock(return_value=True),
        "main.get_rank": AsyncMock(return_value=attack_rank),
    }


class _PatchContext:
    """Context manager that applies all patches from a dict."""

    def __init__(self, patches_dict):
        self._patchers = []
        self.mocks = {}
        for target, mock_val in patches_dict.items():
            if isinstance(mock_val, AsyncMock) or isinstance(mock_val, MagicMock):
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
    """Apply patches, send action request, return response."""
    if payload is None:
        payload = ACTION_PAYLOAD

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
# Test Group 1: HP<=0 ends battle (Task #1)
# ══════════════════════════════════════════════════════════════════════════════


class TestBattleEndsOnHpZero:
    """Verify that when a participant's HP drops to 0 or below,
    the battle finishes with battle_finished=True and winner_team set."""

    def test_hp_zero_finishes_battle(self):
        """When defender HP drops to 0, response includes battle_finished=True."""
        state = _make_battle_state(hp_p1=100, hp_p2=5)
        attack_rank = {
            "id": 1,
            "damage_entries": [
                {"damage_type": "physical", "amount": 10, "chance": 100}
            ],
            "effects": [],
            "cooldown": 0,
            "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
        }
        patches = _build_common_patches(
            state, attack_rank,
            damage_result=(10.0, {"damage_type": "physical", "final": 10.0}),
        )
        response, ctx = _run_action(patches)
        assert response.status_code == 200
        data = response.json()
        assert data["battle_finished"] is True
        assert data["winner_team"] == 0  # attacker's team

    def test_hp_negative_finishes_battle(self):
        """When defender HP drops below 0 (overkill), battle still finishes."""
        state = _make_battle_state(hp_p1=100, hp_p2=3)
        attack_rank = {
            "id": 1,
            "damage_entries": [
                {"damage_type": "physical", "amount": 10, "chance": 100}
            ],
            "effects": [],
            "cooldown": 0,
            "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
        }
        patches = _build_common_patches(
            state, attack_rank,
            damage_result=(50.0, {"damage_type": "physical", "final": 50.0}),
        )
        response, _ = _run_action(patches)
        assert response.status_code == 200
        data = response.json()
        assert data["battle_finished"] is True
        assert data["winner_team"] == 0

    def test_finished_battle_returns_400(self):
        """Attempting an action on a finished battle returns 400."""
        state = _make_battle_state()
        attack_rank = {
            "id": 1, "damage_entries": [], "effects": [],
            "cooldown": 0, "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
        }
        patches = _build_common_patches(
            state, attack_rank, battle_finished_in_db=True,
        )
        response, _ = _run_action(patches)
        assert response.status_code == 400

    def test_no_damage_no_finish(self):
        """When HP stays above 0, battle continues (battle_finished is None)."""
        state = _make_battle_state(hp_p1=100, hp_p2=100)
        attack_rank = {
            "id": 1,
            "damage_entries": [
                {"damage_type": "physical", "amount": 5, "chance": 100}
            ],
            "effects": [],
            "cooldown": 0,
            "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
        }
        patches = _build_common_patches(
            state, attack_rank,
            damage_result=(5.0, {"damage_type": "physical", "final": 5.0}),
        )
        response, _ = _run_action(patches)
        assert response.status_code == 200
        data = response.json()
        assert data.get("battle_finished") is None
        assert data.get("winner_team") is None

    def test_participant_defeated_event_in_events(self):
        """When battle finishes, events list includes 'participant_defeated'
        and 'battle_finished' events."""
        state = _make_battle_state(hp_p1=100, hp_p2=1)
        attack_rank = {
            "id": 1,
            "damage_entries": [
                {"damage_type": "physical", "amount": 5, "chance": 100}
            ],
            "effects": [],
            "cooldown": 0,
            "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
        }
        patches = _build_common_patches(
            state, attack_rank,
            damage_result=(5.0, {"damage_type": "physical", "final": 5.0}),
        )
        response, _ = _run_action(patches)
        assert response.status_code == 200
        events = response.json()["events"]
        event_types = [e["event"] for e in events]
        assert "participant_defeated" in event_types
        assert "battle_finished" in event_types


# ══════════════════════════════════════════════════════════════════════════════
# Test Group 2: Cooldown decrement (Task #2)
# ══════════════════════════════════════════════════════════════════════════════


class TestCooldownDecrement:
    """Verify that decrement_cooldowns properly reduces cooldowns
    and removes them when they reach 0."""

    def test_cooldowns_decrement_by_one(self):
        """Each call to decrement_cooldowns reduces values by 1."""
        state = _make_battle_state(
            cooldowns_p1={"10": 3, "20": 1},
            cooldowns_p2={"30": 2},
        )
        decrement_cooldowns(state)

        assert state["participants"]["1"]["cooldowns"]["10"] == 2
        assert "20" not in state["participants"]["1"]["cooldowns"]
        assert state["participants"]["2"]["cooldowns"]["30"] == 1

    def test_cooldowns_removed_at_zero(self):
        """Cooldowns reaching 0 are removed from the dict entirely."""
        state = _make_battle_state(
            cooldowns_p1={"10": 1, "20": 1},
        )
        decrement_cooldowns(state)
        assert state["participants"]["1"]["cooldowns"] == {}

    def test_multiple_decrements(self):
        """Successive calls correctly decrement each time."""
        state = _make_battle_state(cooldowns_p1={"10": 3})

        decrement_cooldowns(state)
        assert state["participants"]["1"]["cooldowns"]["10"] == 2

        decrement_cooldowns(state)
        assert state["participants"]["1"]["cooldowns"]["10"] == 1

        decrement_cooldowns(state)
        assert state["participants"]["1"]["cooldowns"] == {}

    def test_empty_cooldowns_no_error(self):
        """Decrementing with no cooldowns does not raise."""
        state = _make_battle_state()
        decrement_cooldowns(state)
        assert state["participants"]["1"]["cooldowns"] == {}
        assert state["participants"]["2"]["cooldowns"] == {}

    def test_set_cooldown_then_decrement(self):
        """set_cooldown + decrement_cooldowns work together."""
        state = _make_battle_state()
        set_cooldown(state, 1, 42, 2)
        assert state["participants"]["1"]["cooldowns"]["42"] == 2

        decrement_cooldowns(state)
        assert state["participants"]["1"]["cooldowns"]["42"] == 1

        decrement_cooldowns(state)
        assert "42" not in state["participants"]["1"]["cooldowns"]

    def test_skill_on_cooldown_returns_400(self):
        """Using a skill that is on cooldown returns HTTP 400."""
        # Rank 1 has cooldown of 2. After decrement at start of turn -> 1
        # which is still > 0, so it should fail.
        state = _make_battle_state(cooldowns_p1={"1": 2})
        attack_rank = {
            "id": 1,
            "damage_entries": [],
            "effects": [],
            "cooldown": 2,
            "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
        }
        patches = _build_common_patches(state, attack_rank)
        response, _ = _run_action(patches)
        assert response.status_code == 400
        assert "перезарядке" in response.json()["detail"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# Test Group 3: Enemy effects not duplicated (Task #3)
# ══════════════════════════════════════════════════════════════════════════════


class TestEffectsNotDuplicated:
    """Verify that enemy effects from attack skills are applied exactly
    once per turn, not duplicated."""

    def test_attack_enemy_effects_applied_once(self):
        """Enemy effects from attack rank are applied exactly once."""
        state = _make_battle_state(hp_p1=100, hp_p2=100)
        attack_rank = {
            "id": 1,
            "damage_entries": [
                {"damage_type": "physical", "amount": 5, "chance": 100}
            ],
            "effects": [
                {
                    "effect_name": "Buff:fire",
                    "attribute_key": None,
                    "magnitude": 10,
                    "duration": 3,
                    "target_side": "enemy",
                }
            ],
            "cooldown": 0,
            "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
        }

        patches = _build_common_patches(
            state, attack_rank,
            damage_result=(5.0, {"damage_type": "physical", "final": 5.0}),
        )

        # Patch apply_new_effects on main module (where it was imported)
        mock_apply = MagicMock()
        patches["main.apply_new_effects"] = mock_apply

        response, _ = _run_action(patches)
        assert response.status_code == 200

        # apply_new_effects should be called exactly once for the defender
        # from the attack enemy effects
        enemy_effect_calls = [
            c for c in mock_apply.call_args_list
            if c[0][1] == 2  # pid=2 (defender)
        ]
        assert len(enemy_effect_calls) == 1, (
            f"Expected exactly 1 apply_new_effects call for defender, "
            f"got {len(enemy_effect_calls)}"
        )

        events = response.json()["events"]
        attack_effect_events = [
            e for e in events
            if e.get("event") == "apply_effects"
            and e.get("kind") == "attack"
        ]
        assert len(attack_effect_events) == 1, (
            f"Expected exactly 1 apply_effects(attack) event, "
            f"got {len(attack_effect_events)}"
        )

    def test_support_and_attack_effects_each_once(self):
        """When using both support and attack with enemy effects,
        each applies exactly once."""
        state = _make_battle_state(hp_p1=100, hp_p2=100)

        attack_rank = {
            "id": 1,
            "damage_entries": [
                {"damage_type": "physical", "amount": 5, "chance": 100}
            ],
            "effects": [
                {
                    "effect_name": "Buff:fire",
                    "attribute_key": None,
                    "magnitude": 10,
                    "duration": 3,
                    "target_side": "enemy",
                }
            ],
            "cooldown": 0,
            "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
        }
        support_rank = {
            "id": 2,
            "effects": [
                {
                    "effect_name": "Resist:physical",
                    "attribute_key": None,
                    "magnitude": -5,
                    "duration": 2,
                    "target_side": "enemy",
                }
            ],
            "cooldown": 0,
            "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
        }

        async def _get_rank_side_effect(rank_id):
            if rank_id == 1:
                return attack_rank
            elif rank_id == 2:
                return support_rank
            return {}

        mock_apply = MagicMock()

        patches = _build_common_patches(
            state, attack_rank,
            damage_result=(5.0, {"damage_type": "physical", "final": 5.0}),
        )
        # Override get_rank to return different ranks
        patches["main.get_rank"] = AsyncMock(side_effect=_get_rank_side_effect)
        patches["main.character_has_rank"] = AsyncMock(return_value=True)
        patches["main.apply_new_effects"] = mock_apply

        payload = {
            "participant_id": 1,
            "skills": {
                "attack_rank_id": 1,
                "defense_rank_id": None,
                "support_rank_id": 2,
                "item_id": None,
            },
        }

        response, _ = _run_action(patches, payload=payload)
        assert response.status_code == 200

        # Calls on defender (pid=2): once from support, once from attack
        enemy_effect_calls = [
            c for c in mock_apply.call_args_list
            if c[0][1] == 2
        ]
        assert len(enemy_effect_calls) == 2, (
            f"Expected 2 apply_new_effects calls on defender "
            f"(support + attack), got {len(enemy_effect_calls)}"
        )

        events = response.json()["events"]
        apply_events = [
            e for e in events if e.get("event") == "apply_effects"
        ]
        kinds = [e["kind"] for e in apply_events]
        assert kinds.count("attack") == 1
        assert kinds.count("support") == 1

    def test_no_effects_no_apply_call(self):
        """When attack rank has no effects, apply_new_effects is not called
        for the defender."""
        state = _make_battle_state(hp_p1=100, hp_p2=100)
        attack_rank = {
            "id": 1,
            "damage_entries": [
                {"damage_type": "physical", "amount": 5, "chance": 100}
            ],
            "effects": [],  # No effects
            "cooldown": 0,
            "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
        }
        mock_apply = MagicMock()

        patches = _build_common_patches(
            state, attack_rank,
            damage_result=(5.0, {"damage_type": "physical", "final": 5.0}),
        )
        patches["main.apply_new_effects"] = mock_apply

        response, _ = _run_action(patches)
        assert response.status_code == 200

        enemy_effect_calls = [
            c for c in mock_apply.call_args_list
            if c[0][1] == 2
        ]
        assert len(enemy_effect_calls) == 0
