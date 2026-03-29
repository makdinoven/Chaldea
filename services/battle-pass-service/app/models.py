from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class BpSeason(Base):
    __tablename__ = "bp_seasons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    segment_name = Column(String(50), nullable=False)
    year = Column(Integer, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    grace_end_date = Column(DateTime, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("segment_name", "year", name="uq_segment_year"),
    )

    levels = relationship("BpLevel", back_populates="season", cascade="all, delete-orphan")
    missions = relationship("BpMission", back_populates="season", cascade="all, delete-orphan")


class BpLevel(Base):
    __tablename__ = "bp_levels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_id = Column(Integer, ForeignKey("bp_seasons.id", ondelete="CASCADE"), nullable=False)
    level_number = Column(Integer, nullable=False)
    required_xp = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("season_id", "level_number", name="uq_season_level"),
    )

    season = relationship("BpSeason", back_populates="levels")
    rewards = relationship("BpReward", back_populates="level", cascade="all, delete-orphan")


class BpReward(Base):
    __tablename__ = "bp_rewards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    level_id = Column(Integer, ForeignKey("bp_levels.id", ondelete="CASCADE"), nullable=False)
    track = Column(String(10), nullable=False)  # "free" or "premium"
    reward_type = Column(String(20), nullable=False)  # gold, xp, item, diamonds, frame, chat_background
    reward_value = Column(Integer, nullable=False)
    item_id = Column(Integer, nullable=True)
    cosmetic_slug = Column(String(50), nullable=True)

    level = relationship("BpLevel", back_populates="rewards")


class BpMission(Base):
    __tablename__ = "bp_missions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    season_id = Column(Integer, ForeignKey("bp_seasons.id", ondelete="CASCADE"), nullable=False)
    week_number = Column(Integer, nullable=False)
    mission_type = Column(String(50), nullable=False)
    description = Column(String(500), nullable=False)
    target_count = Column(Integer, nullable=False)
    xp_reward = Column(Integer, nullable=False)

    __table_args__ = (
        Index("idx_season_week", "season_id", "week_number"),
    )

    season = relationship("BpSeason", back_populates="missions")


class BpUserProgress(Base):
    __tablename__ = "bp_user_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    season_id = Column(Integer, ForeignKey("bp_seasons.id", ondelete="CASCADE"), nullable=False)
    current_level = Column(Integer, nullable=False, default=0)
    current_xp = Column(Integer, nullable=False, default=0)
    is_premium = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "season_id", name="uq_user_season"),
        Index("idx_user_id", "user_id"),
    )


class BpUserReward(Base):
    __tablename__ = "bp_user_rewards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    season_id = Column(Integer, ForeignKey("bp_seasons.id", ondelete="CASCADE"), nullable=False)
    level_id = Column(Integer, ForeignKey("bp_levels.id", ondelete="CASCADE"), nullable=False)
    track = Column(String(10), nullable=False)
    claimed_at = Column(DateTime, nullable=False, server_default=func.now())
    delivered_to_character_id = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "level_id", "track", name="uq_user_level_track"),
        Index("idx_user_season_rewards", "user_id", "season_id"),
    )


class BpUserMissionProgress(Base):
    __tablename__ = "bp_user_mission_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    mission_id = Column(Integer, ForeignKey("bp_missions.id", ondelete="CASCADE"), nullable=False)
    current_count = Column(Integer, nullable=False, default=0)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "mission_id", name="uq_user_mission"),
        Index("idx_user_mission_user_id", "user_id"),
    )


class BpLocationVisit(Base):
    __tablename__ = "bp_location_visits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    season_id = Column(Integer, ForeignKey("bp_seasons.id", ondelete="CASCADE"), nullable=False)
    location_id = Column(Integer, nullable=False)
    character_id = Column(Integer, nullable=False)
    visited_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "season_id", "location_id", name="uq_user_season_location"),
        Index("idx_user_season_visits", "user_id", "season_id"),
    )


class BpUserSnapshot(Base):
    __tablename__ = "bp_user_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    season_id = Column(Integer, ForeignKey("bp_seasons.id", ondelete="CASCADE"), nullable=False)
    character_id = Column(Integer, nullable=False)
    snapshot_type = Column(String(50), nullable=False)  # "pve_kills", "level"
    value_at_enrollment = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "user_id", "season_id", "character_id", "snapshot_type",
            name="uq_user_season_char_type",
        ),
    )
