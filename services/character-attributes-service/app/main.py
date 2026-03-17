import os
import asyncio
import threading
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
from rabbitmq_consumer import start_consumer
from auth_http import get_admin_user, UserRead

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

models.Base.metadata.create_all(bind=engine)


def _run_consumer_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_consumer())


@app.on_event("startup")
def startup():
    thread = threading.Thread(target=_run_consumer_thread, daemon=True)
    thread.start()


router = APIRouter(prefix="/attributes")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------
# 1. Создание атрибутов
# -----------------------------
@router.post("/", response_model=schemas.CharacterAttributesResponse)
def create_character_attributes(attributes: schemas.CharacterAttributesCreate, db: Session = Depends(get_db)):
    try:
        logger.info(f"Создание атрибутов для персонажа ID {attributes.character_id}")
        db_attributes = crud.create_character_attributes(db, attributes)
        return db_attributes
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при создании атрибутов: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")

# -----------------------------
# 2. Получение passive_experience
# -----------------------------
@router.get("/{character_id}/passive_experience", response_model=schemas.PassiveExperienceResponse)
def get_passive_experience_endpoint(character_id: int, db: Session = Depends(get_db)):
    logger.info(f"Получение passive_experience для персонажа ID {character_id}")
    passive_experience = crud.get_passive_experience(db, character_id)
    if passive_experience is None:
        raise HTTPException(status_code=404, detail="Passive experience not found")
    return {"passive_experience": passive_experience}

# -----------------------------
# 3. Получение всех атрибутов
# -----------------------------
@router.get("/{character_id}", response_model=schemas.CharacterAttributesResponse)
def get_full_attributes(character_id: int, db: Session = Depends(get_db)):
    attr = db.query(models.CharacterAttributes).filter(models.CharacterAttributes.character_id == character_id).first()
    if not attr:
        raise HTTPException(status_code=404, detail="Attributes not found")
    return attr

# -----------------------------
# 4. Прокачка (upgrade)
# -----------------------------
@router.post("/{character_id}/upgrade", response_model=schemas.AttributesResponse)
async def upgrade_attributes(character_id: int, upgrade_request: schemas.StatsUpgradeRequest, db: Session = Depends(get_db)):
    logger.info(f"Запрос на прокачку статов у персонажа {character_id}")
    # --- Логика прокачки из вашего примера (запрос в character-service, списание stat_points, и т.д.) ---
    try:
        async with httpx.AsyncClient() as client:
            full_profile_url = f"{settings.CHARACTER_SERVICE_URL}/characters/{character_id}/full_profile"
            resp = await client.get(full_profile_url)
            if resp.status_code != 200:
                raise HTTPException(status_code=404, detail="Character not found")
            char_data = resp.json()
            available_stat_points = char_data.get("stat_points", 0)
    except httpx.RequestError as e:
        logger.exception(f"Ошибка при запросе к character-service: {e}")
        raise HTTPException(status_code=500, detail="Failed to communicate with character-service")

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
    if total_needed == 0:
        raise HTTPException(status_code=400, detail="No stats to upgrade")
    if available_stat_points < total_needed:
        raise HTTPException(status_code=400, detail="Not enough stat points")

    # Списываем stat_points
    try:
        async with httpx.AsyncClient() as client:
            deduct_url = f"{settings.CHARACTER_SERVICE_URL}/characters/{character_id}/deduct_points"
            payload = {"points_to_deduct": total_needed}
            resp = await client.put(deduct_url, json=payload)
            if resp.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to deduct stat points")
            deduct_response = resp.json()
            remaining_points = deduct_response.get("remaining_points", available_stat_points - total_needed)
    except httpx.RequestError as e:
        logger.exception(f"Ошибка при списании stat_points: {e}")
        raise HTTPException(status_code=500, detail="Failed to communicate with character-service")

    # Применяем прокачку (транзакция)
    try:
        with db.begin():
            attr = db.query(models.CharacterAttributes).filter(
                models.CharacterAttributes.character_id == character_id
            ).with_for_update().first()
            if not attr:
                raise HTTPException(status_code=404, detail="Attributes not found")

            # Код из вашего примера
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
            attr.critical_hit_chance += upgrade_request.luck * 0.1
            attr.dodge += upgrade_request.luck * 0.1

            # Округляем
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

        db.refresh(attr)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to upgrade attributes")

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


# -----------------------------
# 5. apply_modifiers (общий)
# -----------------------------
HEALTH_MULTIPLIER = 10
MANA_MULTIPLIER = 10
ENERGY_MULTIPLIER = 5
STAMINA_MULTIPLIER = 5

@router.post("/{character_id}/apply_modifiers")
def apply_modifiers(character_id: int, modifiers: dict, db: Session = Depends(get_db)):
    """
    Применяем модификаторы к CharacterAttributes.
    'health', 'mana', 'energy', 'stamina' => пересчитываем max_/current_.
    Остальные поля (strength, damage, res_fire и т.д.) просто складываем.
    """
    with db.begin():
        attr = db.query(models.CharacterAttributes).filter(
            models.CharacterAttributes.character_id == character_id
        ).with_for_update().first()

        if not attr:
            raise HTTPException(status_code=404, detail="Character attributes not found")

        # ------- health -------
        delta_health = modifiers.get("health", 0)
        if delta_health != 0:
            old_health = attr.health
            new_health = old_health + delta_health
            if new_health < 0:
                new_health = 0

            old_max_health = attr.max_health
            diff = (new_health - old_health) * HEALTH_MULTIPLIER
            new_max_health = old_max_health + diff

            new_current_health = attr.current_health + diff
            if new_current_health < 0:
                new_current_health = 0
            if new_current_health > new_max_health:
                new_current_health = new_max_health

            attr.health = new_health
            attr.max_health = new_max_health
            attr.current_health = new_current_health

        # ------- mana -------
        delta_mana = modifiers.get("mana", 0)
        if delta_mana != 0:
            old_mana = attr.mana
            new_mana = old_mana + delta_mana
            if new_mana < 0:
                new_mana = 0

            old_max_mana = attr.max_mana
            diff = (new_mana - old_mana) * MANA_MULTIPLIER
            new_max_mana = old_max_mana + diff

            new_current_mana = attr.current_mana + diff
            if new_current_mana < 0:
                new_current_mana = 0
            if new_current_mana > new_max_mana:
                new_current_mana = new_max_mana

            attr.mana = new_mana
            attr.max_mana = new_max_mana
            attr.current_mana = new_current_mana

        # ------- energy -------
        delta_energy = modifiers.get("energy", 0)
        if delta_energy != 0:
            old_energy = attr.energy
            new_energy = old_energy + delta_energy
            if new_energy < 0:
                new_energy = 0

            old_max_energy = attr.max_energy
            diff = (new_energy - old_energy) * ENERGY_MULTIPLIER
            new_max_energy = old_max_energy + diff

            new_current_energy = attr.current_energy + diff
            if new_current_energy < 0:
                new_current_energy = 0
            if new_current_energy > new_max_energy:
                new_current_energy = new_max_energy

            attr.energy = new_energy
            attr.max_energy = new_max_energy
            attr.current_energy = new_current_energy

        # ------- stamina -------
        delta_stamina = modifiers.get("stamina", 0)
        if delta_stamina != 0:
            old_stamina = attr.stamina
            new_stamina = old_stamina + delta_stamina
            if new_stamina < 0:
                new_stamina = 0

            old_max_stamina = attr.max_stamina
            diff = (new_stamina - old_stamina) * STAMINA_MULTIPLIER
            new_max_stamina = old_max_stamina + diff

            new_current_stamina = attr.current_stamina + diff
            if new_current_stamina < 0:
                new_current_stamina = 0
            if new_current_stamina > new_max_stamina:
                new_current_stamina = new_max_stamina

            attr.stamina = new_stamina
            attr.max_stamina = new_max_stamina
            attr.current_stamina = new_current_stamina

        # ------- Остальные (strength, agility, damage, dodge, resistances, etc.) -------
        # Просто складываем. Перечислим все поля, которые есть в модели:
        simple_keys = [
            "strength",
            "agility",
            "intelligence",
            "endurance",
            "charisma",
            "luck",
            "damage",
            "dodge",
            "res_effects",
            "res_physical",
            "res_catting",
            "res_crushing",
            "res_piercing",
            "res_magic",
            "res_fire",
            "res_ice",
            "res_watering",    # в модели "res_watering"
            "res_electricity",
            "res_wind",
            "res_sainting",
            "res_damning",
            "critical_hit_chance",
            "critical_damage",
            "vul_effects",
            "vul_physical",
            "vul_catting",
            "vul_crushing",
            "vul_piercing",
            "vul_magic",
            "vul_fire",
            "vul_ice",
            "vul_watering",
            "vul_electricity",
            "vul_sainting",
            "vul_wind",
            "vul_damning"
            # ... если есть ещё поля, которые просто суммируются, добавьте.
        ]

        for key in simple_keys:
            if key in modifiers and modifiers[key] != 0:
                old_val = getattr(attr, key, 0)
                setattr(attr, key, old_val + modifiers[key])

        db.flush()

    db.refresh(attr)
    return {"detail": "Modifiers applied successfully"}

# -----------------------------
# 6. Восстановление (recover)
# -----------------------------
@router.post("/{character_id}/recover")
def recover_resources(character_id: int, recovery: dict, db: Session = Depends(get_db)):
    """
    Восстанавливаем здоровье, ману, энергию, выносливость (current_*) но не превышаем max_*.
    """
    with db.begin():
        attr = db.query(models.CharacterAttributes).filter(
            models.CharacterAttributes.character_id == character_id
        ).with_for_update().first()
        if not attr:
            raise HTTPException(status_code=404, detail="Character attributes not found")

        health_rec = recovery.get("health_recovery", 0)
        mana_rec = recovery.get("mana_recovery", 0)
        energy_rec = recovery.get("energy_recovery", 0)
        stamina_rec = recovery.get("stamina_recovery", 0)

        new_health = min(attr.current_health + health_rec, attr.max_health)
        attr.current_health = max(0, new_health)

        new_mana = min(attr.current_mana + mana_rec, attr.max_mana)
        attr.current_mana = max(0, new_mana)

        new_energy = min(attr.current_energy + energy_rec, attr.max_energy)
        attr.current_energy = max(0, new_energy)

        new_stamina = min(attr.current_stamina + stamina_rec, attr.max_stamina)
        attr.current_stamina = max(0, new_stamina)

        db.flush()

    db.refresh(attr)
    return {"detail": "Resources recovered successfully"}

@router.put("/{character_id}/active_experience")
def update_active_experience(
    character_id: int,
    request: schemas.UpdateActiveExperienceRequest,
    db: Session = Depends(get_db)
):
    """
    Увеличивает или уменьшает active_experience на указанное значение.
    request.amount > 0 => добавляем
    request.amount < 0 => снимаем
    """
    attr = db.query(models.CharacterAttributes).filter(
        models.CharacterAttributes.character_id == character_id
    ).first()

    if not attr:
        raise HTTPException(status_code=404, detail="Character attributes not found")

    new_value = attr.active_experience + request.amount
    if new_value < 0:
        # На ваше усмотрение: либо разрешаем уходить в минус, либо блокируем
        raise HTTPException(status_code=400, detail="active_experience cannot be negative")

    attr.active_experience = new_value

    db.commit()
    db.refresh(attr)

    return {
        "detail": "Active experience updated",
        "active_experience": attr.active_experience
    }


@router.post("/{character_id}/consume_stamina")
def consume_stamina(character_id: int, payload: dict, db: Session = Depends(get_db)):
    """
    Списывает указанное количество выносливости (stamina) у персонажа.

    Запрос:
      {
          "amount": <целое число>
      }

    Если у персонажа недостаточно выносливости, возвращается ошибка.
    В случае успеха возвращается сообщение и оставшаяся выносливость.
    """
    amount = payload.get("amount")
    if amount is None or not isinstance(amount, int):
        raise HTTPException(status_code=400, detail="Поле 'amount' обязательно и должно быть целым числом")

    attr = db.query(models.CharacterAttributes).filter(models.CharacterAttributes.character_id == character_id).first()
    if not attr:
        raise HTTPException(status_code=404, detail="Атрибуты персонажа не найдены")

    if attr.current_stamina < amount:
        raise HTTPException(status_code=400, detail="Недостаточно выносливости для списания")

    attr.current_stamina -= amount
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка при списании выносливости: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении выносливости")
    db.refresh(attr)

    return {
        "detail": "Выносливость списана успешно",
        "current_stamina": attr.current_stamina
    }

# -----------------------------
# 7. Admin: обновление атрибутов (partial update, без ограничений прокачки)
# -----------------------------
@router.put("/admin/{character_id}", response_model=schemas.CharacterAttributesResponse)
def admin_update_attributes(
    character_id: int,
    data: schemas.AdminAttributeUpdate,
    db: Session = Depends(get_db),
    admin: UserRead = Depends(get_admin_user),
):
    attr = db.query(models.CharacterAttributes).filter(
        models.CharacterAttributes.character_id == character_id
    ).first()
    if not attr:
        raise HTTPException(status_code=404, detail="Attributes not found")

    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(attr, field, value)

    try:
        db.commit()
        db.refresh(attr)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при админском обновлении атрибутов: {e}")
        raise HTTPException(status_code=500, detail="Failed to update attributes")

    return attr


# -----------------------------
# 8. Admin: удаление атрибутов
# -----------------------------
@router.delete("/{character_id}")
def admin_delete_attributes(
    character_id: int,
    db: Session = Depends(get_db),
    admin: UserRead = Depends(get_admin_user),
):
    attr = db.query(models.CharacterAttributes).filter(
        models.CharacterAttributes.character_id == character_id
    ).first()
    if not attr:
        raise HTTPException(status_code=404, detail="Attributes not found")

    try:
        db.delete(attr)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при удалении атрибутов: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete attributes")

    return {"detail": "Attributes deleted"}


app.include_router(router)
