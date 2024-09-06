from sqlalchemy import Column, Integer, String
from database import Base

# Определяем модель для хранения навыков персонажа
class CharacterSkills(Base):
    __tablename__ = "character_skills"

    id = Column(Integer, primary_key=True, index=True)  # Первичный ключ
    character_id = Column(Integer, unique=True, index=True)  # ID персонажа
    skill_1 = Column(String(100), default="Basic Attack")  # Навык 1
    skill_2 = Column(String(100), default="Basic Defense")  # Навык 2
    skill_3 = Column(String(100), default="Basic Heal")  # Навык 3
