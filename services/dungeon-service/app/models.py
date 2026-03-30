from sqlalchemy import (
    Column, BigInteger, Integer, String, Text, Float, Boolean,
    Enum, JSON, TIMESTAMP, ForeignKey, UniqueConstraint, Index,
    func,
)
from sqlalchemy.orm import relationship
from database import Base


class Dungeon(Base):
    __tablename__ = "dungeons"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    lore_text = Column(Text, nullable=True)
    stability_type = Column(
        Enum("static", "unstable", "chaotic", name="dungeon_stability_type"),
        nullable=False, server_default="static",
    )
    danger_level = Column(
        Enum("safe", "deadly", name="dungeon_danger_level"),
        nullable=False, server_default="safe",
    )
    location_id = Column(BigInteger, nullable=False, index=True)
    recommended_level = Column(Integer, nullable=True, default=1)
    recommended_party_size = Column(Integer, nullable=True, default=1)
    cooldown_hours = Column(Integer, nullable=False, default=24)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    # Modifiers
    mob_multiplier = Column(Float, nullable=False, default=1.0)
    loot_multiplier = Column(Float, nullable=False, default=1.0)
    stamina_multiplier = Column(Float, nullable=False, default=1.0)
    difficulty_modifier = Column(Float, nullable=False, default=1.0)
    disable_rest_rooms = Column(Boolean, nullable=False, default=False)
    disable_merchants = Column(Boolean, nullable=False, default=False)
    mana_core_chance = Column(Float, nullable=False, default=0.0)
    mana_core_item_id = Column(BigInteger, nullable=True)
    image_url = Column(String(512), nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    rooms = relationship("DungeonRoom", back_populates="dungeon", cascade="all, delete-orphan")
    corridors = relationship("DungeonCorridor", back_populates="dungeon", cascade="all, delete-orphan")
    sessions = relationship("DungeonSession", back_populates="dungeon", cascade="all, delete-orphan")
    room_visits = relationship("DungeonRoomVisit", back_populates="dungeon", cascade="all, delete-orphan")


class DungeonRoom(Base):
    __tablename__ = "dungeon_rooms"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dungeon_id = Column(BigInteger, ForeignKey("dungeons.id", ondelete="CASCADE"), nullable=False, index=True)
    room_type = Column(
        Enum(
            "battle", "boss", "treasure", "trap", "event",
            "rest", "merchant", "fork", "teleport", "deadend",
            name="dungeon_room_type",
        ),
        nullable=False, index=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    image_url = Column(String(512), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_entrance = Column(Boolean, nullable=False, default=False)
    is_boss_room = Column(Boolean, nullable=False, default=False)
    is_mana_core_room = Column(Boolean, nullable=False, default=False)
    room_config = Column(JSON, nullable=True)
    position_x = Column(Float, nullable=True, default=None)
    position_y = Column(Float, nullable=True, default=None)
    created_at = Column(TIMESTAMP, server_default=func.now())

    dungeon = relationship("Dungeon", back_populates="rooms")
    corridors_from = relationship(
        "DungeonCorridor",
        foreign_keys="DungeonCorridor.from_room_id",
        back_populates="from_room",
        cascade="all, delete-orphan",
    )
    corridors_to = relationship(
        "DungeonCorridor",
        foreign_keys="DungeonCorridor.to_room_id",
        back_populates="to_room",
        cascade="all, delete-orphan",
    )
    visits = relationship("DungeonRoomVisit", back_populates="room", cascade="all, delete-orphan")
    room_states = relationship("DungeonRoomState", back_populates="room", cascade="all, delete-orphan")


class DungeonCorridor(Base):
    __tablename__ = "dungeon_corridors"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dungeon_id = Column(BigInteger, ForeignKey("dungeons.id", ondelete="CASCADE"), nullable=False, index=True)
    from_room_id = Column(BigInteger, ForeignKey("dungeon_rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    to_room_id = Column(BigInteger, ForeignKey("dungeon_rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    stamina_cost = Column(Integer, nullable=False, default=5)
    is_bidirectional = Column(Boolean, nullable=False, default=True)

    # Corridor events
    random_battle_chance = Column(Float, nullable=False, default=0.0)
    random_battle_mob_ids = Column(JSON, nullable=True)
    trap_chance = Column(Float, nullable=False, default=0.0)
    trap_config = Column(JSON, nullable=True)
    description = Column(String(512), nullable=True)

    # Visual editor handle positions (which side of the room the corridor connects to)
    source_handle = Column(String(16), nullable=True)
    target_handle = Column(String(16), nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.now())

    dungeon = relationship("Dungeon", back_populates="corridors")
    from_room = relationship("DungeonRoom", foreign_keys=[from_room_id], back_populates="corridors_from")
    to_room = relationship("DungeonRoom", foreign_keys=[to_room_id], back_populates="corridors_to")

    __table_args__ = (
        UniqueConstraint("from_room_id", "to_room_id", name="uq_corridor"),
    )


class DungeonSession(Base):
    __tablename__ = "dungeon_sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dungeon_id = Column(BigInteger, ForeignKey("dungeons.id", ondelete="CASCADE"), nullable=False, index=True)
    leader_character_id = Column(BigInteger, nullable=False, index=True)
    status = Column(
        Enum("forming", "active", "completed", "escaped", "wiped", name="dungeon_session_status"),
        nullable=False, server_default="forming", index=True,
    )
    current_room_id = Column(BigInteger, ForeignKey("dungeon_rooms.id", ondelete="SET NULL"), nullable=True)
    started_at = Column(TIMESTAMP, nullable=True)
    finished_at = Column(TIMESTAMP, nullable=True)
    cooldown_until = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    dungeon = relationship("Dungeon", back_populates="sessions")
    current_room = relationship("DungeonRoom", foreign_keys=[current_room_id])
    members = relationship("DungeonSessionMember", back_populates="session", cascade="all, delete-orphan")
    inventory = relationship("DungeonSessionInventory", back_populates="session", cascade="all, delete-orphan")
    room_states = relationship("DungeonRoomState", back_populates="session", cascade="all, delete-orphan")


class DungeonSessionMember(Base):
    __tablename__ = "dungeon_session_members"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(BigInteger, ForeignKey("dungeon_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    character_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False)
    status = Column(
        Enum("alive", "dead", "disconnected", name="dungeon_member_status"),
        nullable=False, server_default="alive",
    )
    joined_at = Column(TIMESTAMP, server_default=func.now())

    session = relationship("DungeonSession", back_populates="members")

    __table_args__ = (
        UniqueConstraint("session_id", "character_id", name="uq_session_member"),
    )


class DungeonSessionInventory(Base):
    __tablename__ = "dungeon_session_inventory"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(BigInteger, ForeignKey("dungeon_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(BigInteger, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    source_description = Column(String(255), nullable=True)

    session = relationship("DungeonSession", back_populates="inventory")


class DungeonRoomVisit(Base):
    __tablename__ = "dungeon_room_visits"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dungeon_id = Column(BigInteger, ForeignKey("dungeons.id", ondelete="CASCADE"), nullable=False)
    character_id = Column(BigInteger, nullable=False)
    room_id = Column(BigInteger, ForeignKey("dungeon_rooms.id", ondelete="CASCADE"), nullable=False)
    first_visited_at = Column(TIMESTAMP, server_default=func.now())
    last_visited_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    visit_count = Column(Integer, nullable=False, default=1)

    dungeon = relationship("Dungeon", back_populates="room_visits")
    room = relationship("DungeonRoom", back_populates="visits")

    __table_args__ = (
        UniqueConstraint("dungeon_id", "character_id", "room_id", name="uq_visit"),
        Index("idx_visits_char_dungeon", "character_id", "dungeon_id"),
    )


class DungeonRoomState(Base):
    __tablename__ = "dungeon_room_state"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(BigInteger, ForeignKey("dungeon_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    room_id = Column(BigInteger, ForeignKey("dungeon_rooms.id", ondelete="CASCADE"), nullable=False)
    is_cleared = Column(Boolean, nullable=False, default=False)
    loot_collected = Column(Boolean, nullable=False, default=False)
    event_choice_index = Column(Integer, nullable=True)
    extra_data = Column(JSON, nullable=True)

    session = relationship("DungeonSession", back_populates="room_states")
    room = relationship("DungeonRoom", back_populates="room_states")

    __table_args__ = (
        UniqueConstraint("session_id", "room_id", name="uq_room_state"),
    )
