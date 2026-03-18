"""
FEAT-033 Task #5 — Tests verifying preview endpoints have been removed
from photo-service, and that the remaining avatar endpoints still work.

Covers:
1. POST /photo/character_avatar_preview returns 404/405 (endpoint removed)
2. POST /photo/user_avatar_preview returns 404/405 (endpoint removed)
3. POST /photo/change_user_avatar_photo still works (mock S3 + DB + auth)
4. POST /photo/change_character_avatar_photo still works (mock S3 + DB + auth)
5. Preview CRUD functions no longer importable from crud module
"""

import io
from unittest.mock import patch, MagicMock

from PIL import Image

import crud


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


# ---------------------------------------------------------------------------
# 1. Removed endpoint: POST /photo/character_avatar_preview
# ---------------------------------------------------------------------------

class TestCharacterAvatarPreviewRemoved:
    """Verify that the character avatar preview endpoint no longer exists."""

    @patch("auth_http.requests.get")
    def test_post_character_avatar_preview_returns_404(self, mock_auth, client):
        """POST /photo/character_avatar_preview must not be routable (404 or 405)."""
        mock_auth.return_value = _mock_response(200, USER_42)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/character_avatar_preview",
            data={"character_id": "1", "user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )
        assert response.status_code in (404, 405)


# ---------------------------------------------------------------------------
# 2. Removed endpoint: POST /photo/user_avatar_preview
# ---------------------------------------------------------------------------

class TestUserAvatarPreviewRemoved:
    """Verify that the user avatar preview endpoint no longer exists."""

    @patch("auth_http.requests.get")
    def test_post_user_avatar_preview_returns_404(self, mock_auth, client):
        """POST /photo/user_avatar_preview must not be routable (404 or 405)."""
        mock_auth.return_value = _mock_response(200, USER_42)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/user_avatar_preview",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )
        assert response.status_code in (404, 405)


# ---------------------------------------------------------------------------
# 3. Remaining endpoint: POST /photo/change_user_avatar_photo still works
# ---------------------------------------------------------------------------

class TestChangeUserAvatarStillWorks:
    """Verify that the user avatar upload endpoint still functions correctly."""

    @patch("main.update_user_avatar")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/bucket/user_avatars/photo.webp")
    @patch("auth_http.requests.get")
    def test_upload_user_avatar_returns_200(self, mock_auth, mock_s3, mock_db, client):
        """POST with valid image + correct auth -> 200 with avatar_url."""
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

    @patch("main.update_user_avatar")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/bucket/user_avatars/photo.webp")
    @patch("auth_http.requests.get")
    def test_upload_user_avatar_no_preview_side_effect(self, mock_auth, mock_s3, mock_db, client):
        """update_user_avatar should be called WITHOUT preview table writes."""
        mock_auth.return_value = _mock_response(200, USER_42)
        image_bytes = _create_test_image()

        client.post(
            "/photo/change_user_avatar_photo",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )

        # update_user_avatar should be called once (for the main avatar update)
        mock_db.assert_called_once()


# ---------------------------------------------------------------------------
# 4. Remaining endpoint: POST /photo/change_character_avatar_photo still works
# ---------------------------------------------------------------------------

class TestChangeCharacterAvatarStillWorks:
    """Verify that the character avatar upload endpoint still functions correctly."""

    @patch("main.update_character_avatar")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/bucket/character_avatars/photo.webp")
    @patch("main.get_character_owner_id", return_value=42)
    @patch("auth_http.requests.get")
    def test_upload_character_avatar_returns_200(self, mock_auth, mock_owner, mock_s3, mock_db, client):
        """POST with valid image + correct auth -> 200 with avatar_url."""
        mock_auth.return_value = _mock_response(200, USER_42)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1", "user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        body = response.json()
        assert "avatar_url" in body
        assert body["message"] == "Фото успешно загружено"

    @patch("main.update_character_avatar")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/bucket/character_avatars/photo.webp")
    @patch("main.get_character_owner_id", return_value=42)
    @patch("auth_http.requests.get")
    def test_upload_character_avatar_no_preview_side_effect(self, mock_auth, mock_owner, mock_s3, mock_db, client):
        """update_character_avatar should be called WITHOUT preview table writes."""
        mock_auth.return_value = _mock_response(200, USER_42)
        image_bytes = _create_test_image()

        client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1", "user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )

        # update_character_avatar should be called once (for the main avatar update)
        mock_db.assert_called_once()


# ---------------------------------------------------------------------------
# 5. Preview CRUD functions no longer exist
# ---------------------------------------------------------------------------

class TestPreviewCrudFunctionsRemoved:
    """Verify that legacy preview CRUD functions are no longer importable."""

    def test_update_user_avatar_preview_not_in_crud(self):
        """update_user_avatar_preview should not exist in crud module."""
        assert not hasattr(crud, "update_user_avatar_preview"), \
            "update_user_avatar_preview should have been removed from crud.py"

    def test_update_character_avatar_preview_not_in_crud(self):
        """update_character_avatar_preview should not exist in crud module."""
        assert not hasattr(crud, "update_character_avatar_preview"), \
            "update_character_avatar_preview should have been removed from crud.py"
