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
    """Every call in autobattle-service that targets a `/battles/internal/`
    path must pass `internal_token_headers()`. Adding a new one without the
    header fails here."""

    GATED = ("/battles/internal/",)
    FILES = ("clients.py", "main.py", "strategy.py", "tasks.py")

    def test_all_gated_calls_carry_the_header(self):
        offenders = []
        for filename in self.FILES:
            path = os.path.join(APP_DIR, filename)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as fh:
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
                            "internal_token_headers()" not in window
                            and "X-Internal-Token" not in window
                        ):
                            offenders.append(f"{filename}:{line_no + 1} -> {gated}")
                    idx += len(gated)
        assert not offenders, (
            "gated call(s) without the internal header: " + "; ".join(offenders)
        )
