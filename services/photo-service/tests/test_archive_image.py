"""
Integration tests for POST /photo/upload_archive_image endpoint.

Covers:
- Successful upload (mocked S3 + image conversion) — returns 200 with image_url
- Invalid MIME type — returns 400
- Missing file — returns 422
- Unauthorized (no token) — returns 401
- No permission (valid token, missing photos:upload) — returns 403
"""

import io
from unittest.mock import patch, MagicMock

from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_image(width: int = 100, height: int = 100, fmt: str = "PNG") -> bytes:
    """Create a minimal valid image in memory and return its bytes."""
    img = Image.new("RGB", (width, height), color=(0, 128, 255))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _multipart_file(content: bytes, filename: str = "test.png", content_type: str = "image/png"):
    """Return a file tuple suitable for TestClient ``files=`` parameter."""
    return ("file", (filename, io.BytesIO(content), content_type))


def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


ADMIN_HEADERS = {"Authorization": "Bearer admin-token"}
ADMIN_USER_RESPONSE = {"id": 1, "username": "admin", "role": "admin", "permissions": [
    "photos:upload", "photos:delete",
]}
USER_NO_PERMISSION_RESPONSE = {"id": 2, "username": "editor", "role": "editor", "permissions": []}


# ===========================================================================
# 1. Successful upload
# ===========================================================================

class TestArchiveImageUploadSuccess:
    """Happy-path: valid image, mocked S3, admin auth with photos:upload permission."""

    @patch("main.upload_file_to_s3", return_value="https://s3.twcstorage.ru/bucket/archive_images/archive_abc_123.webp")
    @patch("auth_http.requests.get")
    def test_upload_returns_200_with_image_url(self, mock_auth, mock_s3, client):
        """POST with valid image and authorized user -> 200, response contains image_url."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/upload_archive_image",
            files=[_multipart_file(image_bytes)],
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 200
        body = response.json()
        assert "image_url" in body
        assert body["image_url"] == "https://s3.twcstorage.ru/bucket/archive_images/archive_abc_123.webp"

    @patch("main.upload_file_to_s3", return_value="https://s3.twcstorage.ru/bucket/archive_images/archive_test.webp")
    @patch("auth_http.requests.get")
    def test_upload_calls_s3_with_archive_images_subdirectory(self, mock_auth, mock_s3, client):
        """Verify that S3 upload is called with subdirectory='archive_images'."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        image_bytes = _create_test_image()

        client.post(
            "/photo/upload_archive_image",
            files=[_multipart_file(image_bytes)],
            headers=ADMIN_HEADERS,
        )

        mock_s3.assert_called_once()
        call_kwargs = mock_s3.call_args.kwargs
        if call_kwargs:
            assert call_kwargs.get("subdirectory") == "archive_images"
        else:
            # Positional args: upload_file_to_s3(data, filename, subdirectory, content_type)
            call_args = mock_s3.call_args[0]
            assert "archive_images" in call_args

    @patch("main.upload_file_to_s3", return_value="https://s3.twcstorage.ru/bucket/archive_images/archive_test.webp")
    @patch("auth_http.requests.get")
    def test_upload_response_has_no_db_fields(self, mock_auth, mock_s3, client):
        """Archive image upload returns only image_url, no message or other fields."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/upload_archive_image",
            files=[_multipart_file(image_bytes)],
            headers=ADMIN_HEADERS,
        )

        body = response.json()
        assert list(body.keys()) == ["image_url"]


# ===========================================================================
# 2. Invalid MIME type
# ===========================================================================

class TestArchiveImageUploadInvalidMime:
    """Non-image content is rejected by validate_image_mime -> 400."""

    @patch("auth_http.requests.get")
    def test_non_image_mime_returns_400(self, mock_auth, client):
        """Non-image MIME type (text/plain) -> 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        fake_content = b"This is not an image at all. Just plain text."

        response = client.post(
            "/photo/upload_archive_image",
            files=[_multipart_file(fake_content, filename="fake.txt", content_type="text/plain")],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("auth_http.requests.get")
    def test_pdf_mime_returns_400(self, mock_auth, client):
        """PDF MIME type -> 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        fake_content = b"%PDF-1.4 fake pdf content"

        response = client.post(
            "/photo/upload_archive_image",
            files=[_multipart_file(fake_content, filename="doc.pdf", content_type="application/pdf")],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400


# ===========================================================================
# 3. Missing file -> 422
# ===========================================================================

class TestArchiveImageUploadMissingFile:
    """FastAPI returns 422 when required File field is missing."""

    @patch("auth_http.requests.get")
    def test_missing_file_returns_422(self, mock_auth, client):
        """No file in request -> 422."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.post(
            "/photo/upload_archive_image",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422


# ===========================================================================
# 4. Unauthorized (no token) -> 401
# ===========================================================================

class TestArchiveImageUploadUnauthorized:
    """Missing or invalid auth token returns 401."""

    def test_missing_token_returns_401(self, client):
        """No Authorization header -> 401."""
        image_bytes = _create_test_image()
        response = client.post(
            "/photo/upload_archive_image",
            files=[_multipart_file(image_bytes)],
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_auth, client):
        """User-service returns 401 for bad token -> 401."""
        mock_auth.return_value = _mock_response(401)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/upload_archive_image",
            files=[_multipart_file(image_bytes)],
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401


# ===========================================================================
# 5. No permission -> 403
# ===========================================================================

class TestArchiveImageUploadNoPermission:
    """Valid token but missing photos:upload permission returns 403."""

    @patch("auth_http.requests.get")
    def test_no_permission_returns_403(self, mock_auth, client):
        """Authenticated user without photos:upload permission -> 403."""
        mock_auth.return_value = _mock_response(200, USER_NO_PERMISSION_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/upload_archive_image",
            files=[_multipart_file(image_bytes)],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403
