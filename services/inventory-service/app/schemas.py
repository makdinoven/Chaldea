from pydantic import BaseModel
from typing import List, Optional

# Схема для отображения предмета в инвентаре
class ItemInInventory(BaseModel):
    id: int  # ID предмета
    quantity: int  # Количество предмета

    class Config:
        orm_mode = True  # Включаем режим ORM для поддержки работы с моделями SQLAlchemy

# Схема для отображения слота экипировки
class EquipmentSlotInInventory(BaseModel):
    slot_type: str
    item_id: Optional[int] = None  # ID предмета в слоте, может быть None, если слот пуст

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
    equipment_slots: List[EquipmentSlotInInventory]  # Список слотов экипировки

    class Config:
        orm_mode = True  # Включаем режим ORM для поддержки работы с моделями SQLAlchemy
