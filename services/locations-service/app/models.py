from sqlalchemy import Column, Integer, String, ForeignKey, Text, Boolean, Enum, BigInteger, TIMESTAMP, func, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# Модель для Countries
class Country(Base):
    __tablename__ = 'Countries'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    leader_id = Column(BigInteger, nullable=True)  # ID лидера страны (персонажа)
    map_image_url = Column(String(255), nullable=True)  # Изображение карты страны
    map_points = Column(JSON, nullable=True)  # Точки на карте (JSON)

    regions = relationship("Region", back_populates="country")



# Модель для Regions
class Region(Base):
    __tablename__ = 'Regions'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    country_id = Column(BigInteger, ForeignKey('Countries.id', ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    image_url = Column(String(255), nullable=False)
    entrance_location_id = Column(BigInteger, ForeignKey('Locations.id', ondelete="SET NULL"))
    leader_id = Column(BigInteger, nullable=True)
    map_image_url = Column(String(255), nullable=True)
    map_points = Column(JSON, nullable=True)

    country = relationship("Country", back_populates="regions")
    districts = relationship("District", back_populates="region")


# Модель для Districts
class District(Base):
    __tablename__ = 'Districts'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    region_id = Column(BigInteger, ForeignKey('Regions.id', ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    image_url = Column(String(255), nullable=False)
    entry_location = Column(BigInteger, ForeignKey('Locations.id', ondelete="SET NULL"))

    region = relationship("Region", back_populates="districts")
    locations = relationship(
        "Location",
        back_populates="district",
        foreign_keys="[Location.district_id]"  # Указываем, какой внешний ключ использовать
    )
    entry_location_detail = relationship(
        "Location",
        foreign_keys="[District.entry_location]"  # Указываем, что использовать entry_location
    )


# Модель для Locations
class Location(Base):
    __tablename__ = 'Locations'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    district_id = Column(BigInteger, ForeignKey('Districts.id', ondelete="CASCADE"), nullable=False)
    type = Column(Enum('location', 'subdistrict', name='location_type'), nullable=False)
    image_url = Column(String(255), nullable=False)
    recommended_level = Column(Integer, nullable=False)
    quick_travel_marker = Column(Boolean, nullable=False)
    parent_id = Column(BigInteger, ForeignKey('Locations.id', ondelete="CASCADE"))
    description = Column(String(255), nullable=False)

    district = relationship(
        "District",
        back_populates="locations",
        foreign_keys="[Location.district_id]"
    )
    parent = relationship("Location", remote_side=[id], backref="children")
    posts = relationship("Post", back_populates="location", cascade="all, delete-orphan")


# Модель для LocationsPath
class LocationPath(Base):
    __tablename__ = 'LocationsPath'

    ancestor_id = Column(BigInteger, ForeignKey('Locations.id', ondelete="CASCADE"), primary_key=True)
    descendant_id = Column(BigInteger, ForeignKey('Locations.id', ondelete="CASCADE"), primary_key=True)
    depth = Column(Integer, nullable=False)

    ancestor = relationship("Location", foreign_keys=[ancestor_id], backref="descendant_paths")
    descendant = relationship("Location", foreign_keys=[descendant_id], backref="ancestor_paths")

class LocationNeighbor(Base):
    __tablename__ = "LocationNeighbors"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    location_id = Column(BigInteger, ForeignKey("Locations.id", ondelete="CASCADE"), nullable=False)
    neighbor_id = Column(BigInteger, ForeignKey("Locations.id", ondelete="CASCADE"), nullable=False)
    energy_cost = Column(Integer, nullable=False)

    location = relationship("Location", foreign_keys=[location_id], backref="neighbors")
    neighbor = relationship("Location", foreign_keys=[neighbor_id])


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, nullable=False)  # ID персонажа из character-service
    location_id = Column(BigInteger, ForeignKey("Locations.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)  # Содержимое поста
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    location = relationship("Location", back_populates="posts")