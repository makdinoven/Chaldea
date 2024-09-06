from fastapi import FastAPI, Depends, HTTPException, APIRouter
from sqlalchemy.orm import Session
from . import models, schemas, crud
from .database import SessionLocal, engine
from .config import settings

# Создаем все таблицы в базе данных, если они еще не созданы
models.Base.metadata.create_all(bind=engine)

# Создаем экземпляр приложения FastAPI
app = FastAPI()

router = APIRouter(prefix="/inventory")


# Зависимость для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/inventory/", response_model=schemas.CharacterInventory)
def generate_character_inventory(character_id: int, db: Session = Depends(get_db)):
    """
    Эндпоинт для генерации инвентаря персонажа на основе ID расы.

    :param character_id: ID персонажа
    :param db: Сессия базы данных
    :return: Сгенерированный инвентарь персонажа
    """
    # Для примера создаем базовый инвентарь
    inventory = schemas.CharacterInventoryCreate(character_id=character_id)
    return crud.create_character_inventory(db, inventory)
