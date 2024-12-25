from pydantic import BaseModel
from typing import Optional, List, Literal
from datetime import datetime

# Модель для чтения Country

class Country(BaseModel):
    id: int
    name: str
    description: str
    country_image_url: Optional[str]
    map_image_url: Optional[str]
    map_points: Optional[List[dict]]
    leader_id: Optional[int]

    class Config:
        orm_mode = True

class CountryBase(BaseModel):
    name: str
    description: str

class CountryCreate(CountryBase):
    pass

class Country(CountryBase):
    id: int
    regions: Optional[List["Region"]] = []  # Связанные регионы

    class Config:
        orm_mode = True


# Модель для Region
class RegionBase(BaseModel):
    id: int
    name: str
    description: str
    image_url: str
    map_image_url: Optional[str]
    map_points: Optional[List[dict]]  # Список точек карты
    entrance_location_id: Optional[int]
    ruler_id: Optional[int]
    districts: Optional[List["District"]] = []  # Районы в регионе

    class Config:
        orm_mode = True


class RegionCreate(RegionBase):
    entrance_location_id: Optional[int] = None

class Region(RegionBase):
    id: int
    districts: Optional[List["District"]] = []  # Связанные районы
    entrance_location_id: Optional[int]

    class Config:
        orm_mode = True


# Модель для District
class DistrictBase(BaseModel):
    name: str
    description: str
    image_url: str
    region_id: int

class DistrictCreate(DistrictBase):
    entry_location: Optional[int] = None

class District(DistrictBase):
    id: int
    entry_location: Optional[int]
    locations: Optional[List["Location"]] = []  # Связанные локации

    class Config:
        orm_mode = True


# Модель для Location
class LocationBase(BaseModel):
    name: str
    district_id: int
    type: Literal["location", "subdistrict"]
    image_url: str
    recommended_level: int
    quick_travel_marker: bool
    description: str

class LocationCreate(LocationBase):
    parent_id: Optional[int] = None

class Location(LocationBase):
    id: int
    parent_id: Optional[int]
    children: Optional[List["Location"]] = []  # Вложенные локации

    class Config:
        orm_mode = True


# Модель для LocationPath
class LocationPathBase(BaseModel):
    ancestor_id: int
    descendant_id: int
    depth: int

class LocationPath(LocationPathBase):
    class Config:
        orm_mode = True

class LocationNeighborCreate(BaseModel):
    neighbor_id: int
    energy_cost: int

class LocationNeighbor(BaseModel):
        id: int
        location_id: int
        neighbor_id: int
        energy_cost: int

        class Config:
            orm_mode = True

class PostResponse(BaseModel):
    id: int
    character_id: int
    location_id: int
    content: str
    created_at: datetime

    class Config:
        orm_mode = True

class PostCreate(BaseModel):
    character_id: int
    location_id: int
    content: str


# Разрешаем ссылки на другие модели
Country.update_forward_refs()
Region.update_forward_refs()
District.update_forward_refs()
Location.update_forward_refs()