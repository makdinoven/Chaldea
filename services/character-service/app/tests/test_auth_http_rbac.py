"""
Tests for updated auth_http.py RBAC logic in character-service.

Verifies:
1. get_admin_user() accepts admin and moderator roles, rejects others.
2. UserRead schema correctly parses responses with/without permissions field.
"""

import pytest
from fastapi import HTTPException

from auth_http import UserRead, get_admin_user


# ---------------------------------------------------------------------------
# 1. get_admin_user() role acceptance
# ---------------------------------------------------------------------------


class TestGetAdminUserRoleAcceptance:
    """Verify get_admin_user() accepts admin/moderator and rejects others."""

    def test_admin_role_accepted(self):
        user = UserRead(id=1, username="admin", role="admin", permissions=["users:manage"])
        result = get_admin_user(user)
        assert result.role == "admin"
        assert result.id == 1

    def test_moderator_role_accepted(self):
        user = UserRead(id=2, username="mod", role="moderator", permissions=["items:read"])
        result = get_admin_user(user)
        assert result.role == "moderator"
        assert result.id == 2

    def test_editor_role_rejected(self):
        user = UserRead(id=3, username="editor", role="editor", permissions=[])
        with pytest.raises(HTTPException) as exc_info:
            get_admin_user(user)
        assert exc_info.value.status_code == 403

    def test_user_role_rejected(self):
        user = UserRead(id=4, username="player", role="user", permissions=[])
        with pytest.raises(HTTPException) as exc_info:
            get_admin_user(user)
        assert exc_info.value.status_code == 403

    def test_none_role_rejected(self):
        user = UserRead(id=5, username="norole", role=None, permissions=[])
        with pytest.raises(HTTPException) as exc_info:
            get_admin_user(user)
        assert exc_info.value.status_code == 403

    def test_rejected_error_detail_is_informative(self):
        """403 response includes a descriptive detail message."""
        user = UserRead(id=6, username="user", role="user", permissions=[])
        with pytest.raises(HTTPException) as exc_info:
            get_admin_user(user)
        assert exc_info.value.detail  # non-empty message


# ---------------------------------------------------------------------------
# 2. UserRead schema parsing
# ---------------------------------------------------------------------------


class TestUserReadSchemaParsing:
    """Verify UserRead Pydantic model handles various response shapes."""

    def test_with_permissions_field(self):
        user = UserRead(
            id=1,
            username="admin",
            role="admin",
            permissions=["users:manage", "items:create"],
        )
        assert user.permissions == ["users:manage", "items:create"]
        assert user.role == "admin"

    def test_without_permissions_field_defaults_to_empty_list(self):
        """Backward compat: old user-service responses without permissions."""
        user = UserRead(id=2, username="olduser", role="user")
        assert user.permissions == []

    def test_without_role_field_defaults_to_none(self):
        user = UserRead(id=3, username="minimaluser")
        assert user.role is None
        assert user.permissions == []

    def test_all_fields_correctly_parsed(self):
        user = UserRead(
            id=10,
            username="fulluser",
            role="moderator",
            permissions=["items:read", "items:create", "items:delete"],
        )
        assert user.id == 10
        assert user.username == "fulluser"
        assert user.role == "moderator"
        assert len(user.permissions) == 3

    def test_from_dict_like_api_response(self):
        """Simulate parsing a dict as returned by user-service /users/me."""
        data = {
            "id": 7,
            "username": "apiuser",
            "role": "admin",
            "permissions": ["users:manage"],
        }
        user = UserRead(**data)
        assert user.id == 7
        assert user.permissions == ["users:manage"]

    def test_from_dict_without_permissions(self):
        """Simulate old API response that lacks the permissions field."""
        data = {"id": 8, "username": "oldapi", "role": "user"}
        user = UserRead(**data)
        assert user.permissions == []

    def test_extra_fields_ignored(self):
        """Extra fields from API response should not cause errors."""
        data = {
            "id": 9,
            "username": "extrafields",
            "role": "user",
            "permissions": [],
            "email": "extra@test.com",
            "avatar_url": "/img.png",
        }
        # Pydantic v1 ignores extra fields by default
        user = UserRead(**data)
        assert user.id == 9
        assert user.username == "extrafields"
