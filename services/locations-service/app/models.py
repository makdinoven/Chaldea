# models.py

from sqlalchemy import (
    Column, Integer, String, ForeignKey, Text, Boolean, Enum, BigInteger, TIMESTAMP,
    func, Float
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Country(Base):
    __tablename__ = 'Countries'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    leader_id = Column(BigInteger, nullable=True)
    map_image_url = Column(String(255), nullable=True)

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


class District(Base):
    __tablename__ = 'Districts'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    region_id = Column(BigInteger, ForeignKey('Regions.id', ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    image_url = Column(String(255), nullable=True)
    entry_location = Column(BigInteger, ForeignKey('Locations.id', ondelete="SET NULL"))
    recommended_level = Column(Integer, nullable=True, default=1)

    x = Column(Float, nullable=True)
    y = Column(Float, nullable=True)

    region = relationship("Region", back_populates="districts")

    # ВАЖНО: указываем, что в таблице Locations есть district_id,
    # который связан именно с этим relationship.
    locations = relationship(
        "Location",
        back_populates="district",
        foreign_keys="[Location.district_id]"  # <-- явная привязка
    )

    entry_location_detail = relationship(
        "Location",
        foreign_keys=[entry_location]  # <-- указываем, что entry_location ссылается на Location.id
    )


class Location(Base):
    __tablename__ = 'Locations'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    district_id = Column(BigInteger, ForeignKey('Districts.id', ondelete="CASCADE"), nullable=False)
    type = Column(Enum('location', 'subdistrict', name='location_type'), nullable=False)
    image_url = Column(String(255), nullable=True)
    recommended_level = Column(Integer, nullable=False)
    quick_travel_marker = Column(Boolean, nullable=False)
    parent_id = Column(BigInteger, ForeignKey('Locations.id', ondelete="CASCADE"))
    description = Column(String(255), nullable=False)

    # ЯВНО указываем, какие колонке использовать в ForeignKey для district:
    district = relationship(
        "District",
        back_populates="locations",
        foreign_keys=[district_id]
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
