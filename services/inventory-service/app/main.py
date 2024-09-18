from fastapi import FastAPI, Depends, HTTPException, APIRouter
from sqlalchemy.orm import Session
import models
import schemas
import crud
from database import SessionLocal, engine

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


@router.post("/", response_model=schemas.CharacterInventory)
def generate_character_inventory(inventory_request: schemas.CharacterInventoryCreate, db: Session = Depends(get_db)):
    """
    Эндпоинт для генерации инвентаря персонажа на основе ID персонажа.

    :param inventory_request: Схема с данными для создания инвентаря
    :param db: Сессия базы данных
    :return: Сгенерированный инвентарь персонажа
    """
    # Проверяем, существует ли персонаж с переданным ID
    existing_inventory = crud.get_inventory_by_character_id(db, inventory_request.character_id)
    if existing_inventory:
        raise HTTPException(status_code=400, detail="Инвентарь для данного персонажа уже существует")

    # Создаем инвентарь персонажа
    db_inventory = crud.create_character_inventory(db, inventory_request)
    return db_inventory

app.include_router(router)
