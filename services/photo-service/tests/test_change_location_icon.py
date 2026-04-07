"""
Tests for POST /photo/change_location_icon replacement behavior (FEAT-119).

Covers:
- Success with existing old map_icon_url -> delete_s3_file called once with old URL
- Old URL is NULL -> delete_s3_file NOT called
- delete_s3_file raises -> endpoint still returns 200 with new URL (non-blocking)
- Unauthorized (no photos:upload permission) -> 403
"""

import io
from unittest.mock import patch, MagicMock

from PIL import Image


def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


def _create_test_image(fmt: str = "PNG") -> bytes:
    img = Image.new("RGB", (100, 100), color=(255, 64, 32))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _fake_file(content: bytes = None, filename: str = "icon.png", content_type: str = "image/png"):
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

NEW_URL = "https://s3.example.com/location_icons/new_icon.webp"
OLD_URL = "https://s3.example.com/location_icons/old_icon.webp"


class TestChangeLocationIconReplacement:
    """FEAT-119 replacement behavior."""

    @patch("main.delete_s3_file")
    @patch("main.update_location_icon")
    @patch("main.get_location_map_icon_url", return_value=OLD_URL)
    @patch("main.upload_file_to_s3", return_value=NEW_URL)
    @patch("auth_http.requests.get")
    def test_success_with_old_url_deletes_old_file(
        self, mock_auth, mock_s3, mock_get_old, mock_update, mock_delete, client
    ):
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.post(
            "/photo/change_location_icon",
            data={"location_id": "7"},
            files=[_fake_file()],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["map_icon_url"] == NEW_URL
        mock_update.assert_called_once()
        mock_delete.assert_called_once_with(OLD_URL)

    @patch("main.delete_s3_file")
    @patch("main.update_location_icon")
    @patch("main.get_location_map_icon_url", return_value=None)
    @patch("main.upload_file_to_s3", return_value=NEW_URL)
    @patch("auth_http.requests.get")
    def test_null_old_url_does_not_call_delete(
        self, mock_auth, mock_s3, mock_get_old, mock_update, mock_delete, client
    ):
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.post(
            "/photo/change_location_icon",
            data={"location_id": "7"},
            files=[_fake_file()],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["map_icon_url"] == NEW_URL
        mock_delete.assert_not_called()

    @patch("main.delete_s3_file", side_effect=RuntimeError("S3 boom"))
    @patch("main.update_location_icon")
    @patch("main.get_location_map_icon_url", return_value=OLD_URL)
    @patch("main.upload_file_to_s3", return_value=NEW_URL)
    @patch("auth_http.requests.get")
    def test_delete_failure_is_non_blocking(
        self, mock_auth, mock_s3, mock_get_old, mock_update, mock_delete, client
    ):
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.post(
            "/photo/change_location_icon",
            data={"location_id": "7"},
            files=[_fake_file()],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["map_icon_url"] == NEW_URL
        mock_update.assert_called_once()
        mock_delete.assert_called_once_with(OLD_URL)

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_auth, client):
        mock_auth.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        response = client.post(
            "/photo/change_location_icon",
            data={"location_id": "7"},
            files=[_fake_file()],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403
