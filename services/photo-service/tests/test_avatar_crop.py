"""Framing of player avatars: the chosen square becomes the avatar, the whole
picture stays beside it under a name it can be found back from."""

import io
from unittest.mock import MagicMock, patch

from PIL import Image

import avatar_crop

PREFIX = f"{avatar_crop.S3_ENDPOINT_URL}/{avatar_crop.S3_BUCKET_NAME}/"
AUTH = {"Authorization": "Bearer valid-token"}
USER_42 = {"id": 42, "username": "u", "role": "user"}
CROP = {"crop_x": "10", "crop_y": "20", "crop_width": "50", "crop_height": "50"}


def _png(w=200, h=100):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (0, 128, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _auth():
    resp = MagicMock(status_code=200)
    resp.json.return_value = USER_42
    return resp


def _fake_s3(store):
    def upload(data, filename, subdirectory="", content_type="image/webp"):
        url = f"{PREFIX}{subdirectory}/{filename}"
        store[url] = data
        return url
    return upload


# --- naming -----------------------------------------------------------------

def test_original_of_strips_the_crop_tail():
    orig = f"{PREFIX}user_avatars/profile_photo_4_ab.webp"
    assert avatar_crop.original_of(f"{orig}.crop-123abc.webp") == orig
    assert avatar_crop.original_of(orig) == orig


def test_folder_of_only_our_files():
    assert avatar_crop.folder_of(f"{PREFIX}episode_images/x.webp") == "episode_images"
    assert avatar_crop.folder_of("https://evil.example/episode_images/x.webp") is None


def test_half_a_crop_box_is_refused():
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        avatar_crop.crop_box(1, 2, None, 4)
    assert avatar_crop.crop_box(None, None, None, None) is None


# --- upload with a frame ----------------------------------------------------

@patch("main.update_user_avatar")
@patch("auth_http.requests.get")
def test_user_avatar_keeps_the_whole_picture(mock_auth, mock_db, client):
    mock_auth.return_value = _auth()
    store = {}
    with patch("avatar_crop.upload_file_to_s3", side_effect=_fake_s3(store)):
        resp = client.post("/photo/change_user_avatar_photo", headers=AUTH,
                           data={"user_id": "42", **CROP},
                           files=[("file", ("a.png", io.BytesIO(_png()), "image/png"))])
    assert resp.status_code == 200
    avatar = resp.json()["avatar_url"]
    assert avatar_crop.CROP_MARK in avatar and avatar_crop.original_of(avatar) in store
    with Image.open(io.BytesIO(store[avatar])) as framed:
        assert framed.size == (50, 50)
    mock_db.assert_called_once()


@patch("auth_http.requests.get")
def test_without_a_frame_the_whole_picture_is_the_avatar(mock_auth, client):
    mock_auth.return_value = _auth()
    store = {}
    with patch("avatar_crop.upload_file_to_s3", side_effect=_fake_s3(store)), patch("main.update_user_avatar"):
        resp = client.post("/photo/change_user_avatar_photo", headers=AUTH, data={"user_id": "42"},
                           files=[("file", ("a.png", io.BytesIO(_png()), "image/png"))])
    assert avatar_crop.CROP_MARK not in resp.json()["avatar_url"] and len(store) == 1


# --- re-framing -------------------------------------------------------------

@patch("main.update_character_avatar")
@patch("main.get_character_owner_id", return_value=42)
@patch("auth_http.requests.get")
def test_character_reframe_cuts_from_the_original(mock_auth, mock_owner, mock_db, client):
    mock_auth.return_value = _auth()
    orig = f"{PREFIX}character_avatars/profile_photo_7_x.webp"
    store = {}
    with patch("main.get_character_avatar", return_value=f"{orig}.crop-old.webp"), \
            patch("avatar_crop.download_s3_file", return_value=_png(300, 300)) as dl, \
            patch("avatar_crop.upload_file_to_s3", side_effect=_fake_s3(store)):
        resp = client.post("/photo/recrop_character_avatar", headers=AUTH, data={"character_id": "7", **CROP})
    assert resp.status_code == 200
    dl.assert_called_once_with(orig)
    assert avatar_crop.original_of(resp.json()["avatar_url"]) == orig
    mock_db.assert_called_once()


@patch("main.get_character_owner_id", return_value=99)
@patch("auth_http.requests.get")
def test_someone_elses_character_cannot_be_reframed(mock_auth, mock_owner, client):
    mock_auth.return_value = _auth()
    resp = client.post("/photo/recrop_character_avatar", headers=AUTH, data={"character_id": "7", **CROP})
    assert resp.status_code == 403


@patch("auth_http.requests.get")
def test_only_own_user_avatar_is_reframed(mock_auth, client):
    mock_auth.return_value = _auth()
    resp = client.post("/photo/recrop_user_avatar", headers=AUTH, data={"user_id": "5", **CROP})
    assert resp.status_code == 403


@patch("auth_http.requests.get")
def test_recrop_image_only_for_unsaved_folders(mock_auth, client):
    mock_auth.return_value = _auth()
    resp = client.post("/photo/recrop_image", headers=AUTH,
                       data={"image_url": f"{PREFIX}user_avatars/x.webp", **CROP})
    assert resp.status_code == 400
    store = {}
    with patch("avatar_crop.download_s3_file", return_value=_png()), \
            patch("avatar_crop.upload_file_to_s3", side_effect=_fake_s3(store)):
        resp = client.post("/photo/recrop_image", headers=AUTH,
                           data={"image_url": f"{PREFIX}episode_images/r.webp", **CROP})
    assert resp.status_code == 200 and resp.json()["image_url"].startswith(f"{PREFIX}episode_images/r.webp.crop-")
