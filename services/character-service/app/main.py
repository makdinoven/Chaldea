import httpx
from fastapi import FastAPI, Depends, APIRouter, HTTPException
from sqlalchemy.orm import Session
import asyncio
import models, schemas, crud
from database import SessionLocal, engine
from config import settings
from presets import SUBRACE_ATTRIBUTES, CLASS_ITEMS # Импортируем пресеты подрас
from typing import List, Dict
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

models.Base.metadata.create_all(bind=engine)

router = APIRouter(prefix="/characters")
# Зависимость для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Создание заявки на персонажа
@router.post("/requests/", response_model=schemas.CharacterRequest)
async def create_character_request(request: schemas.CharacterRequestCreate, db: Session = Depends(get_db)):
    """
    Создание заявки на персонажа.
    """
    try:
        user_id = request.user_id
        db_request = crud.create_character_request(db, request, user_id)
        return db_request
    except Exception as e:
        print(f"Ошибка при создании заявки: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании заявки на персонажа.")

# Эндпоинт для одобрения заявки
@router.post("/requests/{request_id}/approve")
async def approve_character_request(request_id: int, db: Session = Depends(get_db)):
    try:
        print(f"[INFO] Начало обработки заявки с ID {request_id}")

        db_request = db.query(models.CharacterRequest).filter(models.CharacterRequest.id == request_id).first()
        if not db_request:
            print(f"[ERROR] Заявка с ID {request_id} не найдена")
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        print(f"[INFO] Заявка с ID {request_id} найдена")

        new_character = crud.create_preliminary_character(db, db_request)
        print(f"[INFO] Создан персонаж с ID {new_character.id}")

        attributes = crud.generate_attributes_for_subrace(db_request.id_subrace)
        print(f"[INFO] Сгенерированы атрибуты для подрасы {db_request.id_subrace}: {attributes}")

        items_to_add = CLASS_ITEMS.get(new_character.id_class, [])
        print(f"[INFO] Стартовая экипировка для класса {new_character.id_class}: {items_to_add}")

        # Отправка запроса на создание инвентаря
        inventory_response = await crud.send_inventory_request(new_character.id, items_to_add)
        if inventory_response:
            print(f"[INFO] Инвентарь создан: {inventory_response}")
        else:
            print("[ERROR] Ошибка при создании инвентаря")
            raise HTTPException(status_code=500, detail="Не удалось создать инвентарь")

        # Отправка запросов на создание навыков и атрибутов
        skills_response = await crud.send_skills_request(new_character.id)
        if skills_response:
            print(f"[INFO] Навыки созданы: {skills_response}")
        else:
            print("[ERROR] Ошибка при создании навыков")
            raise HTTPException(status_code=500, detail="Не удалось создать навыки")

        attributes_response = await crud.send_attributes_request(new_character.id, attributes)
        if attributes_response:
            print(f"[INFO] Атрибуты созданы: {attributes_response}")
        else:
            print("[ERROR] Ошибка при создании атрибутов")
            raise HTTPException(status_code=500, detail="Не удалось создать атрибуты")

        # Обновляем персонажа с зависимостями
        updated_character = crud.update_character_with_dependencies(
            db, new_character.id,
            skills_id=skills_response['id'],
            attributes_id=attributes_response['id']
        )
        print(f"[INFO] Персонаж с ID {new_character.id} обновлен с зависимостями")

        crud.update_character_request_status(db, request_id, "approved")
        print(f"[INFO] Заявка с ID {request_id} одобрена")

        # Присваиваем персонажа пользователю
        assign_result = await crud.assign_character_to_user(db_request.user_id, updated_character.id)
        if assign_result:
            print(f"[INFO] Персонаж с ID {updated_character.id} успешно присвоен пользователю {db_request.user_id}")
        else:
            print("[ERROR] Не удалось присвоить персонажа пользователю")
            raise HTTPException(status_code=500, detail="Не удалось присвоить персонажа пользователю")

        print(f"[INFO] Завершение обработки заявки с ID {request_id}")
        return {"message": f"Персонаж с ID {new_character.id} успешно создан и присвоен пользователю."}

    except Exception as e:
        print(f"[ERROR] Ошибка при одобрении заявки: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

# Эндпоинт для удаления персонажа
@router.delete("/{character_id}")
async def delete_character(character_id: int, db: Session = Depends(get_db)):
    """
    Удаление персонажа по его ID.
    """
    try:
        result = crud.delete_character(db, character_id)
        if not result:
            raise HTTPException(status_code=404, detail="Персонаж не найден")
        return {"message": f"Персонаж с ID {character_id} успешно удален."}
    except Exception as e:
        print(f"Ошибка при удалении персонажа: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

# Отправка запроса на обновление пользователя в user-service
async def update_user_with_character(user_id: int, character_id: int):
    try:
        # Отправляем запрос в микросервис пользователей для добавления записи в таблицу user_characters
        async with httpx.AsyncClient() as client:
            print(f"Отправляем запрос на создание связи между пользователем {user_id} и персонажем {character_id}")
            create_relation_response = await client.post(
                f"{settings.USER_SERVICE_URL}/users/user_characters/",
                json={"user_id": user_id, "character_id": character_id}
            )

            if create_relation_response.status_code not in [200, 201]:
                print(f"Ошибка при создании записи в user_characters: {create_relation_response.status_code}")
                return False

            print(f"Запись в user_characters успешно создана для пользователя {user_id} и персонажа {character_id}")

            # Второй запрос: обновляем поле current_character у пользователя
            print(f"Отправляем запрос на обновление current_character для пользователя {user_id} с персонажем {character_id}")
            update_user_response = await client.put(
                f"{settings.USER_SERVICE_URL}/users/{user_id}/update_character",
                json={"current_character": character_id}
            )

            if update_user_response.status_code == 200:
                print(f"Пользователь с ID {user_id} успешно обновлен с персонажем ID {character_id}")
                return True
            else:
                print(f"Ошибка при обновлении пользователя: {update_user_response.status_code}")
                print(f"Ответ от сервера: {update_user_response.text}")
                return False

    except Exception as e:
        print(f"Ошибка при отправке запросов на обновление пользователя: {e}")
        return False


@router.post("/requests/{request_id}/reject")
async def reject_character_request(request_id: int, db: Session = Depends(get_db)):
    """
    Отклоняет заявку на создание персонажа и обновляет статус на 'rejected'.
    """
    try:
        db_request = crud.update_character_request_status(db, request_id, "rejected")
        if not db_request:
            raise HTTPException(status_code=404, detail="Заявка не найдена")

        return {"message": f"Заявка с ID {request_id} была отклонена."}

    except Exception as e:
        print(f"Ошибка при отклонении заявки: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при отклонении заявки")

#Возвращает список всех рас, их подрас и атрибуты для каждой подрасы.
@router.get("/metadata", response_model=dict)
async def get_races_and_subraces(db: Session = Depends(get_db)):

    try:
        races_data = crud.get_all_races_and_subraces(db)
        # Добавляем атрибуты к каждой подрасе на основе ее id
        for race_id, race_info in races_data.items():
            for subrace in race_info["subraces"]:
                subrace_attributes = SUBRACE_ATTRIBUTES.get(subrace["id_subrace"], {})
                subrace["attributes"] = subrace_attributes

        return races_data
    except Exception as e:
        print(f"Ошибка при получении рас и подрас: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении рас и подрас.")


@router.get("/moderation-requests", response_model=Dict)
async def get_moderation_requests(db: Session = Depends(get_db)):
    """
    Эндпоинт для получения всех заявок на модерации
    """
    try:
        requests = crud.get_moderation_requests(db)  # Вызов функции из CRUD для получения заявок

        if not requests:
            raise HTTPException(status_code=404, detail="Заявки на модерацию не найдены")

        return requests
    except Exception as e:
        print(f"Ошибка при получении заявок на модерацию: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении заявок на модерацию.")


@router.post("/titles/", response_model=schemas.Title)
async def create_title(request: schemas.TitleCreate, db: Session = Depends(get_db)):
    """
    Создание нового титула.
    """
    try:
        title = crud.create_title(db, request.name, request.description)
        return title
    except Exception as e:
        print(f"Ошибка при создании титула: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании титула.")

@router.post("/{character_id}/titles/{title_id}")
async def assign_title(character_id: int, title_id: int, db: Session = Depends(get_db)):
    """
    Присваивает титул персонажу.
    """
    try:
        assignment = crud.assign_title_to_character(db, character_id, title_id)
        if not assignment:
            raise HTTPException(status_code=404, detail="Персонаж или титул не найден")
        return {"message": f"Титул с ID {title_id} успешно присвоен персонажу с ID {character_id}."}
    except Exception as e:
        print(f"Ошибка при присвоении титула: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при присвоении титула персонажу.")


@router.post("/{character_id}/current-title/{title_id}")
async def set_current_title(character_id: int, title_id: int, db: Session = Depends(get_db)):
    """
    Устанавливает текущий титул для персонажа.
    """
    try:
        character = crud.set_current_title(db, character_id, title_id)
        if not character:
            raise HTTPException(status_code=404, detail="Персонаж не найден")
        return {"message": f"Титул с ID {title_id} успешно установлен как текущий для персонажа с ID {character_id}."}
    except Exception as e:
        print(f"Ошибка при установке текущего титула: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при установке титула.")

@router.get("/titles/", response_model=List[schemas.Title])
async def get_titles(db: Session = Depends(get_db)):
    """
    Получить список всех титулов.
    """
    try:
        titles = crud.get_all_titles(db)
        return titles
    except Exception as e:
        print(f"Ошибка при получении титулов: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении титулов.")

@router.get("/{character_id}/titles", response_model=List[schemas.Title])
async def get_titles_for_character(character_id: int, db: Session = Depends(get_db)):
    """
    Получить все титулы для конкретного персонажа.
    """
    try:
        titles = crud.get_titles_for_character(db, character_id)
        if not titles:
            raise HTTPException(status_code=404, detail="Персонаж не имеет титулов")
        return titles
    except Exception as e:
        print(f"Ошибка при получении титулов для персонажа {character_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении титулов для персонажа.")

app.include_router(router)
