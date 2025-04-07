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