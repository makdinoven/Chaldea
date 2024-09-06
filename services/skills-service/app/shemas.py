from pydantic import BaseModel

# Базовая схема для навыков персонажа
class CharacterSkillsBase(BaseModel):
    character_id: int
    skill_1: str = "Basic Attack"
    skill_2: str = "Basic Defense"
    skill_3: str = "Basic Heal"

# Схема для создания навыков персонажа
class CharacterSkillsCreate(CharacterSkillsBase):
    pass

# Схема для отображения навыков персонажа
class CharacterSkills(CharacterSkillsBase):
    id: int

    class Config:
        orm_mode = True  # Включаем режим ORM для поддержки работы с моделями SQLAlchemy
