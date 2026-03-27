import os
import time
import traceback
from uuid import uuid4

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Depends
from sqlalchemy.orm import Session
from database import get_db
from crud import (
    update_user_avatar, get_user_avatar,
    update_character_avatar, get_character_avatar, update_location_image,
    update_district_image, update_district_icon, update_district_map_image,
    update_region_image, update_region_map_image,
    update_country_map_image,
    update_area_map_image, update_country_emblem,
    update_skill_rank_image, update_skill_image, update_item_image, update_rule_image,
    update_profile_bg_image, get_profile_bg_image, get_character_owner_id,
    update_race_image, update_subrace_image, update_location_icon,
    update_mob_template_avatar, update_recipe_image,
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
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("profile_photo", user_id, extension=result.extension)
        avatar_url = upload_file_to_s3(result.data, unique_filename, subdirectory="user_avatars", content_type=result.content_type)
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
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("profile_photo", character_id, extension=result.extension)
        avatar_url = upload_file_to_s3(result.data, unique_filename, subdirectory="character_avatars", content_type=result.content_type)
        update_character_avatar(db, character_id, avatar_url, user_id)
        return {"message": "Фото успешно загружено", "avatar_url": avatar_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/photo/change_npc_avatar")
async def change_npc_avatar(
    character_id: int = Form(...),
    file: UploadFile = File(...),
    current_user=Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Admin-only: upload avatar for an NPC character."""
    validate_image_mime(file)
    try:
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("npc_avatar", character_id, extension=result.extension)
        avatar_url = upload_file_to_s3(result.data, unique_filename, subdirectory="character_avatars", content_type=result.content_type)
        update_character_avatar(db, character_id, avatar_url, current_user.id)
        return {"message": "Аватар НПС загружен", "avatar_url": avatar_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/photo/change_mob_avatar")
async def change_mob_avatar(
    mob_template_id: int = Form(...),
    file: UploadFile = File(...),
    current_user=Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Admin-only: upload avatar for a mob template."""
    validate_image_mime(file)
    try:
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("mob_avatar", mob_template_id, extension=result.extension)
        avatar_url = upload_file_to_s3(result.data, unique_filename, subdirectory="mob_avatars", content_type=result.content_type)
        update_mob_template_avatar(db, mob_template_id, avatar_url)
        return {"message": "Аватар моба загружен", "avatar_url": avatar_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/photo/change_area_map")
async def change_area_map_photo(area_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    """
    Загружает карту области (map_image_url) в таблице Areas.
    Сохранение файлов происходит в папке /media/maps/.
    """
    validate_image_mime(file)
    try:
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("area_map", area_id, extension=result.extension)

        # Сохраняем файл в подкаталог "maps"
        map_url = upload_file_to_s3(result.data, unique_filename, subdirectory="maps", content_type=result.content_type)

        # Обновляем поле map_image_url в таблице Areas
        update_area_map_image(db, area_id, map_url)

        return {
            "message": "Карта области успешно загружена",
            "map_image_url": map_url
        }
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
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("country_map", country_id, extension=result.extension)

        # Сохраняем файл в подкаталог "maps"
        map_url = upload_file_to_s3(result.data, unique_filename, subdirectory="maps", content_type=result.content_type)

        # Обновляем поле map_image_url в таблице Countries
        update_country_map_image(db, country_id, map_url)

        return {
            "message": "Карта страны успешно загружена",
            "map_image_url": map_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/photo/change_country_emblem")
async def change_country_emblem(country_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    """
    Загружает эмблему страны (emblem_url) в таблице Countries.
    Сохранение файлов происходит в папке /media/emblems/.
    """
    validate_image_mime(file)
    try:
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("country_emblem", country_id, extension=result.extension)

        file_url = upload_file_to_s3(result.data, unique_filename, subdirectory="emblems", content_type=result.content_type)

        update_country_emblem(db, country_id, file_url)

        return {
            "message": "Эмблема страны успешно загружена",
            "emblem_url": file_url
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
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("region_map", region_id, extension=result.extension)
        map_url = upload_file_to_s3(result.data, unique_filename, subdirectory="maps", content_type=result.content_type)

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
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("region_image", region_id, extension=result.extension)
        image_url = upload_file_to_s3(result.data, unique_filename, subdirectory="locations", content_type=result.content_type)

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
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("district_image", district_id, extension=result.extension)
        image_url = upload_file_to_s3(result.data, unique_filename, subdirectory="locations", content_type=result.content_type)

        update_district_image(db, district_id, image_url)

        return {
            "message": "Изображение района успешно загружено",
            "image_url": image_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 4b) Загрузить иконку района для карты региона (map_icon_url)
@app.post("/photo/change_district_icon")
async def change_district_icon(district_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    """
    Загружает иконку района для отображения на карте региона (map_icon_url).
    Сохранение файлов происходит в папке /media/district_icons/.
    """
    validate_image_mime(file)
    try:
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("district_icon", district_id, extension=result.extension)
        file_url = upload_file_to_s3(result.data, unique_filename, subdirectory="district_icons", content_type=result.content_type)

        update_district_icon(db, district_id, file_url)

        return {
            "message": "Иконка района успешно загружена",
            "map_icon_url": file_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 4d) Загрузить карту района/города (map_image_url)
@app.post("/photo/change_district_map")
async def change_district_map_photo(district_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    """
    Загружает карту района/города (map_image_url) в таблице Districts.
    Сохранение файлов происходит в папке /media/maps/.
    """
    validate_image_mime(file)
    try:
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("district_map", district_id, extension=result.extension)
        map_url = upload_file_to_s3(result.data, unique_filename, subdirectory="maps", content_type=result.content_type)

        update_district_map_image(db, district_id, map_url)

        return {
            "message": "Карта района успешно загружена",
            "map_image_url": map_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 5) Добавить изображение для локации (Location, image_url)
@app.post("/photo/change_location_image")
async def change_location_image(location_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    validate_image_mime(file)
    try:
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("location_image", location_id, extension=result.extension)
        image_url = upload_file_to_s3(result.data, unique_filename, subdirectory="locations", content_type=result.content_type)

        update_location_image(db, location_id, image_url)

        return {
            "message": "Изображение локации успешно загружено",
            "image_url": image_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 6) Загрузить иконку локации для карты региона (map_icon_url)
@app.post("/photo/change_location_icon")
async def change_location_icon(location_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    """
    Загружает иконку локации для отображения на карте региона (map_icon_url).
    Сохранение файлов происходит в папке /media/location_icons/.
    """
    validate_image_mime(file)
    try:
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("location_icon", location_id, extension=result.extension)
        file_url = upload_file_to_s3(result.data, unique_filename, subdirectory="location_icons", content_type=result.content_type)

        update_location_icon(db, location_id, file_url)

        return {
            "message": "Иконка локации успешно загружена",
            "map_icon_url": file_url
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
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("skill_image", skill_id, extension=result.extension)
        image_url = upload_file_to_s3(result.data, unique_filename, subdirectory="skills", content_type=result.content_type)

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
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("skill_rank_image", skill_rank_id, extension=result.extension)
        image_url = upload_file_to_s3(result.data, unique_filename, subdirectory="skill_ranks", content_type=result.content_type)

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
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("item_image", item_id, extension=result.extension)
        image_url = upload_file_to_s3(result.data, unique_filename, subdirectory="items", content_type=result.content_type)

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
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("rule_image", rule_id, extension=result.extension)
        image_url = upload_file_to_s3(result.data, unique_filename, subdirectory="rules", content_type=result.content_type)

        update_rule_image(db, rule_id, image_url)

        return {
            "message": "Изображение правила успешно загружено",
            "image_url": image_url
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/photo/change_race_image")
async def change_race_image(race_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    """
    Загружает или заменяет изображение расы.
    """
    validate_image_mime(file)
    try:
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("race_image", race_id, extension=result.extension)
        image_url = upload_file_to_s3(result.data, unique_filename, subdirectory="race_images", content_type=result.content_type)

        update_race_image(db, race_id, image_url)

        return {
            "message": "Изображение расы успешно загружено",
            "image_url": image_url
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/photo/change_subrace_image")
async def change_subrace_image(subrace_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    """
    Загружает или заменяет изображение подрасы.
    """
    validate_image_mime(file)
    try:
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("subrace_image", subrace_id, extension=result.extension)
        image_url = upload_file_to_s3(result.data, unique_filename, subdirectory="race_images", content_type=result.content_type)

        update_subrace_image(db, subrace_id, image_url)

        return {
            "message": "Изображение подрасы успешно загружено",
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

        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("profile_bg", user_id, extension=result.extension)
        bg_url = upload_file_to_s3(result.data, unique_filename, subdirectory="profile_backgrounds", content_type=result.content_type)
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


@app.post("/photo/change_recipe_image")
async def change_recipe_image(recipe_id: int = Form(...), file: UploadFile = File(...), current_user = Depends(require_permission("photos:upload")), db: Session = Depends(get_db)):
    """
    Загружает или заменяет иконку рецепта (Recipe.icon).
    Также обновляет image у авто-созданного предмета-рецепта (item_type='recipe').
    """
    validate_image_mime(file)
    try:
        result = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("recipe_image", recipe_id, extension=result.extension)
        image_url = upload_file_to_s3(result.data, unique_filename, subdirectory="recipes", content_type=result.content_type)

        update_recipe_image(db, recipe_id, image_url)

        return {
            "message": "Изображение рецепта успешно загружено",
            "image_url": image_url
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/photo/upload_archive_image")
async def upload_archive_image(
    file: UploadFile = File(...),
    current_user=Depends(require_permission("photos:upload")),
):
    """
    Загружает изображение для статьи архива (Lore Wiki).
    Не привязано к конкретной сущности — просто загружает файл в S3 и возвращает URL.
    URL затем вставляется в HTML-контент статьи через WYSIWYG-редактор.
    """
    validate_image_mime(file)
    try:
        result = convert_to_webp(file.file)
        timestamp = int(time.time())
        unique_filename = f"archive_{uuid4().hex}_{timestamp}{result.extension}"
        image_url = upload_file_to_s3(
            result.data, unique_filename, subdirectory="archive_images", content_type=result.content_type
        )

        return {"image_url": image_url}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/photo/upload_ticket_attachment")
async def upload_ticket_attachment(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user_via_http),
):
    """
    Загружает изображение-вложение для тикета поддержки.
    Не привязано к конкретной сущности — загружает файл в S3 и возвращает URL.
    URL сохраняется в поле attachment_url сообщения тикета.
    Доступно любому авторизованному пользователю.
    """
    validate_image_mime(file)
    try:
        result = convert_to_webp(file.file)
        timestamp = int(time.time())
        unique_filename = f"ticket_{uuid4().hex}_{timestamp}{result.extension}"
        image_url = upload_file_to_s3(
            result.data, unique_filename, subdirectory="ticket_attachments", content_type=result.content_type
        )

        return {"image_url": image_url}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
