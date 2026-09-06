"""
FEAT-154 (task #25) — tests for the new player-facing request endpoints.

Covers:
(a) GET /characters/classes — the public class directory that replaces INITIAL_CLASSES
(b) GET /characters/requests/my — owner scoping (user A never sees user B's requests)
(c) PUT /characters/requests/{id} — edit and resubmit a rejected request
    (403 for a non-owner, 404, 409 when the status is not 'rejected', 400 domain
    validation, success path returning to 'pending' with the reason cleared)
(d) security: unauthenticated access, ownership checked BEFORE domain validation,
    SQL injection in free-text fields
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

import database
from database import Base
import models
from auth_http import get_current_user_via_http, OAUTH2_SCHEME, UserRead
from main import app, get_db


USER_A = UserRead(id=42, username="playerA", role="user", permissions=[])
USER_B = UserRead(id=77, username="playerB", role="user", permissions=[])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def stub_locations_client():
    """Keep the domain validator off the network (see test_approval_flow.py).

    ``validate_character_request_payload`` probes locations-service for the
    starting point and the current in-game year. Unpatched, each call burns the
    5 s client timeout before falling through gracefully.
    """
    with patch("crud.locations_client") as mock_client:
        mock_client.probe_starting_point = AsyncMock(return_value=True)
        mock_client.get_current_game_year = AsyncMock(return_value=1787)
        yield mock_client


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
    """Build a TestClient authenticated as an arbitrary user."""

    def _factory(user=None):
        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        if user is not None:
            app.dependency_overrides[get_current_user_via_http] = lambda: user
            app.dependency_overrides[OAUTH2_SCHEME] = lambda: "fake-token"
        else:
            app.dependency_overrides.pop(get_current_user_via_http, None)
            app.dependency_overrides.pop(OAUTH2_SCHEME, None)
        return TestClient(app)

    yield _factory
    app.dependency_overrides.clear()


@pytest.fixture
def client_a(make_client):
    return make_client(USER_A)


@pytest.fixture
def anon_client(make_client):
    return make_client(None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_request(db, user_id=42, status="pending", **overrides):
    fields = dict(
        user_id=user_id,
        name="Аэлис",
        id_race=2,
        id_subrace=4,
        id_class=1,
        biography="Био",
        personality="Характер",
        appearance="Высокая эльфийка",
        background="Предыстория",
        sex="female",
        age=120,
        weight="52",
        height="168",
        avatar="https://example.com/a.webp",
        status=status,
        request_type="creation",
    )
    fields.update(overrides)
    req = models.CharacterRequest(**fields)
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def _valid_payload(**overrides):
    payload = {
        "name": "Аэлис",
        "id_race": 2,
        "id_subrace": 4,
        "id_class": 1,
        "biography": "Новая био",
        "personality": "Новый характер",
        "appearance": "Новая внешность",
        "background": "Новая предыстория",
        "sex": "female",
        "age": 120,
        "weight": "52",
        "height": "168",
        "avatar": "https://example.com/new.webp",
        "origin_id": 7,
        "start_location_id": None,
        "skitaltsy_since_year": None,
        "skitaltsy_since_segment": None,
    }
    payload.update(overrides)
    return payload


# ===========================================================================
# (a) GET /characters/classes
# ===========================================================================

class TestClassesEndpoint:
    def test_classes_are_public(self, db_session, anon_client):
        """No token required — the wizard reads it before login state matters."""
        response = anon_client.get("/characters/classes")
        assert response.status_code == 200

    def test_classes_returns_seeded_classes_ordered(self, db_session, anon_client):
        data = anon_client.get("/characters/classes").json()
        assert [c["id_class"] for c in data] == [1, 2, 3]
        assert {c["name"] for c in data} == {"Воин", "Плут", "Маг"}

    def test_classes_expose_description_field(self, db_session, anon_client):
        cls = db_session.query(models.Class).filter_by(id_class=1).one()
        cls.description = "Мастер ближнего боя."
        db_session.commit()

        data = anon_client.get("/characters/classes").json()
        warrior = next(c for c in data if c["id_class"] == 1)
        assert warrior["description"] == "Мастер ближнего боя."
        # The mock payload of INITIAL_CLASSES is gone: no fake item/skill keys.
        assert set(warrior.keys()) == {"id_class", "name", "description"}


# ===========================================================================
# (b) GET /characters/requests/my — owner scoping
# ===========================================================================

class TestMyRequests:
    def test_returns_only_own_requests(self, db_session, make_client):
        """Owner isolation: user A must never see user B's requests."""
        mine = _seed_request(db_session, user_id=USER_A.id, name="Моя")
        theirs = _seed_request(db_session, user_id=USER_B.id, name="Чужая")

        data = make_client(USER_A).get("/characters/requests/my").json()
        assert [r["id"] for r in data] == [mine.id]
        assert all(r["name"] != "Чужая" for r in data)

        other = make_client(USER_B).get("/characters/requests/my").json()
        assert [r["id"] for r in other] == [theirs.id]

    def test_empty_list_when_user_has_no_requests(self, db_session, make_client):
        _seed_request(db_session, user_id=USER_B.id)
        assert make_client(USER_A).get("/characters/requests/my").json() == []

    def test_newest_first(self, db_session, client_a):
        first = _seed_request(db_session, user_id=USER_A.id, name="Первая")
        second = _seed_request(db_session, user_id=USER_A.id, name="Вторая")

        data = client_a.get("/characters/requests/my").json()
        assert [r["id"] for r in data] == [second.id, first.id]

    def test_reference_names_are_expanded(self, db_session, client_a):
        """The client must not need N+1 lookups for race/subrace/class names."""
        _seed_request(db_session, user_id=USER_A.id)
        item = client_a.get("/characters/requests/my").json()[0]

        assert item["race_name"] == "Эльф"
        assert item["subrace_name"] == "Лесной"
        assert item["class_name"] == "Воин"

    def test_rejected_request_carries_reason_and_new_fields(self, db_session, client_a):
        _seed_request(
            db_session,
            user_id=USER_A.id,
            status="rejected",
            rejection_reason="Возраст не соответствует подрасе",
            origin_id=7,
            start_location_id=1183,
            skitaltsy_since_year=1783,
            skitaltsy_since_segment=2,
        )
        item = client_a.get("/characters/requests/my").json()[0]

        assert item["status"] == "rejected"
        assert item["rejection_reason"] == "Возраст не соответствует подрасе"
        assert item["origin_id"] == 7
        assert item["start_location_id"] == 1183
        assert item["skitaltsy_since_year"] == 1783
        assert item["skitaltsy_since_segment"] == 2
        assert item["request_type"] == "creation"
        assert item["created_at"] is not None

    def test_route_is_not_parsed_as_an_int_path_param(self, db_session, client_a):
        """/requests/my must be declared before /requests/{request_id} (§3.1)."""
        response = client_a.get("/characters/requests/my")
        assert response.status_code == 200
        assert response.status_code != 422

    def test_unauthenticated_returns_401(self, db_session, anon_client):
        assert anon_client.get("/characters/requests/my").status_code == 401


# ===========================================================================
# (c) PUT /characters/requests/{id}
# ===========================================================================

class TestUpdateRequest:
    def test_rejected_request_returns_to_pending_and_clears_reason(self, db_session, client_a):
        req = _seed_request(
            db_session, user_id=USER_A.id, status="rejected",
            rejection_reason="Слишком юн",
        )

        response = client_a.put(
            f"/characters/requests/{req.id}",
            json=_valid_payload(name="Аэлис II"),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pending"
        assert body["rejection_reason"] is None
        assert body["name"] == "Аэлис II"

        db_session.refresh(req)
        assert req.status == "pending"
        assert req.rejection_reason is None
        assert req.name == "Аэлис II"

    def test_editable_fields_are_written(self, db_session, client_a):
        req = _seed_request(db_session, user_id=USER_A.id, status="rejected")

        payload = _valid_payload(
            id_race=1, id_subrace=2, id_class=3,
            appearance="Совсем другая внешность",
            origin_id=3, skitaltsy_since_year=1780, skitaltsy_since_segment=5,
        )
        body = client_a.put(f"/characters/requests/{req.id}", json=payload).json()

        assert (body["id_race"], body["id_subrace"], body["id_class"]) == (1, 2, 3)
        assert body["appearance"] == "Совсем другая внешность"
        assert body["origin_id"] == 3
        assert body["skitaltsy_since_year"] == 1780
        assert body["skitaltsy_since_segment"] == 5

    def test_owner_cannot_be_reassigned_via_payload(self, db_session, client_a):
        """user_id in the body is ignored — the owner comes from the token."""
        req = _seed_request(db_session, user_id=USER_A.id, status="rejected")

        response = client_a.put(
            f"/characters/requests/{req.id}",
            json=_valid_payload(user_id=USER_B.id),
        )
        assert response.status_code == 200

        db_session.refresh(req)
        assert req.user_id == USER_A.id

    def test_non_owner_gets_403(self, db_session, make_client):
        req = _seed_request(db_session, user_id=USER_B.id, status="rejected")

        response = make_client(USER_A).put(
            f"/characters/requests/{req.id}", json=_valid_payload()
        )
        assert response.status_code == 403

        db_session.refresh(req)
        assert req.status == "rejected"

    def test_ownership_is_checked_before_domain_validation(self, db_session, make_client):
        """A non-owner sending an invalid body still gets 403, never 400."""
        req = _seed_request(db_session, user_id=USER_B.id, status="rejected")

        response = make_client(USER_A).put(
            f"/characters/requests/{req.id}",
            json=_valid_payload(id_class=9999, name=""),
        )
        assert response.status_code == 403

    def test_not_found_returns_404(self, db_session, client_a):
        assert client_a.put("/characters/requests/99999", json=_valid_payload()).status_code == 404

    def test_pending_request_returns_409(self, db_session, client_a):
        req = _seed_request(db_session, user_id=USER_A.id, status="pending")

        response = client_a.put(f"/characters/requests/{req.id}", json=_valid_payload())
        assert response.status_code == 409
        assert "отклонённую" in response.json()["detail"]

    def test_approved_request_returns_409(self, db_session, client_a):
        req = _seed_request(db_session, user_id=USER_A.id, status="approved")

        assert client_a.put(
            f"/characters/requests/{req.id}", json=_valid_payload()
        ).status_code == 409

    def test_subrace_not_belonging_to_race_returns_400(self, db_session, client_a):
        req = _seed_request(db_session, user_id=USER_A.id, status="rejected")

        response = client_a.put(
            f"/characters/requests/{req.id}",
            json=_valid_payload(id_race=1, id_subrace=4),  # subrace 4 belongs to race 2
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Подраса не принадлежит выбранной расе."

        db_session.refresh(req)
        assert req.status == "rejected"

    def test_blank_appearance_returns_400(self, db_session, client_a):
        req = _seed_request(db_session, user_id=USER_A.id, status="rejected")

        response = client_a.put(
            f"/characters/requests/{req.id}", json=_valid_payload(appearance="   ")
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Опишите внешность персонажа."

    def test_own_pending_request_does_not_block_its_own_resubmit(self, db_session, client_a):
        """The edited request must not count against the player's own limit."""
        for _ in range(4):
            _seed_request(db_session, user_id=USER_A.id, status="pending")
        req = _seed_request(db_session, user_id=USER_A.id, status="rejected")

        response = client_a.put(f"/characters/requests/{req.id}", json=_valid_payload())
        assert response.status_code == 200

    def test_unauthenticated_returns_401(self, db_session, anon_client):
        req = _seed_request(db_session, user_id=USER_A.id, status="rejected")
        assert anon_client.put(
            f"/characters/requests/{req.id}", json=_valid_payload()
        ).status_code == 401

    def test_sql_injection_in_text_fields_is_stored_literally(self, db_session, client_a):
        req = _seed_request(db_session, user_id=USER_A.id, status="rejected")
        # Kept within the 20-char name limit so the injection reaches the DB layer
        # instead of being turned away by Pydantic.
        payload_name = "'; DROP TABLE t; --"

        response = client_a.put(
            f"/characters/requests/{req.id}",
            json=_valid_payload(
                name=payload_name,
                biography='" OR 1=1 --',
                appearance="'); DELETE FROM character_requests; --",
            ),
        )
        assert response.status_code == 200
        assert response.json()["name"] == payload_name

        # The tables are still there and the value was stored, not executed.
        assert db_session.query(models.CharacterRequest).count() == 1
        db_session.refresh(req)
        assert req.name == payload_name

    def test_name_over_20_chars_is_rejected(self, db_session, client_a):
        req = _seed_request(db_session, user_id=USER_A.id, status="rejected")

        response = client_a.put(
            f"/characters/requests/{req.id}", json=_valid_payload(name="А" * 21)
        )
        # N20 / task #36: the domain validator now owns the length rule, so this
        # is a 400 with a Russian message — not Pydantic's English 422.
        assert response.status_code == 400
        assert response.json()["detail"] == "Имя обязательно и не длиннее 20 символов."

    def test_name_of_exactly_20_chars_is_accepted(self, db_session, client_a):
        req = _seed_request(db_session, user_id=USER_A.id, status="rejected")
        name = "А" * 20

        response = client_a.put(
            f"/characters/requests/{req.id}", json=_valid_payload(name=name)
        )
        assert response.status_code == 200, response.text
        db_session.refresh(req)
        assert req.name == name

    def test_padded_20_char_name_is_stored_stripped(self, db_session, client_a):
        """N21 — the validator writes the cleaned name back, so String(20) is safe."""
        req = _seed_request(db_session, user_id=USER_A.id, status="rejected")
        name = "А" * 20

        response = client_a.put(
            f"/characters/requests/{req.id}", json=_valid_payload(name="   " + name)
        )
        assert response.status_code == 200, response.text
        db_session.refresh(req)
        assert req.name == name
        assert len(req.name) == 20
