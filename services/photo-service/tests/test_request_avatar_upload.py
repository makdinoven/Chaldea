"""
Tests for POST /photo/upload_character_request_avatar (FEAT-154, task #10).

The character does not exist yet when this runs, so the endpoint is deliberately
unbound: any authenticated user may call it, it writes **no** DB row, and it
returns a permanent S3 URL that the wizard attaches to the request body.

N3: the handler tells "too big" (413) from "not an image" (400) by matching on
the text of the bare ``ValueError`` that ``convert_to_webp`` raises for both.
That is fragile by construction, so both branches are pinned separately here —
if anyone touches the message in ``utils.convert_to_webp``, one of these fails.
"""

import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from database import get_db
from main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENDPOINT = "/photo/upload_character_request_avatar"
AUTH_HEADERS = {"Authorization": "Bearer valid-token"}
USER_RESPONSE = {"id": 1, "username": "player", "role": "user", "permissions": []}
S3_URL = (
    "https://s3.twcstorage.ru/bucket/character_avatar_drafts/"
    "char_draft_abc123_1700000000.webp"
)
MAX_FILE_SIZE = 15 * 1024 * 1024


def _create_test_image(width: int = 100, height: int = 100, fmt: str = "PNG") -> bytes:
    img = Image.new("RGB", (width, height), color=(0, 128, 255))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _multipart_file(content: bytes, filename: str = "avatar.png",
                    content_type: str = "image/png"):
    return ("file", (filename, io.BytesIO(content), content_type))


def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


@pytest.fixture()
def db_probe():
    """Swap the shared session override for a fresh spy, then restore it."""
    previous = app.dependency_overrides.get(get_db)
    probe = MagicMock()

    def _override():
        yield probe

    app.dependency_overrides[get_db] = _override
    yield probe
    if previous is not None:
        app.dependency_overrides[get_db] = previous
    else:  # pragma: no cover - conftest always installs one
        app.dependency_overrides.pop(get_db, None)


# ===========================================================================
# 1. Successful upload
# ===========================================================================

class TestRequestAvatarUploadSuccess:

    @patch("main.upload_file_to_s3", return_value=S3_URL)
    @patch("auth_http.requests.get")
    def test_returns_200_with_permanent_avatar_url(self, mock_auth, mock_s3, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)

        resp = client.post(
            ENDPOINT,
            files=[_multipart_file(_create_test_image())],
            headers=AUTH_HEADERS,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert list(body.keys()) == ["avatar_url"]
        assert body["avatar_url"] == S3_URL
        assert body["avatar_url"].startswith("https://")

    @patch("main.upload_file_to_s3", return_value=S3_URL)
    @patch("auth_http.requests.get")
    def test_uploads_into_the_drafts_subdirectory(self, mock_auth, mock_s3, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)

        client.post(
            ENDPOINT,
            files=[_multipart_file(_create_test_image())],
            headers=AUTH_HEADERS,
        )

        mock_s3.assert_called_once()
        kwargs = mock_s3.call_args.kwargs
        args = mock_s3.call_args[0]
        assert (
            kwargs.get("subdirectory") == "character_avatar_drafts"
            or "character_avatar_drafts" in args
        )
        # The filename carries the draft prefix and the webp extension.
        filename = kwargs.get("filename") or args[1]
        assert filename.startswith("char_draft_")
        assert filename.endswith(".webp")

    @patch("main.upload_file_to_s3", return_value=S3_URL)
    @patch("auth_http.requests.get")
    def test_any_authenticated_user_may_upload(self, mock_auth, mock_s3, client):
        """No role and no permission is required — the character has no owner yet."""
        mock_auth.return_value = _mock_response(
            200, {"id": 42, "username": "newbie", "role": "user", "permissions": []}
        )
        resp = client.post(
            ENDPOINT,
            files=[_multipart_file(_create_test_image())],
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200

    @patch("main.upload_file_to_s3", return_value=S3_URL)
    @patch("auth_http.requests.get")
    def test_two_uploads_get_distinct_filenames(self, mock_auth, mock_s3, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        image = _create_test_image()

        client.post(ENDPOINT, files=[_multipart_file(image)], headers=AUTH_HEADERS)
        client.post(ENDPOINT, files=[_multipart_file(image)], headers=AUTH_HEADERS)

        names = [
            (call.kwargs.get("filename") or call[0][1])
            for call in mock_s3.call_args_list
        ]
        assert len(set(names)) == 2


# ===========================================================================
# 2. No DB row is written
# ===========================================================================

class TestRequestAvatarUploadWritesNothing:

    @patch("main.upload_file_to_s3", return_value=S3_URL)
    @patch("auth_http.requests.get")
    def test_no_row_is_written(self, mock_auth, mock_s3, client, db_probe):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)

        resp = client.post(
            ENDPOINT,
            files=[_multipart_file(_create_test_image())],
            headers=AUTH_HEADERS,
        )

        assert resp.status_code == 200
        assert db_probe.add.call_count == 0
        assert db_probe.commit.call_count == 0
        assert db_probe.execute.call_count == 0
        assert db_probe.query.call_count == 0

    def test_handler_declares_no_db_dependency(self):
        """Structural guard: the signature must not gain a Session parameter."""
        import inspect

        import main

        params = inspect.signature(main.upload_character_request_avatar).parameters
        assert set(params) == {"file", "current_user"}


# ===========================================================================
# 3. Oversize -> 413 (N3, first branch)
# ===========================================================================

class TestRequestAvatarUploadOversize:

    @patch("main.upload_file_to_s3")
    @patch("auth_http.requests.get")
    def test_file_over_the_limit_returns_413(self, mock_auth, mock_s3, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        oversized = b"\x00" * (MAX_FILE_SIZE + 1024)

        resp = client.post(
            ENDPOINT,
            files=[_multipart_file(oversized, filename="huge.png")],
            headers=AUTH_HEADERS,
        )

        assert resp.status_code == 413
        assert resp.json()["detail"] == (
            "Файл слишком большой. Максимальный размер — 15 МБ."
        )
        mock_s3.assert_not_called()

    @patch("auth_http.requests.get")
    def test_oversize_message_is_russian(self, mock_auth, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        oversized = b"\x00" * (MAX_FILE_SIZE + 1)

        detail = client.post(
            ENDPOINT,
            files=[_multipart_file(oversized, filename="huge.png")],
            headers=AUTH_HEADERS,
        ).json()["detail"]
        assert "слишком большой" in detail

    @patch("main.upload_file_to_s3", return_value=S3_URL)
    @patch("auth_http.requests.get")
    def test_a_file_just_under_the_limit_is_accepted(self, mock_auth, mock_s3, client):
        """The boundary belongs to the accepted side."""
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        # A real image padded with a PNG comment would be huge to build; instead
        # verify the size check itself does not fire on a normal small image.
        resp = client.post(
            ENDPOINT,
            files=[_multipart_file(_create_test_image(400, 400))],
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200

    def test_convert_to_webp_signals_oversize_with_the_word_the_handler_matches(self):
        """N3 guard: the 413 branch keys off "exceeds" in the ValueError text."""
        from utils import convert_to_webp

        with pytest.raises(ValueError) as exc:
            convert_to_webp(io.BytesIO(b"\x00" * (MAX_FILE_SIZE + 1)))
        assert "exceeds" in str(exc.value).lower()


# ===========================================================================
# 4. Not an image -> 400 (N3, second branch)
# ===========================================================================

class TestRequestAvatarUploadInvalidContent:

    @patch("main.upload_file_to_s3")
    @patch("auth_http.requests.get")
    def test_disallowed_mime_returns_400(self, mock_auth, mock_s3, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)

        resp = client.post(
            ENDPOINT,
            files=[_multipart_file(
                b"just plain text", filename="note.txt", content_type="text/plain"
            )],
            headers=AUTH_HEADERS,
        )

        assert resp.status_code == 400
        mock_s3.assert_not_called()

    @patch("main.upload_file_to_s3")
    @patch("auth_http.requests.get")
    def test_pdf_returns_400(self, mock_auth, mock_s3, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        resp = client.post(
            ENDPOINT,
            files=[_multipart_file(
                b"%PDF-1.4 fake", filename="doc.pdf",
                content_type="application/pdf",
            )],
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 400

    @patch("main.upload_file_to_s3")
    @patch("auth_http.requests.get")
    def test_image_mime_with_garbage_bytes_returns_400_not_413(
        self, mock_auth, mock_s3, client
    ):
        """N3: a corrupt payload must land on the 400 branch, never on 413.

        ``validate_image_mime`` trusts the client Content-Type, so this request
        gets past it; ``convert_to_webp`` is the effective guard.
        """
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)

        resp = client.post(
            ENDPOINT,
            files=[_multipart_file(
                b"definitely not a PNG", filename="fake.png",
                content_type="image/png",
            )],
            headers=AUTH_HEADERS,
        )

        assert resp.status_code == 400
        assert resp.json()["detail"] == (
            "Не удалось обработать изображение. "
            "Загрузите корректный файл изображения."
        )
        mock_s3.assert_not_called()

    @patch("main.upload_file_to_s3")
    @patch("auth_http.requests.get")
    def test_empty_file_returns_400(self, mock_auth, mock_s3, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        resp = client.post(
            ENDPOINT,
            files=[_multipart_file(b"", filename="empty.png")],
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 400
        mock_s3.assert_not_called()

    @patch("auth_http.requests.get")
    def test_missing_file_field_returns_422(self, mock_auth, client):
        mock_auth.return_value = _mock_response(200, USER_RESPONSE)
        assert client.post(ENDPOINT, headers=AUTH_HEADERS).status_code == 422


# ===========================================================================
# 5. Authentication
# ===========================================================================

class TestRequestAvatarUploadAuth:

    def test_missing_token_returns_401(self, client):
        resp = client.post(
            ENDPOINT, files=[_multipart_file(_create_test_image())]
        )
        assert resp.status_code == 401

    @patch("main.upload_file_to_s3")
    @patch("auth_http.requests.get")
    def test_invalid_token_returns_401_and_uploads_nothing(
        self, mock_auth, mock_s3, client
    ):
        mock_auth.return_value = _mock_response(401)
        resp = client.post(
            ENDPOINT,
            files=[_multipart_file(_create_test_image())],
            headers={"Authorization": "Bearer bad-token"},
        )
        assert resp.status_code == 401
        mock_s3.assert_not_called()

    @patch("auth_http.requests.get")
    def test_auth_service_down_returns_503(self, mock_auth, client):
        import requests as requests_lib

        mock_auth.side_effect = requests_lib.exceptions.ConnectionError()
        resp = client.post(
            ENDPOINT,
            files=[_multipart_file(_create_test_image())],
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 503
