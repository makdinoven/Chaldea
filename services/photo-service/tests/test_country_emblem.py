"""
Tests for POST /photo/change_country_emblem endpoint (photo-service).

Covers:
- Successful upload (mocked S3 + DB + auth) — returns 200 with emblem_url
- Invalid MIME type — returns 400
- Missing auth token — returns 401
- Missing required fields — returns 422
- SQL injection in country_id — returns 422
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


def _multipart_file(content: bytes, filename: str = "emblem.png", content_type: str = "image/png"):
    """Return a file tuple suitable for TestClient ``files=`` parameter."""
    return ("file", (filename, io.BytesIO(content), content_type))


def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


AUTH_HEADERS = {"Authorization": "Bearer valid-token"}
ADMIN_USER = {
    "id": 1,
    "username": "admin",
    "role": "admin",
    "permissions": ["photos:upload"],
}
USER_NO_PERM = {
    "id": 2,
    "username": "user",
    "role": "user",
    "permissions": [],
}


# ===========================================================================
# 1. Successful upload
# ===========================================================================

class TestCountryEmblemUploadSuccess:
    """Happy-path: valid image, mocked S3 and DB, correct auth."""

    @patch("main.update_country_emblem")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/media/emblems/country_emblem_5_abc.webp")
    @patch("auth_http.requests.get")
    def test_upload_returns_200_with_emblem_url(self, mock_auth, mock_s3, mock_db, client):
        """POST with valid image + correct auth -> 200, response contains emblem_url."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_country_emblem",
            data={"country_id": "5"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        body = response.json()
        assert "emblem_url" in body
        assert body["emblem_url"] == "https://s3.example.com/media/emblems/country_emblem_5_abc.webp"
        assert body["message"] == "Эмблема страны успешно загружена"

    @patch("main.update_country_emblem")
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/media/emblems/country_emblem_7_xyz.webp")
    @patch("auth_http.requests.get")
    def test_upload_calls_s3_and_db(self, mock_auth, mock_s3, mock_db, client):
        """Verify that S3 upload and DB update are called."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER)
        image_bytes = _create_test_image()

        client.post(
            "/photo/change_country_emblem",
            data={"country_id": "7"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )

        mock_s3.assert_called_once()
        mock_db.assert_called_once()


# ===========================================================================
# 2. Invalid MIME type -> 400
# ===========================================================================

class TestCountryEmblemInvalidMime:
    """Non-image MIME type is rejected by validate_image_mime with 400."""

    @patch("auth_http.requests.get")
    def test_non_image_mime_returns_400(self, mock_auth, client):
        """text/plain MIME type -> 400."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER)
        fake_content = b"This is not an image at all. Just plain text."

        response = client.post(
            "/photo/change_country_emblem",
            data={"country_id": "5"},
            files=[_multipart_file(fake_content, filename="fake.txt", content_type="text/plain")],
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 400


# ===========================================================================
# 3. Auth enforcement
# ===========================================================================

class TestCountryEmblemAuth:
    """Auth checks for country emblem upload."""

    def test_missing_token_returns_401(self, client):
        """No Authorization header -> 401."""
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_country_emblem",
            data={"country_id": "5"},
            files=[_multipart_file(image_bytes)],
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401(self, mock_auth, client):
        """User-service returns 401 for bad token -> 401."""
        mock_auth.return_value = _mock_response(401)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_country_emblem",
            data={"country_id": "5"},
            files=[_multipart_file(image_bytes)],
            headers={"Authorization": "Bearer bad-token"},
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_no_permission_returns_403(self, mock_auth, client):
        """User without photos:upload permission -> 403."""
        mock_auth.return_value = _mock_response(200, USER_NO_PERM)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_country_emblem",
            data={"country_id": "5"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 403


# ===========================================================================
# 4. Missing required fields -> 422
# ===========================================================================

class TestCountryEmblemMissingFields:
    """FastAPI returns 422 when required Form/File fields are missing."""

    @patch("auth_http.requests.get")
    def test_missing_country_id_returns_422(self, mock_auth, client):
        """No country_id in form data -> 422."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_country_emblem",
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 422

    @patch("auth_http.requests.get")
    def test_missing_file_returns_422(self, mock_auth, client):
        """No file uploaded -> 422."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER)

        response = client.post(
            "/photo/change_country_emblem",
            data={"country_id": "5"},
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 422


# ===========================================================================
# 5. Security — SQL injection
# ===========================================================================

class TestCountryEmblemSecurity:
    """Security: verify that malicious input does not crash the service."""

    @patch("auth_http.requests.get")
    def test_sql_injection_in_country_id(self, mock_auth, client):
        """country_id is typed as int. SQL injection string -> 422."""
        mock_auth.return_value = _mock_response(200, ADMIN_USER)
        image_bytes = _create_test_image()

        response = client.post(
            "/photo/change_country_emblem",
            data={"country_id": "1; DROP TABLE Countries; --"},
            files=[_multipart_file(image_bytes)],
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 422
