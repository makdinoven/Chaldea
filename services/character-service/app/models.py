from sqlalchemy import Column, Integer, String, Text, Enum, TIMESTAMP, ForeignKey, func, BigInteger, JSON, Boolean
from sqlalchemy.orm import relationship
from database import Base

class CharacterRequest(Base):
    __tablename__ = "character_requests"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(20), index=True)
    id_subrace = Column(Integer, ForeignKey("subraces.id_subrace"))
    biography = Column(Text)
    personality = Column(Text)
    id_class = Column(Integer, ForeignKey("classes.id_class"))
    status = Column(Enum('pending', 'approved', 'rejected'), default='pending')
    created_at = Column(TIMESTAMP, server_default=func.now())
    user_id = Column(Integer, nullable=True)
    appearance = Column(Text, nullable=False)
    sex=Column(Enum('male', 'female','genderless'), default='genderless' )
    background=Column(Text, nullable=True)
    age = Column(Integer, nullable=True)
    weight = Column(String(10), nullable=True)
    height = Column(String(10), nullable=True)
    id_race = Column(Integer, ForeignKey('races.id_race'), nullable=False)
    avatar = Column(String(255), nullable=True)



class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    id_subrace = Column(Integer, nullable=False)
    biography = Column(Text, nullable=True)
    personality = Column(Text, nullable=True)
    id_class = Column(Integer, nullable=False)
    id_attributes = Column(Integer, nullable=True)  # Поле для атрибутов
    currency_balance = Column(Integer, default=0)
    request_id = Column(Integer, ForeignKey("character_requests.id"), nullable=True)  # Ссылка на заявку (nullable for NPCs)
    user_id = Column(Integer, nullable=True)  # Добавляем поле user_id
    appearance = Column(Text, nullable=False)
    sex = Column(Enum('male', 'female', 'genderless'), default='genderless')
    background = Column(Text, nullable=True)
    age = Column(Integer, nullable=True)
    weight = Column(String(10), nullable=True)
    height = Column(String(10), nullable=True)
    id_race = Column(Integer, nullable=False)
    avatar = Column(String(255), nullable=False)
    current_title_id = Column(Integer, ForeignKey("titles.id_title"), nullable=True)
    level = Column(Integer, nullable=False, default=1)
    stat_points = Column(Integer, nullable=False, default=0)
    current_location_id = Column(BigInteger, nullable=True)
    is_npc = Column(Boolean, nullable=False, default=False, index=True)
    npc_role = Column(String(50), nullable=True)

    titles = relationship("CharacterTitle", back_populates="character")
    current_title = relationship("Title")


class Race(Base):
    __tablename__ = "races"

    id_race = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    image = Column(String(255), nullable=True)

    # Связь с подрасами
    subraces = relationship("Subrace", back_populates="race")


class Subrace(Base):
    __tablename__ = "subraces"

    id_subrace = Column(Integer, primary_key=True, index=True)
    id_race = Column(Integer, ForeignKey("races.id_race"), nullable=False)
    name = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    stat_preset = Column(JSON, nullable=True)
    image = Column(String(255), nullable=True)

    # Связь с расами
    race = relationship("Race", back_populates="subraces")
class Class(Base):
    __tablename__ = "classes"
    id_class = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)

class Title(Base):
    __tablename__ = "titles"

    id_title = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # Связь с персонажами через промежуточную таблицу
    characters = relationship("CharacterTitle", back_populates="title")


class CharacterTitle(Base):
    __tablename__ = "character_titles"

    character_id = Column(Integer, ForeignKey("characters.id"), primary_key=True)
    title_id = Column(Integer, ForeignKey("titles.id_title"), primary_key=True)

    # Дата присвоения титула
    assigned_at = Column(TIMESTAMP, server_default=func.now())

    # Связь с персонажем и титулом
    character = relationship("Character", back_populates="titles")
    title = relationship("Title", back_populates="characters")

class LevelThreshold(Base):
    __tablename__ = "level_thresholds"
    id = Column(Integer, primary_key=True, index=True)
    level_number = Column(Integer, unique=True, nullable=False)
    required_experience = Column(Integer, nullable=False)


class StarterKit(Base):
    __tablename__ = "starter_kits"

    id = Column(Integer, primary_key=True, index=True)
    class_id = Column(Integer, ForeignKey("classes.id_class"), unique=True, nullable=False)
    items = Column(JSON, nullable=False, default=list)
    skills = Column(JSON, nullable=False, default=list)
    currency_amount = Column(Integer, nullable=False, default=0)


