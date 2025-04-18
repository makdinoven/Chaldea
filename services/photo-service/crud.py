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



# 1) Обновляем map_image_url в таблице Countries
def update_country_map_image(country_id: int, map_url: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE Countries SET map_image_url = %s WHERE id = %s"
            cursor.execute(sql, (map_url, country_id))
        connection.commit()
    except:
        connection.rollback()
        raise
    finally:
        connection.close()


# 2) Обновляем map_image_url в таблице Regions
def update_region_map_image(region_id: int, map_url: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE Regions SET map_image_url = %s WHERE id = %s"
            cursor.execute(sql, (map_url, region_id))
        connection.commit()
    except:
        connection.rollback()
        raise
    finally:
        connection.close()


# 3) Обновляем image_url в таблице Regions
def update_region_image(region_id: int, image_url: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE Regions SET image_url = %s WHERE id = %s"
            cursor.execute(sql, (image_url, region_id))
        connection.commit()
    except:
        connection.rollback()
        raise
    finally:
        connection.close()


# 4) Обновляем image_url в таблице Districts
def update_district_image(district_id: int, image_url: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE Districts SET image_url = %s WHERE id = %s"
            cursor.execute(sql, (image_url, district_id))
        connection.commit()
    except:
        connection.rollback()
        raise
    finally:
        connection.close()


# 5) Обновляем image_url в таблице Locations
def update_location_image(location_id: int, image_url: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE Locations SET image_url = %s WHERE id = %s"
            cursor.execute(sql, (image_url, location_id))
        connection.commit()
    except:
        connection.rollback()
        raise
    finally:
        connection.close()

def update_skill_image(skill_id: int, image_url: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE skills SET skill_image = %s WHERE id = %s"
            cursor.execute(sql, (image_url, skill_id))
        connection.commit()
    except:
        connection.rollback()
        raise
    finally:
        connection.close()

def update_skill_rank_image(skill_rank_id: int, image_url: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE skill_ranks SET rank_image = %s WHERE id = %s"
            cursor.execute(sql, (image_url, skill_rank_id))
        connection.commit()
    except:
        connection.rollback()
        raise
    finally:
        connection.close()

def update_item_image(item_id: int, image_url: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE items SET image = %s WHERE id = %s"
            cursor.execute(sql, (image_url, item_id))
        connection.commit()
    except:
        connection.rollback()
        raise
    finally:
        connection.close()
