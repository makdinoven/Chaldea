from sqlalchemy.orm import Session
import models, schemas
import traceback
from constants import (
    BASE_HEALTH, BASE_MANA, BASE_ENERGY, BASE_STAMINA,
    BASE_DODGE, BASE_CRIT, BASE_CRIT_DMG,
    HEALTH_MULTIPLIER, MANA_MULTIPLIER, ENERGY_MULTIPLIER, STAMINA_MULTIPLIER,
    STAT_BONUS_PER_POINT, ALL_RESISTANCE_FIELDS,
    PHYSICAL_RESISTANCE_FIELDS, MAGICAL_RESISTANCE_FIELDS,
    ENDURANCE_RES_EFFECTS_MULTIPLIER,
)


def compute_derived_stats(attr):
    """
    Compute all derived stats on a CharacterAttributes ORM object
    from its base (upgradeable) stats. Sets resource maximums,
    combat stats, and resistances in-place.
    """
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

    # Physical resistances (boosted by Strength)
    for field in PHYSICAL_RESISTANCE_FIELDS:
        setattr(attr, field, round(attr.strength * b, 2))

    # Magical resistances (boosted by Intelligence)
    for field in MAGICAL_RESISTANCE_FIELDS:
        setattr(attr, field, round(attr.intelligence * b, 2))

    # res_effects: endurance * 0.2 + luck * 0.1
    attr.res_effects = round(
        attr.endurance * ENDURANCE_RES_EFFECTS_MULTIPLIER + attr.luck * b, 2
    )


# Функция для создания атрибутов персонажа

def create_character_attributes(db: Session, attributes: schemas.CharacterAttributesCreate):
    """
    Создает атрибуты персонажа с учетом переданных stat-поинтов.
    Derived stats (resistances, dodge, crit, resources) are computed
    from the base stats before committing.
    """
    # Создаем атрибуты персонажа с base stats
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
    )

    # Set current resources to max before compute (so clamp works correctly)
    db_attributes.current_health = int(BASE_HEALTH + attributes.health * HEALTH_MULTIPLIER)
    db_attributes.current_mana = int(BASE_MANA + attributes.mana * MANA_MULTIPLIER)
    db_attributes.current_energy = int(BASE_ENERGY + attributes.energy * ENERGY_MULTIPLIER)
    db_attributes.current_stamina = int(BASE_STAMINA + attributes.stamina * STAMINA_MULTIPLIER)

    # Compute all derived stats (resources, combat, resistances)
    compute_derived_stats(db_attributes)

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

    compute_derived_stats(attr)

    db.commit()
    db.refresh(attr)
    return attr