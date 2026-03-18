"""
Tests for admin endpoint authentication in inventory-service.

Verifies that admin endpoints (create_item, update_item, delete_item)
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


ITEM_PAYLOAD = {
    "name": "Test Sword",
    "item_level": 1,
    "item_type": "main_weapon",
    "item_rarity": "common",
    "max_stack_size": 1,
    "is_unique": False,
    "description": "A test weapon",
}


# ── POST /inventory/items (create_item) ────────────────────────────────────


class TestCreateItemAuth:
    """Auth tests for POST /inventory/items."""

    def test_missing_token_returns_401(self, client: TestClient):
        """No Authorization header → 401."""
        response = client.post("/inventory/items", json=ITEM_PAYLOAD)
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client: TestClient):
        """Valid token but role != admin → 403."""
        mock_get.return_value = _mock_response(
            200, {"id": 2, "username": "user", "role": "user"}
        )
        response = client.post(
            "/inventory/items",
            json=ITEM_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_admin_returns_201(self, mock_get, client: TestClient, db_session):
        """Valid admin token → 201 (item created)."""
        mock_get.return_value = _mock_response(
            200, {"id": 1, "username": "admin", "role": "admin", "permissions": ["items:create", "items:read", "items:update", "items:delete"]}
        )
        response = client.post(
            "/inventory/items",
            json=ITEM_PAYLOAD,
            headers={"Authorization": "Bearer admin-token"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == ITEM_PAYLOAD["name"]


# ── DELETE /inventory/items/{item_id} (delete_item) ────────────────────────


class TestDeleteItemAuth:
    """Auth tests for DELETE /inventory/items/{item_id}."""

    def test_missing_token_returns_401(self, client: TestClient):
        response = client.delete("/inventory/items/1")
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client: TestClient):
        mock_get.return_value = _mock_response(
            200, {"id": 2, "username": "user", "role": "user"}
        )
        response = client.delete(
            "/inventory/items/1",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
