import os
import uuid
from PIL import Image
import io

MEDIA_ROOT = os.getenv("MEDIA_ROOT", "./media")
os.makedirs(MEDIA_ROOT, exist_ok=True)


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


def save_file(file_bytes: bytes, filename: str, subdirectory: str = "") -> str:
    # Определяем путь к поддиректории
    directory_path = os.path.join(MEDIA_ROOT, subdirectory)
    os.makedirs(directory_path, exist_ok=True)

    file_path = os.path.join(directory_path, filename)
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # Возвращаем относительный путь. Например: "/media/character_preview/filename.webp"
    return f"/media/{subdirectory}/{filename}"


def delete_file_by_url(file_url: str):
    # Предполагается, что file_url имеет вид "/media/subdir/filename.webp"
    # Возьмём только часть пути после "/media/"
    relative_path = file_url.lstrip("/")
    file_path = os.path.join(MEDIA_ROOT, os.path.relpath(relative_path, "media"))
    if os.path.exists(file_path):
        os.remove(file_path)
