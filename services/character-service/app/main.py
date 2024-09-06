from fastapi import FastAPI, Depends, APIRouter
from sqlalchemy.orm import Session
import asyncio
from . import models, schemas, crud
from .database import SessionLocal, engine
from .rabbitmq_producer import send_to_rabbitmq

app = FastAPI()

router = APIRouter(prefix="/character")


# Зависимость для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/requests/", response_model=schemas.CharacterRequest)
async def create_character_request(request: schemas.CharacterRequestCreate, db: Session = Depends(get_db)):
    """
    Создание заявки на персонажа. Отправляет запрос в RabbitMQ на обработку заявки.
    """
    # Сохраняем заявку в базе данных
    db_request = crud.create_character_request(db, request)

    # Формируем сообщение для отправки в RabbitMQ
    message = {
        "request_id": db_request.id,
        "name": db_request.name,
        "id_subrace": db_request.id_subrace,
        "biography": db_request.biography,
        "personality": db_request.personality,
        "id_class": db_request.id_class,
        "status": db_request.status,
        "action": "create_request"
    }

    # Отправляем запрос в очередь RabbitMQ для обработки заявки
    asyncio.create_task(send_to_rabbitmq("character_request_queue", message))

    return db_request

@app.post("/requests/{request_id}/approve")
async def approve_character_request(request_id: int, db: Session = Depends(get_db)):
    """
    Подтверждает заявку на создание персонажа и отправляет запрос на создание персонажа в очереди RabbitMQ.
    """
    # Подтверждаем заявку и создаем запись персонажа в базе данных
    character = crud.approve_character_request(db, request_id)

    # Формируем сообщение для отправки в очереди RabbitMQ
    message = {
        "character_id": character.id,
        "name": character.name,
        "id_subrace": character.id_subrace,
        "biography": character.biography,
        "personality": character.personality,
        "id_class": character.id_class,
        "action": "create_character"
    }

    # Отправляем сообщения для создания характеристик, навыков и инвентаря
    asyncio.create_task(send_to_rabbitmq("character_attributes_queue", message))
    asyncio.create_task(send_to_rabbitmq("character_skills_queue", message))
    asyncio.create_task(send_to_rabbitmq("character_inventory_queue", message))

    return {"message": f"Персонаж с ID {character.id} создается."}