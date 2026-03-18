"""
Tests for require_permission() enforcement in locations-service.

Verifies:
1. require_permission() accepts users with the correct permission and rejects others.
2. Admin user (all permissions) passes all checks.
3. Cross-module isolation — locations permissions do not grant rules access and vice versa.
4. Endpoint-level tests via TestClient with mocked auth.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

from auth_http import UserRead, require_permission
from main import app
from database import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LOCATIONS_PERMISSIONS = [
    "locations:create",
    "locations:read",
    "locations:update",
    "locations:delete",
]

RULES_PERMISSIONS = [
    "rules:create",
    "rules:read",
    "rules:update",
    "rules:delete",
]

ALL_PERMISSIONS = LOCATIONS_PERMISSIONS + RULES_PERMISSIONS


def _make_user(permissions: list[str], role: str = "moderator", user_id: int = 10) -> UserRead:
    """Create a UserRead with the given permissions."""
    return UserRead(id=user_id, username="testuser", role=role, permissions=permissions)


def _call_require_permission(permission: str, user: UserRead) -> UserRead:
    """Invoke the inner checker produced by require_permission()."""
    checker = require_permission(permission)
    return checker(user)


def _mock_response(status_code: int, json_data: dict | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


COUNTRY_PAYLOAD = {
    "name": "Test Country",
    "description": "A test country",
}

RULE_PAYLOAD = {
    "title": "Test Rule",
    "content": "Some rule content",
    "sort_order": 1,
}


# ---------------------------------------------------------------------------
# 1. require_permission() acceptance tests
# ---------------------------------------------------------------------------


class TestRequirePermissionAcceptance:
    """Verify require_permission() grants/denies based on user.permissions."""

    def test_user_with_locations_create_succeeds(self):
        user = _make_user(["locations:create"])
        result = _call_require_permission("locations:create", user)
        assert result.id == user.id

    def test_user_without_locations_create_gets_403(self):
        user = _make_user(["locations:read"])
        with pytest.raises(HTTPException) as exc_info:
            _call_require_permission("locations:create", user)
        assert exc_info.value.status_code == 403

    def test_user_with_rules_create_but_not_locations_create(self):
        """User with rules:create can create rules but not locations."""
        user = _make_user(["rules:create"])
        result = _call_require_permission("rules:create", user)
        assert result.id == user.id
        with pytest.raises(HTTPException) as exc_info:
            _call_require_permission("locations:create", user)
        assert exc_info.value.status_code == 403

    def test_admin_with_all_permissions_succeeds(self):
        """Admin user passes all permission checks."""
        user = _make_user(ALL_PERMISSIONS, role="admin")
        for perm in ALL_PERMISSIONS:
            result = _call_require_permission(perm, user)
            assert result.id == user.id

    def test_user_with_empty_permissions_fails_all(self):
        """User with no permissions is rejected everywhere."""
        user = _make_user([], role="user")
        for perm in ALL_PERMISSIONS:
            with pytest.raises(HTTPException) as exc_info:
                _call_require_permission(perm, user)
            assert exc_info.value.status_code == 403

    def test_403_detail_message_is_present(self):
        user = _make_user([])
        with pytest.raises(HTTPException) as exc_info:
            _call_require_permission("locations:create", user)
        assert exc_info.value.detail


# ---------------------------------------------------------------------------
# 2. Cross-module isolation
# ---------------------------------------------------------------------------


class TestCrossModuleIsolation:
    """Verify that locations permissions do not grant rules access and vice versa."""

    def test_locations_perms_cannot_access_rules(self):
        """User with all locations:* permissions cannot access rules:* endpoints."""
        user = _make_user(LOCATIONS_PERMISSIONS)
        # locations succeed
        for perm in LOCATIONS_PERMISSIONS:
            result = _call_require_permission(perm, user)
            assert result.id == user.id
        # rules fail
        for perm in RULES_PERMISSIONS:
            with pytest.raises(HTTPException) as exc_info:
                _call_require_permission(perm, user)
            assert exc_info.value.status_code == 403

    def test_rules_perms_cannot_access_locations(self):
        """User with all rules:* permissions cannot access locations:* endpoints."""
        user = _make_user(RULES_PERMISSIONS)
        # rules succeed
        for perm in RULES_PERMISSIONS:
            result = _call_require_permission(perm, user)
            assert result.id == user.id
        # locations fail
        for perm in LOCATIONS_PERMISSIONS:
            with pytest.raises(HTTPException) as exc_info:
                _call_require_permission(perm, user)
            assert exc_info.value.status_code == 403

    def test_single_locations_create_cannot_locations_delete(self):
        user = _make_user(["locations:create"])
        _call_require_permission("locations:create", user)
        with pytest.raises(HTTPException) as exc_info:
            _call_require_permission("locations:delete", user)
        assert exc_info.value.status_code == 403

    def test_single_rules_update_cannot_rules_delete(self):
        user = _make_user(["rules:update"])
        _call_require_permission("rules:update", user)
        with pytest.raises(HTTPException) as exc_info:
            _call_require_permission("rules:delete", user)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Fixture: TestClient that returns 500 instead of raising on server errors
# ---------------------------------------------------------------------------

@pytest.fixture()
def safe_client():
    """TestClient that does NOT raise on server-side errors (returns 500)."""
    async def _fake_get_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _fake_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 3. Endpoint-level tests via TestClient
# ---------------------------------------------------------------------------


class TestEndpointRBACEnforcement:
    """Test that actual endpoints enforce require_permission() via mocked auth."""

    @patch("auth_http.requests.get")
    def test_create_country_with_permission_passes_auth(self, mock_get, safe_client):
        """User with locations:create passes auth on country create endpoint."""
        mock_get.return_value = _mock_response(200, {
            "id": 1, "username": "mod", "role": "moderator",
            "permissions": ["locations:create"],
        })
        response = safe_client.post(
            "/locations/countries/create",
            json=COUNTRY_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        # May fail on DB logic (500) but should NOT be 401/403
        assert response.status_code != 401
        assert response.status_code != 403

    @patch("auth_http.requests.get")
    def test_create_country_without_permission_returns_403(self, mock_get, client):
        """User without locations:create gets 403 on country create."""
        mock_get.return_value = _mock_response(200, {
            "id": 2, "username": "user", "role": "user",
            "permissions": ["locations:read"],
        })
        response = client.post(
            "/locations/countries/create",
            json=COUNTRY_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_create_rule_with_permission_passes_auth(self, mock_get, safe_client):
        """User with rules:create passes auth on rule create endpoint."""
        mock_get.return_value = _mock_response(200, {
            "id": 1, "username": "mod", "role": "moderator",
            "permissions": ["rules:create"],
        })
        response = safe_client.post(
            "/rules/create",
            json=RULE_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        # May fail on DB logic (500) but should NOT be 401/403
        assert response.status_code != 401
        assert response.status_code != 403

    @patch("auth_http.requests.get")
    def test_create_rule_without_permission_returns_403(self, mock_get, client):
        """User without rules:create gets 403 on rule create."""
        mock_get.return_value = _mock_response(200, {
            "id": 3, "username": "mod", "role": "moderator",
            "permissions": ["locations:create"],
        })
        response = client.post(
            "/rules/create",
            json=RULE_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_delete_location_without_permission_returns_403(self, mock_get, client):
        """User without locations:delete gets 403."""
        mock_get.return_value = _mock_response(200, {
            "id": 4, "username": "user", "role": "user",
            "permissions": [],
        })
        response = client.delete(
            "/locations/999/delete",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_delete_rule_without_permission_returns_403(self, mock_get, client):
        """User without rules:delete gets 403."""
        mock_get.return_value = _mock_response(200, {
            "id": 5, "username": "user", "role": "user",
            "permissions": ["rules:read"],
        })
        response = client.delete(
            "/rules/999/delete",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403

    def test_missing_token_returns_401(self, client):
        """No Authorization header returns 401."""
        response = client.post("/locations/countries/create", json=COUNTRY_PAYLOAD)
        assert response.status_code in (401, 403)

    @patch("auth_http.requests.get")
    def test_cross_module_endpoint_isolation(self, mock_get, client):
        """User with only locations:create gets 403 on rules:create endpoint."""
        mock_get.return_value = _mock_response(200, {
            "id": 6, "username": "mod", "role": "moderator",
            "permissions": ["locations:create", "locations:update", "locations:delete"],
        })
        response = client.post(
            "/rules/create",
            json=RULE_PAYLOAD,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403
