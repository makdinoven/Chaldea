import pymysql
import os

# Настройка подключения к базе данных
db_config = {
    'user': os.getenv('DB_USERNAME'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_DATABASE'),
}


def update_user_avatar(user_id: int, avatar_url: str):
    """Обновление URL аватара в таблице пользователей и в таблице превью аватаров"""
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Обновляем аватар в таблице users
            query_users = "UPDATE users SET avatar = %s WHERE id = %s"
            cursor.execute(query_users, (avatar_url, user_id))

            # Обновляем аватар в таблице users_avatar_preview
            query_preview = "UPDATE users_avatar_preview SET avatar = %s WHERE user_id = %s"
            cursor.execute(query_preview, (avatar_url, user_id))

            # Подтверждаем изменения
            connection.commit()
    except Exception as e:
        # В случае ошибки откатываем транзакцию
        connection.rollback()
        raise e
    finally:
        connection.close()


def get_db_connection():
    """Создание подключения к базе данных MySQL"""
    return pymysql.connect(
        host=db_config['host'],
        user=db_config['user'],
        password=db_config['password'],
        database=db_config['database'],
        cursorclass=pymysql.cursors.DictCursor
    )
def update_character_avatar(character_id: int, avatar_url: str, user_id: int):
    """Обновление URL аватара в таблице пользователей"""
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Обновляем аватар в таблице users
            query_users = "UPDATE characters SET avatar = %s WHERE id = %s"
            cursor.execute(query_users, (avatar_url, character_id))

            # Обновляем аватар в таблице users_avatar_preview
            query_preview = "UPDATE users_avatar_character_preview SET avatar = %s WHERE user_id = %s"
            cursor.execute(query_preview, (avatar_url, user_id))

            # Подтверждаем изменения
            connection.commit()
    except Exception as e:
        # В случае ошибки откатываем транзакцию
        connection.rollback()
        raise e
    finally:
        connection.close()

def update_character_avatar_preview(user_id: int, avatar_url: str):
    """Обновление URL аватара в таблице пользователей"""
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            query = "UPDATE character_avatar_preview SET avatar = %s WHERE id = %s"
            cursor.execute(query, (avatar_url, user_id))
            connection.commit()
    finally:
        connection.close()

def update_user_avatar_preview(user_id: int, avatar_url: str):
    """Обновление URL аватара в таблице пользователей"""
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            query = "UPDATE users_avatar_preview SET avatar = %s WHERE id = %s"
            cursor.execute(query, (avatar_url, user_id))
            connection.commit()
    finally:
        connection.close()