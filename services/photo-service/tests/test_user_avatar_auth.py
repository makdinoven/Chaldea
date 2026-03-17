"""
Tests for JWT authentication on user avatar endpoints.

Covers:
- change_user_avatar_photo: 401 without token, 403 wrong user, 200 correct user
- user_avatar_preview: 401 without token, 403 wrong user, 200 correct user
"""

import io
from unittest.mock import patch, MagicMock

from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_image(width: int = 100, height: int = 100, fmt: str = "PNG") -> bytes:
    """Create a minimal valid image in memory and return its bytes."""
    img = Image.new("RGB", (width, height), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _multipart_file(content: bytes, filename: str = "avatar.png", content_type: str = "image/png"):
    """Return a file tuple suitable for TestClient ``files=`` parameter."""
    return ("file", (filename, io.BytesIO(content), content_type))


def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


AUTH_HEADERS = {"Authorization": "Bearer valid-token"}
USER_42 = {"id": 42, "username": "testuser", "role": "user"}
USER_99 = {"id": 99, "username": "otheruser", "role": "user"}


# ===========================================================================
# POST /photo/change_user_avatar_photo
# ===========================================================================

class TestChangeUserAvatarAuth:
    """Auth tests for POST /photo/change_user_avatar_photo."""

    def test_missing_token_returns_401(self, client):
        """No Authorization header -> 401."""
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_user_avatar_photo",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes)],
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_auth, client):
        """User-service returns 401 for bad token -> 401."""
        mock_auth.return_value = _mock_response(401)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_user_avatar_photo",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers={"Authorization": "Bearer bad-token"},
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_wrong_user_id_returns_403(self, mock_auth, client):
        """Authenticated as user 99, trying to upload for user 42 -> 403."""
        mock_auth.return_value = _mock_response(200, USER_99)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_user_avatar_photo",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 403
        assert "аватар" in response.json()["detail"].lower() or "свой" in response.json()["detail"].lower()

    @patch("main.update_user_avatar")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/bucket/user_avatars/photo.webp")
    @patch("auth_http.requests.get")
    def test_correct_user_returns_200(self, mock_auth, mock_s3, mock_db, client):
        """Authenticated as user 42, uploading for user 42 -> 200."""
        mock_auth.return_value = _mock_response(200, USER_42)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_user_avatar_photo",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        assert "avatar_url" in body
        assert body["message"] == "Фото успешно загружено"


# ===========================================================================
# POST /photo/user_avatar_preview
# ===========================================================================

class TestUserAvatarPreviewAuth:
    """Auth tests for POST /photo/user_avatar_preview."""

    def test_missing_token_returns_401(self, client):
        """No Authorization header -> 401."""
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/user_avatar_preview",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes)],
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_auth, client):
        """User-service returns 401 for bad token -> 401."""
        mock_auth.return_value = _mock_response(401)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/user_avatar_preview",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers={"Authorization": "Bearer bad-token"},
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_wrong_user_id_returns_403(self, mock_auth, client):
        """Authenticated as user 99, preview for user 42 -> 403."""
        mock_auth.return_value = _mock_response(200, USER_99)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/user_avatar_preview",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 403

    @patch("main.update_user_avatar_preview")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/bucket/user_preview/photo.webp")
    @patch("auth_http.requests.get")
    def test_correct_user_returns_200(self, mock_auth, mock_s3, mock_db, client):
        """Authenticated as user 42, preview for user 42 -> 200."""
        mock_auth.return_value = _mock_response(200, USER_42)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/user_avatar_preview",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        body = response.json()
        assert "avatar_url" in body
        assert body["message"] == "Фото успешно загружено"
