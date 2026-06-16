"""
Integration tests for POST /photo/change_group_avatar endpoint (FEAT-135).

Covers: success (mocked S3 + DB + auth), participation 403, non-group 400,
auth 401.
"""

import io
from unittest.mock import patch, MagicMock

from PIL import Image


def _create_test_image(width: int = 64, height: int = 64, fmt: str = "PNG") -> bytes:
    img = Image.new("RGB", (width, height), color=(0, 128, 255))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _multipart_file(content: bytes, filename: str = "avatar.png", content_type: str = "image/png"):
    return ("file", (filename, io.BytesIO(content), content_type))


def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


AUTH_HEADERS = {"Authorization": "Bearer valid-token"}
USER_42 = {"id": 42, "username": "testuser", "role": "user"}
S3_URL = "https://s3.example.com/bucket/group_avatars/group_avatar.webp"


class TestGroupAvatarUpload:

    @patch("main.validate_image_mime")
    @patch("main.convert_to_webp", return_value=MagicMock(extension="webp", content_type="image/webp"))
    @patch("main.update_conversation_avatar")
    @patch("main.upload_file_to_s3", return_value=S3_URL)
    @patch("main.get_conversation_type", return_value="group")
    @patch("main.is_conversation_participant", return_value=True)
    @patch("auth_http.requests.get")
    def test_upload_returns_200(self, mock_auth, mock_part, mock_type, mock_s3, mock_db, mock_convert, mock_validate, client):
        mock_auth.return_value = _mock_response(200, USER_42)
        resp = client.post(
            "/photo/change_group_avatar",
            data={"conversation_id": "5"},
            files=[_multipart_file(_create_test_image())],
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["avatar_url"] == S3_URL
        mock_s3.assert_called_once()
        mock_db.assert_called_once()

    @patch("main.is_conversation_participant", return_value=False)
    @patch("auth_http.requests.get")
    def test_non_participant_returns_403(self, mock_auth, mock_part, client):
        mock_auth.return_value = _mock_response(200, USER_42)
        resp = client.post(
            "/photo/change_group_avatar",
            data={"conversation_id": "5"},
            files=[_multipart_file(_create_test_image())],
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 403

    @patch("main.get_conversation_type", return_value="direct")
    @patch("main.is_conversation_participant", return_value=True)
    @patch("auth_http.requests.get")
    def test_direct_conversation_returns_400(self, mock_auth, mock_part, mock_type, client):
        mock_auth.return_value = _mock_response(200, USER_42)
        resp = client.post(
            "/photo/change_group_avatar",
            data={"conversation_id": "5"},
            files=[_multipart_file(_create_test_image())],
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 400

    def test_missing_token_returns_401(self, client):
        resp = client.post(
            "/photo/change_group_avatar",
            data={"conversation_id": "5"},
            files=[_multipart_file(_create_test_image())],
        )
        assert resp.status_code == 401
