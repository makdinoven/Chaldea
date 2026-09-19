"""
FEAT-169 #17 (QA) — user-service: `activity/increment` is internal-only now.

`POST /users/{user_id}/activity/increment` used to sit on a **public** prefix
with a docstring that merely claimed to be internal: nginx proxies `/users/`
wholesale, so anyone could inflate (or, with a negative `points`, deflate) any
user's activity points from the outside. Exactly the shape of the FEAT-167
`cumulative_stats/increment` hole.

Two things changed, and both are pinned here:

1. The route **moved** to `POST /users/internal/{user_id}/activity/increment`
   behind `verify_internal_token` (gate I). The old path is gone — 404, not a
   silent alias, so a caller that was never updated fails loudly instead of
   quietly skipping the increment.
2. `points` is validated: `Field(1, ge=1, le=100)`. It used to accept anything,
   including negatives.

user-service had no internal-token machinery at all before this feature, so the
fail-closed semantics (empty token → 503) are asserted here for the first time.
"""

import pytest

import auth
import models


TOKEN = "test-internal-token"
GOOD_HEADERS = {"X-Internal-Token": TOKEN}
WRONG_HEADERS = {"X-Internal-Token": "not-the-token"}

USER_ID = 501
NEW_PATH = f"/users/internal/{USER_ID}/activity/increment"
OLD_PATH = f"/users/{USER_ID}/activity/increment"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _token_is_configured(monkeypatch):
    """`auth` resolves INTERNAL_SERVICE_TOKEN into a module-level constant at
    import time, so pinning the env var alone would do nothing — the constant
    is what `verify_internal_token` reads."""
    monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", TOKEN)


@pytest.fixture()
def active_user(db_session):
    user = models.User(
        id=USER_ID,
        email="activity@example.com",
        username="activity_user",
        hashed_password="x",
        activity_points=10,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _points(db_session):
    db_session.expire_all()
    return db_session.query(models.User).filter(
        models.User.id == USER_ID
    ).one().activity_points


# ══════════════════════════════════════════════════════════════════════════════
# 1. Gate I — the auth matrix, with the DB checked after every rejection
# ══════════════════════════════════════════════════════════════════════════════


class TestActivityIncrementRejectsOutsiders:

    def test_no_header_returns_401_and_writes_nothing(self, client, db_session,
                                                      active_user):
        resp = client.post(NEW_PATH, json={"points": 5})
        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"] == "Недействительный internal token"
        assert _points(db_session) == 10, \
            "the rejected call still moved activity_points"

    def test_wrong_header_returns_401_and_writes_nothing(self, client, db_session,
                                                         active_user):
        resp = client.post(NEW_PATH, json={"points": 5}, headers=WRONG_HEADERS)
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Недействительный internal token"
        assert _points(db_session) == 10

    def test_empty_header_value_returns_401_and_writes_nothing(
        self, client, db_session, active_user
    ):
        resp = client.post(NEW_PATH, json={"points": 5},
                           headers={"X-Internal-Token": ""})
        assert resp.status_code == 401
        assert _points(db_session) == 10

    def test_player_bearer_token_is_not_accepted(self, client, db_session,
                                                 active_user):
        """The route has no player-facing caller — a JWT must not open it."""
        resp = client.post(NEW_PATH, json={"points": 5},
                           headers={"Authorization": "Bearer player-jwt"})
        assert resp.status_code == 401
        assert _points(db_session) == 10

    def test_auth_runs_before_schema_validation(self, client, active_user):
        """An anonymous call with a malformed body must answer 401, not 422 —
        a 422 would mean the request reached the handler."""
        resp = client.post(NEW_PATH, json={"points": "nonsense"})
        assert resp.status_code == 401, resp.text

    def test_header_name_is_case_insensitive_but_value_is_not(self, client,
                                                              active_user):
        assert client.post(NEW_PATH, json={"points": 1},
                           headers={"x-internal-token": TOKEN}
                           ).status_code not in (401, 503)
        assert client.post(NEW_PATH, json={"points": 1},
                           headers={"X-Internal-Token": TOKEN.upper()}
                           ).status_code == 401


class TestActivityIncrementFailsClosed:

    def test_empty_token_env_returns_503_and_never_200(self, client, db_session,
                                                       active_user, monkeypatch):
        monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", "")
        for headers in ({}, GOOD_HEADERS, WRONG_HEADERS,
                        {"X-Internal-Token": ""}):
            resp = client.post(NEW_PATH, json={"points": 5}, headers=headers)
            assert resp.status_code == 503, resp.text
            assert resp.json()["detail"] == "Internal service token не настроен"
        assert _points(db_session) == 10


class TestActivityIncrementAcceptsTheToken:

    def test_good_header_increments(self, client, db_session, active_user):
        resp = client.post(NEW_PATH, json={"points": 5}, headers=GOOD_HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"activity_points": 15}
        assert _points(db_session) == 15

    def test_unknown_user_is_404(self, client, active_user):
        resp = client.post("/users/internal/999999/activity/increment",
                           json={"points": 1}, headers=GOOD_HEADERS)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Пользователь не найден"

    def test_a_null_starting_balance_is_treated_as_zero(self, client, db_session):
        """`activity_points` is nullable in older rows."""
        db_session.add(models.User(id=USER_ID, email="n@example.com",
                                   username="null_points", hashed_password="x",
                                   activity_points=None))
        db_session.commit()
        resp = client.post(NEW_PATH, json={"points": 3}, headers=GOOD_HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json()["activity_points"] == 3


# ══════════════════════════════════════════════════════════════════════════════
# 2. The old, publicly routable path is gone
# ══════════════════════════════════════════════════════════════════════════════


class TestTheOldPathIsRemoved:

    def test_old_path_returns_404_anonymously(self, client, db_session,
                                              active_user):
        resp = client.post(OLD_PATH, json={"points": 5})
        assert resp.status_code == 404, resp.text
        assert _points(db_session) == 10

    def test_old_path_returns_404_even_with_the_token(self, client, db_session,
                                                      active_user):
        """No alias was kept: a caller that was never re-pointed must break
        loudly rather than silently stop awarding points."""
        resp = client.post(OLD_PATH, json={"points": 5}, headers=GOOD_HEADERS)
        assert resp.status_code == 404
        assert _points(db_session) == 10

    def test_the_route_table_has_only_the_internal_path(self):
        from fastapi.routing import APIRoute
        from main import app

        paths = {
            route.path
            for route in app.routes
            if isinstance(route, APIRoute) and "POST" in route.methods
            and route.path.endswith("/activity/increment")
        }
        assert paths == {"/users/internal/{user_id}/activity/increment"}, paths

    def test_the_internal_route_is_gated(self):
        from fastapi.routing import APIRoute
        from main import app

        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            if route.path != "/users/internal/{user_id}/activity/increment":
                continue
            names = {
                getattr(dep.call, "__name__", type(dep.call).__name__)
                for dep in route.dependant.dependencies
            }
            assert "verify_internal_token" in names, sorted(names)
            return
        pytest.fail("the internal activity route is no longer registered")


# ══════════════════════════════════════════════════════════════════════════════
# 3. `points` validation — Field(1, ge=1, le=100)
# ══════════════════════════════════════════════════════════════════════════════


class TestPointsValidation:

    @pytest.mark.parametrize("points", [0, -5, -1, 101, 1000])
    def test_out_of_range_points_are_422_and_write_nothing(
        self, client, db_session, active_user, points
    ):
        resp = client.post(NEW_PATH, json={"points": points},
                           headers=GOOD_HEADERS)
        assert resp.status_code == 422, resp.text
        assert _points(db_session) == 10, \
            f"points={points} was rejected but the balance still moved"

    @pytest.mark.parametrize("points", [1, 2, 100])
    def test_in_range_points_are_accepted(self, client, db_session, active_user,
                                          points):
        resp = client.post(NEW_PATH, json={"points": points},
                           headers=GOOD_HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json()["activity_points"] == 10 + points

    def test_points_defaults_to_one_when_omitted(self, client, db_session,
                                                 active_user):
        resp = client.post(NEW_PATH, json={}, headers=GOOD_HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json()["activity_points"] == 11
        assert _points(db_session) == 11

    def test_an_empty_body_also_defaults_to_one(self, client, active_user):
        """notification-service sends `{"points": 1}`, but the default must
        stay usable — and must never be 0 or negative."""
        resp = client.post(NEW_PATH, json=None, headers=GOOD_HEADERS)
        assert resp.status_code in (200, 422), resp.text

    def test_a_negative_value_can_no_longer_drain_the_balance(
        self, client, db_session, active_user
    ):
        """The concrete regression: before FEAT-169 `points: -1000` was a valid
        body and subtracted from somebody else's activity points."""
        resp = client.post(NEW_PATH, json={"points": -1000},
                           headers=GOOD_HEADERS)
        assert resp.status_code == 422
        assert _points(db_session) == 10
