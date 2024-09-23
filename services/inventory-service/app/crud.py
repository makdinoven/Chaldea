from sqlalchemy.orm import Session
import models
import schemas


# Получить инвентарь по ID персонажа
def get_inventory_by_character_id(db: Session, character_id: int):
    return db.query(models.CharacterInventory).filter(models.CharacterInventory.character_id == character_id).first()


# Функция для создания инвентаря персонажа
def create_character_inventory(db: Session, inventory: schemas.CharacterInventoryCreate):
    """
    Создает инвентарь персонажа и сохраняет его в базе данных.

    :param db: Сессия базы данных
    :param inventory: Схема Pydantic с данными для создания инвентаря
    :return: Созданный инвентарь персонажа
    """
    db_inventory = models.CharacterInventory(**inventory.dict())  # Преобразуем Pydantic модель в SQLAlchemy модель
    db.add(db_inventory)  # Добавляем запись в сессию
    db.commit()  # Фиксируем изменения в базе данных
    db.refresh(db_inventory)  # Обновляем объект, чтобы получить данные из базы
    return db_inventory  # Возвращаем созданный инвентарь

def create_equipment_slot(db: Session, slot_data: dict):
    """
    Создает слот экипировки для персонажа.

    :param db: Сессия базы данных
    :param slot_data: Данные для создания слота экипировки
    :return: Созданный слот экипировки
    """
    equipment_slot = models.EquipmentSlot(
        character_id=slot_data["character_id"],
        slot_type=slot_data["slot_type"],
        item_id=slot_data.get("item_id")  # Если есть предмет, иначе None
    )
    db.add(equipment_slot)  # Добавляем слот в сессию
    db.commit()  # Фиксируем изменения
    db.refresh(equipment_slot)  # Обновляем объект, чтобы получить данные из базы
    return equipment_slot  # Возвращаем созданный слот
