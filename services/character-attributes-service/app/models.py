from sqlalchemy import Column, Integer, Float
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
    current_stamina = Column(Integer, default=50)

    # Максимальные значения
    max_health = Column(Integer, default=100)
    max_mana = Column(Integer, default=75)
    max_energy = Column(Integer, default=50)
    max_stamina = Column(Integer, default=50)

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
    res_cutting = Column(Float, default=0.0)  # Сопротивление режущему (%)
    res_crushing = Column(Float, default=0.0)  # Сопротивление дробящему (%)
    res_piersing = Column(Float, default=0.0)  # Сопротивление колющему (%)
    res_magic = Column(Float, default=0.0)  # Сопротивление магическому (%)
    res_fire = Column(Float, default=0.0)  # Сопротивление огню (%)
    res_ice = Column(Float, default=0.0)  # Сопротивление льду (%)
    res_watering = Column(Float, default=0.0)  # Сопротивление воде (%)
    res_electricity = Column(Float, default=0.0)  # Сопротивление электрическому (%)
    res_sainting = Column(Float, default=0.0)  # Сопротивление святому (%)
    res_wind = Column(Float, default=0.0)  # Сопротивление ветру (%)
    res_damning = Column(Float, default=0.0)  # Сопротивление проклятому (%)




