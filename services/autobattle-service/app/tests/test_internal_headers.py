"""
FEAT-169 (QA task #18) — autobattle-service must send `X-Internal-Token` on its
calls into `/battles/internal/*`.

Those battle-service routes are **not gated yet** (§3.10 item 3 keeps them for a
later sweep), so the header is inert today. That is exactly why this file
exists: autobattle drives every mob turn and every auto-clicked player turn
through `/battles/internal/{id}/state` and `/action`, and the eventual gating of
that prefix must not kill auto-battle silently. The helper and the env var were
added on spec (§3.6); these assertions keep them from being "cleaned up" as
unused before the gate arrives.

`get_character_owner` hits a public character-service route and is pinned the
other way: it must keep sending nothing.

Everything runs against the real `clients.*` functions with `httpx.AsyncClient`
patched. autobattle-service's pytest run has **no** `--asyncio-mode=auto`, so
every coroutine test carries an explicit `@pytest.mark.asyncio`.
"""

import importlib.util
import os

import pytest


APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load_real_clients():
    """Import `clients.py` from disk under a private module name.

    Four autobattle test modules park a `MagicMock` in `sys.modules["clients"]`
    (`test_autobattle_auth.py:41`, `test_endpoint_auth.py:34`,
    `test_handle_turn.py:38`, `test_speed.py:44`), and a header asserted against
    a mock proves nothing. Loading the file directly guarantees these assertions
    run against the production functions whatever collection order pytest picks,
    and leaves the other modules' mock untouched.
    """
    path = os.path.join(APP_DIR, "clients.py")
    spec = importlib.util.spec_from_file_location("_feat169_real_clients", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


clients = _load_real_clients()


TOKEN = "test-internal-token"


@pytest.fixture()
def token_env(monkeypatch):
    """`internal_token_headers()` reads the env at call time."""
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = {} if payload is None else payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


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

        async def get(self, url, **kwargs):
            calls.append(("GET", url, kwargs))
            return resp

        async def post(self, url, **kwargs):
            calls.append(("POST", url, kwargs))
            return resp

    monkeypatch.setattr(clients.httpx, "AsyncClient", _Client)
    return calls


class TestGetBattleState:

    @pytest.mark.asyncio
    async def test_sends_the_internal_token(self, monkeypatch, token_env):
        state = {"turn_number": 3, "participants": {}}
        calls = _patch_client(monkeypatch, _Resp(200, state))

        assert await clients.get_battle_state(42) == state

        assert len(calls) == 1
        verb, url, kwargs = calls[0]
        assert verb == "GET"
        assert url.endswith("/battles/internal/42/state"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "autobattle dropped X-Internal-Token on /battles/internal/{id}/state "
            "— the day that prefix is gated, every mob turn would 401 and "
            "auto-battle would stall with no player-visible error"
        )


class TestPostBattleAction:

    @pytest.mark.asyncio
    async def test_sends_the_internal_token(self, monkeypatch, token_env):
        payload = {"character_id": 7, "action": "attack", "target_id": 2}
        calls = _patch_client(monkeypatch, _Resp(200, {"ok": True}))

        assert await clients.post_battle_action(42, payload) == {"ok": True}

        assert len(calls) == 1
        verb, url, kwargs = calls[0]
        assert verb == "POST"
        assert url.endswith("/battles/internal/42/action"), url
        assert kwargs["headers"]["X-Internal-Token"] == TOKEN, (
            "autobattle dropped X-Internal-Token on /battles/internal/{id}/action"
        )
        assert kwargs["json"] == payload


class TestTokenIsReadAtCallTime:
    """A module-level constant captured at import would send an empty header in
    a container that received the variable later — two env values must produce
    two different headers."""

    @pytest.mark.asyncio
    async def test_two_env_values_produce_two_headers(self, monkeypatch):
        calls = _patch_client(monkeypatch)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "first")
        await clients.get_battle_state(1)
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "second")
        await clients.get_battle_state(1)
        assert [c[2]["headers"]["X-Internal-Token"] for c in calls] == \
            ["first", "second"]

    @pytest.mark.asyncio
    async def test_missing_token_still_sends_the_key(self, monkeypatch):
        """Fail-closed on the callee side: the key is always present, so a
        misconfiguration surfaces as a clear 401 rather than a mystery."""
        monkeypatch.delenv("INTERNAL_SERVICE_TOKEN", raising=False)
        calls = _patch_client(monkeypatch)
        await clients.get_battle_state(1)
        assert calls[0][2]["headers"]["X-Internal-Token"] == ""


class TestPublicRouteSendsNothing:
    """`GET /characters/{cid}/profile` is a public read; the ownership check in
    autobattle uses it. Pinned so nobody leaks the service token onto a public
    route — and so nobody strips the two real headers above "for symmetry"."""

    @pytest.mark.asyncio
    async def test_get_character_owner_sends_no_header(self, monkeypatch, token_env):
        calls = _patch_client(monkeypatch, _Resp(200, {"user_id": 9}))

        assert await clients.get_character_owner(5) == 9

        verb, url, kwargs = calls[0]
        assert verb == "GET"
        assert url.endswith("/characters/5/profile"), url
        assert "headers" not in kwargs or "X-Internal-Token" not in (
            kwargs.get("headers") or {}
        ), "the ownership lookup targets a public route — no token there"

    @pytest.mark.asyncio
    async def test_unknown_character_returns_none(self, monkeypatch, token_env):
        _patch_client(monkeypatch, _Resp(404, {}))
        assert await clients.get_character_owner(5) is None


class TestEveryInternalCallSiteSendsHeaders:
    """FEAT-170 T15(iii) — the **inverted** sweep.

    This class replaces the FEAT-169 `GATED = ("/battles/internal/",)`
    allowlist, which only ever looked at one prefix and therefore waved through
    a call to any *other* service's internal route. The rule now has no
    exemption list: any call in autobattle-service whose **resolved** URL
    contains `/internal/` must pass `headers=`. Variable URLs (`url = f"..."`
    a line above the call) are resolved with the AST helper from
    `inventory-service/app/tests/test_outgoing_internal_headers.py`.
    """

    FILES = ("main.py", "clients.py", "strategy.py", "tasks.py")

    #: Floor so that a URL refactor cannot silently empty the sweep — the two
    #: `clients.py` calls (`/battles/internal/{id}/state` and `/action`) that
    #: drive every mob turn and every auto-played player turn.
    MIN_CHECKED = 2

    def _resolve(self, source, tree):
        """{(start, end) of a function: {variable: assigned source}}."""
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

    def _url_of(self, source, tree, env, node):
        import ast

        raw = ast.get_source_segment(source, node.args[0]) if node.args else ""
        raw = raw or ""
        if "/" in raw:
            return raw
        # a URL-building helper — inline its return
        if node.args and isinstance(node.args[0], ast.Call) \
                and isinstance(node.args[0].func, ast.Name):
            builder = node.args[0].func.id
            for sub in ast.walk(tree):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and sub.name == builder:
                    for inner in ast.walk(sub):
                        if isinstance(inner, ast.Return) and inner.value is not None:
                            return ast.get_source_segment(source, inner.value) or raw
        # a bare name — look it up in the innermost enclosing function
        scopes = [(end - start, local) for (start, end), local in env.items()
                  if start <= node.lineno <= end]
        scopes.sort(key=lambda pair: pair[0])
        for _, local in scopes:
            if raw in local:
                return local[raw]
        return raw

    def _sweep(self):
        import ast

        offenders, checked = [], []
        for filename in self.FILES:
            path = os.path.join(APP_DIR, filename)
            if not os.path.exists(path):
                continue
            source = open(path, encoding="utf-8").read()
            tree = ast.parse(source)
            env = self._resolve(source, tree)

            # `@app.post("/internal/register")` is a route *declaration*, not
            # an outgoing call — skip every decorator expression.
            decorators = set()
            for owner in ast.walk(tree):
                if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    decorators.update(id(d) for d in owner.decorator_list)

            for node in ast.walk(tree):
                if id(node) in decorators:
                    continue
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)):
                    continue
                if node.func.attr not in ("get", "post", "put", "patch", "delete"):
                    continue
                url = self._url_of(source, tree, env, node)
                if "/internal/" not in url:
                    continue
                base = ast.get_source_segment(source, node.func.value)
                where = f"{filename}:{node.lineno} {base}.{node.func.attr}"
                checked.append(where)
                if "headers" not in {kw.arg for kw in node.keywords}:
                    offenders.append(f"{where}({url[:70]}) без headers=")
        return checked, offenders

    def test_no_internal_call_is_missing_headers(self):
        checked, offenders = self._sweep()

        assert len(checked) >= self.MIN_CHECKED, (
            "свип перестал находить внутренние вызовы — URL отрефакторили, "
            f"и проверка стала пустой (найдено {len(checked)}, "
            f"ожидалось >= {self.MIN_CHECKED}): {checked}"
        )
        assert not offenders, (
            "межсервисный вызов на /internal/ без X-Internal-Token — боевой "
            "сервис ответит 401 и автобой встанет молча: " + "; ".join(offenders)
        )

    def test_the_sweep_has_no_allowlist(self):
        """FEAT-170: the `GATED` allowlist is gone and must not come back —
        with one, a new internal target passes silently."""
        attrs = {name for name in dir(self) if not name.startswith("test_")}
        forbidden = {"GATED", "KNOWN_UNGATED_TARGETS", "_KNOWN_UNGATED_TARGETS",
                     "EXEMPT", "SKIP", "ALLOWLIST"}
        assert not (attrs & forbidden), (
            "an exemption list crept back into the inverted sweep: "
            f"{sorted(attrs & forbidden)}"
        )

    def test_the_known_internal_call_sites_are_still_there(self):
        """Guard for the sweep itself: if the URLs are refactored out of
        recognition the sweep silently matches nothing."""
        source = open(os.path.join(APP_DIR, "clients.py"), encoding="utf-8").read()
        assert "/battles/internal/{battle_id}/state" in source
        assert "/battles/internal/{battle_id}/action" in source
