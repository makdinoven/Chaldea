from sqlalchemy.orm import Session
import models, schemas


# Функция для создания характеристик персонажа
def create_character_attributes(db: Session, attributes: schemas.CharacterAttributesCreate):
    """
    Создает характеристики персонажа и сохраняет их в базе данных.

    :param db: Сессия базы данных
    :param attributes: Схема Pydantic с данными для создания характеристик
    :return: Созданные характеристики персонажа
    """
    db_attributes = models.CharacterAttributes(**attributes.dict())  # Преобразуем Pydantic модель в SQLAlchemy модель
    db.add(db_attributes)  # Добавляем запись в сессию
    db.commit()  # Фиксируем изменения в базе данных
    db.refresh(db_attributes)  # Обновляем объект, чтобы получить данные из базы
    return db_attributes  # Возвращаем созданные характеристики
