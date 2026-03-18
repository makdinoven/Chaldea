"""
FEAT-030 Task #8 — Tests for profile background upload/delete endpoints.

Covers:
1. POST /photo/change_profile_background — upload background image
2. DELETE /photo/delete_profile_background — delete background image
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


def _multipart_file(content: bytes, filename: str = "bg.png", content_type: str = "image/png"):
    """Return a file tuple suitable for TestClient ``files=`` parameter."""
    return ("file", (filename, io.BytesIO(content), content_type))


def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


AUTH_HEADERS = {"Authorization": "Bearer test-token"}
USER_RESPONSE = {"id": 42, "username": "testuser", "role": "user"}
OTHER_USER_RESPONSE = {"id": 99, "username": "otheruser", "role": "user"}
S3_BG_URL = "https://s3.example.com/bucket/profile_backgrounds/profile_bg_42_abc.webp"


# ===========================================================================
# 1. POST /photo/change_profile_background
# ===========================================================================

class TestUploadProfileBackground:

    @patch("main.update_profile_bg_image")
    @patch("main.upload_file_to_s3", return_value=S3_BG_URL)
    @patch("main.get_profile_bg_image", return_value=None)
    @patch("auth_http.requests.get")
    def test_upload_background_success(self, mock_auth, mock_get_bg, mock_s3, mock_db, client):
        """Successful upload: mock S3 + crud, verify response."""
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_profile_background",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Фон профиля успешно загружен"
        assert data["profile_bg_image"] == S3_BG_URL
        mock_s3.assert_called_once()
        mock_db.assert_called_once_with(42, S3_BG_URL)

    @patch("main.update_profile_bg_image")
    @patch("main.upload_file_to_s3", return_value=S3_BG_URL)
    @patch("main.delete_s3_file")
    @patch("main.get_profile_bg_image", return_value="https://s3.example.com/old_bg.webp")
    @patch("auth_http.requests.get")
    def test_upload_background_replaces_old(self, mock_auth, mock_get_bg, mock_del_s3, mock_s3, mock_db, client):
        """When old background exists, it should be deleted from S3 before uploading new one."""
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_profile_background",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        mock_del_s3.assert_called_once_with("https://s3.example.com/old_bg.webp")

    @patch("auth_http.requests.get")
    def test_upload_background_invalid_mime(self, mock_auth, client):
        """Non-image file should be rejected with 400."""
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)

        response = client.post(
            "/photo/change_profile_background",
            data={"user_id": "42"},
            files=[_multipart_file(b"not an image", filename="doc.pdf", content_type="application/pdf")],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 400
        assert "формат" in response.json()["detail"].lower() or "Разрешены" in response.json()["detail"]

    @patch("auth_http.requests.get")
    def test_upload_background_wrong_user(self, mock_auth, client):
        """user_id != current_user.id should return 403."""
        mock_auth.return_value = _mock_response(200, OTHER_USER_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_profile_background",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 403

    def test_upload_background_unauthenticated(self, client):
        """No/invalid token should return 401."""
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_profile_background",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes)],
            # No Authorization header
        )
        assert response.status_code in (401, 403)

    @patch("auth_http.requests.get")
    def test_upload_background_invalid_token(self, mock_auth, client):
        """Invalid token (auth service returns non-200) should return 401."""
        mock_auth.return_value = _mock_response(401, {"detail": "Invalid"})
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_profile_background",
            data={"user_id": "42"},
            files=[_multipart_file(image_bytes)],
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_upload_background_svg_rejected(self, mock_auth, client):
        """SVG MIME type is not in allowlist."""
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        svg_content = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'

        response = client.post(
            "/photo/change_profile_background",
            data={"user_id": "42"},
            files=[_multipart_file(svg_content, filename="bg.svg", content_type="image/svg+xml")],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 400


# ===========================================================================
# 2. DELETE /photo/delete_profile_background
# ===========================================================================

class TestDeleteProfileBackground:

    @patch("main.update_profile_bg_image")
    @patch("main.delete_s3_file")
    @patch("main.get_profile_bg_image", return_value=S3_BG_URL)
    @patch("auth_http.requests.get")
    def test_delete_background_success(self, mock_auth, mock_get_bg, mock_del_s3, mock_db, client):
        """Successful delete: verify S3 file deleted and DB updated."""
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)

        response = client.delete(
            "/photo/delete_profile_background",
            params={"user_id": 42},
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Фон профиля успешно удалён"
        mock_del_s3.assert_called_once_with(S3_BG_URL)
        mock_db.assert_called_once_with(42, None)

    @patch("main.get_profile_bg_image", return_value=None)
    @patch("auth_http.requests.get")
    def test_delete_background_not_set(self, mock_auth, mock_get_bg, client):
        """No background exists — should return 404."""
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)

        response = client.delete(
            "/photo/delete_profile_background",
            params={"user_id": 42},
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 404

    @patch("auth_http.requests.get")
    def test_delete_background_wrong_user(self, mock_auth, client):
        """user_id != current_user.id should return 403."""
        mock_auth.return_value = _mock_response(200, OTHER_USER_RESPONSE)

        response = client.delete(
            "/photo/delete_profile_background",
            params={"user_id": 42},
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 403

    def test_delete_background_unauthenticated(self, client):
        """No token should return 401."""
        response = client.delete(
            "/photo/delete_profile_background",
            params={"user_id": 42},
        )
        assert response.status_code in (401, 403)

    @patch("auth_http.requests.get")
    def test_delete_background_invalid_token(self, mock_auth, client):
        """Invalid token should return 401."""
        mock_auth.return_value = _mock_response(401, {"detail": "Invalid"})

        response = client.delete(
            "/photo/delete_profile_background",
            params={"user_id": 42},
            headers={"Authorization": "Bearer bad-token"},
        )
        assert response.status_code == 401
