"""
FEAT-171 task 19 (battle-service) — the engine's cross-service reads moved onto
the internal twins, and every one of them must carry `X-Internal-Token`.

Pass A repointed three call sites in `battle_engine` plus one in `skills_client`
that the §2.7 list had missed:

| function | was | now |
|---|---|---|
| `battle_engine.fetch_full_attributes` | `GET /attributes/{id}` (anonymous) | `GET /attributes/internal/{id}` (A1i) |
| `battle_engine.fetch_weapons` — equipment | `GET /inventory/{id}/equipment` (anonymous) | `GET /inventory/internal/characters/{id}/equipment` (I2i) |
| `battle_engine.fetch_weapons` — item template | `GET /inventory/items/{id}` (anonymous) | `GET /inventory/internal/items/{id}` (I3i) |
| `skills_client.get_item` | `GET /inventory/items/{id}` (anonymous) | `GET /inventory/internal/items/{id}` (I3i) |

`inventory_client.get_item` / `get_equipment_durability` are covered in
`test_internal_headers.py::TestItemAndEquipmentGetsUseTheInternalTwins`.

Why assert the header and not just "it worked": these are the routes the whole
feature closed. A missing header now means 401 from the twin. `fetch_weapons`
and `fetch_full_attributes` `raise_for_status()`, so *those* would fail loudly
— but `skills_client.get_item` feeds item effects whose absence looks like an
item with no effects, and the public routes they used to call still exist (I3
is still anonymous, just **thin**). A call that drifted back to the public path
would therefore return `200` with a card that has no `damage_entries` and no
`*_modifier` at all: a weapon that silently does no damage. So both the URL and
the header value are asserted on the real client functions.

`battle_engine` is loaded from its own file under a private module name,
because other test files park a `MagicMock` in `sys.modules["battle_engine"]`.
"""

import importlib.util
import os
import sys

from unittest.mock import MagicMock

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

_APP_DIR = os.path.join(os.path.dirname(__file__), "..")


def _load_private(module_name, filename):
    """Import a module from its file under a private name, so the MagicMocks
    other test files leave in `sys.modules` cannot be mistaken for it."""
    spec = importlib.util.spec_from_file_location(
        module_name, os.path.join(_APP_DIR, filename)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


battle_engine = _load_private("_feat171_battle_engine", "battle_engine.py")
skills_client = _load_private("_feat171_skills_client", "skills_client.py")


TOKEN = "test-internal-token"


@pytest.fixture()
def token_env(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError(
                f"{self.status_code}", request=MagicMock(), response=MagicMock()
            )


EQUIPMENT = [
    {"slot_type": "main_weapon", "item_id": 331, "effective_damage": 42.0},
    {"slot_type": "additional_weapons", "item_id": None},
    {"slot_type": "fast_slot_1", "item_id": 900},
]
ITEM_TEMPLATE = {"id": 331, "name": "Меч", "damage_modifier": 7, "damage_entries": []}
ATTRIBUTES = {"current_health": 10, "max_health": 10}


def _patch(monkeypatch, module, router):
    """Replace `module.httpx.AsyncClient` and record every GET."""
    calls = []

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return router(url)

    monkeypatch.setattr(module.httpx, "AsyncClient", _Client)
    return calls


def _engine_router(url):
    if "/attributes/" in url:
        return _Resp(200, dict(ATTRIBUTES))
    if url.endswith("/equipment"):
        return _Resp(200, list(EQUIPMENT))
    return _Resp(200, dict(ITEM_TEMPLATE))


# ═══════════════════════════════════════════════════════════════════════════
# battle_engine.fetch_full_attributes -> A1i
# ═══════════════════════════════════════════════════════════════════════════

class TestFetchFullAttributes:

    @pytest.mark.asyncio
    async def test_targets_the_internal_twin(self, monkeypatch, token_env):
        calls = _patch(monkeypatch, battle_engine, _engine_router)
        await battle_engine.fetch_full_attributes(11)
        assert len(calls) == 1
        url, _kwargs = calls[0]
        assert url.endswith("/attributes/internal/11"), url

    @pytest.mark.asyncio
    async def test_sends_the_internal_token(self, monkeypatch, token_env):
        calls = _patch(monkeypatch, battle_engine, _engine_router)
        await battle_engine.fetch_full_attributes(11)
        _url, kwargs = calls[0]
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "the battle engine dropped X-Internal-Token on the attributes read "
            "— every combatant's stats would come back 401"
        )

    @pytest.mark.asyncio
    async def test_never_uses_the_player_route(self, monkeypatch, token_env):
        """`GET /attributes/{id}` is now owner-only; a mob has no owner, so a
        drift back to the public path breaks every PvE fight."""
        calls = _patch(monkeypatch, battle_engine, _engine_router)
        await battle_engine.fetch_full_attributes(11)
        assert all("/attributes/internal/" in url for url, _ in calls), calls

    @pytest.mark.asyncio
    async def test_the_token_is_read_at_call_time(self, monkeypatch):
        calls = _patch(monkeypatch, battle_engine, _engine_router)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        await battle_engine.fetch_full_attributes(11)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        await battle_engine.fetch_full_attributes(11)
        assert [kw["headers"]["X-Internal-Token"] for _u, kw in calls] == [
            "first", "second"
        ]

    @pytest.mark.asyncio
    async def test_an_unset_token_still_sends_the_key(self, monkeypatch):
        """Fail-closed on the server side needs the key present, not absent —
        an absent header and a wrong one must both be a 401, not a 422."""
        monkeypatch.delenv("INTERNAL_SERVICE_TOKEN", raising=False)
        calls = _patch(monkeypatch, battle_engine, _engine_router)
        await battle_engine.fetch_full_attributes(11)
        assert calls[0][1]["headers"]["X-Internal-Token"] == ""


# ═══════════════════════════════════════════════════════════════════════════
# battle_engine.fetch_weapons -> I2i + I3i
# ═══════════════════════════════════════════════════════════════════════════

class TestFetchWeapons:

    @pytest.mark.asyncio
    async def test_the_equipment_read_targets_the_internal_twin(
        self, monkeypatch, token_env
    ):
        calls = _patch(monkeypatch, battle_engine, _engine_router)
        await battle_engine.fetch_weapons(11)
        equipment = [u for u, _ in calls if u.endswith("/equipment")]
        assert equipment == [
            "http://inventory-service:8004"
            "/inventory/internal/characters/11/equipment"
        ], calls

    @pytest.mark.asyncio
    async def test_the_item_read_targets_the_internal_twin(
        self, monkeypatch, token_env
    ):
        """The public `/inventory/items/{id}` is now the THIN card: a drift
        back there returns 200 with no `damage_modifier` at all, and the
        weapon silently stops hitting."""
        calls = _patch(monkeypatch, battle_engine, _engine_router)
        await battle_engine.fetch_weapons(11)
        items = [u for u, _ in calls if "/items/" in u]
        assert items == [
            "http://inventory-service:8004/inventory/internal/items/331"
        ], calls

    @pytest.mark.asyncio
    async def test_every_call_carries_the_token(self, monkeypatch, token_env):
        calls = _patch(monkeypatch, battle_engine, _engine_router)
        await battle_engine.fetch_weapons(11)
        assert calls, "fetch_weapons made no request at all"
        for url, kwargs in calls:
            assert kwargs["headers"]["X-Internal-Token"] == TOKEN, url

    @pytest.mark.asyncio
    async def test_no_call_goes_to_a_player_facing_path(self, monkeypatch, token_env):
        calls = _patch(monkeypatch, battle_engine, _engine_router)
        await battle_engine.fetch_weapons(11)
        for url, _ in calls:
            assert "/inventory/internal/" in url, f"anonymous path survived: {url}"

    @pytest.mark.asyncio
    async def test_the_effective_damage_still_comes_from_the_slot(
        self, monkeypatch, token_env
    ):
        """FEAT-167: the slot, not the template, owns the weapon's damage. The
        twin must keep serving it or the engine reads 0.0."""
        _patch(monkeypatch, battle_engine, _engine_router)
        weapons = await battle_engine.fetch_weapons(11)
        assert weapons["main_weapon"]["effective_damage"] == 42.0
        assert weapons["additional_weapons"] is None

    @pytest.mark.asyncio
    async def test_fetch_main_weapon_goes_through_the_same_path(
        self, monkeypatch, token_env
    ):
        calls = _patch(monkeypatch, battle_engine, _engine_router)
        await battle_engine.fetch_main_weapon(11)
        for url, kwargs in calls:
            assert "/internal/" in url
            assert kwargs["headers"]["X-Internal-Token"] == TOKEN


# ═══════════════════════════════════════════════════════════════════════════
# skills_client.get_item -> I3i  (the call site §2.7 missed)
# ═══════════════════════════════════════════════════════════════════════════

class TestSkillsClientItemLookup:
    """Two different header positions live in this one module: the skills
    reads put the secret in `Authorization: Bearer`, this one puts it in
    `X-Internal-Token`. Mixing them up produces a 401 that looks like a
    missing item."""

    @pytest.mark.asyncio
    async def test_targets_the_internal_twin_with_the_header(
        self, monkeypatch, token_env
    ):
        calls = _patch(
            monkeypatch, skills_client, lambda url: _Resp(200, dict(ITEM_TEMPLATE))
        )
        await skills_client.get_item(331)
        url, kwargs = calls[0]
        assert url.endswith("/inventory/internal/items/331"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN

    @pytest.mark.asyncio
    async def test_it_does_not_use_the_bearer_position_for_this_one(
        self, monkeypatch, token_env
    ):
        calls = _patch(
            monkeypatch, skills_client, lambda url: _Resp(200, dict(ITEM_TEMPLATE))
        )
        await skills_client.get_item(331)
        assert "Authorization" not in calls[0][1]["headers"]

    @pytest.mark.asyncio
    async def test_the_token_is_read_at_call_time(self, monkeypatch):
        calls = _patch(
            monkeypatch, skills_client, lambda url: _Resp(200, dict(ITEM_TEMPLATE))
        )
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        await skills_client.get_item(331)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        await skills_client.get_item(331)
        assert [kw["headers"]["X-Internal-Token"] for _u, kw in calls] == [
            "first", "second"
        ]

    @pytest.mark.asyncio
    async def test_a_bad_id_never_reaches_the_network(self, monkeypatch, token_env):
        calls = _patch(
            monkeypatch, skills_client, lambda url: _Resp(200, dict(ITEM_TEMPLATE))
        )
        with pytest.raises(ValueError):
            await skills_client.get_item(0)
        assert calls == []


# ═══════════════════════════════════════════════════════════════════════════
# The assertions above must bite — a source sweep with no allowlist
# ═══════════════════════════════════════════════════════════════════════════

class TestNoAnonymousReadSurvivesInTheSource:
    """The per-call tests only cover the call sites we know about. This sweep
    reads the two source files and fails on any *remaining* read of a route
    FEAT-171 gated — a new call site added tomorrow is caught without anyone
    remembering to extend the list above."""

    @staticmethod
    def _source(filename):
        with open(os.path.join(_APP_DIR, filename), encoding="utf-8") as fh:
            return fh.read()

    @pytest.mark.parametrize(
        "filename", ["battle_engine.py", "skills_client.py", "inventory_client.py"]
    )
    def test_no_attributes_or_inventory_read_is_missing_internal(self, filename):
        import re

        source = self._source(filename)
        # Every f-string URL aimed at attributes-service or inventory-service.
        urls = re.findall(
            r'f"\{[A-Za-z_\.]*(?:ATTR_SERVICE_URL|ATTRIBUTES_SERVICE_URL|'
            r'INVENTORY_SERVICE_URL|INVENTORY_URL|BASE)\}([^"]*)"',
            source,
        )
        assert urls, f"the sweep matched no URL in {filename} — it went blind"
        offenders = [
            u for u in urls
            if ("/attributes/" in u or "/inventory/" in u)
            and "/internal/" not in u
        ]
        assert offenders == [], (
            f"{filename} still reads a FEAT-171-gated route anonymously: {offenders}"
        )

    def test_the_sweep_really_catches_a_public_path(self):
        """Red-proof for the sweep itself: the same matcher run over a sample
        that *does* contain the old anonymous path must flag it."""
        import re

        sample = 'f"{INVENTORY_SERVICE_URL}/inventory/items/{item_id}"'
        urls = re.findall(
            r'f"\{[A-Za-z_\.]*(?:ATTR_SERVICE_URL|ATTRIBUTES_SERVICE_URL|'
            r'INVENTORY_SERVICE_URL|INVENTORY_URL|BASE)\}([^"]*)"',
            sample,
        )
        offenders = [u for u in urls if "/inventory/" in u and "/internal/" not in u]
        assert offenders == ["/inventory/items/{item_id}"]

    def test_the_sweep_covers_every_client_module_that_leaves_the_service(self):
        """Guard on the guard: if a new `*_client.py` appears, it must be added
        to the parametrisation above rather than silently escaping the sweep."""
        clients = sorted(
            name for name in os.listdir(_APP_DIR)
            if name.endswith("_client.py") or name == "battle_engine.py"
        )
        assert clients == [
            "battle_engine.py", "character_client.py",
            "inventory_client.py", "mongo_client.py", "skills_client.py",
        ], (
            "a new outgoing client module appeared — add it to the sweep "
            f"parametrisation: {clients}"
        )
