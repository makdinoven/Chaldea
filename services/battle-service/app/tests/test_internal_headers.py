"""
FEAT-169 (QA task #18) — battle-service must send `X-Internal-Token` on every
call into a route this feature gated, and `get_fast_slots` must now target the
**internal twin** of the belt route.

Why this file exists at all: 4 of the 5 call sites swallow their error
(`update-durability`, `add_rewards`, `/party/internal/xp-bonus`,
`/party/internal/active-members`). A forgotten header would raise nothing —
durability writes, PvE rewards and party XP would just quietly stop, which is
the project's documented silent-failure pattern. So **every** assertion below
reads the header VALUE off the real client function; none of them merely
asserts "nothing was raised".

Two client families are covered:
  * `inventory_client` — `consume_item`, `update_durability`, `get_fast_slots`
    (gated) and `get_item` / `get_equipment_durability` (deliberately public
    GETs that must keep sending **nothing**);
  * `main` — `_distribute_pve_rewards` (`add_rewards` + `/party/internal/xp-bonus`)
    and `_party_active_members_data` (`/party/internal/active-members`).

`inventory_client` is loaded from its own file under a private module name so
that the MagicMock other test files park in `sys.modules["inventory_client"]`
cannot be mistaken for the real thing (and so this file does not disturb them).
"""

import importlib.util
import os
import sys

from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "testuser")
os.environ.setdefault("DB_PASSWORD", "testpass")
os.environ.setdefault("DB_DATABASE", "testdb")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("aioredis", MagicMock())
sys.modules.setdefault("celery", MagicMock())

import database  # noqa: E402

database.engine = MagicMock()

for _mod_name in (
    "redis_state",
    "mongo_client",
    "mongo_helpers",
    "tasks",
    "inventory_client",
    "character_client",
    "skills_client",
    "buffs",
    "battle_engine",
):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

_redis_state_mock = sys.modules["redis_state"]
_redis_state_mock.ZSET_DEADLINES = "battle:deadlines"
_redis_state_mock.KEY_BATTLE_TURNS = "battle:{id}:turns"
_redis_state_mock.state_key = MagicMock(return_value="battle:1:state")
_redis_state_mock.init_battle_state = AsyncMock()
_redis_state_mock.load_state = AsyncMock(return_value=None)
_redis_state_mock.save_state = AsyncMock()
_redis_state_mock.get_redis_client = AsyncMock(return_value=AsyncMock())
_redis_state_mock.cache_snapshot = AsyncMock()
_redis_state_mock.get_cached_snapshot = AsyncMock(return_value=None)

_tasks_mock = sys.modules["tasks"]
_tasks_mock.save_log = MagicMock()
_tasks_mock.save_log.delay = MagicMock()

import main  # noqa: E402

main.app.router.on_startup.clear()


APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOKEN = "test-internal-token"


def _load_real_inventory_client():
    """Import `inventory_client.py` from disk under a private name.

    Several battle-service test modules park a `MagicMock` in
    `sys.modules["inventory_client"]`; asserting headers against that mock would
    prove nothing. Loading the file directly guarantees the assertions below run
    against the production functions, whatever collection order pytest picks.
    """
    path = os.path.join(APP_DIR, "inventory_client.py")
    spec = importlib.util.spec_from_file_location(
        "_feat169_real_inventory_client", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inventory_client = _load_real_inventory_client()


@pytest.fixture()
def token_env(monkeypatch):
    """Both helpers read `INTERNAL_SERVICE_TOKEN` at call time."""
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = {} if payload is None else payload
        self.text = str(self._payload)

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _patch_inventory_transport(monkeypatch, response=None):
    """Patch `httpx.AsyncClient` inside the real inventory_client module."""
    calls = []
    resp = response or _Resp()

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, **kwargs):
            calls.append(("GET", url, kwargs))
            return resp

        async def post(self, url, **kwargs):
            calls.append(("POST", url, kwargs))
            return resp

    monkeypatch.setattr(inventory_client.httpx, "AsyncClient", _Client)
    return calls


def _patch_main_transport(monkeypatch, get_payload=None, post_payload=None):
    """Patch `httpx.AsyncClient` inside `main` and record every verb."""
    calls = []

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, **kwargs):
            calls.append(("GET", url, kwargs))
            return _Resp(200, get_payload if get_payload is not None else {})

        async def post(self, url, **kwargs):
            calls.append(("POST", url, kwargs))
            return _Resp(200, post_payload if post_payload is not None else {})

        async def put(self, url, **kwargs):
            calls.append(("PUT", url, kwargs))
            return _Resp(200, {})

    monkeypatch.setattr(main.httpx, "AsyncClient", _Client)
    return calls


def _only(calls, needle):
    return [c for c in calls if needle in c[1]]


# ═══════════════════════════════════════════════════════════════════════════
# inventory_client — the three gated calls
# ═══════════════════════════════════════════════════════════════════════════


class TestConsumeItem:
    """`POST /inventory/internal/characters/{cid}/consume_item` (gate I).

    The only one of the three whose failure reaches the player (it returns
    `{"status": "error"}`), but a 401 here still means belt items stop working
    mid-battle."""

    @pytest.mark.asyncio
    async def test_sends_the_internal_token(self, monkeypatch, token_env):
        calls = _patch_inventory_transport(
            monkeypatch, _Resp(200, {"status": "ok", "remaining_quantity": 4})
        )

        result = await inventory_client.consume_item(11, 331)

        assert len(calls) == 1, "consume_item never reached inventory-service"
        verb, url, kwargs = calls[0]
        assert verb == "POST"
        assert url.endswith("/inventory/internal/characters/11/consume_item"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "battle-service dropped X-Internal-Token on consume_item — "
            "inventory-service answers 401 and the belt item is never spent"
        )
        assert kwargs["json"] == {"item_id": 331}
        assert result == {"status": "ok", "remaining_quantity": 4}

    @pytest.mark.asyncio
    async def test_401_is_reported_as_an_error_not_a_success(
        self, monkeypatch, token_env
    ):
        """If the header were ever wrong, the player must see an error rather
        than a silently consumed nothing."""
        _patch_inventory_transport(
            monkeypatch, _Resp(401, {"detail": "Недействительный internal token"})
        )
        result = await inventory_client.consume_item(11, 331)
        assert result["status"] == "error"
        assert result["detail"] == "Недействительный internal token"


class TestUpdateDurability:
    """`POST /inventory/internal/update-durability` (gate I) — best-effort,
    the caller swallows the exception, so only a header assertion can catch a
    regression here."""

    @pytest.mark.asyncio
    async def test_sends_the_internal_token(self, monkeypatch, token_env):
        calls = _patch_inventory_transport(monkeypatch)
        entries = [{"slot_type": "main_weapon", "new_durability": 7}]

        await inventory_client.update_durability(11, entries)

        assert len(calls) == 1, "update_durability never reached inventory-service"
        verb, url, kwargs = calls[0]
        assert verb == "POST"
        assert url.endswith("/inventory/internal/update-durability"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "battle-service dropped X-Internal-Token on update-durability — "
            "post-battle durability writes would vanish without a single log line"
        )
        assert kwargs["json"] == {"character_id": 11, "entries": entries}


class TestGetFastSlots:
    """`GET /inventory/internal/characters/{cid}/fast_slots` (gate I, NEW).

    The player path `/inventory/characters/{cid}/fast_slots` now requires a JWT
    plus ownership, so a service token there would 401 — and mobs/NPCs have no
    owner at all. The URL assertion is therefore as load-bearing as the header."""

    BELT = [
        {
            "slot_type": "fast_slot_1",
            "item_id": 3,
            "quantity": 5,
            "name": "Зелье",
            "image": "/p.png",
            "health_recovery": 30,
            "mana_recovery": 0,
            "consumable_action": None,
            "coating_turns": None,
            "coating_bonus_damage": None,
            "effects": [{"effect_type": "heal"}],
            "damage_entries": [],
        }
    ]

    @pytest.mark.asyncio
    async def test_uses_the_internal_route_with_the_token(
        self, monkeypatch, token_env
    ):
        calls = _patch_inventory_transport(monkeypatch, _Resp(200, self.BELT))

        slots = await inventory_client.get_fast_slots(11)

        assert len(calls) == 1
        verb, url, kwargs = calls[0]
        assert verb == "GET"
        assert url.endswith("/inventory/internal/characters/11/fast_slots"), (
            f"battle start still reads the belt through the player route: {url} — "
            "that route is JWT + ownership gated now and would 401"
        )
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "battle-service dropped X-Internal-Token on fast_slots — no battle "
            "could start"
        )
        # the FEAT-168 payload still survives the mapping
        assert slots[0]["item_id"] == 3
        assert slots[0]["health_recovery"] == 30
        assert "mana_recovery" not in slots[0], "zero recovery must stay omitted"
        assert slots[0]["effects"] == [{"effect_type": "heal"}]

    @pytest.mark.asyncio
    async def test_does_not_use_the_player_route(self, monkeypatch, token_env):
        calls = _patch_inventory_transport(monkeypatch, _Resp(200, []))
        await inventory_client.get_fast_slots(11)
        url = calls[0][1]
        assert "/inventory/characters/11/fast_slots" not in url, (
            "the player (JWT + ownership) belt route would 401 for a service"
        )


class TestItemAndEquipmentGetsUseTheInternalTwins:
    """FEAT-171 Pass A: `get_item` and `get_equipment_durability` used to hit
    the public routes (`/inventory/items/{id}`, `/inventory/{cid}/equipment`).
    Those are being thinned and gated, so both now read the internal twins
    (I3i / I2i) with `X-Internal-Token`.

    These two callers raise on failure, but `get_equipment_durability`'s
    per-item lookup is swallowed — a missing header would silently zero every
    durability tick. Hence the assertion is on the URL *and* the header, never
    on "nothing raised"."""

    @pytest.mark.asyncio
    async def test_get_item_uses_internal_twin_with_token(
        self, monkeypatch, token_env
    ):
        calls = _patch_inventory_transport(monkeypatch, _Resp(200, {"id": 3}))
        await inventory_client.get_item(3)

        verb, url, kwargs = calls[0]
        assert verb == "GET"
        assert url.endswith("/inventory/internal/items/3"), url
        assert kwargs["headers"]["X-Internal-Token"] == token_env

    @pytest.mark.asyncio
    async def test_get_equipment_durability_uses_internal_twin_with_token(
        self, monkeypatch, token_env
    ):
        calls = _patch_inventory_transport(monkeypatch, _Resp(200, []))
        await inventory_client.get_equipment_durability(11)

        verb, url, kwargs = calls[0]
        assert verb == "GET"
        assert url.endswith("/inventory/internal/characters/11/equipment"), url
        assert kwargs["headers"]["X-Internal-Token"] == token_env


class TestTokenIsReadAtCallTime:
    """A module-level constant captured at import would send an empty header in
    a container that received the variable later. Two env values → two headers."""

    @pytest.mark.asyncio
    async def test_two_env_values_produce_two_headers(self, monkeypatch):
        calls = _patch_inventory_transport(monkeypatch)

        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        await inventory_client.update_durability(1, [])
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        await inventory_client.update_durability(1, [])

        assert [c[2]["headers"]["X-Internal-Token"] for c in calls] == [
            "first",
            "second",
        ]

    @pytest.mark.asyncio
    async def test_missing_token_still_sends_the_key(self, monkeypatch):
        """Fail-closed on the callee side: the key is always present, so the
        failure is a clear 401 instead of a mystery."""
        monkeypatch.delenv("INTERNAL_SERVICE_TOKEN", raising=False)
        calls = _patch_inventory_transport(monkeypatch)
        await inventory_client.update_durability(1, [])
        assert calls[0][2]["headers"]["X-Internal-Token"] == ""


# ═══════════════════════════════════════════════════════════════════════════
# main.py — add_rewards, xp-bonus, active-members
# ═══════════════════════════════════════════════════════════════════════════


MOB_REWARD_DATA = {
    "xp_reward": 50,
    "gold_reward": 10,
    "loot_table": [],
    "template_name": "Волк",
    "tier": "normal",
}


def _pve_state():
    return {
        "turn_number": 5,
        "next_actor": 1,
        "first_actor": 1,
        "turn_order": [1, 2],
        "total_turns": 5,
        "last_turn": None,
        "deadline_at": "2026-01-01T00:00:00",
        "location_id": 77,
        "participants": {
            "1": {"character_id": 10, "hp": 100, "team": 0, "cooldowns": {},
                  "fast_slots": []},
            "2": {"character_id": 20, "hp": 0, "team": 1, "cooldowns": {},
                  "fast_slots": []},
        },
        "active_effects": {},
    }


class TestPveRewardDistribution:
    """`main.py:425` add_rewards and `main.py:443` `/party/internal/xp-bonus`.
    Both are best-effort (logged, never re-raised), so the header value is the
    only thing that can fail loudly in a test."""

    @pytest.mark.asyncio
    async def test_add_rewards_sends_the_internal_token(
        self, monkeypatch, token_env
    ):
        calls = _patch_main_transport(monkeypatch, get_payload=MOB_REWARD_DATA)

        rewards = await main._distribute_pve_rewards(_pve_state(), 0, [])

        assert rewards is not None and rewards.xp == 50
        grants = _only(calls, "/add_rewards")
        assert len(grants) == 1, "the PvE reward grant never left battle-service"
        verb, url, kwargs = grants[0]
        assert verb == "POST"
        assert url.endswith("/characters/10/add_rewards"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "battle-service dropped X-Internal-Token on add_rewards — "
            "character-service answers 401 and the PvE XP/gold is lost with "
            "only a log line"
        )
        assert kwargs["json"] == {"xp": 50, "gold": 10}

    @pytest.mark.asyncio
    async def test_party_xp_bonus_sends_the_internal_token(
        self, monkeypatch, token_env
    ):
        calls = _patch_main_transport(monkeypatch, get_payload=MOB_REWARD_DATA)

        await main._distribute_pve_rewards(_pve_state(), 0, [])

        bonuses = _only(calls, "/party/internal/xp-bonus")
        assert len(bonuses) == 1, "the party XP bonus never left battle-service"
        verb, url, kwargs = bonuses[0]
        assert verb == "POST"
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "battle-service dropped X-Internal-Token on /party/internal/xp-bonus "
            "— squad XP would silently stop (the call is wrapped in a bare "
            "`except` that only warns)"
        )
        assert kwargs["json"]["character_id"] == 10
        assert kwargs["json"]["source"] == "combat"
        assert kwargs["json"]["base_xp"] == 50

    @pytest.mark.asyncio
    async def test_mob_reward_lookup_also_carries_the_token(
        self, monkeypatch, token_env
    ):
        """`/characters/internal/mob-reward-data` was gated by FEAT-162; it is
        the gate that decides a battle is PvE at all."""
        calls = _patch_main_transport(monkeypatch, get_payload=MOB_REWARD_DATA)
        await main._distribute_pve_rewards(_pve_state(), 0, [])

        lookups = _only(calls, "/characters/internal/mob-reward-data/")
        assert lookups
        assert lookups[0][2]["headers"]["X-Internal-Token"] == TOKEN

    @pytest.mark.asyncio
    async def test_token_is_read_at_call_time(self, monkeypatch):
        calls = _patch_main_transport(monkeypatch, get_payload=MOB_REWARD_DATA)

        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        await main._distribute_pve_rewards(_pve_state(), 0, [])
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        await main._distribute_pve_rewards(_pve_state(), 0, [])

        seen = [c[2]["headers"]["X-Internal-Token"]
                for c in _only(calls, "/add_rewards")]
        assert seen == ["first", "second"]


class TestPartyActiveMembers:
    """`GET /party/internal/active-members` — the whole `/party/internal/`
    prefix is gated now. battle-service calls it from three places; this is the
    one that is a plain function (`main.py:3713`), the other two
    (`main.py:990`, `:1171`) are covered by the source sweep below."""

    @pytest.mark.asyncio
    async def test_sends_the_internal_token(self, monkeypatch, token_env):
        roster = {"party_id": 4, "member_character_ids": [10, 11]}
        calls = _patch_main_transport(monkeypatch, get_payload=roster)

        data = await main._party_active_members_data(10, 77)

        assert data == roster
        assert len(calls) == 1
        verb, url, kwargs = calls[0]
        assert verb == "GET"
        assert url.endswith("/party/internal/active-members"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "battle-service dropped X-Internal-Token on active-members — "
            "party-vs-party PvP would silently degrade to a 1v1"
        )
        assert kwargs["params"] == {"character_id": 10, "location_id": 77}

    @pytest.mark.asyncio
    async def test_missing_token_still_sends_the_key(self, monkeypatch):
        monkeypatch.delenv("INTERNAL_SERVICE_TOKEN", raising=False)
        calls = _patch_main_transport(monkeypatch, get_payload={})
        await main._party_active_members_data(10, 77)
        assert calls[0][2]["headers"]["X-Internal-Token"] == ""


# ═══════════════════════════════════════════════════════════════════════════
# FEAT-170 (QA task #15) — battle-service's seven NEW outgoing call sites
# ═══════════════════════════════════════════════════════════════════════════
# All seven were headerless before FEAT-170 and **all seven swallow their
# error**, so "nothing was raised" proves exactly nothing:
#
#   main.py:807   POST /autobattle/internal/register          -> mobs stop acting
#   main.py:725   POST /locations/quests/internal/auto-progress -> quests stall
#   main.py:911   POST /locations/internal/action-gate/consume  -> attack refused
#   main.py:1251  POST /locations/internal/action-gate/consume  -> PvP refused
#   main.py:1035  POST /locations/internal/gathering-status     -> gatherers dragged in
#   main.py:1203  POST /locations/internal/gathering-status     -> same
#   main.py:3755  POST /locations/internal/gathering-status     -> same
#
# Every assertion below therefore reads the header VALUE off the **real**
# production function with only the HTTP transport patched.


def _npc_db(npc_ids=(), levels=None, mob_rows=None):
    """An AsyncSession double that answers battle-service's raw `text()` probes.

    `npc_ids` are the character ids that come back as NPC/mob; `levels` maps a
    character id to its level; `mob_rows` maps a character id to
    `(mob_template_id, tier)`.
    """
    levels = levels or {}
    mob_rows = mob_rows or {}

    async def _execute(query, params=None):
        q = str(query)
        cid = (params or {}).get("cid")
        result = MagicMock()
        if "active_mobs" in q:
            result.fetchone = MagicMock(return_value=mob_rows.get(cid))
        elif "is_npc, level" in q:
            result.fetchone = MagicMock(
                return_value=(cid in npc_ids, levels.get(cid, 0))
            )
        elif "is_npc" in q:
            result.fetchone = MagicMock(return_value=(cid in npc_ids,))
        else:
            result.fetchone = MagicMock(return_value=None)
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_execute)
    return db


class TestAutobattleRegister:
    """`POST /autobattle/internal/register` (`main.py:807`) — gated by FEAT-170
    task #11.

    The single most likely silent breakage in the whole feature: the call is
    wrapped in a `logger.warning` **inside** a `logger.error` **inside** a bare
    `except Exception`. A dropped header means mobs simply never take a turn,
    with nothing in the response to show for it.
    """

    @pytest.mark.asyncio
    async def test_sends_the_internal_token(self, monkeypatch, token_env):
        calls = _patch_main_transport(monkeypatch)
        _stub_assemble_battle(monkeypatch)

        db = _npc_db(npc_ids={20})
        await main._assemble_battle(db, [10, 20], [0, 1], "pve", 7)

        regs = _only(calls, "/internal/register")
        assert len(regs) == 1, (
            "регистрация моба в autobattle не ушла — без неё моб не ходит"
        )
        verb, url, kwargs = regs[0]
        assert verb == "POST"
        assert url.endswith("/internal/register"), url
        assert url.startswith(main.settings.AUTOBATTLE_SERVICE_URL), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "battle-service dropped X-Internal-Token on /autobattle/internal/"
            "register — autobattle answers 401, the mob never takes a turn and "
            "the only trace is a WARNING line"
        )
        assert kwargs["json"] == {"participant_id": 2, "battle_id": 77}

    @pytest.mark.asyncio
    async def test_only_npc_participants_are_registered(self, monkeypatch, token_env):
        """Sanity for the assertion above: the player must not be registered,
        so a call count of 1 really is the mob's."""
        calls = _patch_main_transport(monkeypatch)
        _stub_assemble_battle(monkeypatch)

        await main._assemble_battle(_npc_db(npc_ids=set()), [10, 20], [0, 1], "pve", 7)

        assert not _only(calls, "/internal/register")

    @pytest.mark.asyncio
    async def test_dropping_the_header_would_be_caught(self, monkeypatch, token_env):
        """Negative control (precedent: inventory-service
        `test_outgoing_internal_headers.py::test_dropping_the_header_would_be_caught`).

        If a future edit removed `headers=_internal_token_headers()` the call
        still happens and still "succeeds" — the header is the ONLY observable
        difference, which is why every assertion above reads its value.
        """
        calls = _patch_main_transport(monkeypatch)
        _stub_assemble_battle(monkeypatch)
        monkeypatch.setattr(main, "_internal_token_headers", dict)

        await main._assemble_battle(_npc_db(npc_ids={20}), [10, 20], [0, 1], "pve", 7)

        regs = _only(calls, "/internal/register")
        assert len(regs) == 1, (
            "вызов по-прежнему происходит — проверка по количеству вызовов "
            "ничего не заметила бы"
        )
        assert "X-Internal-Token" not in (regs[0][2].get("headers") or {}), (
            "заголовок — единственное наблюдаемое отличие, поэтому именно его "
            "проверяют тесты выше"
        )


def _stub_assemble_battle(monkeypatch):
    """Neutralise everything in `_assemble_battle` except the autobattle POST."""
    battle = MagicMock()
    battle.id = 77
    p1, p2 = MagicMock(), MagicMock()
    p1.id, p1.character_id, p1.team = 1, 10, 0
    p2.id, p2.character_id, p2.team = 2, 20, 1

    monkeypatch.setattr(main, "create_battle", AsyncMock(return_value=(battle, [p1, p2])))

    async def _info(character_id, pid):
        return {
            "participant_id": pid, "character_id": character_id,
            "name": "X", "avatar": "/x.png",
            "attributes": {
                "current_health": 100, "current_mana": 10,
                "current_energy": 10, "current_stamina": 10,
                "max_health": 100, "max_mana": 10,
                "max_energy": 10, "max_stamina": 10,
            },
            "skills": [], "fast_slots": [],
        }

    monkeypatch.setattr(main, "build_participant_info", AsyncMock(side_effect=_info))
    monkeypatch.setattr(main, "init_battle_state", AsyncMock())
    monkeypatch.setattr(main, "save_snapshot", AsyncMock())
    monkeypatch.setattr(main, "cache_snapshot", AsyncMock())
    rds = AsyncMock()
    rds.zadd = AsyncMock()
    monkeypatch.setattr(main, "get_redis_client", AsyncMock(return_value=rds))


class TestQuestAutoProgress:
    """`POST /locations/quests/internal/auto-progress` (`main.py:725`, URL built
    at `:702`) — gated by FEAT-170 task #8. Swallowed with a `logger.warning`:
    a dropped header means quest objectives silently stop ticking after a kill.
    """

    STATE = {
        "participants": {
            "1": {"character_id": 10, "team": 0, "hp": 100, "max_hp": 100},
            "2": {"character_id": 20, "team": 1, "hp": 0, "max_hp": 100},
        }
    }

    @pytest.mark.asyncio
    async def test_every_quest_event_carries_the_internal_token(
        self, monkeypatch, token_env
    ):
        calls = _patch_main_transport(monkeypatch)
        db = _npc_db(npc_ids={20}, levels={20: 25}, mob_rows={20: (5, "normal")})

        await main._track_cumulative_stats(self.STATE, 0, "pve", 4, db)

        quests = _only(calls, "/locations/quests/internal/auto-progress")
        assert quests, "квестовый auto-progress не ушёл после победы над мобом"
        for verb, url, kwargs in quests:
            assert verb == "POST"
            assert url.startswith(main.settings.LOCATIONS_SERVICE_URL), url
            assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
                "battle-service dropped X-Internal-Token on quest auto-progress "
                "— locations-service answers 401 and quest objectives stop "
                "ticking with only a WARNING"
            )
        assert {c[2]["json"]["event_type"] for c in quests} == {
            "defeat_any", "kill_mob", "kill_mob_any",
        }

    @pytest.mark.asyncio
    async def test_token_is_read_at_call_time(self, monkeypatch):
        """The helper must read `os.environ` per call, not capture at import —
        a container that received the variable late would send an empty header
        forever."""
        calls = _patch_main_transport(monkeypatch)
        db = _npc_db(npc_ids={20}, levels={20: 25}, mob_rows={20: (5, "normal")})

        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        await main._track_cumulative_stats(self.STATE, 0, "pve", 4, db)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        await main._track_cumulative_stats(self.STATE, 0, "pve", 4, db)

        seen = {c[2]["headers"]["X-Internal-Token"]
                for c in _only(calls, "/quests/internal/auto-progress")}
        assert seen == {"first", "second"}


class TestActionGateConsume:
    """`POST /locations/internal/action-gate/consume` — the two battle-service
    call sites (`main.py:911` combat, `:1251` PvP), gated by FEAT-170 task #8.

    These two fail **closed**: the helper returns `False` on any error, and the
    caller turns that into `403 Нужен боевой пост…`. A dropped header does not
    degrade quietly here — it refuses every attack and every PvP fight.
    """

    @pytest.mark.asyncio
    async def test_combat_gate_sends_the_internal_token(self, monkeypatch, token_env):
        calls = _patch_main_transport(monkeypatch, post_payload={"consumed": True})

        ok = await main._consume_combat_gate(10, 7, 20)

        assert ok is True
        assert len(calls) == 1
        verb, url, kwargs = calls[0]
        assert verb == "POST"
        assert url == (
            f"{main.settings.LOCATIONS_SERVICE_URL}"
            "/locations/internal/action-gate/consume"
        ), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "battle-service dropped X-Internal-Token on the combat action-gate "
            "— the consume 401s, the helper returns False and every attack is "
            "refused with 403"
        )
        assert kwargs["json"] == {
            "character_id": 10, "location_id": 7,
            "action_type": "combat", "target_ref": 20,
        }

    @pytest.mark.asyncio
    async def test_pvp_gate_sends_the_internal_token(self, monkeypatch, token_env):
        calls = _patch_main_transport(monkeypatch, post_payload={"consumed": True})

        ok = await main._consume_pvp_gate(10, 7, 20)

        assert ok is True
        assert len(calls) == 1
        verb, url, kwargs = calls[0]
        assert verb == "POST"
        assert url.endswith("/locations/internal/action-gate/consume"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "battle-service dropped X-Internal-Token on the PvP action-gate — "
            "every forced PvP request would be refused with 403"
        )
        assert kwargs["json"]["action_type"] == "pvp"

    @pytest.mark.asyncio
    async def test_a_401_fails_closed_rather_than_letting_the_attack_through(
        self, monkeypatch, token_env
    ):
        """Documents the blast radius of a missed header: refusal, not a free
        attack. (Fail-closed is the correct behaviour — this pins it.)"""
        class _Client:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, **kwargs):
                return _Resp(401, {"detail": "Недействительный internal token"})

        monkeypatch.setattr(main.httpx, "AsyncClient", _Client)
        assert await main._consume_combat_gate(10, 7, 20) is False


class TestGatheringStatus:
    """`POST /locations/internal/gathering-status` — all three battle-service
    call sites, gated by FEAT-170 task #8. Swallowed: on error the "busy" set
    comes back empty, so squadmates who are peacefully gathering get dragged
    into a fight. Nothing is logged that a player would ever see.
    """

    ROSTER = {"party_id": 4, "member_character_ids": [10, 11]}

    @pytest.mark.asyncio
    async def test_filter_available_sends_the_internal_token(
        self, monkeypatch, token_env
    ):
        """`main.py:3755` — `_filter_available`, a plain function."""
        calls = _patch_main_transport(
            monkeypatch, post_payload={"gathering_character_ids": [11]}
        )
        monkeypatch.setattr(main, "get_active_battle_for_character",
                            AsyncMock(return_value=None))

        available = await main._filter_available(AsyncMock(), [10, 11])

        assert available == [10], "the gatherer must be excluded"
        assert len(calls) == 1
        verb, url, kwargs = calls[0]
        assert verb == "POST"
        assert url.endswith("/locations/internal/gathering-status"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "battle-service dropped X-Internal-Token on gathering-status — the "
            "busy set comes back empty and gatherers are pulled into fights"
        )
        assert kwargs["json"] == {"character_ids": [10, 11]}

    @pytest.mark.asyncio
    async def test_party_mob_attack_sends_the_internal_token(
        self, monkeypatch, token_env
    ):
        """`main.py:1035` — inside the `/party/mob-attack` endpoint body. The
        handler is called directly (real function, patched transport); it aborts
        later at the action-gate, which is fine: the gathering-status call has
        already been made and recorded by then."""
        from fastapi import HTTPException

        calls = _patch_main_transport(
            monkeypatch,
            get_payload=self.ROSTER,
            post_payload={"gathering_character_ids": []},
        )
        monkeypatch.setattr(main, "_get_character_info", AsyncMock(
            return_value={"user_id": 1, "current_location_id": 7}))
        monkeypatch.setattr(main, "get_active_battle_for_character",
                            AsyncMock(return_value=None))

        req = main.PartyMobAttack(leader_character_id=10, mob_character_id=20)
        user = main.UserRead(id=1, username="p", role="user", permissions=[])
        db = _npc_db(npc_ids={20})

        async def _loc_row(query, params=None):
            result = MagicMock()
            result.fetchone = MagicMock(return_value=(7, True))
            return result

        db.execute = AsyncMock(side_effect=_loc_row)

        with pytest.raises(HTTPException):
            # `post_payload` makes the action-gate answer `consumed: False`
            await main.party_mob_attack(req, db, user)

        gathering = _only(calls, "/locations/internal/gathering-status")
        assert len(gathering) == 1, "проверка сбора не ушла из /party/mob-attack"
        assert gathering[0][2]["headers"]["X-Internal-Token"] == TOKEN, (
            "/party/mob-attack dropped X-Internal-Token on gathering-status"
        )

    @pytest.mark.asyncio
    async def test_party_pack_attack_sends_the_internal_token(
        self, monkeypatch, token_env
    ):
        """`main.py:1203` — inside the `/party/pack-attack` endpoint body."""
        from fastapi import HTTPException

        calls = _patch_main_transport(
            monkeypatch,
            get_payload=self.ROSTER,
            post_payload={"gathering_character_ids": []},
        )
        monkeypatch.setattr(main, "_get_character_info", AsyncMock(
            return_value={"user_id": 1, "current_location_id": 7}))
        monkeypatch.setattr(main, "_get_pack_roster", AsyncMock(return_value={
            "location_id": 7,
            "member_character_ids": [20, 21],
            "lead_character_id": 20,
        }))
        monkeypatch.setattr(main, "get_active_battle_for_character",
                            AsyncMock(return_value=None))

        req = main.PartyPackAttack(leader_character_id=10, active_pack_id=3)
        user = main.UserRead(id=1, username="p", role="user", permissions=[])

        with pytest.raises(HTTPException):
            await main.party_pack_attack(req, AsyncMock(), user)

        gathering = _only(calls, "/locations/internal/gathering-status")
        assert len(gathering) == 1, "проверка сбора не ушла из /party/pack-attack"
        assert gathering[0][2]["headers"]["X-Internal-Token"] == TOKEN, (
            "/party/pack-attack dropped X-Internal-Token on gathering-status"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Source sweep
# ═══════════════════════════════════════════════════════════════════════════


def _statement_window(source: str, idx: int) -> str:
    """The source of the call that starts at `idx`, and nothing after it.

    A fixed forward window bleeds into the *next* function, so a call that lost
    its header would still "see" the neighbour's `_internal_token_headers()` and
    the sweep would pass. Cutting at the first blank line keeps the window to
    one statement/`try` block — verified by deleting a header and watching the
    sweep go red.
    """
    window = source[idx: idx + 900]
    end = window.find(chr(10) * 2)
    return window if end == -1 else window[:end]


class TestSourceSweep:
    """Every call in battle-service that targets a FEAT-162/167/169-gated path
    must pass a token header. Adding a new one without it fails here — this is
    what covers `main.py:990` and `:1171`, which live inside endpoint bodies.

    Kept alongside the **inverted** AST sweep below: this one also catches
    `/add_rewards`, which has no `internal` segment in its path but is gated
    all the same.
    """

    GATED = (
        "/add_rewards",
    )

    FILES = ("main.py", "inventory_client.py")

    def test_all_gated_calls_carry_a_token_header(self):
        offenders = []
        for filename in self.FILES:
            with open(os.path.join(APP_DIR, filename), encoding="utf-8") as fh:
                source = fh.read()
            lines = source.split("\n")
            for gated in self.GATED:
                idx = 0
                while True:
                    idx = source.find(gated, idx)
                    if idx == -1:
                        break
                    line_no = source.count("\n", 0, idx)
                    # Only real URL construction counts — docstrings, comments
                    # and log messages name these paths too.
                    if 'f"' in lines[line_no]:
                        window = _statement_window(source, idx)
                        if (
                            "_internal_token_headers()" not in window
                            and "X-Internal-Token" not in window
                        ):
                            offenders.append(f"{filename}:{line_no + 1} -> {gated}")
                    idx += len(gated)
        assert not offenders, (
            "gated call(s) without an internal token header: "
            + "; ".join(offenders)
        )

    def test_fast_slots_is_only_reached_through_the_internal_route(self):
        """Nobody may re-point the belt read back at the player route."""
        with open(os.path.join(APP_DIR, "inventory_client.py"), encoding="utf-8") as fh:
            source = fh.read()
        assert "/inventory/internal/characters/{character_id}/fast_slots" in source
        assert "{BASE}/inventory/characters/" not in source, (
            "inventory_client targets the JWT-gated player belt route again"
        )


# ═══════════════════════════════════════════════════════════════════════════
# FEAT-170 (QA task #15 iv) — INVERTED source sweep
# ═══════════════════════════════════════════════════════════════════════════
# The sweep above is allowlist-based: a call to a target nobody thought to list
# passes silently. That is exactly how the seven FEAT-170 call sites stayed
# headerless through two previous features. The rule here has no allowlist and
# no exemption list:
#
#     ANY httpx/client/requests get|post|put|patch|delete whose RESOLVED url
#     contains "/internal/" MUST pass `headers=`.
#
# "Resolved" matters: most battle-service call sites build the URL into a local
# variable one line above the call (`quest_url = f"..."`), so a literal-only
# scan would see nothing at all. The AST resolver is copied from
# `inventory-service/app/tests/test_outgoing_internal_headers.py`
# (`TestEveryInternalCallSiteSendsHeaders._resolve` / `._url_of`).
#
# Note `main.py:~4140` (`/locations/internal/cancel-gathering`) builds the
# header inline as a dict rather than through the helper — it does pass
# `headers=`, so it is legitimately green here.

#: Every module in `services/battle-service/app/` that makes outgoing HTTP
#: calls. Widened past `main.py` per §3.12(d): a client module is exactly where
#: a headerless call would hide.
SWEPT_FILES = tuple(
    name for name in (
        "main.py",
        "crud.py",
        "inventory_client.py",
        "character_client.py",
        "skills_client.py",
    )
    if os.path.exists(os.path.join(APP_DIR, name))
)


class TestEveryInternalCallSiteSendsHeaders:
    """No allowlist. Any resolved `/internal/` URL must carry `headers=`."""

    def _resolve(self, source, tree):
        """{(func start, func end): {variable: assigned source}} for `x = expr`."""
        import ast

        env = {}

        class _V(ast.NodeVisitor):
            def _scope(self, node):
                local = {}
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Assign) and len(sub.targets) == 1 \
                            and isinstance(sub.targets[0], ast.Name):
                        local[sub.targets[0].id] = \
                            ast.get_source_segment(source, sub.value) or ""
                env[(node.lineno, node.end_lineno)] = local
                self.generic_visit(node)

            visit_FunctionDef = _scope
            visit_AsyncFunctionDef = _scope

        _V().visit(tree)
        return env

    def _url_of(self, source, env, node):
        import ast

        arg = node.args[0] if node.args else None
        if arg is None:
            for kw in node.keywords:
                if kw.arg == "url":
                    arg = kw.value
                    break
        raw = (ast.get_source_segment(source, arg) if arg is not None else "") or ""
        if "/" in raw:
            return raw
        # a URL-building helper — `_some_url(cid)`: inline its return
        if arg is not None and isinstance(arg, ast.Call) \
                and isinstance(arg.func, ast.Name):
            builder = arg.func.id
            for sub in ast.walk(self._tree):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and sub.name == builder:
                    for inner in ast.walk(sub):
                        if isinstance(inner, ast.Return) and inner.value is not None:
                            return ast.get_source_segment(
                                self._source, inner.value) or raw
        # a bare name — look it up in the innermost enclosing function
        scopes = [(end - start, local) for (start, end), local in env.items()
                  if start <= node.lineno <= end]
        scopes.sort(key=lambda pair: pair[0])
        for _, local in scopes:
            if raw in local:
                return local[raw]
        return raw

    def _scan_source(self, filename, source):
        """The whole rule, for one module's source. No allowlist anywhere."""
        import ast

        offenders, checked = [], 0
        tree = ast.parse(source)
        self._source, self._tree = source, tree
        env = self._resolve(source, tree)

        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in ("get", "post", "put", "patch", "delete"):
                continue
            base = ast.get_source_segment(source, node.func.value)
            if base not in ("httpx", "client", "requests"):
                continue
            url = self._url_of(source, env, node)
            if "/internal/" not in url:
                continue
            checked += 1
            if "headers" not in {kw.arg for kw in node.keywords}:
                offenders.append(
                    f"{filename}:{node.lineno} "
                    f"{base}.{node.func.attr}({url[:70]}) без headers="
                )
        return checked, offenders

    def _sweep(self):
        offenders, checked = [], 0
        for filename in SWEPT_FILES:
            with open(os.path.join(APP_DIR, filename), encoding="utf-8") as fh:
                source = fh.read()
            found, bad = self._scan_source(filename, source)
            checked += found
            offenders.extend(bad)
        return checked, offenders

    def test_no_internal_call_is_missing_headers(self):
        checked, offenders = self._sweep()

        # Floor: 7 FEAT-170 sites + add_rewards' neighbours already covered by
        # FEAT-162/167/169 (party active-members ×3, xp-bonus, mob-reward-data,
        # unlink, cancel-gathering, the inventory_client trio, …). A refactor
        # that drops below this emptied the sweep rather than fixing anything.
        assert checked >= 14, (
            "свип перестал находить внутренние вызовы — URL отрефакторили, "
            f"и проверка стала пустой (найдено {checked})"
        )
        assert not offenders, (
            "межсервисный вызов на /internal/ без X-Internal-Token — целевой "
            "маршрут ответит 401, а вызывающий это проглотит: "
            + "; ".join(offenders)
        )

    def test_the_seven_feat170_targets_are_still_there(self):
        """Guard for the sweep itself: if a URL is refactored out of
        recognition the sweep silently matches nothing."""
        source = open(os.path.join(APP_DIR, "main.py"), encoding="utf-8").read()
        for needle in (
            "/internal/register",
            "/locations/quests/internal/auto-progress",
            "/locations/internal/action-gate/consume",
            "/locations/internal/gathering-status",
        ):
            assert needle in source, f"{needle} исчез из battle-service"
        assert source.count("/locations/internal/gathering-status") >= 3
        assert source.count("/locations/internal/action-gate/consume") >= 2

    def test_the_sweep_really_catches_a_headerless_call(self):
        """Negative control for the sweep itself.

        A sweep that matches nothing is indistinguishable from a sweep that
        passes. This feeds `_scan_source` a synthetic module holding one
        headered and one headerless internal call and demands it flag exactly
        the second — including the variable-URL form the real call sites use.
        """
        synthetic = (
            "import httpx\n"
            "\n"
            "async def good(client):\n"
            "    url = f'{BASE}/locations/internal/gathering-status'\n"
            "    await client.post(url, json={}, headers=_internal_token_headers())\n"
            "\n"
            "async def bad(client):\n"
            "    url = f'{BASE}/locations/internal/action-gate/consume'\n"
            "    await client.post(url, json={})\n"
        )
        checked, offenders = self._scan_source("synthetic.py", synthetic)

        assert checked == 2, f"resolver missed a variable URL (checked={checked})"
        assert len(offenders) == 1, offenders
        assert "action-gate/consume" in offenders[0]
        assert "без headers=" in offenders[0]

    def test_the_sweep_has_no_exemption_list(self):
        """FEAT-170 §3.12(d): no allowlist may creep back in. The FEAT-169
        markers (a tuple of "known ungated targets", a `GATED` prefix tuple used
        to *skip* internal URLs) are what made the old sweeps toothless, so the
        rule is checked for the absence of any `continue` that depends on the
        URL's identity rather than on it being internal."""
        import ast
        import inspect
        import textwrap

        body = textwrap.dedent(inspect.getsource(self._scan_source))
        # Build the forbidden name in pieces so this assertion does not trip
        # over its own source when the file is scanned.
        forbidden = "_KNOWN_" + "UNGATED_TARGETS"
        assert forbidden not in body
        # The only `continue`s allowed are the four structural filters.
        continues = sum(1 for n in ast.walk(ast.parse(body))
                        if isinstance(n, ast.Continue))
        assert continues == 4, (
            "в свип добавили ещё одну ветку пропуска — именно так семь вызовов "
            f"FEAT-170 и прожили две фичи без заголовка (найдено {continues})"
        )
