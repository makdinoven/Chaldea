"""
FEAT-167 — inventory-service's own outgoing calls, and the 11 apply-modifier
sites.

Two things are pinned:

1. `apply_modifiers_in_attributes_service` and `recover_in_attributes_service`
   must send `X-Internal-Token`. Both target endpoints are internal-only now, so
   without the header every equip / unequip / sharpen / gem / repair would get a
   401 from character-attributes-service.
2. Every place that applies an *equipped* item's modifiers must be weapon-aware:
   either it passes `slot_type=` into `build_modifiers_dict`, or (for the three
   manually built dicts — sharpening delta, gem socket, gem unsocket) it drops
   the `damage` key for `crud.WEAPON_SLOTS`. A site that forgets is exactly the
   FEAT-167 silent failure: the weapon's damage creeps back into
   `character_attributes.damage`, the profile and the battle disagree again, and
   nothing raises.
"""

import inspect
import os
import re

import pytest

import crud
import main


TOKEN = "test-internal-token"

_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture()
def token_env(monkeypatch):
    """`main._internal_token_headers` reads the env at call time."""
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


class _Resp:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.text = "{}"

    def json(self):
        return {"detail": "ok"}

    def raise_for_status(self):
        return None


def _patch_client(monkeypatch, response=None):
    calls = []
    resp = response or _Resp()

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return resp

    monkeypatch.setattr(main.httpx, "AsyncClient", _Client)
    return calls


class TestOutgoingHeaders:

    @pytest.mark.asyncio
    async def test_apply_modifiers_sends_the_token(self, monkeypatch, token_env):
        calls = _patch_client(monkeypatch)
        await main.apply_modifiers_in_attributes_service(5, {"strength": 10})

        url, kwargs = calls[0]
        assert url.endswith("/attributes/5/apply_modifiers"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "inventory-service dropped X-Internal-Token — equipping anything "
            "would fail with a 401 from character-attributes-service"
        )
        assert kwargs["json"] == {"strength": 10}

    @pytest.mark.asyncio
    async def test_recover_sends_the_token(self, monkeypatch, token_env):
        calls = _patch_client(monkeypatch)
        await main.recover_in_attributes_service(5, {"health_recovery": 10})

        url, kwargs = calls[0]
        assert url.endswith("/attributes/5/recover"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN

    @pytest.mark.asyncio
    async def test_token_is_read_at_call_time(self, monkeypatch):
        calls = _patch_client(monkeypatch)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        await main.apply_modifiers_in_attributes_service(1, {"strength": 1})
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        await main.apply_modifiers_in_attributes_service(1, {"strength": 1})
        assert [c[1]["headers"]["X-Internal-Token"] for c in calls] == \
            ["first", "second"]

    def test_helper_reads_the_env_not_a_frozen_constant(self):
        source = inspect.getsource(main._internal_token_headers)
        assert 'os.environ.get("INTERNAL_SERVICE_TOKEN"' in source


class TestEveryApplySiteIsWeaponAware:
    """The §3.1.2 checklist, enforced instead of reviewed by hand."""

    #: sites that deliberately do not deal with an equipped slot
    _NON_EQUIPMENT_MARKERS = (
        "recovery",          # use_item recovery payload
        "is_food",           # the food payload (display only)
    )

    def _read(self, filename):
        with open(os.path.join(_APP_DIR, filename), encoding="utf-8") as fh:
            return fh.read()

    def test_every_build_modifiers_dict_call_passes_slot_type(self):
        """Except the two display/consumable sites, which have no slot at all."""
        offenders = []
        for filename in ("main.py", "crud.py"):
            source = self._read(filename)
            for match in re.finditer(r"build_modifiers_dict\(", source):
                start = match.end()
                # the call's argument text, up to the matching close paren
                depth = 1
                idx = start
                while idx < len(source) and depth:
                    if source[idx] == "(":
                        depth += 1
                    elif source[idx] == ")":
                        depth -= 1
                    idx += 1
                args = source[start:idx]
                if source[max(0, match.start() - 40):match.start()].strip().endswith("def"):
                    continue  # the definition itself
                if "slot_type=" in args:
                    continue
                line = source.count("\n", 0, match.start()) + 1
                # allow the documented non-equipment sites
                window = source[max(0, match.start() - 600): match.start() + 200]
                if any(marker in window for marker in self._NON_EQUIPMENT_MARKERS):
                    continue
                offenders.append(f"{filename}:{line} args={args.strip()[:80]}")
        assert not offenders, (
            "build_modifiers_dict called for an equipped item without "
            "slot_type= — the weapon's damage leaks into the attribute: "
            + "; ".join(offenders)
        )

    def test_the_manual_modifier_dicts_drop_weapon_damage(self):
        """Sharpening delta, gem socket and gem unsocket build their dict by
        hand; each must strip `damage` for a weapon slot."""
        source = self._read("main.py")
        for marker in ("delta", "gem_only_mods", "gem_neg_mods"):
            pattern = re.compile(
                r"crud\.WEAPON_SLOTS[\s\S]{0,120}?" + re.escape(marker) + r"\.pop\(\"damage\""
            )
            alt = re.compile(
                re.escape(marker) + r"\.pop\(\"damage\"[\s\S]{0,10}\)"
            )
            assert alt.search(source), f"{marker} no longer drops the damage key"
        assert source.count('.pop("damage", None)') >= 3
        assert "crud.WEAPON_SLOTS" in source

    def test_npc_equip_paths_pass_the_slot_type(self):
        """NPC gear goes through `admin_equip_npc_item` / `admin_unequip_npc_item`
        — mobs must not get double damage either."""
        for func in (crud.admin_equip_npc_item, crud.admin_unequip_npc_item):
            source = inspect.getsource(func)
            for match in re.finditer(r"build_modifiers_dict\([^)]*\)", source):
                assert "slot_type=" in match.group(0), (
                    f"{func.__name__}: {match.group(0)}"
                )

    def test_weapon_slots_constant_covers_both_hands(self):
        assert set(crud.WEAPON_SLOTS) == {"main_weapon", "additional_weapons"}


# ---------------------------------------------------------------------------
# FEAT-167 #17 — the cumulative-stats call
# ---------------------------------------------------------------------------
# `POST /attributes/cumulative_stats/increment` is internal-only now.
# `main._track_cumulative_stats` is fire-and-forget (warn-and-continue), so a
# missing header would silently stop crafting/gathering counters — and the perks
# that depend on them — without a single error visible to anyone.


class TestCumulativeStatsHeader:

    def _patch_sync_post(self, monkeypatch):
        calls = []

        def _post(url, **kwargs):
            calls.append((url, kwargs))
            return _Resp()

        monkeypatch.setattr(main.httpx, "post", _post)
        return calls

    def test_track_cumulative_stats_sends_the_token(self, monkeypatch, token_env):
        calls = self._patch_sync_post(monkeypatch)
        main._track_cumulative_stats(5, {"items_crafted": 1})

        url, kwargs = calls[0]
        assert url.endswith("/cumulative_stats/increment"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "inventory-service dropped X-Internal-Token — crafting and "
            "gathering counters (and their perks) would silently stop"
        )
        assert kwargs["json"]["character_id"] == 5

    def test_token_is_read_at_call_time(self, monkeypatch):
        calls = self._patch_sync_post(monkeypatch)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        main._track_cumulative_stats(1, {"items_crafted": 1})
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        main._track_cumulative_stats(1, {"items_crafted": 1})
        assert [c[1]["headers"]["X-Internal-Token"] for c in calls] == \
            ["first", "second"]


class TestCreateInventoryRouteIsGated:
    """`POST /inventory/` (FEAT-167 #18) — the auth matrix lives in
    `test_endpoint_auth.py`; this is the cheap structural guard next to the
    other FEAT-167 sweeps."""

    def test_the_route_requires_the_internal_token(self):
        from fastapi.routing import APIRoute

        for route in main.app.routes:
            if not isinstance(route, APIRoute):
                continue
            if route.path != "/inventory/" or "POST" not in route.methods:
                continue
            names = {
                getattr(dep.call, "__name__", type(dep.call).__name__)
                for dep in route.dependant.dependencies
            }
            assert "verify_internal_token" in names, (
                f"POST /inventory/ is open again: deps={sorted(names)}"
            )
            return
        raise AssertionError("POST /inventory/ is missing from the route table")


# ---------------------------------------------------------------------------
# Review #5 — no blocking HTTP call may sit on the event loop
# ---------------------------------------------------------------------------
# inventory-service runs a SINGLE uvicorn worker. A blocking `httpx.post` inside
# an `async def` handler freezes the whole service for up to its timeout. That
# is not just slow: character-service calls back into this service
# (`/inventory/internal/characters/{cid}/xp-multiplier`) while handling
# `evaluate-titles`, so the callback cannot be served, times out at 5 s and
# fails open to a multiplier of 1.0 — the player silently loses an XP book.
# Review #5 measured 5429 ms for an equip that unlocks a passive-XP title.
#
# Unit tests mock the HTTP boundary and therefore cannot observe the deadlock
# itself (the reviewer said so explicitly). What they CAN do is guarantee the
# shape that makes it impossible: no blocking client call anywhere on an async
# path. That is a static property, so it is checked statically — and it covers
# every future handler, not just the two that were broken.

_BLOCKING_CLIENT_METHODS = {"get", "post", "put", "delete", "patch", "request", "stream"}
# Sync fire-and-forget helpers: fine from a `def` handler (threadpool),
# forbidden from an `async def` one — each has an `_async` twin.
_SYNC_ONLY_HELPERS = {"_track_cumulative_stats", "_reconcile_perks"}


def _main_ast():
    import ast

    source = open(os.path.join(_APP_DIR, "main.py"), encoding="utf-8").read()
    return ast, ast.parse(source)


def _enclosing_functions(ast, tree):
    """[(name, is_async, start, end)] for every function in the module."""
    found = []

    class _V(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            found.append((node.name, False, node.lineno, node.end_lineno))
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node):
            found.append((node.name, True, node.lineno, node.end_lineno))
            self.generic_visit(node)

    _V().visit(tree)
    return found


def _innermost(functions, line):
    matches = [f for f in functions if f[2] <= line <= f[3]]
    matches.sort(key=lambda f: f[3] - f[2])
    return matches[0] if matches else ("<module>", False, 0, 0)


class TestNoBlockingHttpOnTheEventLoop:

    def test_no_blocking_httpx_call_inside_an_async_function(self):
        ast, tree = _main_ast()
        functions = _enclosing_functions(ast, tree)

        offenders = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            module = getattr(node.func.value, "id", None)
            if module not in ("httpx", "requests"):
                continue
            if node.func.attr not in _BLOCKING_CLIENT_METHODS:
                continue
            name, is_async, _, _ = _innermost(functions, node.lineno)
            if is_async:
                offenders.append(f"main.py:{node.lineno} {module}.{node.func.attr}() in async def {name}")

        assert offenders == [], (
            "blocking HTTP call on the event loop — inventory-service has one "
            "uvicorn worker, so this freezes the whole service and deadlocks "
            "the character-service XP-multiplier callback:\n  "
            + "\n  ".join(offenders)
        )

    def test_async_handlers_use_the_async_fire_and_forget_helpers(self):
        ast, tree = _main_ast()
        functions = _enclosing_functions(ast, tree)

        offenders = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id not in _SYNC_ONLY_HELPERS:
                continue
            name, is_async, _, _ = _innermost(functions, node.lineno)
            if is_async:
                offenders.append(
                    f"main.py:{node.lineno} {node.func.id}() in async def {name} "
                    f"— use {node.func.id}_async() instead"
                )

        assert offenders == [], (
            "sync fire-and-forget helper called from an async handler; it makes "
            "a blocking httpx call and freezes the event loop:\n  "
            + "\n  ".join(offenders)
        )

    def test_the_async_twins_exist_and_are_coroutines(self):
        for name in ("_track_cumulative_stats_async", "_reconcile_perks_async",
                     "_evaluate_titles_async"):
            fn = getattr(main, name, None)
            assert fn is not None, f"main.{name} is gone — async handlers have nothing to await"
            assert inspect.iscoroutinefunction(fn), f"main.{name} must be a coroutine function"

    def test_evaluate_titles_goes_through_async_client(self, monkeypatch, token_env):
        """The title call must use AsyncClient — and carry the internal token."""
        import asyncio

        calls = []

        class _FakeAsyncClient:
            def __init__(self, **kwargs):
                calls.append({"init": kwargs})

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, **kwargs):
                calls.append({"url": url, **kwargs})
                return _Resp()

        # Any blocking use would hit this and fail the test loudly.
        def _boom(*a, **kw):
            raise AssertionError("evaluate-titles used a blocking httpx call")

        monkeypatch.setattr(main.httpx, "AsyncClient", _FakeAsyncClient)
        monkeypatch.setattr(main.httpx, "post", _boom)

        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            main._evaluate_titles_async(7, "equip")
        )

        posted = [c for c in calls if "url" in c]
        assert len(posted) == 1, calls
        assert posted[0]["url"].endswith("/characters/internal/evaluate-titles")
        assert posted[0]["json"] == {"character_id": 7}
        assert posted[0]["headers"]["X-Internal-Token"] == TOKEN
