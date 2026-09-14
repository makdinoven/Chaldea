import os
import uuid
from collections import namedtuple
from PIL import Image, ImageOps, ImageSequence
import io
import boto3
from dotenv import load_dotenv
from botocore.config import Config
import logging
import hashlib
import base64
from fastapi import UploadFile, HTTPException

logging.basicConfig(level=logging.INFO)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("boto3").setLevel(logging.WARNING)
load_dotenv()

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

ImageResult = namedtuple("ImageResult", ["data", "extension", "content_type"])


def validate_image_mime(file: UploadFile):
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Недопустимый формат файла. Разрешены: JPEG, PNG, WebP, GIF"
        )

# Настройки из окружения
S3_ENDPOINT_URL = os.getenv('S3_ENDPOINT_URL', 'https://s3.twcstorage.ru')
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
S3_REGION = os.getenv("S3_REGION", "ru-1")

# Конфигурация клиента S3 (исправленная версия)
s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT_URL,
    region_name=S3_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    config=Config(
        signature_version='s3v4',
        s3={'addressing_style': 'path'},
    )
)


def convert_to_webp(input_file, quality=80) -> ImageResult:
    """Convert an image to WebP, preserving animated GIFs as-is.

    Returns an ImageResult namedtuple with (data, extension, content_type).
    For animated GIFs: keeps GIF format to preserve animation.
    For all other images: converts to WebP as before.
    """
    MAX_FILE_SIZE = 15 * 1024 * 1024  # 15MB

    try:
        # Чтение и проверка размера файла
        input_data = input_file.read()
        if len(input_data) > MAX_FILE_SIZE:
            raise ValueError(f"File size exceeds {MAX_FILE_SIZE // 1024 // 1024}MB limit")
        if not input_data:
            raise ValueError("Empty input file")

        # Проверка целостности изображения
        with io.BytesIO(input_data) as buffer:
            try:
                Image.open(buffer).verify()
            except Exception as verify_error:
                raise ValueError("Invalid image content") from verify_error

            # Переоткрытие и обработка
            buffer.seek(0)
            with Image.open(buffer) as image:
                is_animated_gif = (
                    image.format == "GIF"
                    and getattr(image, "is_animated", False)
                )

                if is_animated_gif:
                    # Сохраняем анимированный GIF без конвертации
                    frames = []
                    durations = []
                    for frame in ImageSequence.Iterator(image):
                        frames.append(frame.copy())
                        durations.append(frame.info.get("duration", 100))

                    output_stream = io.BytesIO()
                    frames[0].save(
                        output_stream,
                        format="GIF",
                        save_all=True,
                        append_images=frames[1:],
                        duration=durations,
                        loop=image.info.get("loop", 0),
                        disposal=image.info.get("disposal", 2),
                    )
                    gif_data = output_stream.getvalue()

                    if len(gif_data) < 100:
                        raise ValueError("Invalid GIF processing result")

                    return ImageResult(
                        data=gif_data,
                        extension=".gif",
                        content_type="image/gif",
                    )

                # Статические изображения — конвертация в WebP
                image = image.copy()

                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA" if image.mode == "P" else "RGB")

                # Оптимизация параметров сохранения
                output_stream = io.BytesIO()
                save_args = {
                    "format": "WEBP",
                    "quality": quality,
                    "method": 6,
                    "lossless": False
                }

                image.save(output_stream, **save_args)
                webp_data = output_stream.getvalue()

                if len(webp_data) < 100:  # Минимальный размер для WebP
                    raise ValueError("Invalid WEBP conversion result")

                return ImageResult(
                    data=webp_data,
                    extension=".webp",
                    content_type="image/webp",
                )

    except Exception as e:
        logging.error(f"Image processing error: {str(e)}", exc_info=True)
        raise

# Longest side of a cropped item icon; icons are never shown larger than this
ITEM_ICON_MAX_SIZE = 512


def normalize_orientation(input_data: bytes) -> bytes:
    """Bake the EXIF rotation into the pixels of a still image.

    Browsers draw photos already rotated by EXIF, so the crop box the admin picks
    is in rotated coordinates. Pillow ignores EXIF, so without this the stored
    original and the crop would not line up. Animated GIFs carry no EXIF and are
    returned untouched, as is anything that needs no rotation.
    """
    with Image.open(io.BytesIO(input_data)) as image:
        if getattr(image, "is_animated", False):
            return input_data
        if image.getexif().get(0x0112, 1) == 1:  # 0x0112 = Orientation tag
            return input_data
        rotated = ImageOps.exif_transpose(image)
        output_stream = io.BytesIO()
        rotated.save(output_stream, format="PNG")
        return output_stream.getvalue()


def _clamp_crop_box(image_size, x: float, y: float, width: float, height: float):
    """Turn a crop rectangle in pixels into a Pillow box that lies inside the image."""
    img_w, img_h = image_size
    if width <= 0 or height <= 0:
        raise HTTPException(status_code=400, detail="Область обрезки должна иметь положительный размер")
    left = max(0, min(int(round(x)), img_w - 1))
    top = max(0, min(int(round(y)), img_h - 1))
    right = max(left + 1, min(int(round(x + width)), img_w))
    bottom = max(top + 1, min(int(round(y + height)), img_h))
    return left, top, right, bottom


def crop_image(input_data: bytes, x: float, y: float, width: float, height: float,
               max_size: int = ITEM_ICON_MAX_SIZE, quality: int = 80) -> ImageResult:
    """Cut a rectangle (in source pixels) out of an image and shrink it to max_size.

    Still images come back as WebP; animated GIFs are cropped frame by frame and
    stay GIF so the animation survives.
    """
    with Image.open(io.BytesIO(input_data)) as image:
        box = _clamp_crop_box(image.size, x, y, width, height)

        def fit(frame):
            frame = frame.crop(box)
            frame.thumbnail((max_size, max_size))
            return frame

        if image.format == "GIF" and getattr(image, "is_animated", False):
            frames, durations = [], []
            for frame in ImageSequence.Iterator(image):
                frames.append(fit(frame.convert("RGBA")))
                durations.append(frame.info.get("duration", 100))
            output_stream = io.BytesIO()
            frames[0].save(
                output_stream,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                loop=image.info.get("loop", 0),
                disposal=2,
            )
            return ImageResult(output_stream.getvalue(), ".gif", "image/gif")

        cropped = image.copy()
        if cropped.mode not in ("RGB", "RGBA"):
            cropped = cropped.convert("RGBA" if cropped.mode in ("P", "LA") else "RGB")
        cropped = fit(cropped)
        output_stream = io.BytesIO()
        cropped.save(output_stream, format="WEBP", quality=quality, method=6)
        return ImageResult(output_stream.getvalue(), ".webp", "image/webp")


def download_s3_file(file_url: str) -> bytes:
    """Read back a file this service uploaded, addressed by its public URL."""
    s3_key = "/".join(file_url.split("/")[4:])
    response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
    return response["Body"].read()


def generate_unique_filename(prefix: str, entity_id: int, extension: str = ".webp") -> str:
    return f"{prefix}_{entity_id}_{uuid.uuid4().hex}{extension}"


def upload_file_to_s3(file_stream: bytes, filename: str, subdirectory: str = "", content_type: str = "image/webp") -> str:
    try:
        if not isinstance(file_stream, bytes):
            raise TypeError("Expected bytes content")

        s3_key = f"{subdirectory}/{filename}" if subdirectory else filename

        # Проверка MD5 для целостности данных
        md5_hash = hashlib.md5(file_stream).digest()
        content_md5 = base64.b64encode(md5_hash).decode()

        response = s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=file_stream,
            ACL='public-read',
            ContentType=content_type,
            ContentLength=len(file_stream),
            ContentMD5=content_md5,
            Metadata={
                'Content-Encoding': 'binary',
                'Cache-Control': 'max-age=31536000'  # Кеширование на год
            }
        )

        if response['ResponseMetadata']['HTTPStatusCode'] != 200:
            raise RuntimeError("S3 upload failed")

        logging.info(f"Uploaded to S3: {s3_key}, Size: {len(file_stream)} bytes, ETag: {response['ETag']}")
        return f"{S3_ENDPOINT_URL}/{S3_BUCKET_NAME}/{s3_key}"

    except Exception as e:
        logging.error(f"S3 Upload Error: {str(e)}", exc_info=True)
        raise

def delete_s3_file(file_url: str):
    try:
        s3_key = "/".join(file_url.split("/")[4:])
        s3_client.delete_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key
        )
    except Exception as e:
        logging.error(f"S3 Delete Error: {str(e)}")
        raise