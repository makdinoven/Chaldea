"""
Tests for POST /photo/change_location_icon endpoint (FEAT-054).

Covers:
- Success: mock S3 + mock DB, valid admin auth, valid image -> 200
- Invalid MIME type -> 400
- Missing auth token -> 401
- Non-admin user (no photos:upload permission) -> 403
"""

import io
from unittest.mock import patch, MagicMock

from PIL import Image

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _create_test_image(width: int = 100, height: int = 100, fmt: str = "PNG") -> bytes:
    """Create a minimal valid image in memory and return its bytes."""
    img = Image.new("RGBA", (width, height), color=(255, 0, 0, 128))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _fake_file(content: bytes = None, filename: str = "icon.png", content_type: str = "image/png"):
    """Return a file tuple suitable for multipart upload."""
    if content is None:
        content = _create_test_image()
    return ("file", (filename, io.BytesIO(content), content_type))


ADMIN_HEADERS = {"Authorization": "Bearer admin-token"}

ADMIN_USER_RESPONSE = {
    "id": 1,
    "username": "admin",
    "role": "admin",
    "permissions": ["photos:upload", "photos:delete"],
}

REGULAR_USER_RESPONSE = {
    "id": 2,
    "username": "user",
    "role": "user",
    "permissions": [],
}


# ===========================================================================
# Auth tests for POST /photo/change_location_icon
# ===========================================================================

class TestChangeLocationIconAuth:
    """Auth tests for POST /photo/change_location_icon."""

    def test_missing_token_returns_401(self, client):
        """No Authorization header -> 401."""
        response = client.post(
            "/photo/change_location_icon",
            data={"location_id": "1"},
            files=[_fake_file()],
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        """Valid token but role=user (no photos:upload permission) -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.post(
            "/photo/change_location_icon",
            data={"location_id": "1"},
            files=[_fake_file()],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get, client):
        """User-service returns 401 for bad token -> 401."""
        mock_get.return_value = _mock_response(401)
        response = client.post(
            "/photo/change_location_icon",
            data={"location_id": "1"},
            files=[_fake_file()],
            headers={"Authorization": "Bearer bad-token"},
        )
        assert response.status_code == 401


# ===========================================================================
# MIME validation for POST /photo/change_location_icon
# ===========================================================================

class TestChangeLocationIconMime:
    """MIME type validation for location icon upload."""

    @patch("auth_http.requests.get")
    def test_invalid_mime_type_returns_400(self, mock_auth, client):
        """Non-image MIME type (text/plain) -> 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_location_icon",
            data={"location_id": "1"},
            files=[_fake_file(image_bytes, filename="icon.txt", content_type="text/plain")],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400

    @patch("auth_http.requests.get")
    def test_pdf_mime_type_returns_400(self, mock_auth, client):
        """application/pdf -> 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.post(
            "/photo/change_location_icon",
            data={"location_id": "1"},
            files=[_fake_file(b"not an image", filename="doc.pdf", content_type="application/pdf")],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400


# ===========================================================================
# Success case for POST /photo/change_location_icon
# ===========================================================================

class TestChangeLocationIconSuccess:
    """Success case: valid auth, valid image -> 200 with map_icon_url."""

    @patch("main.update_location_icon")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/location_icons/icon.webp")
    @patch("auth_http.requests.get")
    def test_upload_success(self, mock_auth, mock_s3, mock_db, client):
        """Admin uploads valid PNG -> 200 with correct response."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        image_bytes = _create_test_image(fmt="PNG")

        response = client.post(
            "/photo/change_location_icon",
            data={"location_id": "1"},
            files=[_fake_file(image_bytes, filename="icon.png", content_type="image/png")],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert "map_icon_url" in data
        assert data["map_icon_url"] == "https://s3.example.com/location_icons/icon.webp"
        assert data["message"] == "Иконка локации успешно загружена"

    @patch("main.update_location_icon")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/location_icons/icon.webp")
    @patch("auth_http.requests.get")
    def test_upload_calls_s3_with_correct_subdirectory(self, mock_auth, mock_s3, mock_db, client):
        """Verify S3 upload uses subdirectory='location_icons'."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        image_bytes = _create_test_image(fmt="PNG")

        client.post(
            "/photo/change_location_icon",
            data={"location_id": "5"},
            files=[_fake_file(image_bytes, filename="icon.png", content_type="image/png")],
            headers=ADMIN_HEADERS,
        )
        # Verify upload_file_to_s3 was called with subdirectory="location_icons"
        mock_s3.assert_called_once()
        call_kwargs = mock_s3.call_args
        # upload_file_to_s3(data, filename, subdirectory=..., content_type=...)
        assert call_kwargs[1].get("subdirectory") == "location_icons" or \
               (len(call_kwargs[0]) >= 3 and call_kwargs[0][2] == "location_icons") or \
               "location_icons" in str(call_kwargs)

    @patch("main.update_location_icon")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/location_icons/icon.webp")
    @patch("auth_http.requests.get")
    def test_upload_calls_update_location_icon(self, mock_auth, mock_s3, mock_db, client):
        """Verify update_location_icon CRUD is called with correct args."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        image_bytes = _create_test_image(fmt="PNG")

        client.post(
            "/photo/change_location_icon",
            data={"location_id": "7"},
            files=[_fake_file(image_bytes, filename="icon.png", content_type="image/png")],
            headers=ADMIN_HEADERS,
        )
        mock_db.assert_called_once()
        call_args = mock_db.call_args[0]
        # update_location_icon(db, location_id, icon_url)
        assert call_args[1] == 7  # location_id
        assert call_args[2] == "https://s3.example.com/location_icons/icon.webp"
