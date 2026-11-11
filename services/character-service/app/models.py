from sqlalchemy import Column, Integer, SmallInteger, String, Text, Enum, TIMESTAMP, ForeignKey, func, BigInteger, JSON, Boolean, Float, Index, UniqueConstraint, DateTime, Numeric, CheckConstraint, Date
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
    # FEAT-197 (NPC only): the minimum reputation tier code (reputation_core.TIER_CODES) a player needs in the
    # NPC's region for ANY interaction; and the per-NPC kill weight overriding the role weight. NULL = none.
    reputation_min_tier = Column(String(20), nullable=True)
    reputation_kill_points = Column(Integer, nullable=True)
    # FEAT-198 law (see law_crud.py / activity_lock.py): in jail while `jailed_until` is in the future (lazy, like
    # `unconscious_until`); `law_encounter_id` is set while the guards wait for the player's choice. On a guard NPC
    # `unconscious_until` is its knock-out after a lost fight (guards never die).
    jailed_until = Column(DateTime, nullable=True, default=None)
    jail_region_id = Column(Integer, nullable=True, default=None)
    law_encounter_id = Column(Integer, nullable=True, default=None)
    # FEAT-202 (042): the country-prison district snapshot of the serving term (NULL for a station term) — a jailed
    # character may move only inside its subtree; consulted only while the lock reason is `jail`.
    jail_district_id = Column(Integer, nullable=True, default=None)
    # FEAT-209 (048, NPC only, admin-only — never add to public schemas): the «Готов» mark of the NPC admin page;
    # `npc_ready_at` is UTC naive, `npc_ready_by` a username snapshot of the admin who set it.
    npc_ready = Column(Boolean, nullable=False, default=False, server_default='0')
    npc_ready_at = Column(DateTime, nullable=True, default=None)
    npc_ready_by = Column(String(255), nullable=True, default=None)

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
    # FEAT-210: admin-only «Готов» mark (never exposed by public schemas, not part of create/update payloads).
    # `admin_ready_at` is UTC naive, `admin_ready_by` a username snapshot of the admin who set it.
    admin_ready = Column(Boolean, nullable=False, default=False, server_default='0')
    admin_ready_at = Column(DateTime, nullable=True, default=None)
    admin_ready_by = Column(String(255), nullable=True, default=None)
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
    # FEAT-197: minimum reputation tier in the source NPC's region (NULL = no gate)
    min_reputation_tier = Column(String(20), nullable=True)

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
    currency_name = Column(String(50), nullable=False, default="Марки")
    currency_genitive = Column(String(50), nullable=False, default="марок")
    currency_one = Column(String(50), nullable=False, default="марка")
    currency_few = Column(String(50), nullable=False, default="марки")
    currency_many = Column(String(50), nullable=False, default="марок")
    currency_short = Column(String(20), nullable=False, default="ṃ")
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


# ---------------------------------------------------------------------------
# FEAT-182 living regions: goods groups, chains, region templates, per-region state,
# tick runs, history, item -> group overrides, sim settings (migration 028_econ_living_regions).
# No FK to Regions / items (owned by locations- / inventory-service).
# ---------------------------------------------------------------------------

class EconGoodsGroup(Base):
    __tablename__ = "econ_goods_groups"

    code = Column(String(32), primary_key=True)
    name = Column(String(100), nullable=False)
    sort_order = Column(SmallInteger, nullable=False, default=0, server_default="0")
    is_food = Column(Boolean, nullable=False, default=False, server_default="0")
    base_price = Column(Integer, nullable=False)
    norm_per_1000 = Column(Numeric(10, 3), nullable=False)
    norm_days = Column(Numeric(6, 2), nullable=False)
    prosperity_elasticity = Column(Numeric(5, 3), nullable=False, default=0, server_default="0")
    price_elasticity = Column(Numeric(5, 3), nullable=False, default=0, server_default="0")
    # FEAT-194: per-capita demand weights of the poor / middling / rich (normalised to the template mix)
    class_demand_poor = Column(Numeric(6, 3), nullable=False, default=1, server_default="1.000")
    class_demand_middling = Column(Numeric(6, 3), nullable=False, default=1, server_default="1.000")
    class_demand_rich = Column(Numeric(6, 3), nullable=False, default=1, server_default="1.000")
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class EconGroupInput(Base):
    __tablename__ = "econ_group_inputs"

    group_code = Column(String(32), ForeignKey("econ_goods_groups.code", name="fk_egi_group"), primary_key=True)
    input_code = Column(String(32), ForeignKey("econ_goods_groups.code", name="fk_egi_input"), primary_key=True)
    ratio = Column(Numeric(6, 3), nullable=False)

    __table_args__ = (
        Index("ix_econ_group_inputs_input", "input_code"),
        CheckConstraint("ratio > 0", name="ck_egi_ratio"),
    )


class EconRegionTemplate(Base):
    __tablename__ = "econ_region_templates"

    code = Column(String(32), primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    settlement_noun = Column(String(50), nullable=False)          # «Город», «Крепость», «Округа»
    noun_gender = Column(String(1), nullable=False, default="m", server_default="m")  # m | f | n
    default_population = Column(Integer, nullable=False)
    tax_rate = Column(Numeric(5, 4), nullable=False)
    sort_order = Column(SmallInteger, nullable=False, default=0, server_default="0")
    # FEAT-194: default class mix of the template's regions (sum 1)
    class_poor = Column(Numeric(6, 4), nullable=False, default=0.45, server_default="0.4500")
    class_middling = Column(Numeric(6, 4), nullable=False, default=0.45, server_default="0.4500")
    class_rich = Column(Numeric(6, 4), nullable=False, default=0.1, server_default="0.1000")
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("noun_gender IN ('m', 'f', 'n')", name="ck_ert_noun_gender"),
    )


class EconTemplateGood(Base):
    __tablename__ = "econ_template_goods"

    template_code = Column(String(32), ForeignKey("econ_region_templates.code", name="fk_etg_template",
                                                  ondelete="CASCADE"), primary_key=True)
    group_code = Column(String(32), ForeignKey("econ_goods_groups.code", name="fk_etg_group"), primary_key=True)
    production_per_1000 = Column(Numeric(12, 3), nullable=False, default=0, server_default="0")
    consumption_mult = Column(Numeric(5, 3), nullable=False, default=1, server_default="1")

    __table_args__ = (
        Index("ix_etg_group", "group_code"),
    )


class EconRegion(Base):
    __tablename__ = "econ_regions"

    region_id = Column(BigInteger, primary_key=True, autoincrement=False)  # Regions.id (no FK)
    template_code = Column(String(32), ForeignKey("econ_region_templates.code", name="fk_econ_regions_template",
                                                  ondelete="SET NULL"), nullable=True)
    population = Column(Integer, nullable=False, default=0, server_default="0")
    tax_rate = Column(Numeric(5, 4), nullable=False, default=0.1, server_default="0.1000")
    stability = Column(Numeric(5, 2), nullable=False, default=70, server_default="70")
    prosperity = Column(Numeric(5, 2), nullable=False, default=50, server_default="50")
    hunger = Column(Numeric(5, 4), nullable=False, default=0, server_default="0")
    satisfaction = Column(Numeric(5, 4), nullable=False, default=1, server_default="1")
    treasury_target = Column(BigInteger, nullable=False, default=0, server_default="0")
    last_income = Column(BigInteger, nullable=False, default=0, server_default="0")
    last_tax = Column(BigInteger, nullable=False, default=0, server_default="0")
    last_wages = Column(BigInteger, nullable=False, default=0, server_default="0")
    last_grant = Column(BigInteger, nullable=False, default=0, server_default="0")
    last_run_id = Column(BigInteger, nullable=True)
    last_tick_at = Column(DateTime, nullable=True)
    low_stability_since = Column(DateTime, nullable=True)  # FEAT-187 riot clock (set / cleared by the tick)
    # FEAT-193 guild: the per-recount allowance (shares of the purse / positive treasury for food), set by the tick
    guild_budget = Column(BigInteger, nullable=False, default=0, server_default="0")
    guild_food_budget = Column(BigInteger, nullable=False, default=0, server_default="0")
    # FEAT-194 social classes: live mix (NULL = no classes), shift of the last recount, wealth norm / tax
    class_poor = Column(Numeric(9, 6), nullable=True)
    class_middling = Column(Numeric(9, 6), nullable=True)
    class_rich = Column(Numeric(9, 6), nullable=True)
    class_dpoor = Column(Numeric(9, 6), nullable=False, default=0, server_default="0")
    class_drich = Column(Numeric(9, 6), nullable=False, default=0, server_default="0")
    wealth_norm = Column(BigInteger, nullable=False, default=0, server_default="0")
    last_wealth_tax = Column(BigInteger, nullable=False, default=0, server_default="0")
    # FEAT-211: admin override of the region's trade gate (Locations.id, no FK); NULL = the guard station
    trade_gate_location_id = Column(BigInteger, nullable=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_econ_regions_template", "template_code"),
    )


class EconRegionGood(Base):
    __tablename__ = "econ_region_goods"

    region_id = Column(BigInteger, ForeignKey("econ_regions.region_id", name="fk_erg_region", ondelete="CASCADE"),
                       primary_key=True, autoincrement=False)
    group_code = Column(String(32), ForeignKey("econ_goods_groups.code", name="fk_erg_group"), primary_key=True)
    production_per_1000 = Column(Numeric(12, 3), nullable=False, default=0, server_default="0")
    consumption_mult = Column(Numeric(5, 3), nullable=False, default=1, server_default="1")
    stock = Column(Numeric(16, 3), nullable=False, default=0, server_default="0")
    norm_stock = Column(Numeric(16, 3), nullable=False, default=0, server_default="0")
    price_mult = Column(Numeric(6, 3), nullable=False, default=1, server_default="1")
    prev_price_mult = Column(Numeric(6, 3), nullable=False, default=1, server_default="1")
    last_produced = Column(Numeric(14, 3), nullable=False, default=0, server_default="0")
    last_consumed = Column(Numeric(14, 3), nullable=False, default=0, server_default="0")
    last_demand = Column(Numeric(14, 3), nullable=False, default=0, server_default="0")
    last_spoiled = Column(Numeric(14, 3), nullable=False, default=0, server_default="0")

    __table_args__ = (
        Index("ix_erg_group", "group_code"),
    )


class EconTickRun(Base):
    __tablename__ = "econ_tick_runs"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    slot = Column(BigInteger, nullable=True)            # floor(unix / 21600) for auto runs, NULL for manual
    trigger_kind = Column(String(10), nullable=False)   # auto | manual
    actor_user_id = Column(Integer, nullable=True)
    status = Column(String(10), nullable=False)         # running | done | partial | failed
    grant_plan = Column(JSON, nullable=True)
    regions_total = Column(Integer, nullable=False, default=0, server_default="0")
    regions_done = Column(Integer, nullable=False, default=0, server_default="0")
    regions_failed = Column(Integer, nullable=False, default=0, server_default="0")
    error = Column(String(500), nullable=True)
    started_at = Column(DateTime, nullable=False, server_default=func.now())
    heartbeat_at = Column(DateTime, nullable=False, server_default=func.now())
    finished_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("slot", name="uq_econ_tick_runs_slot"),
        Index("ix_econ_tick_runs_started", "started_at"),
    )


class EconRegionHistory(Base):
    __tablename__ = "econ_region_history"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, ForeignKey("econ_tick_runs.id", name="fk_erh_run", ondelete="CASCADE"),
                    nullable=False)
    region_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    population = Column(Integer, nullable=False)
    stability = Column(Numeric(5, 2), nullable=False)
    prosperity = Column(Numeric(5, 2), nullable=False)
    hunger = Column(Numeric(5, 4), nullable=False)
    purse = Column(BigInteger, nullable=False)
    treasury = Column(BigInteger, nullable=False)
    income = Column(BigInteger, nullable=False)
    tax = Column(BigInteger, nullable=False)
    wages = Column(BigInteger, nullable=False)
    grant_amount = Column(BigInteger, nullable=False)
    goods = Column(JSON, nullable=False)
    # FEAT-194 (NULL for older rows)
    class_poor = Column(Numeric(9, 6), nullable=True)
    class_middling = Column(Numeric(9, 6), nullable=True)
    class_rich = Column(Numeric(9, 6), nullable=True)
    wealth_norm = Column(BigInteger, nullable=True)
    wealth_tax = Column(BigInteger, nullable=True)

    __table_args__ = (
        Index("ix_erh_run", "run_id"),
        Index("ix_erh_region_created", "region_id", "created_at"),
    )


class EconItemGroup(Base):
    __tablename__ = "econ_item_groups"

    item_id = Column(BigInteger, primary_key=True, autoincrement=False)  # items.id (no FK)
    group_code = Column(String(32), ForeignKey("econ_goods_groups.code", name="fk_eig_group"), nullable=True)
    off_market = Column(Boolean, nullable=True)  # NULL = auto rule
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    updated_by_user_id = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_eig_group", "group_code"),
    )


class EconSimSettings(Base):
    __tablename__ = "econ_sim_settings"

    id = Column(SmallInteger, primary_key=True, autoincrement=False)  # always 1
    tick_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    params = Column(JSON, nullable=False)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    updated_by_user_id = Column(Integer, nullable=True)
    caravan_pass_last_run_at = Column(DateTime, nullable=True)   # FEAT-211: claim of the caravan pass


# --------------------------------------------------------------------------- FEAT-184 banks (migration 031)

class EconBank(Base):
    """One bank per region. Money: ledger accounts ``bank`` / ``bank_deposits`` (ref = region_id)."""

    __tablename__ = "econ_banks"

    region_id = Column(BigInteger, primary_key=True, autoincrement=False)  # Regions.id (no FK)
    is_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    deposit_rate_factor = Column(Numeric(5, 4), nullable=False, default=1, server_default="1.0000")
    resident_deposits = Column(BigInteger, nullable=False, default=0, server_default="0")
    resident_loans = Column(BigInteger, nullable=False, default=0, server_default="0")
    resident_dep_carry = Column(Numeric(16, 6), nullable=False, default=0, server_default="0")
    resident_loan_carry = Column(Numeric(16, 6), nullable=False, default=0, server_default="0")
    accrued_at = Column(DateTime, nullable=True)
    capital_seeded_at = Column(DateTime, nullable=True)
    last_run_id = Column(BigInteger, nullable=True)
    last_tick_at = Column(DateTime, nullable=True)
    last_stats = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    loan_min_reputation_tier = Column(String(20), nullable=True)   # FEAT-197: loans need this tier (NULL = none)

    __table_args__ = (
        CheckConstraint("resident_deposits >= 0 AND resident_loans >= 0", name="ck_econ_banks_res"),
    )


class BankDeposit(Base):
    """A player deposit: ``demand`` (current rate) or ``term`` (rate fixed at opening)."""

    __tablename__ = "bank_deposits"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)        # characters.id (no FK; deletion hook closes rows)
    region_id = Column(BigInteger, ForeignKey("econ_banks.region_id", name="fk_bank_deposits_bank"), nullable=False)
    kind = Column(String(8), nullable=False)              # demand | term
    status = Column(String(8), nullable=False, default="open", server_default="open")  # open | closed
    amount = Column(BigInteger, nullable=False, default=0, server_default="0")
    interest_base = Column(BigInteger, nullable=False, default=0, server_default="0")
    interest_accrued = Column(BigInteger, nullable=False, default=0, server_default="0")
    interest_total = Column(BigInteger, nullable=False, default=0, server_default="0")
    interest_carry = Column(Numeric(16, 6), nullable=False, default=0, server_default="0")
    rate_day = Column(Numeric(8, 6), nullable=True)       # term: fixed at opening; demand: NULL
    term_days = Column(SmallInteger, nullable=True)
    opened_at = Column(DateTime, nullable=False)
    matures_at = Column(DateTime, nullable=True)
    accrued_at = Column(DateTime, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    demand_owner_id = Column(Integer, nullable=True)      # = character_id while kind=demand AND open
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("region_id", "demand_owner_id", name="uq_bank_deposits_demand"),
        Index("ix_bank_deposits_region_status", "region_id", "status"),
        Index("ix_bank_deposits_char_status", "character_id", "status"),
        CheckConstraint("kind IN ('demand', 'term')", name="ck_bank_deposits_kind"),
        CheckConstraint("status IN ('open', 'closed')", name="ck_bank_deposits_status"),
        CheckConstraint("amount >= 0 AND interest_accrued >= 0 AND interest_base >= 0",
                        name="ck_bank_deposits_amounts"),
    )


class BankLoan(Base):
    """A player loan; ``active_character_id`` = character_id while active|overdue (one open loan per character)."""

    __tablename__ = "bank_loans"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    region_id = Column(BigInteger, ForeignKey("econ_banks.region_id", name="fk_bank_loans_bank"), nullable=False)
    status = Column(String(12), nullable=False, default="active", server_default="active")
    principal = Column(BigInteger, nullable=False)
    debt = Column(BigInteger, nullable=False)
    interest_total = Column(BigInteger, nullable=False, default=0, server_default="0")
    penalty_total = Column(BigInteger, nullable=False, default=0, server_default="0")
    paid_total = Column(BigInteger, nullable=False, default=0, server_default="0")
    collected_total = Column(BigInteger, nullable=False, default=0, server_default="0")
    written_off = Column(BigInteger, nullable=False, default=0, server_default="0")
    rate_day = Column(Numeric(8, 6), nullable=False)
    penalty_rate_day = Column(Numeric(8, 6), nullable=False)
    term_days = Column(SmallInteger, nullable=False)
    issued_at = Column(DateTime, nullable=False)
    due_at = Column(DateTime, nullable=False)
    accrued_at = Column(DateTime, nullable=False)
    interest_carry = Column(Numeric(16, 6), nullable=False, default=0, server_default="0")
    closed_at = Column(DateTime, nullable=True)
    closed_by_user_id = Column(Integer, nullable=True)
    note = Column(String(500), nullable=True)
    active_character_id = Column(Integer, nullable=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("active_character_id", name="uq_bank_loans_active"),
        Index("ix_bank_loans_region_status", "region_id", "status"),
        Index("ix_bank_loans_char", "character_id"),
        Index("ix_bank_loans_status_due", "status", "due_at"),
        CheckConstraint("principal > 0 AND debt >= 0", name="ck_bank_loans_amounts"),
        CheckConstraint("status IN ('active', 'overdue', 'closed', 'written_off')", name="ck_bank_loans_status"),
    )


# --------------------------------------------------------------------------- FEAT-187 region events (migration 033)

class EconEventTemplate(Base):
    """An admin-defined region event (crisis / boon): effects built from the sim levers, see econ_events."""

    __tablename__ = "econ_event_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(32), nullable=False)                 # stable slug, immutable (chains refer to it)
    name = Column(String(100), nullable=False)
    icon = Column(String(32), nullable=False, default="alert", server_default="alert")
    kind = Column(String(4), nullable=False)                  # good | bad
    player_text = Column(String(500), nullable=False)
    admin_note = Column(String(1000), nullable=True)
    trigger_kind = Column(String(16), nullable=False, default="random", server_default="random")
    weight = Column(Numeric(7, 2), nullable=False, default=1, server_default="1.00")
    duration_min_days = Column(Numeric(6, 2), nullable=False)
    duration_max_days = Column(Numeric(6, 2), nullable=False)
    scope = Column(String(12), nullable=False, default="region", server_default="region")
    spread_chance = Column(Numeric(5, 4), nullable=False, default=0, server_default="0")
    region_templates = Column(JSON, nullable=True)            # econ_region_templates codes; NULL / [] = any
    seasons = Column(JSON, nullable=True)                     # econ_events.GAME_SEGMENTS; NULL / [] = any
    effects = Column(JSON, nullable=False)
    chains = Column(JSON, nullable=True)                      # [{"code": ..., "chance": ...}]
    is_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    updated_by_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("code", name="uq_econ_event_templates_code"),
        CheckConstraint("kind IN ('good', 'bad')", name="ck_eet_kind"),
        CheckConstraint("trigger_kind IN ('random', 'low_stability', 'manual')", name="ck_eet_trigger"),
        CheckConstraint("scope IN ('region', 'neighbours', 'country', 'world')", name="ck_eet_scope"),
        CheckConstraint("duration_min_days > 0 AND duration_max_days >= duration_min_days", name="ck_eet_duration"),
        CheckConstraint("weight >= 0 AND spread_chance >= 0 AND spread_chance <= 1", name="ck_eet_numbers"),
    )


class EconRegionEvent(Base):
    """One event instance in one region — active state AND the permanent history (never purged).

    Carries a snapshot of the template taken at start; no FK to Regions / econ_regions / econ_tick_runs
    (history outlives regions and purged runs).
    """

    __tablename__ = "econ_region_events"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    region_id = Column(BigInteger, nullable=False)
    region_name = Column(String(255), nullable=True)
    country_id = Column(BigInteger, nullable=True)
    template_id = Column(Integer, ForeignKey("econ_event_templates.id", name="fk_ere_template", ondelete="SET NULL"),
                         nullable=True)
    template_code = Column(String(32), nullable=False)
    name = Column(String(100), nullable=False)
    icon = Column(String(32), nullable=False)
    kind = Column(String(4), nullable=False)
    player_text = Column(String(500), nullable=False)
    trigger_kind = Column(String(16), nullable=False)
    effects = Column(JSON, nullable=False)
    chains = Column(JSON, nullable=True)
    spread_chance = Column(Numeric(5, 4), nullable=False, default=0, server_default="0")
    origin = Column(String(8), nullable=False)                # random | manual | spread | chain | riot
    parent_event_id = Column(_EconId, ForeignKey("econ_region_events.id", name="fk_ere_parent", ondelete="SET NULL"),
                             nullable=True)
    root_event_id = Column(BigInteger, nullable=True)
    generation = Column(SmallInteger, nullable=False, default=0, server_default="0")
    origin_key = Column(String(96), nullable=True)
    active_key = Column(String(48), nullable=True)            # 'r<region>:<code>' while active, else NULL
    status = Column(String(10), nullable=False, default="active", server_default="active")
    started_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    game_segment = Column(String(16), nullable=True)
    run_id = Column(BigInteger, nullable=True)
    started_by_user_id = Column(Integer, nullable=True)
    cancelled_by_user_id = Column(Integer, nullable=True)
    cancel_comment = Column(String(500), nullable=True)
    applied_at = Column(DateTime, nullable=True)
    applied_run_id = Column(BigInteger, nullable=True)
    population_before = Column(Integer, nullable=True)
    population_after = Column(Integer, nullable=True)
    outcome = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("origin_key", name="uq_ere_origin_key"),
        UniqueConstraint("active_key", name="uq_ere_active_key"),
        Index("ix_ere_template", "template_id"),
        Index("ix_ere_parent", "parent_event_id"),
        Index("ix_ere_region_status", "region_id", "status"),
        Index("ix_ere_status_ends", "status", "ends_at"),
        Index("ix_ere_root", "root_event_id"),
        Index("ix_ere_started", "started_at"),
        Index("ix_ere_ended", "ended_at"),
        CheckConstraint("status IN ('active', 'ended', 'cancelled')", name="ck_ere_status"),
        CheckConstraint("origin IN ('random', 'manual', 'spread', 'chain', 'riot')", name="ck_ere_origin"),
        CheckConstraint("ends_at >= started_at", name="ck_ere_time"),
    )


# --------------------------------------------------------------------------- FEAT-191 mint (migration 034)

class EconMint(Base):
    """Per-country mint settings (Countries.id, no FK). No row = all defaults (auto capital, enabled)."""

    __tablename__ = "econ_mints"

    country_id = Column(Integer, primary_key=True, autoincrement=False)
    capital_region_id = Column(Integer, nullable=True)   # NULL = auto (the single 'capital'-template region)
    season_limit = Column(BigInteger, nullable=True)     # NULL = sim param mint_season_limit
    is_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(Integer, nullable=True)


class EconMintItem(Base):
    """Ore accepted from players at a minter NPC, with its rate (items.id, no FK)."""

    __tablename__ = "econ_mint_items"

    item_id = Column(Integer, primary_key=True, autoincrement=False)
    marks_per_item = Column(Integer, nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(Integer, nullable=True)


class EconMintSeason(Base):
    """The lockable shared season limit counter of one country (court + players)."""

    __tablename__ = "econ_mint_seasons"

    country_id = Column(Integer, primary_key=True, autoincrement=False)
    period_index = Column(Integer, primary_key=True, autoincrement=False)
    minted_court = Column(BigInteger, nullable=False, default=0, server_default="0")
    minted_players = Column(BigInteger, nullable=False, default=0, server_default="0")
    ore_units_court = Column(Numeric(16, 3), nullable=False, default=0, server_default="0")
    ore_units_players = Column(Numeric(16, 3), nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=True)


# --------------------------------------------------------------------------- FEAT-192 caravans (migration 035)

class EconTradePair(Base):
    """Trade permission of two countries, symmetric (country_a < country_b, app-enforced; Countries.id, no FK).
    No row = trade forbidden."""

    __tablename__ = "econ_trade_pairs"

    country_a = Column(Integer, primary_key=True, autoincrement=False)
    country_b = Column(Integer, primary_key=True, autoincrement=False)
    is_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    duty_pct = Column(Numeric(5, 2), nullable=False, default=10, server_default="10.00")
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(Integer, nullable=True)


class EconCaravan(Base):
    """One NPC caravan (dispatch idempotency marker + kept history). Regions / countries: no FK."""

    __tablename__ = "econ_caravans"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    dispatch_run_id = Column(Integer, nullable=False)
    from_region_id = Column(Integer, nullable=False)
    to_region_id = Column(Integer, nullable=False)
    from_country_id = Column(Integer, nullable=False)
    to_country_id = Column(Integer, nullable=False)
    group_code = Column(String(32), nullable=False)
    units = Column(Numeric(16, 3), nullable=False)
    unit_price = Column(Numeric(14, 4), nullable=False)
    value = Column(BigInteger, nullable=False)
    duty = Column(BigInteger, nullable=False, default=0, server_default="0")
    duty_pct = Column(Numeric(5, 2), nullable=False, default=0, server_default="0")
    paid_purse = Column(BigInteger, nullable=False, default=0, server_default="0")
    paid_treasury = Column(BigInteger, nullable=False, default=0, server_default="0")
    travel_runs = Column(SmallInteger, nullable=False)
    runs_left = Column(SmallInteger, nullable=False)
    last_run_id = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False)                # in_transit | delivered | cancelled
    cancel_reason = Column(String(32), nullable=True)          # destination_left | destination_deleted
    goods_returned = Column(Boolean, nullable=True)
    dispatch_op_id = Column(BigInteger, nullable=True)
    finish_op_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    finished_run_id = Column(Integer, nullable=True)
    # FEAT-211 physical caravans (migration 050): a route of Locations ids (start gate ... end gate), the position on
    # it, the step clock, the one-time post-hold window and what a raid took (units / escrow marks)
    is_physical = Column(Boolean, nullable=False, default=False, server_default="0")
    route = Column(JSON, nullable=True)
    route_index = Column(SmallInteger, nullable=False, default=0, server_default="0")
    current_location_id = Column(BigInteger, nullable=True)
    next_move_at = Column(DateTime, nullable=True)
    arrived_at = Column(DateTime, nullable=True)
    hold_started_at = Column(DateTime, nullable=True)
    guard_count = Column(SmallInteger, nullable=False, default=0, server_default="0")
    stolen_units = Column(Numeric(16, 3), nullable=False, default=0, server_default="0")
    raid_paid = Column(BigInteger, nullable=False, default=0, server_default="0")

    __table_args__ = (
        UniqueConstraint("dispatch_run_id", "from_region_id", "to_region_id", "group_code",
                         name="uq_econ_caravans_dispatch"),
        Index("ix_econ_caravans_status", "status", "id"),
        Index("ix_econ_caravans_to", "to_region_id", "status"),
        Index("ix_econ_caravans_from", "from_region_id", "status"),
        Index("ix_econ_caravans_finished", "finished_at"),
        Index("ix_econ_caravans_move", "is_physical", "status", "next_move_at"),
        Index("ix_econ_caravans_loc", "current_location_id", "status"),
    )


# --------------------------------------------------------------------------- FEAT-211 raids / guards / fences (050)

class EconCaravanRaid(Base):
    """One raid on a physical caravan (UNIQUE caravan_id = one raid per caravan). Locations / regions / battles:
    no FK. status: starting | fighting | won | repelled | aborted | expired."""

    __tablename__ = "econ_caravan_raids"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    caravan_id = Column(BigInteger, nullable=False)
    leader_character_id = Column(Integer, nullable=False)
    is_group = Column(Boolean, nullable=False, default=False, server_default="0")
    location_id = Column(BigInteger, nullable=False)
    region_id = Column(BigInteger, nullable=True)
    status = Column(String(16), nullable=False)
    battle_id = Column(Integer, nullable=True)
    attacker_ids = Column(JSON, nullable=True)
    guard_ids = Column(JSON, nullable=True)
    guard_template_id = Column(Integer, nullable=True)
    guard_mult = Column(Numeric(6, 3), nullable=True)
    marks = Column(BigInteger, nullable=False, default=0, server_default="0")
    stolen_units = Column(Numeric(16, 3), nullable=False, default=0, server_default="0")
    stolen_value = Column(BigInteger, nullable=False, default=0, server_default="0")
    bales = Column(Integer, nullable=False, default=0, server_default="0")
    payout_op_id = Column(BigInteger, nullable=True)
    law_done = Column(Boolean, nullable=False, default=False, server_default="0")
    guards_despawned = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("caravan_id", name="uq_econ_caravan_raids_caravan"),
        Index("ix_econ_caravan_raids_battle", "battle_id"),
        Index("ix_econ_caravan_raids_status", "status", "id"),
    )


class EconCaravanRaidShare(Base):
    """One raider's share of a won raid (marks paid by the raid op, bales delivered via inventory-service)."""

    __tablename__ = "econ_caravan_raid_shares"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    raid_id = Column(BigInteger, nullable=False)
    character_id = Column(Integer, nullable=False)
    marks = Column(BigInteger, nullable=False, default=0, server_default="0")
    bales = Column(Integer, nullable=False, default=0, server_default="0")
    bale_item_id = Column(Integer, nullable=True)
    bales_delivered_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("raid_id", "character_id", name="uq_econ_caravan_raid_shares"),
    )


class EconCaravanGuardTemplate(Base):
    """The pool of mob templates caravan guards are spawned from (admin A8/A9)."""

    __tablename__ = "econ_caravan_guard_templates"

    mob_template_id = Column(Integer, ForeignKey("mob_templates.id", name="fk_econ_caravan_guard_tpl",
                                                 ondelete="CASCADE"), primary_key=True, autoincrement=False)
    created_at = Column(DateTime, nullable=False)


class EconFence(Base):
    """Settings of a fence NPC (role ``fence``); no row = defaults. characters.id: no FK."""

    __tablename__ = "econ_fences"

    npc_id = Column(Integer, primary_key=True, autoincrement=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    price_pct = Column(SmallInteger, nullable=False, default=40, server_default="40")
    accepted_groups = Column(JSON, nullable=True)
    cash_target = Column(BigInteger, nullable=False, default=2000, server_default="2000")
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(Integer, nullable=True)


# --------------------------------------------------------------------------- FEAT-193 guild orders (migration 036)

class EconGuildOrder(Base):
    """One opening of a region's guild order for a goods group (history kept). Regions: no FK.

    open_key = 'r<region>:<group>' while status = 'open', NULL afterwards (UNIQUE: one open order per pair)."""

    __tablename__ = "econ_guild_orders"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    region_id = Column(Integer, nullable=False)
    group_code = Column(String(32), nullable=False)
    open_key = Column(String(48), nullable=True)
    status = Column(String(16), nullable=False)                # open | filled | closed
    close_reason = Column(String(32), nullable=True)           # filled | no_shortage | no_money | disabled | region_left
    units_total = Column(Numeric(16, 3), nullable=False)
    units_left = Column(Numeric(16, 3), nullable=False)
    units_filled = Column(Numeric(16, 3), nullable=False, default=0, server_default="0")
    price_mult = Column(Numeric(10, 3), nullable=False)
    markup_pct = Column(Numeric(6, 2), nullable=False)
    pieces = Column(Integer, nullable=False, default=0, server_default="0")
    paid_total = Column(BigInteger, nullable=False, default=0, server_default="0")
    paid_treasury = Column(BigInteger, nullable=False, default=0, server_default="0")
    hand_ins = Column(Integer, nullable=False, default=0, server_default="0")
    opened_run_id = Column(Integer, nullable=False)
    last_run_id = Column(Integer, nullable=False)
    closed_run_id = Column(Integer, nullable=True)
    opened_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("open_key", name="uq_econ_guild_orders_open"),
        Index("ix_econ_guild_orders_region", "region_id", "status"),
        Index("ix_econ_guild_orders_status", "status", "id"),
        Index("ix_econ_guild_orders_closed", "closed_at"),
    )


class EconGuildXpDay(Base):
    """Base guild XP granted to a character on one UTC day (the daily cap counter)."""

    __tablename__ = "econ_guild_xp_days"

    character_id = Column(Integer, primary_key=True, autoincrement=False)
    day = Column(Date, primary_key=True)
    xp = Column(Integer, nullable=False, default=0, server_default="0")


# --------------------------------------------------------------------------- FEAT-197 reputation (migration 038)
# Writes go through reputation_crud.apply_reputation only (raw SQL row creation + locked ORM updates).

class CharacterReputation(Base):
    """Reputation value per (character, region); no row = 0. ``decay_at`` anchors the negative decay."""

    __tablename__ = "character_reputation"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("characters.id", name="fk_char_rep_character", ondelete="CASCADE"),
                          nullable=False)
    region_id = Column(Integer, nullable=False)                 # Regions.id (no FK)
    value = Column(Integer, nullable=False, default=0, server_default="0")
    decay_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("character_id", "region_id", name="uq_char_rep"),
        Index("ix_char_rep_decay", "decay_at"),
    )


class ReputationLog(Base):
    """One applied change (origin and echo rows share ``event_key``; UNIQUE(event_key, region_id))."""

    __tablename__ = "reputation_log"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("characters.id", name="fk_rep_log_character", ondelete="CASCADE"),
                          nullable=False)
    region_id = Column(Integer, nullable=False)
    action = Column(String(40), nullable=False)
    event_key = Column(String(191), nullable=False)
    is_echo = Column(Boolean, nullable=False, default=False, server_default="0")
    origin_region_id = Column(Integer, nullable=True)
    requested_delta = Column(Integer, nullable=False)
    applied_delta = Column(Integer, nullable=False)
    value_after = Column(Integer, nullable=False)
    tier_before = Column(String(20), nullable=False)
    tier_after = Column(String(20), nullable=False)
    reason = Column(String(500), nullable=True)
    actor_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("event_key", "region_id", name="uq_rep_log_event"),
        Index("ix_rep_log_char", "character_id", "created_at"),
        Index("ix_rep_log_cap", "character_id", "region_id", "action", "created_at"),
    )


class ReputationSettings(Base):
    """Single row id=1."""

    __tablename__ = "reputation_settings"

    id = Column(Integer, primary_key=True, autoincrement=False)
    min_value = Column(Integer, nullable=False, default=-1000, server_default="-1000")
    max_value = Column(Integer, nullable=False, default=1000, server_default="1000")
    echo_pct = Column(Numeric(5, 2), nullable=False, default=20, server_default="20.00")
    decay_per_day = Column(Numeric(8, 2), nullable=False, default=10, server_default="10.00")
    decay_last_run_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False)


class ReputationTier(Base):
    """Exactly 8 rows with the fixed codes of reputation_core.TIER_CODES."""

    __tablename__ = "reputation_tiers"

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, unique=True)
    name = Column(String(60), nullable=False)
    min_value = Column(Integer, nullable=True)
    price_pct = Column(Numeric(5, 2), nullable=False, default=0, server_default="0")
    sell_pct = Column(Numeric(5, 2), nullable=False, default=0, server_default="0")
    trade_refused = Column(Boolean, nullable=False, default=False, server_default="0")


class ReputationAction(Base):
    __tablename__ = "reputation_actions"

    code = Column(String(40), primary_key=True)
    name = Column(String(100), nullable=False)
    points = Column(Integer, nullable=False, default=0, server_default="0")
    daily_cap = Column(Integer, nullable=True)
    is_builtin = Column(Boolean, nullable=False, default=False, server_default="0")
    has_source = Column(Boolean, nullable=False, default=False, server_default="0")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")


class ReputationNpcRoleWeight(Base):
    __tablename__ = "reputation_npc_role_weights"

    role = Column(String(50), primary_key=True)
    points = Column(Integer, nullable=False)


# --------------------------------------------------------------------------- FEAT-198 law (migration 039)
# Writes go through law_crud only. No FK to Regions / Locations (owned by locations-service).

class CharacterWanted(Base):
    """Wanted value per (character, region); no row = 0. ``decay_at`` anchors the linear decay (NULL at 0)."""

    __tablename__ = "character_wanted"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("characters.id", name="fk_char_wanted_character", ondelete="CASCADE"),
                          nullable=False)
    region_id = Column(Integer, nullable=False)
    value = Column(Integer, nullable=False, default=0, server_default="0")
    decay_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("character_id", "region_id", name="uq_char_wanted"),
        Index("ix_char_wanted_region", "region_id"),
    )


class LawSettings(Base):
    """Single row id=1."""

    __tablename__ = "law_settings"

    id = Column(Integer, primary_key=True, autoincrement=False)
    max_wanted = Column(Integer, nullable=False, default=1000, server_default="1000")
    decay_per_day = Column(Numeric(8, 2), nullable=False, default=50, server_default="50.00")
    heavy_wanted = Column(Integer, nullable=False, default=600, server_default="600")
    outlaw_min_level = Column(String(20), nullable=False, default="criminal", server_default="criminal")
    encounter_timeout_hours = Column(Integer, nullable=False, default=24, server_default="24")
    guard_ko_hours = Column(Integer, nullable=False, default=6, server_default="6")
    flee_base_pct = Column(Numeric(5, 2), nullable=False, default=20, server_default="20.00")
    flee_per_point_pct = Column(Numeric(6, 3), nullable=False, default=0.25, server_default="0.250")
    flee_min_pct = Column(Numeric(5, 2), nullable=False, default=5, server_default="5.00")
    flee_max_pct = Column(Numeric(5, 2), nullable=False, default=85, server_default="85.00")
    escape_base_pct = Column(Numeric(5, 2), nullable=False, default=5, server_default="5.00")
    escape_per_point_pct = Column(Numeric(6, 3), nullable=False, default=0.3, server_default="0.300")
    escape_min_pct = Column(Numeric(5, 2), nullable=False, default=2, server_default="2.00")
    escape_max_pct = Column(Numeric(5, 2), nullable=False, default=50, server_default="50.00")
    escape_cooldown_hours = Column(Integer, nullable=False, default=6, server_default="6")
    escape_fail_extend_pct = Column(Numeric(5, 2), nullable=False, default=50, server_default="50.00")
    max_remaining_jail_hours = Column(Integer, nullable=False, default=168, server_default="168")
    bail_multiplier = Column(Numeric(5, 2), nullable=False, default=2, server_default="2.00")
    # FEAT-202 (042): the country prison
    country_prison_min_level = Column(String(20), nullable=False, default="villain", server_default="villain")
    country_escape_multiplier = Column(Numeric(5, 2), nullable=False, default=0.5, server_default="0.50")
    country_escape_cooldown_hours = Column(Integer, nullable=False, default=12, server_default="12")
    # FEAT-203 (043): the guard-detection roll on entry
    detect_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    detect_base_safe_pct = Column(Numeric(5, 2), nullable=False, default=100, server_default="100.00")
    detect_base_farm_pct = Column(Numeric(5, 2), nullable=False, default=70, server_default="70.00")
    detect_base_dangerous_pct = Column(Numeric(5, 2), nullable=False, default=40, server_default="40.00")
    detect_base_dungeon_pct = Column(Numeric(5, 2), nullable=False, default=25, server_default="25.00")
    detect_base_default_pct = Column(Numeric(5, 2), nullable=False, default=50, server_default="50.00")
    detect_per_guard_pct = Column(Numeric(5, 2), nullable=False, default=10, server_default="10.00")
    detect_mask_factor_pct = Column(Numeric(5, 2), nullable=False, default=75, server_default="75.00")
    detect_min_pct = Column(Numeric(5, 2), nullable=False, default=5, server_default="5.00")
    detect_max_pct = Column(Numeric(5, 2), nullable=False, default=100, server_default="100.00")
    # FEAT-204 (044): guard patrols — the global switch and the max hold of a patrol guard by an open encounter
    patrols_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    patrol_encounter_hold_min = Column(Integer, nullable=False, default=30, server_default="30")
    pass_last_run_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False)


class LawLevel(Base):
    """Exactly 5 rows with the fixed codes of law_core.LEVEL_CODES."""

    __tablename__ = "law_levels"

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, unique=True)
    name = Column(String(60), nullable=False)
    min_value = Column(Integer, nullable=False)
    fine = Column(Integer, nullable=False)
    jail_hours = Column(Integer, nullable=False)
    # FEAT-203 (043): the severity multiplier of the guard-detection chance, %
    detect_pct = Column(Numeric(5, 2), nullable=False, default=100, server_default="100.00")


class LawCrime(Base):
    """A crime event (stage 2b inserts a witness step between ``reported`` and the wanted change)."""

    __tablename__ = "law_crimes"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    event_key = Column(String(191), nullable=False)
    crime_type = Column(String(30), nullable=False)
    character_id = Column(Integer, ForeignKey("characters.id", name="fk_law_crime_character", ondelete="CASCADE"),
                          nullable=False)
    region_id = Column(Integer, nullable=False)
    location_id = Column(Integer, nullable=True)
    victim_character_id = Column(Integer, nullable=True)
    battle_id = Column(Integer, nullable=True)
    wanted_points = Column(Integer, nullable=False)
    wanted_applied = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String(20), nullable=False)             # reported | unwitnessed | masked | closed (FEAT-199)
    created_at = Column(DateTime, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    # FEAT-199 (migration 040): the snapshot a deferred (unwitnessed / masked) crime applies on reveal
    reputation_delta = Column(Integer, nullable=True)
    reputation_key = Column(String(191), nullable=True)     # EXACT apply_reputation idem key
    reputation_reason = Column(String(255), nullable=True)
    wanted_floor = Column(Integer, nullable=True)
    masked = Column(Boolean, nullable=False, default=False, server_default="0")
    witness_chance_pct = Column(Numeric(5, 2), nullable=True)
    witness_roll_pct = Column(Numeric(5, 2), nullable=True)
    stealth_reduction_pct = Column(Numeric(5, 2), nullable=True)   # FEAT-201 (041): reveal snapshot, NULL = 0
    reveal_until = Column(DateTime, nullable=True)
    next_roll_at = Column(DateTime, nullable=True)
    reveal_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    revealed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("event_key", name="uq_law_crime_key"),
        Index("ix_law_crime_char", "character_id", "created_at"),
        Index("ix_law_crime_status", "status"),
        Index("ix_law_crime_reveal", "status", "next_roll_at"),
    )


class LawEncounter(Base):
    __tablename__ = "law_encounters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("characters.id", name="fk_law_enc_character", ondelete="CASCADE"),
                          nullable=False)
    region_id = Column(Integer, nullable=False)
    location_id = Column(Integer, nullable=False)
    from_location_id = Column(Integer, nullable=True)       # where the character came from (a flee goes back there)
    guard_npc_id = Column(Integer, nullable=True)
    is_outlaw = Column(Boolean, nullable=False)
    has_jail = Column(Boolean, nullable=False)
    level_code = Column(String(20), nullable=False)
    wanted_value = Column(Integer, nullable=False)
    fine = Column(Integer, nullable=False)
    jail_hours = Column(Integer, nullable=False)
    flee_used = Column(Boolean, nullable=False, default=False, server_default="0")
    status = Column(String(20), nullable=False)
    battle_id = Column(Integer, nullable=True)
    source = Column(String(20), nullable=False)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    fight_started_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    cooldown_until = Column(DateTime, nullable=True)        # after a successful flee: no new stop here until then

    __table_args__ = (
        Index("ix_law_enc_char", "character_id", "created_at"),
        Index("ix_law_enc_status", "status", "expires_at"),
        Index("ix_law_enc_battle", "battle_id"),
        Index("ix_law_enc_cooldown", "character_id", "location_id", "cooldown_until"),
        Index("ix_law_enc_guard", "guard_npc_id", "status"),          # FEAT-204 (044): is a guard held?
    )


class GuardPatrol(Base):
    """FEAT-204 (044): the patrol of one guard NPC (no row = a fixed post). Written by patrol_crud only.
    No FK (the NPC delete cleans up explicitly)."""

    __tablename__ = "guard_patrols"

    npc_id = Column(Integer, primary_key=True, autoincrement=False)
    mode = Column(String(10), nullable=False, default="post", server_default="post")            # post|route|zone
    route_style = Column(String(10), nullable=False, default="loop", server_default="loop")     # loop|pingpong
    zone_kind = Column(String(10), nullable=False, default="district", server_default="district")  # district|locations
    zone_district_id = Column(BigInteger, nullable=True)
    interval_min = Column(SmallInteger, nullable=False, default=20, server_default="20")
    jitter_pct = Column(SmallInteger, nullable=False, default=25, server_default="25")
    next_move_at = Column(DateTime, nullable=True)
    route_index = Column(SmallInteger, nullable=False, default=0, server_default="0")
    route_dir = Column(SmallInteger, nullable=False, default=1, server_default="1")
    last_location_id = Column(BigInteger, nullable=True)
    last_moved_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False)
    updated_by_user_id = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_guard_patrols_due", "mode", "next_move_at"),
    )


class GuardPatrolPoint(Base):
    """FEAT-204 (044): an ordered route point / a zone location of a guard patrol."""

    __tablename__ = "guard_patrol_points"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    npc_id = Column(Integer, nullable=False)
    kind = Column(String(10), nullable=False)               # route | zone
    position = Column(SmallInteger, nullable=False)
    location_id = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("npc_id", "kind", "position", name="uq_guard_patrol_point"),
        Index("ix_guard_patrol_point_loc", "location_id"),
    )


class LawJailTerm(Base):
    __tablename__ = "law_jail_terms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("characters.id", name="fk_law_jail_character", ondelete="CASCADE"),
                          nullable=False)
    region_id = Column(Integer, nullable=False)
    location_id = Column(Integer, nullable=False)
    encounter_id = Column(Integer, nullable=True)
    level_code = Column(String(20), nullable=False)
    fine_base = Column(Integer, nullable=False)
    bail_price = Column(Integer, nullable=False)
    started_at = Column(DateTime, nullable=False)
    until = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False)
    escape_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    next_escape_at = Column(DateTime, nullable=True)
    bailed_by_character_id = Column(Integer, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    notified = Column(Boolean, nullable=False, default=False, server_default="0")
    # FEAT-202 (042): the facility snapshot; `region_id` stays the crime / wanted region
    facility = Column(String(10), nullable=False, default="station", server_default="station")
    country_id = Column(Integer, nullable=True)
    district_id = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_law_jail_char", "character_id", "status"),
        Index("ix_law_jail_status", "status", "until"),
    )


class LawLog(Base):
    __tablename__ = "law_log"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    event_key = Column(String(191), nullable=False)
    character_id = Column(Integer, ForeignKey("characters.id", name="fk_law_log_character", ondelete="CASCADE"),
                          nullable=False)
    region_id = Column(Integer, nullable=True)
    action = Column(String(30), nullable=False)
    wanted_before = Column(Integer, nullable=True)
    wanted_after = Column(Integer, nullable=True)
    amount = Column(Integer, nullable=True)
    chance_pct = Column(Numeric(5, 2), nullable=True)
    roll_pct = Column(Numeric(5, 2), nullable=True)
    ref_id = Column(Integer, nullable=True)
    reason = Column(String(500), nullable=True)
    actor_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("event_key", name="uq_law_log_key"),
        Index("ix_law_log_char", "character_id", "created_at"),
    )


# --------------------------------------------------------------------------- FEAT-199 shadow / renown (migration 040)
# Writes go through shadow_crud / renown_crud only.

class ShadowSettings(Base):
    """Single row id=1 (witness / reveal / suspicion / infamy / fame weights)."""

    __tablename__ = "shadow_settings"

    id = Column(Integer, primary_key=True, autoincrement=False)
    witness_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    witness_base_safe_pct = Column(Numeric(5, 2), nullable=False, default=100, server_default="100.00")
    witness_base_farm_pct = Column(Numeric(5, 2), nullable=False, default=70, server_default="70.00")
    witness_base_dangerous_pct = Column(Numeric(5, 2), nullable=False, default=40, server_default="40.00")
    witness_base_dungeon_pct = Column(Numeric(5, 2), nullable=False, default=25, server_default="25.00")
    witness_base_default_pct = Column(Numeric(5, 2), nullable=False, default=50, server_default="50.00")
    # FEAT-201 (migration 041): the stealth stat (effective, capped) multiplies the chance down
    stealth_pct_per_point = Column(Numeric(6, 3), nullable=False, default=0.5, server_default="0.500")
    stealth_max_reduction_pct = Column(Numeric(5, 2), nullable=False, default=90, server_default="90.00")
    stealth_assassin_points = Column(Integer, nullable=False, default=30, server_default="30")
    stealth_trickster_points = Column(Integer, nullable=False, default=30, server_default="30")
    stealth_agent_points = Column(Integer, nullable=False, default=20, server_default="20")
    witness_group_per_extra_pct = Column(Numeric(5, 2), nullable=False, default=10, server_default="10.00")
    witness_min_pct = Column(Numeric(5, 2), nullable=False, default=5, server_default="5.00")
    witness_max_pct = Column(Numeric(5, 2), nullable=False, default=100, server_default="100.00")
    reveal_days = Column(Integer, nullable=False, default=3, server_default="3")
    reveal_base_pct = Column(Numeric(5, 2), nullable=False, default=15, server_default="15.00")
    reveal_per_suspicion_pct = Column(Numeric(6, 3), nullable=False, default=0.4, server_default="0.400")
    reveal_mask_factor_pct = Column(Numeric(5, 2), nullable=False, default=50, server_default="50.00")
    reveal_min_pct = Column(Numeric(5, 2), nullable=False, default=1, server_default="1.00")
    reveal_max_pct = Column(Numeric(5, 2), nullable=False, default=90, server_default="90.00")
    suspicion_max = Column(Integer, nullable=False, default=100, server_default="100")
    suspicion_unwitnessed = Column(Integer, nullable=False, default=10, server_default="10")
    suspicion_masked = Column(Integer, nullable=False, default=20, server_default="20")
    suspicion_decay_per_day = Column(Numeric(8, 2), nullable=False, default=5, server_default="5.00")
    suspicion_uneasy_at = Column(Integer, nullable=False, default=20, server_default="20")
    suspicion_alarmed_at = Column(Integer, nullable=False, default=50, server_default="50")
    suspicion_fear_at = Column(Integer, nullable=False, default=80, server_default="80")
    infamy_ratio = Column(Numeric(6, 3), nullable=False, default=1, server_default="1.000")
    infamy_min_gain = Column(Integer, nullable=False, default=10, server_default="10")
    fame_quest_default = Column(Integer, nullable=False, default=5, server_default="5")
    fame_rep_ratio = Column(Numeric(6, 3), nullable=False, default=0.5, server_default="0.500")
    fame_guild_ratio = Column(Numeric(6, 3), nullable=False, default=0, server_default="0.000")
    updated_at = Column(DateTime, nullable=False)


class RegionSuspicion(Base):
    """Suspicion per region (Regions.id, no FK); lazy linear decay from ``decay_at`` (NULL at 0)."""

    __tablename__ = "region_suspicion"

    region_id = Column(Integer, primary_key=True, autoincrement=False)
    value = Column(Integer, nullable=False, default=0, server_default="0")
    decay_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False)


class CharacterRenown(Base):
    """Fame (public as a tier) and infamy (owner + staff) of a character; no row = 0 / 0."""

    __tablename__ = "character_renown"

    character_id = Column(Integer, ForeignKey("characters.id", name="fk_char_renown_character", ondelete="CASCADE"),
                          primary_key=True, autoincrement=False)
    fame = Column(Integer, nullable=False, default=0, server_default="0")
    infamy = Column(Integer, nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime, nullable=False)


class RenownTier(Base):
    """Exactly 5 rows per scale with the fixed codes of shadow_core.FAME_CODES / INFAMY_CODES."""

    __tablename__ = "renown_tiers"

    scale = Column(String(10), primary_key=True)
    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False)
    name = Column(String(60), nullable=False)
    min_value = Column(Integer, nullable=False)
    witness_pct = Column(Numeric(5, 2), nullable=False, default=0, server_default="0.00")

    __table_args__ = (
        UniqueConstraint("scale", "sort_order", name="uq_renown_tier_order"),
    )


class RenownLog(Base):
    __tablename__ = "renown_log"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    event_key = Column(String(191), nullable=False)
    character_id = Column(Integer, ForeignKey("characters.id", name="fk_renown_log_character", ondelete="CASCADE"),
                          nullable=False)
    scale = Column(String(10), nullable=False)
    source = Column(String(30), nullable=False)
    delta = Column(Integer, nullable=False)
    value_after = Column(Integer, nullable=False)
    tier_before = Column(String(20), nullable=False)
    tier_after = Column(String(20), nullable=False)
    ref_id = Column(BigInteger, nullable=True)
    reason = Column(String(500), nullable=True)
    actor_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("event_key", name="uq_renown_log_key"),
        Index("ix_renown_log_char", "character_id", "created_at"),
    )


# --------------------------------------------------------------------------- FEAT-205 factions (migration 045)
# Rules: faction_core (pure); flows: faction_crud / faction_admin_crud; rewards outbox: faction_rewards.

class Faction(Base):
    __tablename__ = "factions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    emblem_url = Column(String(512), nullable=True)
    hq_location_id = Column(BigInteger, nullable=True)          # Locations.id (no FK, cross-service)
    leader_npc_ids = Column(JSON, nullable=True)                # [characters.id of NPCs]
    member_limit = Column(Integer, nullable=True)               # NULL = unlimited
    is_invite_only = Column(Boolean, nullable=False, default=False, server_default="0")
    is_secret = Column(Boolean, nullable=False, default=False, server_default="0")
    is_active = Column(Boolean, nullable=False, default=False, server_default="0")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    # FEAT-207 (migration 047): per-faction kill-point day cap (NULL = faction_settings.kill_points_daily_cap)
    kill_points_daily_cap = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("name", name="uq_factions_name"),
    )


class FactionRank(Base):
    __tablename__ = "faction_ranks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_rank_faction", ondelete="CASCADE"),
                        nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False)
    min_points = Column(Integer, nullable=False, default=0, server_default="0")
    min_level = Column(Integer, nullable=False, default=0, server_default="0")
    required_quest_id = Column(BigInteger, nullable=True)       # quests.id (non-repeatable)
    reward_xp = Column(Integer, nullable=False, default=0, server_default="0")
    reward_title_id = Column(Integer, nullable=True)            # titles.id_title (validated)
    reward_items = Column(JSON, nullable=True)                  # [{item_id, quantity}]
    reward_house_location_id = Column(BigInteger, nullable=True)
    reward_plot_location_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, nullable=False)
    # FEAT-206 (migration 046): marks paid through the debt queue on grant; quartermaster discount of this rank
    reward_marks = Column(Integer, nullable=False, default=0, server_default="0")
    qm_discount_pct = Column(Integer, nullable=False, default=0, server_default="0")
    # FEAT-207 (migration 047): battle-time passive of this rank (cumulative up the ladder)
    passive_name = Column(String(100), nullable=True)
    passive_description = Column(String(500), nullable=True)
    passive_modifiers = Column(JSON, nullable=True)             # {key: int}, keys in faction_core.FACTION_PASSIVE_KEYS

    __table_args__ = (
        Index("ix_faction_ranks_order", "faction_id", "sort_order"),
    )


class FactionCondition(Base):
    __tablename__ = "faction_conditions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_cond_faction", ondelete="CASCADE"),
                        nullable=False, index=True)
    cond_type = Column(String(30), nullable=False)
    params = Column(JSON, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")


class FactionHostility(Base):
    __tablename__ = "faction_hostilities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    faction_a_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_host_a", ondelete="CASCADE"),
                          nullable=False)                       # always faction_a_id < faction_b_id
    faction_b_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_host_b", ondelete="CASCADE"),
                          nullable=False)
    irreconcilable = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("faction_a_id", "faction_b_id", name="uq_faction_hostility"),
        Index("ix_faction_host_b", "faction_b_id"),
    )


class FactionMember(Base):
    """One row per (character, faction); survives leave / expel (status), so rejoin reuses it."""

    __tablename__ = "faction_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("characters.id", name="fk_faction_member_character", ondelete="CASCADE"),
                          nullable=False)
    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_member_faction", ondelete="CASCADE"),
                        nullable=False)
    status = Column(String(10), nullable=False)                 # active | left | expelled
    points = Column(Integer, nullable=False, default=0, server_default="0")
    rank_id = Column(Integer, ForeignKey("faction_ranks.id", name="fk_faction_member_rank", ondelete="SET NULL"),
                     nullable=True, index=True)
    joined_at = Column(DateTime, nullable=False)
    left_at = Column(DateTime, nullable=True)
    rejoin_after = Column(DateTime, nullable=True)
    warning_at = Column(DateTime, nullable=True)
    warning_reasons = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("character_id", "faction_id", name="uq_faction_member"),
        Index("ix_faction_members_status", "faction_id", "status"),
        Index("ix_faction_members_warning", "status", "warning_at"),
    )


class FactionApplication(Base):
    __tablename__ = "faction_applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("characters.id", name="fk_faction_app_character", ondelete="CASCADE"),
                          nullable=False, index=True)
    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_app_faction", ondelete="CASCADE"),
                        nullable=False, index=True)
    status = Column(String(10), nullable=False)                 # pending | approved | rejected | cancelled
    message = Column(String(500), nullable=True)
    pending_key = Column(String(40), nullable=True)             # "{character_id}:{faction_id}" while pending
    reject_reason = Column(String(500), nullable=True)
    decided_by_user_id = Column(Integer, nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("pending_key", name="uq_faction_app_pending"),
        Index("ix_faction_app_status", "status", "created_at"),
    )


class FactionRankGrant(Base):
    """Rank reward ledger: once per (character, rank), forever (leave / rejoin never re-grants)."""

    __tablename__ = "faction_rank_grants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("characters.id", name="fk_faction_grant_character", ondelete="CASCADE"),
                          nullable=False)
    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_grant_faction", ondelete="CASCADE"),
                        nullable=False, index=True)
    rank_id = Column(Integer, ForeignKey("faction_ranks.id", name="fk_faction_grant_rank", ondelete="RESTRICT"),
                     nullable=False, index=True)
    granted_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("character_id", "rank_id", name="uq_faction_grant"),
    )


class FactionRewardDelivery(Base):
    """Outbox: one row per reward component of a grant (xp | title | item | voucher)."""

    __tablename__ = "faction_reward_deliveries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    grant_id = Column(Integer, ForeignKey("faction_rank_grants.id", name="fk_faction_delivery_grant",
                                          ondelete="CASCADE"), nullable=False, index=True)
    character_id = Column(Integer, nullable=False, index=True)
    kind = Column(String(15), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(String(10), nullable=False)                 # pending | sending | done | failed
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at = Column(DateTime, nullable=False)
    last_error = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_faction_delivery_due", "status", "next_attempt_at"),
    )


class FactionLog(Base):
    """Player journal + audit; ``event_key`` + UNIQUE(event_key, faction_id) = idempotency."""

    __tablename__ = "faction_log"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("characters.id", name="fk_faction_log_character", ondelete="CASCADE"),
                          nullable=False)
    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_log_faction", ondelete="CASCADE"),
                        nullable=False, index=True)
    event_type = Column(String(30), nullable=False)
    points_delta = Column(Integer, nullable=True)
    points_after = Column(Integer, nullable=True)
    rank_id = Column(Integer, nullable=True)
    event_key = Column(String(120), nullable=True)
    reason = Column(String(500), nullable=True)
    actor_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("event_key", "faction_id", name="uq_faction_log_key"),
        Index("ix_faction_log_char", "character_id", "id"),
    )


class FactionSettings(Base):
    """Single row id=1 (seeded by migration 045)."""

    __tablename__ = "faction_settings"

    id = Column(Integer, primary_key=True, autoincrement=False)
    warning_days = Column(Integer, nullable=False, default=3, server_default="3")
    rejoin_cooldown_days = Column(Integer, nullable=False, default=7, server_default="7")
    leave_burn_pct = Column(Integer, nullable=False, default=50, server_default="50")
    hostile_penalty_pct = Column(Integer, nullable=False, default=50, server_default="50")
    reapply_cooldown_hours = Column(Integer, nullable=False, default=24, server_default="24")
    pass_last_run_at = Column(DateTime, nullable=True)
    # FEAT-206 (migration 046): donations, the faction tick step, quartermaster restock
    donation_marks_per_point = Column(Integer, nullable=False, default=10, server_default="10")
    donation_points_daily_cap = Column(Integer, nullable=False, default=50, server_default="50")
    econ_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    econ_purse_share_pct = Column(Integer, nullable=False, default=2, server_default="2")
    econ_treasury_share_pct = Column(Integer, nullable=False, default=1, server_default="1")
    members_leave_pct = Column(Integer, nullable=False, default=5, server_default="5")
    members_grow_pct = Column(Integer, nullable=False, default=1, server_default="1")
    qm_take_share_pct = Column(Integer, nullable=False, default=5, server_default="5")
    # FEAT-207 (migration 047): kill points, outlaw membership checks, donated item sale
    kill_points_daily_cap = Column(Integer, nullable=False, default=50, server_default="50")
    pvp_kill_repeat_hours = Column(Integer, nullable=False, default=24, server_default="24")
    outlaw_check_cooldown_hours = Column(Integer, nullable=False, default=24, server_default="24")
    econ_item_sale_share_pct = Column(Integer, nullable=False, default=2, server_default="2")


# --------------------------------------------------------------------------- FEAT-206 faction economy (migration 046)
# Rules: faction_econ (pure); flows: faction_econ_crud / faction_qm_crud; tick step: econ_tick._faction_econ_pass.

class FactionEconTemplate(Base):
    __tablename__ = "faction_econ_templates"

    code = Column(String(32), primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    params = Column(JSON, nullable=False)                       # whitelisted keys (faction_econ.PARAM_KEYS)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime, nullable=False)


class FactionEconomy(Base):
    """1:1 with ``factions`` (ensured lazily by faction_econ_crud.ensure_economy_row)."""

    __tablename__ = "faction_economy"

    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_econ_faction", ondelete="CASCADE"),
                        primary_key=True, autoincrement=False)
    template_code = Column(String(32), ForeignKey("faction_econ_templates.code", name="fk_faction_econ_template",
                                                  ondelete="RESTRICT"), nullable=True, index=True)
    overrides = Column(JSON, nullable=True)
    econ_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    members_count = Column(Integer, nullable=False, default=0, server_default="0")
    members_carry = Column(Numeric(10, 4), nullable=False, default=0, server_default="0")
    members_min = Column(Integer, nullable=False, default=10, server_default="10")
    members_max = Column(Integer, nullable=False, default=5000, server_default="5000")
    payout_seq = Column(Integer, nullable=False, default=0, server_default="0")
    last_run_id = Column(BigInteger, nullable=True)
    last_tick_at = Column(DateTime, nullable=True)
    last_dues = Column(BigInteger, nullable=False, default=0, server_default="0")
    last_profile = Column(BigInteger, nullable=False, default=0, server_default="0")
    last_wages_due = Column(BigInteger, nullable=False, default=0, server_default="0")
    last_wages_paid = Column(BigInteger, nullable=False, default=0, server_default="0")
    last_restock = Column(BigInteger, nullable=False, default=0, server_default="0")
    last_debts_paid = Column(BigInteger, nullable=False, default=0, server_default="0")
    last_members_delta = Column(Integer, nullable=False, default=0, server_default="0")
    last_wealth = Column(Integer, nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime, nullable=False)
    last_item_sales = Column(BigInteger, nullable=False, default=0, server_default="0")    # FEAT-207


class FactionEconHistory(Base):
    __tablename__ = "faction_econ_history"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, nullable=False)
    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_econ_hist_faction", ondelete="CASCADE"),
                        nullable=False)
    balance_before = Column(BigInteger, nullable=False, default=0, server_default="0")
    balance_after = Column(BigInteger, nullable=False, default=0, server_default="0")
    dues = Column(BigInteger, nullable=False, default=0, server_default="0")
    profile = Column(BigInteger, nullable=False, default=0, server_default="0")
    wages_due = Column(BigInteger, nullable=False, default=0, server_default="0")
    wages_paid = Column(BigInteger, nullable=False, default=0, server_default="0")
    restock_spent = Column(BigInteger, nullable=False, default=0, server_default="0")
    restock_items = Column(Integer, nullable=False, default=0, server_default="0")
    debts_paid = Column(BigInteger, nullable=False, default=0, server_default="0")
    members_before = Column(Integer, nullable=False, default=0, server_default="0")
    members_after = Column(Integer, nullable=False, default=0, server_default="0")
    wealth = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, nullable=False)
    item_sales = Column(BigInteger, nullable=False, default=0, server_default="0")         # FEAT-207
    items_sold = Column(Integer, nullable=False, default=0, server_default="0")

    __table_args__ = (
        UniqueConstraint("run_id", "faction_id", name="uq_faction_econ_hist_run"),
        Index("ix_faction_econ_hist_faction", "faction_id", "id"),
    )


class FactionDebt(Base):
    """Payout queue (rank marks, deferred refunds); survives leave / expel / hide; paid FIFO, partially."""

    __tablename__ = "faction_debts"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("characters.id", name="fk_faction_debt_character", ondelete="CASCADE"),
                          nullable=False)
    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_debt_faction", ondelete="CASCADE"),
                        nullable=False)
    source = Column(String(10), nullable=False)                 # rank | refund
    source_key = Column(String(64), nullable=False)             # rank:g<grant_id> | refund:p<purchase_id>
    amount = Column(BigInteger, nullable=False)
    paid = Column(BigInteger, nullable=False, default=0, server_default="0")
    status = Column(String(8), nullable=False)                  # open | paid
    unpaid_notified = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime, nullable=False)
    paid_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("source_key", name="uq_faction_debt_source"),
        Index("ix_faction_debts_queue", "faction_id", "status", "id"),
        Index("ix_faction_debts_character", "character_id", "status"),
    )


class FactionDonationDay(Base):
    __tablename__ = "faction_donation_days"

    character_id = Column(Integer, ForeignKey("characters.id", name="fk_faction_don_character", ondelete="CASCADE"),
                          primary_key=True, autoincrement=False)
    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_don_faction", ondelete="CASCADE"),
                        primary_key=True, autoincrement=False, index=True)
    day = Column(Date, primary_key=True)
    marks = Column(BigInteger, nullable=False, default=0, server_default="0")
    points = Column(Integer, nullable=False, default=0, server_default="0")
    kill_points = Column(Integer, nullable=False, default=0, server_default="0")          # FEAT-207 own day cap


class FactionQuartermaster(Base):
    __tablename__ = "faction_quartermasters"

    npc_id = Column(Integer, ForeignKey("characters.id", name="fk_faction_qm_npc", ondelete="CASCADE"),
                    primary_key=True, autoincrement=False)
    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_qm_faction", ondelete="CASCADE"),
                        nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)


class FactionQmItem(Base):
    __tablename__ = "faction_qm_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_qm_item_faction", ondelete="CASCADE"),
                        nullable=False)
    item_id = Column(Integer, nullable=False)                   # items.id (validated, no FK)
    price = Column(Integer, nullable=False)
    min_rank_id = Column(Integer, ForeignKey("faction_ranks.id", name="fk_faction_qm_item_rank", ondelete="RESTRICT"),
                         nullable=True, index=True)
    stock = Column(Integer, nullable=False, default=0, server_default="0")
    restock_target = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("faction_id", "item_id", name="uq_faction_qm_item"),
        Index("ix_faction_qm_items_order", "faction_id", "sort_order"),
    )


class FactionQmPurchase(Base):
    """Purchase journal + item delivery outbox (pending | sending | done | failed | refunded)."""

    __tablename__ = "faction_qm_purchases"

    id = Column(_EconId, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("characters.id", name="fk_faction_qmp_character", ondelete="CASCADE"),
                          nullable=False, index=True)
    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_qmp_faction", ondelete="CASCADE"),
                        nullable=False, index=True)
    qm_item_id = Column(Integer, ForeignKey("faction_qm_items.id", name="fk_faction_qmp_item", ondelete="SET NULL"),
                        nullable=True, index=True)
    npc_id = Column(Integer, nullable=True)
    item_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    price_total = Column(BigInteger, nullable=False)
    op_key = Column(String(128), nullable=False)
    status = Column(String(10), nullable=False)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at = Column(DateTime, nullable=False)
    last_error = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("op_key", name="uq_faction_qm_purchase_key"),
        Index("ix_faction_qm_purchases_due", "status", "next_attempt_at"),
    )


# --------------------------------------------------------------------------- FEAT-207 territory / enemies (migration 047)
# Rules: faction_core (pure); flows: faction_territory / faction_kills / faction_items.

class FactionAccessRule(Base):
    """A closed location / dungeon: only active members (optionally from a rank up) may enter."""

    __tablename__ = "faction_access_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String(10), nullable=False)                   # location | dungeon
    target_id = Column(BigInteger, nullable=False)              # Locations.id | dungeons.id (validated, no FK)
    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_access_faction", ondelete="CASCADE"),
                        nullable=False, index=True)
    min_rank_id = Column(Integer, ForeignKey("faction_ranks.id", name="fk_faction_access_rank", ondelete="RESTRICT"),
                         nullable=True, index=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("kind", "target_id", name="uq_faction_access_target"),
    )


class FactionEnemy(Base):
    __tablename__ = "faction_enemies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_enemy_faction", ondelete="CASCADE"),
                        nullable=False)
    kind = Column(String(10), nullable=False)                   # mob | npc | hostile
    ref_id = Column(BigInteger, nullable=False, default=0, server_default="0")
    points = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("faction_id", "kind", "ref_id", name="uq_faction_enemy"),
    )


class FactionPvpKill(Base):
    """24 h per-opponent rule for PvP kill points."""

    __tablename__ = "faction_pvp_kills"

    character_id = Column(Integer, ForeignKey("characters.id", name="fk_faction_pvp_character", ondelete="CASCADE"),
                          primary_key=True, autoincrement=False)
    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_pvp_faction", ondelete="CASCADE"),
                        primary_key=True, autoincrement=False, index=True)
    victim_id = Column(Integer, ForeignKey("characters.id", name="fk_faction_pvp_victim", ondelete="CASCADE"),
                       primary_key=True, autoincrement=False, index=True)
    last_at = Column(DateTime, nullable=False)


class FactionOutlawRegion(Base):
    __tablename__ = "faction_outlaw_regions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_outlaw_faction", ondelete="CASCADE"),
                        nullable=False)
    region_id = Column(BigInteger, nullable=False, index=True)  # Regions.id (validated, no FK)
    level_code = Column(String(16), nullable=False)             # law level code

    __table_args__ = (
        UniqueConstraint("faction_id", "region_id", name="uq_faction_outlaw_region"),
    )


class FactionItemStock(Base):
    """Donated items waiting for the tick sale on the HQ region market."""

    __tablename__ = "faction_item_stock"

    faction_id = Column(Integer, ForeignKey("factions.id", name="fk_faction_item_stock_faction", ondelete="CASCADE"),
                        primary_key=True, autoincrement=False)
    item_id = Column(Integer, primary_key=True, autoincrement=False)     # items.id (no FK)
    quantity = Column(Integer, nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime, nullable=False)


# Balance guard: a persistent Character.currency_balance changed through the ORM is a bypass of the
# ledger and raises EconomyError at flush. Strict since FEAT-181 B2 (no ORM writer is left; every
# change goes through econ_ledger.post_operation). Fixtures/repair scripts that must seed a balance
# directly wrap the write in econ_ledger.allow_direct_balance_write(session).
BALANCE_GUARD_STRICT = True
econ_ledger.install_balance_guard(Character, "currency_balance", strict=BALANCE_GUARD_STRICT)
