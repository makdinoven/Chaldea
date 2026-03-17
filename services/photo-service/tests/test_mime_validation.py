"""
Tests for MIME type validation across photo-service upload endpoints.

Verifies that:
- Non-image MIME types are rejected with 400
- Valid image MIME types (JPEG, PNG, WebP, GIF) are accepted
- Uses change_user_avatar_photo as representative endpoint
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


AUTH_HEADERS = {"Authorization": "Bearer test-token"}
USER_RESPONSE = {"id": 42, "username": "testuser", "role": "user"}
ADMIN_RESPONSE = {"id": 1, "username": "admin", "role": "admin"}


# ===========================================================================
# 1. Rejected MIME types — 400
# ===========================================================================

class TestMimeRejection:
    """Non-image MIME types must be rejected with 400."""

    @patch("auth_http.requests.get")
    def test_text_plain_rejected(self, mock_auth, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_user_avatar_photo",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes, filename="test.txt", content_type="text/plain")],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 400
        assert "формат" in response.json()["detail"].lower() or "Разрешены" in response.json()["detail"]

    @patch("auth_http.requests.get")
    def test_application_pdf_rejected(self, mock_auth, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_user_avatar_photo",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes, filename="doc.pdf", content_type="application/pdf")],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 400

    @patch("auth_http.requests.get")
    def test_application_octet_stream_rejected(self, mock_auth, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_user_avatar_photo",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes, filename="file.bin", content_type="application/octet-stream")],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 400

    @patch("auth_http.requests.get")
    def test_text_html_rejected(self, mock_auth, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_user_avatar_photo",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes, filename="page.html", content_type="text/html")],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 400

    @patch("auth_http.requests.get")
    def test_image_svg_rejected(self, mock_auth, client):
        """SVG is not in the allowlist — must be rejected."""
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        svg_content = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'

        response = client.post(
            "/photo/change_user_avatar_photo",
            data={"user_id": "42"},
            files=[_multipart_file(svg_content, filename="icon.svg", content_type="image/svg+xml")],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 400


# ===========================================================================
# 2. Accepted MIME types — pass validation (mock S3 and DB)
# ===========================================================================

class TestMimeAccepted:
    """Valid image MIME types must pass validation and reach S3 upload."""

    @patch("main.update_user_avatar")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/bucket/user_avatars/photo.webp")
    @patch("auth_http.requests.get")
    def test_image_jpeg_accepted(self, mock_auth, mock_s3, mock_db, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        image_bytes = _create_test_image(fmt="JPEG")

        response = client.post(
            "/photo/change_user_avatar_photo",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes, filename="photo.jpg", content_type="image/jpeg")],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200

    @patch("main.update_user_avatar")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/bucket/user_avatars/photo.webp")
    @patch("auth_http.requests.get")
    def test_image_png_accepted(self, mock_auth, mock_s3, mock_db, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        image_bytes = _create_test_image(fmt="PNG")

        response = client.post(
            "/photo/change_user_avatar_photo",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes, filename="photo.png", content_type="image/png")],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200

    @patch("main.update_user_avatar")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/bucket/user_avatars/photo.webp")
    @patch("auth_http.requests.get")
    def test_image_webp_accepted(self, mock_auth, mock_s3, mock_db, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        image_bytes = _create_test_image(fmt="WEBP")

        response = client.post(
            "/photo/change_user_avatar_photo",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes, filename="photo.webp", content_type="image/webp")],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200

    @patch("main.update_user_avatar")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/bucket/user_avatars/photo.webp")
    @patch("auth_http.requests.get")
    def test_image_gif_accepted(self, mock_auth, mock_s3, mock_db, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        image_bytes = _create_test_image(fmt="GIF")

        response = client.post(
            "/photo/change_user_avatar_photo",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes, filename="photo.gif", content_type="image/gif")],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200


# ===========================================================================
# 3. MIME validation on admin endpoint (change_rule_image) — verify it works there too
# ===========================================================================

class TestMimeValidationOnAdminEndpoint:
    """MIME validation also applies to admin endpoints."""

    @patch("auth_http.requests.get")
    def test_admin_endpoint_rejects_non_image(self, mock_auth, client):
        """Admin endpoint with valid admin auth but bad MIME type -> 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_RESPONSE)

        response = client.post(
            "/photo/change_rule_image",
            data={"rule_id": "1"},
            files=[_multipart_file(b"not an image", filename="doc.pdf", content_type="application/pdf")],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 400
