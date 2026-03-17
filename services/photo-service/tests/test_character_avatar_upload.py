"""
Integration tests for POST /photo/change_character_avatar_photo endpoint.

Covers:
- Successful upload (mocked S3 + DB + auth) — returns 200 with avatar_url
- File too large (>15 MB) — returns 500 (convert_to_webp raises ValueError)
- Non-image MIME type — returns 400 (MIME validation)
- Missing required fields — returns 422 (FastAPI validation)
- Auth: 401 without token, 403 wrong owner, 404 character not found
- SQL injection in character_id — returns 422
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


# ---------------------------------------------------------------------------
# 1. Successful upload (with auth)
# ---------------------------------------------------------------------------

class TestCharacterAvatarUploadSuccess:
    """Happy-path: valid image, mocked S3 and DB, correct auth."""

    @patch("main.update_character_avatar")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/bucket/character_avatars/photo.webp")
    @patch("main.get_character_owner_id", return_value=42)
    @patch("auth_http.requests.get")
    def test_upload_returns_200_with_avatar_url(self, mock_auth, mock_owner, mock_s3, mock_db, client):
        """POST with valid image + correct auth -> 200, response contains avatar_url."""
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
        assert body["avatar_url"] == "https://s3.example.com/bucket/character_avatars/photo.webp"
        assert body["message"] == "Фото успешно загружено"

    @patch("main.update_character_avatar")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/bucket/character_avatars/photo.webp")
    @patch("main.get_character_owner_id", return_value=42)
    @patch("auth_http.requests.get")
    def test_upload_calls_s3_and_db(self, mock_auth, mock_owner, mock_s3, mock_db, client):
        """Verify that S3 upload and DB update are called with correct args."""
        mock_auth.return_value = _mock_response(200, USER_42)
        image_bytes = _create_test_image()

        client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "7", "user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )

        mock_s3.assert_called_once()
        mock_db.assert_called_once()
        db_args = mock_db.call_args[0]
        assert db_args[0] == 7   # character_id
        assert db_args[2] == 42  # user_id


# ---------------------------------------------------------------------------
# 2. Auth enforcement
# ---------------------------------------------------------------------------

class TestCharacterAvatarUploadAuth:
    """JWT auth and character ownership checks."""

    def test_missing_token_returns_401(self, client):
        """No Authorization header -> 401."""
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1", "user_id": "42"},
            files=[_multipart_file(image_bytes)],
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_auth, client):
        """User-service returns 401 for bad token -> 401."""
        mock_auth.return_value = _mock_response(401)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1", "user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers={"Authorization": "Bearer bad-token"},
        )
        assert response.status_code == 401

    @patch("main.get_character_owner_id", return_value=99)
    @patch("auth_http.requests.get")
    def test_wrong_owner_returns_403(self, mock_auth, mock_owner, client):
        """Character belongs to user 99, authenticated as user 42 -> 403."""
        mock_auth.return_value = _mock_response(200, USER_42)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1", "user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 403
        assert "персонаж" in response.json()["detail"].lower() or "свой" in response.json()["detail"].lower()

    @patch("main.get_character_owner_id", return_value=None)
    @patch("auth_http.requests.get")
    def test_character_not_found_returns_404(self, mock_auth, mock_owner, client):
        """Character does not exist -> 404."""
        mock_auth.return_value = _mock_response(200, USER_42)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "9999", "user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 404
        assert "не найден" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 3. File too large (>15 MB)
# ---------------------------------------------------------------------------

class TestCharacterAvatarUploadTooLarge:
    """File exceeding 15 MB limit is rejected by convert_to_webp."""

    @patch("main.get_character_owner_id", return_value=42)
    @patch("auth_http.requests.get")
    def test_oversized_file_returns_500(self, mock_auth, mock_owner, client):
        """
        convert_to_webp raises ValueError when file > 15 MB.
        The endpoint catches all exceptions and returns 500.
        """
        mock_auth.return_value = _mock_response(200, USER_42)
        oversized_data = b"\x89PNG\r\n\x1a\n" + (b"\x00" * (15 * 1024 * 1024 + 1))

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1", "user_id": "42"},
            files=[_multipart_file(oversized_data, filename="big.png")],
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 500
        assert "15" in response.json()["detail"] or "limit" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 4. Non-image MIME type -> 400
# ---------------------------------------------------------------------------

class TestCharacterAvatarUploadInvalidMime:
    """Non-image MIME type is rejected by validate_image_mime with 400."""

    @patch("main.get_character_owner_id", return_value=42)
    @patch("auth_http.requests.get")
    def test_non_image_mime_returns_400(self, mock_auth, mock_owner, client):
        """text/plain MIME type -> 400."""
        mock_auth.return_value = _mock_response(200, USER_42)
        fake_content = b"This is not an image at all. Just plain text."

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1", "user_id": "42"},
            files=[_multipart_file(fake_content, filename="fake.txt", content_type="text/plain")],
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 400


# ---------------------------------------------------------------------------
# 5. Missing required fields -> 422
# ---------------------------------------------------------------------------

class TestCharacterAvatarUploadMissingFields:
    """FastAPI returns 422 when required Form/File fields are missing (with valid auth)."""

    @patch("main.get_character_owner_id", return_value=42)
    @patch("auth_http.requests.get")
    def test_missing_character_id_returns_422(self, mock_auth, mock_owner, client):
        """No character_id in form data -> 422."""
        mock_auth.return_value = _mock_response(200, USER_42)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 422

    @patch("main.get_character_owner_id", return_value=42)
    @patch("auth_http.requests.get")
    def test_missing_user_id_returns_422(self, mock_auth, mock_owner, client):
        """No user_id in form data -> 422."""
        mock_auth.return_value = _mock_response(200, USER_42)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 422

    @patch("auth_http.requests.get")
    def test_missing_file_returns_422(self, mock_auth, client):
        """No file uploaded -> 422."""
        mock_auth.return_value = _mock_response(200, USER_42)

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1", "user_id": "42"},
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 422

    def test_missing_all_fields_no_auth_returns_401(self, client):
        """No fields and no auth -> 401 (auth checked first)."""
        response = client.post(
            "/photo/change_character_avatar_photo",
        )

        assert response.status_code == 401


# ---------------------------------------------------------------------------
# 6. SQL injection — security test
# ---------------------------------------------------------------------------

class TestCharacterAvatarUploadSecurity:
    """Security: verify that malicious input does not crash the service."""

    @patch("auth_http.requests.get")
    def test_sql_injection_in_character_id(self, mock_auth, client):
        """
        character_id is typed as int in FastAPI Form(...).
        Passing a SQL injection string should be rejected (422).
        """
        mock_auth.return_value = _mock_response(200, USER_42)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1; DROP TABLE characters; --", "user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 422
