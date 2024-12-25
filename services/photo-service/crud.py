import os
import pymysql
from pymysql.cursors import DictCursor

DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USERNAME')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_DATABASE = os.getenv('DB_DATABASE')

def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_DATABASE,
        cursorclass=DictCursor
    )

def update_user_avatar(user_id: int, avatar_url: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            query_users = "UPDATE users SET avatar = %s WHERE id = %s"
            cursor.execute(query_users, (avatar_url, user_id))

            query_preview = "UPDATE users_avatar_preview SET avatar = %s WHERE user_id = %s"
            cursor.execute(query_preview, (avatar_url, user_id))
        connection.commit()
    except:
        connection.rollback()
        raise
    finally:
        connection.close()

def get_user_avatar(user_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            query = "SELECT avatar FROM users WHERE id = %s"
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()
            return result["avatar"] if result else None
    finally:
        connection.close()

def update_user_avatar_preview(user_id: int, avatar_url: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            query = "UPDATE users_avatar_preview SET avatar = %s WHERE id = %s"
            cursor.execute(query, (avatar_url, user_id))
        connection.commit()
    finally:
        connection.close()

def update_character_avatar(character_id: int, avatar_url: str, user_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            query_char = "UPDATE characters SET avatar = %s WHERE id = %s"
            cursor.execute(query_char, (avatar_url, character_id))

            query_preview = "UPDATE users_avatar_character_preview SET avatar = %s WHERE user_id = %s"
            cursor.execute(query_preview, (avatar_url, user_id))
        connection.commit()
    except:
        connection.rollback()
        raise
    finally:
        connection.close()

def get_character_avatar(character_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            query = "SELECT avatar FROM characters WHERE id = %s"
            cursor.execute(query, (character_id,))
            result = cursor.fetchone()
            return result["avatar"] if result else None
    finally:
        connection.close()

def update_character_avatar_preview(user_id: int, avatar_url: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            query = "UPDATE users_avatar_character_preview SET avatar = %s WHERE id = %s"
            cursor.execute(query, (avatar_url, user_id))
        connection.commit()
    finally:
        connection.close()
