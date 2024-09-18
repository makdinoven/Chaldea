from sqlalchemy import Column, Integer
from database import Base

# Определяем модель для хранения характеристик персонажа
class CharacterAttributes(Base):
    __tablename__ = "character_attributes"

    id = Column(Integer, primary_key=True, index=True)  # Первичный ключ
    character_id = Column(Integer, unique=True, index=True)  # ID персонажа
    health = Column(Integer, default=100)  # Здоровье
    mana = Column(Integer, default=75)  # Мана
    energy = Column(Integer, default=50)  # Энергия
    stamina = Column(Integer, default=50) #Выносливость
    endurance = Column(Integer, default=100)  # Живучесть
    strength = Column(Integer, default=10)  # Сила
    agility = Column(Integer, default=10)  # Ловкость
    intelligence = Column(Integer, default=10)  # Интеллект
    luck = Column(Integer, default=10)  # Везучесть
    charisma = Column(Integer, default=10)  # Харизма

    # Боевые характеристики
    damage = Column(Integer, default=0)  # Урон
    dodge = Column(Integer, default=5)  # Уклонение (%)
    critical_hit_chance = Column(Integer, default=20)  # Шанс крит удара (%)
    critical_damage = Column(Integer, default=125)  # Урон крит удара (%)

    # Сопротивления
    res_effects = Column(Integer, default=0)  # Сопротивление эффектам (%)
    res_physical = Column(Integer, default=0)  # Сопротивление физическому урону (%)
    res_cutting = Column(Integer, default=0)  # Сопротивление режущему (%)
    res_crushing = Column(Integer, default=0)  # Сопротивление дробящему (%)
    res_piersing = Column(Integer, default=0)  # Сопротивление колющему (%)
    res_magic = Column(Integer, default=0)  # Сопротивление магическому (%)
    res_fire = Column(Integer, default=0)  # Сопротивление огню (%)
    res_ice = Column(Integer, default=0)  # Сопротивление льду (%)
    res_watering = Column(Integer, default=0)  # Сопротивление воде (%)
    res_electricity = Column(Integer, default=0)  # Сопротивление электрическому (%)
    res_sainting = Column(Integer, default=0)  # Сопротивление святому (%)
    res_wind = Column(Integer, default=0)  # Сопротивление ветру (%)
    res_damning = Column(Integer, default=0)  # Сопротивление проклятому (%)
