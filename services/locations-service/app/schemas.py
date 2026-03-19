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
    area_id: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None

class CountryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    leader_id: Optional[int] = None
    map_image_url: Optional[str] = None
    area_id: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None

class CountryRead(BaseModel):
    id: int
    name: str
    description: str
    leader_id: Optional[int] = None
    map_image_url: Optional[str] = None
    area_id: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None

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
    marker_type: Optional[Literal["safe", "dangerous", "dungeon"]] = "safe"

class LocationCreateResponse(BaseModel):
    id: int
    name: str
    district_id: int
    parent_id: Optional[int] = None
    description: Optional[str] = ""
    image_url: Optional[str] = ""
    recommended_level: Optional[int] = 1
    quick_travel_marker: Optional[bool] = False
    marker_type: str = "safe"

class LocationUpdate(BaseModel):
    name: Optional[str] = None
    district_id: Optional[int] = None
    type: Optional[Literal["location", "subdistrict"]] = None
    image_url: Optional[str] = ""
    recommended_level: Optional[int] = 1
    quick_travel_marker: Optional[bool] = False
    description: Optional[str] = ""
    parent_id: Optional[int] = None
    marker_type: Optional[Literal["safe", "dangerous", "dungeon"]] = None

class LocationRead(BaseModel):
    id: int
    name: str
    type: str
    description: str
    recommended_level: int
    quick_travel_marker: bool
    image_url: Optional[str] = None
    parent_id: Optional[int] = None
    marker_type: str = "safe"

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
#   AREA SCHEMAS
# -------------------------------
class AreaCreate(BaseModel):
    name: str
    description: str
    sort_order: int = 0

class AreaUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None

class AreaRead(BaseModel):
    id: int
    name: str
    description: str
    map_image_url: Optional[str] = None
    sort_order: int = 0

    class Config:
        orm_mode = True

class AreaWithCountries(AreaRead):
    countries: List[CountryRead] = []

    class Config:
        orm_mode = True

class AreaLookup(BaseModel):
    id: int
    name: str


# -------------------------------
#   CLICKABLE ZONE SCHEMAS
# -------------------------------
class ZonePoint(BaseModel):
    x: float
    y: float

class ClickableZoneCreate(BaseModel):
    parent_type: Literal["area", "country"]
    parent_id: int
    target_type: Literal["country", "region"]
    target_id: int
    zone_data: List[ZonePoint]
    label: Optional[str] = None

class ClickableZoneUpdate(BaseModel):
    parent_type: Optional[Literal["area", "country"]] = None
    parent_id: Optional[int] = None
    target_type: Optional[Literal["country", "region"]] = None
    target_id: Optional[int] = None
    zone_data: Optional[List[ZonePoint]] = None
    label: Optional[str] = None

class ClickableZoneRead(BaseModel):
    id: int
    parent_type: str
    parent_id: int
    target_type: str
    target_id: int
    zone_data: list
    label: Optional[str] = None

    class Config:
        orm_mode = True


# -------------------------------
#   HIERARCHY TREE
# -------------------------------
class HierarchyNode(BaseModel):
    id: int
    name: str
    type: str
    marker_type: Optional[str] = None
    children: List['HierarchyNode'] = []


# -------------------------------
#   Forward references
# -------------------------------
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    DistrictRead.update_forward_refs()
    RegionRead.update_forward_refs()
    LocationRead.update_forward_refs()
    HierarchyNode.update_forward_refs()
else:
    DistrictRead.update_forward_refs()
    RegionRead.update_forward_refs()
    LocationRead.update_forward_refs()
    HierarchyNode.update_forward_refs()

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
    areas: List[AreaRead] = []
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

class PlayerInLocation(BaseModel):
    character_name: str
    character_title: str
    character_photo: str

class NeighborClient(BaseModel):
    neighbor_id: int
    name: str
    recommended_level: int
    image_url: Optional[str] = None
    energy_cost: int

class ClientPost(BaseModel):
    character_id: int
    character_photo: str
    character_title: str
    character_name: Optional[str]
    user_id: int
    user_nickname: str
    content: str
    length: int

class LocationClientDetails(BaseModel):
    id: int
    name: str
    type: str
    parent_id: Optional[int]
    description: str
    image_url: Optional[str]
    recommended_level: int
    quick_travel_marker: bool
    district_id: int
    neighbors: List[NeighborClient] = []
    players: List[PlayerInLocation] = []
    posts: List[ClientPost] = []

    class Config:
        orm_mode = True

class MovementPostRequest(BaseModel):
    character_id: int
    content: str


# -------------------------------
#   GAME RULE SCHEMAS
# -------------------------------
class GameRuleCreate(BaseModel):
    title: str
    content: Optional[str] = None
    sort_order: int = 0

class GameRuleUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    sort_order: Optional[int] = None

class GameRuleRead(BaseModel):
    id: int
    title: str
    image_url: Optional[str] = None
    content: Optional[str] = None
    sort_order: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class GameRuleReorderItem(BaseModel):
    id: int
    sort_order: int

class GameRuleReorder(BaseModel):
    order: List[GameRuleReorderItem]


# -------------------------------
#   GAME TIME SCHEMAS
# -------------------------------
class GameTimePublicResponse(BaseModel):
    epoch: datetime
    offset_days: int
    server_time: datetime


class ComputedGameTime(BaseModel):
    year: int
    segment_name: str
    segment_type: str
    week: Optional[int] = None
    is_transition: bool


class GameTimeAdminResponse(BaseModel):
    id: int
    epoch: datetime
    offset_days: int
    updated_at: datetime
    computed: ComputedGameTime
    server_time: datetime

    class Config:
        orm_mode = True


class GameTimeAdminUpdate(BaseModel):
    epoch: Optional[datetime] = None
    offset_days: Optional[int] = None
    target_year: Optional[int] = None
    target_segment: Optional[str] = None
    target_week: Optional[int] = None

