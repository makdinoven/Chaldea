from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from crud import (
    update_user_avatar, get_user_avatar, update_user_avatar_preview,
    update_character_avatar, get_character_avatar, update_character_avatar_preview, update_location_image,
    update_district_image, update_region_image, update_region_map_image, update_country_map_image
)
from utils import convert_to_webp, generate_unique_filename, save_file, delete_file_by_url

app = FastAPI()

@app.post("/photo/change_user_avatar_photo")
async def change_user_avatar_photo(user_id: int = Form(...), file: UploadFile = File(...)):
    try:
        file_bytes = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("profile_photo", user_id)
        avatar_url = save_file(file_bytes, unique_filename, subdirectory="user_avatars")
        update_user_avatar(user_id, avatar_url)
        return {"message": "Фото успешно загружено", "avatar_url": avatar_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/photo/delete_user_avatar_photo")
async def delete_user_avatar_photo(user_id: int):
    try:
        avatar_url = get_user_avatar(user_id)
        if not avatar_url:
            raise HTTPException(status_code=404, detail="Пользователь не найден или аватар не установлен")

        delete_file_by_url(avatar_url)
        update_user_avatar(user_id, None)
        return {"message": "Фото успешно удалено"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/photo/change_character_avatar_photo")
async def change_character_avatar_photo(character_id: int = Form(...), user_id: int = Form(...), file: UploadFile = File(...)):
    try:
        file_bytes = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("profile_photo", character_id)
        avatar_url = save_file(file_bytes, unique_filename, subdirectory="character_avatars")
        update_character_avatar(character_id, avatar_url, user_id)
        return {"message": "Фото успешно загружено", "avatar_url": avatar_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/photo/character_avatar_preview")
async def character_avatar_preview(user_id: int = Form(...), file: UploadFile = File(...)):
    try:
        file_bytes = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("profile_photo", user_id)
        avatar_url = save_file(file_bytes, unique_filename, subdirectory="character_preview")
        update_character_avatar_preview(user_id, avatar_url)
        return {"message": "Фото успешно загружено", "avatar_url": avatar_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/photo/user_avatar_preview")
async def user_avatar_preview(user_id: int = Form(...), file: UploadFile = File(...)):
    try:
        file_bytes = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("profile_photo", user_id)
        avatar_url = save_file(file_bytes, unique_filename, subdirectory="user_preview")
        update_user_avatar_preview(user_id, avatar_url)
        return {"message": "Фото успешно загружено", "avatar_url": avatar_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/photo/change_country_map")
async def change_country_map_photo(country_id: int = Form(...), file: UploadFile = File(...)):
    """
    Загружает карту страны (map_image_url) в таблице Countries.
    Сохранение файлов происходит в папке /media/maps/.
    """
    try:
        file_bytes = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("country_map", country_id)
        # Пример: "country_map_17_a4c3b8c73f...webp"

        # Сохраняем файл в подкаталог "maps"
        map_url = save_file(file_bytes, unique_filename, subdirectory="maps")

        # Обновляем поле map_image_url в таблице Countries
        update_country_map_image(country_id, map_url)

        return {
            "message": "Карта страны успешно загружена",
            "map_image_url": map_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 2) Добавить фотографию карты региона
@app.post("/photo/change_region_map")
async def change_region_map_photo(region_id: int = Form(...), file: UploadFile = File(...)):
    """
    Загружает карту региона (map_image_url) в таблице Regions.
    Сохранение файлов происходит в папке /media/maps/.
    """
    try:
        file_bytes = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("region_map", region_id)
        map_url = save_file(file_bytes, unique_filename, subdirectory="maps")

        update_region_map_image(region_id, map_url)

        return {
            "message": "Карта региона успешно загружена",
            "map_image_url": map_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 3) Добавить изображение для региона (image_url)
@app.post("/photo/change_region_image")
async def change_region_image(region_id: int = Form(...), file: UploadFile = File(...)):
    """
    Загружает обычное изображение региона (image_url) в таблице Regions.
    Сохранение файлов происходит в папке /media/locations/.
    """
    try:
        file_bytes = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("region_image", region_id)
        image_url = save_file(file_bytes, unique_filename, subdirectory="locations")

        update_region_image(region_id, image_url)

        return {
            "message": "Изображение региона успешно загружено",
            "image_url": image_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 4) Добавить изображение для района (District, image_url)
@app.post("/photo/change_district_image")
async def change_district_image(district_id: int = Form(...), file: UploadFile = File(...)):
    """
    Загружает изображение для района (image_url) в таблице Districts.
    Сохранение файлов происходит в папке /media/locations/.
    """
    try:
        file_bytes = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("district_image", district_id)
        image_url = save_file(file_bytes, unique_filename, subdirectory="locations")

        update_district_image(district_id, image_url)

        return {
            "message": "Изображение района успешно загружено",
            "image_url": image_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 5) Добавить изображение для локации (Location, image_url)
@app.post("/photo/change_location_image")
async def change_location_image(location_id: int = Form(...), file: UploadFile = File(...)):
    """
    Загружает изображение для локации (image_url) в таблице Locations.
    Сохранение файлов происходит в папке /media/locations/.
    """
    try:
        file_bytes = convert_to_webp(file.file)
        unique_filename = generate_unique_filename("location_image", location_id)
        image_url = save_file(file_bytes, unique_filename, subdirectory="locations")

        update_location_image(location_id, image_url)

        return {
            "message": "Изображение локации успешно загружено",
            "image_url": image_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))