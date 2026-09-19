"""
FEAT-169 §3.1 group 3 — the three `/attributes/internal/*` routes that used to
be protected by nothing but an nginx rule are now gated with the fail-closed
`verify_internal_token`:

    POST /attributes/internal/settle-regen
    POST /attributes/internal/{id}/satiety
    POST /attributes/internal/{id}/reconcile-perks

`test_internal_auth.py` (FEAT-167) covers the six mutating `/attributes/{id}/…`
routes the same way; this file is its sibling for the three internal ones.

Two things beyond the plain matrix:

  * **`reconcile-perks` had no HTTP test at all** (§2.4: "No test file currently
    exercises `update-durability` or `reconcile-perks` over HTTP — a coverage
    gap worth closing while here"). Its handler is what inventory-service and
    character-service call after a gear change or a level-up, and **all three
    call sites swallow the error** — so a broken gate or a broken handler would
    show up only as perks quietly never updating. A real happy path over HTTP
    (grant *and* revoke, with the bonus actually written to the attributes row)
    is therefore part of this file, not only the 401/503 matrix.

  * **The in-process callers must stay untouched.** `reconcile_perks` is also
    invoked as a direct Python call from `GET /attributes/{id}/perks`
    (`main.py:345`), from the upgrade path (`main.py:697`) and from
    `regen.py:341`. Those are not HTTP requests and must keep working with no
    token whatsoever — `TestInProcessReconcileIsNotGated` pins that, so nobody
    "fixes" the gate by putting it inside `reconcile_perks` itself.

Rejected calls are also checked against the database: a guard that answers 401
*after* writing would still fail here.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import create_engine, event
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
    add_character,
    create_shared_tables,
    drop_shared_tables,
)

TOKEN = "test-internal-token"
GOOD_HEADERS = {"X-Internal-Token": TOKEN}
WRONG_HEADERS = {"X-Internal-Token": "not-the-token"}

CID = 909

SETTLE_PATH = "/attributes/internal/settle-regen"
SATIETY_PATH = f"/attributes/internal/{CID}/satiety"
RECONCILE_PATH = f"/attributes/internal/{CID}/reconcile-perks"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _setup_tables():
    # Shared tables first: another module registers a reduced `characters`
    # model in Base.metadata, and create_all then skips the existing table.
    create_shared_tables(_test_engine)
    models.Base.metadata.create_all(bind=_test_engine)
    yield
    drop_shared_tables(_test_engine)
    models.Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture(autouse=True)
def _token_is_configured(monkeypatch):
    """`auth_http` resolves the secret into a module-level constant at import
    time, so the constant is what must be pinned — `monkeypatch.setenv` alone
    would have no effect at all (the trap documented in FEAT-167 §2.0)."""
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)


@pytest.fixture()
def db_session():
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    def _override_get_db():
        s = _TestSessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _satiety_body(**kw):
    body = {
        "item_id": 345,
        "source_item_name": "Жаркое из кабана",
        "rarity": "rare",
        "modifiers": {"strength": 2},
        "recovery": {
            "health_recovery": 30,
            "mana_recovery": 0,
            "energy_recovery": 0,
            "stamina_recovery": 0,
        },
    }
    body.update(kw)
    return body


def _seed_attributes(db, character_id=CID, **values):
    add_character(db, character_id)
    base = dict(
        current_health=50, max_health=100,
        current_mana=75, max_mana=75,
        current_energy=50, max_energy=50,
        current_stamina=100, max_stamina=100,
        strength=10, damage=0,
    )
    base.update(values)
    row = models.CharacterAttributes(character_id=character_id, **base)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _seed_cumulative(db, character_id=CID, **values):
    row = models.CharacterCumulativeStats(character_id=character_id, **values)
    db.add(row)
    db.commit()
    return row


_PERK_BONUS = {"flat": {"damage": 3}, "percent": {}, "contextual": {}, "passive": {}}
_STRENGTH_COND = [
    {"type": "attribute", "stat": "strength", "operator": ">=", "value": 15}
]


def _seed_perk(db, conditions=None, bonuses=None, **overrides):
    defaults = dict(
        name="Перк силача",
        description="perk",
        category="combat",
        rarity="common",
        icon="icon.png",
        conditions=conditions if conditions is not None else _STRENGTH_COND,
        bonuses=bonuses if bonuses is not None else _PERK_BONUS,
        sort_order=0,
        is_active=True,
    )
    defaults.update(overrides)
    perk = models.Perk(**defaults)
    db.add(perk)
    db.commit()
    db.refresh(perk)
    return perk


def _reload(db, character_id=CID):
    db.expire_all()
    return db.query(models.CharacterAttributes).filter_by(
        character_id=character_id
    ).one()


def _character_perks(db, character_id=CID):
    db.expire_all()
    return db.query(models.CharacterPerk).filter_by(character_id=character_id).all()


def _satiety_row(db, character_id=CID):
    db.expire_all()
    return db.query(models.CharacterSatiety).filter_by(
        character_id=character_id
    ).one_or_none()


@pytest.fixture()
def seeded(db_session):
    """A character whose strength already satisfies the perk condition, plus
    the perk itself — so every gated call below *would* change something if it
    were allowed through."""
    attrs = _seed_attributes(db_session, strength=20)
    _seed_cumulative(db_session)
    perk = _seed_perk(db_session)
    return attrs, perk


# ---------------------------------------------------------------------------
# The three gated routes, as (name, path, body)
# ---------------------------------------------------------------------------

GATED_ROUTES = [
    ("settle-regen", SETTLE_PATH, {"character_ids": [CID]}),
    ("satiety", SATIETY_PATH, _satiety_body()),
    ("reconcile-perks", RECONCILE_PATH, None),
]

_ROUTE_IDS = [name for name, _, _ in GATED_ROUTES]


def _call(client, path, body, headers=None):
    kwargs = {"headers": headers or {}}
    if body is not None:
        kwargs["json"] = body
    return client.post(path, **kwargs)


def _snapshot(db):
    """Everything the three routes could possibly move."""
    row = _reload(db)
    return (
        row.strength, row.damage, row.current_health,
        row.current_stamina, row.regen_anchor_at,
        len(_character_perks(db)),
        _satiety_row(db) is not None,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. No header / wrong header — rejected, and nothing written
# ══════════════════════════════════════════════════════════════════════════════


class TestInternalRoutesRejectOutsiders:

    @pytest.mark.parametrize("name, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_no_header_returns_401_and_writes_nothing(
        self, client, db_session, seeded, name, path, body,
    ):
        before = _snapshot(db_session)

        response = _call(client, path, body)

        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "Недействительный internal token"
        assert _snapshot(db_session) == before, (
            f"{name} modified the database despite rejecting the request"
        )

    @pytest.mark.parametrize("name, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_wrong_header_returns_401_and_writes_nothing(
        self, client, db_session, seeded, name, path, body,
    ):
        before = _snapshot(db_session)

        response = _call(client, path, body, WRONG_HEADERS)

        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "Недействительный internal token"
        assert _snapshot(db_session) == before

    @pytest.mark.parametrize("name, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_empty_header_value_returns_401(
        self, client, db_session, seeded, name, path, body,
    ):
        before = _snapshot(db_session)
        response = _call(client, path, body, {"X-Internal-Token": ""})
        assert response.status_code == 401
        assert _snapshot(db_session) == before

    @pytest.mark.parametrize("name, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_player_bearer_token_is_not_accepted(
        self, client, db_session, seeded, name, path, body,
    ):
        """None of the three has a browser caller (§2.4: "None of the eight is
        called from the frontend"), so a player JWT must not open them."""
        before = _snapshot(db_session)
        response = _call(client, path, body,
                         {"Authorization": "Bearer player-jwt"})
        assert response.status_code == 401
        assert _snapshot(db_session) == before

    @pytest.mark.parametrize("name, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_header_name_is_case_insensitive_but_value_is_not(
        self, client, seeded, name, path, body,
    ):
        """HTTP header names are case-insensitive (callers may send
        `x-internal-token`); the secret itself must match byte for byte."""
        assert _call(client, path, body,
                     {"x-internal-token": TOKEN}).status_code not in (401, 503)
        assert _call(client, path, body,
                     {"X-Internal-Token": TOKEN.upper()}).status_code == 401

    @pytest.mark.parametrize("name, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_auth_runs_before_body_validation(self, client, seeded,
                                              name, path, body):
        """An anonymous request with a nonsense body must be a 401, not a 422:
        a 422 would mean the request reached the handler."""
        response = client.post(path, json={"nonsense": True})
        assert response.status_code == 401, response.text


# ══════════════════════════════════════════════════════════════════════════════
# 2. Fail-closed: an unconfigured service rejects everything with 503
# ══════════════════════════════════════════════════════════════════════════════


class TestFailClosedWithoutToken:

    @pytest.mark.parametrize("name, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_empty_token_env_returns_503(self, client, seeded, monkeypatch,
                                         name, path, body):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        response = _call(client, path, body, GOOD_HEADERS)
        assert response.status_code == 503, response.text
        assert response.json()["detail"] == "Internal service token не настроен"

    @pytest.mark.parametrize("name, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_empty_token_env_never_allows_the_call(
        self, client, db_session, seeded, monkeypatch, name, path, body,
    ):
        """The whole point of fail-closed: "not configured" must never come out
        as "not authenticated"."""
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        before = _snapshot(db_session)

        for headers in ({}, GOOD_HEADERS, WRONG_HEADERS,
                        {"X-Internal-Token": ""}):
            response = _call(client, path, body, headers)
            assert response.status_code == 503, response.text
            assert response.json()["detail"] == "Internal service token не настроен"

        assert _snapshot(db_session) == before


# ══════════════════════════════════════════════════════════════════════════════
# 3. Good header — the real service-to-service callers still work
# ══════════════════════════════════════════════════════════════════════════════


class TestInternalRoutesAcceptTheToken:

    @pytest.mark.parametrize("name, path, body", GATED_ROUTES, ids=_ROUTE_IDS)
    def test_good_header_passes_the_guard(self, client, seeded,
                                          name, path, body):
        response = _call(client, path, body, GOOD_HEADERS)
        assert response.status_code not in (401, 403, 503), response.text

    def test_settle_regen_reports_settled_and_missing(self, client, seeded):
        """party-service calls this one before reading a squad's HP."""
        response = client.post(
            SETTLE_PATH,
            json={"character_ids": [CID, 4242]},
            headers=GOOD_HEADERS,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["settled"] == [CID]
        assert payload["missing"] == [4242]

    def test_satiety_creates_the_row_and_applies_the_modifier(
        self, client, db_session, seeded,
    ):
        """inventory-service's eat-food path — the one internal route here that
        surfaces its error to the player."""
        response = client.post(SATIETY_PATH, json=_satiety_body(),
                               headers=GOOD_HEADERS)
        assert response.status_code == 201, response.text
        assert _satiety_row(db_session) is not None
        assert _reload(db_session).strength == 22  # 20 + 2


# ══════════════════════════════════════════════════════════════════════════════
# 4. reconcile-perks over HTTP — the route that had no test at all
# ══════════════════════════════════════════════════════════════════════════════
# Callers: inventory-service `main.py:844` (sync) and `~:870` (async) after a
# gear change, character-service `main.py:1963` after a level-up. All three log
# and continue, so nothing anywhere would raise if this route were broken — the
# perks would simply stop moving. Hence a functional test, not just a matrix.


class TestReconcilePerksOverHttp:

    def test_grants_the_perk_and_writes_the_bonus(self, client, db_session, seeded):
        _attrs, perk = seeded

        response = client.post(RECONCILE_PATH, headers=GOOD_HEADERS)

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["detail"] == "Perks reconciled"
        assert perk.id in [g["id"] for g in payload["granted"]]
        assert payload["revoked"] == []

        rows = _character_perks(db_session)
        assert [r.perk_id for r in rows] == [perk.id]
        assert _reload(db_session).damage == 3, "the perk bonus was not applied"

    def test_revokes_the_perk_when_the_condition_stops_holding(
        self, client, db_session, seeded,
    ):
        """The gear-change case inventory-service calls it for: unequipping the
        strength item must take the perk *and* its bonus away again."""
        attrs, perk = seeded
        assert client.post(RECONCILE_PATH, headers=GOOD_HEADERS).status_code == 200
        assert _reload(db_session).damage == 3

        attrs = _reload(db_session)
        attrs.strength = 5
        db_session.commit()

        response = client.post(RECONCILE_PATH, headers=GOOD_HEADERS)

        assert response.status_code == 200, response.text
        assert perk.id in [r["id"] for r in response.json()["revoked"]]
        assert _character_perks(db_session) == []
        assert _reload(db_session).damage == 0, "the bonus was not reversed"

    def test_is_idempotent(self, client, db_session, seeded):
        """battle/inventory may call it twice for one gear change — the second
        pass must not double the bonus or flip the perk."""
        client.post(RECONCILE_PATH, headers=GOOD_HEADERS)
        second = client.post(RECONCILE_PATH, headers=GOOD_HEADERS)

        assert second.status_code == 200, second.text
        assert second.json()["granted"] == []
        assert second.json()["revoked"] == []
        assert len(_character_perks(db_session)) == 1
        assert _reload(db_session).damage == 3

    def test_unmet_condition_grants_nothing(self, client, db_session):
        _seed_attributes(db_session, strength=5)
        _seed_cumulative(db_session)
        _seed_perk(db_session)

        response = client.post(RECONCILE_PATH, headers=GOOD_HEADERS)

        assert response.status_code == 200, response.text
        assert response.json()["granted"] == []
        assert _character_perks(db_session) == []

    def test_unknown_character_does_not_500(self, client):
        """Mobs and freshly-deleted characters reach this route too; a 500 here
        would spam the caller's logs on every gear change."""
        response = client.post(
            "/attributes/internal/999999/reconcile-perks", headers=GOOD_HEADERS,
        )
        assert response.status_code != 500, response.text

    def test_anonymous_call_grants_no_perk(self, client, db_session, seeded):
        """The hole this closes: before FEAT-169 anyone could drive a full perk
        evaluation (and the DB writes behind it) from outside."""
        response = client.post(RECONCILE_PATH)

        assert response.status_code == 401
        assert "granted" not in response.json()
        assert _character_perks(db_session) == []
        assert _reload(db_session).damage == 0


# ══════════════════════════════════════════════════════════════════════════════
# 5. The in-process callers of reconcile_perks are NOT gated
# ══════════════════════════════════════════════════════════════════════════════
# `main.py:345` (GET /perks self-heal), `main.py:697` (after an upgrade) and
# `regen.py:341` call `reconcile_perks` as a plain Python function. Task #4 says
# explicitly: "Do **not** touch the in-process `reconcile_perks` calls". If
# somebody ever moves the token check inside `perk_evaluator.reconcile_perks`,
# these tests fail instead of the profile page quietly breaking.


class TestInProcessReconcileIsNotGated:

    def test_get_perks_self_heals_without_any_token(self, client, db_session, seeded):
        _attrs, perk = seeded

        response = client.get(f"/attributes/{CID}/perks")

        assert response.status_code == 200, response.text
        assert [r.perk_id for r in _character_perks(db_session)] == [perk.id], (
            "the in-process self-heal in GET /perks stopped working"
        )

    def test_reconcile_perks_function_takes_no_token(self, db_session, seeded):
        from perk_evaluator import reconcile_perks

        result = reconcile_perks(db_session, CID)

        assert [g["id"] for g in result["granted"]] == [seeded[1].id]

    def test_settle_character_still_reconciles_in_process(self, db_session, seeded):
        """`regen.settle_character` -> `reconcile_perks_after_expiry` is the
        third in-process caller; it must not need a header either."""
        import regen

        assert regen.settle_character(db_session, CID) is not None


# ══════════════════════════════════════════════════════════════════════════════
# 6. Route-table sweep — nobody may quietly un-gate one of the three
# ══════════════════════════════════════════════════════════════════════════════


class TestTheThreeRoutesAreOnTheGatedList:

    def test_all_three_require_the_internal_token(self):
        from fastapi.routing import APIRoute

        wanted = {
            ("POST", "/attributes/internal/settle-regen"),
            ("POST", "/attributes/internal/{character_id}/satiety"),
            ("POST", "/attributes/internal/{character_id}/reconcile-perks"),
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

    def test_every_internal_route_of_this_service_is_gated(self):
        """A prefix sweep: `/attributes/internal/…` is internal by name, so a
        new route added there without the dependency is a hole by construction.
        """
        from fastapi.routing import APIRoute

        offenders = []
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            if "/internal/" not in route.path:
                continue
            names = {
                getattr(dep.call, "__name__", type(dep.call).__name__)
                for dep in route.dependant.dependencies
            }
            if "verify_internal_token" not in names:
                offenders.append(f"{sorted(route.methods)} {route.path}")

        assert not offenders, (
            "internal routes without verify_internal_token: " + "; ".join(offenders)
        )
