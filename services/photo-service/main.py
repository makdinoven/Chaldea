from fastapi import FastAPI, File, UploadFile, HTTPException
from google.cloud import storage
import pymysql
import os
import uuid

app = FastAPI()

# Настройка клиента GCS
bucket_name = os.getenv('GCS_BUCKET_NAME')
gcs_client = storage.Client()

# Настройка подключения к базе данных
db_config = {
    'user': os.getenv('DB_USERNAME'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_DATABASE'),
}


def get_db_connection():
    """Создание подключения к базе данных MySQL"""
    return pymysql.connect(
        host=db_config['host'],
        user=db_config['user'],
        password=db_config['password'],
        database=db_config['database'],
        cursorclass=pymysql.cursors.DictCursor
    )


def update_user_avatar(user_id: int, avatar_url: str):
    """Обновление URL аватара в таблице пользователей"""
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            query = "UPDATE users SET avatar = %s WHERE id = %s"
            cursor.execute(query, (avatar_url, user_id))
            connection.commit()
    finally:
        connection.close()


def generate_unique_filename(user_id: int, original_filename: str, prefix: str = "profile_photo") -> str:
    """Генерация уникального имени файла для сохранения в GCS"""
    # Извлечение расширения файла (например, .jpg, .png)
    extension = os.path.splitext(original_filename)[1]
    # Генерация уникального имени файла
    unique_filename = f"{prefix}_{user_id}_{uuid.uuid4().hex}{extension}"
    return unique_filename


@app.post("/upload-photo")
async def upload_photo(user_id: int, file: UploadFile = File(...)):
    """Загрузка фотографии пользователя в Google Cloud Storage"""
    try:
        # Генерация уникального имени файла с префиксом и user_id
        unique_filename = generate_unique_filename(user_id, file.filename)

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


@app.delete("/delete-photo")
async def delete_photo(user_id: int):
    """Удаление фотографии пользователя"""
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
