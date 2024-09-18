from pydantic import BaseModel

# Базовая схема для характеристик персонажа
class CharacterAttributesBase(BaseModel):
    character_id: int
    health: int = 100
    mana: int = 75
    energy: int = 50
    stamina: int = 50
    endurance: int = 100
    strength: int = 10
    agility: int = 10
    intelligence: int = 10
    luck: int = 10
    charisma: int = 10

    damage: int = 0
    dodge: int = 5
    critical_hit_chance: int = 20
    critical_damage: int = 125

    res_effects: int = 0
    res_physical: int = 0
    res_cutting: int = 0
    res_crushing: int = 0
    res_piersing: int = 0
    res_magic: int = 0
    res_fire: int = 0
    res_ice: int = 0
    res_watering: int = 0
    res_electricity: int = 0
    res_sainting: int = 0
    res_wind: int = 0
    res_damning: int = 0

# Схема для создания характеристик персонажа
class CharacterAttributesCreate(CharacterAttributesBase):
    pass

# Схема для отображения характеристик персонажа
class CharacterAttributes(CharacterAttributesBase):
    id: int

    class Config:
        orm_mode = True  # Включаем режим ORM для поддержки работы с моделями SQLAlchemy
