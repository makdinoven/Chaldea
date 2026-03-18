"""
FEAT-033 Task #5 — Tests verifying legacy upload-avatar endpoint and preview
models have been removed from user-service.

Covers:
1. POST /users/upload-avatar/ returns 404/405 (endpoint removed)
2. No /assets static route is mounted
3. User registration (create_user) works without preview table writes
4. Preview model classes are no longer in models.py
"""

from unittest.mock import patch

from crud import create_user
from schemas import UserCreate
import models


# ---------------------------------------------------------------------------
# 1. Removed endpoint: POST /users/upload-avatar/
# ---------------------------------------------------------------------------

class TestUploadAvatarEndpointRemoved:
    """Verify that the legacy upload-avatar endpoint no longer exists."""

    def test_post_upload_avatar_returns_404_or_405(self, client):
        """POST /users/upload-avatar/ must not be routable (404 or 405)."""
        response = client.post(
            "/users/upload-avatar/",
            files=[("file", ("test.png", b"fake-image-data", "image/png"))],
        )
        assert response.status_code in (404, 405)

    def test_get_upload_avatar_not_routable(self, client):
        """GET /users/upload-avatar/ must not return 200 (endpoint removed)."""
        response = client.get("/users/upload-avatar/")
        # May return 404, 405, or 422 depending on router matching;
        # the key assertion is that it does NOT return 200.
        assert response.status_code != 200


# ---------------------------------------------------------------------------
# 2. Static mount /assets is removed
# ---------------------------------------------------------------------------

class TestStaticMountRemoved:
    """Verify that /assets static file serving is no longer mounted."""

    def test_assets_route_returns_404(self, client):
        """GET /assets/avatars/test.png should return 404 (no static mount)."""
        response = client.get("/assets/avatars/test.png")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# 3. Registration still works without preview table writes
# ---------------------------------------------------------------------------

class TestCreateUserWithoutPreviews:
    """Verify that create_user works correctly after preview table removal."""

    def test_create_user_succeeds(self, db_session):
        """create_user should create a user without errors (no preview writes)."""
        user_data = UserCreate(
            email="newuser@example.com",
            username="newuser",
            password="ValidPass123",
        )
        user = create_user(db_session, user_data)

        assert user.id is not None
        assert user.email == "newuser@example.com"
        assert user.username == "newuser"
        assert user.avatar is not None  # Default avatar should be set

    @patch("main.send_notification_event")
    def test_register_endpoint_succeeds(self, mock_notify, client, db_session):
        """POST /users/register should work without preview table side-effects."""
        response = client.post("/users/register", json={
            "email": "regtest@example.com",
            "username": "regtest",
            "password": "ValidPass123",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "regtest"
        assert "id" in data


# ---------------------------------------------------------------------------
# 4. Preview model classes removed from models.py
# ---------------------------------------------------------------------------

class TestPreviewModelsRemoved:
    """Verify that legacy preview model classes no longer exist."""

    def test_user_avatar_preview_model_absent(self):
        """UserAvatarPreview should not exist in models module."""
        assert not hasattr(models, "UserAvatarPreview"), \
            "UserAvatarPreview model should have been removed"

    def test_user_avatar_character_preview_model_absent(self):
        """UserAvatarCharacterPreview should not exist in models module."""
        assert not hasattr(models, "UserAvatarCharacterPreview"), \
            "UserAvatarCharacterPreview model should have been removed"
