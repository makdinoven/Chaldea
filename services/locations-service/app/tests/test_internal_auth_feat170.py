"""
FEAT-170 — the six locations-service routes that were held open by nginx alone.

Until this feature these answered any request that reached the container, with
no credential at all:

    GET  /locations/quests/internal/check-completed     (read)
    GET  /locations/quests/internal/completed-count     (read)
    POST /locations/internal/gathering-status           (read)
    GET  /locations/internal/action-gate                (read)
    POST /locations/quests/internal/auto-progress       (MUTATOR — pays rewards)
    POST /locations/internal/action-gate/consume        (MUTATOR — burns attempts)

None of the six had an HTTP test of any kind before, so everything here is new
coverage. Contract (FEAT-170 §3.2), identical for all six:

    no header            -> 401 "Недействительный internal token"
    wrong header         -> 401 "Недействительный internal token"
    empty env token      -> 503 "Internal service token не настроен"  (fail-closed)
    correct header       -> the route runs unchanged

For the two mutators every rejection is also checked against the CRUD layer:
the mutating function must never have been called. A guard that answered 401
*after* advancing a quest objective or burning an action gate would pass a
status-code-only test and fail here.

`verify_internal_token` reads a **module-level** constant captured at import
(`main.INTERNAL_SERVICE_TOKEN`, hoisted to the top of `main.py` by FEAT-170
§3.5), so these tests pin the module attribute — `monkeypatch.setenv` alone has
no effect whatsoever.
"""

import os

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

import main
from database import get_db


TOKEN = "test-internal-token"
GOOD_HEADERS = {"X-Internal-Token": TOKEN}
WRONG_HEADERS = {"X-Internal-Token": "not-the-token"}
NO_HEADERS = {}

_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

CHECK_COMPLETED = "/locations/quests/internal/check-completed"
COMPLETED_COUNT = "/locations/quests/internal/completed-count"
AUTO_PROGRESS = "/locations/quests/internal/auto-progress"
GATHERING_STATUS = "/locations/internal/gathering-status"
ACTION_GATE = "/locations/internal/action-gate"
ACTION_GATE_CONSUME = "/locations/internal/action-gate/consume"

AUTO_PROGRESS_BODY = {
    "character_id": 31, "event_type": "collect", "increment": 2, "target_id": 77,
}
GATHERING_BODY = {"character_ids": [31, 32]}
CONSUME_BODY = {
    "character_id": 31, "location_id": 5, "action_type": "combat", "target_ref": 9,
}
GATE_PARAMS = {"character_id": 31, "location_id": 5, "action_type": "combat"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _Result:
    """Minimal stand-in for a SQLAlchemy `Result` — the two read routes use
    raw `text()` SQL, so only `fetchone`/`scalar` are needed."""

    def __init__(self, row=None, scalar=0):
        self._row = row
        self._scalar = scalar

    def fetchone(self):
        return self._row

    def scalar(self):
        return self._scalar


class _FakeSession:
    """Async session whose `execute` is awaitable and records every statement,
    so a rejected request that still touched the DB is visible."""

    def __init__(self, row=None, scalar=0):
        self.statements = []
        self._result = _Result(row=row, scalar=scalar)

    async def execute(self, statement, params=None):
        self.statements.append(str(statement))
        return self._result


@pytest.fixture()
def session():
    return _FakeSession(row=(1,), scalar=4)


@pytest.fixture()
def internal_client(session, monkeypatch):
    """TestClient with the internal token configured and a fake async DB."""
    monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", TOKEN)

    async def _get_db():
        yield session

    main.app.dependency_overrides[get_db] = _get_db
    with TestClient(main.app) as client:
        yield client
    main.app.dependency_overrides.clear()


@pytest.fixture()
def crud_calls(monkeypatch):
    """Record every CRUD entry point the six routes can reach.

    The two mutators are the point: `auto_progress_quests` pays quest rewards
    and `consume_action_gate` burns a limited attempt. If either name shows up
    after a 401/503, the guard ran too late.
    """
    calls = {
        "auto_progress_quests": [],
        "consume_action_gate": [],
        "check_action_gate": [],
        "active_gatherers_among": [],
    }

    async def fake_auto_progress(session, **kwargs):
        calls["auto_progress_quests"].append(kwargs)
        return 2

    async def fake_consume(session, character_id, location_id, action_type,
                           target_ref=None):
        calls["consume_action_gate"].append(
            (character_id, location_id, action_type, target_ref))
        return True

    async def fake_check(session, character_id, location_id, action_type,
                         target_ref=None):
        calls["check_action_gate"].append(
            (character_id, location_id, action_type, target_ref))
        return True

    async def fake_gatherers(session, character_ids):
        calls["active_gatherers_among"].append(list(character_ids))
        return [32]

    monkeypatch.setattr(main.crud, "auto_progress_quests", fake_auto_progress)
    monkeypatch.setattr(main.crud, "consume_action_gate", fake_consume)
    monkeypatch.setattr(main.crud, "check_action_gate", fake_check)
    monkeypatch.setattr(main.crud, "active_gatherers_among", fake_gatherers)
    return calls


def _call(client, route, headers):
    """Issue the route's real request with `headers` (may be empty)."""
    if route == CHECK_COMPLETED:
        return client.get(route, params={"character_id": 31, "quest_id": 3},
                          headers=headers)
    if route == COMPLETED_COUNT:
        return client.get(route, params={"character_id": 31}, headers=headers)
    if route == ACTION_GATE:
        return client.get(route, params=GATE_PARAMS, headers=headers)
    if route == AUTO_PROGRESS:
        return client.post(route, json=AUTO_PROGRESS_BODY, headers=headers)
    if route == GATHERING_STATUS:
        return client.post(route, json=GATHERING_BODY, headers=headers)
    if route == ACTION_GATE_CONSUME:
        return client.post(route, json=CONSUME_BODY, headers=headers)
    raise AssertionError(f"unknown route {route}")


ALL_ROUTES = (
    CHECK_COMPLETED, COMPLETED_COUNT, AUTO_PROGRESS,
    GATHERING_STATUS, ACTION_GATE, ACTION_GATE_CONSUME,
)
MUTATORS = (AUTO_PROGRESS, ACTION_GATE_CONSUME)
MUTATING_CRUD = {
    AUTO_PROGRESS: "auto_progress_quests",
    ACTION_GATE_CONSUME: "consume_action_gate",
}


# ══════════════════════════════════════════════════════════════════════════════
# 1. Rejection — no header, wrong header, unconfigured token
# ══════════════════════════════════════════════════════════════════════════════


class TestInternalRoutesRejectOutsiders:

    @pytest.mark.parametrize("route", ALL_ROUTES)
    def test_no_header_returns_401(self, internal_client, crud_calls, route):
        response = _call(internal_client, route, NO_HEADERS)
        assert response.status_code == 401, f"{route}: {response.text}"
        assert response.json()["detail"] == "Недействительный internal token"

    @pytest.mark.parametrize("route", ALL_ROUTES)
    def test_wrong_header_returns_401(self, internal_client, crud_calls, route):
        response = _call(internal_client, route, WRONG_HEADERS)
        assert response.status_code == 401, f"{route}: {response.text}"
        assert response.json()["detail"] == "Недействительный internal token"

    @pytest.mark.parametrize("route", ALL_ROUTES)
    def test_empty_header_value_returns_401(self, internal_client, crud_calls, route):
        response = _call(internal_client, route, {"X-Internal-Token": ""})
        assert response.status_code == 401, f"{route}: {response.text}"

    @pytest.mark.parametrize("route", ALL_ROUTES)
    def test_a_player_jwt_does_not_open_an_internal_route(
            self, internal_client, crud_calls, route):
        """No browser calls any of these (FEAT-170 §2.0), so a bearer token
        must not be mistaken for a service credential."""
        response = _call(internal_client, route,
                         {"Authorization": "Bearer player-jwt"})
        assert response.status_code == 401, f"{route}: {response.text}"

    @pytest.mark.parametrize("route", ALL_ROUTES)
    def test_the_token_is_compared_case_sensitively(
            self, internal_client, crud_calls, route):
        response = _call(internal_client, route,
                         {"X-Internal-Token": TOKEN.upper()})
        assert response.status_code == 401, f"{route}: {response.text}"

    @pytest.mark.parametrize("route", ALL_ROUTES)
    def test_the_header_name_is_case_insensitive(
            self, internal_client, crud_calls, route):
        """HTTP header names are case-insensitive — a real caller sending
        `x-internal-token` must still get through, or the gate would be a
        transport-level accident rather than a check."""
        response = _call(internal_client, route, {"x-internal-token": TOKEN})
        assert response.status_code not in (401, 403, 503), \
            f"{route}: {response.status_code} {response.text}"

    @pytest.mark.parametrize("route", ALL_ROUTES)
    def test_auth_runs_before_the_request_body_is_validated(
            self, internal_client, crud_calls, route):
        """Garbage from an anonymous caller must be a 401, not a 422 — the
        request must not reach the handler at all."""
        if route in (CHECK_COMPLETED, COMPLETED_COUNT, ACTION_GATE):
            response = internal_client.get(route)  # required params missing
        else:
            response = internal_client.post(route, json={"nonsense": True})
        assert response.status_code == 401, f"{route}: {response.text}"


class TestInternalRoutesFailClosed:
    """An unconfigured `INTERNAL_SERVICE_TOKEN` must never mean "no check"."""

    @pytest.mark.parametrize("route", ALL_ROUTES)
    def test_empty_token_returns_503_for_every_header(
            self, internal_client, crud_calls, monkeypatch, route):
        monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", "")
        for headers in (NO_HEADERS, GOOD_HEADERS, WRONG_HEADERS,
                        {"X-Internal-Token": ""}):
            response = _call(internal_client, route, headers)
            assert response.status_code == 503, f"{route}: {response.text}"
            assert response.json()["detail"] == \
                "Internal service token не настроен"


# ══════════════════════════════════════════════════════════════════════════════
# 2. The mutators must not write anything on the way to a rejection
# ══════════════════════════════════════════════════════════════════════════════


class TestRejectedMutatorsChangeNothing:
    """`auto-progress` completes objectives and pays their reward;
    `action-gate/consume` burns one of a player's limited attempts. Both are
    irreversible, so a guard that rejects *after* the write is a real hole that
    a status-code assertion cannot see. Every rejected call is therefore also
    asserted against the CRUD layer and against the DB session."""

    REJECTIONS = (
        ("no header", NO_HEADERS),
        ("wrong header", WRONG_HEADERS),
        ("empty header", {"X-Internal-Token": ""}),
        ("player jwt", {"Authorization": "Bearer player-jwt"}),
    )

    @pytest.mark.parametrize("route", MUTATORS)
    def test_a_401_never_reaches_the_mutating_crud_call(
            self, internal_client, crud_calls, session, route):
        name = MUTATING_CRUD[route]
        for label, headers in self.REJECTIONS:
            response = _call(internal_client, route, headers)
            assert response.status_code == 401, f"{route} / {label}"
            assert crud_calls[name] == [], (
                f"{route} rejected the {label} request with 401 but still ran "
                f"crud.{name} — quest rewards / action gates were mutated for "
                "an unauthenticated caller"
            )
        assert session.statements == [], (
            f"{route} touched the database for rejected callers: "
            f"{session.statements}"
        )

    @pytest.mark.parametrize("route", MUTATORS)
    def test_a_503_never_reaches_the_mutating_crud_call(
            self, internal_client, crud_calls, session, monkeypatch, route):
        monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", "")
        name = MUTATING_CRUD[route]
        for headers in (NO_HEADERS, GOOD_HEADERS, WRONG_HEADERS):
            response = _call(internal_client, route, headers)
            assert response.status_code == 503
            assert crud_calls[name] == [], (
                f"{route} answered 503 (token not configured) but still ran "
                f"crud.{name} — fail-closed must mean nothing is written"
            )
        assert session.statements == []

    def test_the_rejection_assertions_actually_bite(self, internal_client,
                                                    crud_calls):
        """Negative control for the two tests above: with a valid token the
        very same call DOES reach the mutating CRUD function, so an empty
        `crud_calls` list is evidence and not an artefact of the fixture."""
        assert _call(internal_client, AUTO_PROGRESS,
                     GOOD_HEADERS).status_code == 200
        assert _call(internal_client, ACTION_GATE_CONSUME,
                     GOOD_HEADERS).status_code == 200
        assert crud_calls["auto_progress_quests"], \
            "the fixture never records anything — the guard tests prove nothing"
        assert crud_calls["consume_action_gate"]


# ══════════════════════════════════════════════════════════════════════════════
# 3. With the token the routes behave exactly as before
# ══════════════════════════════════════════════════════════════════════════════


class TestInternalRoutesAcceptTheToken:

    def test_check_completed_returns_the_flag(self, internal_client):
        response = internal_client.get(
            CHECK_COMPLETED, params={"character_id": 31, "quest_id": 3},
            headers=GOOD_HEADERS)
        assert response.status_code == 200, response.text
        assert response.json() == {"completed": True}

    def test_check_completed_reports_a_missing_row_as_false(self, monkeypatch):
        empty = _FakeSession(row=None)

        async def _get_db():
            yield empty

        monkeypatch.setattr(main, "INTERNAL_SERVICE_TOKEN", TOKEN)
        main.app.dependency_overrides[get_db] = _get_db
        try:
            with TestClient(main.app) as client:
                response = client.get(
                    CHECK_COMPLETED,
                    params={"character_id": 31, "quest_id": 3},
                    headers=GOOD_HEADERS)
        finally:
            main.app.dependency_overrides.clear()
        assert response.status_code == 200, response.text
        assert response.json() == {"completed": False}

    def test_completed_count_returns_the_count(self, internal_client):
        response = internal_client.get(
            COMPLETED_COUNT, params={"character_id": 31}, headers=GOOD_HEADERS)
        assert response.status_code == 200, response.text
        assert response.json() == {"count": 4}

    def test_auto_progress_returns_the_updated_objectives(
            self, internal_client, crud_calls):
        response = internal_client.post(
            AUTO_PROGRESS, json=AUTO_PROGRESS_BODY, headers=GOOD_HEADERS)
        assert response.status_code == 200, response.text
        assert response.json() == {"updated_objectives": 2}
        assert crud_calls["auto_progress_quests"] == [{
            "character_id": 31, "event_type": "collect",
            "increment": 2, "target_id": 77, "meta": None,
        }]

    def test_gathering_status_returns_the_busy_characters(
            self, internal_client, crud_calls):
        response = internal_client.post(
            GATHERING_STATUS, json=GATHERING_BODY, headers=GOOD_HEADERS)
        assert response.status_code == 200, response.text
        assert response.json() == {"gathering_character_ids": [32]}
        assert crud_calls["active_gatherers_among"] == [[31, 32]]

    def test_action_gate_read_returns_the_gate_state(
            self, internal_client, crud_calls):
        response = internal_client.get(
            ACTION_GATE, params=GATE_PARAMS, headers=GOOD_HEADERS)
        assert response.status_code == 200, response.text
        assert response.json() == {"open": True}
        assert crud_calls["check_action_gate"] == [(31, 5, "combat", None)]

    def test_action_gate_consume_burns_exactly_one_gate(
            self, internal_client, crud_calls):
        response = internal_client.post(
            ACTION_GATE_CONSUME, json=CONSUME_BODY, headers=GOOD_HEADERS)
        assert response.status_code == 200, response.text
        assert response.json() == {"consumed": True}
        assert crud_calls["consume_action_gate"] == [(31, 5, "combat", 9)]

    def test_a_malformed_body_with_a_valid_token_is_a_422_not_a_401(
            self, internal_client, crud_calls):
        """Past the guard the routes keep their own contract — the guard did
        not swallow validation."""
        response = internal_client.post(
            AUTO_PROGRESS, json={"character_id": 31}, headers=GOOD_HEADERS)
        assert response.status_code == 422, response.text
        assert crud_calls["auto_progress_quests"] == []


# ══════════════════════════════════════════════════════════════════════════════
# 4. Route sweep — the check that stays true for routes nobody has written yet
# ══════════════════════════════════════════════════════════════════════════════


class TestEveryInternalRouteIsGated:
    """FEAT-170 §3.12 e. Dependencies are **flattened**: a guard reached
    through a wrapper dependency still counts, and a route that swapped the
    guard for an unrelated wrapper does not. Both an unguarded new route and a
    refactor that empties the route table fail here."""

    #: `/internal/` routes present in this service when FEAT-170 shipped
    #: (6 gated by this feature + `progress/update`, `cancel-gathering` and
    #: `character-left-location` gated by FEAT-169).
    MIN_INTERNAL_ROUTES = 9

    @staticmethod
    def _flat_deps(dependant):
        names = set()
        stack = list(dependant.dependencies)
        while stack:
            dep = stack.pop()
            call = getattr(dep, "call", None)
            if call is not None:
                names.add(getattr(call, "__name__", type(call).__name__))
            stack.extend(getattr(dep, "dependencies", []))
        return names

    def _internal_routes(self):
        from fastapi.routing import APIRoute

        return [r for r in main.app.routes
                if isinstance(r, APIRoute) and "/internal/" in r.path]

    def test_every_internal_route_carries_verify_internal_token(self):
        offenders = []
        for route in self._internal_routes():
            if "verify_internal_token" not in self._flat_deps(route.dependant):
                offenders.append(
                    f"{'/'.join(sorted(route.methods))} {route.path}")
        assert not offenders, (
            "маршрут под /internal/ без verify_internal_token — его можно "
            "вызвать без токена изнутри сети контейнеров: "
            + "; ".join(offenders)
        )

    def test_the_sweep_actually_found_the_internal_routes(self):
        found = self._internal_routes()
        assert len(found) >= self.MIN_INTERNAL_ROUTES, (
            f"свип нашёл только {len(found)} внутренних маршрутов "
            f"(ожидалось >= {self.MIN_INTERNAL_ROUTES}): "
            + "; ".join(sorted(r.path for r in found))
        )

    def test_all_six_feat170_routes_are_on_the_route_table(self):
        paths = {r.path for r in self._internal_routes()}
        for route in ALL_ROUTES:
            assert route in paths, f"{route} disappeared from the route table"

    def test_the_flattening_would_notice_a_lost_guard(self):
        """Negative control for the sweep: a route with no `verify_internal_token`
        anywhere in its dependency tree must be reported."""
        from fastapi.routing import APIRoute

        public = [r for r in main.app.routes
                  if isinstance(r, APIRoute)
                  and r.path == "/locations/action-gate/status"]
        assert public, "the public action-gate twin vanished"
        assert "verify_internal_token" not in self._flat_deps(public[0].dependant), (
            "the sweep reports verify_internal_token on a route that does not "
            "have it — it would pass for every route and prove nothing"
        )
