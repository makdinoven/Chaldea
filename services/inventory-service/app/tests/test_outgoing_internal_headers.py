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


# ---------------------------------------------------------------------------
# FEAT-169 #13/#14 — the perk-reconcile calls
# ---------------------------------------------------------------------------
# `POST /attributes/internal/{cid}/reconcile-perks` is internal-only now.
# Both callers here are warn-and-continue: a dropped header would not raise
# anywhere, perks would simply stop re-evaluating after equip/unequip, and the
# player would just quietly lose (or keep) a perk. So the header VALUE is
# asserted on the real client functions, never a re-implementation.


class TestReconcilePerksHeader:

    def test_sync_reconcile_sends_the_token(self, monkeypatch, token_env):
        calls = []

        def _post(url, **kwargs):
            calls.append((url, kwargs))
            return _Resp()

        monkeypatch.setattr(main.httpx, "post", _post)
        main._reconcile_perks(11)

        url, kwargs = calls[0]
        assert url.endswith("/attributes/internal/11/reconcile-perks"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "inventory-service dropped X-Internal-Token on reconcile-perks — "
            "perks would silently stop re-evaluating after equip/unequip"
        )

    @pytest.mark.asyncio
    async def test_async_reconcile_sends_the_token(self, monkeypatch, token_env):
        calls = _patch_client(monkeypatch)
        await main._reconcile_perks_async(12)

        url, kwargs = calls[0]
        assert url.endswith("/attributes/internal/12/reconcile-perks"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN

    def test_sync_token_is_read_at_call_time(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            main.httpx, "post",
            lambda url, **kw: (calls.append((url, kw)), _Resp())[1])

        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        main._reconcile_perks(1)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        main._reconcile_perks(1)

        assert [c[1]["headers"]["X-Internal-Token"] for c in calls] == \
            ["first", "second"]

    @pytest.mark.asyncio
    async def test_async_token_is_read_at_call_time(self, monkeypatch):
        calls = _patch_client(monkeypatch)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        await main._reconcile_perks_async(1)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        await main._reconcile_perks_async(1)

        assert [c[1]["headers"]["X-Internal-Token"] for c in calls] == \
            ["first", "second"]

    def test_dropping_the_header_would_be_caught(self, monkeypatch, token_env):
        """Negative control for every assertion in this file.

        If a future edit removed `headers=_internal_token_headers()` from the
        call, the observable difference is the header — not the call count.
        This test proves the assertions above are actually sensitive to it.
        """
        calls = []
        monkeypatch.setattr(
            main.httpx, "post",
            lambda url, **kw: (calls.append((url, kw)), _Resp())[1])
        monkeypatch.setattr(main, "_internal_token_headers", dict)

        main._reconcile_perks(1)

        assert len(calls) == 1, "the call still happens — a count assertion sees nothing"
        assert "X-Internal-Token" not in calls[0][1].get("headers", {}), (
            "the header is the only observable difference, so it is what the "
            "positive tests must assert"
        )


# ---------------------------------------------------------------------------
# FEAT-169 — source sweep: no internal call may lose its header
# FEAT-170 — the sweep is now INVERTED: there is no allowlist any more
# ---------------------------------------------------------------------------
# The per-call tests above pin the call sites that exist today. This sweep
# covers the ones nobody has written yet: any call in this service whose URL
# points at another service's `/internal/` route must pass `headers=`.
#
# Until FEAT-170 this class carried `_KNOWN_UNGATED_TARGETS`, an allowlist that
# exempted `POST /locations/quests/internal/auto-progress` because that route
# was still open. FEAT-170 gated it, so the allowlist was **deleted**, not
# extended — an allowlist-based sweep passes for the wrong reason the moment a
# target is gated, and this one carried an explicit FEAT-170 to-do marker
# saying exactly that. The rule now has no exceptions: *any* resolved URL
# containing `/internal/` must pass `headers=`.


class TestEveryInternalCallSiteSendsHeaders:
    """Any call in this service aimed at another service's `/internal/` route
    must pass `headers=`. Variable URLs (`url = f"..."` one line above the
    call) are resolved, because that is how most of the call sites are written.

    Scanned files: every module of `app/` that can make an outgoing call
    (FEAT-170 §3.12 d — `main.py` alone is no longer enough).
    """

    #: no allowlist — see the module comment above (FEAT-170).
    SCANNED_FILES = ("main.py", "crud.py", "auth_http.py")

    def _segment(self, node):
        """`ast.get_source_segment` without its per-call `splitlines()`.

        The stdlib helper re-splits the whole module for every node, which is
        quadratic over these four-thousand-line files. Offsets are UTF-8
        **byte** offsets (the sources are full of Cyrillic strings), so the
        slicing is done on encoded lines.
        """
        if getattr(node, "lineno", None) is None:
            return ""
        lines = self._blines
        start, end = node.lineno - 1, node.end_lineno - 1
        if start == end:
            return lines[start][node.col_offset:node.end_col_offset].decode(
                "utf-8", "replace")
        parts = [lines[start][node.col_offset:]]
        parts.extend(lines[start + 1:end])
        parts.append(lines[end][:node.end_col_offset])
        return b"\n".join(parts).decode("utf-8", "replace")

    def _resolve(self, source, tree):
        """{function name: {variable: assigned source}} for simple `x = expr`."""
        import ast

        env = {}
        segment = self._segment

        class _V(ast.NodeVisitor):
            def _scope(self, node):
                local = {}
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Assign) and len(sub.targets) == 1 \
                            and isinstance(sub.targets[0], ast.Name):
                        local[sub.targets[0].id] = segment(sub.value)
                env[(node.lineno, node.end_lineno)] = local
                self.generic_visit(node)

            visit_FunctionDef = _scope
            visit_AsyncFunctionDef = _scope

        _V().visit(tree)
        return env

    def _url_of(self, source, env, node):
        import ast

        raw = self._segment(node.args[0]) if node.args else ""
        raw = raw or ""
        if "/" in raw:
            return raw
        # a URL-building helper — `_reconcile_perks_url(cid)`: inline its return
        if node.args and isinstance(node.args[0], ast.Call) \
                and isinstance(node.args[0].func, ast.Name):
            builder = node.args[0].func.id
            for sub in ast.walk(self._tree):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and sub.name == builder:
                    for inner in ast.walk(sub):
                        if isinstance(inner, ast.Return) and inner.value is not None:
                            return self._segment(inner.value) or raw
        # a bare name — look it up in the innermost enclosing function
        scopes = [(end - start, local) for (start, end), local in env.items()
                  if start <= node.lineno <= end]
        scopes.sort(key=lambda pair: pair[0])
        for _, local in scopes:
            if raw in local:
                return local[raw]
        return raw

    def _sweep(self):
        """Return `(checked, offenders)` over every scanned file."""
        import ast

        offenders = []
        checked = 0
        for filename in self.SCANNED_FILES:
            path = os.path.join(_APP_DIR, filename)
            if not os.path.exists(path):
                continue
            source = open(path, encoding="utf-8").read()
            tree = ast.parse(source)
            self._source, self._tree = source, tree
            self._blines = [line.encode("utf-8") for line in source.splitlines()]
            env = self._resolve(source, tree)

            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)):
                    continue
                if node.func.attr not in ("post", "put", "patch", "delete", "get"):
                    continue
                base = self._segment(node.func.value)
                if base not in ("httpx", "client", "requests"):
                    continue
                url = self._url_of(source, env, node)
                # `internal/` rather than `/internal/`: several URLs are built
                # as f"{SERVICE_URL}internal/…" because the setting already
                # ends with a slash (main.py:852, :3491).
                if "internal/" not in url:
                    continue
                checked += 1
                if "headers" not in {kw.arg for kw in node.keywords}:
                    offenders.append(
                        f"{filename}:{node.lineno} {base}.{node.func.attr}"
                        f"({url[:70]}) без headers="
                    )
        return checked, offenders

    def test_no_internal_call_is_missing_headers(self):
        checked, offenders = self._sweep()

        # Floor raised from 4 to 5 by FEAT-170: the allowlist that hid
        # `/locations/quests/internal/auto-progress` is gone, so that call site
        # is now inspected like every other one.
        assert checked >= 5, (
            "свип перестал находить внутренние вызовы — URL отрефакторили, "
            f"и проверка стала пустой (найдено {checked})"
        )
        assert not offenders, (
            "межсервисный вызов на /internal/ без X-Internal-Token — целевой "
            "маршрут ответит 401, а вызывающий это проглотит: "
            + "; ".join(offenders)
        )

    def test_the_sweep_has_no_allowlist(self):
        """FEAT-170: pin the inversion itself.

        An allowlist here would make the sweep pass for the wrong reason — the
        exempted target is exactly the one most likely to be freshly gated. If
        someone reintroduces one, this fails and points them at the rule.
        """
        assert not hasattr(self, "_KNOWN_UNGATED_TARGETS"), (
            "the FEAT-170 inversion was undone — an internal target was "
            "allowlisted out of the sweep again"
        )
        attrs = {name for name, value in vars(type(self)).items()
                 if isinstance(value, (tuple, list, set, frozenset))
                 and any(word in name.upper()
                         for word in ("UNGATED", "ALLOW", "EXEMPT", "SKIP"))}
        assert not attrs, f"allowlist reintroduced into the sweep: {attrs}"

    def test_the_quest_auto_progress_call_is_inside_the_sweep(self):
        """The formerly-allowlisted call site must now actually be inspected —
        otherwise deleting the allowlist changed nothing."""
        import ast

        source = open(os.path.join(_APP_DIR, "main.py"), encoding="utf-8").read()
        tree = ast.parse(source)
        self._source, self._tree = source, tree
        self._blines = [line.encode("utf-8") for line in source.splitlines()]
        env = self._resolve(source, tree)

        seen = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in ("post", "put", "patch", "delete", "get"):
                continue
            if self._segment(node.func.value) not in (
                    "httpx", "client", "requests"):
                continue
            url = self._url_of(source, env, node)
            if "/locations/quests/internal/auto-progress" in url:
                seen.append(node.lineno)
        assert seen, (
            "the quest auto-progress call site vanished from main.py — the "
            "sweep can no longer prove it carries X-Internal-Token"
        )

    def test_the_known_internal_call_sites_are_still_there(self):
        """Guard for the sweep itself: if the URLs are refactored out of
        recognition the sweep silently matches nothing."""
        source = open(os.path.join(_APP_DIR, "main.py"), encoding="utf-8").read()
        assert "internal/{character_id}/satiety" in source
        assert "internal/{character_id}/reconcile-perks" in source
        assert "/locations/quests/internal/auto-progress" in source
        assert source.count("_internal_token_headers()") >= 6


# ---------------------------------------------------------------------------
# FEAT-170 — `POST /locations/quests/internal/auto-progress` is gated now
# ---------------------------------------------------------------------------
# `_add_item_to_inventory_core` (main.py) fires quest auto-progress after every
# collect/grant. The call is wrapped in `except Exception: logger.warning(...)`,
# so a missing header produces a 401 that **nothing** observes: the item still
# lands in the bag, the request still returns 200, and the player's "collect N
# ore" objective simply never moves. The header value is therefore asserted on
# the real function — "nothing raised" would pass even with the header gone,
# which is what `test_quest_auto_progress_without_the_header_is_invisible`
# below demonstrates.


class TestQuestAutoProgressCallCarriesTheToken:

    @staticmethod
    def _fake_db(max_stack_size=10):
        from unittest.mock import MagicMock

        item_row = MagicMock()
        item_row.max_stack_size = max_stack_size

        query = MagicMock()
        query.filter.return_value.first.return_value = item_row
        query.filter.return_value.all.return_value = []

        db = MagicMock()
        db.query.return_value = query
        return db

    def _run(self, monkeypatch, quantity=3):
        """Call the real `_add_item_to_inventory_core`, recording every POST."""
        calls = []
        monkeypatch.setattr(
            main.httpx, "post",
            lambda url, **kw: (calls.append((url, kw)), _Resp())[1])

        main._add_item_to_inventory_core(
            character_id=31,
            item_data=main.schemas.InventoryItem(item_id=77, quantity=quantity),
            db=self._fake_db(),
        )
        return calls

    def test_collect_sends_the_token(self, monkeypatch, token_env):
        calls = self._run(monkeypatch)

        progress = [c for c in calls if "auto-progress" in c[0]]
        assert progress, "the collect event never reached locations-service"
        url, kwargs = progress[0]
        assert url.endswith("/locations/quests/internal/auto-progress"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "inventory-service dropped X-Internal-Token on quest "
            "auto-progress — the caller only logs a WARNING, so collect "
            "objectives would silently stop advancing"
        )
        assert kwargs["json"] == {
            "character_id": 31,
            "event_type": "collect",
            "increment": 3,
            "target_id": 77,
        }

    def test_the_token_is_read_at_call_time(self, monkeypatch):
        """`main._internal_token_headers` reads env per call, so a rotated
        secret must reach the next call without a restart."""
        calls = []
        monkeypatch.setattr(
            main.httpx, "post",
            lambda url, **kw: (calls.append((url, kw)), _Resp())[1])

        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        main._add_item_to_inventory_core(
            31, main.schemas.InventoryItem(item_id=77, quantity=1), self._fake_db())
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        main._add_item_to_inventory_core(
            31, main.schemas.InventoryItem(item_id=77, quantity=1), self._fake_db())

        sent = [kw["headers"]["X-Internal-Token"]
                for url, kw in calls if "auto-progress" in url]
        assert sent == ["first", "second"]

    def test_quest_auto_progress_without_the_header_is_invisible(
            self, monkeypatch, token_env):
        """Negative control — proves the assertion above actually bites.

        With the header helper neutered the call still happens, still carries
        the right URL and the right body, and still raises nothing. Only the
        header differs, so only a header assertion can catch a regression here.
        """
        monkeypatch.setattr(main, "_internal_token_headers", dict)
        calls = self._run(monkeypatch)

        progress = [c for c in calls if "auto-progress" in c[0]]
        assert len(progress) == 1, (
            "the call still happens — a call-count assertion sees nothing")
        assert "X-Internal-Token" not in progress[0][1].get("headers", {})
