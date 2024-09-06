from fastapi import FastAPI, Depends, HTTPException, APIRouter
from sqlalchemy.orm import Session
from . import models, schemas, crud
from .database import SessionLocal, engine
from .config import settings

# Создаем все таблицы в базе данных, если они еще не созданы
models.Base.metadata.create_all(bind=engine)

# Создаем экземпляр приложения FastAPI
app = FastAPI()

router = APIRouter(prefix="/attributes")


# Зависимость для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/attributes/", response_model=schemas.CharacterAttributes)
def generate_character_attributes(character_id: int, db: Session = Depends(get_db)):
    """
    Эндпоинт для генерации характеристик персонажа на основе ID расы.

    :param character_id: ID персонажа
    :param db: Сессия базы данных
    :return: Сгенерированные характеристики персонажа
    """
    # Проверка существования персонажа по его ID
    db_attributes = crud.create_character_attributes(db, schemas.CharacterAttributesCreate(character_id=character_id))
    return db_attributes
