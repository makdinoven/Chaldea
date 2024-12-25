from fastapi import FastAPI, Depends, HTTPException, APIRouter
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import models, schemas, crud
from database import SessionLocal, engine
import traceback
from fastapi.middleware.cors import CORSMiddleware
from config import settings
import httpx
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Измените на нужные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Создание всех таблиц в базе данных
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
@router.post("/", response_model=schemas.CharacterAttributesResponse)
def create_character_attributes(attributes: schemas.CharacterAttributesCreate, db: Session = Depends(get_db)):
    """
    Эндпоинт для создания атрибутов персонажа.
    """
    try:
        # Логирование входящего запроса
        logger.info(
            f"Запрос на создание атрибутов для персонажа с ID {attributes.character_id} с данными: {attributes}")

        # Создание атрибутов персонажа
        db_attributes = crud.create_character_attributes(db, attributes)

        # Логирование успешного создания
        logger.info(f"Атрибуты для персонажа с ID {attributes.character_id} успешно созданы: {db_attributes}")

        return db_attributes
    except SQLAlchemyError as e:
        # Логирование ошибки и стек вызовов
        logger.error(f"Ошибка при создании атрибутов для персонажа ID {attributes.character_id}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")

# Эндпоинт для получения passive_experience персонажа
@router.get("/{character_id}/passive_experience", response_model=schemas.PassiveExperienceResponse)
def get_passive_experience_endpoint(character_id: int, db: Session = Depends(get_db)):
    """
    Получить passive_experience персонажа.
    """
    logger.info(f"Получение passive_experience для персонажа ID {character_id}")
    passive_experience = crud.get_passive_experience(db, character_id)
    if passive_experience is None:
        logger.error(f"Passive experience для персонажа ID {character_id} не найден.")
        raise HTTPException(status_code=404, detail="Passive experience not found")
    return {"passive_experience": passive_experience}

# Эндпоинт для получения всех атрибутов персонажа
@router.get("/{character_id}", response_model=schemas.CharacterAttributesResponse)
def get_full_attributes(character_id: int, db: Session = Depends(get_db)):
    attr = db.query(models.CharacterAttributes).filter(models.CharacterAttributes.character_id == character_id).first()
    if not attr:
        raise HTTPException(status_code=404, detail="Attributes not found")
    return attr

# Эндпоинт для прокачки статов
@router.post("/{character_id}/upgrade", response_model=schemas.AttributesResponse)
async def upgrade_attributes(
    character_id: int,
    upgrade_request: schemas.StatsUpgradeRequest,
    db: Session = Depends(get_db)
):
    """
    Прокачка статов за счет stat_points.
    """
    logger.info(f"Получен запрос на прокачку статов для персонажа ID {character_id}: {upgrade_request}")

    # 1. Получаем текущие stat_points из character-service
    try:
        async with httpx.AsyncClient() as client:
            full_profile_url = f"{settings.CHARACTER_SERVICE_URL}/characters/{character_id}/full_profile"
            logger.info(f"Отправка запроса на получение профиля персонажа по URL: {full_profile_url}")
            resp = await client.get(full_profile_url)
            if resp.status_code != 200:
                logger.error(f"Не удалось получить профиль персонажа ID {character_id}: {resp.status_code} - {resp.text}")
                raise HTTPException(status_code=404, detail="Character not found in character-service")
            char_data = resp.json()
            available_stat_points = char_data.get("stat_points", 0)
            logger.info(f"У персонажа ID {character_id} доступно stat_points: {available_stat_points}")
    except httpx.RequestError as e:
        logger.exception(f"Ошибка при запросе к character-service: {e}")
        raise HTTPException(status_code=500, detail="Failed to communicate with character-service")

    # 2. Считаем, сколько stat_points нужно
    total_needed = (
        upgrade_request.strength +
        upgrade_request.agility +
        upgrade_request.intelligence +
        upgrade_request.endurance +
        upgrade_request.health +
        upgrade_request.energy +
        upgrade_request.mana +
        upgrade_request.stamina +
        upgrade_request.charisma +
        upgrade_request.luck
    )
    logger.info(f"Общее количество stat_points, необходимых для прокачки: {total_needed}")

    if total_needed == 0:
        logger.info("Нет статов для прокачки.")
        raise HTTPException(status_code=400, detail="No stats to upgrade.")

    if available_stat_points < total_needed:
        logger.warning(f"Недостаточно stat_points: требуется {total_needed}, доступно {available_stat_points}")
        raise HTTPException(status_code=400, detail="Not enough stat points")

    # 3. Спишем stat_points в character-service
    try:
        async with httpx.AsyncClient() as client:
            # Исправленный URL с добавлением '/characters/'
            deduct_points_url = f"{settings.CHARACTER_SERVICE_URL}/characters/{character_id}/deduct_points"
            payload = {"points_to_deduct": total_needed}
            logger.info(f"Отправка запроса на списание stat_points: {deduct_points_url} с данными: {payload}")
            resp = await client.put(deduct_points_url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Не удалось списать stat_points: {resp.status_code} - {resp.text}")
                raise HTTPException(status_code=500, detail="Failed to deduct stat points from character-service")
            deduct_response = resp.json()
            remaining_points = deduct_response.get("remaining_points", available_stat_points - total_needed)
            logger.info(f"stat_points успешно списаны. Остаток stat_points: {remaining_points}")
    except httpx.RequestError as e:
        logger.exception(f"Ошибка при запросе к character-service для списания stat_points: {e}")
        raise HTTPException(status_code=500, detail="Failed to communicate with character-service")

    # 4. Применяем прокачку атрибутов внутри транзакции
    try:
        # Начинаем транзакцию
        with db.begin():
            attr = db.query(models.CharacterAttributes).filter(models.CharacterAttributes.character_id == character_id).with_for_update().first()
            if not attr:
                logger.error(f"Атрибуты персонажа ID {character_id} не найдены в character-attributes сервисе.")
                raise HTTPException(status_code=404, detail="Attributes not found")

            logger.info(f"Прокачка атрибутов для персонажа ID {character_id}: {upgrade_request}")

            # Применяем изменения
            attr.res_physical += upgrade_request.strength * 0.1
            attr.dodge += upgrade_request.agility * 0.1
            attr.res_magic += upgrade_request.intelligence * 0.1
            attr.res_effects += upgrade_request.endurance * 0.1

            attr.health += upgrade_request.health
            attr.max_health += upgrade_request.health * 10
            attr.current_health += upgrade_request.health * 10

            attr.energy += upgrade_request.energy
            attr.max_energy += upgrade_request.energy * 5
            attr.current_energy += upgrade_request.energy * 5

            attr.mana += upgrade_request.mana
            attr.max_mana += upgrade_request.mana * 10
            attr.current_mana += upgrade_request.mana * 10

            attr.stamina += upgrade_request.stamina
            attr.max_stamina += upgrade_request.stamina * 5
            attr.current_stamina += upgrade_request.stamina * 5

            attr.charisma += upgrade_request.charisma
            # За каждое +1 luck => +0.1% к крит.шансам и уклонению
            attr.critical_hit_chance += upgrade_request.luck * 0.1
            attr.dodge += upgrade_request.luck * 0.1

            # Округляем нужные поля до целого
            attr.current_health = int(attr.current_health)
            attr.max_health = int(attr.max_health)
            attr.current_mana = int(attr.current_mana)
            attr.max_mana = int(attr.max_mana)
            attr.current_energy = int(attr.current_energy)
            attr.max_energy = int(attr.max_energy)
            attr.current_stamina = int(attr.current_stamina)
            attr.max_stamina = int(attr.max_stamina)
            attr.health = int(attr.health)
            attr.mana = int(attr.mana)
            attr.energy = int(attr.energy)
            attr.stamina = int(attr.stamina)

            # Другие поля остаются float

        # После транзакции, обновляем объект из базы данных
        db.refresh(attr)
        logger.info(f"Атрибуты персонажа ID {character_id} успешно обновлены.")
    except SQLAlchemyError as e:
        logger.exception(f"Ошибка при обновлении атрибутов персонажа ID {character_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to upgrade attributes")

    # Формируем ответ
    updated_attributes = {
        "health": attr.health,
        "max_health": attr.max_health,
        "current_health": attr.current_health,
        "mana": attr.mana,
        "max_mana": attr.max_mana,
        "current_mana": attr.current_mana,
        "energy": attr.energy,
        "max_energy": attr.max_energy,
        "stamina": attr.stamina,
        "max_stamina": attr.max_stamina,
        "current_stamina": attr.current_stamina,
        "res_physical": attr.res_physical,
        "dodge": attr.dodge,
        "res_magic": attr.res_magic,
        "res_effects": attr.res_effects,
        "charisma": attr.charisma,
        "critical_hit_chance": attr.critical_hit_chance
    }

    return schemas.AttributesResponse(
        message="Stats upgraded successfully",
        stat_points_remaining=remaining_points,
        updated_attributes=updated_attributes
    )

# Эндпоинт для получения количества доступных stat_points (опционально)
@router.get("/{character_id}/stat_points")
async def get_stat_points(character_id: int, db: Session = Depends(get_db)):
    """
    Получить количество доступных stat_points персонажа.
    """
    logger.info(f"Получение stat_points для персонажа ID {character_id}")

    # Получаем текущие stat_points из character-service
    try:
        async with httpx.AsyncClient() as client:
            full_profile_url = f"{settings.CHARACTER_SERVICE_URL}/characters/{character_id}/full_profile"
            logger.info(f"Отправка запроса на получение профиля персонажа по URL: {full_profile_url}")
            resp = await client.get(full_profile_url)
            if resp.status_code != 200:
                logger.error(f"Не удалось получить профиль персонажа ID {character_id}: {resp.status_code} - {resp.text}")
                raise HTTPException(status_code=404, detail="Character not found in character-service")
            char_data = resp.json()
            available_stat_points = char_data.get("stat_points", 0)
            logger.info(f"У персонажа ID {character_id} доступно stat_points: {available_stat_points}")
    except httpx.RequestError as e:
        logger.exception(f"Ошибка при запросе к character-service: {e}")
        raise HTTPException(status_code=500, detail="Failed to communicate with character-service")

    return {"stat_points": available_stat_points}

# Регистрируем роутер
app.include_router(router)
