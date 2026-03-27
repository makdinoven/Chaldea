from sqlalchemy import Column, Integer, String, Text, Enum, TIMESTAMP, ForeignKey, func, BigInteger, JSON, Boolean, Float, Index, UniqueConstraint
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
    character_id = Column(Integer, nullable=True)
    request_type = Column(Enum('creation', 'claim'), nullable=False, server_default='creation')



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
    npc_status = Column(Enum('alive', 'dead', name='npc_status_enum'), nullable=False, default='alive', server_default='alive')

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
    rarity = Column(String(20), nullable=False, default='common', server_default='common')
    conditions = Column(JSON, nullable=True)
    icon = Column(String(255), nullable=True)
    reward_passive_exp = Column(Integer, nullable=False, default=0, server_default='0')
    reward_active_exp = Column(Integer, nullable=False, default=0, server_default='0')
    sort_order = Column(Integer, nullable=False, default=0, server_default='0')
    is_active = Column(Boolean, nullable=False, default=True, server_default='1')
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_titles_rarity', 'rarity'),
        Index('idx_titles_is_active', 'is_active'),
    )

    # Связь с персонажами через промежуточную таблицу
    characters = relationship("CharacterTitle", back_populates="title")


class CharacterTitle(Base):
    __tablename__ = "character_titles"

    character_id = Column(Integer, ForeignKey("characters.id"), primary_key=True)
    title_id = Column(Integer, ForeignKey("titles.id_title"), primary_key=True)
    is_custom = Column(Boolean, nullable=False, default=False, server_default='0')

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


class MobTemplate(Base):
    __tablename__ = "mob_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    tier = Column(Enum('normal', 'elite', 'boss'), nullable=False, default='normal', index=True)
    level = Column(Integer, nullable=False, default=1)
    avatar = Column(String(255), nullable=True)
    # Character creation data
    id_race = Column(Integer, nullable=False)
    id_subrace = Column(Integer, nullable=False)
    id_class = Column(Integer, nullable=False)
    sex = Column(Enum('male', 'female', 'genderless'), default='genderless')
    # Base attributes override (JSON with stat keys)
    base_attributes = Column(JSON, nullable=True)
    # Reward configuration
    xp_reward = Column(Integer, nullable=False, default=0)
    gold_reward = Column(Integer, nullable=False, default=0)
    # Respawn configuration
    respawn_enabled = Column(Boolean, nullable=False, default=False)
    respawn_seconds = Column(Integer, nullable=True)
    # Metadata
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    skills = relationship("MobTemplateSkill", back_populates="mob_template", cascade="all, delete-orphan")
    loot_entries = relationship("MobLootTable", back_populates="mob_template", cascade="all, delete-orphan")
    spawn_locations = relationship("LocationMobSpawn", back_populates="mob_template", cascade="all, delete-orphan")
    active_mobs = relationship("ActiveMob", back_populates="mob_template", cascade="all, delete-orphan")


class MobTemplateSkill(Base):
    __tablename__ = "mob_template_skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mob_template_id = Column(Integer, ForeignKey("mob_templates.id", ondelete="CASCADE"), nullable=False)
    skill_rank_id = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint('mob_template_id', 'skill_rank_id', name='uq_mob_template_skill'),
    )

    mob_template = relationship("MobTemplate", back_populates="skills")


class MobLootTable(Base):
    __tablename__ = "mob_loot_table"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mob_template_id = Column(Integer, ForeignKey("mob_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, nullable=False)
    drop_chance = Column(Float, nullable=False, default=0.0)
    min_quantity = Column(Integer, nullable=False, default=1)
    max_quantity = Column(Integer, nullable=False, default=1)

    mob_template = relationship("MobTemplate", back_populates="loot_entries")


class LocationMobSpawn(Base):
    __tablename__ = "location_mob_spawns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mob_template_id = Column(Integer, ForeignKey("mob_templates.id", ondelete="CASCADE"), nullable=False)
    location_id = Column(BigInteger, nullable=False, index=True)
    spawn_chance = Column(Float, nullable=False, default=5.0)
    max_active = Column(Integer, nullable=False, default=1)
    is_enabled = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint('mob_template_id', 'location_id', name='uq_template_location'),
    )

    mob_template = relationship("MobTemplate", back_populates="spawn_locations")


class ActiveMob(Base):
    __tablename__ = "active_mobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mob_template_id = Column(Integer, ForeignKey("mob_templates.id", ondelete="CASCADE"), nullable=False)
    character_id = Column(Integer, nullable=False)
    location_id = Column(BigInteger, nullable=False)
    status = Column(Enum('alive', 'in_battle', 'dead'), nullable=False, default='alive')
    battle_id = Column(Integer, nullable=True)
    spawn_type = Column(Enum('random', 'manual'), nullable=False, default='random')
    spawned_at = Column(TIMESTAMP, server_default=func.now())
    killed_at = Column(TIMESTAMP, nullable=True)
    respawn_at = Column(TIMESTAMP, nullable=True)

    __table_args__ = (
        Index('idx_active_mobs_location', 'location_id', 'status'),
        Index('idx_active_mobs_respawn', 'respawn_at', 'status'),
    )

    mob_template = relationship("MobTemplate", back_populates="active_mobs")


class MobKill(Base):
    __tablename__ = "mob_kills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False, index=True)
    mob_template_id = Column(Integer, ForeignKey("mob_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    killed_at = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('character_id', 'mob_template_id', name='uq_character_mob_kill'),
    )

    mob_template = relationship("MobTemplate")


class CharacterLog(Base):
    __tablename__ = "character_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    event_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index('idx_character_logs_char_created', 'character_id', created_at.desc()),
        Index('idx_character_logs_event_type', 'event_type'),
    )


