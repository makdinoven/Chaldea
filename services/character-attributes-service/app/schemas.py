from typing import Optional, Dict
from pydantic import BaseModel, Field

# Базовая схема для характеристик персонажа
class CharacterAttributesBase(BaseModel):
    strength: Optional[int] = Field(10, ge=0, description="Сила")
    agility: Optional[int] = Field(10, ge=0, description="Ловкость")
    intelligence: Optional[int] = Field(10, ge=0, description="Интеллект")
    endurance: Optional[int] = Field(100, ge=0, description="Живучесть")
    health: Optional[int] = Field(10, ge=0, description="Прокачка здоровья")
    mana: Optional[int] = Field(7, ge=0, description="Прокачка маны")
    energy: Optional[int] = Field(5, ge=0, description="Прокачка энергии")
    stamina: Optional[int] = Field(10, ge=0, description="Прокачка выносливости")
    charisma: Optional[int] = Field(1, ge=0, description="Харизма")
    luck: Optional[int] = Field(1, ge=0, description="Удача")
    damage: Optional[int] = Field(0, ge=0, description = "Базовый урон персонажа")

    class Config:
        schema_extra = {
            "example": {
                "strength": 3,
                "health": 5
            }
        }

# Схема для создания характеристик персонажа
class CharacterAttributesCreate(CharacterAttributesBase):
    character_id: int

    class Config:
        schema_extra = {
            "example": {
                "character_id": 1,
                "strength": 3,
                "health": 5
            }
        }

# Схема для отображения характеристик персонажа
class CharacterAttributesResponse(CharacterAttributesBase):
    id: int
    character_id: int
    current_health: int
    max_health: int
    current_mana: int
    max_mana: int
    current_energy: int
    max_energy: int
    current_stamina: int
    max_stamina: int
    passive_experience: int
    active_experience: int
    dodge: float
    critical_hit_chance: float
    critical_damage: float
    damage: int

    res_effects: float
    res_physical: float
    res_catting: float
    res_crushing: float
    res_piercing: float
    res_magic: float
    res_fire: float
    res_ice: float
    res_watering: float
    res_electricity: float
    res_sainting: float
    res_wind: float
    res_damning: float

    vul_effects: float
    vul_physical: float
    vul_catting: float
    vul_crushing: float
    vul_piercing: float
    vul_magic: float
    vul_fire: float
    vul_ice: float
    vul_watering: float
    vul_electricity: float
    vul_sainting: float
    vul_wind: float
    vul_damning: float

    class Config:
        orm_mode = True

# Схема запроса на прокачку статов
class StatsUpgradeRequest(BaseModel):
    strength: Optional[int] = 0
    agility: Optional[int] = 0
    intelligence: Optional[int] = 0
    endurance: Optional[int] = 0
    health: Optional[int] = 0
    energy: Optional[int] = 0
    mana: Optional[int] = 0
    stamina: Optional[int] = 0
    charisma: Optional[int] = 0
    luck: Optional[int] = 0

    class Config:
        orm_mode = True

# Схема ответа на прокачку статов
class AttributesResponse(BaseModel):
    message: str
    stat_points_remaining: int
    updated_attributes: Dict[str, Optional[float]]

# Схема ответа на запрос passive_experience
class PassiveExperienceResponse(BaseModel):
    passive_experience: int

class UpdateActiveExperienceRequest(BaseModel):
    amount: int  # Положительное число означает "добавить", отрицательное — "снять".


# Схема для админского обновления атрибутов (все поля Optional — partial update)
class AdminAttributeUpdate(BaseModel):
    # Resources
    health: Optional[int] = None
    max_health: Optional[int] = None
    current_health: Optional[int] = None
    mana: Optional[int] = None
    max_mana: Optional[int] = None
    current_mana: Optional[int] = None
    energy: Optional[int] = None
    max_energy: Optional[int] = None
    current_energy: Optional[int] = None
    stamina: Optional[int] = None
    max_stamina: Optional[int] = None
    current_stamina: Optional[int] = None
    # Base stats
    strength: Optional[int] = None
    agility: Optional[int] = None
    intelligence: Optional[int] = None
    endurance: Optional[int] = None
    charisma: Optional[int] = None
    luck: Optional[int] = None
    # Combat
    damage: Optional[int] = None
    dodge: Optional[float] = None
    critical_hit_chance: Optional[float] = None
    critical_damage: Optional[float] = None
    # Experience
    passive_experience: Optional[int] = None
    active_experience: Optional[int] = None
    # Resistances
    res_effects: Optional[float] = None
    res_physical: Optional[float] = None
    res_catting: Optional[float] = None
    res_crushing: Optional[float] = None
    res_piercing: Optional[float] = None
    res_magic: Optional[float] = None
    res_fire: Optional[float] = None
    res_ice: Optional[float] = None
    res_watering: Optional[float] = None
    res_electricity: Optional[float] = None
    res_sainting: Optional[float] = None
    res_wind: Optional[float] = None
    res_damning: Optional[float] = None
    # Vulnerabilities
    vul_effects: Optional[float] = None
    vul_physical: Optional[float] = None
    vul_catting: Optional[float] = None
    vul_crushing: Optional[float] = None
    vul_piercing: Optional[float] = None
    vul_magic: Optional[float] = None
    vul_fire: Optional[float] = None
    vul_ice: Optional[float] = None
    vul_watering: Optional[float] = None
    vul_electricity: Optional[float] = None
    vul_sainting: Optional[float] = None
    vul_wind: Optional[float] = None
    vul_damning: Optional[float] = None