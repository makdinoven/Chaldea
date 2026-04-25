# models.py

from sqlalchemy import (
    Column, Integer, String, ForeignKey, Text, Boolean, Enum, BigInteger, TIMESTAMP,
    func, Float, JSON, text, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Area(Base):
    __tablename__ = 'Areas'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    map_image_url = Column(String(255), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)

    countries = relationship("Country", back_populates="area")


class Country(Base):
    __tablename__ = 'Countries'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    leader_id = Column(BigInteger, nullable=True)
    map_image_url = Column(String(255), nullable=True)
    emblem_url = Column(String(255), nullable=True)
    area_id = Column(BigInteger, ForeignKey('Areas.id', ondelete="SET NULL"), nullable=True)
    x = Column(Float, nullable=True)
    y = Column(Float, nullable=True)
    is_hidden = Column(Boolean, nullable=False, default=False, server_default='0')

    area = relationship("Area", back_populates="countries")
    regions = relationship("Region", back_populates="country")


class Region(Base):
    __tablename__ = 'Regions'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    country_id = Column(BigInteger, ForeignKey('Countries.id', ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    map_image_url = Column(String(255), nullable=True)
    image_url = Column(String(255), nullable=True)
    entrance_location_id = Column(BigInteger, ForeignKey('Locations.id', ondelete="SET NULL"))
    leader_id = Column(BigInteger, nullable=True)

    x = Column(Float, nullable=True)
    y = Column(Float, nullable=True)

    country = relationship("Country", back_populates="regions")
    districts = relationship("District", back_populates="region")
    standalone_locations = relationship(
        "Location",
        back_populates="region",
        foreign_keys="[Location.region_id]"
    )


class District(Base):
    __tablename__ = 'Districts'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    region_id = Column(BigInteger, ForeignKey('Regions.id', ondelete="CASCADE"), nullable=False)
    parent_district_id = Column(BigInteger, ForeignKey('Districts.id', ondelete="CASCADE"), nullable=True)
    description = Column(Text, nullable=False)
    image_url = Column(String(255), nullable=True)
    entrance_location_id = Column(BigInteger, ForeignKey('Locations.id', ondelete="SET NULL"))
    recommended_level = Column(Integer, nullable=True, default=1)
    marker_type = Column(Enum('safe', 'dangerous', 'dungeon', 'farm', name='district_marker_type'), nullable=True, default='safe')

    x = Column(Float, nullable=True)
    y = Column(Float, nullable=True)
    map_icon_url = Column(String(255), nullable=True)
    map_image_url = Column(String(255), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)

    region = relationship("Region", back_populates="districts")
    parent_district = relationship("District", remote_side=[id], back_populates="sub_districts")
    sub_districts = relationship("District", back_populates="parent_district")

    # ВАЖНО: указываем, что в таблице Locations есть district_id,
    # который связан именно с этим relationship.
    locations = relationship(
        "Location",
        back_populates="district",
        foreign_keys="[Location.district_id]"  # <-- явная привязка
    )

    entrance_location_detail = relationship(
        "Location",
        foreign_keys=[entrance_location_id]  # <-- указываем, что entrance_location ссылается на Location.id
    )


class Location(Base):
    __tablename__ = 'Locations'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    district_id = Column(BigInteger, ForeignKey('Districts.id', ondelete="CASCADE"), nullable=True)
    region_id = Column(BigInteger, ForeignKey('Regions.id', ondelete='CASCADE'), nullable=True)
    type = Column(Enum('location', 'subdistrict', name='location_type'), nullable=False)
    image_url = Column(String(255), nullable=True)
    recommended_level = Column(Integer, nullable=False)
    quick_travel_marker = Column(Boolean, nullable=False)
    parent_id = Column(BigInteger, ForeignKey('Locations.id', ondelete="CASCADE"))
    description = Column(Text, nullable=False)
    marker_type = Column(Enum('safe', 'dangerous', 'dungeon', 'farm', name='location_marker_type'), nullable=False, default='safe')
    map_icon_url = Column(String(255), nullable=True)
    map_x = Column(Float, nullable=True)
    map_y = Column(Float, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    no_quick_move = Column(Boolean, nullable=False, default=False, server_default="0")

    # ЯВНО указываем, какие колонке использовать в ForeignKey для district:
    district = relationship(
        "District",
        back_populates="locations",
        foreign_keys=[district_id]
    )

    region = relationship(
        "Region",
        back_populates="standalone_locations",
        foreign_keys=[region_id]
    )

    # для иерархии self -> children
    parent = relationship("Location", remote_side=[id], backref="children")


class LocationNeighbor(Base):
    __tablename__ = "LocationNeighbors"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    location_id = Column(BigInteger, ForeignKey("Locations.id", ondelete="CASCADE"), nullable=False)
    neighbor_id = Column(BigInteger, ForeignKey("Locations.id", ondelete="CASCADE"), nullable=False)
    energy_cost = Column(Integer, nullable=False)
    path_data = Column(JSON, nullable=True)
    is_auto_arrow = Column(Boolean, nullable=False, default=False, server_default="0")


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, nullable=False)
    location_id = Column(BigInteger, ForeignKey("Locations.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index('idx_posts_character_id', 'character_id'),
    )


class PostLike(Base):
    __tablename__ = "post_likes"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    character_id = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('post_id', 'character_id', name='uq_post_character'),
    )


class ClickableZone(Base):
    __tablename__ = 'ClickableZones'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    parent_type = Column(Enum('area', 'country', name='clickable_zone_parent_type'), nullable=False)
    parent_id = Column(BigInteger, nullable=False)
    target_type = Column(Enum('country', 'region', 'area', name='clickable_zone_target_type'), nullable=False)
    target_id = Column(BigInteger, nullable=False)
    zone_data = Column(JSON, nullable=False)
    label = Column(String(255), nullable=True)
    stroke_color = Column(String(20), nullable=True)


class GameRule(Base):
    __tablename__ = 'game_rules'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    image_url = Column(String(512), nullable=True)
    content = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)


class LocationLoot(Base):
    __tablename__ = 'location_loot'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    location_id = Column(BigInteger, ForeignKey('Locations.id', ondelete='CASCADE'), nullable=False, index=True)
    item_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    dropped_by_character_id = Column(Integer, nullable=True)
    dropped_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)


class LocationFavorite(Base):
    __tablename__ = "location_favorites"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    location_id = Column(BigInteger, ForeignKey("Locations.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'location_id', name='uq_user_location_favorite'),
    )


class PostDeletionRequest(Base):
    __tablename__ = "post_deletion_requests"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, nullable=False)
    reason = Column(String(500), nullable=True)
    status = Column(String(20), default="pending", nullable=False)
    reviewed_by_user_id = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    reviewed_at = Column(TIMESTAMP, nullable=True)


class PostReport(Base):
    __tablename__ = "post_reports"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, nullable=False)
    reason = Column(String(500), nullable=True)
    status = Column(String(20), default="pending", nullable=False)
    reviewed_by_user_id = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    reviewed_at = Column(TIMESTAMP, nullable=True)

    __table_args__ = (
        UniqueConstraint('post_id', 'user_id', name='uq_post_report_user'),
    )


class GameTimeConfig(Base):
    __tablename__ = 'game_time_config'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    epoch = Column(TIMESTAMP, nullable=False, server_default=text("'2026-03-19 00:00:00'"))
    offset_days = Column(Integer, nullable=False, server_default=text("0"))
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)


class DialogueTree(Base):
    __tablename__ = 'dialogue_trees'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    npc_id = Column(Integer, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    nodes = relationship("DialogueNode", back_populates="tree", cascade="all, delete-orphan")


class DialogueNode(Base):
    __tablename__ = 'dialogue_nodes'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tree_id = Column(BigInteger, ForeignKey('dialogue_trees.id', ondelete='CASCADE'), nullable=False, index=True)
    npc_text = Column(Text, nullable=False)
    is_root = Column(Boolean, nullable=False, default=False, server_default=text("0"))
    sort_order = Column(Integer, nullable=False, default=0)
    action_type = Column(String(50), nullable=True)
    action_data = Column(JSON, nullable=True)

    tree = relationship("DialogueTree", back_populates="nodes")
    options = relationship("DialogueOption", back_populates="node",
                           foreign_keys="[DialogueOption.node_id]",
                           cascade="all, delete-orphan")


class NpcShopItem(Base):
    __tablename__ = 'npc_shop_items'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    npc_id = Column(Integer, nullable=False, index=True)
    item_id = Column(Integer, nullable=False)
    buy_price = Column(Integer, nullable=False)
    sell_price = Column(Integer, nullable=False, default=0)
    stock = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)


class Quest(Base):
    __tablename__ = 'quests'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    npc_id = Column(Integer, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    quest_type = Column(String(50), nullable=False, default='standard', server_default=text("'standard'"))
    min_level = Column(Integer, nullable=False, default=1, server_default=text("1"))
    reward_currency = Column(Integer, nullable=False, default=0, server_default=text("0"))
    reward_exp = Column(Integer, nullable=False, default=0, server_default=text("0"))
    reward_items = Column(JSON, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    objectives = relationship("QuestObjective", back_populates="quest", cascade="all, delete-orphan")


class QuestObjective(Base):
    __tablename__ = 'quest_objectives'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    quest_id = Column(BigInteger, ForeignKey('quests.id', ondelete='CASCADE'), nullable=False, index=True)
    description = Column(String(500), nullable=False)
    objective_type = Column(String(50), nullable=False)
    target_id = Column(Integer, nullable=True)
    target_count = Column(Integer, nullable=False, default=1, server_default=text("1"))
    sort_order = Column(Integer, nullable=False, default=0, server_default=text("0"))

    quest = relationship("Quest", back_populates="objectives")


class CharacterQuest(Base):
    __tablename__ = 'character_quests'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False, index=True)
    quest_id = Column(BigInteger, ForeignKey('quests.id', ondelete='CASCADE'), nullable=False)
    status = Column(String(20), nullable=False, default='active', server_default=text("'active'"))
    accepted_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    completed_at = Column(TIMESTAMP, nullable=True)

    quest = relationship("Quest")
    progress = relationship("CharacterQuestProgress", back_populates="character_quest", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('character_id', 'quest_id', name='uq_character_quest'),
    )


class CharacterQuestProgress(Base):
    __tablename__ = 'character_quest_progress'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    character_quest_id = Column(BigInteger, ForeignKey('character_quests.id', ondelete='CASCADE'), nullable=False, index=True)
    objective_id = Column(BigInteger, ForeignKey('quest_objectives.id', ondelete='CASCADE'), nullable=False)
    current_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    is_completed = Column(Boolean, nullable=False, default=False, server_default=text("0"))

    character_quest = relationship("CharacterQuest", back_populates="progress")
    objective = relationship("QuestObjective")


class DialogueOption(Base):
    __tablename__ = 'dialogue_options'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    node_id = Column(BigInteger, ForeignKey('dialogue_nodes.id', ondelete='CASCADE'), nullable=False, index=True)
    text = Column(String(500), nullable=False)
    next_node_id = Column(BigInteger, ForeignKey('dialogue_nodes.id', ondelete='SET NULL'), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    condition = Column(JSON, nullable=True)

    node = relationship("DialogueNode", back_populates="options", foreign_keys=[node_id])
    next_node = relationship("DialogueNode", foreign_keys=[next_node_id])


class ArchiveCategory(Base):
    __tablename__ = 'archive_categories'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    articles = relationship(
        "ArchiveArticle",
        secondary="archive_article_categories",
        back_populates="categories"
    )


class ArchiveArticle(Base):
    __tablename__ = 'archive_articles'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    slug = Column(String(255), nullable=False, unique=True)
    content = Column(Text, nullable=True)
    summary = Column(String(500), nullable=True)
    cover_image_url = Column(String(512), nullable=True)
    cover_text_color = Column(String(20), nullable=True, default="#FFFFFF", server_default="'#FFFFFF'")
    is_featured = Column(Boolean, nullable=False, default=False)
    featured_sort_order = Column(Integer, nullable=False, default=0)
    created_by_user_id = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    categories = relationship(
        "ArchiveCategory",
        secondary="archive_article_categories",
        back_populates="articles"
    )


class RegionTransitionArrow(Base):
    __tablename__ = 'region_transition_arrows'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    region_id = Column(BigInteger, ForeignKey('Regions.id', ondelete='CASCADE'), nullable=False, index=True)
    target_region_id = Column(BigInteger, ForeignKey('Regions.id', ondelete='CASCADE'), nullable=False, index=True)
    paired_arrow_id = Column(BigInteger, ForeignKey('region_transition_arrows.id', ondelete='SET NULL'), nullable=True)
    x = Column(Float, nullable=True)
    y = Column(Float, nullable=True)
    label = Column(String(255), nullable=True)
    rotation = Column(Float, nullable=True, server_default="0")


class ArrowNeighbor(Base):
    __tablename__ = 'arrow_neighbors'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    location_id = Column(BigInteger, ForeignKey('Locations.id', ondelete='CASCADE'), nullable=False, index=True)
    arrow_id = Column(BigInteger, ForeignKey('region_transition_arrows.id', ondelete='CASCADE'), nullable=False, index=True)
    energy_cost = Column(Integer, nullable=False, default=0)
    path_data = Column(JSON, nullable=True)


class FloatingStructure(Base):
    __tablename__ = 'floating_structures'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    icon_url = Column(String(500), nullable=True)
    route_json = Column(JSON, nullable=False)
    speed = Column(Float, nullable=False, server_default=text("0"))
    started_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    internal_district_id = Column(
        BigInteger,
        ForeignKey('Districts.id', ondelete='SET NULL'),
        nullable=True,
    )
    area_id = Column(
        BigInteger,
        ForeignKey('Areas.id', ondelete='SET NULL'),
        nullable=True,
    )
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ArchiveArticleCategory(Base):
    __tablename__ = 'archive_article_categories'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    article_id = Column(BigInteger, ForeignKey('archive_articles.id', ondelete='CASCADE'), nullable=False)
    category_id = Column(BigInteger, ForeignKey('archive_categories.id', ondelete='CASCADE'), nullable=False)

    __table_args__ = (
        UniqueConstraint('article_id', 'category_id', name='uq_article_category'),
    )


class GatheringNode(Base):
    """Admin-configured ore/herb/wood gathering node attached to a Location.

    Cross-service note: ``result_item_id`` references the items table owned by
    inventory-service. Per the codebase convention (see LocationLoot.item_id,
    npc_shop_items.item_id) cross-service references are plain Integer columns
    with NO ForeignKey declared.
    """

    __tablename__ = 'gathering_nodes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(
        BigInteger,
        ForeignKey('Locations.id', ondelete='CASCADE'),
        nullable=False,
    )
    node_name = Column(String(120), nullable=False)
    category = Column(
        Enum('ore', 'herb', 'wood', name='gathering_node_category'),
        nullable=False,
    )
    # Cross-service: inventory-service owns the items table — no FK.
    result_item_id = Column(Integer, nullable=False)
    result_quantity_per_gather = Column(Integer, nullable=False, default=1, server_default=text('1'))
    stamina_per_gather = Column(Integer, nullable=False)
    daily_bank_max = Column(Integer, nullable=False)
    current_bank = Column(Integer, nullable=False)
    allow_concurrent_gather = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text('0'),
    )
    depleted_at = Column(TIMESTAMP, nullable=True)
    restore_at = Column(TIMESTAMP, nullable=True)
    is_enabled = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text('1'),
    )
    created_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text('CURRENT_TIMESTAMP'),
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text('CURRENT_TIMESTAMP'),
        onupdate=func.now(),
    )

    location = relationship('Location', foreign_keys=[location_id])
    sessions = relationship(
        'GatheringSession',
        back_populates='node',
        cascade='all, delete-orphan',
    )

    __table_args__ = (
        Index('ix_gathering_nodes_location', 'location_id'),
        Index('ix_gathering_nodes_category', 'category'),
        Index('ix_gathering_nodes_restore_at', 'restore_at'),
        {'mysql_engine': 'InnoDB'},
    )


class GatheringSession(Base):
    """Per-character gathering session on a gathering_node.

    ``effective_*`` fields are snapshots taken at session start so that admin
    edits to the node mid-session do not affect the in-flight calculation.

    Cross-service columns (``character_id``, ``tool_inventory_item_id``) have
    NO ForeignKey declared — characters and inventory items are owned by other
    services. ``tool_inventory_item_id`` is null when the player chose to
    gather without a tool.
    """

    __tablename__ = 'gathering_sessions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(
        Integer,
        ForeignKey('gathering_nodes.id', ondelete='CASCADE'),
        nullable=False,
    )
    # Cross-service: character-service owns characters — no FK.
    character_id = Column(Integer, nullable=False)
    # Cross-service: inventory-service owns inventory items — no FK.
    # null = "without tool"
    tool_inventory_item_id = Column(Integer, nullable=True)
    started_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text('CURRENT_TIMESTAMP'),
    )
    complete_at = Column(TIMESTAMP, nullable=False)
    effective_speed_bonus_pct = Column(Float, nullable=False, default=0, server_default=text('0'))
    effective_double_chance_pct = Column(Float, nullable=False, default=0, server_default=text('0'))
    effective_stamina_bonus_pct = Column(Float, nullable=False, default=0, server_default=text('0'))
    stamina_paid = Column(Integer, nullable=False)
    status = Column(
        Enum(
            'active',
            'completed',
            'cancelled',
            'interrupted_by_battle',
            'inventory_full',
            name='gathering_session_status',
        ),
        nullable=False,
        default='active',
        server_default=text("'active'"),
    )
    finished_at = Column(TIMESTAMP, nullable=True)
    result_quantity = Column(Integer, nullable=True)
    xp_awarded = Column(Integer, nullable=True)

    node = relationship('GatheringNode', back_populates='sessions')

    __table_args__ = (
        Index('ix_gathering_sessions_character', 'character_id'),
        Index('ix_gathering_sessions_node', 'node_id'),
        Index('ix_gathering_sessions_status', 'status'),
        Index('ix_gathering_sessions_complete_at', 'complete_at'),
        {'mysql_engine': 'InnoDB'},
    )
