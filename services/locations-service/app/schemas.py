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

class RegionCreate(RegionBase):
    pass

class RegionUpdate(BaseModel):
    country_id: Optional[int]
    name: Optional[str]
    description: Optional[str]
    map_image_url: Optional[str]
    image_url: Optional[str]
    entrance_location_id: Optional[int]
    leader_id: Optional[int]
    x: Optional[float]
    y: Optional[float]

class RegionRead(BaseModel):
    id: int
    country_id: int
    name: str
    description: str
    map_image_url: str
    image_url: str
    entrance_location_id: Optional[int] = None
    leader_id: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None

    districts: List["DistrictRead"] = []

    class Config:
        orm_mode = True


# -------------------------------
#   DISTRICT SCHEMAS
# -------------------------------
class DistrictBase(BaseModel):
    name: str
    description: str
    image_url: str
    region_id: int
    recommended_level: Optional[int] = 1
    x: Optional[float] = None
    y: Optional[float] = None

class DistrictCreate(DistrictBase):
    entry_location: Optional[int] = None

class DistrictUpdate(BaseModel):
    name: Optional[str]
    description: Optional[str]
    image_url: Optional[str]
    recommended_level: Optional[int]
    entry_location: Optional[int]
    x: Optional[float]
    y: Optional[float]

class DistrictRead(BaseModel):
    id: int
    name: str
    description: str
    image_url: str
    recommended_level: Optional[int]
    entry_location: Optional[int]
    region_id: int
    x: Optional[float]
    y: Optional[float]

    locations: List["LocationRead"] = []

    class Config:
        orm_mode = True


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

class LocationCreate(LocationBase):
    parent_id: Optional[int] = None

class LocationUpdate(BaseModel):
    name: Optional[str]
    district_id: Optional[int]
    type: Optional[Literal["location", "subdistrict"]]
    image_url: Optional[str]
    recommended_level: Optional[int]
    quick_travel_marker: Optional[bool]
    description: Optional[str]
    parent_id: Optional[int]

class LocationRead(BaseModel):
    id: int
    name: str
    district_id: int
    type: str
    image_url: str
    recommended_level: int
    quick_travel_marker: bool
    description: str
    parent_id: Optional[int] = None

    children: List["LocationRead"] = []

    class Config:
        orm_mode = True


# -------------------------------
#   NEIGHBOR / POST SCHEMAS
# -------------------------------
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
