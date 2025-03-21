from pydantic import BaseModel
from typing import Optional, List, Literal
from datetime import datetime


# -------------------------------
#   COUNTRY SCHEMAS
# -------------------------------
class CountryBase(BaseModel):
    name: str
    description: str

class CountryCreate(CountryBase):
    leader_id: Optional[int] = None
    map_image_url: Optional[str] = None

class CountryUpdate(BaseModel):
    name: Optional[str]
    description: Optional[str]
    leader_id: Optional[int]
    map_image_url: Optional[str]

class CountryRead(BaseModel):
    id: int
    name: str
    description: str
    leader_id: Optional[int] = None
    map_image_url: Optional[str] = None

    class Config:
        orm_mode = True

class CountryLookup(BaseModel):
    id: int
    name: str

# -------------------------------
#   LOCATION SCHEMAS
# -------------------------------
class LocationBase(BaseModel):
    name: str
    district_id: int
    type: Literal["location", "subdistrict"]
    image_url: str
    recommended_level: int
    quick_travel_marker: bool
    description: str

class LocationCreate(BaseModel):
    name: str
    district_id: int
    parent_id: Optional[int] = None
    description: Optional[str] = ""
    image_url: Optional[str] = ""
    recommended_level: Optional[int] = 1
    quick_travel_marker: Optional[bool] = False

class LocationUpdate(BaseModel):
    name: Optional[str] = None
    district_id: Optional[int] = None
    type: Optional[Literal["location", "subdistrict"]] = None
    image_url: Optional[str] = ""
    recommended_level: Optional[int] = 1
    quick_travel_marker: Optional[bool] = False
    description: Optional[str] = ""
    parent_id: Optional[int] = None

class LocationRead(BaseModel):
    id: int
    name: str
    type: str
    description: str
    recommended_level: int
    quick_travel_marker: bool
    image_url: Optional[str] = None
    parent_id: Optional[int] = None

    class Config:
        orm_mode = True
# -------------------------------
#   DISTRICT SCHEMAS
# -------------------------------
class DistrictBase(BaseModel):
    name: str
    description: str
    region_id: int
    recommended_level: Optional[int] = 1
    x: Optional[float] = None
    y: Optional[float] = None
    image_url: Optional[str] = None

class DistrictCreate(DistrictBase):
    entrance_location_id: Optional[int] = None

class DistrictUpdate(BaseModel):
    name: Optional[str]
    description: Optional[str]
    image_url: Optional[str]
    recommended_level: Optional[int]
    entrance_location_id: Optional[int]
    x: Optional[float]
    y: Optional[float]

class DistrictRead(BaseModel):
    id: int
    name: str
    description: str
    region_id: int
    entrance_location_id: Optional[int] = None
    recommended_level: Optional[int] = 1
    x: Optional[float] = None
    y: Optional[float] = None
    image_url: Optional[str] = None
    locations: List[LocationRead] = []

    class Config:
        orm_mode = True

# -------------------------------
#   REGION SCHEMAS
# -------------------------------
class RegionBase(BaseModel):
    country_id: int
    name: str
    description: str
    map_image_url: str
    image_url: str
    entrance_location_id: Optional[int] = None
    leader_id: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None

class RegionCreate(BaseModel):
    name: str
    description: str
    country_id: int
    entrance_location_id: Optional[int] = None
    leader_id: Optional[int] = None
    x: Optional[int] = 0
    y: Optional[int] = 0
    map_image_url: Optional[str] = None
    image_url: Optional[str] = None

class RegionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    country_id: Optional[int] = None
    entrance_location_id: Optional[int] = None
    leader_id: Optional[int] = None
    x: Optional[int] = None
    y: Optional[int] = None
    map_image_url: Optional[str] = None
    image_url: Optional[str] = None

class RegionUpdateResponse(BaseModel):
    id: int
    country_id: int
    name: str
    description: str
    map_image_url: Optional[str] = None
    image_url: Optional[str] = None
    entrance_location_id: Optional[int] = None
    leader_id: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None

    class Config:
        orm_mode = True

class RegionRead(BaseModel):
    id: int
    name: str
    description: str
    country_id: int
    entrance_location_id: Optional[int] = None
    leader_id: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None
    map_image_url: Optional[str] = None
    image_url: Optional[str] = None
    districts: List[DistrictRead] = []

    class Config:
        orm_mode = True




# -------------------------------
#   NEIGHBOR / POST SCHEMAS
# -------------------------------
class LocationNeighborCreate(BaseModel):
    neighbor_id: int
    energy_cost: int = 1

class LocationNeighbor(BaseModel):
    id: int
    location_id: int
    neighbor_id: int
    energy_cost: int

    class Config:
        orm_mode = True


class PostCreate(BaseModel):
    character_id: int
    location_id: int
    content: str

class PostResponse(BaseModel):
    id: int
    character_id: int
    location_id: int
    content: str
    created_at: datetime

    class Config:
        orm_mode = True


# -------------------------------
#   LOOKUP SCHEMAS
# -------------------------------
class LocationLookup(BaseModel):
    id: int
    name: str

class DistrictLookup(BaseModel):
    id: int
    name: str


# -------------------------------
#   Forward references
# -------------------------------
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    DistrictRead.update_forward_refs()
    RegionRead.update_forward_refs()
    LocationRead.update_forward_refs()
else:
    DistrictRead.update_forward_refs()
    RegionRead.update_forward_refs()
    LocationRead.update_forward_refs()

# Добавляем схему для ответа при создании региона
class RegionCreateResponse(BaseModel):
    id: int
    name: str
    description: str
    country_id: int
    entrance_location_id: Optional[int] = None
    leader_id: Optional[int] = None
    x: Optional[int] = None
    y: Optional[int] = None
    map_image_url: Optional[str] = None
    image_url: Optional[str] = None

    class Config:
        orm_mode = True

class AdminPanelData(BaseModel):
    countries: List[CountryRead]
    regions: List[RegionRead]

    class Config:
        orm_mode = True

class LocationNeighborResponse(BaseModel):
    neighbor_id: int
    energy_cost: int
    
    class Config:
        orm_mode = True

class LocationNeighborsUpdate(BaseModel):
    neighbors: List[LocationNeighborCreate]
