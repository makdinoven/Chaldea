from pydantic import BaseModel
from typing import Optional, List

# Схема для отображения предмета в инвентаре
class ItemInInventory(BaseModel):
    id: int
    name: str
    item_type: str
    quantity: int

    class Config:
        orm_mode = True  # Включаем режим ORM для поддержки работы с моделями SQLAlchemy


# Базовая схема для инвентаря персонажа
class CharacterInventoryBase(BaseModel):
    character_id: int
    items: List[ItemInInventory]  # Список предметов в инвентаре

# Схема для создания инвентаря персонажа
class CharacterInventoryCreate(CharacterInventoryBase):
    pass

# Схема для отображения инвентаря персонажа
class CharacterInventory(CharacterInventoryBase):
    id: int

    class Config:
        orm_mode = True  # Включаем режим ORM для поддержки работы с моделями SQLAlchemy
