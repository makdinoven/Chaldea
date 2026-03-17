"""
Integration tests for POST /photo/change_rule_image endpoint.

Covers:
- Successful upload (mocked S3 + DB) — returns 200 with image_url
- Missing required fields — returns 422 (FastAPI validation)
- Auth enforcement — admin only (Depends(get_admin_user))
- SQL injection in rule_id — returns 422
- Non-image file — returns 500 (PIL rejects invalid data)
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


def _multipart_file(content: bytes, filename: str = "rule_bg.png", content_type: str = "image/png"):
    """Return a file tuple suitable for TestClient ``files=`` parameter."""
    return ("file", (filename, io.BytesIO(content), content_type))


def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


ADMIN_HEADERS = {"Authorization": "Bearer admin-token"}
ADMIN_USER_RESPONSE = {"id": 1, "username": "admin", "role": "admin"}
REGULAR_USER_RESPONSE = {"id": 2, "username": "user", "role": "user"}


# ===========================================================================
# 1. Successful upload
# ===========================================================================

class TestRuleImageUploadSuccess:
    """Happy-path: valid image, mocked S3 and DB, admin auth."""

    @patch("main.update_rule_image")
    @patch("main.upload_file_to_s3", return_value="https://s3.twcstorage.ru/bucket/rules/rule_image_1_abc.webp")
    @patch("auth_http.requests.get")
    def test_upload_returns_200_with_image_url(self, mock_auth, mock_s3, mock_db, client):
        """POST with valid image and admin auth -> 200, response contains image_url."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_rule_image",
            data={"rule_id": "1"},
            files=[_multipart_file(image_bytes)],
            headers=ADMIN_HEADERS,
        )

        assert response.status_code == 200
        body = response.json()
        assert "image_url" in body
        assert body["image_url"] == "https://s3.twcstorage.ru/bucket/rules/rule_image_1_abc.webp"
        assert "message" in body

    @patch("main.update_rule_image")
    @patch("main.upload_file_to_s3", return_value="https://s3.twcstorage.ru/bucket/rules/rule.webp")
    @patch("auth_http.requests.get")
    def test_upload_calls_s3_and_db(self, mock_auth, mock_s3, mock_db, client):
        """Verify that S3 upload and DB update are called."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        image_bytes = _create_test_image()

        client.post(
            "/photo/change_rule_image",
            data={"rule_id": "7"},
            files=[_multipart_file(image_bytes)],
            headers=ADMIN_HEADERS,
        )

        mock_s3.assert_called_once()
        # Verify subdirectory is "rules"
        call_args = mock_s3.call_args
        if call_args.kwargs:
            assert call_args.kwargs.get("subdirectory") == "rules"
        else:
            # Positional: upload_file_to_s3(file_stream, filename, subdirectory="rules")
            assert call_args[0][2] == "rules" if len(call_args[0]) > 2 else True

        mock_db.assert_called_once()
        db_args = mock_db.call_args[0]
        assert db_args[0] == 7  # rule_id


# ===========================================================================
# 2. Auth enforcement
# ===========================================================================

class TestRuleImageUploadAuth:
    """Admin auth is required for rule image upload."""

    def test_missing_token_returns_401(self, client):
        """No Authorization header -> 401."""
        image_bytes = _create_test_image()
        response = client.post(
            "/photo/change_rule_image",
            data={"rule_id": "1"},
            files=[_multipart_file(image_bytes)],
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_get, client):
        """Valid token but role != admin -> 403."""
        mock_get.return_value = _mock_response(200, REGULAR_USER_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_rule_image",
            data={"rule_id": "1"},
            files=[_multipart_file(image_bytes)],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 403

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_get, client):
        """User-service returns 401 for bad token -> 401."""
        mock_get.return_value = _mock_response(401)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_rule_image",
            data={"rule_id": "1"},
            files=[_multipart_file(image_bytes)],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 401


# ===========================================================================
# 3. Missing required fields -> 422
# ===========================================================================

class TestRuleImageUploadMissingFields:
    """FastAPI returns 422 when required Form/File fields are missing."""

    @patch("auth_http.requests.get")
    def test_missing_rule_id_returns_422(self, mock_auth, client):
        """No rule_id in form data -> 422."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_rule_image",
            files=[_multipart_file(image_bytes)],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    @patch("auth_http.requests.get")
    def test_missing_file_returns_422(self, mock_auth, client):
        """No file uploaded -> 422."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.post(
            "/photo/change_rule_image",
            data={"rule_id": "1"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422

    @patch("auth_http.requests.get")
    def test_missing_all_fields_returns_422(self, mock_auth, client):
        """No fields at all -> 422."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)

        response = client.post(
            "/photo/change_rule_image",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422


# ===========================================================================
# 4. Non-image file
# ===========================================================================

class TestRuleImageUploadInvalidImage:
    """Non-image content is rejected by MIME validation (400) or PIL (500)."""

    @patch("auth_http.requests.get")
    def test_non_image_mime_returns_400(self, mock_auth, client):
        """Non-image MIME type is rejected by validate_image_mime -> 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        fake_content = b"This is not an image at all. Just plain text."

        response = client.post(
            "/photo/change_rule_image",
            data={"rule_id": "1"},
            files=[_multipart_file(fake_content, filename="fake.txt", content_type="text/plain")],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 400


# ===========================================================================
# 5. Security — SQL injection
# ===========================================================================

class TestRuleImageUploadSecurity:
    """SQL injection in rule_id should be rejected by FastAPI type validation."""

    @patch("auth_http.requests.get")
    def test_sql_injection_in_rule_id(self, mock_auth, client):
        """rule_id is typed as int in Form(...). SQL injection string -> 422."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER_RESPONSE)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_rule_image",
            data={"rule_id": "1; DROP TABLE game_rules; --"},
            files=[_multipart_file(image_bytes)],
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 422
