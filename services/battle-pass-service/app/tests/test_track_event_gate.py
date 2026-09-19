"""
FEAT-170 T14 — battle-pass-service: `POST /battle-pass/internal/track-event`
is behind `verify_internal_token`.

The route credits battle-pass progression (location visits ⇒ missions ⇒ season
rewards) for **any** `user_id`/`character_id` in the body, and it had no HTTP
test of any kind before this feature. Its handler also swallows every exception
from `crud.track_location_visit` and still answers `{"ok": True}`, so a guard
that ran *after* the write would look identical from the outside — hence every
rejection below re-reads `bp_location_visits` and asserts the row count did not
move.

`auth_http` captures `INTERNAL_SERVICE_TOKEN` in a module-level constant at
import, so `monkeypatch.setattr(auth_http, ...)` is required; `setenv` alone
would change nothing.
"""

import pytest
from sqlalchemy import select

import auth_http
from models import BpLocationVisit


TOKEN = "test-internal-token"
GOOD_HEADERS = {"X-Internal-Token": TOKEN}
WRONG_HEADERS = {"X-Internal-Token": "not-the-token"}
EMPTY_HEADERS = {"X-Internal-Token": ""}

PATH = "/battle-pass/internal/track-event"
BODY = {
    "user_id": 1,
    "event_type": "location_visit",
    "character_id": 100,
    "metadata": {"location_id": 42},
}


@pytest.fixture(autouse=True)
def _token_is_configured(monkeypatch):
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)


async def _visits(db_session):
    result = await db_session.execute(select(BpLocationVisit))
    return result.scalars().all()


# ══════════════════════════════════════════════════════════════════════════════
# 1. The auth matrix — and no progression is credited on a rejection
# ══════════════════════════════════════════════════════════════════════════════


class TestTrackEventRejectsOutsiders:

    async def test_no_header_is_401_and_credits_nothing(
        self, client, db_session, active_season
    ):
        resp = await client.post(PATH, json=BODY)
        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"] == "Недействительный internal token"
        assert await _visits(db_session) == [], \
            "the rejected call still credited a location visit"

    async def test_wrong_header_is_401_and_credits_nothing(
        self, client, db_session, active_season
    ):
        resp = await client.post(PATH, json=BODY, headers=WRONG_HEADERS)
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Недействительный internal token"
        assert await _visits(db_session) == []

    async def test_empty_header_value_is_401(self, client, db_session,
                                             active_season):
        resp = await client.post(PATH, json=BODY, headers=EMPTY_HEADERS)
        assert resp.status_code == 401
        assert await _visits(db_session) == []

    async def test_a_player_jwt_does_not_open_it(self, client, db_session,
                                                 active_season):
        """locations-service is the only caller; the browser never touches it."""
        resp = await client.post(PATH, json=BODY,
                                 headers={"Authorization": "Bearer player-jwt"})
        assert resp.status_code == 401
        assert await _visits(db_session) == []

    async def test_auth_runs_before_body_validation(self, client, active_season):
        """A malformed body without the header must answer 401, not 422."""
        resp = await client.post(PATH, json={"event_type": "location_visit"})
        assert resp.status_code == 401, resp.text

    async def test_the_token_value_is_case_sensitive(self, client, active_season):
        resp = await client.post(PATH, json=BODY,
                                 headers={"X-Internal-Token": TOKEN.upper()})
        assert resp.status_code == 401

    async def test_the_header_name_is_case_insensitive(self, client,
                                                       active_season):
        resp = await client.post(PATH, json=BODY,
                                 headers={"x-internal-token": TOKEN})
        assert resp.status_code == 200, resp.text


class TestTrackEventFailsClosed:

    async def test_empty_env_token_is_503_for_every_header(
        self, client, db_session, active_season, monkeypatch
    ):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        for headers in (None, GOOD_HEADERS, WRONG_HEADERS, EMPTY_HEADERS):
            kwargs = {"json": BODY}
            if headers is not None:
                kwargs["headers"] = headers
            resp = await client.post(PATH, **kwargs)
            assert resp.status_code == 503, resp.text
            assert resp.json()["detail"] == "Internal service token не настроен"
        assert await _visits(db_session) == [], \
            "the 503'd calls still credited a location visit"


# ══════════════════════════════════════════════════════════════════════════════
# 2. With the right header the route behaves exactly as before
# ══════════════════════════════════════════════════════════════════════════════


class TestTheTokenLetsTrackEventWork:

    async def test_a_location_visit_is_recorded(self, client, db_session,
                                                active_season):
        resp = await client.post(PATH, json=BODY, headers=GOOD_HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"ok": True}

        visits = await _visits(db_session)
        assert len(visits) == 1
        assert visits[0].user_id == 1
        assert visits[0].character_id == 100
        assert visits[0].location_id == 42
        assert visits[0].season_id == active_season.id

    async def test_a_repeated_visit_is_idempotent(self, client, db_session,
                                                  active_season):
        for _ in range(3):
            resp = await client.post(PATH, json=BODY, headers=GOOD_HEADERS)
            assert resp.status_code == 200
        assert len(await _visits(db_session)) == 1

    async def test_an_unknown_event_type_is_ignored_not_rejected(
        self, client, db_session, active_season
    ):
        resp = await client.post(
            PATH,
            json={**BODY, "event_type": "something_else"},
            headers=GOOD_HEADERS,
        )
        assert resp.status_code == 200, resp.text
        assert await _visits(db_session) == []

    async def test_a_malformed_body_with_the_header_is_422_not_401(
        self, client, active_season
    ):
        """With the header the request reaches validation — the guard must not
        mask the handler's own 422."""
        resp = await client.post(PATH, json={"event_type": "location_visit"},
                                 headers=GOOD_HEADERS)
        assert resp.status_code == 422, resp.text

    async def test_no_active_season_still_answers_ok(self, client, db_session):
        """`track_location_visit` returns early with no season — a 200 with no
        row written, not a 401/500."""
        resp = await client.post(PATH, json=BODY, headers=GOOD_HEADERS)
        assert resp.status_code == 200, resp.text
        assert await _visits(db_session) == []


# ══════════════════════════════════════════════════════════════════════════════
# 3. The sweep that survives us — every `/internal/` route carries the guard
# ══════════════════════════════════════════════════════════════════════════════
# The committed version of the ad-hoc `app.routes` walk run by hand in T9.
# Dependencies are flattened recursively, so a guard reached through a
# sub-dependency counts — a route that simply forgot it does not.


def _flat_dependency_names(dependant):
    names = set()
    stack = list(dependant.dependencies)
    while stack:
        dep = stack.pop()
        call = getattr(dep, "call", None)
        if call is not None:
            names.add(getattr(call, "__name__", type(call).__name__))
        stack.extend(getattr(dep, "dependencies", []))
    return names


def _internal_routes():
    from fastapi.routing import APIRoute
    from main import app

    return [r for r in app.routes
            if isinstance(r, APIRoute) and "/internal/" in r.path]


class TestEveryInternalRouteIsGated:

    def test_no_internal_route_is_open(self):
        offenders = [
            f"{sorted(r.methods)} {r.path}"
            for r in _internal_routes()
            if "verify_internal_token" not in _flat_dependency_names(r.dependant)
        ]
        assert not offenders, (
            "маршрут с сегментом /internal/ без verify_internal_token — "
            "он отвечает любому, кто достал до порта контейнера: "
            + "; ".join(offenders)
        )

    def test_the_sweep_actually_found_the_route(self):
        """A path refactor must not silently empty the sweep."""
        found = {f"{sorted(r.methods)[0]} {r.path}" for r in _internal_routes()}
        assert len(found) >= 1, found
        assert "POST /battle-pass/internal/track-event" in found, sorted(found)
