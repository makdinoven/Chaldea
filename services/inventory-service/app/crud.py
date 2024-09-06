from sqlalchemy.orm import Session
import models
import schemas


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
