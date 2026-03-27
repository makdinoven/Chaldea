"""
Integration tests for POST /photo/upload_ticket_attachment endpoint.

Covers:
- Successful upload (mocked S3 + image conversion) — returns 200 with image_url
- Invalid MIME type — returns 400
- Unauthenticated request (no token) — returns 401
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


AUTH_HEADERS = {"Authorization": "Bearer valid-token"}
USER_RESPONSE = {"id": 1, "username": "player", "role": "user", "permissions": []}


# ===========================================================================
# 1. Successful upload
# ===========================================================================

class TestTicketAttachmentUploadSuccess:
    """Happy-path: valid image, mocked S3, authenticated user."""

    @patch("main.upload_file_to_s3", return_value="https://s3.twcstorage.ru/bucket/ticket_attachments/ticket_abc_123.webp")
    @patch("auth_http.requests.get")
    def test_upload_returns_200_with_image_url(self, mock_auth, mock_s3, client):
        """POST with valid image and authorized user -> 200, response contains image_url."""
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/upload_ticket_attachment",
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        body = response.json()
        assert "image_url" in body
        assert body["image_url"] == "https://s3.twcstorage.ru/bucket/ticket_attachments/ticket_abc_123.webp"

    @patch("main.upload_file_to_s3", return_value="https://s3.twcstorage.ru/bucket/ticket_attachments/ticket_test.webp")
    @patch("auth_http.requests.get")
    def test_upload_calls_s3_with_ticket_attachments_subdirectory(self, mock_auth, mock_s3, client):
        """Verify that S3 upload is called with subdirectory='ticket_attachments'."""
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        image_bytes = _create_test_image()

        client.post(
            "/photo/upload_ticket_attachment",
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )

        mock_s3.assert_called_once()
        call_kwargs = mock_s3.call_args.kwargs
        if call_kwargs:
            assert call_kwargs.get("subdirectory") == "ticket_attachments"
        else:
            # Positional args: upload_file_to_s3(data, filename, subdirectory, content_type)
            call_args = mock_s3.call_args[0]
            assert "ticket_attachments" in call_args

    @patch("main.upload_file_to_s3", return_value="https://s3.twcstorage.ru/bucket/ticket_attachments/ticket_test.webp")
    @patch("auth_http.requests.get")
    def test_upload_response_has_only_image_url(self, mock_auth, mock_s3, client):
        """Ticket attachment upload returns only image_url, no other fields."""
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/upload_ticket_attachment",
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )

        body = response.json()
        assert list(body.keys()) == ["image_url"]


# ===========================================================================
# 2. Invalid MIME type -> 400
# ===========================================================================

class TestTicketAttachmentInvalidMime:
    """Non-image content is rejected by validate_image_mime -> 400."""

    @patch("auth_http.requests.get")
    def test_non_image_mime_returns_400(self, mock_auth, client):
        """Non-image MIME type (text/plain) -> 400."""
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        fake_content = b"This is not an image at all. Just plain text."

        response = client.post(
            "/photo/upload_ticket_attachment",
            files=[_multipart_file(fake_content, filename="fake.txt", content_type="text/plain")],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 400

    @patch("auth_http.requests.get")
    def test_pdf_mime_returns_400(self, mock_auth, client):
        """PDF MIME type -> 400."""
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        fake_content = b"%PDF-1.4 fake pdf content"

        response = client.post(
            "/photo/upload_ticket_attachment",
            files=[_multipart_file(fake_content, filename="doc.pdf", content_type="application/pdf")],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 400


# ===========================================================================
# 3. Unauthenticated request -> 401
# ===========================================================================

class TestTicketAttachmentUnauthenticated:
    """Missing or invalid auth token returns 401."""

    def test_missing_token_returns_401(self, client):
        """No Authorization header -> 401."""
        image_bytes = _create_test_image()
        response = client.post(
            "/photo/upload_ticket_attachment",
            files=[_multipart_file(image_bytes)],
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_auth, client):
        """User-service returns 401 for bad token -> 401."""
        mock_auth.return_value = _mock_response(401)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/upload_ticket_attachment",
            files=[_multipart_file(image_bytes)],
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401
