from pydantic import BaseModel

# Базовая схема для характеристик персонажа
class CharacterAttributesBase(BaseModel):
    character_id: int
    health: int = 100
    mana: int = 100
    energy: int = 100
    strength: int = 10
    agility: int = 10
    intelligence: int = 10
    luck: int = 10
    charisma: int = 10

# Схема для создания характеристик персонажа
class CharacterAttributesCreate(CharacterAttributesBase):
    pass

# Схема для отображения характеристик персонажа
class CharacterAttributes(CharacterAttributesBase):
    id: int

    class Config:
        orm_mode = True  # Включаем режим ORM для поддержки работы с моделями SQLAlchemy
