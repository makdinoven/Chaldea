"""
FEAT-154 (task #33) — starter kits keyed by (class x origin).

Covers:
(a) crud.resolve_starter_kit — the one and only fallback chain
    (exact pair -> class default -> empty), including N10: a request for
    origin_id = 0 is reported as "exact", not "class_default"
(b) GET /characters/starter-kits/resolve — including resolved_from and the 404
(c) PUT / DELETE /characters/starter-kits/{class_id}/origins/{origin_id}
(d) GET /characters/starter-kits/coverage
(e) RBAC negatives on every writing / privileged route

The two backward-compatibility cases (GET without params returns only defaults,
PUT /starter-kits/{class_id} still writes the default) already live in
test_starter_kits.py and are not duplicated here.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

import crud
import database
from database import Base
import models
from auth_http import get_admin_user, get_current_user_via_http, OAUTH2_SCHEME, UserRead
from main import app, get_db


ORIGIN_SHINZO = 7
ORIGIN_MIDDENGERD = 3

_ADMIN_USER = UserRead(id=1, username="admin", role="admin", permissions=[
    "characters:create", "characters:read", "characters:update",
    "characters:delete", "characters:approve",
])
_PLAIN_USER = UserRead(id=42, username="player", role="user", permissions=[])
_EDITOR_USER = UserRead(id=9, username="editor", role="editor", permissions=["items:create"])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
def make_client(db_session):
    def _factory(user=_ADMIN_USER):
        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        if user is not None:
            app.dependency_overrides[get_admin_user] = lambda: user
            app.dependency_overrides[get_current_user_via_http] = lambda: user
            app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"
        else:
            app.dependency_overrides.pop(get_admin_user, None)
            app.dependency_overrides.pop(get_current_user_via_http, None)
            app.dependency_overrides.pop(OAUTH2_SCHEME, None)
        return TestClient(app)

    yield _factory
    app.dependency_overrides.clear()


@pytest.fixture
def client(make_client):
    return make_client(_ADMIN_USER)


@pytest.fixture
def anon_client(make_client):
    return make_client(None)


def _seed_kit(db, class_id=1, origin_id=0, items=None, skills=None, currency=100):
    kit = models.StarterKit(
        class_id=class_id,
        origin_id=origin_id,
        items=items if items is not None else [{"item_id": 4, "quantity": 1}],
        skills=skills if skills is not None else [{"skill_id": 1}],
        currency_amount=currency,
    )
    db.add(kit)
    db.commit()
    db.refresh(kit)
    return kit


def _kit_payload(item_id=5, skill_id=6, currency=250):
    return {
        "items": [{"item_id": item_id, "quantity": 1}],
        "skills": [{"skill_id": skill_id}],
        "currency_amount": currency,
    }


# ===========================================================================
# (a) crud.resolve_starter_kit
# ===========================================================================

class TestResolveStarterKit:
    def test_exact_pair_wins(self, db_session):
        _seed_kit(db_session, class_id=1, origin_id=0, currency=100)
        _seed_kit(
            db_session, class_id=1, origin_id=ORIGIN_SHINZO,
            items=[{"item_id": 42, "quantity": 2}], skills=[{"skill_id": 9}], currency=333,
        )

        resolved = crud.resolve_starter_kit(db_session, 1, ORIGIN_SHINZO)
        assert resolved["resolved_from"] == "exact"
        assert resolved["origin_id"] == ORIGIN_SHINZO
        assert resolved["items"] == [{"item_id": 42, "quantity": 2}]
        assert resolved["skills"] == [{"skill_id": 9}]
        assert resolved["currency_amount"] == 333

    def test_falls_back_to_the_class_default(self, db_session):
        _seed_kit(db_session, class_id=1, origin_id=0,
                  items=[{"item_id": 4, "quantity": 1}], currency=100)

        resolved = crud.resolve_starter_kit(db_session, 1, ORIGIN_MIDDENGERD)
        assert resolved["resolved_from"] == "class_default"
        # The echoed origin_id is what was asked for, the contents are the default's.
        assert resolved["origin_id"] == ORIGIN_MIDDENGERD
        assert resolved["items"] == [{"item_id": 4, "quantity": 1}]
        assert resolved["currency_amount"] == 100

    def test_empty_kit_when_the_class_has_none_at_all(self, db_session):
        resolved = crud.resolve_starter_kit(db_session, 1, ORIGIN_SHINZO)
        assert resolved == {
            "class_id": 1, "origin_id": ORIGIN_SHINZO, "resolved_from": "none",
            "items": [], "skills": [], "currency_amount": 0,
        }

    def test_origin_zero_is_exact_not_a_fallback(self, db_session):
        """N10 — nothing was fallen back to, so it is not 'class_default'."""
        _seed_kit(db_session, class_id=1, origin_id=0)

        resolved = crud.resolve_starter_kit(db_session, 1, 0)
        assert resolved["resolved_from"] == "exact"
        assert resolved["origin_id"] == 0

    def test_origin_none_behaves_like_the_default(self, db_session):
        _seed_kit(db_session, class_id=1, origin_id=0)

        resolved = crud.resolve_starter_kit(db_session, 1, None)
        assert resolved["resolved_from"] == "exact"
        assert resolved["origin_id"] == 0

    def test_origin_zero_without_a_default_is_none(self, db_session):
        resolved = crud.resolve_starter_kit(db_session, 1, 0)
        assert resolved["resolved_from"] == "none"
        assert resolved["items"] == []

    def test_an_override_for_another_class_is_not_used(self, db_session):
        _seed_kit(db_session, class_id=2, origin_id=ORIGIN_SHINZO, currency=999)

        resolved = crud.resolve_starter_kit(db_session, 1, ORIGIN_SHINZO)
        assert resolved["resolved_from"] == "none"

    def test_an_override_for_another_origin_is_not_used(self, db_session):
        _seed_kit(db_session, class_id=1, origin_id=ORIGIN_SHINZO, currency=999)

        resolved = crud.resolve_starter_kit(db_session, 1, ORIGIN_MIDDENGERD)
        assert resolved["resolved_from"] == "none"
        assert resolved["currency_amount"] == 0

    def test_result_is_a_plain_json_safe_dict(self, db_session):
        """N10 — the same dict serves as an API response and as the snapshot."""
        import json

        _seed_kit(db_session, class_id=1, origin_id=0)
        resolved = crud.resolve_starter_kit(db_session, 1, 0)
        assert isinstance(resolved, dict)
        json.dumps(resolved)  # must not raise


# ===========================================================================
# (b) GET /characters/starter-kits/resolve
# ===========================================================================

class TestResolveEndpoint:
    def test_exact(self, db_session, client):
        _seed_kit(db_session, class_id=1, origin_id=0, currency=100)
        _seed_kit(db_session, class_id=1, origin_id=ORIGIN_SHINZO,
                  items=[{"item_id": 42, "quantity": 2}], currency=333)

        data = client.get(
            "/characters/starter-kits/resolve",
            params={"class_id": 1, "origin_id": ORIGIN_SHINZO},
        ).json()
        assert data["resolved_from"] == "exact"
        assert data["currency_amount"] == 333

    def test_class_default(self, db_session, client):
        _seed_kit(db_session, class_id=1, origin_id=0, currency=100)

        data = client.get(
            "/characters/starter-kits/resolve",
            params={"class_id": 1, "origin_id": ORIGIN_MIDDENGERD},
        ).json()
        assert data["resolved_from"] == "class_default"
        assert data["currency_amount"] == 100

    def test_none(self, db_session, client):
        data = client.get(
            "/characters/starter-kits/resolve",
            params={"class_id": 1, "origin_id": ORIGIN_SHINZO},
        ).json()
        assert data["resolved_from"] == "none"
        assert data["items"] == []
        assert data["skills"] == []
        assert data["currency_amount"] == 0

    def test_origin_may_be_omitted(self, db_session, client):
        _seed_kit(db_session, class_id=1, origin_id=0, currency=100)

        data = client.get("/characters/starter-kits/resolve", params={"class_id": 1}).json()
        assert data["resolved_from"] == "exact"
        assert data["origin_id"] == 0
        assert data["currency_amount"] == 100

    def test_origin_zero_reports_exact(self, db_session, client):
        """N10 through the HTTP layer."""
        _seed_kit(db_session, class_id=1, origin_id=0)

        data = client.get(
            "/characters/starter-kits/resolve", params={"class_id": 1, "origin_id": 0}
        ).json()
        assert data["resolved_from"] == "exact"

    def test_unknown_class_returns_404(self, db_session, client):
        response = client.get("/characters/starter-kits/resolve", params={"class_id": 9999})
        assert response.status_code == 404
        assert "9999" in response.json()["detail"]

    def test_missing_class_id_returns_422(self, db_session, client):
        assert client.get("/characters/starter-kits/resolve").status_code == 422

    def test_non_numeric_ids_return_422(self, db_session, client):
        response = client.get(
            "/characters/starter-kits/resolve",
            params={"class_id": "1; DROP TABLE starter_kits", "origin_id": "x"},
        )
        assert response.status_code == 422

    def test_endpoint_is_public(self, db_session, anon_client):
        """The wizard's «Путь» step calls it before anything privileged happens."""
        _seed_kit(db_session, class_id=1, origin_id=0)
        assert anon_client.get(
            "/characters/starter-kits/resolve", params={"class_id": 1}
        ).status_code == 200

    def test_resolve_is_not_swallowed_by_the_class_id_route(self, db_session, client):
        """'resolve' must not be parsed as a {class_id} path parameter."""
        response = client.get("/characters/starter-kits/resolve", params={"class_id": 1})
        assert response.status_code != 422


# ===========================================================================
# (c) PUT / DELETE the pair routes
# ===========================================================================

class TestUpsertPairKit:
    def test_creates_an_override(self, db_session, client):
        response = client.put(
            f"/characters/starter-kits/1/origins/{ORIGIN_SHINZO}", json=_kit_payload()
        )
        assert response.status_code == 200
        data = response.json()
        assert data["class_id"] == 1
        assert data["origin_id"] == ORIGIN_SHINZO
        assert data["currency_amount"] == 250

        kit = db_session.query(models.StarterKit).filter_by(
            class_id=1, origin_id=ORIGIN_SHINZO
        ).one()
        assert kit.items == [{"item_id": 5, "quantity": 1}]

    def test_second_put_updates_rather_than_duplicates(self, db_session, client):
        client.put(f"/characters/starter-kits/1/origins/{ORIGIN_SHINZO}", json=_kit_payload())
        response = client.put(
            f"/characters/starter-kits/1/origins/{ORIGIN_SHINZO}",
            json=_kit_payload(item_id=8, currency=999),
        )
        assert response.status_code == 200
        assert response.json()["currency_amount"] == 999

        rows = db_session.query(models.StarterKit).filter_by(
            class_id=1, origin_id=ORIGIN_SHINZO
        ).all()
        assert len(rows) == 1

    def test_override_does_not_touch_the_class_default(self, db_session, client):
        _seed_kit(db_session, class_id=1, origin_id=0, currency=100)

        client.put(
            f"/characters/starter-kits/1/origins/{ORIGIN_SHINZO}", json=_kit_payload(currency=250)
        )

        default_kit = db_session.query(models.StarterKit).filter_by(class_id=1, origin_id=0).one()
        assert default_kit.currency_amount == 100

    def test_origin_zero_returns_400(self, db_session, client):
        """One way to write a default, not two."""
        response = client.put("/characters/starter-kits/1/origins/0", json=_kit_payload())
        assert response.status_code == 400
        assert "по умолчанию" in response.json()["detail"]
        assert db_session.query(models.StarterKit).count() == 0

    def test_negative_origin_returns_400(self, db_session, client):
        response = client.put("/characters/starter-kits/1/origins/-5", json=_kit_payload())
        assert response.status_code == 400

    def test_unknown_class_returns_404(self, db_session, client):
        response = client.put(
            f"/characters/starter-kits/9999/origins/{ORIGIN_SHINZO}", json=_kit_payload()
        )
        assert response.status_code == 404

    def test_unauthenticated_returns_401(self, db_session, anon_client):
        response = anon_client.put(
            f"/characters/starter-kits/1/origins/{ORIGIN_SHINZO}", json=_kit_payload()
        )
        assert response.status_code == 401

    def test_user_without_characters_update_returns_403(self, db_session, make_client):
        response = make_client(_PLAIN_USER).put(
            f"/characters/starter-kits/1/origins/{ORIGIN_SHINZO}", json=_kit_payload()
        )
        assert response.status_code == 403
        assert db_session.query(models.StarterKit).count() == 0

    def test_editor_without_the_permission_returns_403(self, db_session, make_client):
        response = make_client(_EDITOR_USER).put(
            f"/characters/starter-kits/1/origins/{ORIGIN_SHINZO}", json=_kit_payload()
        )
        assert response.status_code == 403


class TestDeletePairKit:
    def test_delete_makes_the_pair_fall_back_again(self, db_session, client):
        _seed_kit(db_session, class_id=1, origin_id=0, currency=100)
        _seed_kit(db_session, class_id=1, origin_id=ORIGIN_SHINZO, currency=333)

        response = client.delete(f"/characters/starter-kits/1/origins/{ORIGIN_SHINZO}")
        assert response.status_code == 200
        assert "удалён" in response.json()["message"]

        resolved = client.get(
            "/characters/starter-kits/resolve",
            params={"class_id": 1, "origin_id": ORIGIN_SHINZO},
        ).json()
        assert resolved["resolved_from"] == "class_default"
        assert resolved["currency_amount"] == 100

    def test_delete_keeps_the_class_default_row(self, db_session, client):
        _seed_kit(db_session, class_id=1, origin_id=0)
        _seed_kit(db_session, class_id=1, origin_id=ORIGIN_SHINZO)

        client.delete(f"/characters/starter-kits/1/origins/{ORIGIN_SHINZO}")
        assert db_session.query(models.StarterKit).filter_by(class_id=1, origin_id=0).count() == 1

    def test_missing_override_returns_404(self, db_session, client):
        _seed_kit(db_session, class_id=1, origin_id=0)
        response = client.delete(f"/characters/starter-kits/1/origins/{ORIGIN_SHINZO}")
        assert response.status_code == 404

    def test_origin_zero_returns_400(self, db_session, client):
        _seed_kit(db_session, class_id=1, origin_id=0)
        response = client.delete("/characters/starter-kits/1/origins/0")
        assert response.status_code == 400
        # The default survived.
        assert db_session.query(models.StarterKit).filter_by(class_id=1, origin_id=0).count() == 1

    def test_unauthenticated_returns_401(self, db_session, anon_client):
        assert anon_client.delete(
            f"/characters/starter-kits/1/origins/{ORIGIN_SHINZO}"
        ).status_code == 401

    def test_user_without_characters_update_returns_403(self, db_session, make_client):
        _seed_kit(db_session, class_id=1, origin_id=ORIGIN_SHINZO)
        response = make_client(_PLAIN_USER).delete(
            f"/characters/starter-kits/1/origins/{ORIGIN_SHINZO}"
        )
        assert response.status_code == 403
        assert db_session.query(models.StarterKit).count() == 1


# ===========================================================================
# (d) GET /characters/starter-kits/coverage
# ===========================================================================

class TestCoverage:
    def test_reports_defaults_and_overrides(self, db_session, client):
        _seed_kit(db_session, class_id=1, origin_id=0)
        _seed_kit(db_session, class_id=1, origin_id=ORIGIN_SHINZO)
        _seed_kit(db_session, class_id=2, origin_id=ORIGIN_MIDDENGERD)

        data = client.get("/characters/starter-kits/coverage").json()
        by_id = {c["id_class"]: c for c in data["classes"]}
        assert by_id[1]["has_default"] is True
        assert by_id[2]["has_default"] is False
        assert by_id[3]["has_default"] is False
        assert by_id[1]["name"] == "Воин"

        assert data["overrides"] == [
            {"class_id": 1, "origin_id": ORIGIN_SHINZO},
            {"class_id": 2, "origin_id": ORIGIN_MIDDENGERD},
        ]

    def test_empty_state_lists_every_class_as_unfilled(self, db_session, client):
        data = client.get("/characters/starter-kits/coverage").json()
        assert data["overrides"] == []
        assert all(c["has_default"] is False for c in data["classes"])
        assert len(data["classes"]) == 3

    def test_overrides_are_sorted(self, db_session, client):
        _seed_kit(db_session, class_id=2, origin_id=9)
        _seed_kit(db_session, class_id=1, origin_id=9)
        _seed_kit(db_session, class_id=1, origin_id=2)

        overrides = client.get("/characters/starter-kits/coverage").json()["overrides"]
        assert overrides == [
            {"class_id": 1, "origin_id": 2},
            {"class_id": 1, "origin_id": 9},
            {"class_id": 2, "origin_id": 9},
        ]

    def test_unauthenticated_returns_401(self, db_session, anon_client):
        """The seeding state is not public (§3.3)."""
        assert anon_client.get("/characters/starter-kits/coverage").status_code == 401

    def test_user_without_characters_update_returns_403(self, db_session, make_client):
        assert make_client(_PLAIN_USER).get(
            "/characters/starter-kits/coverage"
        ).status_code == 403


# ===========================================================================
# (e) GET /characters/starter-kits — the additive origin_id key
# ===========================================================================

class TestListWithOrigins:
    def test_include_origins_returns_every_row(self, db_session, client):
        _seed_kit(db_session, class_id=1, origin_id=0)
        _seed_kit(db_session, class_id=1, origin_id=ORIGIN_SHINZO)
        _seed_kit(db_session, class_id=2, origin_id=ORIGIN_MIDDENGERD)

        data = client.get("/characters/starter-kits?include_origins=true").json()
        assert {(k["class_id"], k["origin_id"]) for k in data} == {
            (1, 0), (1, ORIGIN_SHINZO), (2, ORIGIN_MIDDENGERD),
        }

    def test_every_item_carries_origin_id(self, db_session, client):
        _seed_kit(db_session, class_id=1, origin_id=0)
        data = client.get("/characters/starter-kits").json()
        assert all("origin_id" in kit for kit in data)
