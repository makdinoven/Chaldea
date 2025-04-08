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

logging.basicConfig(level=logging.DEBUG)
load_dotenv()

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
    try:
        # Считываем данные из входного файла в буфер
        input_data = input_file.read()
        buffer = io.BytesIO(input_data)

        # Проверка целостности изображения
        try:
            Image.open(buffer).verify()
        except Exception as verify_error:
            raise ValueError("Invalid image file") from verify_error

        # Переоткрываем изображение после проверки
        buffer.seek(0)
        image = Image.open(buffer)

        if image.mode != "RGB":
            image = image.convert("RGB")

        output_stream = io.BytesIO()
        image.save(output_stream, "webp", quality=quality, method=6)
        webp_data = output_stream.getvalue()

        if len(webp_data) == 0:
            raise ValueError("Empty WEBP data")

        return webp_data
    except Exception as e:
        logging.error(f"Image conversion failed: {str(e)}")
        raise

def generate_unique_filename(prefix: str, entity_id: int, extension: str = ".webp") -> str:
    return f"{prefix}_{entity_id}_{uuid.uuid4().hex}{extension}"


def upload_file_to_s3(file_stream: bytes, filename: str, subdirectory: str = "") -> str:
    s3_key = f"{subdirectory}/{filename}" if subdirectory else filename

    try:
        response = s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=file_stream,
            ACL='public-read',
            ContentType='image/webp',
            ContentLength=len(file_stream),  # Важно!
            ContentMD5=base64.b64encode(hashlib.md5(file_stream).digest()).decode()
        )
        return f"{S3_ENDPOINT_URL}/{S3_BUCKET_NAME}/{s3_key}"

    except Exception as e:
        logging.error(f"S3 Upload Error: {str(e)}")
        raise

def delete_s3_file(file_url: str):
    try:
        s3_key = "/".join(file_url.split("/")[3:])
        s3_client.delete_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key
        )
    except Exception as e:
        logging.error(f"S3 Delete Error: {str(e)}")
        raise