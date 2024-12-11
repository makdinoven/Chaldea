from fastapi import FastAPI, Depends, HTTPException, APIRouter
from sqlalchemy.orm import Session
import models, schemas, crud
from database import SessionLocal, engine
import traceback
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Создаем все таблицы в базе данных, если они еще не созданы
models.Base.metadata.create_all(bind=engine)


router = APIRouter(prefix="/attributes")

# Зависимость для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Эндпоинт для создания атрибутов персонажа
@router.post("/", response_model=schemas.CharacterAttributes)
def create_character_attributes(attributes: schemas.CharacterAttributesCreate, db: Session = Depends(get_db)):
    """
    Эндпоинт для создания атрибутов персонажа.
    """
    try:
        # Логируем входящий запрос
        print(f"Запрос на создание атрибутов для персонажа с ID {attributes.character_id} с данными: {attributes}")

        # Создаем атрибуты персонажа
        db_attributes = crud.create_character_attributes(db, attributes)

        # Логируем успешное создание атрибутов
        print(f"Атрибуты для персонажа с ID {attributes.character_id} успешно созданы: {db_attributes}")

        return db_attributes
    except Exception as e:
        # Логируем ошибку и стек вызовов для отладки
        print(f"Ошибка при создании атрибутов для персонажа: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


app.include_router(router)