from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field
from datetime import datetime

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
    current_health: Optional[int] = 100
    max_health: Optional[int] = 100
    current_mana: Optional[int] = 75
    max_mana: Optional[int] = 75
    current_energy: Optional[int] = 50
    max_energy: Optional[int] = 50
    current_stamina: Optional[int] = 100
    max_stamina: Optional[int] = 100
    passive_experience: Optional[int] = 0
    active_experience: Optional[int] = 0
    dodge: Optional[float] = 5.0
    critical_hit_chance: Optional[float] = 20.0
    critical_damage: Optional[float] = 125.0
    damage: Optional[int] = 0

    res_effects: Optional[float] = 0.0
    res_physical: Optional[float] = 0.0
    res_catting: Optional[float] = 0.0
    res_crushing: Optional[float] = 0.0
    res_piercing: Optional[float] = 0.0
    res_magic: Optional[float] = 0.0
    res_fire: Optional[float] = 0.0
    res_ice: Optional[float] = 0.0
    res_watering: Optional[float] = 0.0
    res_electricity: Optional[float] = 0.0
    res_sainting: Optional[float] = 0.0
    res_wind: Optional[float] = 0.0
    res_damning: Optional[float] = 0.0

    vul_effects: Optional[float] = 0.0
    vul_physical: Optional[float] = 0.0
    vul_catting: Optional[float] = 0.0
    vul_crushing: Optional[float] = 0.0
    vul_piercing: Optional[float] = 0.0
    vul_magic: Optional[float] = 0.0
    vul_fire: Optional[float] = 0.0
    vul_ice: Optional[float] = 0.0
    vul_watering: Optional[float] = 0.0
    vul_electricity: Optional[float] = 0.0
    vul_sainting: Optional[float] = 0.0
    vul_wind: Optional[float] = 0.0
    vul_damning: Optional[float] = 0.0

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


# --- Perk Schemas ---

class PerkCondition(BaseModel):
    type: str  # 'cumulative_stat', 'character_level', 'attribute', 'quest', 'admin_grant'
    stat: Optional[str] = None
    operator: str  # '>=', '<=', '==', '>', '<'
    value: Any


class PerkBonuses(BaseModel):
    flat: Dict[str, Any] = Field(default_factory=dict)  # {"health": 10, "damage": 3}
    percent: Dict[str, Any] = Field(default_factory=dict)  # {"strength": 5}
    contextual: Dict[str, Any] = Field(default_factory=dict)  # {"damage_vs_pve": 5}
    passive: Dict[str, Any] = Field(default_factory=dict)  # {"regen_hp_per_turn": 2}


class PerkCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: str  # 'combat', 'trade', 'exploration', 'progression', 'usage'
    rarity: str = "common"  # 'common', 'rare', 'legendary'
    icon: Optional[str] = None
    conditions: List[PerkCondition]
    bonuses: PerkBonuses
    sort_order: int = 0


class PerkUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    rarity: Optional[str] = None
    icon: Optional[str] = None
    conditions: Optional[List[PerkCondition]] = None
    bonuses: Optional[PerkBonuses] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class PerkResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    category: str
    rarity: str
    icon: Optional[str] = None
    conditions: List[Any]
    bonuses: Dict[str, Any]
    sort_order: int
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class PerkConditionProgress(BaseModel):
    current: Any
    required: Any


class CharacterPerkResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    category: str
    rarity: str
    icon: Optional[str] = None
    conditions: List[Any]
    bonuses: Dict[str, Any]
    is_unlocked: bool
    unlocked_at: Optional[datetime] = None
    is_custom: bool = False
    progress: Dict[str, PerkConditionProgress] = Field(default_factory=dict)

    class Config:
        orm_mode = True


class CumulativeStatsResponse(BaseModel):
    character_id: int
    total_damage_dealt: int = 0
    total_damage_received: int = 0
    pve_kills: int = 0
    pvp_wins: int = 0
    pvp_losses: int = 0
    total_battles: int = 0
    max_damage_single_battle: int = 0
    max_win_streak: int = 0
    current_win_streak: int = 0
    total_rounds_survived: int = 0
    low_hp_wins: int = 0
    total_gold_earned: int = 0
    total_gold_spent: int = 0
    items_bought: int = 0
    items_sold: int = 0
    locations_visited: int = 0
    total_transitions: int = 0
    skills_used: int = 0
    items_equipped: int = 0

    class Config:
        orm_mode = True


class CumulativeStatsIncrement(BaseModel):
    character_id: int
    increments: Dict[str, int] = Field(default_factory=dict)
    set_max: Optional[Dict[str, int]] = Field(default_factory=dict)