from sqlalchemy.orm import Session
import models, schemas
import traceback

# Функция для создания атрибутов персонажа

def create_character_attributes(db: Session, attributes: schemas.CharacterAttributesCreate):
    """
    Создает атрибуты персонажа с учетом переданных stat-поинтов.
    """
    # Рассчитываем текущие и максимальные значения на основе stat points
    base_max_health = 100
    base_max_mana = 75
    base_max_energy = 50
    base_max_stamina = 50

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