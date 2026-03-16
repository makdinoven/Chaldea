"""
Tests for admin endpoint authentication in photo-service.

Verifies that admin-protected image upload endpoints
(change_country_map, change_location_image) enforce JWT + admin role checks.
"""

import io
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helper: build a mock requests.get response
# ---------------------------------------------------------------------------
def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _fake_file():
    """Return a minimal file-like tuple for multipart upload."""
    return ("file", ("test.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png"))


# ── POST /photo/change_country_map ────────────────────────────────────────


class TestChangeCountryMapAuth:
    """Auth tests for POST /photo/change_country_map."""

    def test_missing_token_returns_401(self, client):
        """No Authorization header → 401."""
        response = client.post(
            "/photo/change_country_map",
            data={"country_id": "1"},
            files=[_fake_file()],
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        """Valid token but role != admin → 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 2, "username": "user", "role": "user"}
        )
        response = client.post(
            "/photo/change_country_map",
            data={"country_id": "1"},
            files=[_fake_file()],
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get, client):
        """User-service returns 401 → 401."""
        mock_get.return_value = _mock_response(401)
        response = client.post(
            "/photo/change_country_map",
            data={"country_id": "1"},
            files=[_fake_file()],
            headers={"Authorization": "Bearer bad-token"},
        )
        assert response.status_code == 401


# ── POST /photo/change_location_image ─────────────────────────────────────


class TestChangeLocationImageAuth:
    """Auth tests for POST /photo/change_location_image."""

    def test_missing_token_returns_401(self, client):
        response = client.post(
            "/photo/change_location_image",
            data={"location_id": "1"},
            files=[_fake_file()],
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        mock_get.return_value = _mock_response(
            200, {"id": 2, "username": "user", "role": "user"}
        )
        response = client.post(
            "/photo/change_location_image",
            data={"location_id": "1"},
            files=[_fake_file()],
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
