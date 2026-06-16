"""
Tests for POST /photo/upload_chat_image (FEAT-137).
Uploads a message image to S3 and returns the URL (no DB write).
"""

import io
from unittest.mock import patch, MagicMock

from PIL import Image


def _img() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 200, 10)).save(buf, format="PNG")
    return buf.getvalue()


def _file(content: bytes, name="img.png", ct="image/png"):
    return ("file", (name, io.BytesIO(content), ct))


def _resp(code, data=None):
    r = MagicMock()
    r.status_code = code
    r.json.return_value = data or {}
    return r


AUTH = {"Authorization": "Bearer valid-token"}
USER = {"id": 7, "username": "u", "role": "user"}
URL = "https://s3.example.com/bucket/chat_images/chat_image.webp"


class TestChatImageUpload:

    @patch("main.validate_image_mime")
    @patch("main.convert_to_webp", return_value=MagicMock(extension="webp", content_type="image/webp"))
    @patch("main.upload_file_to_s3", return_value=URL)
    @patch("auth_http.requests.get")
    def test_upload_returns_url(self, mock_auth, mock_s3, mock_conv, mock_val, client):
        mock_auth.return_value = _resp(200, USER)
        resp = client.post("/photo/upload_chat_image", files=[_file(_img())], headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["image_url"] == URL
        mock_s3.assert_called_once()

    def test_missing_token_401(self, client):
        resp = client.post("/photo/upload_chat_image", files=[_file(_img())])
        assert resp.status_code == 401
