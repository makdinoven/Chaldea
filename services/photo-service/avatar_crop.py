"""Framing of player pictures: avatars of users and characters, mini-roles.

The player picks a square on the picture; the square becomes the avatar and the
whole picture is kept beside it, so the frame can be changed later without a
new upload. No table remembers the pair — the cropped file is named after its
original: ``<original file name>.crop-<random><ext>`` in the same folder, and
``original_of`` strips the tail back off. A picture uploaded before framing
existed is its own original.
"""

import io
from typing import Optional, Tuple
from uuid import uuid4

from fastapi import HTTPException

from utils import (
    S3_BUCKET_NAME, S3_ENDPOINT_URL, convert_to_webp, crop_image, download_s3_file,
    normalize_orientation, upload_file_to_s3,
)

AVATAR_MAX_SIZE = 640
CROP_MARK = ".crop-"

CropBox = Tuple[float, float, float, float]


def crop_box(crop_x, crop_y, crop_width, crop_height) -> Optional[CropBox]:
    """All four crop fields together, or none of them (= the whole picture)."""
    values = (crop_x, crop_y, crop_width, crop_height)
    if all(v is None for v in values):
        return None
    if any(v is None for v in values):
        raise HTTPException(status_code=400, detail="Область обрезки задана не полностью")
    return values


def _bucket_prefix() -> str:
    return f"{S3_ENDPOINT_URL}/{S3_BUCKET_NAME}/"


def original_of(url: str) -> str:
    """The whole picture a framed avatar was cut from (or the URL itself)."""
    head, mark, _ = url.rpartition(CROP_MARK)
    return head if mark else url


def folder_of(url: str) -> Optional[str]:
    """The S3 folder of one of our files, or None for a foreign URL."""
    prefix = _bucket_prefix()
    if not url or not url.startswith(prefix):
        return None
    key = url[len(prefix):]
    return key.rpartition("/")[0] or None


def _store_crop(raw: bytes, original_url: str, box: CropBox) -> str:
    cropped = crop_image(raw, *box, max_size=AVATAR_MAX_SIZE)
    folder, _, name = original_url[len(_bucket_prefix()):].rpartition("/")
    return upload_file_to_s3(
        cropped.data,
        f"{name}{CROP_MARK}{uuid4().hex[:12]}{cropped.extension}",
        subdirectory=folder,
        content_type=cropped.content_type,
    )


def upload_framed(file_obj, filename: str, folder: str, box: Optional[CropBox]) -> str:
    """Stores a fresh picture whole and, given a frame, its framed copy; returns
    the URL to show (the framed copy, or the whole picture without a frame)."""
    raw = file_obj.read()
    # convert_to_webp checks size and content first (ValueError the callers map
    # to 413/400); only a valid picture gets its EXIF rotation baked in, so the
    # stored original lines up with the frame the browser showed.
    convert_to_webp(io.BytesIO(raw))
    raw = normalize_orientation(raw)
    original = convert_to_webp(io.BytesIO(raw))
    original_url = upload_file_to_s3(
        original.data, f"{filename}{original.extension}", subdirectory=folder,
        content_type=original.content_type,
    )
    return _store_crop(raw, original_url, box) if box else original_url


def reframe(current_url: Optional[str], box: CropBox) -> str:
    """Cuts a new frame out of the whole picture behind `current_url`."""
    if not current_url or folder_of(current_url) is None:
        raise HTTPException(status_code=404, detail="Картинка не найдена — загрузите её заново")
    original_url = original_of(current_url)
    try:
        raw = download_s3_file(original_url)
    except Exception:
        raise HTTPException(status_code=404, detail="Исходная картинка не найдена — загрузите её заново")
    return _store_crop(raw, original_url, box)
