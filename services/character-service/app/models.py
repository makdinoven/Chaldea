from sqlalchemy import Column, Integer, SmallInteger, String, Text, Enum, TIMESTAMP, ForeignKey, func, BigInteger, JSON, Boolean, Float, Index, UniqueConstraint, DateTime, Numeric, CheckConstraint
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.dialects import mysql as mysql_types
import econ_ledger

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
    # FEAT-154: registration overhaul (all nullable, no backfill)
    origin_id = Column(Integer, nullable=True)  # -> locations-service origin_countries.id (no FK)
    start_location_id = Column(BigInteger, nullable=True)
    skitaltsy_since_year = Column(Integer, nullable=True)
    skitaltsy_since_segment = Column(SmallInteger, nullable=True)
    rejection_reason = Column(Text, nullable=True)



class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    id_subrace = Column(Integer, nullable=False)
    biography = Column(Text, nullable=True)
    personality = Column(Text, nullable=True)
    id_class = Column(Integer, nullable=False)
    id_attributes = Column(Integer, nullable=True)  # Поле для атрибутов
    # FEAT-181: BIGINT; changed ONLY through econ_ledger.post_operation (see the balance guard at the end).
    currency_balance = Column(BigInteger, nullable=False, default=0, server_default="0")
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
    last_teleport_at = Column(DateTime, nullable=True)
    travel_cooldown_until = Column(TIMESTAMP, nullable=True, default=None)
    # FEAT-175 activity lock (see activity_lock.py): in a dungeon run / knocked out.
    dungeon_session_id = Column(Integer, nullable=True, default=None)
    unconscious_until = Column(DateTime, nullable=True, default=None)
    # FEAT-180: asleep in a house bedroom (naive UTC) — locks activity like the
    # two above; rest there is multiplied by sleep_regen_factor. Set and cleared
    # by locations-service (houses), read by the regen in attributes-service.
    asleep_since = Column(DateTime, nullable=True, default=None)
    sleep_regen_factor = Column(Float, nullable=True, default=None)
    sleep_house_room_id = Column(BigInteger, nullable=True, default=None)
    # FEAT-180 stage 6b: reading in a house library (naive UTC) — locks activity
    # like sleep; set and cleared by locations-service (houses).
    reading_since = Column(DateTime, nullable=True, default=None)
    reading_house_room_id = Column(BigInteger, nullable=True, default=None)
    # FEAT-180 stage 7: the house room (locations-service `house_rooms.id`, no FK) the
    # character stands in. Set by locations-service; cleared here on every change of
    # location. Counts only while that room's house stands in `current_location_id`.
    house_room_id = Column(BigInteger, nullable=True, default=None, index=True)
    # FEAT-154: registration overhaul (all nullable, no backfill)
    origin_id = Column(Integer, nullable=True)  # -> locations-service origin_countries.id (no FK)
    registered_at = Column(TIMESTAMP, nullable=True, default=None)
    skitaltsy_since_year = Column(Integer, nullable=True)
    skitaltsy_since_segment = Column(SmallInteger, nullable=True)
    # FEAT-154 rule 12d / D17-D18: замороженный слепок выданного стартового набора.
    # NULL = персонаж создан до фичи, паспорт реконструирует набор живым resolve.
    granted_kit = Column(JSON, nullable=True)
    # FEAT-155 (правило 12d по образцу granted_kit): замороженный слепок
    # стартовых характеристик — пресет подрасы в момент одобрения заявки.
    # Паспорт — запись о вступлении, а не текущее состояние персонажа, поэтому
    # он читает слепок, а не character-attributes-service.
    # NULL = персонаж создан до фичи, паспорт реконструирует пресет подрасы.
    starting_attributes = Column(JSON, nullable=True)

    # character_titles.character_id входит в составной первичный ключ, поэтому
    # ORM по умолчанию пытается занулить его при удалении персонажа и падает с
    # AssertionError. delete-orphan заставляет ORM удалять строки связи явно,
    # а ON DELETE CASCADE на FK страхует удаления в обход ORM (raw SQL).
    titles = relationship(
        "CharacterTitle",
        back_populates="character",
        cascade="all, delete-orphan",
    )
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
    # FEAT-154: registration overhaul (all nullable, no backfill)
    distinctive_features = Column(Text, nullable=True)
    height_min = Column(Integer, nullable=True)
    height_max = Column(Integer, nullable=True)
    typical_origin_ids = Column(JSON, nullable=True)  # -> origin_countries.id list (no FK)

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

    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)
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
    """Стартовый набор, заданный парой (класс x происхождение) — FEAT-154, rules 12a-12c.

    origin_id = 0 означает «набор класса по умолчанию» (D16). Ноль, а не NULL,
    потому что MySQL считает NULL-ы различными внутри UNIQUE-индекса, и с
    nullable-колонкой два конкурирующих дефолта для одного класса были бы
    возможны. origin_countries.id — AUTO_INCREMENT и никогда не выдаёт 0.
    """

    __tablename__ = "starter_kits"

    id = Column(Integer, primary_key=True, index=True)
    class_id = Column(Integer, ForeignKey("classes.id_class"), nullable=False)
    origin_id = Column(Integer, nullable=False, default=0, server_default="0")
    items = Column(JSON, nullable=False, default=list)
    skills = Column(JSON, nullable=False, default=list)
    currency_amount = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint('class_id', 'origin_id', name='uq_starter_kits_class_origin'),
    )


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
    skill_id = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint('mob_template_id', 'skill_id', name='uq_mob_template_skill'),
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
    spawn_type = Column(Enum('random', 'manual', 'dungeon'), nullable=False, default='random')
    # When set, this mob belongs to a spawned pack (FEAT-147). NULL = standalone mob.
    pack_group_id = Column(Integer, ForeignKey("active_mob_packs.id", ondelete="SET NULL"), nullable=True, index=True)
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


# ============================================================
# Mob Packs (FEAT-147) — named heterogeneous groups of mobs
# ============================================================

class MobPack(Base):
    __tablename__ = "mob_packs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    avatar = Column(String(255), nullable=True)
    # Optional pack-wide respawn: the whole pack respawns once all members die.
    respawn_enabled = Column(Boolean, nullable=False, default=False)
    respawn_seconds = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    members = relationship("MobPackMember", back_populates="pack", cascade="all, delete-orphan")


class MobPackMember(Base):
    __tablename__ = "mob_pack_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pack_id = Column(Integer, ForeignKey("mob_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    mob_template_id = Column(Integer, ForeignKey("mob_templates.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)

    pack = relationship("MobPack", back_populates="members")
    mob_template = relationship("MobTemplate")


class ActiveMobPack(Base):
    __tablename__ = "active_mob_packs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pack_id = Column(Integer, ForeignKey("mob_packs.id", ondelete="CASCADE"), nullable=False)
    location_id = Column(BigInteger, nullable=False, index=True)
    status = Column(Enum('alive', 'in_battle', 'dead'), nullable=False, default='alive')
    spawned_at = Column(TIMESTAMP, server_default=func.now())
    killed_at = Column(TIMESTAMP, nullable=True)
    respawn_at = Column(TIMESTAMP, nullable=True)

    __table_args__ = (
        Index('idx_active_mob_packs_location', 'location_id', 'status'),
        Index('idx_active_mob_packs_respawn', 'respawn_at', 'status'),
    )

    pack = relationship("MobPack")


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


class TeleportLink(Base):
    __tablename__ = "teleport_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_npc_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    to_npc_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    cost_gold = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('from_npc_id', 'to_npc_id', name='uq_tlink_pair'),
        Index('idx_tlink_from', 'from_npc_id'),
    )


class GoldTransaction(Base):
    __tablename__ = "gold_transactions"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, nullable=False, index=True)
    amount = Column(Integer, nullable=False)  # positive = earn, negative = spend
    balance_after = Column(Integer, nullable=False)
    transaction_type = Column(String(50), nullable=False)
    source = Column(String(100), nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index('idx_gold_tx_character_created', 'character_id', 'created_at'),
        Index('idx_gold_tx_type', 'transaction_type'),
    )


# ---------------------------------------------------------------------------
# FEAT-181 world economy: double-entry ledger (migration 027_world_economy).
# Balances move ONLY through econ_ledger.post_operation (raw SQL in the caller's
# transaction); these models exist for reads (admin API) and for create_all in tests.
# ---------------------------------------------------------------------------

# BIGINT in MySQL, INTEGER in SQLite (only INTEGER PRIMARY KEY autoincrements there).
_EconId = BigInteger().with_variant(Integer, "sqlite")


class EconSettings(Base):
    __tablename__ = "econ_settings"

    id = Column(SmallInteger, primary_key=True, autoincrement=False)  # always 1
    currency_name = Column(String(50), nullable=False, default="Золото")
    currency_genitive = Column(String(50), nullable=False, default="золота")
    currency_one = Column(String(50), nullable=False, default="золотой")
    currency_few = Column(String(50), nullable=False, default="золотых")
    currency_many = Column(String(50), nullable=False, default="золотых")
    currency_short = Column(String(20), nullable=False, default="зол.")
    country_tax_rate = Column(Numeric(5, 4), nullable=False, default=0.1)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    updated_by_user_id = Column(Integer, nullable=True)


class EconAccount(Base):
    __tablename__ = "econ_accounts"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    kind = Column(String(32), nullable=False)
    ref_id = Column(BigInteger, nullable=False, default=0, server_default="0")
    name = Column(String(255), nullable=True)
    balance = Column(BigInteger, nullable=False, default=0, server_default="0")  # unused (0) for kind='character'
    allow_negative = Column(Boolean, nullable=False, default=False, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("kind", "ref_id", name="uq_econ_accounts_kind_ref"),
        Index("ix_econ_accounts_kind", "kind"),
    )


class EconOperation(Base):
    __tablename__ = "econ_operations"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    op_type = Column(String(50), nullable=False)
    idempotency_key = Column(String(128), nullable=True)
    location_id = Column(BigInteger, nullable=True)
    region_id = Column(BigInteger, nullable=True)
    actor_user_id = Column(Integer, nullable=True)
    source_service = Column(String(32), nullable=False)
    comment = Column(String(500), nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime().with_variant(mysql_types.DATETIME(fsp=6), "mysql"),
                        nullable=False, server_default=func.now())

    postings = relationship("EconPosting", back_populates="operation", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_econ_operations_idem"),
        Index("ix_econ_operations_created", "created_at"),
        Index("ix_econ_operations_type_created", "op_type", "created_at"),
        Index("ix_econ_operations_region_created", "region_id", "created_at"),
    )


class EconPosting(Base):
    __tablename__ = "econ_postings"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    operation_id = Column(BigInteger, ForeignKey("econ_operations.id", name="fk_econ_postings_operation"),
                          nullable=False)
    from_account_id = Column(BigInteger, ForeignKey("econ_accounts.id", name="fk_econ_postings_from"),
                             nullable=False)
    to_account_id = Column(BigInteger, ForeignKey("econ_accounts.id", name="fk_econ_postings_to"),
                           nullable=False)
    amount = Column(BigInteger, nullable=False)
    leg_type = Column(String(32), nullable=False, default="main", server_default="main")
    created_at = Column(DateTime().with_variant(mysql_types.DATETIME(fsp=6), "mysql"),
                        nullable=False, server_default=func.now())

    operation = relationship("EconOperation", back_populates="postings")

    __table_args__ = (
        Index("ix_econ_postings_operation", "operation_id"),
        Index("ix_econ_postings_from_created", "from_account_id", "created_at"),
        Index("ix_econ_postings_to_created", "to_account_id", "created_at"),
        CheckConstraint("amount > 0", name="ck_econ_postings_amount"),
        CheckConstraint("from_account_id <> to_account_id", name="ck_econ_postings_distinct"),
    )


# Balance guard: a persistent Character.currency_balance changed through the ORM is a bypass of the
# ledger and raises EconomyError at flush. Strict since FEAT-181 B2 (no ORM writer is left; every
# change goes through econ_ledger.post_operation). Fixtures/repair scripts that must seed a balance
# directly wrap the write in econ_ledger.allow_direct_balance_write(session).
BALANCE_GUARD_STRICT = True
econ_ledger.install_balance_guard(Character, "currency_balance", strict=BALANCE_GUARD_STRICT)
