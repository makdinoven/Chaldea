import os
import uuid
from PIL import Image
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


def convert_to_webp(input_file, quality=80) -> bytes:
    MAX_FILE_SIZE = 15 * 1024 * 1024  # 10MB

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

            # Переоткрытие и конвертация
            buffer.seek(0)
            with Image.open(buffer) as image:
                image = image.copy()  # Создаем копию для безопасности

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

                return webp_data

    except Exception as e:
        logging.error(f"Image processing error: {str(e)}", exc_info=True)
        raise

def generate_unique_filename(prefix: str, entity_id: int, extension: str = ".webp") -> str:
    return f"{prefix}_{entity_id}_{uuid.uuid4().hex}{extension}"


def upload_file_to_s3(file_stream: bytes, filename: str, subdirectory: str = "") -> str:
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
            ContentType='image/webp',
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