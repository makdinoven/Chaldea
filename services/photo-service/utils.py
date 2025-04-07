import os
import uuid
from PIL import Image
import io
import boto3
from dotenv import load_dotenv
from botocore import UNSIGNED
from botocore.config import Config
import logging
logging.basicConfig(level=logging.DEBUG)

load_dotenv()

# настройки s3 из окружения
S3_ENDPOINT_URL = os.getenv('S3_ENDPOINT_URL')
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
S3_REGION = os.getenv("S3_REGION", "ru-1")


s3_client = boto3.client(
    's3',
    endpoint_url='https://s3.twcstorage.ru',  # Обязательно правильный эндпоинт
    region_name='ru-1',                        # Регион должен быть ru-1
    aws_access_key_id='ВАШ_ACCESS_KEY',        # Логин аккаунта
    aws_secret_access_key='ВАШ_SECRET_KEY',    # Пароль администратора
    config=Config(
        signature_version='s3v4',             # Требуется версия подписи V4
        s3={'addressing_style': 'path'}       # Критически важный параметр!
    )
)

def convert_to_webp(input_file, quality=80) -> bytes:
    try:
        image = Image.open(input_file)
        if image.mode != "RGB":
            image = image.convert("RGB")
        output_stream = io.BytesIO()
        image.save(output_stream, "webp", quality=quality)
        return output_stream.getvalue()  # Возвращаем bytes, а не поток
    except Exception as e:
        raise RuntimeError(f"Image conversion failed: {str(e)}")

def generate_unique_filename(prefix: str, entity_id: int, extension: str = ".webp") -> str:
    return f"{prefix}_{entity_id}_{uuid.uuid4().hex}{extension}"


def upload_file_to_s3(file_stream: bytes, filename: str, subdirectory: str = "") -> str:
    s3_key = f"{subdirectory}/{filename}" if subdirectory else filename
    file_obj = io.BytesIO(file_stream)
    file_obj.seek(0)  # Сброс позиции в начало

    try:
        s3_client.upload_fileobj(
            Fileobj=file_obj,
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            ExtraArgs={
                'ACL': 'public-read',
                'ContentType': 'image/webp',
                'ContentLength': len(file_stream)  # Явное указание длины контента
            }
        )
    except Exception as e:
        logging.error(f"S3 upload error: {str(e)}")
        raise

    return f"{S3_ENDPOINT_URL}/{S3_BUCKET_NAME}/{s3_key}"

def delete_s3_file(file_url: str):
    """
    Удаляет файл из S3 по переданному URL.
    """
    s3_key = "/".join(file_url.split("/")[-2:])
    s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
