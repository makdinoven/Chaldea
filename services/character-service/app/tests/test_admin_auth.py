"""
Tests for admin endpoint authentication in character-service.

Verifies that admin endpoints (approve_character_request, delete_character)
properly enforce JWT + admin role checks.
"""

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helper: build a mock requests.get response
# ---------------------------------------------------------------------------
def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


# ── POST /characters/requests/{request_id}/approve ─────────────────────────


class TestApproveCharacterRequestAuth:
    """Auth tests for POST /characters/requests/{request_id}/approve."""

    def test_missing_token_returns_401(self, client: TestClient):
        """No Authorization header → 401."""
        response = client.post("/characters/requests/1/approve")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client: TestClient):
        """Valid token but role != admin → 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 2, "username": "user", "role": "user", "permissions": []}
        )
        response = client.post(
            "/characters/requests/1/approve",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get, client: TestClient):
        """User-service returns 401 for invalid token → 401."""
        mock_get.return_value = _mock_response(401)
        response = client.post(
            "/characters/requests/1/approve",
            headers={"Authorization": "Bearer bad-token"},
        )
        assert response.status_code == 401


# ── DELETE /characters/{character_id} ──────────────────────────────────────


class TestDeleteCharacterAuth:
    """Auth tests for DELETE /characters/{character_id}."""

    def test_missing_token_returns_401(self, client: TestClient):
        response = client.delete("/characters/1")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client: TestClient):
        mock_get.return_value = _mock_response(
            200, {"id": 2, "username": "user", "role": "user", "permissions": []}
        )
        response = client.delete(
            "/characters/1",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_admin_can_access(self, mock_get, client: TestClient, mock_db_session):
        """Valid admin token → endpoint is reached (404 because request doesn't exist)."""
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "admin", "role": "admin", "permissions": [
                "characters:create", "characters:read", "characters:update",
                "characters:delete", "characters:approve",
            ]}
        )
        # With a mock DB session, crud.delete_character returns None → 404
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        response = client.delete(
            "/characters/1",
            headers={"Authorization": "Bearer admin-token"},
        )
        # 404 means auth passed, but character not found — that's correct
        assert response.status_code == 404
