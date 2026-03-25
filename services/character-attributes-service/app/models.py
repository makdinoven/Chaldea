from sqlalchemy import (
    Column, Integer, Float, String, Text, Boolean, DateTime, JSON, BigInteger,
    ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.sql import func
from database import Base

# Определяем модель для хранения характеристик персонажа
class CharacterAttributes(Base):
    __tablename__ = "character_attributes"

    id = Column(Integer, primary_key=True, index=True)  # Первичный ключ
    character_id = Column(Integer, unique=True, index=True)  # ID персонажа

    passive_experience = Column(Integer, default=0)  # Пасивный опыт
    active_experience = Column(Integer, default=0)  # Активный опыт

    current_health = Column(Integer, default=100)
    current_mana = Column(Integer, default=75)
    current_energy = Column(Integer, default=50)
    current_stamina = Column(Integer, default=100)

    # Максимальные значения
    max_health = Column(Integer, default=100)
    max_mana = Column(Integer, default=75)
    max_energy = Column(Integer, default=50)
    max_stamina = Column(Integer, default=100)

    #Прокачиваемые статы

    health = Column(Integer, default=0)  # Здоровье
    mana = Column(Integer, default=0)  # Мана
    energy = Column(Integer, default=0)  # Энергия
    stamina = Column(Integer, default=0) #Выносливость
    endurance = Column(Integer, default=0)  # Живучесть
    strength = Column(Integer, default=0)  # Сила
    agility = Column(Integer, default=0)  # Ловкость
    intelligence = Column(Integer, default=0)  # Интеллект
    luck = Column(Integer, default=0)  # Везучесть
    charisma = Column(Integer, default=0)  # Харизма


    # Боевые характеристики
    damage = Column(Integer, default=0)  # Урон
    dodge = Column(Float, default=5.0)  # Уклонение (%)
    critical_hit_chance = Column(Float, default=20.0)  # Шанс крит удара (%)
    critical_damage = Column(Integer, default=125)  # Урон крит удара

    # Сопротивления
    res_effects = Column(Float, default=0.0)  # Сопротивление эффектам (%)
    res_physical = Column(Float, default=0.0)  # Сопротивление физическому урону (%)
    res_catting = Column(Float, default=0.0)  # Сопротивление режущему (%)
    res_crushing = Column(Float, default=0.0)  # Сопротивление дробящему (%)
    res_piercing = Column(Float, default=0.0)  # Сопротивление колющему (%)
    res_magic = Column(Float, default=0.0)  # Сопротивление магическому (%)
    res_fire = Column(Float, default=0.0)  # Сопротивление огню (%)
    res_ice = Column(Float, default=0.0)  # Сопротивление льду (%)
    res_watering = Column(Float, default=0.0)  # Сопротивление воде (%)
    res_electricity = Column(Float, default=0.0)  # Сопротивление электрическому (%)
    res_sainting = Column(Float, default=0.0)  # Сопротивление святому (%)
    res_wind = Column(Float, default=0.0)  # Сопротивление ветру (%)
    res_damning = Column(Float, default=0.0)  # Сопротивление проклятому (%)

    vul_effects = Column(Float, default=0.0)
    vul_physical = Column(Float, default=0.0)
    vul_catting = Column(Float, default=0.0)
    vul_crushing = Column(Float, default=0.0)
    vul_piercing = Column(Float, default=0.0)
    vul_magic = Column(Float, default=0.0)
    vul_fire = Column(Float, default=0.0)
    vul_ice = Column(Float, default=0.0)
    vul_watering = Column(Float, default=0.0)
    vul_electricity = Column(Float, default=0.0)
    vul_sainting = Column(Float, default=0.0)
    vul_wind = Column(Float, default=0.0)
    vul_damning = Column(Float, default=0.0)


class Perk(Base):
    __tablename__ = "perks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False)  # 'combat', 'trade', 'exploration', 'progression', 'usage'
    rarity = Column(String(20), nullable=False, server_default="common")  # 'common', 'rare', 'legendary'
    icon = Column(String(255), nullable=True)
    conditions = Column(JSON, nullable=False)  # array of condition objects
    bonuses = Column(JSON, nullable=False)  # {flat: {}, percent: {}, contextual: {}, passive: {}}
    sort_order = Column(Integer, server_default="0")
    is_active = Column(Boolean, server_default="1")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_category", "category"),
        Index("idx_rarity", "rarity"),
    )


class CharacterPerk(Base):
    __tablename__ = "character_perks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    character_id = Column(Integer, nullable=False, index=True)
    perk_id = Column(Integer, ForeignKey("perks.id", ondelete="CASCADE"), nullable=False, index=True)
    unlocked_at = Column(DateTime, server_default=func.now())
    is_custom = Column(Boolean, server_default="0")  # TRUE if admin-granted

    __table_args__ = (
        UniqueConstraint("character_id", "perk_id", name="uq_char_perk"),
    )


class CharacterCumulativeStats(Base):
    __tablename__ = "character_cumulative_stats"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    character_id = Column(Integer, unique=True, nullable=False, index=True)

    # Battle stats (Phase 1)
    total_damage_dealt = Column(BigInteger, server_default="0")
    total_damage_received = Column(BigInteger, server_default="0")
    pve_kills = Column(Integer, server_default="0")
    pvp_wins = Column(Integer, server_default="0")
    pvp_losses = Column(Integer, server_default="0")
    total_battles = Column(Integer, server_default="0")
    max_damage_single_battle = Column(BigInteger, server_default="0")
    max_win_streak = Column(Integer, server_default="0")
    current_win_streak = Column(Integer, server_default="0")
    total_rounds_survived = Column(Integer, server_default="0")
    low_hp_wins = Column(Integer, server_default="0")  # wins with HP < 10%

    # Economic stats (Phase 3)
    total_gold_earned = Column(BigInteger, server_default="0")
    total_gold_spent = Column(BigInteger, server_default="0")
    items_bought = Column(Integer, server_default="0")
    items_sold = Column(Integer, server_default="0")

    # Exploration stats (Phase 3)
    locations_visited = Column(Integer, server_default="0")
    total_transitions = Column(Integer, server_default="0")

    # Skill stats (Phase 3)
    skills_used = Column(Integer, server_default="0")
    items_equipped = Column(Integer, server_default="0")
