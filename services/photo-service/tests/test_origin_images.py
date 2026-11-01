"""
Tests for POST /photo/change_origin_emblem and /photo/change_origin_map (photo-service).

The origin registry (origin_countries, owned by locations-service) had only URL
fields; admins now upload the emblem and the map from their device like other
admin images.
"""

import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

import models

AUTH_HEADERS = {"Authorization": "Bearer valid-token"}
ADMIN_USER = {"id": 1, "username": "admin", "role": "admin", "permissions": ["photos:upload"]}
USER_NO_PERM = {"id": 2, "username": "user", "role": "user", "permissions": []}

ENDPOINTS = [
    ("/photo/change_origin_emblem", "emblem_url", "Герб происхождения загружен", "emblems"),
    ("/photo/change_origin_map", "map_image_url", "Карта происхождения загружена", "maps"),
]


def _image_bytes() -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100))
    img.putdata([((x * 7) % 256, (y * 13) % 256, ((x + y) * 5) % 256) for y in range(100) for x in range(100)])
    img.save(buf, format="PNG")
    return buf.getvalue()


def _file(content: bytes = None, name: str = "pic.png", ctype: str = "image/png"):
    return ("file", (name, io.BytesIO(content if content is not None else _image_bytes()), ctype))


def _auth(user: dict, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = user
    return resp


@pytest.mark.parametrize("url,field,message,subdir", ENDPOINTS)
class TestOriginImageUpload:
    @patch("main.update_origin_image", return_value=True)
    @patch("main.origin_exists", return_value=True)
    @patch("main.upload_file_to_s3", return_value="https://s3.example.com/media/x/origin_5.webp")
    @patch("auth_http.requests.get")
    def test_success(self, mock_auth, mock_s3, mock_exists, mock_update, client, url, field, message, subdir):
        mock_auth.return_value = _auth(ADMIN_USER)
        r = client.post(url, data={"origin_id": "5"}, files=[_file()], headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert r.json() == {"message": message, field: "https://s3.example.com/media/x/origin_5.webp"}
        assert mock_s3.call_args.kwargs["subdirectory"] == subdir
        kind = "emblem" if field == "emblem_url" else "map"
        mock_update.assert_called_once()
        assert mock_update.call_args.args[1:] == (5, kind, "https://s3.example.com/media/x/origin_5.webp")

    @patch("main.upload_file_to_s3")
    @patch("main.origin_exists", return_value=False)
    @patch("auth_http.requests.get")
    def test_unknown_origin_is_404_and_nothing_uploaded(self, mock_auth, mock_exists, mock_s3, client,
                                                        url, field, message, subdir):
        mock_auth.return_value = _auth(ADMIN_USER)
        r = client.post(url, data={"origin_id": "999"}, files=[_file()], headers=AUTH_HEADERS)
        assert r.status_code == 404
        assert r.json()["detail"] == "Происхождение не найдено"
        mock_s3.assert_not_called()

    @patch("main.upload_file_to_s3", side_effect=RuntimeError("s3 secret endpoint down"))
    @patch("main.origin_exists", return_value=True)
    @patch("auth_http.requests.get")
    def test_storage_failure_is_500_without_internals(self, mock_auth, mock_exists, mock_s3, client,
                                                      url, field, message, subdir):
        mock_auth.return_value = _auth(ADMIN_USER)
        r = client.post(url, data={"origin_id": "5"}, files=[_file()], headers=AUTH_HEADERS)
        assert r.status_code == 500
        assert "secret" not in r.text

    @patch("auth_http.requests.get")
    def test_non_image_is_400(self, mock_auth, client, url, field, message, subdir):
        mock_auth.return_value = _auth(ADMIN_USER)
        r = client.post(url, data={"origin_id": "5"}, files=[_file(b"plain text", "a.txt", "text/plain")],
                        headers=AUTH_HEADERS)
        assert r.status_code == 400

    def test_no_token_is_401(self, client, url, field, message, subdir):
        r = client.post(url, data={"origin_id": "5"}, files=[_file()])
        assert r.status_code == 401

    @patch("auth_http.requests.get")
    def test_no_permission_is_403(self, mock_auth, client, url, field, message, subdir):
        mock_auth.return_value = _auth(USER_NO_PERM)
        r = client.post(url, data={"origin_id": "5"}, files=[_file()], headers=AUTH_HEADERS)
        assert r.status_code == 403

    @patch("auth_http.requests.get")
    def test_missing_fields_and_injection_are_422(self, mock_auth, client, url, field, message, subdir):
        mock_auth.return_value = _auth(ADMIN_USER)
        assert client.post(url, files=[_file()], headers=AUTH_HEADERS).status_code == 422
        assert client.post(url, data={"origin_id": "5"}, headers=AUTH_HEADERS).status_code == 422
        r = client.post(url, data={"origin_id": "1; DROP TABLE origin_countries; --"}, files=[_file()],
                        headers=AUTH_HEADERS)
        assert r.status_code == 422


class TestOriginImageCrud:
    """update_origin_image writes the right column and reports a missing row."""

    def _session(self, row):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row
        return db

    def test_emblem_and_map_columns(self):
        from crud import update_origin_image
        row = models.OriginCountry(id=3, emblem_url=None, map_image_url=None)
        db = self._session(row)
        assert update_origin_image(db, 3, "emblem", "e.webp") is True
        assert update_origin_image(db, 3, "map", "m.webp") is True
        assert (row.emblem_url, row.map_image_url) == ("e.webp", "m.webp")
        assert db.commit.call_count == 2

    def test_missing_origin(self):
        from crud import update_origin_image
        db = self._session(None)
        assert update_origin_image(db, 3, "emblem", "e.webp") is False
        db.commit.assert_not_called()

    def test_mirror_model_matches_owner_table(self):
        cols = set(models.OriginCountry.__table__.columns.keys())
        assert models.OriginCountry.__tablename__ == "origin_countries"
        assert cols == {"id", "emblem_url", "map_image_url"}
