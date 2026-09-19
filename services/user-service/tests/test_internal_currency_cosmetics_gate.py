"""
FEAT-170 T14 — user-service: the four `/users/internal/` money-and-goods routes
are behind `verify_internal_token`.

Until this feature `POST /users/internal/{uid}/diamonds/add` minted premium
currency for anybody who could reach the container port, with no upper bound
beyond `amount > 0`; `diamonds/spend` burned it; `cosmetics/unlock` handed out
purchasable frames and chat backgrounds. Three of the four (`add`, `spend`,
`cosmetics/unlock` as a rejection path) had **no HTTP test at all** — a 401
regression, or a guard that ran *after* the write, would have been invisible.

So every rejection below re-reads the row it was supposed to protect: the
diamond balance, and the `user_unlocked_frames` / `user_unlocked_backgrounds`
tables. A guard that answers 401 *after* crediting diamonds fails these tests.

`auth` resolves `INTERNAL_SERVICE_TOKEN` into a module-level constant at import
time, so `monkeypatch.setenv` alone would do nothing — the constant is what
`verify_internal_token` reads. Precedent: `test_activity_increment_internal.py`.
"""

import pytest

import auth
import models


TOKEN = "test-internal-token"
GOOD_HEADERS = {"X-Internal-Token": TOKEN}
WRONG_HEADERS = {"X-Internal-Token": "not-the-token"}
EMPTY_HEADERS = {"X-Internal-Token": ""}

USER_ID = 7701
MISSING_USER_ID = 999777

GET_PATH = f"/users/internal/{USER_ID}/diamonds"
ADD_PATH = f"/users/internal/{USER_ID}/diamonds/add"
SPEND_PATH = f"/users/internal/{USER_ID}/diamonds/spend"
UNLOCK_PATH = f"/users/internal/{USER_ID}/cosmetics/unlock"

START_DIAMONDS = 500
FRAME_SLUG = "feat170-frame"
BG_SLUG = "feat170-bg"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _token_is_configured(monkeypatch):
    monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", TOKEN)


@pytest.fixture()
def rich_user(db_session):
    user = models.User(
        id=USER_ID,
        email="wallet@example.com",
        username="wallet_user",
        hashed_password="x",
        diamonds=START_DIAMONDS,
    )
    db_session.add(user)
    db_session.add(models.CosmeticFrame(id=9001, name="Рамка", slug=FRAME_SLUG))
    db_session.add(models.CosmeticBackground(id=9002, name="Подложка", slug=BG_SLUG))
    db_session.commit()
    return user


def _diamonds(db_session):
    db_session.expire_all()
    return db_session.query(models.User).filter(
        models.User.id == USER_ID
    ).one().diamonds


def _unlocked(db_session):
    """(frames, backgrounds) unlocked for the test user."""
    db_session.expire_all()
    return (
        db_session.query(models.UserUnlockedFrame).filter(
            models.UserUnlockedFrame.user_id == USER_ID
        ).count(),
        db_session.query(models.UserUnlockedBackground).filter(
            models.UserUnlockedBackground.user_id == USER_ID
        ).count(),
    )


ADD_BODY = {"amount": 100, "reason": "feat170"}
SPEND_BODY = {"amount": 100, "reason": "feat170"}
UNLOCK_BODY = {
    "cosmetic_type": "frame",
    "cosmetic_slug": FRAME_SLUG,
    "source": "battlepass",
}

#: (label, method, path, json body) for the four routes gated by T13.
ROUTES = [
    ("get_diamonds", "get", GET_PATH, None),
    ("add_diamonds", "post", ADD_PATH, ADD_BODY),
    ("spend_diamonds", "post", SPEND_PATH, SPEND_BODY),
    ("unlock_cosmetic", "post", UNLOCK_PATH, UNLOCK_BODY),
]


def _call(client, method, path, body, headers=None):
    kwargs = {}
    if body is not None:
        kwargs["json"] = body
    if headers is not None:
        kwargs["headers"] = headers
    return getattr(client, method)(path, **kwargs)


# ══════════════════════════════════════════════════════════════════════════════
# 1. The auth matrix — and nothing moves on a rejection
# ══════════════════════════════════════════════════════════════════════════════


class TestInternalCurrencyRoutesRejectOutsiders:

    @pytest.mark.parametrize("label,method,path,body", ROUTES,
                             ids=[r[0] for r in ROUTES])
    def test_no_header_is_401(self, client, db_session, rich_user,
                              label, method, path, body):
        resp = _call(client, method, path, body)
        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"] == "Недействительный internal token"
        assert _diamonds(db_session) == START_DIAMONDS, \
            f"{label} was rejected but the diamond balance still moved"
        assert _unlocked(db_session) == (0, 0), \
            f"{label} was rejected but cosmetics were still unlocked"

    @pytest.mark.parametrize("label,method,path,body", ROUTES,
                             ids=[r[0] for r in ROUTES])
    def test_wrong_header_is_401(self, client, db_session, rich_user,
                                 label, method, path, body):
        resp = _call(client, method, path, body, WRONG_HEADERS)
        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"] == "Недействительный internal token"
        assert _diamonds(db_session) == START_DIAMONDS
        assert _unlocked(db_session) == (0, 0)

    @pytest.mark.parametrize("label,method,path,body", ROUTES,
                             ids=[r[0] for r in ROUTES])
    def test_empty_header_value_is_401(self, client, db_session, rich_user,
                                       label, method, path, body):
        resp = _call(client, method, path, body, EMPTY_HEADERS)
        assert resp.status_code == 401
        assert _diamonds(db_session) == START_DIAMONDS
        assert _unlocked(db_session) == (0, 0)

    @pytest.mark.parametrize("label,method,path,body", ROUTES,
                             ids=[r[0] for r in ROUTES])
    def test_a_player_jwt_does_not_open_them(self, client, db_session, rich_user,
                                             label, method, path, body):
        """These are service-to-service routes; the browser uses `/users/me`
        and the shop. A Bearer token must not substitute for the header."""
        resp = _call(client, method, path, body,
                     {"Authorization": "Bearer player-jwt"})
        assert resp.status_code == 401
        assert _diamonds(db_session) == START_DIAMONDS
        assert _unlocked(db_session) == (0, 0)

    def test_the_token_value_is_case_sensitive(self, client, rich_user):
        assert client.post(ADD_PATH, json=ADD_BODY,
                           headers={"X-Internal-Token": TOKEN.upper()}
                           ).status_code == 401

    def test_the_header_name_is_case_insensitive(self, client, rich_user):
        resp = client.post(ADD_PATH, json=ADD_BODY,
                           headers={"x-internal-token": TOKEN})
        assert resp.status_code == 200, resp.text

    def test_auth_runs_before_body_validation(self, client, db_session, rich_user):
        """A malformed body without the header must answer 401, not 422 — a 422
        would prove the request reached the handler."""
        resp = client.post(ADD_PATH, json={"amount": "nonsense"})
        assert resp.status_code == 401, resp.text
        assert _diamonds(db_session) == START_DIAMONDS


# ══════════════════════════════════════════════════════════════════════════════
# 2. Fail-closed: an unconfigured token disables the routes, never the check
# ══════════════════════════════════════════════════════════════════════════════


class TestInternalCurrencyRoutesFailClosed:

    @pytest.mark.parametrize("label,method,path,body", ROUTES,
                             ids=[r[0] for r in ROUTES])
    def test_empty_env_token_is_503_for_every_header(
        self, client, db_session, rich_user, monkeypatch, label, method, path, body
    ):
        monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", "")
        for headers in (None, GOOD_HEADERS, WRONG_HEADERS, EMPTY_HEADERS):
            resp = _call(client, method, path, body, headers)
            assert resp.status_code == 503, resp.text
            assert resp.json()["detail"] == "Internal service token не настроен"
        assert _diamonds(db_session) == START_DIAMONDS, \
            f"{label} 503'd but the diamond balance still moved"
        assert _unlocked(db_session) == (0, 0)


# ══════════════════════════════════════════════════════════════════════════════
# 3. With the right header the routes behave exactly as before
# ══════════════════════════════════════════════════════════════════════════════


class TestTheTokenLetsTheRoutesWork:

    def test_get_diamonds_reads_the_balance(self, client, rich_user):
        resp = client.get(GET_PATH, headers=GOOD_HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"user_id": USER_ID, "diamonds": START_DIAMONDS}

    def test_add_credits_the_balance(self, client, db_session, rich_user):
        resp = client.post(ADD_PATH, json=ADD_BODY, headers=GOOD_HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json()["diamonds"] == START_DIAMONDS + 100
        assert _diamonds(db_session) == START_DIAMONDS + 100

    def test_spend_burns_the_balance(self, client, db_session, rich_user):
        resp = client.post(SPEND_PATH, json=SPEND_BODY, headers=GOOD_HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json()["diamonds"] == START_DIAMONDS - 100
        assert _diamonds(db_session) == START_DIAMONDS - 100

    def test_unlock_grants_a_frame(self, client, db_session, rich_user):
        resp = client.post(UNLOCK_PATH, json=UNLOCK_BODY, headers=GOOD_HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json()["unlocked"] is True
        assert _unlocked(db_session) == (1, 0)

    def test_unlock_grants_a_background(self, client, db_session, rich_user):
        resp = client.post(
            UNLOCK_PATH,
            json={"cosmetic_type": "background", "cosmetic_slug": BG_SLUG,
                  "source": "battlepass"},
            headers=GOOD_HEADERS,
        )
        assert resp.status_code == 200, resp.text
        assert _unlocked(db_session) == (0, 1)

    @pytest.mark.parametrize("label,method,path,body", [
        ("get_diamonds", "get", f"/users/internal/{MISSING_USER_ID}/diamonds", None),
        ("add_diamonds", "post", f"/users/internal/{MISSING_USER_ID}/diamonds/add",
         ADD_BODY),
        ("spend_diamonds", "post",
         f"/users/internal/{MISSING_USER_ID}/diamonds/spend", SPEND_BODY),
        ("unlock_cosmetic", "post",
         f"/users/internal/{MISSING_USER_ID}/cosmetics/unlock", UNLOCK_BODY),
    ], ids=["get", "add", "spend", "unlock"])
    def test_the_guard_does_not_mask_a_real_404(self, client, rich_user,
                                                label, method, path, body):
        """With the header the request reaches the handler, so a missing user
        answers the handler's own 404 — never 401/403."""
        resp = _call(client, method, path, body, GOOD_HEADERS)
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == "Пользователь не найден"

    def test_the_handlers_own_validation_still_applies(self, client, db_session,
                                                       rich_user):
        """`amount <= 0` is the handler's 400 — the guard must let it through."""
        resp = client.post(ADD_PATH, json={"amount": 0, "reason": "x"},
                           headers=GOOD_HEADERS)
        assert resp.status_code == 400, resp.text
        assert _diamonds(db_session) == START_DIAMONDS

    def test_a_malformed_body_with_the_header_is_422_not_401(self, client,
                                                             rich_user):
        resp = client.post(ADD_PATH, json={"amount": "nonsense"},
                           headers=GOOD_HEADERS)
        assert resp.status_code == 422, resp.text


# ══════════════════════════════════════════════════════════════════════════════
# 4. The sweep that survives us — every `/internal/` route carries the guard
# ══════════════════════════════════════════════════════════════════════════════
# Committed version of the ad-hoc `app.routes` walk the developers ran by hand
# in T13. Dependencies are flattened recursively: a guard reached through a
# sub-dependency counts, but a route that simply forgot it does not.


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

    def test_the_sweep_actually_found_the_routes(self):
        """A path refactor must not silently empty the sweep. Five today:
        activity/increment (FEAT-169) plus the four closed by FEAT-170."""
        found = {f"{sorted(r.methods)[0]} {r.path}" for r in _internal_routes()}
        assert len(found) >= 5, found
        for expected in (
            "GET /users/internal/{user_id}/diamonds",
            "POST /users/internal/{user_id}/diamonds/add",
            "POST /users/internal/{user_id}/diamonds/spend",
            "POST /users/internal/{user_id}/cosmetics/unlock",
            "POST /users/internal/{user_id}/activity/increment",
        ):
            assert expected in found, (expected, sorted(found))
