from sqlalchemy.orm import Session
import models, schemas

# Получить навыки по ID персонажа
def get_skills_by_character_id(db: Session, character_id: int):
    return db.query(models.CharacterSkills).filter(models.CharacterSkills.character_id == character_id).first()

# Функция для создания навыков персонажа
def create_character_skills(db: Session, skills: schemas.CharacterSkillsCreate):
    """
    Создает навыки персонажа и сохраняет их в базе данных.

    :param db: Сессия базы данных
    :param skills: Схема Pydantic с данными для создания навыков
    :return: Созданные навыки персонажа
    """
    db_skills = models.CharacterSkills(**skills.dict())  # Преобразуем Pydantic модель в SQLAlchemy модель
    db.add(db_skills)  # Добавляем запись в сессию
    db.commit()  # Фиксируем изменения в базе данных
    db.refresh(db_skills)  # Обновляем объект, чтобы получить данные из базы
    return db_skills  # Возвращаем созданные навыки
