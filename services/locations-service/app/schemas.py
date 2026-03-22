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
    emblem_url: Optional[str] = None
    area_id: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None

class CountryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    leader_id: Optional[int] = None
    map_image_url: Optional[str] = None
    emblem_url: Optional[str] = None
    area_id: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None

class CountryRead(BaseModel):
    id: int
    name: str
    description: str
    leader_id: Optional[int] = None
    map_image_url: Optional[str] = None
    emblem_url: Optional[str] = None
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
    district_id: Optional[int] = None
    region_id: Optional[int] = None
    type: Literal["location", "subdistrict"]
    image_url: str
    recommended_level: int
    quick_travel_marker: bool
    description: str

class LocationCreate(BaseModel):
    name: str
    district_id: Optional[int] = None
    region_id: Optional[int] = None
    parent_id: Optional[int] = None
    description: Optional[str] = ""
    image_url: Optional[str] = ""
    recommended_level: Optional[int] = 1
    quick_travel_marker: Optional[bool] = False
    marker_type: Optional[Literal["safe", "dangerous", "dungeon", "farm"]] = "safe"
    map_icon_url: Optional[str] = None
    map_x: Optional[float] = None
    map_y: Optional[float] = None
    sort_order: int = 0

class LocationCreateResponse(BaseModel):
    id: int
    name: str
    district_id: Optional[int] = None
    region_id: Optional[int] = None
    parent_id: Optional[int] = None
    description: Optional[str] = ""
    image_url: Optional[str] = ""
    recommended_level: Optional[int] = 1
    quick_travel_marker: Optional[bool] = False
    marker_type: str = "safe"
    map_icon_url: Optional[str] = None
    map_x: Optional[float] = None
    map_y: Optional[float] = None

class LocationUpdate(BaseModel):
    name: Optional[str] = None
    district_id: Optional[int] = None
    region_id: Optional[int] = None
    type: Optional[Literal["location", "subdistrict"]] = None
    image_url: Optional[str] = ""
    recommended_level: Optional[int] = 1
    quick_travel_marker: Optional[bool] = False
    description: Optional[str] = ""
    parent_id: Optional[int] = None
    marker_type: Optional[Literal["safe", "dangerous", "dungeon", "farm"]] = None
    map_icon_url: Optional[str] = None
    map_x: Optional[float] = None
    map_y: Optional[float] = None

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
    map_icon_url: Optional[str] = None
    map_x: Optional[float] = None
    map_y: Optional[float] = None
    sort_order: int = 0

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
    marker_type: Optional[Literal["safe", "dangerous", "dungeon", "farm"]] = "safe"
    x: Optional[float] = None
    y: Optional[float] = None
    image_url: Optional[str] = None
    map_icon_url: Optional[str] = None
    map_image_url: Optional[str] = None

class DistrictCreate(DistrictBase):
    entrance_location_id: Optional[int] = None
    parent_district_id: Optional[int] = None
    sort_order: int = 0

class DistrictUpdate(BaseModel):
    name: Optional[str]
    description: Optional[str]
    image_url: Optional[str]
    recommended_level: Optional[int]
    marker_type: Optional[Literal["safe", "dangerous", "dungeon", "farm"]] = None
    entrance_location_id: Optional[int]
    x: Optional[float]
    y: Optional[float]
    map_icon_url: Optional[str]
    map_image_url: Optional[str] = None
    parent_district_id: Optional[int] = None

class DistrictRead(BaseModel):
    id: int
    name: str
    description: str
    region_id: int
    parent_district_id: Optional[int] = None
    entrance_location_id: Optional[int] = None
    recommended_level: Optional[int] = 1
    marker_type: Optional[str] = "safe"
    x: Optional[float] = None
    y: Optional[float] = None
    image_url: Optional[str] = None
    map_icon_url: Optional[str] = None
    map_image_url: Optional[str] = None
    sort_order: int = 0
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

class PostLikeRequest(BaseModel):
    character_id: int


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
    target_type: Literal["country", "region", "area"]
    target_id: int
    zone_data: List[ZonePoint]
    label: Optional[str] = None
    stroke_color: Optional[str] = None

class ClickableZoneUpdate(BaseModel):
    parent_type: Optional[Literal["area", "country"]] = None
    parent_id: Optional[int] = None
    target_type: Optional[Literal["country", "region", "area"]] = None
    target_id: Optional[int] = None
    zone_data: Optional[List[ZonePoint]] = None
    label: Optional[str] = None
    stroke_color: Optional[str] = None

class ClickableZoneRead(BaseModel):
    id: int
    parent_type: str
    parent_id: int
    target_type: str
    target_id: int
    zone_data: list
    label: Optional[str] = None
    stroke_color: Optional[str] = None

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
    id: int
    name: str
    avatar: Optional[str] = None
    level: int = 1
    class_name: Optional[str] = None
    race_name: Optional[str] = None
    character_title: Optional[str] = ""
    user_id: Optional[int] = None


class NpcInLocation(BaseModel):
    id: int
    name: str
    avatar: Optional[str] = None
    level: int = 1
    class_name: Optional[str] = None
    race_name: Optional[str] = None
    npc_role: Optional[str] = None

class NeighborClient(BaseModel):
    neighbor_id: int
    name: str
    recommended_level: int
    image_url: Optional[str] = None
    energy_cost: int

class ClientPost(BaseModel):
    post_id: int
    character_id: int
    character_photo: str
    character_title: str
    character_level: Optional[int] = None
    character_name: Optional[str]
    user_id: Optional[int] = None
    user_nickname: Optional[str] = None
    content: str
    length: int
    created_at: datetime
    likes_count: int = 0
    liked_by: List[int] = []

class LocationLootDrop(BaseModel):
    character_id: int
    item_id: int
    quantity: int = 1

class LocationLootPickup(BaseModel):
    character_id: int

class LocationLootItem(BaseModel):
    id: int
    location_id: int
    item_id: int
    quantity: int
    dropped_by_character_id: Optional[int] = None
    dropped_at: Optional[datetime] = None
    item_name: Optional[str] = None
    item_image: Optional[str] = None
    item_rarity: Optional[str] = None
    item_type: Optional[str] = None

    class Config:
        orm_mode = True

class LocationClientDetails(BaseModel):
    id: int
    name: str
    type: str
    parent_id: Optional[int]
    description: str
    image_url: Optional[str]
    recommended_level: int
    quick_travel_marker: bool
    district_id: Optional[int] = None
    region_id: Optional[int] = None
    is_favorited: bool = False
    neighbors: List[NeighborClient] = []
    players: List[PlayerInLocation] = []
    npcs: List[NpcInLocation] = []
    posts: List[ClientPost] = []
    loot: List[LocationLootItem] = []

    class Config:
        orm_mode = True

class MovementPostRequest(BaseModel):
    character_id: int
    content: str

class NpcPostCreate(BaseModel):
    npc_id: int
    location_id: int
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


# -------------------------------
#   SORT ORDER SCHEMAS
# -------------------------------
class SortOrderItem(BaseModel):
    id: int
    type: Literal["district", "location"]
    sort_order: int

class SortOrderUpdate(BaseModel):
    items: List[SortOrderItem]


# -------------------------------
#   FAVORITE / TAG SCHEMAS
# -------------------------------
class LocationFavoriteCreate(BaseModel):
    pass

class TagPlayerRequest(BaseModel):
    target_user_id: int
    sender_character_id: int


# -------------------------------
#   POST MODERATION SCHEMAS
# -------------------------------
class PostDeletionRequestCreate(BaseModel):
    reason: Optional[str] = None

class PostReportCreate(BaseModel):
    reason: Optional[str] = None

class PostDeletionRequestRead(BaseModel):
    id: int
    post_id: int
    user_id: int
    reason: Optional[str] = None
    status: str
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    post_content: Optional[str] = None
    post_character_id: Optional[int] = None
    post_location_id: Optional[int] = None

    class Config:
        orm_mode = True

class PostReportRead(BaseModel):
    id: int
    post_id: int
    user_id: int
    reason: Optional[str] = None
    status: str
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    post_content: Optional[str] = None
    post_character_id: Optional[int] = None
    post_location_id: Optional[int] = None

    class Config:
        orm_mode = True

class PostModerationReview(BaseModel):
    action: str


# -------------------------------
#   DIALOGUE TREE SCHEMAS (Admin)
# -------------------------------
class DialogueOptionCreate(BaseModel):
    text: str
    next_node_index: Optional[int] = None
    sort_order: int = 0
    condition: Optional[dict] = None

class DialogueNodeCreate(BaseModel):
    npc_text: str
    is_root: bool = False
    sort_order: int = 0
    action_type: Optional[str] = None
    action_data: Optional[dict] = None
    options: List[DialogueOptionCreate] = []

class DialogueTreeCreate(BaseModel):
    npc_id: int
    title: str
    is_active: bool = True
    nodes: List[DialogueNodeCreate] = []

class DialogueTreeUpdate(BaseModel):
    title: Optional[str] = None
    is_active: Optional[bool] = None
    nodes: Optional[List[DialogueNodeCreate]] = None

class DialogueOptionRead(BaseModel):
    id: int
    text: str
    next_node_id: Optional[int] = None
    sort_order: int = 0
    condition: Optional[dict] = None

    class Config:
        orm_mode = True

class DialogueNodeRead(BaseModel):
    id: int
    npc_text: str
    is_root: bool = False
    sort_order: int = 0
    action_type: Optional[str] = None
    action_data: Optional[dict] = None
    options: List[DialogueOptionRead] = []

    class Config:
        orm_mode = True

class DialogueTreeRead(BaseModel):
    id: int
    npc_id: int
    title: str
    is_active: bool
    created_at: datetime
    nodes: List[DialogueNodeRead] = []

    class Config:
        orm_mode = True

class DialogueTreeListItem(BaseModel):
    id: int
    npc_id: int
    title: str
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True


# -------------------------------
#   DIALOGUE TREE SCHEMAS (Player)
# -------------------------------
class DialogueOptionResponse(BaseModel):
    id: int
    text: str
    next_node_id: Optional[int] = None

class DialogueNodeResponse(BaseModel):
    id: int
    npc_text: str
    action_type: Optional[str] = None
    action_data: Optional[dict] = None
    options: List[DialogueOptionResponse] = []
    is_end: bool = False

class DialogueChooseRequest(BaseModel):
    option_id: int


# -------------------------------
#   NPC SHOP SCHEMAS
# -------------------------------
class NpcShopItemCreate(BaseModel):
    item_id: int
    buy_price: int
    sell_price: int = 0
    stock: Optional[int] = None

class NpcShopItemUpdate(BaseModel):
    buy_price: Optional[int] = None
    sell_price: Optional[int] = None
    stock: Optional[int] = None
    is_active: Optional[bool] = None

class NpcShopItemRead(BaseModel):
    id: int
    npc_id: int
    item_id: int
    buy_price: int
    sell_price: int
    stock: Optional[int] = None
    is_active: bool
    item_name: Optional[str] = None
    item_image: Optional[str] = None
    item_rarity: Optional[str] = None
    item_type: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True

class ShopBuyRequest(BaseModel):
    character_id: int
    shop_item_id: int
    quantity: int = 1

class ShopSellRequest(BaseModel):
    character_id: int
    item_id: int
    quantity: int = 1

class ShopTransactionResponse(BaseModel):
    success: bool
    message: str
    new_balance: Optional[int] = None
    item_name: Optional[str] = None
    quantity: int = 0
    total_price: int = 0


# -------------------------------
#   QUEST SCHEMAS (Admin)
# -------------------------------
class QuestObjectiveCreate(BaseModel):
    description: str
    objective_type: str  # 'kill', 'collect', 'talk_to', 'visit_location', 'deliver', 'custom'
    target_id: Optional[int] = None
    target_count: int = 1
    sort_order: int = 0

class QuestObjectiveRead(BaseModel):
    id: int
    quest_id: int
    description: str
    objective_type: str
    target_id: Optional[int] = None
    target_count: int = 1
    sort_order: int = 0

    class Config:
        orm_mode = True

class QuestCreate(BaseModel):
    npc_id: int
    title: str
    description: Optional[str] = None
    quest_type: str = 'standard'
    min_level: int = 1
    reward_currency: int = 0
    reward_exp: int = 0
    reward_items: Optional[List[dict]] = None  # [{item_id, quantity}]
    is_active: bool = True
    objectives: List[QuestObjectiveCreate] = []

class QuestUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    quest_type: Optional[str] = None
    min_level: Optional[int] = None
    reward_currency: Optional[int] = None
    reward_exp: Optional[int] = None
    reward_items: Optional[List[dict]] = None
    is_active: Optional[bool] = None
    objectives: Optional[List[QuestObjectiveCreate]] = None

class QuestRead(BaseModel):
    id: int
    npc_id: int
    title: str
    description: Optional[str] = None
    quest_type: str = 'standard'
    min_level: int = 1
    reward_currency: int = 0
    reward_exp: int = 0
    reward_items: Optional[List[dict]] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    objectives: List[QuestObjectiveRead] = []

    class Config:
        orm_mode = True

class QuestListItem(BaseModel):
    id: int
    npc_id: int
    title: str
    quest_type: str = 'standard'
    min_level: int = 1
    is_active: bool = True
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


# -------------------------------
#   QUEST SCHEMAS (Player)
# -------------------------------
class QuestAcceptRequest(BaseModel):
    character_id: int

class QuestCompleteRequest(BaseModel):
    character_id: int

class QuestAbandonRequest(BaseModel):
    character_id: int

class QuestProgressUpdateRequest(BaseModel):
    character_id: int
    quest_id: int
    objective_id: int
    increment: int = 1

class ObjectiveProgressRead(BaseModel):
    objective_id: int
    description: str
    objective_type: str
    target_id: Optional[int] = None
    target_count: int = 1
    current_count: int = 0
    is_completed: bool = False

class ActiveQuestRead(BaseModel):
    id: int
    quest_id: int
    title: str
    description: Optional[str] = None
    quest_type: str
    npc_id: int
    status: str
    accepted_at: Optional[datetime] = None
    reward_currency: int = 0
    reward_exp: int = 0
    reward_items: Optional[List[dict]] = None
    objectives: List[ObjectiveProgressRead] = []

    class Config:
        orm_mode = True

class QuestCompleteResponse(BaseModel):
    success: bool
    message: str
    reward_currency: int = 0
    reward_exp: int = 0
    reward_items: Optional[List[dict]] = None
    new_balance: Optional[int] = None

class QuestAvailableRead(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    quest_type: str = 'standard'
    min_level: int = 1
    reward_currency: int = 0
    reward_exp: int = 0
    reward_items: Optional[List[dict]] = None
    objectives: List[QuestObjectiveRead] = []
    player_status: str = 'available'  # available, active, completed

