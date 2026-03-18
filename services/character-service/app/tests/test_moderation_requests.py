"""
Tests for GET /characters/moderation-requests endpoint.

Covers:
1. Empty results — returns 200 with empty dict {}
2. Populated results — returns 200 with data when requests exist
3. DB error — returns 500 when SQLAlchemyError is raised
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch
from sqlalchemy.exc import SQLAlchemyError


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
