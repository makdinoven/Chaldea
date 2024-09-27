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
    """Обновление URL аватара в таблице пользователей"""
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            query = "UPDATE users SET avatar = %s WHERE id = %s"
            cursor.execute(query, (avatar_url, user_id))
            connection.commit()
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
