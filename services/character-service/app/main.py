import httpx
from fastapi import FastAPI, Depends, APIRouter, HTTPException
from sqlalchemy.orm import Session
import asyncio
import models, schemas, crud
from database import SessionLocal, engine
from config import settings
from presets import SUBRACE_ATTRIBUTES  # Импортируем пресеты подрас

app = FastAPI()

models.Base.metadata.create_all(bind=engine)

router = APIRouter(prefix="/character")

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
    """
    Подтверждает заявку на создание персонажа, обновляет статус и данные о навыках, инвентаре и атрибутах.
    """
    try:
        # Найдем заявку по её ID
        db_request = db.query(models.CharacterRequest).filter(models.CharacterRequest.id == request_id).first()
        if not db_request:
            raise HTTPException(status_code=404, detail="Заявка не найдена")

        # Создаем предварительного персонажа с указанием user_id
        new_character = crud.create_preliminary_character(db, db_request)

        # Генерируем атрибуты на основе subrace_id
        attributes = generate_attributes_for_subrace(db_request.id_subrace)

        # Отправляем запросы на микросервисы для генерации зависимостей
        inventory_response = await send_inventory_request(new_character.id)
        skills_response = await send_skills_request(new_character.id)
        attributes_response = await send_attributes_request(new_character.id, attributes)

        # Проверяем ответы от всех микросервисов
        if not (inventory_response and skills_response and attributes_response):
            raise HTTPException(status_code=500, detail="Не удалось получить ответы от одного или нескольких микросервисов")

        # Обновляем персонажа с зависимостями
        updated_character = crud.update_character_with_dependencies(
            db, new_character.id,
            inventory_id=inventory_response['id'],
            skills_id=skills_response['id'],
            attributes_id=attributes_response['id']
        )

        # Обновляем статус заявки на "approved"
        crud.update_character_request_status(db, request_id, "approved")

        # Присваиваем персонажа пользователю
        assign_result = await assign_character_to_user(db_request.user_id, updated_character.id)
        if not assign_result:
            raise HTTPException(status_code=500, detail="Не удалось присвоить персонажа пользователю")

        return {"message": f"Персонаж с ID {new_character.id} успешно создан и присвоен пользователю."}

    except Exception as e:
        print(f"Ошибка при одобрении заявки: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

# Отправка запроса на микросервис инвентаря
async def send_inventory_request(character_id: int):
    try:
        async with httpx.AsyncClient() as client:
            print(f"Отправка запроса на инвентарь для персонажа {character_id}")  # Лог перед отправкой запроса
            response = await client.post(f"{settings.INVENTORY_SERVICE_URL}", json={"character_id": character_id})

            # Логируем статус-код и тело ответа
            print(f"Статус-код ответа от сервиса инвентаря: {response.status_code}")
            print(f"Тело ответа от сервиса инвентаря: {response.text}")

            if response.status_code == 200:
                return response.json()
            else:
                print(
                    f"Ошибка при запросе инвентаря: {response.status_code} - {response.text}")  # Более детализированный лог
                return None
    except Exception as e:
        print(f"Ошибка при отправке запроса на инвентарь: {e}")
        return None


# Отправка запроса на микросервис навыков
async def send_skills_request(character_id: int):
    try:
        async with httpx.AsyncClient() as client:
            print(f"Отправка запроса на навыки для персонажа {character_id}")  # Лог перед отправкой запроса
            response = await client.post(f"{settings.SKILLS_SERVICE_URL}", json={"character_id": character_id})

            # Логируем статус-код и тело ответа
            print(f"Статус-код ответа от сервиса навыков: {response.status_code}")
            print(f"Тело ответа от сервиса навыков: {response.text}")

            if response.status_code == 200:
                return response.json()
            else:
                print(
                    f"Ошибка при запросе навыков: {response.status_code} - {response.text}")  # Более детализированный лог
                return None
    except Exception as e:
        print(f"Ошибка при отправке запроса на навыки: {e}")
        return None


# Отправка запроса на микросервис атрибутов
async def send_attributes_request(character_id: int, attributes: dict):
    try:
        attributes["character_id"] = character_id  # Вставляем character_id в тело запроса
        async with httpx.AsyncClient() as client:
            print(f"Отправка запроса на создание атрибутов для персонажа {character_id} с атрибутами: {attributes}")

            response = await client.post(f"{settings.ATTRIBUTES_SERVICE_URL}", json=attributes)

            print(f"Статус-код ответа от сервиса атрибутов: {response.status_code}")
            print(f"Тело ответа: {response.text}")

            if response.status_code == 200:
                return response.json()
            else:
                return None
    except Exception as e:
        print(f"Ошибка при отправке запроса на атрибуты: {e}")
        return None


# Генерация атрибутов на основе подрасы
def generate_attributes_for_subrace(subrace_id: int) -> dict:
    """
    Генерирует атрибуты для персонажа на основе его подрасы.
    """
    # Возвращаем атрибуты из пресетов или дефолтные значения, если подраса не найдена
    return SUBRACE_ATTRIBUTES.get(subrace_id, {
        "strength": 10, "agility": 10, "intelligence": 10,
        "endurance": 100, "health": 100, "energy": 50, "mana": 75,
        "stamina": 100, "charisma": 10, "luck": 10
    })

# Отправка запроса в user-service для присвоения персонажа пользователю
async def assign_character_to_user(user_id: int, character_id: int):
    try:
        async with httpx.AsyncClient() as client:
            # Формируем запрос
            response = await client.put(
                f"{settings.USER_SERVICE_URL}/users/{user_id}/update_character",
                json={"character_id": character_id}
            )
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Ошибка при обновлении пользователя: {response.status_code}, {response.text}")
                return None
    except Exception as e:
        print(f"Ошибка при отправке запроса в user-service: {e}")
        return None

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
        async with httpx.AsyncClient() as client:
            response = await client.put(f"{settings.USER_SERVICE_URL}users/{user_id}/update_character", json={"character_id": character_id})
            if response.status_code == 200:
                print(f"Пользователь с ID {user_id} успешно обновлен с персонажем ID {character_id}")
                return True
            else:
                print(f"Ошибка при обновлении пользователя: {response.status_code}")
                return False
    except Exception as e:
        print(f"Ошибка при отправке запроса на обновление пользователя: {e}")
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


app.include_router(router)
