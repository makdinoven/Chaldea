import os
import traceback

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Depends
from sqlalchemy.orm import Session
from database import get_db
from crud import (
    update_user_avatar, get_user_avatar,
    update_character_avatar, get_character_avatar, update_location_image,
    update_district_image, update_region_image, update_region_map_image, update_country_map_image,
    update_skill_rank_image, update_skill_image, update_item_image, update_rule_image,
    update_profile_bg_image, get_profile_bg_image, get_character_owner_id
)
from utils import convert_to_webp, generate_unique_filename, upload_file_to_s3, delete_s3_file, validate_image_mime
from fastapi.middleware.cors import CORSMiddleware
from auth_http import get_admin_user, get_current_user_via_http, require_permission

app = FastAPI()

cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/photo/change_user_avatar_photo")
async def change_user_avatar_photo(user_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(get_current_user_via_http), db: Session = Depends(get_db)):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Вы можете загружать только свой аватар")
    validate_image_mime(file)
    try:
        file_stream = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("profile_photo", user_id)
        avatar_url = upload_file_to_s3(file_stream, unique_filename, subdirectory="user_avatars")
        update_user_avatar(db, user_id, avatar_url)
        return {"message": "Фото успешно загружено", "avatar_url": avatar_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/photo/delete_user_avatar_photo")
async def delete_user_avatar_photo(user_id: int, current_user = Depends(get_current_user_via_http), db: Session = Depends(get_db)):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Вы можете удалять только свой аватар")
    try:
        avatar_url = get_user_avatar(db, user_id)
        if not avatar_url:
            raise HTTPException(status_code=404, detail="Пользователь не найден или аватар не установлен")

        delete_s3_file(avatar_url)
        update_user_avatar(db, user_id, None)
        return {"message": "Фото успешно удалено"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/photo/change_character_avatar_photo")
async def change_character_avatar_photo(character_id: int = Form(...), user_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(get_current_user_via_http), db: Session = Depends(get_db)):
    owner_id = get_character_owner_id(db, character_id)
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    if owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Вы можете загружать аватар только своего персонажа")
    validate_image_mime(file)
    try:
        file_stream = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("profile_photo", character_id)
        avatar_url = upload_file_to_s3(file_stream, unique_filename, subdirectory="character_avatars")
        update_character_avatar(db, character_id, avatar_url, user_id)
        return {"message": "Фото успешно загружено", "avatar_url": avatar_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/photo/change_country_map")
async def change_country_map_photo(country_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    """
    Загружает карту страны (map_image_url) в таблице Countries.
    Сохранение файлов происходит в папке /media/maps/.
    """
    validate_image_mime(file)
    try:
        file_stream = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("country_map", country_id)
        # Пример: "country_map_17_a4c3b8c73f...webp"

        # Сохраняем файл в подкаталог "maps"
        map_url = upload_file_to_s3(file_stream, unique_filename, subdirectory="maps")

        # Обновляем поле map_image_url в таблице Countries
        update_country_map_image(db, country_id, map_url)

        return {
            "message": "Карта страны успешно загружена",
            "map_image_url": map_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 2) Добавить фотографию карты региона
@app.post("/photo/change_region_map")
async def change_region_map_photo(region_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    """
    Загружает карту региона (map_image_url) в таблице Regions.
    Сохранение файлов происходит в папке /media/maps/.
    """
    validate_image_mime(file)
    try:
        file_stream = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("region_map", region_id)
        map_url = upload_file_to_s3(file_stream, unique_filename, subdirectory="maps")

        update_region_map_image(db, region_id, map_url)

        return {
            "message": "Карта региона успешно загружена",
            "map_image_url": map_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 3) Добавить изображение для региона (image_url)
@app.post("/photo/change_region_image")
async def change_region_image(region_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    """
    Загружает обычное изображение региона (image_url) в таблице Regions.
    Сохранение файлов происходит в папке /media/locations/.
    """
    validate_image_mime(file)
    try:
        file_stream = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("region_image", region_id)
        image_url = upload_file_to_s3(file_stream, unique_filename, subdirectory="locations")

        update_region_image(db, region_id, image_url)

        return {
            "message": "Изображение региона успешно загружено",
            "image_url": image_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 4) Добавить изображение для района (District, image_url)
@app.post("/photo/change_district_image")
async def change_district_image(district_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    """
    Загружает изображение для района (image_url) в таблице Districts.
    Сохранение файлов происходит в папке /media/locations/.
    """
    validate_image_mime(file)
    try:
        file_stream = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("district_image", district_id)
        image_url = upload_file_to_s3(file_stream, unique_filename, subdirectory="locations")

        update_district_image(db, district_id, image_url)

        return {
            "message": "Изображение района успешно загружено",
            "image_url": image_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 5) Добавить изображение для локации (Location, image_url)
@app.post("/photo/change_location_image")
async def change_location_image(location_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    validate_image_mime(file)
    try:
        file_stream = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("location_image", location_id)
        image_url = upload_file_to_s3(file_stream, unique_filename, subdirectory="locations")

        update_location_image(db, location_id, image_url)

        return {
            "message": "Изображение локации успешно загружено",
            "image_url": image_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/photo/change_skill_image")
async def change_skill_image(skill_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    """
    Загружает или заменяет изображение для навыка (Skill).
    """
    validate_image_mime(file)
    try:
        file_stream = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("skill_image", skill_id)
        image_url = upload_file_to_s3(file_stream, unique_filename, subdirectory="skills")

        update_skill_image(db, skill_id, image_url)

        return {
            "message": "Изображение навыка успешно загружено",
            "image_url": image_url
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/photo/change_skill_rank_image")
async def change_skill_rank_image(skill_rank_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    """
    Загружает или заменяет изображение для ранга навыка (SkillRank).
    """
    validate_image_mime(file)
    try:
        file_stream = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("skill_rank_image", skill_rank_id)
        image_url = upload_file_to_s3(file_stream, unique_filename, subdirectory="skill_ranks")

        update_skill_rank_image(db, skill_rank_id, image_url)

        return {
            "message": "Изображение ранга навыка успешно загружено",
            "image_url": image_url
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/photo/change_item_image")
async def change_item_image(item_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    """
    Загружает или заменяет изображение для ранга навыка (SkillRank).
    """
    validate_image_mime(file)
    try:
        file_stream = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("item_image", item_id)
        image_url = upload_file_to_s3(file_stream, unique_filename, subdirectory="items")

        update_item_image(db, item_id, image_url)

        return {
            "message": "Изображение предмета успешно загружено",
            "image_url": image_url
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/photo/change_rule_image")
async def change_rule_image(rule_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    """
    Загружает или заменяет изображение для блока правил (GameRule).
    """
    validate_image_mime(file)
    try:
        file_stream = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("rule_image", rule_id)
        image_url = upload_file_to_s3(file_stream, unique_filename, subdirectory="rules")

        update_rule_image(db, rule_id, image_url)

        return {
            "message": "Изображение правила успешно загружено",
            "image_url": image_url
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/photo/change_profile_background")
async def change_profile_background(user_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(get_current_user_via_http), db: Session = Depends(get_db)):
    """Загрузить фоновое изображение профиля."""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Вы можете загружать только свой фон профиля")
    validate_image_mime(file)
    try:
        # Delete old background from S3 if exists
        old_bg = get_profile_bg_image(db, user_id)
        if old_bg:
            try:
                delete_s3_file(old_bg)
            except Exception:
                pass

        file_stream = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("profile_bg", user_id)
        bg_url = upload_file_to_s3(file_stream, unique_filename, subdirectory="profile_backgrounds")
        update_profile_bg_image(db, user_id, bg_url)
        return {"message": "Фон профиля успешно загружен", "profile_bg_image": bg_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/photo/delete_profile_background")
async def delete_profile_background(user_id: int, current_user = Depends(get_current_user_via_http), db: Session = Depends(get_db)):
    """Удалить фоновое изображение профиля."""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Вы можете удалить только свой фон профиля")
    try:
        bg_url = get_profile_bg_image(db, user_id)
        if not bg_url:
            raise HTTPException(status_code=404, detail="Фон профиля не установлен")

        delete_s3_file(bg_url)
        update_profile_bg_image(db, user_id, None)
        return {"message": "Фон профиля успешно удалён"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
