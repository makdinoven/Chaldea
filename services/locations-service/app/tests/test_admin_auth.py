"""
Tests for admin endpoint authentication in locations-service.

Verifies that admin endpoints (create_country, create_location)
properly enforce JWT + admin role checks.
"""

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


COUNTRY_PAYLOAD = {
    "name": "Test Country",
    "description": "A test country",
}

LOCATION_PAYLOAD = {
    "name": "Test Location",
    "district_id": 1,
}


# ── POST /locations/countries/create ───────────────────────────────────────


class TestCreateCountryAuth:
    """Auth tests for POST /locations/countries/create."""

    def test_missing_token_returns_401(self, client):
        """No Authorization header → 401."""
        response = client.post("/locations/countries/create", json=COUNTRY_PAYLOAD)
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        """Valid token but role != admin → 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 2, "username": "user", "role": "user"}
        )
        response = client.post(
            "/locations/countries/create",
            json=COUNTRY_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get, client):
        """User-service returns 401 for invalid token → 401."""
        mock_get.return_value = _mock_response(401)
        response = client.post(
            "/locations/countries/create",
            json=COUNTRY_PAYLOAD,
            headers={"Authorization": "Bearer bad-token"},
        )
        assert response.status_code == 401


# ── POST /locations/ (create_location) ─────────────────────────────────────


class TestCreateLocationAuth:
    """Auth tests for POST /locations/."""

    def test_missing_token_returns_401(self, client):
        response = client.post("/locations/", json=LOCATION_PAYLOAD)
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        mock_get.return_value = _mock_response(
            200, {"id": 2, "username": "user", "role": "user"}
        )
        response = client.post(
            "/locations/",
            json=LOCATION_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
