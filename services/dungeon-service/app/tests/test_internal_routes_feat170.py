"""
FEAT-170 T14 — the two `/dungeons/internal/*` routes are gated now.

    GET  /dungeons/internal/character-session/{character_id}   (main.py:735)
    POST /dungeons/internal/battle-callback                    (main.py:755)

Neither route had **any** HTTP test before this feature (§2.8 lists both under
"routes with no HTTP test at all today"), so a 401 regression — or a gate that
answers 401 *after* doing the work — would have been invisible.

Two things beyond the plain 401/503 matrix:

  * **`battle-callback` mutates dungeon session state**: it marks a room
    cleared, applies casualties and advances the session
    (`gameplay.process_battle_completion`, and `session_state.clear_active_battle`
    on the cleanup path). Every rejected call here is therefore checked against
    the mutators: a guard that rejects after writing fails
    `TestBattleCallbackRejectionsTouchNothing`.

  * **The guard captures the token in a module-level constant at import**
    (`auth_http.INTERNAL_SERVICE_TOKEN`). `monkeypatch.setenv` alone changes
    nothing — every test here pins the module attribute, which is the
    FEAT-162/167 precedent.

Nothing in this file needs a live DB, Redis, battle-service or locations-service:
the session-state and gameplay calls are patched, and `get_db` is the conftest
SQLite override.
"""

import pytest

import auth_http
import main


TOKEN = "test-internal-token"
HEADERS = {"X-Internal-Token": TOKEN}
WRONG_HEADERS = {"X-Internal-Token": "not-the-token"}

NO_TOKEN_DETAIL = "Недействительный internal token"
UNCONFIGURED_DETAIL = "Internal service token не настроен"

CALLBACK_BODY = {"battle_id": 77, "session_id": 100, "defeated_characters": []}


@pytest.fixture()
def token(monkeypatch):
    """The guard compares against a constant captured at import time."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


@pytest.fixture()
def no_token(monkeypatch):
    """`INTERNAL_SERVICE_TOKEN` missing from the environment -> fail closed."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")


class _Spy:
    """Records every call; returns a canned value."""

    def __init__(self, result=None):
        self.calls = []
        self.result = result

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


@pytest.fixture()
def session_spy(monkeypatch):
    """Patch the only read the character-session route performs."""
    spy = _Spy(result=42)
    monkeypatch.setattr(main.session_state, "get_character_active_session", spy)
    return spy


@pytest.fixture()
def callback_spies(monkeypatch):
    """Patch every function `battle_callback` reads or mutates.

    `process_battle_completion` and `clear_active_battle` are the mutators —
    they are what "the dungeon session was advanced" means. `get_session_state`
    is the first thing the handler touches, so it doubles as a tripwire: if the
    guard ran too late, it would have been called.
    """
    spies = {
        "get_session_state": _Spy(result={"active_battle_id": 77}),
        "clear_active_battle": _Spy(result=None),
        "process_battle_completion": _Spy(result={"room_cleared": True}),
        "get_battle_state": _Spy(result={"battle_id": 77, "status": "finished"}),
    }
    monkeypatch.setattr(main.session_state, "get_session_state", spies["get_session_state"])
    monkeypatch.setattr(main.session_state, "clear_active_battle", spies["clear_active_battle"])
    monkeypatch.setattr(main.gameplay, "process_battle_completion", spies["process_battle_completion"])
    monkeypatch.setattr(main.http_clients, "get_battle_state", spies["get_battle_state"])
    return spies


def _assert_untouched(spies):
    offenders = [name for name, spy in spies.items() if spy.calls]
    assert not offenders, (
        "the guard rejected the request but the handler had already run: "
        + ", ".join(sorted(offenders))
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. GET /dungeons/internal/character-session/{character_id}
# ══════════════════════════════════════════════════════════════════════════════


class TestCharacterSessionGate:

    async def test_no_header_is_401(self, no_auth_client, token, session_spy):
        resp = await no_auth_client.get("/dungeons/internal/character-session/11")
        assert resp.status_code == 401
        assert resp.json()["detail"] == NO_TOKEN_DETAIL
        assert not session_spy.calls, "the route answered 401 but still read the session"

    async def test_wrong_header_is_401(self, no_auth_client, token, session_spy):
        resp = await no_auth_client.get(
            "/dungeons/internal/character-session/11", headers=WRONG_HEADERS,
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == NO_TOKEN_DETAIL
        assert not session_spy.calls

    async def test_correct_header_runs_the_route(self, no_auth_client, token, session_spy):
        resp = await no_auth_client.get(
            "/dungeons/internal/character-session/11", headers=HEADERS,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"in_dungeon": True, "session_id": 42}
        assert session_spy.calls == [((11,), {})]

    async def test_correct_header_no_active_session(self, no_auth_client, token, monkeypatch):
        monkeypatch.setattr(
            main.session_state, "get_character_active_session", _Spy(result=None),
        )
        resp = await no_auth_client.get(
            "/dungeons/internal/character-session/11", headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json() == {"in_dungeon": False, "session_id": None}

    async def test_empty_token_is_503(self, no_auth_client, no_token, session_spy):
        """Fail-closed: an unconfigured secret must never *disable* the check."""
        resp = await no_auth_client.get(
            "/dungeons/internal/character-session/11", headers=HEADERS,
        )
        assert resp.status_code == 503
        assert resp.json()["detail"] == UNCONFIGURED_DETAIL
        assert not session_spy.calls


# ══════════════════════════════════════════════════════════════════════════════
# 2. POST /dungeons/internal/battle-callback
# ══════════════════════════════════════════════════════════════════════════════


class TestBattleCallbackGate:

    async def test_no_header_is_401(self, no_auth_client, token, callback_spies):
        resp = await no_auth_client.post(
            "/dungeons/internal/battle-callback", json=CALLBACK_BODY,
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == NO_TOKEN_DETAIL

    async def test_wrong_header_is_401(self, no_auth_client, token, callback_spies):
        resp = await no_auth_client.post(
            "/dungeons/internal/battle-callback",
            json=CALLBACK_BODY,
            headers=WRONG_HEADERS,
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == NO_TOKEN_DETAIL

    async def test_empty_token_is_503(self, no_auth_client, no_token, callback_spies):
        resp = await no_auth_client.post(
            "/dungeons/internal/battle-callback",
            json=CALLBACK_BODY,
            headers=HEADERS,
        )
        assert resp.status_code == 503
        assert resp.json()["detail"] == UNCONFIGURED_DETAIL

    async def test_correct_header_processes_the_callback(
        self, no_auth_client, token, callback_spies,
    ):
        resp = await no_auth_client.post(
            "/dungeons/internal/battle-callback",
            json=CALLBACK_BODY,
            headers=HEADERS,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "status": "processed", "results": {"room_cleared": True},
        }
        assert callback_spies["process_battle_completion"].calls, (
            "the guard passed but the session was never advanced"
        )

    async def test_correct_header_unknown_session_is_404_not_401(
        self, no_auth_client, token, monkeypatch, callback_spies,
    ):
        """A legitimate handler-level rejection — the point is that a valid
        token reaches the handler, so the status is the handler's own 404."""
        monkeypatch.setattr(main.session_state, "get_session_state", _Spy(result=None))
        resp = await no_auth_client.post(
            "/dungeons/internal/battle-callback",
            json=CALLBACK_BODY,
            headers=HEADERS,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Сессия подземелья не найдена"

    async def test_correct_header_battle_id_mismatch_is_ignored(
        self, no_auth_client, token, monkeypatch, callback_spies,
    ):
        monkeypatch.setattr(
            main.session_state, "get_session_state", _Spy(result={"active_battle_id": 999}),
        )
        resp = await no_auth_client.post(
            "/dungeons/internal/battle-callback",
            json=CALLBACK_BODY,
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ignored", "reason": "battle_id_mismatch"}


class TestBattleCallbackRejectionsTouchNothing:
    """`battle-callback` marks a room cleared and applies casualties. A guard
    that answers 401/503 *after* mutating would still pass a status-code-only
    test — these assertions are what makes that impossible."""

    @pytest.mark.parametrize(
        "headers", [None, WRONG_HEADERS], ids=["no-header", "wrong-header"],
    )
    async def test_401_leaves_the_session_untouched(
        self, no_auth_client, token, callback_spies, headers,
    ):
        resp = await no_auth_client.post(
            "/dungeons/internal/battle-callback",
            json=CALLBACK_BODY,
            headers=headers,
        )
        assert resp.status_code == 401
        _assert_untouched(callback_spies)

    async def test_503_leaves_the_session_untouched(
        self, no_auth_client, no_token, callback_spies,
    ):
        resp = await no_auth_client.post(
            "/dungeons/internal/battle-callback",
            json=CALLBACK_BODY,
            headers=HEADERS,
        )
        assert resp.status_code == 503
        _assert_untouched(callback_spies)

    async def test_a_rejected_call_cannot_even_reach_the_body_validation(
        self, no_auth_client, token, callback_spies,
    ):
        """A malformed body plus no header must still be 401, not 422 — the
        guard runs before anything else, so nothing about the payload leaks."""
        resp = await no_auth_client.post(
            "/dungeons/internal/battle-callback", json={"nonsense": True},
        )
        assert resp.status_code == 401
        _assert_untouched(callback_spies)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Route-table sweep — the check that stays true for routes nobody wrote yet
# ══════════════════════════════════════════════════════════════════════════════


def _flat_dependency_names(dependant):
    """Every dependency of the route, sub-dependencies included.

    `verify_internal_token` is attached through `dependencies=[Depends(...)]`
    today, i.e. at the top level — but a future route could pick it up through
    a wrapper dependency, and that must count as gated too.
    """
    names = set()
    stack = list(dependant.dependencies)
    while stack:
        dep = stack.pop()
        call = getattr(dep, "call", None)
        if call is not None:
            names.add(getattr(call, "__name__", type(call).__name__))
        stack.extend(getattr(dep, "dependencies", []))
    return names


class TestEveryInternalRouteIsGated:

    def test_no_internal_route_is_open(self):
        from fastapi.routing import APIRoute

        offenders = []
        checked = 0
        for route in main.app.routes:
            if not isinstance(route, APIRoute) or "/internal/" not in route.path:
                continue
            checked += 1
            if "verify_internal_token" not in _flat_dependency_names(route.dependant):
                offenders.append(f"{sorted(route.methods)} {route.path}")

        assert checked >= 2, (
            "the sweep stopped finding internal routes — the paths were "
            f"refactored and the check is now empty (found {checked})"
        )
        assert not offenders, (
            "internal route(s) reachable without X-Internal-Token: "
            + "; ".join(offenders)
        )

    def test_the_two_known_routes_are_on_the_gated_list(self):
        """Guard for the sweep itself: if these paths are renamed out of
        recognition the sweep above silently matches nothing."""
        from fastapi.routing import APIRoute

        found = set()
        for route in main.app.routes:
            if not isinstance(route, APIRoute):
                continue
            if "verify_internal_token" not in _flat_dependency_names(route.dependant):
                continue
            for method in route.methods:
                found.add((method, route.path))

        wanted = {
            ("GET", "/dungeons/internal/character-session/{character_id}"),
            ("POST", "/dungeons/internal/battle-callback"),
        }
        assert wanted <= found, f"no longer gated: {sorted(wanted - found)}"
