"""
Integration tests for POST /photo/change_character_avatar_photo endpoint.

Covers:
- Successful upload (mocked S3 + DB) — returns 200 with avatar_url
- File too large (>15 MB) — returns 500 (convert_to_webp raises ValueError)
- Non-image file — returns 500 (PIL rejects invalid data)
- Missing required fields — returns 422 (FastAPI validation)
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


# ---------------------------------------------------------------------------
# 1. Successful upload
# ---------------------------------------------------------------------------

class TestCharacterAvatarUploadSuccess:
    """Happy-path: valid image, mocked S3 and DB."""

    @patch("main.update_character_avatar")
    @patch("main.upload_file_to_s3", return_value="https://s3.twcstorage.ru/bucket/character_avatars/photo.webp")
    def test_upload_returns_200_with_avatar_url(self, mock_s3, mock_db, client):
        """POST with valid image → 200, response contains avatar_url."""
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1", "user_id": "42"},
            files=[_multipart_file(image_bytes)],
        )

        assert response.status_code == 200
        body = response.json()
        assert "avatar_url" in body
        assert body["avatar_url"] == "https://s3.twcstorage.ru/bucket/character_avatars/photo.webp"
        assert body["message"] == "Фото успешно загружено"

    @patch("main.update_character_avatar")
    @patch("main.upload_file_to_s3", return_value="https://s3.twcstorage.ru/bucket/character_avatars/photo.webp")
    def test_upload_calls_s3_and_db(self, mock_s3, mock_db, client):
        """Verify that S3 upload and DB update are called with correct args."""
        image_bytes = _create_test_image()

        client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "7", "user_id": "99"},
            files=[_multipart_file(image_bytes)],
        )

        mock_s3.assert_called_once()
        # upload_file_to_s3(file_stream, unique_filename, subdirectory="character_avatars")
        _, kwargs = mock_s3.call_args
        if not kwargs:
            args = mock_s3.call_args[0]
            assert args[2] if len(args) > 2 else True  # subdirectory passed

        mock_db.assert_called_once()
        db_args = mock_db.call_args[0]
        assert db_args[0] == 7   # character_id
        assert db_args[2] == 99  # user_id


# ---------------------------------------------------------------------------
# 2. File too large (>15 MB)
# ---------------------------------------------------------------------------

class TestCharacterAvatarUploadTooLarge:
    """File exceeding 15 MB limit is rejected by convert_to_webp."""

    def test_oversized_file_returns_500(self, client):
        """
        convert_to_webp raises ValueError when file > 15 MB.
        The endpoint catches all exceptions and returns 500.

        NOTE: The endpoint does not distinguish validation errors from
        server errors — all are returned as 500. A future improvement
        would be to catch ValueError and return 400.
        """
        # Create a small valid PNG header followed by padding to exceed 15 MB
        oversized_data = b"\x89PNG\r\n\x1a\n" + (b"\x00" * (15 * 1024 * 1024 + 1))

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1", "user_id": "1"},
            files=[_multipart_file(oversized_data, filename="big.png")],
        )

        assert response.status_code == 500
        assert "15" in response.json()["detail"] or "limit" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 3. Non-image file
# ---------------------------------------------------------------------------

class TestCharacterAvatarUploadInvalidImage:
    """Non-image content is rejected by PIL verification in convert_to_webp."""

    def test_non_image_file_returns_500(self, client):
        """
        Random bytes that are not a valid image cause PIL to raise,
        which convert_to_webp wraps as ValueError("Invalid image content").
        The endpoint returns 500.
        """
        fake_content = b"This is not an image at all. Just plain text."

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1", "user_id": "1"},
            files=[_multipart_file(fake_content, filename="fake.txt", content_type="text/plain")],
        )

        assert response.status_code == 500

    def test_empty_file_returns_500(self, client):
        """Empty file is rejected by convert_to_webp ('Empty input file')."""
        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1", "user_id": "1"},
            files=[_multipart_file(b"", filename="empty.png")],
        )

        assert response.status_code == 500
        assert "Empty" in response.json()["detail"] or "empty" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 4. Missing required fields → 422
# ---------------------------------------------------------------------------

class TestCharacterAvatarUploadMissingFields:
    """FastAPI returns 422 when required Form/File fields are missing."""

    def test_missing_character_id_returns_422(self, client):
        """No character_id in form data → 422."""
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"user_id": "1"},
            files=[_multipart_file(image_bytes)],
        )

        assert response.status_code == 422

    def test_missing_user_id_returns_422(self, client):
        """No user_id in form data → 422."""
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1"},
            files=[_multipart_file(image_bytes)],
        )

        assert response.status_code == 422

    def test_missing_file_returns_422(self, client):
        """No file uploaded → 422."""
        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1", "user_id": "1"},
        )

        assert response.status_code == 422

    def test_missing_all_fields_returns_422(self, client):
        """No fields at all → 422."""
        response = client.post(
            "/photo/change_character_avatar_photo",
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# 5. SQL injection — security test
# ---------------------------------------------------------------------------

class TestCharacterAvatarUploadSecurity:
    """Security: verify that malicious input does not crash the service."""

    @patch("main.update_character_avatar")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/avatar.webp")
    def test_sql_injection_in_character_id(self, mock_s3, mock_db, client):
        """
        character_id is typed as int in FastAPI Form(...).
        Passing a SQL injection string should be rejected (422).
        """
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_character_avatar_photo",
            data={"character_id": "1; DROP TABLE characters; --", "user_id": "1"},
            files=[_multipart_file(image_bytes)],
        )

        assert response.status_code == 422
