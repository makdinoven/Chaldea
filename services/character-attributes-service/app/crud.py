from sqlalchemy.orm import Session
import models, schemas
import traceback
from constants import (
    BASE_HEALTH, BASE_MANA, BASE_ENERGY, BASE_STAMINA,
    BASE_DODGE, BASE_CRIT, BASE_CRIT_DMG,
    HEALTH_MULTIPLIER, MANA_MULTIPLIER, ENERGY_MULTIPLIER, STAMINA_MULTIPLIER,
    STAT_BONUS_PER_POINT, ALL_RESISTANCE_FIELDS,
)

# Функция для создания атрибутов персонажа

def create_character_attributes(db: Session, attributes: schemas.CharacterAttributesCreate):
    """
    Создает атрибуты персонажа с учетом переданных stat-поинтов.
    """
    # Рассчитываем текущие и максимальные значения на основе stat points
    base_max_health = BASE_HEALTH
    base_max_mana = BASE_MANA
    base_max_energy = BASE_ENERGY
    base_max_stamina = BASE_STAMINA

    max_health = base_max_health + (attributes.health * 10)
    current_health = max_health

    max_mana = base_max_mana + (attributes.mana * 10)
    current_mana = max_mana

    max_energy = base_max_energy + (attributes.energy * 5)
    current_energy = max_energy

    max_stamina = base_max_stamina + (attributes.stamina * 5)
    current_stamina = max_stamina

    # Создаем атрибуты персонажа
    db_attributes = models.CharacterAttributes(
        character_id=attributes.character_id,
        strength=attributes.strength,
        agility=attributes.agility,
        intelligence=attributes.intelligence,
        endurance=attributes.endurance,
        health=attributes.health,
        mana=attributes.mana,
        energy=attributes.energy,
        stamina=attributes.stamina,
        charisma=attributes.charisma,
        luck=attributes.luck,
        current_health=current_health,
        max_health=max_health,
        current_mana=current_mana,
        max_mana=max_mana,
        current_energy=current_energy,
        max_energy=max_energy,
        current_stamina=current_stamina,
        max_stamina=max_stamina,
        # остальные поля уже имеют дефолтные значения
    )

    db.add(db_attributes)
    db.commit()
    db.refresh(db_attributes)
    return db_attributes
def get_passive_experience(db: Session, character_id: int):
    """
    Получает passive_experience персонажа.
    """
    attr = db.query(models.CharacterAttributes).filter(models.CharacterAttributes.character_id == character_id).first()
    if not attr:
        return None
    return attr.passive_experience

def update_passive_experience(db: Session, character_id: int, new_passive_experience: int):
    """
    Обновляет passive_experience персонажа.
    """
    attr = db.query(models.CharacterAttributes).filter(models.CharacterAttributes.character_id == character_id).first()
    if not attr:
        return None
    attr.passive_experience = new_passive_experience
    db.commit()
    db.refresh(attr)
    return attr.passive_experience


def recalculate_attributes(db: Session, character_id: int):
    """
    Пересчитывает все производные статы из базовых значений (10 прокачиваемых статов).
    Не учитывает модификаторы экипировки — предназначен для админского использования
    при изменении формул.
    """
    attr = db.query(models.CharacterAttributes).filter(
        models.CharacterAttributes.character_id == character_id
    ).with_for_update().first()

    if not attr:
        return None

    b = STAT_BONUS_PER_POINT

    # Resource stats
    attr.max_health = int(BASE_HEALTH + attr.health * HEALTH_MULTIPLIER)
    attr.max_mana = int(BASE_MANA + attr.mana * MANA_MULTIPLIER)
    attr.max_energy = int(BASE_ENERGY + attr.energy * ENERGY_MULTIPLIER)
    attr.max_stamina = int(BASE_STAMINA + attr.stamina * STAMINA_MULTIPLIER)

    # Clamp current to not exceed new max
    attr.current_health = min(attr.current_health, attr.max_health)
    attr.current_mana = min(attr.current_mana, attr.max_mana)
    attr.current_energy = min(attr.current_energy, attr.max_energy)
    attr.current_stamina = min(attr.current_stamina, attr.max_stamina)

    # Combat stats
    attr.dodge = round(BASE_DODGE + attr.agility * b + attr.luck * b, 2)
    attr.critical_hit_chance = round(BASE_CRIT + attr.luck * b, 2)
    attr.critical_damage = BASE_CRIT_DMG  # Only modified by items

    # Resistances
    attr.res_physical = round(attr.strength * b + attr.endurance * b, 2)
    attr.res_magic = round(attr.intelligence * b + attr.endurance * b, 2)

    # res_effects: endurance reduces enemy effect proc (negative), luck adds own chance
    attr.res_effects = round(attr.endurance * b + attr.luck * b, 2)

    # All other resistances = endurance * 0.1
    endurance_res = round(attr.endurance * b, 2)
    attr.res_catting = endurance_res
    attr.res_crushing = endurance_res
    attr.res_piercing = endurance_res
    attr.res_fire = endurance_res
    attr.res_ice = endurance_res
    attr.res_watering = endurance_res
    attr.res_electricity = endurance_res
    attr.res_sainting = endurance_res
    attr.res_wind = endurance_res
    attr.res_damning = endurance_res

    db.commit()
    db.refresh(attr)
    return attr