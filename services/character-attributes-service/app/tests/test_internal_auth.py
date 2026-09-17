"""
FEAT-167 — the six mutating endpoints of character-attributes-service are
internal-only.

Until this feature every one of them was reachable through the gateway without
any credential at all: anyone could heal a character, hand out stats, award
experience or zero somebody's stamina from the outside. They are now gated with
the fail-closed `verify_internal_token`:

    POST /attributes/{id}/apply_modifiers
    POST /attributes/{id}/recover
    PUT  /attributes/{id}/active_experience
    PUT  /attributes/{id}/passive_experience
    POST /attributes/{id}/consume_stamina
    POST /attributes/{id}/refund_stamina

Every route is covered three ways (no header / wrong header / good header) plus
the fail-closed case where `INTERNAL_SERVICE_TOKEN` is empty — that must answer
503 and never 200. Rejected calls are also checked against the database: the
stored row must be untouched, so a guard that returns 401 *after* writing would
still fail here.

Also pinned: the GET endpoints stay open. FEAT-164 put passive-regen catch-up
inside `GET /attributes/{id}` and `/rest-status`, and battle-service reads them
on every attack — gating them would break battles, skills XP and the profile.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# SQLite test engine — configured before importing app modules
# ---------------------------------------------------------------------------

_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(_test_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

import database  # noqa: E402

database.engine = _test_engine
database.SessionLocal = _TestSessionLocal

import auth_http  # noqa: E402
import models  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app, get_db  # noqa: E402

from tests.regen_shared_tables import (  # noqa: E402
    create_shared_tables,
    drop_shared_tables,
)

# conftest.py sets INTERNAL_SERVICE_TOKEN before auth_http is imported.
TOKEN = "test-internal-token"
GOOD_HEADERS = {"X-Internal-Token": TOKEN}
WRONG_HEADERS = {"X-Internal-Token": "not-the-token"}

CHARACTER_ID = 77


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _setup_tables():
    models.Base.metadata.create_all(bind=_test_engine)
    create_shared_tables(_test_engine)
    yield
    drop_shared_tables(_test_engine)
    models.Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture(autouse=True)
def _token_is_configured(monkeypatch):
    """`auth_http` reads the secret into a module-level constant at import time,
    so tests must pin the constant — setting the env var afterwards has no
    effect (this is exactly the trap the fail-closed test below documents)."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)


@pytest.fixture()
def db_session():
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        s = _TestSessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture()
def attrs(db_session):
    """A seeded attributes row with real column names."""
    row = models.CharacterAttributes(
        character_id=CHARACTER_ID,
        strength=10,
        damage=7,
        current_health=50, max_health=100,
        current_stamina=20, max_stamina=50,
        active_experience=100,
        passive_experience=200,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _reload(db_session):
    db_session.expire_all()
    return db_session.query(models.CharacterAttributes).filter(
        models.CharacterAttributes.character_id == CHARACTER_ID
    ).one()


# ---------------------------------------------------------------------------
# The six gated routes, as (method, path suffix, body)
# ---------------------------------------------------------------------------

GATED_ROUTES = [
    ("post", "apply_modifiers", {"damage": 5}),
    ("post", "recover", {"health_recovery": 10}),
    ("put", "active_experience", {"amount": 5}),
    ("put", "passive_experience", {"amount": 5}),
    ("post", "consume_stamina", {"amount": 3}),
    ("post", "refund_stamina", {"amount": 3}),
]

_ROUTE_IDS = [f"{method.upper()} {suffix}" for method, suffix, _ in GATED_ROUTES]


def _call(client, method, suffix, body, headers=None):
    return getattr(client, method)(
        f"/attributes/{CHARACTER_ID}/{suffix}", json=body, headers=headers or {}
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. No header / wrong header — rejected, and nothing written
# ══════════════════════════════════════════════════════════════════════════════


class TestGatedRoutesRejectOutsiders:

    @pytest.mark.parametrize("method, suffix, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_no_header_returns_401(self, client, db_session, attrs,
                                   method, suffix, body):
        before = (_reload(db_session).damage, _reload(db_session).current_health,
                  _reload(db_session).current_stamina,
                  _reload(db_session).active_experience,
                  _reload(db_session).passive_experience)

        response = _call(client, method, suffix, body)

        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "Недействительный internal token"
        row = _reload(db_session)
        assert (row.damage, row.current_health, row.current_stamina,
                row.active_experience, row.passive_experience) == before, \
            f"{suffix} modified the row despite rejecting the request"

    @pytest.mark.parametrize("method, suffix, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_wrong_header_returns_401(self, client, db_session, attrs,
                                      method, suffix, body):
        response = _call(client, method, suffix, body, WRONG_HEADERS)
        assert response.status_code == 401
        assert response.json()["detail"] == "Недействительный internal token"

    @pytest.mark.parametrize("method, suffix, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_empty_header_value_returns_401(self, client, attrs,
                                            method, suffix, body):
        response = _call(client, method, suffix, body,
                         {"X-Internal-Token": ""})
        assert response.status_code == 401

    @pytest.mark.parametrize("method, suffix, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_player_bearer_token_is_not_accepted(self, client, attrs,
                                                 method, suffix, body):
        """These routes have no player-facing caller: a JWT must not open them
        (locations-service used to forward the player's token on its grants)."""
        response = _call(client, method, suffix, body,
                         {"Authorization": "Bearer player-jwt"})
        assert response.status_code == 401

    @pytest.mark.parametrize("method, suffix, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_header_name_is_case_insensitive_but_value_is_not(
        self, client, attrs, method, suffix, body
    ):
        """HTTP header names are case-insensitive (so callers may send
        `x-internal-token`), the secret itself must match exactly."""
        assert _call(client, method, suffix, body,
                     {"x-internal-token": TOKEN}).status_code not in (401, 503)
        assert _call(client, method, suffix, body,
                     {"X-Internal-Token": TOKEN.upper()}).status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 2. Fail-closed: an unconfigured service rejects everything with 503
# ══════════════════════════════════════════════════════════════════════════════


class TestFailClosedWithoutToken:

    @pytest.mark.parametrize("method, suffix, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_empty_token_env_returns_503(self, client, db_session, attrs,
                                         monkeypatch, method, suffix, body):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        response = _call(client, method, suffix, body, GOOD_HEADERS)
        assert response.status_code == 503, response.text
        assert response.json()["detail"] == "Internal service token не настроен"

    @pytest.mark.parametrize("method, suffix, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_empty_token_env_never_allows_the_call(self, client, db_session, attrs,
                                                   monkeypatch, method, suffix, body):
        """The whole point of fail-closed: no configuration must never mean
        "no authentication"."""
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        before = _reload(db_session)
        snapshot = (before.damage, before.current_health, before.current_stamina,
                    before.active_experience, before.passive_experience)

        for headers in ({}, GOOD_HEADERS, WRONG_HEADERS,
                        {"X-Internal-Token": ""}):
            response = _call(client, method, suffix, body, headers)
            assert response.status_code == 503

        row = _reload(db_session)
        assert (row.damage, row.current_health, row.current_stamina,
                row.active_experience, row.passive_experience) == snapshot


# ══════════════════════════════════════════════════════════════════════════════
# 3. Good header — the internal callers still work, and really write
# ══════════════════════════════════════════════════════════════════════════════


class TestGatedRoutesAcceptTheInternalToken:

    @pytest.mark.parametrize("method, suffix, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_good_header_passes_the_guard(self, client, attrs,
                                          method, suffix, body):
        response = _call(client, method, suffix, body, GOOD_HEADERS)
        assert response.status_code not in (401, 403, 503), response.text

    def test_apply_modifiers_writes_the_damage_delta(self, client, db_session, attrs):
        response = _call(client, "post", "apply_modifiers", {"damage": 5},
                         GOOD_HEADERS)
        assert response.status_code == 200, response.text
        assert _reload(db_session).damage == 12  # 7 + 5

    def test_recover_writes_the_health(self, client, db_session, attrs):
        response = _call(client, "post", "recover", {"health_recovery": 10}, GOOD_HEADERS)
        assert response.status_code == 200, response.text
        assert _reload(db_session).current_health == 60

    def test_active_experience_writes_the_amount(self, client, db_session, attrs):
        response = _call(client, "put", "active_experience", {"amount": -25},
                         GOOD_HEADERS)
        assert response.status_code == 200, response.text
        assert _reload(db_session).active_experience == 75

    def test_passive_experience_writes_the_amount(self, client, db_session, attrs):
        response = _call(client, "put", "passive_experience", {"amount": 30},
                         GOOD_HEADERS)
        assert response.status_code == 200, response.text
        assert _reload(db_session).passive_experience == 230

    def test_consume_and_refund_stamina_write_the_amount(self, client, db_session,
                                                          attrs):
        consumed = _call(client, "post", "consume_stamina", {"amount": 5},
                         GOOD_HEADERS)
        assert consumed.status_code == 200, consumed.text
        assert _reload(db_session).current_stamina == 15

        refunded = _call(client, "post", "refund_stamina", {"amount": 5},
                         GOOD_HEADERS)
        assert refunded.status_code == 200, refunded.text
        assert _reload(db_session).current_stamina == 20


# ══════════════════════════════════════════════════════════════════════════════
# 4. The GETs must stay open (FEAT-164 regen lives in them)
# ══════════════════════════════════════════════════════════════════════════════


class TestReadsStayOpen:

    def test_get_attributes_needs_no_token(self, client, attrs):
        response = client.get(f"/attributes/{CHARACTER_ID}")
        assert response.status_code == 200, response.text
        assert response.json()["character_id"] == CHARACTER_ID

    def test_get_rest_status_needs_no_token(self, client, attrs):
        response = client.get(f"/attributes/{CHARACTER_ID}/rest-status")
        assert response.status_code == 200, response.text

    def test_get_passive_experience_needs_no_token(self, client, attrs):
        """character-service reads this one, and the nginx second layer only
        blocks the *mutating* methods on this path (`limit_except GET HEAD`)."""
        response = client.get(f"/attributes/{CHARACTER_ID}/passive_experience")
        assert response.status_code == 200, response.text

    def test_the_gate_is_on_exactly_the_six_routes(self):
        """A sweep: `verify_internal_token` must guard the six mutating routes
        and nothing that a GET path depends on. If somebody gates a GET, battles
        and the profile break — if somebody un-gates one of the six, the hole is
        back."""
        from fastapi.routing import APIRoute

        gated = set()
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            names = {
                getattr(dep.call, "__name__", type(dep.call).__name__)
                for dep in route.dependant.dependencies
            }
            if "verify_internal_token" in names:
                for method in route.methods:
                    if method in ("GET", "HEAD"):
                        pytest.fail(
                            f"{method} {route.path} is gated by the internal "
                            "token — FEAT-164 regen catch-up runs in the GETs"
                        )
                    gated.add((method, route.path))

        expected = {
            ("POST", "/attributes/{character_id}/apply_modifiers"),
            ("POST", "/attributes/{character_id}/recover"),
            ("PUT", "/attributes/{character_id}/active_experience"),
            ("PUT", "/attributes/{character_id}/passive_experience"),
            ("POST", "/attributes/{character_id}/consume_stamina"),
            ("POST", "/attributes/{character_id}/refund_stamina"),
        }
        assert expected <= gated, f"no longer gated: {sorted(expected - gated)}"


# ══════════════════════════════════════════════════════════════════════════════
# 5. FEAT-167 #17 — the two routes the Reviewer found still open
# ══════════════════════════════════════════════════════════════════════════════
# `POST /attributes/cumulative_stats/increment` was reachable anonymously
# through the gateway (an anonymous POST answered 200 «Stats updated»). It pumps
# pve_kills / pvp_wins / damage totals / win streaks **and** returns
# `newly_unlocked_perks` — i.e. it handed out perks for free. Its own docstring
# already called it internal.
#
# `POST /attributes/` (create the attributes row) reached its handler too
# (422 on the schema, not 401), so anyone could seed attribute rows for
# arbitrary character ids.
#
# Both are service-to-service only, so both got the same fail-closed gate.
# Callers: increment ← battle-service, locations-service, inventory-service,
# skills-service; create ← character-service (character creation, admin NPC,
# mob spawn).

INCREMENT_PATH = "/attributes/cumulative_stats/increment"
CREATE_PATH = "/attributes/"

_INCREMENT_BODY = {
    "character_id": CHARACTER_ID,
    "increments": {"pvp_wins": 1, "pve_kills": 3},
}


def _cumulative(db_session):
    db_session.expire_all()
    return db_session.query(models.CharacterCumulativeStats).filter(
        models.CharacterCumulativeStats.character_id == CHARACTER_ID
    ).one_or_none()


class TestCumulativeIncrementIsInternalOnly:
    """The free-perks hole: no counter may move without the internal token."""

    def test_no_header_returns_401_and_writes_nothing(self, client, db_session, attrs):
        response = client.post(INCREMENT_PATH, json=_INCREMENT_BODY)
        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "Недействительный internal token"
        assert _cumulative(db_session) is None, \
            "the row was created despite rejecting the request"

    def test_wrong_header_returns_401(self, client, db_session, attrs):
        response = client.post(INCREMENT_PATH, json=_INCREMENT_BODY,
                               headers=WRONG_HEADERS)
        assert response.status_code == 401
        assert response.json()["detail"] == "Недействительный internal token"
        assert _cumulative(db_session) is None

    def test_empty_header_value_returns_401(self, client, db_session, attrs):
        response = client.post(INCREMENT_PATH, json=_INCREMENT_BODY,
                               headers={"X-Internal-Token": ""})
        assert response.status_code == 401
        assert _cumulative(db_session) is None

    def test_player_bearer_token_is_not_accepted(self, client, db_session, attrs):
        response = client.post(INCREMENT_PATH, json=_INCREMENT_BODY,
                               headers={"Authorization": "Bearer player-jwt"})
        assert response.status_code == 401
        assert _cumulative(db_session) is None

    def test_empty_token_env_returns_503_and_never_200(self, client, db_session,
                                                       attrs, monkeypatch):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        for headers in ({}, GOOD_HEADERS, WRONG_HEADERS,
                        {"X-Internal-Token": ""}):
            response = client.post(INCREMENT_PATH, json=_INCREMENT_BODY,
                                   headers=headers)
            assert response.status_code == 503, response.text
            assert response.json()["detail"] == "Internal service token не настроен"
        assert _cumulative(db_session) is None

    def test_no_perk_is_unlocked_for_an_anonymous_caller(self, client, attrs):
        """The specific damage of this hole: `newly_unlocked_perks` must never
        be reachable without the token, whatever the body claims."""
        response = client.post(
            INCREMENT_PATH,
            json={"character_id": CHARACTER_ID,
                  "increments": {"pvp_wins": 1000, "pve_kills": 1000}},
        )
        assert response.status_code == 401
        assert "newly_unlocked_perks" not in response.json()

    def test_good_header_still_increments(self, client, db_session, attrs):
        """battle / locations / inventory / skills must keep working."""
        response = client.post(INCREMENT_PATH, json=_INCREMENT_BODY,
                               headers=GOOD_HEADERS)
        assert response.status_code == 200, response.text
        assert response.json()["detail"] == "Stats updated"
        row = _cumulative(db_session)
        assert row is not None
        assert (row.pvp_wins, row.pve_kills) == (1, 3)

    def test_header_name_is_case_insensitive_but_value_is_not(self, client, attrs):
        assert client.post(INCREMENT_PATH, json=_INCREMENT_BODY,
                           headers={"x-internal-token": TOKEN}
                           ).status_code not in (401, 503)
        assert client.post(INCREMENT_PATH, json=_INCREMENT_BODY,
                           headers={"X-Internal-Token": TOKEN.upper()}
                           ).status_code == 401

    def test_the_cumulative_get_stays_open(self, client, attrs):
        """`GET /attributes/{id}/cumulative_stats` is a read used by the profile
        — the gate must not have spilled onto it."""
        response = client.get(f"/attributes/{CHARACTER_ID}/cumulative_stats")
        assert response.status_code == 200, response.text


class TestCreateAttributesIsInternalOnly:
    """`POST /attributes/` — character creation, NPCs and mob spawns only."""

    NEW_CHARACTER_ID = 4343

    def _body(self):
        return {"character_id": self.NEW_CHARACTER_ID, "strength": 10}

    def _row(self, db_session):
        db_session.expire_all()
        return db_session.query(models.CharacterAttributes).filter(
            models.CharacterAttributes.character_id == self.NEW_CHARACTER_ID
        ).one_or_none()

    def test_no_header_returns_401_and_creates_nothing(self, client, db_session):
        response = client.post(CREATE_PATH, json=self._body())
        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "Недействительный internal token"
        assert self._row(db_session) is None

    def test_wrong_header_returns_401(self, client, db_session):
        response = client.post(CREATE_PATH, json=self._body(),
                               headers=WRONG_HEADERS)
        assert response.status_code == 401
        assert self._row(db_session) is None

    def test_empty_header_value_returns_401(self, client, db_session):
        response = client.post(CREATE_PATH, json=self._body(),
                               headers={"X-Internal-Token": ""})
        assert response.status_code == 401
        assert self._row(db_session) is None

    def test_player_bearer_token_is_not_accepted(self, client, db_session):
        response = client.post(CREATE_PATH, json=self._body(),
                               headers={"Authorization": "Bearer player-jwt"})
        assert response.status_code == 401
        assert self._row(db_session) is None

    def test_auth_runs_before_schema_validation(self, client):
        """The reported symptom was a 422: the request reached the handler and
        only the body shape stopped it. Auth must answer first, so a malformed
        anonymous body is still a 401."""
        response = client.post(CREATE_PATH, json={"nonsense": True})
        assert response.status_code == 401, response.text

    def test_empty_token_env_returns_503_and_never_200(self, client, db_session,
                                                       monkeypatch):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        for headers in ({}, GOOD_HEADERS, WRONG_HEADERS,
                        {"X-Internal-Token": ""}):
            response = client.post(CREATE_PATH, json=self._body(),
                                   headers=headers)
            assert response.status_code == 503, response.text
            assert response.json()["detail"] == "Internal service token не настроен"
        assert self._row(db_session) is None

    def test_good_header_creates_the_row(self, client, db_session):
        """Character creation must keep working end to end."""
        response = client.post(CREATE_PATH, json=self._body(),
                               headers=GOOD_HEADERS)
        assert response.status_code == 200, response.text
        assert self._row(db_session) is not None


class TestTheTwoNewGatesAreOnTheRouteTable:
    """A sweep, so nobody can quietly un-gate either route."""

    def test_both_routes_require_the_internal_token(self):
        from fastapi.routing import APIRoute

        wanted = {
            ("POST", "/attributes/cumulative_stats/increment"),
            ("POST", "/attributes/"),
        }
        found = set()
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            names = {
                getattr(dep.call, "__name__", type(dep.call).__name__)
                for dep in route.dependant.dependencies
            }
            if "verify_internal_token" not in names:
                continue
            for method in route.methods:
                found.add((method, route.path))
        assert wanted <= found, f"no longer gated: {sorted(wanted - found)}"
