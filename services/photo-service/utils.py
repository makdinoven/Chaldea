import os
import uuid
from PIL import Image
import io
import boto3
from dotenv import load_dotenv

load_dotenv()

# настройки s3 из окружения
S3_ENDPOINT_URL = os.getenv('S3_ENDPOINT_URL')
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')


s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT_URL,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

def convert_to_webp(input_file, quality=80):
    image = Image.open(input_file)
    if image.mode != "RGB":
        image = image.convert("RGB")
    output_stream = io.BytesIO()
    image.save(output_stream, "webp", quality=quality)
    output_stream.seek(0)
    return output_stream.read()

def generate_unique_filename(prefix: str, entity_id: int, extension: str = ".webp") -> str:
    return f"{prefix}_{entity_id}_{uuid.uuid4().hex}{extension}"

def upload_file_to_s3(file_bytes: bytes, filename: str, subdirectory: str = "") -> str:
    """
    Загружает файл в S3 и возвращает URL для доступа к файлу.
    """
    s3_key = f"{subdirectory}/{filename}" if subdirectory else filename
    print(f"[DEBUG] upload_file_to_s3 — BUCKET={S3_BUCKET_NAME}, KEY={s3_key}")
    s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=s3_key, Body=file_bytes, ACL='public-read', ContentType='image/webp')

    # Возвращает публичный URL
    return f"{S3_ENDPOINT_URL}/{S3_BUCKET_NAME}/{s3_key}"

def delete_s3_file(file_url: str):
    """
    Удаляет файл из S3 по переданному URL.
    """
    s3_key = "/".join(file_url.split("/")[-2:])
    s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
