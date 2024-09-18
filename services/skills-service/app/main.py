from fastapi import FastAPI, Depends, HTTPException, APIRouter
from sqlalchemy.orm import Session
import models, schemas, crud
from database import SessionLocal, engine

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


@router.post("/", response_model=schemas.CharacterSkills)
def generate_character_skills(skills_request: schemas.CharacterSkillsCreate, db: Session = Depends(get_db)):
    """
    Эндпоинт для генерации навыков персонажа на основе ID персонажа.

    :param skills_request: Данные для создания навыков
    :param db: Сессия базы данных
    :return: Сгенерированные навыки персонажа
    """
    # Проверяем, существуют ли навыки для данного персонажа
    existing_skills = crud.get_skills_by_character_id(db, skills_request.character_id)
    if existing_skills:
        raise HTTPException(status_code=400, detail="Навыки для данного персонажа уже существуют")

    # Создаем навыки персонажа
    db_skills = crud.create_character_skills(db, skills_request)
    return db_skills

app.include_router(router)
