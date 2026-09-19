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


class TestPublicGetsSendNothing:
    """`get_item` and `get_equipment_durability` hit routes that stayed public
    (§3.3 M3). Pinning them both ways: nobody should "helpfully" add a token to
    a public GET, and nobody should strip the real headers elsewhere by
    symmetry with these two."""

    @pytest.mark.asyncio
    async def test_get_item_sends_no_header(self, monkeypatch, token_env):
        calls = _patch_inventory_transport(monkeypatch, _Resp(200, {"id": 3}))
        await inventory_client.get_item(3)

        verb, url, kwargs = calls[0]
        assert verb == "GET"
        assert url.endswith("/inventory/items/3"), url
        assert "headers" not in kwargs or "X-Internal-Token" not in (
            kwargs.get("headers") or {}
        ), "get_item targets a public route — it must not leak the service token"

    @pytest.mark.asyncio
    async def test_get_equipment_durability_sends_no_header(
        self, monkeypatch, token_env
    ):
        calls = _patch_inventory_transport(monkeypatch, _Resp(200, []))
        await inventory_client.get_equipment_durability(11)

        verb, url, kwargs = calls[0]
        assert verb == "GET"
        assert url.endswith("/inventory/11/equipment"), url
        assert "headers" not in kwargs or "X-Internal-Token" not in (
            kwargs.get("headers") or {}
        )


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
    what covers `main.py:990` and `:1171`, which live inside endpoint bodies."""

    GATED = (
        "/add_rewards",
        "/party/internal/",
        "/inventory/internal/",
        "/characters/internal/",
        "/attributes/internal/",
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
