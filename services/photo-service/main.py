from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from crud import (
    update_user_avatar, get_user_avatar, update_user_avatar_preview,
    update_character_avatar, get_character_avatar, update_character_avatar_preview
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
