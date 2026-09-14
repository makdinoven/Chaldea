"""
Tests for item pictures: the uncropped original + a square icon cut from it.

Covers:
- crop_image: box in source pixels, clamping to the image, shrink to max size,
  animated GIF stays animated, non-positive box rejected
- normalize_orientation: EXIF rotation is baked into pixels
- POST /photo/change_item_image: original + icon stored, no crop = same URL,
  partial crop box -> 400, auth
- POST /photo/recrop_item_image: re-cuts from the stored original,
  404 when there is no original, auth
"""

import io
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException
from PIL import Image

from utils import crop_image, normalize_orientation, ITEM_ICON_MAX_SIZE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _image_bytes(width=200, height=100, fmt="PNG", color=(0, 128, 255)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _two_tone_bytes() -> bytes:
    """200x100: left half red, right half blue."""
    img = Image.new("RGB", (200, 100), color=(255, 0, 0))
    img.paste((0, 0, 255), (100, 0, 200, 100))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _animated_gif_bytes(frames=3) -> bytes:
    images = [Image.new("RGB", (60, 40), color=(i * 80, 0, 0)) for i in range(frames)]
    buf = io.BytesIO()
    images[0].save(buf, format="GIF", save_all=True, append_images=images[1:], duration=50, loop=0)
    return buf.getvalue()


def _open(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def _mock_response(status_code: int, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


HEADERS = {"Authorization": "Bearer admin-token"}
ADMIN = {"id": 1, "username": "admin", "role": "admin", "permissions": ["photos:upload"]}
REGULAR = {"id": 2, "username": "user", "role": "user", "permissions": []}

FULL_URL = "https://s3.twcstorage.ru/bucket/items/item_full_image_5_a.webp"
ICON_URL = "https://s3.twcstorage.ru/bucket/items/item_image_5_b.webp"


def _file(content: bytes):
    return ("file", ("sword.png", io.BytesIO(content), "image/png"))


def _crop(x=0, y=0, w=100, h=100):
    return {"crop_x": str(x), "crop_y": str(y), "crop_width": str(w), "crop_height": str(h)}


# ===========================================================================
# 1. crop_image / normalize_orientation
# ===========================================================================

class TestCropImage:

    def test_cuts_the_requested_area(self):
        result = crop_image(_two_tone_bytes(), 100, 0, 100, 100)
        img = _open(result.data)
        assert result.content_type == "image/webp"
        assert img.size == (100, 100)
        r, g, b = img.convert("RGB").getpixel((50, 50))
        assert b > 200 and r < 50  # right (blue) half, not the red one

    def test_box_is_clamped_to_the_image(self):
        result = crop_image(_image_bytes(200, 100), 150, -20, 300, 300)
        assert _open(result.data).size == (50, 100)

    def test_large_crop_is_shrunk_to_icon_size(self):
        big = _image_bytes(2000, 2000)
        result = crop_image(big, 0, 0, 2000, 2000)
        assert _open(result.data).size == (ITEM_ICON_MAX_SIZE, ITEM_ICON_MAX_SIZE)

    @pytest.mark.parametrize("w,h", [(0, 10), (10, 0), (-5, 10)])
    def test_non_positive_box_is_rejected(self, w, h):
        with pytest.raises(HTTPException) as exc:
            crop_image(_image_bytes(), 0, 0, w, h)
        assert exc.value.status_code == 400

    def test_animated_gif_stays_animated(self):
        result = crop_image(_animated_gif_bytes(3), 10, 0, 40, 40)
        img = _open(result.data)
        assert result.content_type == "image/gif"
        assert img.is_animated and img.n_frames == 3
        assert img.size == (40, 40)

    def test_exif_rotation_is_baked_in(self):
        img = Image.new("RGB", (200, 100), color=(0, 0, 0))
        exif = img.getexif()
        exif[0x0112] = 6  # rotate 90° clockwise on display
        buf = io.BytesIO()
        img.save(buf, format="JPEG", exif=exif)

        normalized = _open(normalize_orientation(buf.getvalue()))
        assert normalized.size == (100, 200)

    def test_image_without_rotation_is_untouched(self):
        data = _image_bytes()
        assert normalize_orientation(data) is data


# ===========================================================================
# 2. POST /photo/change_item_image
# ===========================================================================

class TestChangeItemImage:

    @patch("main.update_item_image")
    @patch("main.upload_file_to_s3", side_effect=[FULL_URL, ICON_URL])
    @patch("auth_http.requests.get")
    def test_stores_original_and_cropped_icon(self, mock_auth, mock_s3, mock_db, client):
        mock_auth.return_value = _mock_response(200, ADMIN)

        response = client.post(
            "/photo/change_item_image",
            data={"item_id": "5", **_crop(100, 0, 100, 100)},
            files=[_file(_two_tone_bytes())],
            headers=HEADERS,
        )

        assert response.status_code == 200
        assert response.json()["image_url"] == ICON_URL
        assert response.json()["full_image_url"] == FULL_URL
        assert mock_s3.call_count == 2

        original_bytes = mock_s3.call_args_list[0][0][0]
        icon_bytes = mock_s3.call_args_list[1][0][0]
        assert _open(original_bytes).size == (200, 100)
        assert _open(icon_bytes).size == (100, 100)

        args = mock_db.call_args[0]
        assert args[1:] == (5, ICON_URL, FULL_URL)

    @patch("main.update_item_image")
    @patch("main.upload_file_to_s3", return_value=FULL_URL)
    @patch("auth_http.requests.get")
    def test_without_crop_icon_is_the_whole_picture(self, mock_auth, mock_s3, mock_db, client):
        mock_auth.return_value = _mock_response(200, ADMIN)

        response = client.post(
            "/photo/change_item_image",
            data={"item_id": "5"},
            files=[_file(_image_bytes())],
            headers=HEADERS,
        )

        assert response.status_code == 200
        assert response.json()["image_url"] == FULL_URL
        mock_s3.assert_called_once()
        assert mock_db.call_args[0][1:] == (5, FULL_URL, FULL_URL)

    @patch("main.update_item_image")
    @patch("main.upload_file_to_s3")
    @patch("auth_http.requests.get")
    def test_partial_crop_box_returns_400(self, mock_auth, mock_s3, mock_db, client):
        mock_auth.return_value = _mock_response(200, ADMIN)

        response = client.post(
            "/photo/change_item_image",
            data={"item_id": "5", "crop_x": "0", "crop_y": "0"},
            files=[_file(_image_bytes())],
            headers=HEADERS,
        )

        assert response.status_code == 400
        mock_s3.assert_not_called()
        mock_db.assert_not_called()

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_auth, client):
        mock_auth.return_value = _mock_response(200, REGULAR)
        response = client.post(
            "/photo/change_item_image",
            data={"item_id": "5", **_crop()},
            files=[_file(_image_bytes())],
            headers=HEADERS,
        )
        assert response.status_code == 403

    def test_missing_token_returns_401(self, client):
        response = client.post(
            "/photo/change_item_image",
            data={"item_id": "5"},
            files=[_file(_image_bytes())],
        )
        assert response.status_code == 401

    @patch("auth_http.requests.get")
    def test_sql_injection_in_item_id_returns_422(self, mock_auth, client):
        mock_auth.return_value = _mock_response(200, ADMIN)
        response = client.post(
            "/photo/change_item_image",
            data={"item_id": "1; DROP TABLE items;--"},
            files=[_file(_image_bytes())],
            headers=HEADERS,
        )
        assert response.status_code == 422


# ===========================================================================
# 3. POST /photo/recrop_item_image
# ===========================================================================

class TestRecropItemImage:

    @patch("main.update_item_image")
    @patch("main.upload_file_to_s3", return_value=ICON_URL)
    @patch("main.download_s3_file")
    @patch("main.get_item_full_image", return_value=FULL_URL)
    @patch("auth_http.requests.get")
    def test_recuts_icon_from_stored_original(
        self, mock_auth, mock_get_full, mock_download, mock_s3, mock_db, client,
    ):
        mock_auth.return_value = _mock_response(200, ADMIN)
        mock_download.return_value = _two_tone_bytes()

        response = client.post(
            "/photo/recrop_item_image",
            data={"item_id": "5", **_crop(0, 0, 100, 100)},
            headers=HEADERS,
        )

        assert response.status_code == 200
        assert response.json()["image_url"] == ICON_URL
        mock_download.assert_called_once_with(FULL_URL)

        icon = _open(mock_s3.call_args[0][0]).convert("RGB")
        r, g, b = icon.getpixel((50, 50))
        assert r > 200 and b < 50  # left (red) half

        # Only the icon changes; the original is left as is
        assert mock_db.call_args[0][1:] == (5, ICON_URL)

    @patch("main.upload_file_to_s3")
    @patch("main.get_item_full_image", return_value=None)
    @patch("auth_http.requests.get")
    def test_item_without_original_returns_404(self, mock_auth, mock_get_full, mock_s3, client):
        mock_auth.return_value = _mock_response(200, ADMIN)

        response = client.post(
            "/photo/recrop_item_image",
            data={"item_id": "5", **_crop()},
            headers=HEADERS,
        )

        assert response.status_code == 404
        mock_s3.assert_not_called()

    @patch("auth_http.requests.get")
    def test_missing_crop_fields_returns_422(self, mock_auth, client):
        mock_auth.return_value = _mock_response(200, ADMIN)
        response = client.post(
            "/photo/recrop_item_image",
            data={"item_id": "5", "crop_x": "0"},
            headers=HEADERS,
        )
        assert response.status_code == 422

    @patch("auth_http.requests.get")
    def test_non_admin_returns_403(self, mock_auth, client):
        mock_auth.return_value = _mock_response(200, REGULAR)
        response = client.post(
            "/photo/recrop_item_image",
            data={"item_id": "5", **_crop()},
            headers=HEADERS,
        )
        assert response.status_code == 403
