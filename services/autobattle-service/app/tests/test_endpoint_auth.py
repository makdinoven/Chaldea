"""
Tests for endpoint authentication in autobattle-service.

Covers:
- AB1: POST /mode        — admin-only (battles:manage)
- AB2: POST /register    — admin-only (battles:manage)
- AB3: POST /unregister  — admin-only (battles:manage)

All three endpoints require the `battles:manage` permission.

Uses dependency overrides and patches to avoid real Redis connections.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# Mock aioredis before importing main (it connects on startup)
aioredis_mock = MagicMock()
aioredis_mock.from_url = AsyncMock(return_value=MagicMock())
sys.modules["aioredis"] = aioredis_mock

# Mock clients module to avoid battle-service HTTP calls
clients_mock = MagicMock()
clients_mock.get_battle_state = AsyncMock(return_value={})
clients_mock.post_battle_action = AsyncMock(return_value={})
sys.modules["clients"] = clients_mock

# Mock strategy module
strategy_mock = MagicMock()
sys.modules["strategy"] = strategy_mock

from main import app  # noqa: E402

# Clear startup handlers to prevent Redis connection
app.router.on_startup.clear()

from fastapi.testclient import TestClient  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


# ═══════════════════════════════════════════════════════════════════════════
# AB1: POST /mode — requires battles:manage
# ═══════════════════════════════════════════════════════════════════════════


class TestSetModeAuth:
    """Auth + permission tests for POST /mode."""

    def test_missing_token_returns_401(self):
        with TestClient(app) as client:
            response = client.post("/mode", json={"mode": "attack"})
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get):
        mock_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.post(
                "/mode",
                json={"mode": "attack"},
                headers={"Authorization": "Bearer bad-token"},
            )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_no_permission_returns_403(self, mock_auth_get):
        """User without battles:manage permission -> 403."""
        mock_auth_get.return_value = _mock_response(
            200, {"id": 2, "username": "user", "role": "user", "permissions": []}
        )
        with TestClient(app) as client:
            response = client.post(
                "/mode",
                json={"mode": "attack"},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_with_permission_passes_auth(self, mock_auth_get):
        """User with battles:manage permission -> auth passes."""
        mock_auth_get.return_value = _mock_response(
            200,
            {
                "id": 1,
                "username": "admin",
                "role": "admin",
                "permissions": ["battles:manage"],
            },
        )
        with TestClient(app) as client:
            response = client.post(
                "/mode",
                json={"mode": "attack"},
                headers={"Authorization": "Bearer fake-token"},
            )
        # Should not be 401 or 403
        assert response.status_code not in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════
# AB2: POST /register — requires battles:manage
# ═══════════════════════════════════════════════════════════════════════════


class TestRegisterAuth:
    """Auth + permission tests for POST /register."""

    def test_missing_token_returns_401(self):
        with TestClient(app) as client:
            response = client.post(
                "/register", json={"participant_id": 1, "battle_id": 0}
            )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get):
        mock_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.post(
                "/register",
                json={"participant_id": 1, "battle_id": 0},
                headers={"Authorization": "Bearer bad-token"},
            )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_no_permission_returns_403(self, mock_auth_get):
        """User without battles:manage -> 403."""
        mock_auth_get.return_value = _mock_response(
            200, {"id": 2, "username": "user", "role": "user", "permissions": []}
        )
        with TestClient(app) as client:
            response = client.post(
                "/register",
                json={"participant_id": 1, "battle_id": 0},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_with_permission_passes_auth(self, mock_auth_get):
        """User with battles:manage -> auth passes, returns success."""
        mock_auth_get.return_value = _mock_response(
            200,
            {
                "id": 1,
                "username": "admin",
                "role": "admin",
                "permissions": ["battles:manage"],
            },
        )
        with TestClient(app) as client:
            response = client.post(
                "/register",
                json={"participant_id": 100, "battle_id": 0},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code not in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════
# AB3: POST /unregister — requires battles:manage
# ═══════════════════════════════════════════════════════════════════════════


class TestUnregisterAuth:
    """Auth + permission tests for POST /unregister."""

    def test_missing_token_returns_401(self):
        with TestClient(app) as client:
            response = client.post("/unregister", json={"participant_id": 1})
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get):
        mock_get.return_value = _mock_response(401)
        with TestClient(app) as client:
            response = client.post(
                "/unregister",
                json={"participant_id": 1},
                headers={"Authorization": "Bearer bad-token"},
            )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_no_permission_returns_403(self, mock_auth_get):
        """User without battles:manage -> 403."""
        mock_auth_get.return_value = _mock_response(
            200, {"id": 2, "username": "user", "role": "user", "permissions": []}
        )
        with TestClient(app) as client:
            response = client.post(
                "/unregister",
                json={"participant_id": 1},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_with_permission_passes_auth(self, mock_auth_get):
        """User with battles:manage -> auth passes."""
        mock_auth_get.return_value = _mock_response(
            200,
            {
                "id": 1,
                "username": "admin",
                "role": "admin",
                "permissions": ["battles:manage"],
            },
        )
        with TestClient(app) as client:
            response = client.post(
                "/unregister",
                json={"participant_id": 999},
                headers={"Authorization": "Bearer fake-token"},
            )
        assert response.status_code not in (401, 403)
