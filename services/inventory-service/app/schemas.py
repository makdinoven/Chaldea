from pydantic import BaseModel

# Базовая схема для инвентаря персонажа
class CharacterInventoryBase(BaseModel):
    character_id: int
    item_1: str = "Basic Sword"
    item_2: str = "Basic Shield"
    item_3: str = "Health Potion"

# Схема для создания инвентаря персонажа
class CharacterInventoryCreate(CharacterInventoryBase):
    pass

# Схема для отображения инвентаря персонажа
class CharacterInventory(CharacterInventoryBase):
    id: int

    class Config:
        orm_mode = True  # Включаем режим ORM для поддержки работы с моделями SQLAlchemy
