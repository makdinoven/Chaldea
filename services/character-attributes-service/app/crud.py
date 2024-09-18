from sqlalchemy.orm import Session
import models, schemas
import traceback

# Функция для создания атрибутов персонажа
def create_character_attributes(db: Session, attributes: schemas.CharacterAttributesCreate):
    """
    Создает атрибуты персонажа и сохраняет их в базе данных.
    """
    try:
        # Логируем перед сохранением в базу данных
        print(f"Создание атрибутов для персонажа с ID {attributes.character_id}: {attributes}")

        db_attributes = models.CharacterAttributes(**attributes.dict())  # Преобразование схемы в SQLAlchemy модель
        db.add(db_attributes)  # Добавляем запись в сессию
        db.commit()  # Фиксируем изменения в базе данных
        db.refresh(db_attributes)  # Обновляем объект для получения данных из базы

        print(f"Атрибуты для персонажа с ID {attributes.character_id} успешно сохранены: {db_attributes}")
        return db_attributes
    except Exception as e:
        # Логируем ошибку
        print(f"Ошибка при сохранении атрибутов для персонажа с ID {attributes.character_id}: {str(e)}")
        traceback.print_exc()
        raise e

