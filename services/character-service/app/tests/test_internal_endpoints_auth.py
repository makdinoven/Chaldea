"""FEAT-162 tasks #2 / #14 — the four character-service write endpoints that
used to be reachable from the public internet with no credentials at all.

Before this feature:

  * `PUT  /characters/{id}/update_location`      — move any character anywhere
  * `POST /characters/{id}/set_travel_cooldown`  — `{"minutes": 0}` = free travel
  * `PUT  /characters/{id}/deduct_points`        — burn anyone's stat points
  * `POST /characters/{id}/logs`                 — forge journal entries

All four now live under `/characters/internal/…` (nginx answers 403 on that
prefix) behind `verify_internal_token`. Two layers, and this file tests the
one that survives a gateway mistake: the token.

Three things are asserted for every route, because each is a different way to
be wrong:

  * **no header → 401** and **wrong header → 401** — the obvious one;
  * **token env unset → 503** — fail-closed. A deployment that forgets the env
    var must break loudly, never silently serve an unauthenticated endpoint;
  * **the old public path is gone** — a fix that leaves the old route mounted
    fixes nothing. `POST /characters/{id}/logs` is the one deliberate
    exception: it answers **405**, not 404, because `GET` on that same path is
    still public (the frontend reads the journal through it).

`deduct_points` additionally gets the functional coverage it never had — the
absence of which is a large part of why it stayed unauthenticated through
three audits.
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

import auth_http
import database
import models
from database import Base
from main import app, get_db


TOKEN = "test-internal-token-162"
GOOD = {"X-Internal-Token": TOKEN}
WRONG = {"X-Internal-Token": "definitely-not-the-token"}

LOC_A = 601
LOC_B = 602


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def internal_token():
    """Pin the module constant for the duration of a test and restore it.

    Other suites mutate the same global, so it is always saved and put back.
    """
    original = auth_http.INTERNAL_SERVICE_TOKEN
    auth_http.INTERNAL_SERVICE_TOKEN = TOKEN
    try:
        yield TOKEN
    finally:
        auth_http.INTERNAL_SERVICE_TOKEN = original


@pytest.fixture
def token_unset():
    """Simulate a deployment where INTERNAL_SERVICE_TOKEN was never set."""
    original = auth_http.INTERNAL_SERVICE_TOKEN
    auth_http.INTERNAL_SERVICE_TOKEN = ""
    try:
        yield
    finally:
        auth_http.INTERNAL_SERVICE_TOKEN = original


@pytest.fixture
def db_session(seed_fk_data):
    Base.metadata.create_all(bind=database.engine)
    session = database.SessionLocal()
    seed_fk_data(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=database.engine)


@pytest.fixture
def character(db_session):
    char = models.Character(
        name="Служебный",
        id_race=1, id_subrace=1, id_class=1,
        appearance="test", avatar="t.jpg",
        is_npc=False, npc_role=None,
        current_location_id=LOC_A,
        level=1, stat_points=10, currency_balance=0,
        travel_cooldown_until=datetime.utcnow() + timedelta(minutes=30),
    )
    db_session.add(char)
    db_session.commit()
    db_session.refresh(char)
    return char


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Route table: (method, new path template, old path template, body)
# ---------------------------------------------------------------------------

def _routes(character_id):
    return [
        (
            "update_location",
            "put",
            f"/characters/internal/{character_id}/update_location",
            f"/characters/{character_id}/update_location",
            404,
            {"new_location_id": LOC_B},
        ),
        (
            "set_travel_cooldown",
            "post",
            f"/characters/internal/{character_id}/set_travel_cooldown",
            f"/characters/{character_id}/set_travel_cooldown",
            404,
            {"minutes": 0},
        ),
        (
            "deduct_points",
            "put",
            f"/characters/internal/{character_id}/deduct_points",
            f"/characters/{character_id}/deduct_points",
            404,
            {"points_to_deduct": 1},
        ),
        (
            # GET on this path is still public (the frontend reads the journal),
            # so the vanished POST surfaces as 405 rather than 404.
            "logs",
            "post",
            f"/characters/internal/{character_id}/logs",
            f"/characters/{character_id}/logs",
            405,
            {"event_type": "test", "description": "d", "metadata": None},
        ),
    ]


def _ids():
    return [r[0] for r in _routes(1)]


@pytest.fixture(params=range(4), ids=_ids())
def route(request, character):
    return _routes(character.id)[request.param]


# ===========================================================================
# 1. The token guard — every moved route, every way to be wrong
# ===========================================================================

class TestInternalTokenGuard:
    def test_missing_header_is_rejected(self, client, route, internal_token):
        _, method, new_path, _old, _code, body = route
        resp = getattr(client, method)(new_path, json=body)
        assert resp.status_code == 401, f"{new_path} accepted a request with no token"
        assert resp.json()["detail"] == "Недействительный internal token"

    def test_wrong_token_is_rejected(self, client, route, internal_token):
        _, method, new_path, _old, _code, body = route
        resp = getattr(client, method)(new_path, json=body, headers=WRONG)
        assert resp.status_code == 401, f"{new_path} accepted a wrong token"

    def test_empty_token_header_is_rejected(self, client, route, internal_token):
        _, method, new_path, _old, _code, body = route
        resp = getattr(client, method)(
            new_path, json=body, headers={"X-Internal-Token": ""},
        )
        assert resp.status_code == 401

    def test_unset_env_fails_closed_with_503(self, client, route, token_unset):
        """Fail-closed: an unconfigured token rejects EVERY caller, including
        one presenting the value the service would otherwise have expected."""
        _, method, new_path, _old, _code, body = route
        for headers in (None, GOOD, {"X-Internal-Token": ""}):
            resp = getattr(client, method)(new_path, json=body, headers=headers)
            assert resp.status_code == 503, (
                f"{new_path} did not fail closed with headers={headers}"
            )
            assert resp.json()["detail"] == "Internal service token не настроен"

    def test_valid_token_is_accepted(self, client, route, internal_token):
        _, method, new_path, _old, _code, body = route
        resp = getattr(client, method)(new_path, json=body, headers=GOOD)
        assert resp.status_code in (200, 201), resp.text


# ===========================================================================
# 2. The old public paths are gone
# ===========================================================================

class TestOldPublicPathsAreGone:
    def test_old_path_no_longer_serves_the_write(
        self, client, route, internal_token,
    ):
        """The pre-fix behaviour — an unauthenticated 200 — must be gone.

        Asserted as "not a success", not merely "not 200": a 201/204 would be
        the same hole wearing a different number.
        """
        _, method, _new, old_path, expected, body = route
        resp = getattr(client, method)(old_path, json=body)
        assert resp.status_code == expected, (
            f"{method.upper()} {old_path} answered {resp.status_code}, "
            f"expected {expected}"
        )
        assert not (200 <= resp.status_code < 300), (
            f"{method.upper()} {old_path} still performs the write unauthenticated"
        )

    def test_old_path_is_gone_even_with_a_valid_token(
        self, client, route, internal_token,
    ):
        """Not a 'wrong credentials' answer — the route simply is not there."""
        _, method, _new, old_path, expected, body = route
        resp = getattr(client, method)(old_path, json=body, headers=GOOD)
        assert resp.status_code == expected

    def test_get_logs_stays_public(self, client, character, internal_token):
        """The one route deliberately NOT closed: the frontend reads the
        journal through it (`api/characterLogs.ts`)."""
        resp = client.get(f"/characters/{character.id}/logs")
        assert resp.status_code == 200


# ===========================================================================
# 3. The moved routes still do their job
# ===========================================================================

class TestMovedRoutesStillWork:
    def test_update_location_writes_the_column(
        self, client, db_session, character, internal_token,
    ):
        resp = client.put(
            f"/characters/internal/{character.id}/update_location",
            json={"new_location_id": LOC_B}, headers=GOOD,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["current_location_id"] == LOC_B
        db_session.expire_all()
        fresh = db_session.query(models.Character).filter_by(id=character.id).first()
        assert fresh.current_location_id == LOC_B

    def test_update_location_missing_field_returns_400(
        self, client, character, internal_token,
    ):
        resp = client.put(
            f"/characters/internal/{character.id}/update_location",
            json={}, headers=GOOD,
        )
        assert resp.status_code == 400

    def test_update_location_unknown_character_returns_404(
        self, client, internal_token,
    ):
        resp = client.put(
            "/characters/internal/987654/update_location",
            json={"new_location_id": LOC_B}, headers=GOOD,
        )
        assert resp.status_code == 404

    def test_set_cooldown_zero_clears_it(
        self, client, db_session, character, internal_token,
    ):
        resp = client.post(
            f"/characters/internal/{character.id}/set_travel_cooldown",
            json={"minutes": 0}, headers=GOOD,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["travel_cooldown_until"] is None
        db_session.expire_all()
        fresh = db_session.query(models.Character).filter_by(id=character.id).first()
        assert fresh.travel_cooldown_until is None

    def test_set_cooldown_positive_sets_a_future_timestamp(
        self, client, db_session, character, internal_token,
    ):
        resp = client.post(
            f"/characters/internal/{character.id}/set_travel_cooldown",
            json={"minutes": 15}, headers=GOOD,
        )
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        fresh = db_session.query(models.Character).filter_by(id=character.id).first()
        until = fresh.travel_cooldown_until
        assert until is not None and until > datetime.utcnow()

    def test_logs_route_creates_a_journal_row(
        self, client, db_session, character, internal_token,
    ):
        resp = client.post(
            f"/characters/internal/{character.id}/logs",
            json={"event_type": "rp_post", "description": "Написал пост",
                  "metadata": {"char_count": 500}},
            headers=GOOD,
        )
        assert resp.status_code == 201, resp.text
        rows = db_session.query(models.CharacterLog).filter_by(
            character_id=character.id, event_type="rp_post",
        ).all()
        assert len(rows) == 1
        assert rows[0].metadata_ == {"char_count": 500}


# ===========================================================================
# 4. deduct_points — the endpoint that had zero tests
# ===========================================================================

class TestDeductPoints:
    """It shipped unauthenticated through three audits partly because nothing
    exercised it. Behaviour is pinned here so the next change to it is visible."""

    def _call(self, client, character_id, points, headers=GOOD):
        return client.put(
            f"/characters/internal/{character_id}/deduct_points",
            json={"points_to_deduct": points}, headers=headers,
        )

    def test_deducts_and_returns_the_remainder(
        self, client, db_session, character, internal_token,
    ):
        resp = self._call(client, character.id, 4)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "message": "Stat points deducted", "remaining_points": 6,
        }
        db_session.expire_all()
        assert db_session.query(models.Character).filter_by(id=character.id).first().stat_points == 6

    def test_deducting_the_whole_balance_is_allowed(
        self, client, db_session, character, internal_token,
    ):
        resp = self._call(client, character.id, 10)
        assert resp.status_code == 200
        assert resp.json()["remaining_points"] == 0

    def test_more_than_available_returns_400_and_deducts_nothing(
        self, client, db_session, character, internal_token,
    ):
        resp = self._call(client, character.id, 11)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Not enough stat points"
        db_session.expire_all()
        assert db_session.query(models.Character).filter_by(id=character.id).first().stat_points == 10

    @pytest.mark.parametrize("bad", [0, -1, -100, "3", 1.5, None, [1], {"a": 1}])
    def test_non_positive_or_non_int_returns_400(
        self, client, db_session, character, internal_token, bad,
    ):
        resp = self._call(client, character.id, bad)
        assert resp.status_code == 400
        db_session.expire_all()
        fresh = db_session.query(models.Character).filter_by(id=character.id).first()
        assert fresh.stat_points == 10

    def test_json_true_is_treated_as_one_point(
        self, client, db_session, character, internal_token,
    ):
        """Quirk, pinned rather than silently tolerated: `isinstance(True, int)`
        is True in Python, so `{"points_to_deduct": true}` passes the type check
        and deducts exactly one point. Harmless today (the route is
        token-guarded and its only caller sends an int), but if it ever changes
        this test says so out loud."""
        resp = self._call(client, character.id, True)
        assert resp.status_code == 200
        assert resp.json()["remaining_points"] == 9

    def test_missing_field_returns_400(self, client, character, internal_token):
        resp = client.put(
            f"/characters/internal/{character.id}/deduct_points",
            json={}, headers=GOOD,
        )
        assert resp.status_code == 400

    def test_unknown_character_returns_404(self, client, internal_token):
        resp = self._call(client, 987654, 1)
        assert resp.status_code == 404

    def test_cannot_be_called_without_the_token(
        self, client, db_session, character, internal_token,
    ):
        """The actual exploit, replayed: the old path drained anyone's points."""
        resp = client.put(
            f"/characters/{character.id}/deduct_points",
            json={"points_to_deduct": 10},
        )
        assert resp.status_code == 404
        db_session.expire_all()
        assert db_session.query(models.Character).filter_by(id=character.id).first().stat_points == 10
