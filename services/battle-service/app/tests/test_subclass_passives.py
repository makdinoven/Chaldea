"""FEAT-188 (Task #6) — subclass passives in battle-service.

Covered:
  1. ``passives.rage_bonus_pct`` — Berserk «Ярость» math: +4% per FULL 10% of
     max HP lost, capped at +36%; clamping and garbage-in (old states).
  2. ``passives.passive_damage_bonus`` — dispatch: no key / unknown key / any
     non-rage registry key → ``(0, None)``; berserker → its percent.
     Plus a contract check against the skills-service registry: the set of
     passives marked ``implemented=True`` there is exactly the set that has an
     effect here (all 21 since FEAT-190), and the Berserk description quotes
     the real constants.
  3. ``skills_client.get_character_subclass`` — the REAL function, with a fake
     ``httpx.AsyncClient``: URL ``/skills/internal/characters/{id}/subclass``,
     header ``X-Internal-Token: <env value>``, NO ``Authorization: Bearer``
     (the skills-service ``verify_internal_token`` rejects the Bearer position
     with 401 — and this battle-side call soft-fails, so a wrong header would
     look exactly like "nobody has a passive". This project has repeatedly
     shipped that kind of silent failure with green tests; these asserts are on
     the literal header name and value).
  4. ``build_participant_info`` — passive attached for a player, ``None`` for
     NPCs (whatever skills-service says about them), soft failure on network /
     HTTP / plain-MagicMock ``TypeError`` with ``logger.error`` and the rest of
     the snapshot intact; and the real client wired in end-to-end (a 401 from
     skills-service ends in the soft-fail path, a 200 ends with the passive).
  5. ``_assemble_battle`` → real ``init_battle_state`` → the JSON written to
     Redis carries ``passive_key`` (berserker → key, mob → None).
     ``init_battle_state`` copies the key and tolerates payloads without it.
  6. ``_make_action_core`` damage hooks (skill attack + item damage) with the
     REAL buffs engine and the REAL damage formula: a wounded berserker gets the
     rage percent in the "all" bucket (``buff_pct``) and the damage event carries
     ``passive_key``/``passive_pct``; full-HP berserker and non-berserker get
     nothing; dodge events unchanged; a pre-FEAT-188 state (no ``passive_key``,
     no ``max_hp``) resolves a turn without the new keys.

PvP invitation accept, PvP attack and the admin join approval are covered in
``test_pvp_invitations.py``, ``test_pvp_attack.py`` and ``test_join_requests.py``
(they reuse those files' DB fakes).

Nothing here touches a real network, Redis, MySQL or Mongo.
"""

import importlib
import importlib.util
import json
import math
import os
import re
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, APP_DIR)

sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("aioredis", MagicMock())
sys.modules.setdefault("celery", MagicMock())

import database  # noqa: E402

database.engine = MagicMock()

for _mod_name in [
    "redis_state", "mongo_client", "mongo_helpers", "tasks",
    "inventory_client", "character_client", "skills_client", "rabbitmq_publisher",
]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

_redis_state_mock = sys.modules["redis_state"]
if isinstance(_redis_state_mock, MagicMock):
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
if isinstance(_tasks_mock, MagicMock):
    _tasks_mock.save_log = MagicMock()
    _tasks_mock.save_log.delay = MagicMock()

# `main` binds these names at import; if THIS file is the first to import main,
# later files (join / PvP tests) rely on them being awaitable — configure them
# the same way those files do.
_mongo_helpers_mock = sys.modules["mongo_helpers"]
if isinstance(_mongo_helpers_mock, MagicMock):
    _mongo_helpers_mock.save_snapshot = AsyncMock()
    _mongo_helpers_mock.load_snapshot = AsyncMock(return_value=None)
_rmq_mock = sys.modules["rabbitmq_publisher"]
if isinstance(_rmq_mock, MagicMock):
    _rmq_mock.publish_notification = AsyncMock()
_skills_mock = sys.modules["skills_client"]
if isinstance(_skills_mock, MagicMock):
    _skills_mock.character_has_skill = AsyncMock(return_value=True)
    _skills_mock.get_resolved_skill = AsyncMock(return_value={})
    _skills_mock.get_item = AsyncMock(return_value={})
    _skills_mock.character_skills = AsyncMock(return_value=[])
_inv_mock = sys.modules["inventory_client"]
if isinstance(_inv_mock, MagicMock):
    _inv_mock.get_fast_slots = AsyncMock(return_value=[])
    _inv_mock.consume_item = AsyncMock(return_value={"status": "ok", "remaining_quantity": 0})
_char_mock = sys.modules["character_client"]
if isinstance(_char_mock, MagicMock):
    _char_mock.get_character_profile = AsyncMock(
        return_value={"character_name": "Test", "character_photo": ""})

# Real engine (other files swap it for a MagicMock during collection).
if "battle_engine" in sys.modules:
    del sys.modules["battle_engine"]
battle_engine = importlib.import_module("battle_engine")
sys.modules["battle_engine"] = battle_engine


def _load_private(module_name, path):
    """Load a module from its file under a private name — immune to the
    MagicMocks other test files park in ``sys.modules``."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


buffs = _load_private("_feat188_buffs", os.path.join(APP_DIR, "buffs.py"))
real_redis_state = _load_private("_feat188_redis_state", os.path.join(APP_DIR, "redis_state.py"))
passives = _load_private("_feat188_passives", os.path.join(APP_DIR, "passives.py"))

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
_REAL_compute_damage_with_rolls = battle_engine.compute_damage_with_rolls
_REAL_apply_flat_modifiers = battle_engine.apply_flat_modifiers
assert not isinstance(_REAL_compute_damage_with_rolls, MagicMock)

import main  # noqa: E402
from main import app  # noqa: E402
from database import get_db  # noqa: E402

app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402

# main must hold the REAL passive hook (nobody mocks `passives`, but guard it).
assert not isinstance(main.passive_damage_bonus, MagicMock)
_REAL_passive_damage_bonus = main.passive_damage_bonus
_REAL_build_participant_info = main.build_participant_info

TOKEN = "feat188-internal-token"
BERSERK = "berserker_rage"

SKILLS_REGISTRY_PATH = os.path.normpath(os.path.join(
    APP_DIR, "..", "..", "skills-service", "app", "subclasses.py"
))


# ══════════════════════════════════════════════════════════════════════════════
# 1. rage_bonus_pct
# ══════════════════════════════════════════════════════════════════════════════

class TestRageBonusPct:

    def test_constants_are_the_agreed_numbers(self):
        assert passives.PASSIVE_BERSERKER_RAGE == BERSERK
        assert passives.RAGE_HP_STEP_PCT == 10
        assert passives.RAGE_PCT_PER_STEP == 4
        assert passives.RAGE_MAX_STEPS == 9
        assert passives.RAGE_PCT_PER_STEP * passives.RAGE_MAX_STEPS == 36

    @pytest.mark.parametrize("hp, expected", [
        (100, 0),        # full HP
        (90.01, 0),      # 9.99% lost — not a full step
        (90, 4),         # exactly 10%
        (80.1, 4),       # 19.9%
        (80, 8),         # exactly 20%
        (75, 8),         # 25%
        (50, 20),        # 50%
        (10.1, 32),      # 89.9%
        (10, 36),        # exactly 90% — cap
        (1, 36),         # 99%
        (0, 36),         # dead
    ])
    def test_steps_over_max_hp_100(self, hp, expected):
        assert passives.rage_bonus_pct(hp, 100) == expected

    @pytest.mark.parametrize("hp", [-1, -50, -10_000])
    def test_negative_hp_is_clamped_to_zero_and_capped(self, hp):
        assert passives.rage_bonus_pct(hp, 100) == 36

    @pytest.mark.parametrize("hp", [101, 150, 10_000])
    def test_hp_above_max_is_clamped_to_full(self, hp):
        assert passives.rage_bonus_pct(hp, 100) == 0

    @pytest.mark.parametrize("max_hp", [0, -5, None, "", "abc", float("nan"), float("inf")])
    def test_bad_max_hp_gives_zero(self, max_hp):
        # old states without max_hp, broken values: never a crash, never a bonus
        assert passives.rage_bonus_pct(10, max_hp) == 0

    @pytest.mark.parametrize("hp", [None, "abc", float("nan")])
    def test_bad_hp_gives_zero(self, hp):
        assert passives.rage_bonus_pct(hp, 100) == 0

    def test_scales_with_any_max_hp(self):
        assert passives.rage_bonus_pct(1350, 1500) == 4    # exactly 10%
        assert passives.rage_bonus_pct(750, 1500) == 20    # 50%
        assert passives.rage_bonus_pct(151, 1500) == 32    # 89.93%
        assert passives.rage_bonus_pct(150, 1500) == 36    # 90%

    def test_float_hp_after_float_damage(self):
        # HP in state is a float reduced by float `dealt`.
        assert passives.rage_bonus_pct(100 - 10.00001, 100) == 4
        assert passives.rage_bonus_pct(89.99999, 100) == 4
        # (1.0 - 0.9) * 100 == 9.999999999999998 — "exactly 10%" with rounding
        # noise must still be a full step (that is what the epsilon is for).
        assert (1.0 - 0.9) * 100 / 1.0 < 10
        assert passives.rage_bonus_pct(0.9, 1.0) == 4
        # ten float hits of 0.7 on max 70 → "exactly 10%" lost, with whatever
        # accumulation noise float subtraction produces
        hp = 70.0
        for _ in range(10):
            hp -= 0.7
        assert passives.rage_bonus_pct(hp, 70.0) == 4

    def test_returns_int(self):
        assert isinstance(passives.rage_bonus_pct(50, 100), int)


# ══════════════════════════════════════════════════════════════════════════════
# 2. passive_damage_bonus + registry contract
# ══════════════════════════════════════════════════════════════════════════════

def _registry():
    if not os.path.exists(SKILLS_REGISTRY_PATH):
        pytest.skip("skills-service registry not present in this checkout")
    return _load_private("_feat188_skills_registry", SKILLS_REGISTRY_PATH)


class TestPassiveDamageBonus:

    @pytest.mark.parametrize("state", [None, [], "berserker_rage", 42])
    def test_non_dict_state(self, state):
        assert passives.passive_damage_bonus(state) == (0, None)

    def test_no_key(self):
        assert passives.passive_damage_bonus({"hp": 10, "max_hp": 100}) == (0, None)

    def test_key_is_none(self):
        assert passives.passive_damage_bonus(
            {"hp": 10, "max_hp": 100, "passive_key": None}) == (0, None)

    def test_unknown_key(self):
        assert passives.passive_damage_bonus(
            {"hp": 10, "max_hp": 100, "passive_key": "no_such_passive"}) == (0, None)

    def test_berserker_wounded(self):
        assert passives.passive_damage_bonus(
            {"hp": 50, "max_hp": 100, "passive_key": BERSERK}) == (20, BERSERK)

    def test_berserker_capped(self):
        assert passives.passive_damage_bonus(
            {"hp": 0, "max_hp": 100, "passive_key": BERSERK}) == (36, BERSERK)

    def test_berserker_full_hp_reports_no_passive(self):
        # pct 0 → (0, None): the log must not get a "+0%" passive line
        assert passives.passive_damage_bonus(
            {"hp": 100, "max_hp": 100, "passive_key": BERSERK}) == (0, None)

    def test_berserker_old_state_without_max_hp(self):
        assert passives.passive_damage_bonus(
            {"hp": 10, "passive_key": BERSERK}) == (0, None)

    def test_berserker_without_hp_counts_as_dead(self):
        # .get("hp", 0) → 0 HP; with a valid max_hp that is the cap.
        assert passives.passive_damage_bonus(
            {"max_hp": 100, "passive_key": BERSERK}) == (36, BERSERK)

    def test_no_registry_passive_is_left_unimplemented(self):
        """FEAT-190 (wave 2) made the last 7 live: no registry passive is
        `implemented=False` any more, and every registry key is known to
        battle-service. (Was: «the 7 not-implemented passives have no
        effect» — that FEAT-189 guarantee no longer applies; the wave-2
        effects are pinned in test_passives_wave2_integration.py.)"""
        reg = _registry()
        not_implemented = [s.passive.key for s in reg.SUBCLASSES if not s.passive.implemented]
        assert not_implemented == []
        for s in reg.SUBCLASSES:
            assert s.passive.key in passives.IMPLEMENTED_PASSIVES, s.passive.key

    def test_only_rage_uses_the_flat_damage_dispatch(self):
        # every other implemented passive works through the FEAT-189 hooks
        assert set(passives._DAMAGE_PASSIVES) == {BERSERK}
        reg = _registry()
        for s in reg.SUBCLASSES:
            if s.passive.key != BERSERK:
                assert passives.passive_damage_bonus(
                    {"hp": 1, "max_hp": 100, "passive_key": s.passive.key}) == (0, None)

    def test_implemented_flag_matches_what_battle_applies(self):
        """skills-service shows «пока не действует в бою» for implemented=False.
        If battle-service gained an effect without flipping the flag (or the flag
        were flipped without an effect), players would be told the wrong thing.
        battle-side truth: `passives.IMPLEMENTED_PASSIVES` (rage + wave 1 +
        wave 2 = all 21 since FEAT-190)."""
        reg = _registry()
        implemented = {s.passive.key for s in reg.SUBCLASSES if s.passive.implemented}
        assert implemented == set(passives.IMPLEMENTED_PASSIVES)
        assert len(implemented) == 21
        assert implemented == {s.passive.key for s in reg.SUBCLASSES}
        assert implemented == {
            BERSERK, "inquisitor_heresy_seal", "saber_monster_hunter", "gladiator_arena",
            "agent_weak_spot", "lancer_pin", "mechanic_shrapnel", "archer_first_blood",
            "assassin_from_shadow", "trickster_deceit", "monk_harmony",
            "salamander_kindling", "caster_pure_energy", "sparkmage_chain_lightning",
            # FEAT-190 (wave 2)
            "paladin_sacred_vow", "guardian_retribution", "bard_rhythm",
            "necromancer_blood_price", "etheriad_spirit_whisper", "auromancer_tide",
            "priest_faith",
        }
        # every implemented key has its battle-side constant
        consts = {v for k, v in vars(passives).items()
                  if k.startswith("PASSIVE_") and isinstance(v, str)}
        assert implemented <= consts

    def test_berserk_description_quotes_the_constants(self):
        reg = _registry()
        desc = reg.get_passive_for_subclass("warrior_berserker").description
        assert f"+{passives.RAGE_PCT_PER_STEP}%" in desc
        assert f"{passives.RAGE_HP_STEP_PCT}%" in desc
        assert f"+{passives.RAGE_PCT_PER_STEP * passives.RAGE_MAX_STEPS}%" in desc


# ══════════════════════════════════════════════════════════════════════════════
# 3. skills_client.get_character_subclass — the real function
# ══════════════════════════════════════════════════════════════════════════════

class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}", request=MagicMock(), response=MagicMock()
            )


def _fake_httpx(monkeypatch, module, router):
    """Replace ``module.httpx.AsyncClient``; record constructor kwargs + GETs."""
    calls = []
    ctor = []

    class _Client:
        def __init__(self, *a, **kw):
            ctor.append(kw)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return router(url)

    monkeypatch.setattr(module.httpx, "AsyncClient", _Client)
    return calls, ctor


SUBCLASS_PAYLOAD = {
    "character_id": 77, "is_npc": False,
    "subclass_key": "warrior_berserker", "subclass_name": "Берсерк",
    "passive": {"key": BERSERK, "name": "Ярость",
                "description": "…", "implemented": True},
}


@pytest.fixture()
def client_module(monkeypatch):
    """skills_client loaded fresh AFTER the env var is set — the module reads
    INTERNAL_SERVICE_TOKEN at import, exactly as in the container."""
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    return _load_private("_feat188_skills_client", os.path.join(APP_DIR, "skills_client.py"))


class TestGetCharacterSubclassClient:

    @pytest.mark.asyncio
    async def test_url_path(self, monkeypatch, client_module):
        calls, _ = _fake_httpx(monkeypatch, client_module, lambda u: _Resp(200, SUBCLASS_PAYLOAD))
        await client_module.get_character_subclass(77)
        assert len(calls) == 1
        url, _ = calls[0]
        assert url.endswith("/skills/internal/characters/77/subclass"), url
        assert url == f"{client_module.BASE}/skills/internal/characters/77/subclass"

    @pytest.mark.asyncio
    async def test_sends_exactly_x_internal_token_with_the_env_value(
        self, monkeypatch, client_module
    ):
        calls, _ = _fake_httpx(monkeypatch, client_module, lambda u: _Resp(200, SUBCLASS_PAYLOAD))
        await client_module.get_character_subclass(77)
        headers = calls[0][1]["headers"]
        assert headers == {"X-Internal-Token": TOKEN}

    @pytest.mark.asyncio
    async def test_never_uses_the_bearer_position(self, monkeypatch, client_module):
        calls, _ = _fake_httpx(monkeypatch, client_module, lambda u: _Resp(200, SUBCLASS_PAYLOAD))
        await client_module.get_character_subclass(77)
        headers = calls[0][1]["headers"]
        assert "Authorization" not in headers
        assert not any("Bearer" in str(v) for v in headers.values())

    def test_the_other_skills_reads_still_use_bearer(self, client_module):
        # The module deliberately has two header styles; make sure they did not
        # get swapped wholesale.
        assert client_module._service_headers() == {"Authorization": f"Bearer {TOKEN}"}
        assert client_module._internal_headers() == {"X-Internal-Token": TOKEN}

    @pytest.mark.asyncio
    async def test_uses_the_short_timeout(self, monkeypatch, client_module):
        _, ctor = _fake_httpx(monkeypatch, client_module, lambda u: _Resp(200, SUBCLASS_PAYLOAD))
        await client_module.get_character_subclass(77)
        assert ctor[0].get("timeout") == client_module.SUBCLASS_LOOKUP_TIMEOUT_S == 3.0

    @pytest.mark.asyncio
    async def test_returns_the_json(self, monkeypatch, client_module):
        _fake_httpx(monkeypatch, client_module, lambda u: _Resp(200, SUBCLASS_PAYLOAD))
        assert await client_module.get_character_subclass(77) == SUBCLASS_PAYLOAD

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [401, 404, 503])
    async def test_http_errors_raise(self, monkeypatch, client_module, status):
        _fake_httpx(monkeypatch, client_module, lambda u: _Resp(status, {"detail": "x"}))
        with pytest.raises(httpx.HTTPStatusError):
            await client_module.get_character_subclass(77)


# ══════════════════════════════════════════════════════════════════════════════
# 4. build_participant_info
# ══════════════════════════════════════════════════════════════════════════════

INFO_ATTRS = {
    "current_health": 100, "current_mana": 50, "current_energy": 50,
    "current_stamina": 50, "max_health": 100, "max_mana": 50,
    "max_energy": 50, "max_stamina": 50,
    "agility": 10, "strength": 10, "intelligence": 5,
}


def _info_patches(subclass_fn):
    return [
        patch.object(main, "fetch_full_attributes", AsyncMock(return_value=dict(INFO_ATTRS))),
        patch.object(main, "character_skills", AsyncMock(return_value=[{"skill_id": 1}])),
        patch.object(main, "get_fast_slots", AsyncMock(return_value=[{"slot_type": "fast_slot_1"}])),
        patch.object(main, "get_character_profile", AsyncMock(
            return_value={"character_name": "Ашари", "character_photo": "a.png"})),
        patch.object(main, "get_equipment_durability", AsyncMock(return_value={"head": 10})),
        patch.object(main, "get_character_subclass", subclass_fn),
    ]


async def _build_info(subclass_fn, char_id=77, pid=5):
    logger = MagicMock()
    ps = _info_patches(subclass_fn) + [patch.object(main, "logger", logger)]
    for p in ps:
        p.start()
    try:
        info = await _REAL_build_participant_info(char_id, pid)
    finally:
        for p in reversed(ps):
            p.stop()
    return info, logger


def _assert_rest_intact(info):
    assert info["participant_id"] == 5
    assert info["character_id"] == 77
    assert info["name"] == "Ашари"
    assert info["avatar"] == "a.png"
    assert info["attributes"]["max_health"] == 100
    assert info["skills"] == [{"skill_id": 1}]
    assert info["fast_slots"] == [{"slot_type": "fast_slot_1"}]
    assert info["equipment_durability"] == {"head": 10}


class TestBuildParticipantInfo:

    @pytest.mark.asyncio
    async def test_berserker_gets_subclass_and_passive(self):
        sub = AsyncMock(return_value=dict(SUBCLASS_PAYLOAD))
        info, logger = await _build_info(sub)
        sub.assert_awaited_once_with(77)
        assert info["subclass"] == {"key": "warrior_berserker", "name": "Берсерк"}
        assert info["passive"]["key"] == BERSERK
        assert info["passive"]["name"] == "Ярость"
        assert main._passive_key_of(info) == BERSERK
        _assert_rest_intact(info)
        logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_subclass_chosen(self):
        sub = AsyncMock(return_value={
            "character_id": 77, "is_npc": False,
            "subclass_key": None, "subclass_name": None, "passive": None,
        })
        info, logger = await _build_info(sub)
        assert info["subclass"] is None
        assert info["passive"] is None
        assert main._passive_key_of(info) is None
        logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_npc_gets_nothing_even_if_skills_service_sent_a_passive(self):
        payload = dict(SUBCLASS_PAYLOAD, is_npc=True)
        info, logger = await _build_info(AsyncMock(return_value=payload))
        assert info["subclass"] is None
        assert info["passive"] is None
        _assert_rest_intact(info)
        logger.error.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("exc", [
        httpx.ConnectError("skills-service down"),
        httpx.ReadTimeout("slow"),
        httpx.HTTPStatusError("401", request=MagicMock(), response=MagicMock()),
        KeyError("subclass_key"),
    ])
    async def test_soft_fail_on_errors(self, exc):
        info, logger = await _build_info(AsyncMock(side_effect=exc))
        assert info["subclass"] is None
        assert info["passive"] is None
        _assert_rest_intact(info)
        logger.error.assert_called_once()
        assert "77" in logger.error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_soft_fail_on_plain_magicmock(self):
        """22 older test files replace skills_client with a plain MagicMock →
        `await MagicMock()` is a TypeError. That must stay a soft failure."""
        info, logger = await _build_info(MagicMock())
        assert info["subclass"] is None
        assert info["passive"] is None
        _assert_rest_intact(info)
        logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_end_to_end_with_the_real_client_200(self, monkeypatch, client_module):
        calls, _ = _fake_httpx(monkeypatch, client_module, lambda u: _Resp(200, SUBCLASS_PAYLOAD))
        info, logger = await _build_info(client_module.get_character_subclass)
        assert info["passive"]["key"] == BERSERK
        assert calls[0][1]["headers"] == {"X-Internal-Token": TOKEN}
        logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_end_to_end_with_the_real_client_401(self, monkeypatch, client_module):
        """What a wrong header looks like in production: skills-service 401 →
        no passive, battle still built, and an ERROR in the log (not silent)."""
        _fake_httpx(monkeypatch, client_module, lambda u: _Resp(401, {"detail": "nope"}))
        info, logger = await _build_info(client_module.get_character_subclass)
        assert info["passive"] is None
        _assert_rest_intact(info)
        logger.error.assert_called_once()


class TestPassiveKeyOf:

    @pytest.mark.parametrize("snap, expected", [
        ({"passive": {"key": BERSERK}}, BERSERK),
        ({"passive": None}, None),
        ({}, None),                          # pre-FEAT-188 snapshot
        ({"passive": "berserker_rage"}, None),  # garbage — not a dict
        ({"passive": {}}, None),
    ])
    def test_values(self, snap, expected):
        assert main._passive_key_of(snap) == expected


# ══════════════════════════════════════════════════════════════════════════════
# 5. _assemble_battle → real init_battle_state → Redis JSON
# ══════════════════════════════════════════════════════════════════════════════

def _stored_state(fake_rds):
    set_calls = [c for c in fake_rds.set.call_args_list if "state" in str(c.args[0])]
    assert set_calls, "init_battle_state did not write the state"
    return json.loads(set_calls[0].args[1])


class TestInitBattleState:

    def _payload(self, **extra):
        p = {
            "participant_id": 11, "character_id": 101, "team": 0,
            "hp": 100, "mana": 50, "energy": 50, "stamina": 50,
            "max_hp": 100, "max_mana": 100, "max_energy": 100,
            "max_stamina": 100, "fast_slots": [],
        }
        p.update(extra)
        return p

    async def _init(self, payload):
        fake_rds = AsyncMock()
        with patch.object(real_redis_state, "get_redis_client",
                          AsyncMock(return_value=fake_rds)):
            await real_redis_state.init_battle_state(
                battle_id=9, participants_payload=payload,
                first_actor_participant_id=payload[0]["participant_id"],
                deadline_at=real_redis_state.utc_now(), location_id=1,
            )
        return _stored_state(fake_rds)

    @pytest.mark.asyncio
    async def test_copies_passive_key(self):
        state = await self._init([
            self._payload(passive_key=BERSERK),
            self._payload(participant_id=12, character_id=102, team=1, passive_key=None),
        ])
        assert state["participants"]["11"]["passive_key"] == BERSERK
        assert state["participants"]["12"]["passive_key"] is None

    @pytest.mark.asyncio
    async def test_payload_without_the_key_gives_none(self):
        state = await self._init([self._payload()])
        assert "passive_key" in state["participants"]["11"]
        assert state["participants"]["11"]["passive_key"] is None


class TestAssembleBattleReachesRedis:

    @pytest.mark.asyncio
    async def test_berserker_and_mob(self):
        participants = [
            SimpleNamespace(id=11, character_id=101, team=0),
            SimpleNamespace(id=12, character_id=102, team=1),
        ]
        battle_obj = SimpleNamespace(id=555)

        async def _subclass(char_id):
            if char_id == 101:
                return dict(SUBCLASS_PAYLOAD, character_id=101)
            return {"character_id": 102, "is_npc": True, "subclass_key": None,
                    "subclass_name": None, "passive": None}

        fake_rds = AsyncMock()
        save_snapshot = AsyncMock()
        result = MagicMock()
        result.fetchone = MagicMock(return_value=None)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)

        ps = _info_patches(AsyncMock(side_effect=_subclass)) + [
            patch.object(main, "build_participant_info", _REAL_build_participant_info),
            patch.object(main, "create_battle",
                         AsyncMock(return_value=(battle_obj, participants))),
            patch.object(main, "save_snapshot", save_snapshot),
            patch.object(main, "cache_snapshot", AsyncMock()),
            patch.object(main, "get_redis_client", AsyncMock(return_value=AsyncMock())),
            patch.object(main, "init_battle_state", real_redis_state.init_battle_state),
            patch.object(main, "compute_initiative", real_redis_state.compute_initiative),
            patch.object(main, "utc_now", real_redis_state.utc_now),
            patch.object(real_redis_state, "get_redis_client",
                         AsyncMock(return_value=fake_rds)),
        ]
        for p in ps:
            p.start()
        try:
            await main._assemble_battle(db, [101, 102], [0, 1], "pve", 7)
        finally:
            for p in reversed(ps):
                p.stop()

        state = _stored_state(fake_rds)
        assert state["participants"]["11"]["passive_key"] == BERSERK
        assert state["participants"]["12"]["passive_key"] is None
        # snapshot carries the display data
        snap = save_snapshot.await_args.args[1]
        by_pid = {s["participant_id"]: s for s in snap}
        assert by_pid[11]["passive"]["name"] == "Ярость"
        assert by_pid[11]["subclass"]["name"] == "Берсерк"
        assert by_pid[12]["passive"] is None

    def test_participant_payload_helper(self):
        snap = {
            "participant_id": 11, "character_id": 101,
            "attributes": dict(INFO_ATTRS), "fast_slots": [],
            "passive": {"key": BERSERK},
        }
        objs = [SimpleNamespace(id=11, team=0)]
        with patch.object(main, "compute_initiative", real_redis_state.compute_initiative):
            payload = main._participant_payload(snap, objs)
        assert payload["passive_key"] == BERSERK
        assert payload["team"] == 0
        assert payload["max_hp"] == 100
        assert payload["equipment_durability"] == {}
        old = {k: v for k, v in snap.items() if k != "passive"}
        with patch.object(main, "compute_initiative", real_redis_state.compute_initiative):
            assert main._participant_payload(old, objs)["passive_key"] is None

    def test_every_inline_builder_uses_the_helper(self):
        """Source guard: the three battle-start sites share one payload helper,
        so a new state key cannot be forgotten in one of them again."""
        with open(os.path.join(APP_DIR, "main.py"), encoding="utf-8") as fh:
            src = fh.read()
        assert len(re.findall(r"_participant_payload\(snap, participant_objs\)", src)) == 3
        assert src.count('"passive_key": _passive_key_of(participant_info)') == 1


# ══════════════════════════════════════════════════════════════════════════════
# 6. Damage hooks in _make_action_core
# ══════════════════════════════════════════════════════════════════════════════

ATTACKER_PID = 1
DEFENDER_PID = 2
ATTACKER_CHAR = 10
DEFENDER_CHAR = 20

TURN_ATTRS = {
    "strength": 20, "agility": 10, "intelligence": 5, "endurance": 0, "luck": 0,
    "charisma": 1, "damage": 5, "dodge": 0,
    "critical_hit_chance": 0, "critical_damage": 100,
    "current_health": 100, "current_mana": 50,
    "current_energy": 50, "current_stamina": 50,
}


def _mock_response(status_code, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _participant(character_id, team, **over):
    part = {
        "character_id": character_id, "team": team,
        "hp": 100, "mana": 50, "energy": 50, "stamina": 50,
        "max_hp": 100, "max_mana": 100, "max_energy": 100, "max_stamina": 100,
        "cooldowns": {}, "fast_slots": [], "equipment_durability": {},
        "total_damage_dealt": 0, "total_damage_received": 0,
    }
    part.update(over)
    return part


def _state(attacker_over=None, defender_over=None):
    attacker = _participant(ATTACKER_CHAR, 0)
    attacker.update(attacker_over or {})
    defender = _participant(DEFENDER_CHAR, 1, hp=1000, max_hp=1000)
    defender.update(defender_over or {})
    return {
        "turn_number": 3, "next_actor": ATTACKER_PID, "first_actor": ATTACKER_PID,
        "initiator_acted_once": True, "first_cycle": False,
        "turn_order": [ATTACKER_PID, DEFENDER_PID], "total_turns": 2,
        "last_turn": None, "deadline_at": "2026-01-01T00:00:00",
        "participants": {str(ATTACKER_PID): attacker, str(DEFENDER_PID): defender},
        "active_effects": {},
    }


def _damage_row(amount=20, damage_type="physical", weapon_slot="no_weapon"):
    return {
        "damage_type": damage_type, "amount": amount, "chance": 100,
        "weapon_slot": weapon_slot, "target_side": "enemy",
        "aoe_shape": "single", "aoe_falloff": 50, "aoe_max_targets": 3,
    }


ATTACK_SKILL = {
    "id": 1, "name": "Удар", "damage_entries": [_damage_row()], "effects": [],
    "cooldown": 0, "cost_energy": 0, "cost_mana": 0, "cost_stamina": 0,
}
NO_ATTACK = dict(ATTACK_SKILL, damage_entries=[])

SCROLL = {
    "slot_type": "fast_slot_1", "item_id": 50, "quantity": 2,
    "name": "Свиток огня", "image": "s.png",
    "health_recovery": 0, "mana_recovery": 0, "energy_recovery": 0,
    "stamina_recovery": 0, "consumable_action": None,
    "coating_turns": None, "coating_bonus_damage": None, "effects": [],
    "damage_entries": [_damage_row(amount=20, damage_type="fire")],
}


def _payload(item_id=None, attack_skill_id=None):
    return {
        "participant_id": ATTACKER_PID,
        "target_id": DEFENDER_PID,
        "skills": {"attack_skill_id": attack_skill_id, "defense_skill_id": None,
                   "support_skill_id": None, "item_id": item_id},
    }


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
    def __init__(self):
        self.calls = []

    async def __call__(self, **kwargs):
        # copy: the buckets dict is the engine's input at the moment of the hit
        self.calls.append({**kwargs, "percent_buffs": dict(kwargs["percent_buffs"])})
        return await _REAL_compute_damage_with_rolls(**kwargs)


def _run_turn(state, payload, attack_skill=None, dodge=False):
    spy = _DamageSpy()
    save_state_mock = AsyncMock()
    patches = {
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
            200, {"id": 5, "username": "player", "role": "user", "permissions": []})),
        "main.fetch_full_attributes": AsyncMock(return_value=dict(TURN_ATTRS)),
        "main.fetch_main_weapon": AsyncMock(return_value=None),
        "main.fetch_weapons": AsyncMock(
            return_value={"main_weapon": None, "additional_weapons": None}),
        "main.fetch_character_class_id": AsyncMock(return_value=1),
        "main.character_has_skill": AsyncMock(return_value=True),
        "main.get_resolved_skill": AsyncMock(return_value=attack_skill or NO_ATTACK),
        "main.consume_item": AsyncMock(return_value={"status": "ok", "remaining_quantity": 1}),
        "main.roll_chance": MagicMock(return_value=True),
        "main.roll_dodge": MagicMock(return_value=dodge),
        "main.compute_damage_with_rolls": spy,
        "main.passive_damage_bonus": _REAL_passive_damage_bonus,
        **{f"main.{name}": fn for name, fn in REAL_BUFFS.items()},
        "main.apply_flat_modifiers": _REAL_apply_flat_modifiers,
    }
    patchers = [patch(t, v) for t, v in patches.items()]
    db = _mock_db()

    async def _fake_get_db():
        yield db

    # pin crits off inside the real formula
    patchers.append(patch.object(battle_engine, "roll_crit", return_value=False))
    patchers.append(patch.object(battle_engine, "roll_chance", return_value=True))

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
    assert response.status_code == 200, response.text
    saved = save_state_mock.call_args[0][1] if save_state_mock.called else state
    return response, spy, saved


def _damage_events(response):
    return [e for e in response.json()["events"] if e["event"] == "damage"]


WOUNDED_BERSERK = {"hp": 50, "passive_key": BERSERK}      # 50% lost → +20%
FULL_BERSERK = {"hp": 100, "passive_key": BERSERK}
WOUNDED_PLAIN = {"hp": 50, "passive_key": None}


class TestSkillAttackHook:

    def _attack(self, attacker_over, dodge=False):
        return _run_turn(_state(attacker_over), _payload(attack_skill_id=1),
                         attack_skill=ATTACK_SKILL, dodge=dodge)

    def test_wounded_berserker_gets_rage_in_all_bucket(self):
        resp, spy, _ = self._attack(WOUNDED_BERSERK)
        assert spy.calls, "the attack must reach the damage formula"
        assert spy.calls[0]["percent_buffs"].get("all") == 20
        ev, = _damage_events(resp)
        assert ev["buff_pct"] == 20
        assert ev["passive_key"] == BERSERK
        assert ev["passive_pct"] == 20

    def test_damage_is_really_higher(self):
        resp_w, _, _ = self._attack(WOUNDED_BERSERK)
        resp_p, _, _ = self._attack(WOUNDED_PLAIN)
        (ev_w,), (ev_p,) = _damage_events(resp_w), _damage_events(resp_p)
        assert ev_p["buff_pct"] == 0
        assert ev_w["final"] == pytest.approx(ev_p["final"] * 1.2, rel=1e-6)

    def test_stacks_with_an_existing_all_buff(self):
        state = _state(WOUNDED_BERSERK)
        state["active_effects"] = {str(ATTACKER_PID): [{
            "name": "Buff", "attribute": "percent_damage", "magnitude": 10,
            "duration": 3, "owner_id": ATTACKER_PID,
        }]}
        resp, spy, _ = _run_turn(state, _payload(attack_skill_id=1), attack_skill=ATTACK_SKILL)
        all_bucket = spy.calls[0]["percent_buffs"].get("all")
        ev, = _damage_events(resp)
        assert ev["passive_pct"] == 20
        # whatever the buff contributes, the passive adds exactly +20 on top
        baseline_state = _state(WOUNDED_PLAIN)
        baseline_state["active_effects"] = state["active_effects"]
        _, spy_b, _ = _run_turn(baseline_state, _payload(attack_skill_id=1),
                                attack_skill=ATTACK_SKILL)
        assert spy_b.calls[0]["percent_buffs"].get("all") == 10, "the buff must reach the engine"
        assert all_bucket == 30

    def test_full_hp_berserker_gets_nothing(self):
        resp, spy, _ = self._attack(FULL_BERSERK)
        assert spy.calls[0]["percent_buffs"].get("all", 0) == 0
        ev, = _damage_events(resp)
        assert "passive_key" not in ev and "passive_pct" not in ev

    def test_non_berserker_gets_nothing(self):
        resp, spy, _ = self._attack(WOUNDED_PLAIN)
        assert spy.calls[0]["percent_buffs"].get("all", 0) == 0
        ev, = _damage_events(resp)
        assert "passive_key" not in ev and "passive_pct" not in ev

    def test_other_registry_passive_gets_nothing(self):
        resp, spy, _ = self._attack({"hp": 10, "passive_key": "priest_faith"})
        assert spy.calls[0]["percent_buffs"].get("all", 0) == 0
        ev, = _damage_events(resp)
        assert "passive_pct" not in ev

    def test_dodge_event_unchanged(self):
        resp, spy, _ = self._attack(WOUNDED_BERSERK, dodge=True)
        assert spy.calls == []
        ev, = _damage_events(resp)
        assert ev == {"event": "damage", "source": ATTACKER_PID,
                      "target": DEFENDER_PID, "dodged": True, "final": 0}

    def test_old_state_without_passive_key_and_max_hp(self):
        state = _state({"hp": 50})
        attacker = state["participants"][str(ATTACKER_PID)]
        attacker.pop("max_hp")
        attacker.pop("passive_key", None)
        resp, spy, saved = _run_turn(state, _payload(attack_skill_id=1),
                                     attack_skill=ATTACK_SKILL)
        ev, = _damage_events(resp)
        assert ev["final"] > 0
        assert "passive_key" not in ev
        assert saved["participants"][str(DEFENDER_PID)]["hp"] < 1000

    def test_old_berserker_state_without_max_hp_gets_nothing(self):
        state = _state(WOUNDED_BERSERK)
        state["participants"][str(ATTACKER_PID)].pop("max_hp")
        resp, spy, _ = _run_turn(state, _payload(attack_skill_id=1),
                                 attack_skill=ATTACK_SKILL)
        ev, = _damage_events(resp)
        assert "passive_pct" not in ev
        assert spy.calls[0]["percent_buffs"].get("all", 0) == 0


class TestItemDamageHook:

    def _scroll(self, attacker_over, dodge=False):
        over = dict(attacker_over, fast_slots=[dict(SCROLL)])
        return _run_turn(_state(over), _payload(item_id=50), dodge=dodge)

    def test_wounded_berserker_item_damage(self):
        resp, spy, _ = self._scroll(WOUNDED_BERSERK)
        assert spy.calls, "the scroll must reach the damage formula"
        assert spy.calls[0]["percent_buffs"].get("all") == 20
        ev, = _damage_events(resp)
        assert ev["source_kind"] == "item"
        assert ev["buff_pct"] == 20
        assert ev["passive_key"] == BERSERK
        assert ev["passive_pct"] == 20

    def test_full_hp_berserker_item_damage(self):
        resp, spy, _ = self._scroll(FULL_BERSERK)
        assert spy.calls[0]["percent_buffs"].get("all", 0) == 0
        ev, = _damage_events(resp)
        assert "passive_key" not in ev and "passive_pct" not in ev

    def test_non_berserker_item_damage(self):
        resp, spy, _ = self._scroll(WOUNDED_PLAIN)
        assert spy.calls[0]["percent_buffs"].get("all", 0) == 0
        ev, = _damage_events(resp)
        assert "passive_key" not in ev and "passive_pct" not in ev

    def test_item_dodge_event_unchanged(self):
        resp, spy, _ = self._scroll(WOUNDED_BERSERK, dodge=True)
        assert spy.calls == []
        ev, = _damage_events(resp)
        assert "passive_key" not in ev and "passive_pct" not in ev
        assert ev["dodged"] is True and ev["final"] == 0

    def test_scroll_and_attack_in_one_turn_both_tagged(self):
        over = dict(WOUNDED_BERSERK, fast_slots=[dict(SCROLL)])
        resp, spy, _ = _run_turn(_state(over), _payload(item_id=50, attack_skill_id=1),
                                 attack_skill=ATTACK_SKILL)
        evs = _damage_events(resp)
        assert len(evs) == 2
        # HP of the berserker does not change between the item and the attack
        # step here, so both carry the same +20.
        assert [e["passive_pct"] for e in evs] == [20, 20]
        assert all(c["percent_buffs"].get("all") == 20 for c in spy.calls)
