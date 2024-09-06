from fastapi import FastAPI, Depends, HTTPException, APIRouter
from sqlalchemy.orm import Session
from . import models, schemas, crud
from .database import SessionLocal, engine
from .config import settings

# Создаем все таблицы в базе данных, если они еще не созданы
models.Base.metadata.create_all(bind=engine)

# Создаем экземпляр приложения FastAPI
app = FastAPI()

router = APIRouter(prefix="/skills")

# Зависимость для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/skills/", response_model=schemas.CharacterSkills)
def generate_character_skills(character_id: int, db: Session = Depends(get_db)):
    """
    Эндпоинт для генерации навыков персонажа на основе ID расы.

    :param character_id: ID персонажа
    :param db: Сессия базы данных
    :return: Сгенерированные навыки персонажа
    """
    # Для примера создаем базовые навыки
    skills = schemas.CharacterSkillsCreate(character_id=character_id)
    return crud.create_character_skills(db, skills)
