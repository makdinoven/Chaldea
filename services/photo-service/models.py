"""
Mirror models for photo-service.

These are lightweight models reflecting only the columns that photo-service
reads or writes. The tables are OWNED by other services — photo-service
never creates or drops them.
"""

from sqlalchemy import Column, Integer, String, Text
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    avatar = Column(String(500), nullable=True)
    profile_bg_image = Column(String(500), nullable=True)


class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    avatar = Column(String(500), nullable=True)


class Area(Base):
    __tablename__ = "Areas"

    id = Column(Integer, primary_key=True)
    map_image_url = Column(Text, nullable=True)


class Country(Base):
    __tablename__ = "Countries"

    id = Column(Integer, primary_key=True)
    map_image_url = Column(Text, nullable=True)
    emblem_url = Column(Text, nullable=True)


class Region(Base):
    __tablename__ = "Regions"

    id = Column(Integer, primary_key=True)
    map_image_url = Column(Text, nullable=True)
    image_url = Column(Text, nullable=True)


class District(Base):
    __tablename__ = "Districts"

    id = Column(Integer, primary_key=True)
    image_url = Column(Text, nullable=True)
    map_icon_url = Column(Text, nullable=True)
    map_image_url = Column(Text, nullable=True)


class Location(Base):
    __tablename__ = "Locations"

    id = Column(Integer, primary_key=True)
    image_url = Column(Text, nullable=True)
    map_icon_url = Column(Text, nullable=True)


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True)
    skill_image = Column(String(500), nullable=True)


class SkillRank(Base):
    __tablename__ = "skill_ranks"

    id = Column(Integer, primary_key=True)
    rank_image = Column(String(500), nullable=True)


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True)
    image = Column(String(500), nullable=True)


class MobTemplate(Base):
    __tablename__ = "mob_templates"

    id = Column(Integer, primary_key=True)
    avatar = Column(String(255), nullable=True)


class Race(Base):
    __tablename__ = "races"

    id_race = Column(Integer, primary_key=True)
    image = Column(String(255), nullable=True)


class Subrace(Base):
    __tablename__ = "subraces"

    id_subrace = Column(Integer, primary_key=True)
    image = Column(String(255), nullable=True)


class GameRule(Base):
    __tablename__ = "game_rules"

    id = Column(Integer, primary_key=True)
    image_url = Column(Text, nullable=True)


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True)
    icon = Column(String(255), nullable=True)
