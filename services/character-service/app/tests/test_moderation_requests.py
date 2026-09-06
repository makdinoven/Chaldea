"""
Tests for GET /characters/moderation-requests endpoint.

Covers:
1. Empty results — returns 200 with empty dict {}
2. Populated results — returns 200 with data when requests exist
3. DB error — returns 500 when SQLAlchemyError is raised
4. FEAT-154 (N25) — the shape of what ``crud.get_moderation_requests`` really
   builds, exercised against a real session rather than a mock, because the
   endpoint tests above stub the crud function whole and therefore cannot see
   a missing column.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

import crud
import database
from database import Base
import models


# Keys the moderation row carried before FEAT-154. None may disappear.
LEGACY_MODERATION_KEYS = {
    "request_id", "user_id", "name", "biography", "appearance",
    "personality", "background", "age", "weight", "height", "sex",
    "id_class", "class_name", "id_race", "race_name", "id_subrace",
    "subrace_name", "status", "created_at", "avatar",
    "request_type", "character_id",
}

# Keys FEAT-154 adds so the moderator passport can print origin, tenure, the
# first assignment and the rejection reason (N25).
NEW_MODERATION_KEYS = {
    "origin_id", "start_location_id",
    "skitaltsy_since_year", "skitaltsy_since_segment", "rejection_reason",
}


class TestModerationRequestsEmpty:
    """Test that endpoint returns 200 with empty dict when no requests exist."""

    @patch("main.crud")
    def test_returns_200_with_empty_dict(self, mock_crud, admin_mock_client):
        mock_crud.get_moderation_requests.return_value = {}

        response = admin_mock_client.get("/characters/moderation-requests")

        assert response.status_code == 200
        assert response.json() == {}
        mock_crud.get_moderation_requests.assert_called_once()

    @patch("main.crud")
    def test_returns_200_with_none_treated_as_empty(self, mock_crud, admin_mock_client):
        """When crud returns a falsy value, endpoint should return empty dict."""
        mock_crud.get_moderation_requests.return_value = None

        response = admin_mock_client.get("/characters/moderation-requests")

        assert response.status_code == 200
        assert response.json() == {}


class TestModerationRequestsWithData:
    """Test that endpoint returns 200 with populated dict when requests exist."""

    @patch("main.crud")
    def test_returns_200_with_single_pending_request(self, mock_crud, admin_mock_client):
        sample_data = {
            1: {
                "request_id": 1,
                "user_id": 42,
                "name": "Артас",
                "biography": "Принц Лордерона",
                "appearance": "Высокий блондин",
                "personality": "Решительный",
                "background": "Рыцарь",
                "age": 25,
                "weight": "85",
                "height": "190",
                "sex": "male",
                "id_class": 1,
                "class_name": "Воин",
                "id_race": 1,
                "race_name": "Человек",
                "id_subrace": 1,
                "subrace_name": "Северянин",
                "status": "pending",
                "created_at": "2026-03-12T10:00:00",
                "avatar": "https://example.com/avatar.webp",
            }
        }
        mock_crud.get_moderation_requests.return_value = sample_data

        response = admin_mock_client.get("/characters/moderation-requests")

        assert response.status_code == 200
        data = response.json()
        # FastAPI serializes int keys as strings in JSON
        assert "1" in data
        entry = data["1"]
        assert entry["request_id"] == 1
        assert entry["status"] == "pending"
        assert entry["class_name"] == "Воин"
        assert entry["race_name"] == "Человек"
        assert entry["subrace_name"] == "Северянин"
        assert entry["name"] == "Артас"
        assert entry["user_id"] == 42

    @patch("main.crud")
    def test_returns_200_with_multiple_requests(self, mock_crud, admin_mock_client):
        sample_data = {
            1: {
                "request_id": 1,
                "user_id": 10,
                "name": "Герой",
                "biography": "Био",
                "appearance": "Вид",
                "personality": "Характер",
                "background": "Фон",
                "age": 20,
                "weight": "70",
                "height": "175",
                "sex": "male",
                "id_class": 1,
                "class_name": "Воин",
                "id_race": 1,
                "race_name": "Человек",
                "id_subrace": 1,
                "subrace_name": "Северянин",
                "status": "pending",
                "created_at": "2026-03-12T10:00:00",
                "avatar": "",
            },
            2: {
                "request_id": 2,
                "user_id": 20,
                "name": "Маг",
                "biography": "Био маг",
                "appearance": "Худой",
                "personality": "Мудрый",
                "background": "Академия",
                "age": 50,
                "weight": "60",
                "height": "170",
                "sex": "male",
                "id_class": 3,
                "class_name": "Маг",
                "id_race": 2,
                "race_name": "Эльф",
                "id_subrace": 3,
                "subrace_name": "Высший эльф",
                "status": "approved",
                "created_at": "2026-03-11T08:00:00",
                "avatar": "https://example.com/mage.webp",
            },
        }
        mock_crud.get_moderation_requests.return_value = sample_data

        response = admin_mock_client.get("/characters/moderation-requests")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert "1" in data
        assert "2" in data

    @patch("main.crud")
    def test_response_contains_all_expected_fields(self, mock_crud, admin_mock_client):
        """Verify all expected fields are present in the response."""
        expected_fields = {
            "request_id", "user_id", "name", "biography", "appearance",
            "personality", "background", "age", "weight", "height", "sex",
            "id_class", "class_name", "id_race", "race_name", "id_subrace",
            "subrace_name", "status", "created_at", "avatar",
            # FEAT-154 (N25)
            "origin_id", "start_location_id", "skitaltsy_since_year",
            "skitaltsy_since_segment", "rejection_reason",
        }
        sample_data = {
            1: {
                "request_id": 1,
                "user_id": 1,
                "name": "Тест",
                "biography": "Био",
                "appearance": "Вид",
                "personality": "Характер",
                "background": "Фон",
                "age": 20,
                "weight": "70",
                "height": "175",
                "sex": "female",
                "id_class": 2,
                "class_name": "Разбойник",
                "id_race": 1,
                "race_name": "Человек",
                "id_subrace": 2,
                "subrace_name": "Южанин",
                "status": "pending",
                "created_at": "2026-03-12T12:00:00",
                "avatar": "",
                "origin_id": 7,
                "start_location_id": 1183,
                "skitaltsy_since_year": 1783,
                "skitaltsy_since_segment": 2,
                "rejection_reason": None,
            }
        }
        mock_crud.get_moderation_requests.return_value = sample_data

        response = admin_mock_client.get("/characters/moderation-requests")

        assert response.status_code == 200
        entry = response.json()["1"]
        assert set(entry.keys()) == expected_fields


class TestModerationRequestsDBError:
    """Test that endpoint returns 500 when a DB error occurs."""

    @patch("main.crud")
    def test_returns_500_on_sqlalchemy_error(self, mock_crud, admin_mock_client):
        mock_crud.get_moderation_requests.side_effect = SQLAlchemyError(
            "Connection refused"
        )

        response = admin_mock_client.get("/characters/moderation-requests")

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "модерацию" in data["detail"].lower() or "модерации" in data["detail"].lower()

    @patch("main.crud")
    def test_500_response_does_not_leak_db_details(self, mock_crud, admin_mock_client):
        """Ensure the error response does not expose internal DB error details."""
        mock_crud.get_moderation_requests.side_effect = SQLAlchemyError(
            "FATAL: password authentication failed for user 'myuser'"
        )

        response = admin_mock_client.get("/characters/moderation-requests")

        assert response.status_code == 500
        body = response.text
        assert "password" not in body.lower()
        assert "myuser" not in body.lower()


# ===========================================================================
# FEAT-154 (N25) — the real crud function, no mock
# ===========================================================================

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


def _seed_request(db, **overrides):
    fields = dict(
        user_id=42,
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
        status="pending",
        request_type="creation",
        origin_id=7,
        start_location_id=1183,
        skitaltsy_since_year=1783,
        skitaltsy_since_segment=2,
    )
    fields.update(overrides)
    req = models.CharacterRequest(**fields)
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


class TestModerationRowShape:
    """The tests above mock crud whole, so only these see the real columns."""

    def test_no_legacy_key_disappeared(self, db_session):
        req = _seed_request(db_session)

        row = crud.get_moderation_requests(db_session)[req.id]

        missing = LEGACY_MODERATION_KEYS - set(row.keys())
        assert missing == set(), f"пропали существующие ключи: {missing}"

    def test_new_passport_keys_are_present(self, db_session):
        req = _seed_request(db_session)

        row = crud.get_moderation_requests(db_session)[req.id]

        missing = NEW_MODERATION_KEYS - set(row.keys())
        assert missing == set(), f"не добавлены ключи FEAT-154: {missing}"

    def test_new_keys_carry_the_real_values(self, db_session):
        req = _seed_request(db_session)

        row = crud.get_moderation_requests(db_session)[req.id]

        assert row["origin_id"] == 7
        assert row["start_location_id"] == 1183
        assert row["skitaltsy_since_year"] == 1783
        assert row["skitaltsy_since_segment"] == 2
        assert row["rejection_reason"] is None

    def test_rejection_reason_is_carried_to_the_moderator(self, db_session):
        req = _seed_request(
            db_session, status="rejected",
            rejection_reason="Возраст не соответствует подрасе",
        )

        row = crud.get_moderation_requests(db_session)[req.id]

        assert row["status"] == "rejected"
        assert row["rejection_reason"] == "Возраст не соответствует подрасе"

    def test_pre_feature_request_reports_nulls_not_errors(self, db_session):
        """A request created before FEAT-154 has NULLs in every new column."""
        req = _seed_request(
            db_session, origin_id=None, start_location_id=None,
            skitaltsy_since_year=None, skitaltsy_since_segment=None,
        )

        row = crud.get_moderation_requests(db_session)[req.id]

        assert row["origin_id"] is None
        assert row["start_location_id"] is None
        assert row["skitaltsy_since_year"] is None
        assert row["skitaltsy_since_segment"] is None
        # The rest of the row still renders.
        assert row["name"] == "Аэлис"
        assert row["race_name"] == "Эльф"
