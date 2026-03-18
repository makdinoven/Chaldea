"""
Tests for require_permission() enforcement in character-service.

Verifies:
1. require_permission() accepts users with the correct permission and rejects others.
2. Granular permission isolation — one permission does not grant access to another.
3. Admin user (all permissions) passes all checks.
4. User with empty permissions fails all checks.
5. Endpoint-level tests via TestClient with mocked auth.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

from auth_http import UserRead, require_permission


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_CHARACTER_PERMISSIONS = [
    "characters:create",
    "characters:read",
    "characters:update",
    "characters:delete",
    "characters:approve",
]


def _make_user(permissions: list[str], role: str = "moderator", user_id: int = 10) -> UserRead:
    """Create a UserRead with the given permissions."""
    return UserRead(id=user_id, username="testuser", role=role, permissions=permissions)


def _call_require_permission(permission: str, user: UserRead) -> UserRead:
    """Invoke the inner checker produced by require_permission()."""
    checker = require_permission(permission)
    # The checker is a function(user: UserRead) -> UserRead
    return checker(user)


# ---------------------------------------------------------------------------
# Helper for endpoint-level tests
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, json_data: dict | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


# ---------------------------------------------------------------------------
# 1. require_permission() acceptance tests
# ---------------------------------------------------------------------------


class TestRequirePermissionAcceptance:
    """Verify require_permission() grants/denies based on user.permissions."""

    def test_user_with_approve_permission_succeeds(self):
        user = _make_user(["characters:approve"])
        result = _call_require_permission("characters:approve", user)
        assert result.id == user.id

    def test_user_without_approve_permission_gets_403(self):
        user = _make_user(["characters:read"])
        with pytest.raises(HTTPException) as exc_info:
            _call_require_permission("characters:approve", user)
        assert exc_info.value.status_code == 403

    def test_user_with_read_but_not_delete(self):
        """User with characters:read can read but cannot delete."""
        user = _make_user(["characters:read"])
        # read succeeds
        result = _call_require_permission("characters:read", user)
        assert result.id == user.id
        # delete fails
        with pytest.raises(HTTPException) as exc_info:
            _call_require_permission("characters:delete", user)
        assert exc_info.value.status_code == 403

    def test_admin_with_all_permissions_succeeds(self):
        """Admin user (all permissions) passes all checks."""
        user = _make_user(ALL_CHARACTER_PERMISSIONS, role="admin")
        for perm in ALL_CHARACTER_PERMISSIONS:
            result = _call_require_permission(perm, user)
            assert result.id == user.id

    def test_user_with_empty_permissions_fails_all(self):
        """User with no permissions is rejected by every check."""
        user = _make_user([], role="user")
        for perm in ALL_CHARACTER_PERMISSIONS:
            with pytest.raises(HTTPException) as exc_info:
                _call_require_permission(perm, user)
            assert exc_info.value.status_code == 403

    def test_403_detail_message_is_present(self):
        """403 response includes a non-empty detail."""
        user = _make_user([])
        with pytest.raises(HTTPException) as exc_info:
            _call_require_permission("characters:approve", user)
        assert exc_info.value.detail  # non-empty


# ---------------------------------------------------------------------------
# 2. Granular permission isolation
# ---------------------------------------------------------------------------


class TestGranularPermissionIsolation:
    """Verify that one permission does not implicitly grant another."""

    def test_create_cannot_update(self):
        user = _make_user(["characters:create"])
        # create succeeds
        result = _call_require_permission("characters:create", user)
        assert result.id == user.id
        # update fails
        with pytest.raises(HTTPException) as exc_info:
            _call_require_permission("characters:update", user)
        assert exc_info.value.status_code == 403

    def test_read_cannot_approve(self):
        user = _make_user(["characters:read"])
        # read succeeds
        result = _call_require_permission("characters:read", user)
        assert result.id == user.id
        # approve fails
        with pytest.raises(HTTPException) as exc_info:
            _call_require_permission("characters:approve", user)
        assert exc_info.value.status_code == 403

    def test_delete_cannot_create(self):
        user = _make_user(["characters:delete"])
        result = _call_require_permission("characters:delete", user)
        assert result.id == user.id
        with pytest.raises(HTTPException) as exc_info:
            _call_require_permission("characters:create", user)
        assert exc_info.value.status_code == 403

    def test_approve_cannot_delete(self):
        user = _make_user(["characters:approve"])
        result = _call_require_permission("characters:approve", user)
        assert result.id == user.id
        with pytest.raises(HTTPException) as exc_info:
            _call_require_permission("characters:delete", user)
        assert exc_info.value.status_code == 403

    def test_multiple_permissions_grant_only_listed(self):
        """User with create+read can do those but not update/delete/approve."""
        user = _make_user(["characters:create", "characters:read"])
        _call_require_permission("characters:create", user)
        _call_require_permission("characters:read", user)
        for denied in ["characters:update", "characters:delete", "characters:approve"]:
            with pytest.raises(HTTPException) as exc_info:
                _call_require_permission(denied, user)
            assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 3. Endpoint-level tests via TestClient
# ---------------------------------------------------------------------------


class TestEndpointRBACEnforcement:
    """Test that actual endpoints enforce require_permission() via mocked auth."""

    @patch("auth_http.requests.get")
    def test_approve_endpoint_with_permission_passes_auth(self, mock_get, client):
        """User with characters:approve passes the auth check on approve endpoint."""
        mock_get.return_value = _mock_response(200, {
            "id": 1, "username": "mod", "role": "moderator",
            "permissions": ["characters:approve"],
        })
        response = client.post(
            "/characters/requests/999/approve",
            headers={"Authorization": "Bearer fake-token"},
        )
        # May fail on DB/business logic but should NOT be 401/403
        assert response.status_code != 401
        assert response.status_code != 403

    @patch("auth_http.requests.get")
    def test_approve_endpoint_without_permission_returns_403(self, mock_get, client):
        """User without characters:approve gets 403 on approve endpoint."""
        mock_get.return_value = _mock_response(200, {
            "id": 2, "username": "mod", "role": "moderator",
            "permissions": ["characters:read"],
        })
        response = client.post(
            "/characters/requests/999/approve",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_delete_endpoint_without_permission_returns_403(self, mock_get, client):
        """User without characters:delete gets 403 on delete endpoint."""
        mock_get.return_value = _mock_response(200, {
            "id": 3, "username": "editor", "role": "editor",
            "permissions": ["characters:read"],
        })
        response = client.delete(
            "/characters/999",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_admin_list_endpoint_without_permission_returns_403(self, mock_get, client):
        """User without characters:read gets 403 on admin list endpoint."""
        mock_get.return_value = _mock_response(200, {
            "id": 4, "username": "user", "role": "user",
            "permissions": [],
        })
        response = client.get(
            "/characters/admin/list",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_missing_token_returns_401(self, mock_get, client):
        """No Authorization header returns 401."""
        response = client.post("/characters/requests/999/approve")
        assert response.status_code in (401, 403)
