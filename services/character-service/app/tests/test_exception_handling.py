"""
Tests for HTTPException propagation in character-service endpoints.

Verifies that after the FEAT-004 fix (except Exception -> except SQLAlchemyError),
HTTPException (e.g. 404) propagates correctly and is NOT converted to 500.

Covers 6 high-priority endpoints:
1. approve_character_request  — POST /characters/requests/{id}/approve
2. reject_character_request   — POST /characters/requests/{id}/reject
3. delete_character           — DELETE /characters/{id}
4. assign_title               — POST /characters/{id}/titles/{title_id}
5. set_current_title          — POST /characters/{id}/current-title/{title_id}
6. get_titles_for_character   — GET /characters/{id}/titles
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
from sqlalchemy.exc import SQLAlchemyError


# ---------------------------------------------------------------------------
# 1. approve_character_request — POST /characters/requests/{id}/approve
# ---------------------------------------------------------------------------

class TestApproveCharacterRequest:
    """Test that approve endpoint returns 404 when request not found."""

    @patch("main.crud")
    def test_returns_404_when_request_not_found(self, mock_crud, client, mock_db_session):
        """When the character request does not exist, expect 404 (not 500)."""
        # The endpoint queries DB directly: db.query(models.CharacterRequest).filter(...).first()
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        response = client.post("/characters/requests/99999/approve")

        assert response.status_code == 404
        assert "не найдена" in response.json()["detail"].lower() or "найдена" in response.json()["detail"]

    @patch("main.crud")
    def test_returns_500_on_sqlalchemy_error(self, mock_crud, client, mock_db_session):
        """When a DB error occurs, expect 500."""
        mock_db_session.query.side_effect = SQLAlchemyError("DB connection lost")

        response = client.post("/characters/requests/1/approve")

        assert response.status_code == 500
        assert "detail" in response.json()


# ---------------------------------------------------------------------------
# 2. reject_character_request — POST /characters/requests/{id}/reject
# ---------------------------------------------------------------------------

class TestRejectCharacterRequest:
    """Test that reject endpoint returns 404 when request not found."""

    @patch("main.crud")
    def test_returns_404_when_request_not_found(self, mock_crud, client):
        """When crud.update_character_request_status returns None, expect 404."""
        mock_crud.update_character_request_status.return_value = None

        response = client.post("/characters/requests/99999/reject")

        assert response.status_code == 404
        assert "найдена" in response.json()["detail"]

    @patch("main.crud")
    def test_returns_200_when_request_exists(self, mock_crud, client):
        """When crud returns a valid object, expect success."""
        mock_crud.update_character_request_status.return_value = MagicMock()

        response = client.post("/characters/requests/1/reject")

        assert response.status_code == 200
        assert "отклонена" in response.json()["message"]

    @patch("main.crud")
    def test_returns_500_on_sqlalchemy_error(self, mock_crud, client):
        """When a DB error occurs, expect 500."""
        mock_crud.update_character_request_status.side_effect = SQLAlchemyError(
            "Deadlock detected"
        )

        response = client.post("/characters/requests/1/reject")

        assert response.status_code == 500
        assert "detail" in response.json()


# ---------------------------------------------------------------------------
# 3. delete_character — DELETE /characters/{id}
# ---------------------------------------------------------------------------

class TestDeleteCharacter:
    """Test that delete endpoint returns 404 when character not found."""

    @patch("main.crud")
    def test_returns_404_when_character_not_found(self, mock_crud, client):
        """When crud.delete_character returns None/False, expect 404."""
        mock_crud.delete_character.return_value = None

        response = client.delete("/characters/99999")

        assert response.status_code == 404
        assert "найден" in response.json()["detail"]

    @patch("main.crud")
    def test_returns_200_when_character_deleted(self, mock_crud, client):
        """When crud.delete_character returns True, expect success."""
        mock_crud.delete_character.return_value = True

        response = client.delete("/characters/1")

        assert response.status_code == 200
        assert "удален" in response.json()["message"]

    @patch("main.crud")
    def test_returns_500_on_sqlalchemy_error(self, mock_crud, client):
        """When a DB error occurs, expect 500."""
        mock_crud.delete_character.side_effect = SQLAlchemyError("Table locked")

        response = client.delete("/characters/1")

        assert response.status_code == 500
        assert "detail" in response.json()


# ---------------------------------------------------------------------------
# 4. assign_title — POST /characters/{id}/titles/{title_id}
# ---------------------------------------------------------------------------

class TestAssignTitle:
    """Test that assign_title endpoint returns 404 when character/title not found."""

    @patch("main.crud")
    def test_returns_404_when_not_found(self, mock_crud, client):
        """When crud.assign_title_to_character returns None, expect 404."""
        mock_crud.assign_title_to_character.return_value = None

        response = client.post("/characters/1/titles/999")

        assert response.status_code == 404
        assert "найден" in response.json()["detail"]

    @patch("main.crud")
    def test_returns_200_when_assigned(self, mock_crud, client):
        """When crud returns a valid assignment, expect success."""
        mock_crud.assign_title_to_character.return_value = MagicMock()

        response = client.post("/characters/1/titles/1")

        assert response.status_code == 200
        assert "присвоен" in response.json()["message"]

    @patch("main.crud")
    def test_returns_500_on_sqlalchemy_error(self, mock_crud, client):
        """When a DB error occurs, expect 500."""
        mock_crud.assign_title_to_character.side_effect = SQLAlchemyError(
            "Foreign key constraint"
        )

        response = client.post("/characters/1/titles/1")

        assert response.status_code == 500
        assert "detail" in response.json()


# ---------------------------------------------------------------------------
# 5. set_current_title — POST /characters/{id}/current-title/{title_id}
# ---------------------------------------------------------------------------

class TestSetCurrentTitle:
    """Test that set_current_title endpoint returns 404 when character not found."""

    @patch("main.crud")
    def test_returns_404_when_character_not_found(self, mock_crud, client):
        """When crud.set_current_title returns None, expect 404."""
        mock_crud.set_current_title.return_value = None

        response = client.post("/characters/1/current-title/999")

        assert response.status_code == 404
        assert "найден" in response.json()["detail"]

    @patch("main.crud")
    def test_returns_200_when_title_set(self, mock_crud, client):
        """When crud returns a valid character, expect success."""
        mock_crud.set_current_title.return_value = MagicMock()

        response = client.post("/characters/1/current-title/1")

        assert response.status_code == 200
        assert "установлен" in response.json()["message"]

    @patch("main.crud")
    def test_returns_500_on_sqlalchemy_error(self, mock_crud, client):
        """When a DB error occurs, expect 500."""
        mock_crud.set_current_title.side_effect = SQLAlchemyError("Connection reset")

        response = client.post("/characters/1/current-title/1")

        assert response.status_code == 500
        assert "detail" in response.json()


# ---------------------------------------------------------------------------
# 6. get_titles_for_character — GET /characters/{id}/titles
# ---------------------------------------------------------------------------

class TestGetTitlesForCharacter:
    """Test that get_titles_for_character endpoint returns 404 when no titles."""

    @patch("main.crud")
    def test_returns_404_when_no_titles(self, mock_crud, client):
        """When crud.get_titles_for_character returns empty list, expect 404."""
        mock_crud.get_titles_for_character.return_value = []

        response = client.get("/characters/1/titles")

        assert response.status_code == 404
        assert "титул" in response.json()["detail"].lower()

    @patch("main.crud")
    def test_returns_404_when_none(self, mock_crud, client):
        """When crud.get_titles_for_character returns None, expect 404."""
        mock_crud.get_titles_for_character.return_value = None

        response = client.get("/characters/99999/titles")

        assert response.status_code == 404

    @patch("main.crud")
    def test_returns_200_with_titles(self, mock_crud, client):
        """When crud returns titles, expect 200 with title list."""
        mock_title = MagicMock()
        mock_title.id_title = 1
        mock_title.name = "Герой"
        mock_title.description = "Отважный герой"
        mock_crud.get_titles_for_character.return_value = [mock_title]

        response = client.get("/characters/1/titles")

        assert response.status_code == 200

    @patch("main.crud")
    def test_returns_500_on_sqlalchemy_error(self, mock_crud, client):
        """When a DB error occurs, expect 500."""
        mock_crud.get_titles_for_character.side_effect = SQLAlchemyError(
            "Query timeout"
        )

        response = client.get("/characters/1/titles")

        assert response.status_code == 500
        assert "detail" in response.json()

    @patch("main.crud")
    def test_500_does_not_leak_db_details(self, mock_crud, client):
        """Ensure the error response does not expose internal DB error details."""
        mock_crud.get_titles_for_character.side_effect = SQLAlchemyError(
            "FATAL: password authentication failed for user 'dbadmin'"
        )

        response = client.get("/characters/1/titles")

        assert response.status_code == 500
        body = response.text
        assert "password" not in body.lower()
        assert "dbadmin" not in body.lower()
