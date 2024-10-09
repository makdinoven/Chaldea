from fastapi import FastAPI, File, UploadFile, HTTPException, APIRouter, Form
from google.cloud import storage
import uuid
from crud import *

app = FastAPI()

router = APIRouter(prefix="/photo")

# Настройка клиента GCS
bucket_name = os.getenv('GCS_BUCKET_NAME')
gcs_client = storage.Client()


def generate_unique_filename_for_profile_photo(user_id: int, original_filename: str, prefix: str = "profile_photo") -> str:
    """Генерация уникального имени файла для сохранения в GCS"""
    # Извлечение расширения файла (например, .jpg, .png)
    extension = os.path.splitext(original_filename)[1]
    # Генерация уникального имени файла
    unique_filename = f"{prefix}_{user_id}_{uuid.uuid4().hex}{extension}"
    return unique_filename

def generate_unique_filename_for_character_photo(character_id: int, original_filename: str, prefix: str = "profile_photo") -> str:
    """Генерация уникального имени файла для сохранения в GCS"""
    # Извлечение расширения файла (например, .jpg, .png)
    extension = os.path.splitext(original_filename)[1]
    # Генерация уникального имени файла
    unique_filename = f"{prefix}_{character_id}_{uuid.uuid4().hex}{extension}"
    return unique_filename


@router.post("/change_user_avatar_photo")
async def upload_photo(user_id: int = Form(...), file: UploadFile = File(...)):
    """Загрузка фотографии пользователя в Google Cloud Storage"""
    try:
        # Генерация уникального имени файла с префиксом и user_id
        unique_filename = generate_unique_filename_for_profile_photo(user_id, file.filename)

        # Получение бакета по имени
        bucket = gcs_client.bucket(bucket_name)

        # Создание объекта (blob) в бакете с уникальным именем файла
        blob = bucket.blob(unique_filename)

        
        # Загрузка файла в GCS из переданного файла
        blob.upload_from_file(file.file)

        # Получение публичного URL загруженного файла
        avatar_url = blob.public_url

        # Обновление URL аватара в БД
        update_user_avatar(user_id, avatar_url)

        return {"message": "Фото успешно загружено", "avatar_url": avatar_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке фотографии: {e}")


@router.delete("/delete_user_avatar_photo")
async def delete_photo(user_id: int):
    """Удаление фотографии пользователя"""
    global connection
    try:
        # Получение текущего URL аватара из БД
        connection = get_db_connection()
        with connection.cursor() as cursor:
            query = "SELECT avatar FROM users WHERE id = %s"
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()
            if result is None:
                raise HTTPException(status_code=404, detail="Пользователь не найден")

            avatar_url = result['avatar']

        # Удаление файла из GCS
        bucket = gcs_client.bucket(bucket_name)
        blob_name = avatar_url.split('/')[-1]
        blob = bucket.blob(blob_name)
        blob.delete()

        # Обновление URL аватара в БД
        update_user_avatar(user_id, None)

        return {"message": "Фото успешно удалено"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении фотографии: {e}")

    finally:
        connection.close()


@router.post("/change_character_avatar_photo")
async def upload_photo_character(character_id: int = Form(...), file: UploadFile = File(...), user_id: int = Form(...)):
    """Загрузка фотографии пользователя в Google Cloud Storage"""
    try:
        # Генерация уникального имени файла с префиксом и user_id
        unique_filename = generate_unique_filename_for_profile_photo(character_id, file.filename)

        # Получение бакета по имени
        bucket = gcs_client.bucket(bucket_name)

        # Создание объекта (blob) в бакете с уникальным именем файла
        blob = bucket.blob(unique_filename)

        # Загрузка файла в GCS из переданного файла
        blob.upload_from_file(file.file)

        # Получение публичного URL загруженного файла
        avatar_url = blob.public_url

        # Обновление URL аватара в БД
        update_character_avatar(character_id, avatar_url, user_id)

        return {"message": "Фото успешно загружено", "avatar_url": avatar_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке фотографии: {e}")


@router.post("/character_avatar_preview")
async def upload_photo(user_id: int = Form(...), file: UploadFile = File(...)):
    """Загрузка фотографии пользователя в Google Cloud Storage"""
    try:
        # Генерация уникального имени файла с префиксом и user_id
        unique_filename = generate_unique_filename_for_profile_photo(user_id, file.filename)

        # Получение бакета по имени
        bucket = gcs_client.bucket(bucket_name)

        # Создание объекта (blob) в бакете с уникальным именем файла
        blob = bucket.blob(unique_filename)

        # Загрузка файла в GCS из переданного файла
        blob.upload_from_file(file.file)

        # Получение публичного URL загруженного файла
        avatar_url = blob.public_url

        # Обновление URL аватара в БД
        update_character_avatar_preview(user_id, avatar_url)

        return {"message": "Фото успешно загружено", "avatar_url": avatar_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке фотографии: {e}")

@router.post("/user_avatar_preview")
async def upload_photo(user_id: int = Form(...), file: UploadFile = File(...)):
    """Загрузка фотографии пользователя в Google Cloud Storage"""
    try:
        # Генерация уникального имени файла с префиксом и user_id
        unique_filename = generate_unique_filename_for_profile_photo(user_id, file.filename)

        # Получение бакета по имени
        bucket = gcs_client.bucket(bucket_name)

        # Создание объекта (blob) в бакете с уникальным именем файла
        blob = bucket.blob(unique_filename)

        # Загрузка файла в GCS из переданного файла
        blob.upload_from_file(file.file)

        # Получение публичного URL загруженного файла
        avatar_url = blob.public_url

        # Обновление URL аватара в БД
        update_user_avatar_preview(user_id, avatar_url)

        return {"message": "Фото успешно загружено", "avatar_url": avatar_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке фотографии: {e}")

app.include_router(router)