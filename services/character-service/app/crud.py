from sqlalchemy.orm import Session
import models, schemas


# Функция для создания заявки на персонажа
def create_character_request(db: Session, request: schemas.CharacterRequestCreate):
    """
    Создание заявки на создание персонажа.
    """
    db_request = models.CharacterRequest(**request.dict())
    db.add(db_request)
    db.commit()
    db.refresh(db_request)
    return db_request


# Функция для создания предварительного персонажа (без зависимостей)
def create_preliminary_character(db: Session, character_request: models.CharacterRequest):
    """
    Создает предварительную запись персонажа с отложенными полями для инвентаря, навыков и атрибутов.
    """
    new_character = models.Character(
        name=character_request.name,
        id_subrace=character_request.id_subrace,
        biography=character_request.biography,
        personality=character_request.personality,
        id_item_inventory=None,  # Поля для инвентаря, навыков и атрибутов остаются пустыми
        id_skill_inventory=None,
        id_attributes=None,
        id_class=character_request.id_class,
        currency_balance=0,
        request_id=character_request.id
    )
    db.add(new_character)
    db.commit()
    db.refresh(new_character)
    return new_character


# Функция для обновления персонажа после получения зависимостей
def update_character_with_dependencies(db: Session, character_id: int,
                                       inventory_id: int, skills_id: int, attributes_id: int):
    """
    Обновляет поля персонажа с полученными инвентарем, навыками и атрибутами.
    """
    db_character = db.query(models.Character).filter(models.Character.id == character_id).first()
    if db_character:
        db_character.id_item_inventory = inventory_id
        db_character.id_skill_inventory = skills_id
        db_character.id_attributes = attributes_id
        db.commit()
        db.refresh(db_character)
        return db_character
    return None


# Функция для удаления заявки после одобрения
def delete_character_request(db: Session, request_id: int):
    """
    Удаляет заявку на персонажа после её одобрения.
    """
    db_request = db.query(models.CharacterRequest).filter(models.CharacterRequest.id == request_id).first()
    if db_request:
        db.delete(db_request)
        db.commit()
        return True
    return False

# Функция для удаления персонажа
def delete_character(db: Session, character_id: int):
    """
    Удаление персонажа из базы данных по его ID.
    """
    db_character = db.query(models.Character).filter(models.Character.id == character_id).first()
    if db_character:
        db.delete(db_character)
        db.commit()
        return True
    return False
