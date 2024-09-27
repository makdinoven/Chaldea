from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base  # Предполагается, что вы используете базовый класс из базы данных

class Country(Base):
    __tablename__ = 'countries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)

    regions = relationship("Region", back_populates="country", cascade="all, delete")

class Region(Base):
    __tablename__ = 'regions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    country_id = Column(Integer, ForeignKey('countries.id'), nullable=False)
    description = Column(Text)
    image_url = Column(String(255))

    country = relationship("Country", back_populates="regions")
    districts = relationship("District", back_populates="region", cascade="all, delete")

class District(Base):
    __tablename__ = 'districts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    region_id = Column(Integer, ForeignKey('regions.id'), nullable=False)
    description = Column(Text)
    image_url = Column(String(255))

    region = relationship("Region", back_populates="districts")
    locations = relationship("Location", back_populates="district", cascade="all, delete")

class Location(Base):
    __tablename__ = 'locations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    district_id = Column(Integer, ForeignKey('districts.id'), nullable=False)
    is_district = Column(Boolean, default=False)  # Локация также может быть районом
    description = Column(Text)
    image_url = Column(String(255))
    recommended_level = Column(Integer)
    quick_travel_marker = Column(Boolean, default=False)

    district = relationship("District", back_populates="locations")
    characters = relationship("LocationCharacter", back_populates="location", cascade="all, delete")
    mobs = relationship("LocationMob", back_populates="location", cascade="all, delete")
    neighbors = relationship("LocationNeighbor", back_populates="location", cascade="all, delete")
    activities = relationship("LocationActivity", back_populates="location", cascade="all, delete")
    logs = relationship("LocationLog", back_populates="location", cascade="all, delete")

class LocationCharacter(Base):
    __tablename__ = 'location_characters'

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey('locations.id'), nullable=False)
    character_id = Column(Integer, nullable=False)

class LocationMob(Base):
    __tablename__ = 'location_mobs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey('locations.id'), nullable=False)
    mob_id = Column(Integer, nullable=False)

class LocationNeighbor(Base):
    __tablename__ = 'location_neighbors'

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey('locations.id'), nullable=False)
    neighbor_id = Column(Integer, ForeignKey('locations.id'), nullable=False)
    energy_cost = Column(Integer, nullable=False)

class LocationActivity(Base):
    __tablename__ = 'location_activities'

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey('locations.id'), nullable=False)
    activity_description = Column(Text)
    
class LocationLog(Base):
    __tablename__ = 'location_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey('locations.id'), nullable=False)
    log_entry = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())