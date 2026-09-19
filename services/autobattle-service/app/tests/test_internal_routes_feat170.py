"""
FEAT-170 T14 — `POST /autobattle/internal/register` is gated now (`main.py:136`).

The route registers a participant into the AI driver **with no ownership
check** — that is deliberate (battle-service uses it to drive mobs) and is
exactly why it must never answer without the shared token. Its public twin
`POST /autobattle/register` (`main.py:102`) keeps JWT + ownership and must stay
untouched; the last class in this file pins that.

The route had no HTTP test of its own before this feature beyond one happy-path
line in `test_speed.py`.

Two things beyond the plain 401/503 matrix:

  * **The route mutates in-process registries** — `ALLOWED`, `PID_BATTLE` (and
    the public twin also `SPEED`, `OWNER`), `main.py:119-126`. They are plain
    dicts, so a guard that rejects *after* writing would leave a participant
    registered while answering 401. Every rejected call in
    `TestRejectionsLeaveTheRegistriesUntouched` is checked against a snapshot.

  * **The guard captures the token in a module-level constant at import**
    (`auth_http.INTERNAL_SERVICE_TOKEN`), so `monkeypatch.setenv` alone changes
    nothing — the module attribute is what every test here pins.

No Redis, no battle-service: `aioredis`, `clients` and `strategy` are stubbed
before `main` is imported (the pattern every autobattle test module uses), and
the startup handler is cleared.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, AsyncMock  # noqa: E402

import pytest  # noqa: E402

# Mock aioredis before importing main (it connects on startup)
aioredis_mock = MagicMock()
aioredis_mock.from_url = AsyncMock(return_value=MagicMock())
sys.modules.setdefault("aioredis", aioredis_mock)

# Mock clients module to avoid battle-service HTTP calls
clients_mock = MagicMock()
clients_mock.get_battle_state = AsyncMock(return_value={})
clients_mock.post_battle_action = AsyncMock(return_value={})
clients_mock.get_character_owner = AsyncMock(return_value=None)
sys.modules.setdefault("clients", clients_mock)

# Mock strategy module
sys.modules.setdefault("strategy", MagicMock())

import auth_http  # noqa: E402
import main  # noqa: E402
from main import app, ALLOWED, PID_BATTLE, OWNER, SPEED  # noqa: E402

# Clear startup handlers to prevent Redis connection
app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402


TOKEN = "test-internal-token"
HEADERS = {"X-Internal-Token": TOKEN}
WRONG_HEADERS = {"X-Internal-Token": "not-the-token"}
JWT_HEADERS = {"Authorization": "Bearer jwt-for-user-1"}

NO_TOKEN_DETAIL = "Недействительный internal token"
UNCONFIGURED_DETAIL = "Internal service token не настроен"

USER_1 = {"id": 1, "username": "player", "role": "user", "permissions": []}

BODY = {"participant_id": 50, "battle_id": 0}


def _clear_registries():
    ALLOWED.clear()
    PID_BATTLE.clear()
    OWNER.clear()
    SPEED.clear()


@pytest.fixture(autouse=True)
def clean_registries():
    """The registries are module-level dicts shared by every test module."""
    _clear_registries()
    yield
    _clear_registries()


@pytest.fixture()
def token(monkeypatch):
    """The guard compares against a constant captured at import time."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)
    return TOKEN


@pytest.fixture()
def no_token(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")


def _snapshot():
    return {
        "ALLOWED": set(ALLOWED),
        "PID_BATTLE": dict(PID_BATTLE),
        "OWNER": dict(OWNER),
        "SPEED": dict(SPEED),
    }


def _assert_registries_match(before):
    after = _snapshot()
    assert after == before, (
        "the guard rejected the request but the in-process autobattle "
        f"registries changed: before={before} after={after}"
    )


def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


# ══════════════════════════════════════════════════════════════════════════════
# 1. POST /internal/register — the auth matrix
# ══════════════════════════════════════════════════════════════════════════════


class TestInternalRegisterGate:

    def test_no_header_is_401(self, token):
        with TestClient(app) as client:
            resp = client.post("/internal/register", json=BODY)
        assert resp.status_code == 401
        assert resp.json()["detail"] == NO_TOKEN_DETAIL

    def test_wrong_header_is_401(self, token):
        with TestClient(app) as client:
            resp = client.post("/internal/register", json=BODY, headers=WRONG_HEADERS)
        assert resp.status_code == 401
        assert resp.json()["detail"] == NO_TOKEN_DETAIL

    def test_empty_token_is_503(self, no_token):
        """Fail-closed: an unconfigured secret must never *disable* the check."""
        with TestClient(app) as client:
            resp = client.post("/internal/register", json=BODY, headers=HEADERS)
        assert resp.status_code == 503
        assert resp.json()["detail"] == UNCONFIGURED_DETAIL

    def test_correct_header_registers_the_participant(self, token):
        with TestClient(app) as client:
            resp = client.post("/internal/register", json=BODY, headers=HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"ok": True, "allowed": [50]}
        assert 50 in ALLOWED
        # mobs get no SPEED/OWNER entry — that is the public twin's job
        assert 50 not in SPEED
        assert 50 not in OWNER

    def test_correct_header_with_battle_id_records_the_battle(self, token):
        ctx = {"runtime": {"current_actor": 999}}
        with patch("main.get_battle_state", new_callable=AsyncMock) as state:
            state.return_value = ctx
            with TestClient(app) as client:
                resp = client.post(
                    "/internal/register",
                    json={"participant_id": 51, "battle_id": 7},
                    headers=HEADERS,
                )
        assert resp.status_code == 200, resp.text
        assert PID_BATTLE[51] == 7

    def test_correct_header_with_a_malformed_body_is_422_not_401(self, token):
        """A valid token reaches the handler, so the failure becomes the
        handler's own validation error rather than an auth one."""
        with TestClient(app) as client:
            resp = client.post(
                "/internal/register", json={"participant_id": "nope"}, headers=HEADERS,
            )
        assert resp.status_code == 422


class TestRejectionsLeaveTheRegistriesUntouched:
    """`ALLOWED`, `PID_BATTLE`, `SPEED` and `OWNER` are plain in-process dicts
    (`main.py:119-126`). A guard that writes first and rejects afterwards would
    register a participant anyway — these snapshots make that fail."""

    @pytest.mark.parametrize(
        "headers", [None, WRONG_HEADERS], ids=["no-header", "wrong-header"],
    )
    def test_401_registers_nobody(self, token, headers):
        ALLOWED.add(1)
        PID_BATTLE[1] = 3
        before = _snapshot()

        with TestClient(app) as client:
            resp = client.post("/internal/register", json=BODY, headers=headers)

        assert resp.status_code == 401
        _assert_registries_match(before)
        assert 50 not in ALLOWED

    def test_503_registers_nobody(self, no_token):
        before = _snapshot()

        with TestClient(app) as client:
            resp = client.post("/internal/register", json=BODY, headers=HEADERS)

        assert resp.status_code == 503
        _assert_registries_match(before)
        assert 50 not in ALLOWED


# ══════════════════════════════════════════════════════════════════════════════
# 2. The public twin must not have changed
# ══════════════════════════════════════════════════════════════════════════════


class TestPublicRegisterIsUnchanged:
    """`POST /register` is the browser's path: JWT + ownership, and **no**
    internal token. FEAT-170 must not have leaked the service gate onto it, and
    must not have loosened it either."""

    def test_public_register_still_requires_a_jwt(self, token):
        with TestClient(app) as client:
            resp = client.post("/register", json=BODY)
        assert resp.status_code == 401

    def test_the_internal_token_does_not_unlock_the_public_twin(self, token):
        """Holding the service secret must not be a way around the JWT."""
        with TestClient(app) as client:
            resp = client.post("/register", json=BODY, headers=HEADERS)
        assert resp.status_code == 401
        assert 50 not in ALLOWED

    @patch("auth_http.requests.get")
    def test_public_register_works_with_a_jwt_and_no_internal_token(self, mock_auth, token):
        """The public route must NOT require X-Internal-Token — only the JWT."""
        mock_auth.return_value = _mock_response(200, USER_1)

        with TestClient(app) as client:
            resp = client.post("/register", json=BODY, headers=JWT_HEADERS)

        assert resp.status_code == 200, resp.text
        assert 50 in ALLOWED
        assert OWNER[50] == 1
        assert SPEED[50] == "fast"

    @patch("main.get_character_owner", new_callable=AsyncMock)
    @patch("main.get_battle_state", new_callable=AsyncMock)
    @patch("auth_http.requests.get")
    def test_public_register_still_checks_ownership(
        self, mock_auth, mock_state, mock_owner, token,
    ):
        mock_auth.return_value = _mock_response(200, USER_1)
        mock_state.return_value = {
            "runtime": {"participants": {"50": {"character_id": 900}}, "current_actor": 0},
        }
        mock_owner.return_value = 2  # somebody else's character

        with TestClient(app) as client:
            resp = client.post(
                "/register",
                json={"participant_id": 50, "battle_id": 7},
                headers=JWT_HEADERS,
            )

        assert resp.status_code == 403
        assert 50 not in ALLOWED


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

        assert checked >= 1, (
            "the sweep stopped finding internal routes — the paths were "
            f"refactored and the check is now empty (found {checked})"
        )
        assert not offenders, (
            "internal route(s) reachable without X-Internal-Token: "
            + "; ".join(offenders)
        )

    def test_the_known_route_is_on_the_gated_list(self):
        from fastapi.routing import APIRoute

        found = set()
        for route in main.app.routes:
            if not isinstance(route, APIRoute):
                continue
            if "verify_internal_token" not in _flat_dependency_names(route.dependant):
                continue
            for method in route.methods:
                found.add((method, route.path))

        assert ("POST", "/internal/register") in found, sorted(found)

    def test_the_public_twin_is_not_gated_by_the_internal_token(self):
        from fastapi.routing import APIRoute

        for route in main.app.routes:
            if isinstance(route, APIRoute) and route.path == "/register":
                names = _flat_dependency_names(route.dependant)
                assert "verify_internal_token" not in names, (
                    "the public /register twin must stay JWT-gated, not "
                    "service-token-gated — the browser has no shared secret"
                )
                assert "get_current_user_via_http" in names, names
                break
        else:
            pytest.fail("the public POST /register route disappeared")
