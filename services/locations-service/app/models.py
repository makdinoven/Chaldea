# models.py

from sqlalchemy import (
    Column, Integer, String, ForeignKey, Text, Boolean, Enum, BigInteger, TIMESTAMP,
    func, Float, JSON, text, UniqueConstraint
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


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, nullable=False)
    location_id = Column(BigInteger, ForeignKey("Locations.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)


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


class GameTimeConfig(Base):
    __tablename__ = 'game_time_config'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    epoch = Column(TIMESTAMP, nullable=False, server_default=text("'2026-03-19 00:00:00'"))
    offset_days = Column(Integer, nullable=False, server_default=text("0"))
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)
