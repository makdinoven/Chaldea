# models.py

from sqlalchemy import (
    Column, Integer, String, ForeignKey, Text, Boolean, Enum, BigInteger, TIMESTAMP,
    func, Float, JSON, text, UniqueConstraint, Index
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT, TINYINT
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Area(Base):
    __tablename__ = 'Areas'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    map_image_url = Column(String(255), nullable=True)
    # JSON {"samples": [{x, y}], "tolerance": n}: how photo-service tells land from water
    map_land_settings = Column(Text, nullable=True)
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
    # JSON {"samples": [{x, y}], "tolerance": n}: how photo-service tells land from water
    map_land_settings = Column(Text, nullable=True)
    area_id = Column(BigInteger, ForeignKey('Areas.id', ondelete="SET NULL"), nullable=True)
    x = Column(Float, nullable=True)
    y = Column(Float, nullable=True)
    is_hidden = Column(Boolean, nullable=False, default=False, server_default='0')
    # Manual override of the recommended level range; NULL bound = computed from locations
    recommended_level_min = Column(Integer, nullable=True)
    recommended_level_max = Column(Integer, nullable=True)

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
    # Manual override of the recommended level range; NULL bound = computed from locations
    recommended_level_min = Column(Integer, nullable=True)
    recommended_level_max = Column(Integer, nullable=True)

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
    is_starting = Column(Boolean, nullable=False, default=False, server_default="0")
    starting_blurb = Column(Text, nullable=True)

    __table_args__ = (
        Index('ix_locations_is_starting', 'is_starting'),
    )

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
    # Declared intent of the post (FEAT-145): regular | combat | pvp | gathering |
    # dungeon | npc_dialogue. Non-regular posts gate the matching action.
    post_type = Column(String(20), server_default='regular', nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    # FEAT-159: the «изменено» marker. NULL until the post is edited for the
    # first time; the hour-long edit window is always measured from created_at,
    # never from edited_at, so repeated edits cannot extend it.
    edited_at = Column(TIMESTAMP, nullable=True, server_default=None)
    # Who performed the last edit (the author, or an admin). Audit trail only —
    # never sent to clients; get_post_details derives `edited_by_admin` from it.
    edited_by_user_id = Column(Integer, nullable=True, server_default=None)

    __table_args__ = (
        Index('idx_posts_character_id', 'character_id'),
    )


class ActionGate(Base):
    """A right, granted by an intent post, to perform an action on a location
    (FEAT-145). Consumed when the action fires; expired when the character leaves
    the location."""
    __tablename__ = "action_gates"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    location_id = Column(BigInteger, ForeignKey("Locations.id", ondelete="CASCADE"), nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="SET NULL"), nullable=True)
    action_type = Column(String(20), nullable=False)   # combat | pvp | gathering | dungeon | npc_dialogue
    target_ref = Column(Integer, nullable=True)        # mob/player character_id, node_id, npc_id, ...
    status = Column(String(12), server_default='open', nullable=False)  # open | consumed | expired
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    consumed_at = Column(TIMESTAMP, nullable=True)

    __table_args__ = (
        Index('idx_action_gates_lookup', 'character_id', 'location_id', 'action_type', 'status'),
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


class PostVersion(Base):
    """The text a post had BEFORE an edit (FEAT-160).

    A row stores the content the edit *destroyed*, not the content it produced.
    Storing the "after" text would lose the original at the very first edit —
    and the original wording is exactly what gets quoted and then disputed. The
    post's current text is never duplicated here; it is read live from
    ``posts.content``.

    Hence the deliberate off-by-one: ``edited_by_user_id`` and ``created_at``
    describe the edit that **replaced** ``content``, not the one that wrote it.
    ``crud.get_post_versions`` flips this once, server-side, into the shape an
    admin thinks in.

    Unlike ``post_gate_requests`` / ``post_deletion_requests`` / ``post_reports``
    (``SET NULL``, migrations 037/039), ``post_id`` is NOT NULL and cascades: a
    version is a copy of the post's content, not a staff decision about it. Once
    the post is deleted — often deleted by moderation *for* that content — an
    orphaned copy would defeat the deletion instead of documenting it.
    """
    __tablename__ = "post_versions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    post_id = Column(
        Integer,
        ForeignKey("posts.id", ondelete="CASCADE", name="fk_post_versions_post_id"),
        nullable=False,
    )
    # 1 = the oldest stored text. Assigned as MAX(version_no) + 1 under the
    # SELECT ... FOR UPDATE in crud.edit_post; the unique key is the backstop.
    version_no = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    # Who performed the edit that replaced `content` (author or admin).
    edited_by_user_id = Column(Integer, nullable=False)
    # MEANINGFUL ONLY ON version_no = 1. Set at write time to
    # (posts.edited_at IS NULL): True when this row really holds the original,
    # False when the post had already been edited before history existed and
    # the true original is unrecoverable. Ignore it on every later row.
    is_original = Column(Boolean, nullable=False, server_default=text("1"))
    # When the edit that replaced `content` happened.
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('post_id', 'version_no', name='uq_post_versions_post_version'),
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
    # Exact coastline of the zone (SVG path in the same 0..100 space as zone_data),
    # computed by photo-service from the map image. NULL = draw the rough polygon.
    precise_path = Column(Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=True)
    # JSON {"samples": [{x, y}], "tolerance": n}: this zone's own water samples,
    # overriding the map-level map_land_settings. NULL = use the map's.
    land_settings = Column(Text, nullable=True)


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
    # post_id survives post deletion as NULL (migration 037, FEAT-158 bug 4):
    # moderation decision history must outlive the post it is about.
    post_id = Column(
        Integer,
        ForeignKey("posts.id", ondelete="SET NULL", name="fk_post_deletion_requests_post_id"),
        nullable=True,
    )
    user_id = Column(Integer, nullable=False)
    reason = Column(String(500), nullable=True)
    status = Column(String(20), default="pending", nullable=False)
    reviewed_by_user_id = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    reviewed_at = Column(TIMESTAMP, nullable=True)


class PostReport(Base):
    __tablename__ = "post_reports"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # post_id survives post deletion as NULL (migration 037, FEAT-158 bug 4):
    # moderation decision history must outlive the post it is about.
    post_id = Column(
        Integer,
        ForeignKey("posts.id", ondelete="SET NULL", name="fk_post_reports_post_id"),
        nullable=True,
    )
    user_id = Column(Integer, nullable=False)
    reason = Column(String(500), nullable=True)
    status = Column(String(20), default="pending", nullable=False)
    reviewed_by_user_id = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    reviewed_at = Column(TIMESTAMP, nullable=True)

    __table_args__ = (
        UniqueConstraint('post_id', 'user_id', name='uq_post_report_user'),
    )


class PostGateRequest(Base):
    """A moderation request to grant intent gates that were added to a post
    *after* publication, during an edit (FEAT-159, Phase B).

    A retro-added gate never fires on its own: the edit writes a row here and
    nothing else. ``action_gates`` rows are created only when an admin approves
    (see the review endpoint), so a rejected request leaves no rights behind.

    Deliberately NOT folded into ``post_deletion_requests``: that table's
    approve branch deletes the post, and a "grant rights" conditional has no
    business living next to it (FEAT-159 section 3.7).
    """
    __tablename__ = "post_gate_requests"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # post_id survives post deletion as NULL — the policy of migration 037:
    # a moderation decision must outlive the post it is about.
    post_id = Column(
        Integer,
        ForeignKey("posts.id", ondelete="SET NULL", name="fk_post_gate_requests_post_id"),
        nullable=True,
    )
    character_id = Column(Integer, nullable=False)
    location_id = Column(
        BigInteger,
        ForeignKey("Locations.id", ondelete="CASCADE", name="fk_post_gate_requests_location_id"),
        nullable=False,
    )
    # The requester. Not derivable from character_id: an admin may file a
    # request while editing somebody else's post.
    user_id = Column(Integer, nullable=False)
    # [{"action_type": "...", "targets": [...]}] — the gates to grant on approval.
    gates = Column(JSON, nullable=False)
    # pending | approved | rejected | expired
    status = Column(String(20), server_default='pending', nullable=False)
    reviewed_by_user_id = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    reviewed_at = Column(TIMESTAMP, nullable=True, server_default=None)

    __table_args__ = (
        Index('idx_pgr_queue', 'status', 'created_at'),
        Index('idx_pgr_post', 'post_id'),
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
        Enum('ore', 'herb', 'wood', 'ingredient', name='gathering_node_category'),
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


class OriginCountry(Base):
    """Справочник происхождения персонажа (FEAT-154).

    Шире, чем игровые страны на карте: сюда входят и неигровые державы.
    ``archive_slug`` — мягкая ссылка на ``archive_articles.slug`` (без FK,
    статьи — контент и могут быть переименованы).

    FEAT-155: связь с игровой картой (``country_id``) и флаг ``is_playable``
    удалены — они дублировали друг друга и могли противоречить. Связь
    происхождения с миром выражается только через ``origin_starting_points``.
    """

    __tablename__ = 'origin_countries'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    skitaltsy_attitude = Column(Text, nullable=True)
    emblem_url = Column(String(255), nullable=True)
    map_image_url = Column(String(255), nullable=True)
    archive_slug = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default='1')
    sort_order = Column(Integer, nullable=False, default=0, server_default='0')

    __table_args__ = (
        UniqueConstraint('name', name='uq_origin_countries_name'),
        Index('ix_origin_countries_active_sort', 'is_active', 'sort_order'),
        {'mysql_engine': 'InnoDB'},
    )


class OriginStartingPoint(Base):
    """Рекомендованные стартовые точки происхождения (FEAT-155).

    Полноценная таблица связи, а не JSON-колонка: обе стороны (``origin_countries``
    и ``Locations``) принадлежат locations-service и лежат в одной БД, поэтому
    внешние ключи технически возможны — в отличие от ``subraces.typical_origin_ids``,
    где связь пересекала границу сервисов.

    ``ON DELETE CASCADE`` с обеих сторон закрывает правило 9 брифа: удалённая
    локация исчезает из набора сама, без «висячих» идентификаторов и без
    фильтрации на чтении.
    """

    __tablename__ = 'origin_starting_points'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    origin_id = Column(
        BigInteger,
        ForeignKey('origin_countries.id', ondelete='CASCADE'),
        nullable=False,
    )
    location_id = Column(
        BigInteger,
        ForeignKey('Locations.id', ondelete='CASCADE'),
        nullable=False,
    )
    sort_order = Column(Integer, nullable=False, default=0, server_default='0')

    __table_args__ = (
        UniqueConstraint('origin_id', 'location_id', name='uq_origin_starting_point'),
        Index('ix_origin_starting_points_origin', 'origin_id', 'sort_order'),
        Index('ix_origin_starting_points_location', 'location_id'),
        {'mysql_engine': 'InnoDB'},
    )


class PostDraft(Base):
    """Черновик ролевого поста — пара «персонаж + локация» (FEAT-156).

    ``content`` — ``MEDIUMTEXT``, а не ``TEXT``: ``TEXT`` вмещает 64 КБ, кириллица
    в ``utf8mb4`` стоит 2 байта на символ, плюс разметка TipTap. Длинный пост
    упёрся бы в потолок и молча обрезался — ровно тот баг, ради которого фича и
    делается.

    ``active`` — намеренно nullable-флаг, а не boolean. MySQL не умеет частично
    уникальные индексы, но считает ``NULL`` различными внутри UNIQUE-ключа,
    поэтому ``UNIQUE (character_id, location_id, active)`` даёт ровно один живой
    черновик на пару «персонаж + локация» и при этом не ограничивает число
    архивных строк. Это гарантия на уровне БД против гонки «две вкладки сразу».
    Код пишет только ``1`` или ``NULL``, никогда ``0``.

    FK только на ``Locations.id`` — внешних ключей в таблицы чужих сервисов в
    этом сервисе нет; очистка по персонажу делается admin-эндпоинтом (см. 3.12).
    """

    __tablename__ = "post_drafts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    character_id = Column(Integer, nullable=False)
    location_id = Column(
        BigInteger, ForeignKey("Locations.id", ondelete="CASCADE"), nullable=False
    )
    content = Column(MEDIUMTEXT, nullable=False)
    # 1 = живой черновик локации; NULL = архивная строка (вытесненная или отправленная)
    active = Column(TINYINT, nullable=True)
    # NOT NULL => этот текст стал настоящим постом («дописанный» из брифа)
    sent_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    # Проставляется явно в crud (datetime.now(timezone.utc)), без MySQL ON UPDATE —
    # чтобы порядок вытеснения был детерминированным и тестируемым.
    updated_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            'character_id', 'location_id', 'active', name='uq_post_drafts_active'
        ),
        Index('idx_post_drafts_char_updated', 'character_id', 'updated_at'),
        {'mysql_engine': 'InnoDB'},
    )

    # Производные флаги для Pydantic-схем (orm_mode читает их как обычные атрибуты).
    @property
    def is_sent(self) -> bool:
        """Текст стал настоящим постом («дописанный» из брифа)."""
        return self.sent_at is not None

    @property
    def is_active(self) -> bool:
        """Это живой черновик своей локации, а не архивная строка."""
        return self.active == 1
