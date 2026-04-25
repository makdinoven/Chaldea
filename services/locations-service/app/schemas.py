from pydantic import BaseModel, validator
from typing import Optional, List, Literal, Dict, Any
from datetime import datetime


# -------------------------------
#   COUNTRY SCHEMAS
# -------------------------------
class CountryBase(BaseModel):
    name: str
    description: str
    is_hidden: bool = False

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
    is_hidden: Optional[bool] = None

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
    is_hidden: bool = False

    @validator('is_hidden', pre=True, always=True)
    def _default_is_hidden(cls, v):
        return False if v is None else bool(v)

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
    no_quick_move: Optional[bool] = False
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
    no_quick_move: Optional[bool] = False
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
    no_quick_move: Optional[bool] = False
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
    no_quick_move: bool = False
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
#   PATH / WAYPOINT SCHEMAS
# -------------------------------
class PathWaypoint(BaseModel):
    x: float  # 0-100 percentage
    y: float  # 0-100 percentage

class PathDataUpdate(BaseModel):
    path_data: List[PathWaypoint]

class NeighborEdgeResponse(BaseModel):
    from_id: int
    to_id: int
    energy_cost: int
    path_data: Optional[List[PathWaypoint]] = None

    class Config:
        orm_mode = True

# -------------------------------
#   NEIGHBOR / POST SCHEMAS
# -------------------------------
class LocationNeighborCreate(BaseModel):
    neighbor_id: int
    energy_cost: int = 1
    path_data: Optional[List[PathWaypoint]] = None

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
    path_data: Optional[List[PathWaypoint]] = None

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
    character_title_rarity: Optional[str] = None
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
    id: int
    name: str
    recommended_level: int
    image_url: Optional[str] = None
    energy_cost: int

class ClientPost(BaseModel):
    post_id: int
    character_id: int
    character_photo: str
    character_title: str
    character_title_rarity: Optional[str] = None
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
    no_quick_move: bool = False
    marker_type: Optional[str] = None
    district_id: Optional[int] = None
    region_id: Optional[int] = None
    is_favorited: bool = False
    neighbors: List[NeighborClient] = []
    players: List[PlayerInLocation] = []
    npcs: List[NpcInLocation] = []
    posts: List[ClientPost] = []
    loot: List[LocationLootItem] = []
    gathering_nodes: List["GatheringNodeClient"] = []

    class Config:
        orm_mode = True

class MovementPostRequest(BaseModel):
    character_id: int
    content: str

class QuickMoveRequest(BaseModel):
    character_id: int

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
    discounted_buy_price: Optional[int] = None

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
    discount_percent: float = 0


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


class QuestAutoProgressRequest(BaseModel):
    character_id: int
    event_type: str  # kill_mob, kill_mob_any, visit_location, write_posts, collect, etc.
    increment: int = 1
    target_id: Optional[int] = None  # mob_template_id, location_id, item_id, npc_id, etc.
    meta: Optional[dict] = None  # additional data (e.g. {"tier": "boss"})

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


# -------------------------------
#   ARCHIVE CATEGORY SCHEMAS
# -------------------------------
class ArchiveCategoryCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    sort_order: int = 0

class ArchiveCategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None

class ArchiveCategoryRead(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    sort_order: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class ArchiveCategoryWithCount(ArchiveCategoryRead):
    article_count: int = 0


# -------------------------------
#   ARCHIVE ARTICLE SCHEMAS
# -------------------------------
class ArchiveArticleCreate(BaseModel):
    title: str
    slug: str
    content: Optional[str] = None
    summary: Optional[str] = None
    cover_image_url: Optional[str] = None
    cover_text_color: Optional[str] = None
    is_featured: bool = False
    featured_sort_order: int = 0
    category_ids: List[int] = []

class ArchiveArticleUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    cover_image_url: Optional[str] = None
    cover_text_color: Optional[str] = None
    is_featured: Optional[bool] = None
    featured_sort_order: Optional[int] = None
    category_ids: Optional[List[int]] = None

class ArchiveArticleRead(BaseModel):
    id: int
    title: str
    slug: str
    content: Optional[str] = None
    summary: Optional[str] = None
    cover_image_url: Optional[str] = None
    cover_text_color: Optional[str] = None
    is_featured: bool
    featured_sort_order: int
    created_by_user_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    categories: List[ArchiveCategoryRead] = []

    class Config:
        orm_mode = True

class ArchiveArticleListItem(BaseModel):
    """Lightweight schema for list views — no content field."""
    id: int
    title: str
    slug: str
    summary: Optional[str] = None
    cover_image_url: Optional[str] = None
    cover_text_color: Optional[str] = None
    is_featured: bool
    featured_sort_order: int
    created_at: datetime
    updated_at: datetime
    categories: List[ArchiveCategoryRead] = []

    class Config:
        orm_mode = True

class ArchiveArticlePreview(BaseModel):
    """Minimal schema for hover preview tooltips."""
    id: int
    title: str
    slug: str
    summary: Optional[str] = None
    cover_image_url: Optional[str] = None

    class Config:
        orm_mode = True

class ArchiveSearchResult(BaseModel):
    articles: List[ArchiveArticleListItem]
    total: int


# -------------------------------
#   CHARACTER POST STATS SCHEMAS
# -------------------------------
class CharacterPostStats(BaseModel):
    count: int
    last_date: Optional[datetime] = None

class CharacterPostStatsResponse(BaseModel):
    stats: Dict[str, CharacterPostStats]


# -------------------------------
#   TRANSITION ARROW SCHEMAS
# -------------------------------
class TransitionArrowCreate(BaseModel):
    region_id: int
    target_region_id: int
    x: Optional[float] = None
    y: Optional[float] = None
    label: Optional[str] = None
    rotation: Optional[float] = 0

class TransitionArrowUpdate(BaseModel):
    x: Optional[float] = None
    y: Optional[float] = None
    label: Optional[str] = None
    rotation: Optional[float] = None

class TransitionArrowRead(BaseModel):
    id: int
    region_id: int
    target_region_id: int
    target_region_name: Optional[str] = None
    paired_arrow_id: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None
    label: Optional[str] = None
    rotation: Optional[float] = None

    class Config:
        orm_mode = True

class TransitionArrowCreateResponse(BaseModel):
    arrow: TransitionArrowRead
    paired_arrow: TransitionArrowRead

class ArrowNeighborCreate(BaseModel):
    location_id: int
    energy_cost: int = 0
    path_data: Optional[List[PathWaypoint]] = None

class ArrowNeighborRead(BaseModel):
    id: int
    location_id: int
    arrow_id: int
    energy_cost: int
    path_data: Optional[List[PathWaypoint]] = None

    class Config:
        orm_mode = True

class ArrowEdgeResponse(BaseModel):
    location_id: int
    arrow_id: int
    energy_cost: int
    path_data: Optional[List[PathWaypoint]] = None

    class Config:
        orm_mode = True


# -------------------------------
#   FLOATING STRUCTURES (FEAT-123)
# -------------------------------
def _validate_route_json(v: Any) -> List[Dict[str, float]]:
    if not isinstance(v, list):
        raise ValueError("route_json должен быть списком точек")
    cleaned: List[Dict[str, float]] = []
    for i, point in enumerate(v):
        if not isinstance(point, dict):
            raise ValueError(f"route_json[{i}] должен быть объектом {{x, y}}")
        if 'x' not in point or 'y' not in point:
            raise ValueError(f"route_json[{i}] должен содержать поля x и y")
        try:
            x = float(point['x'])
            y = float(point['y'])
        except (TypeError, ValueError):
            raise ValueError(f"route_json[{i}].x и .y должны быть числами")
        if not (0 <= x <= 100) or not (0 <= y <= 100):
            raise ValueError(f"route_json[{i}] x и y должны быть в диапазоне [0, 100]")
        cleaned.append({"x": x, "y": y})
    return cleaned


class FloatingStructureBase(BaseModel):
    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    route_json: List[Dict[str, float]] = []
    speed: float
    started_at: Optional[datetime] = None
    internal_district_id: Optional[int] = None
    area_id: Optional[int] = None

    @validator('route_json', pre=True, always=True)
    def _vroute(cls, v):
        if v is None:
            return []
        return _validate_route_json(v)

    @validator('speed')
    def _vspeed(cls, v):
        if v is None or v <= 0:
            raise ValueError("speed должен быть больше 0")
        return v

    @validator('name')
    def _vname(cls, v):
        if not v or not v.strip():
            raise ValueError("name не должно быть пустым")
        if len(v) > 120:
            raise ValueError("name не должно превышать 120 символов")
        return v


class FloatingStructureCreate(FloatingStructureBase):
    pass


class FloatingStructureUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon_url: Optional[str] = None
    route_json: Optional[List[Dict[str, float]]] = None
    speed: Optional[float] = None
    started_at: Optional[datetime] = None
    internal_district_id: Optional[int] = None
    area_id: Optional[int] = None

    @validator('route_json')
    def _vroute(cls, v):
        if v is None:
            return v
        return _validate_route_json(v)

    @validator('speed')
    def _vspeed(cls, v):
        if v is None:
            return v
        if v <= 0:
            raise ValueError("speed должен быть больше 0")
        return v

    @validator('name')
    def _vname(cls, v):
        if v is None:
            return v
        if not v.strip():
            raise ValueError("name не должно быть пустым")
        if len(v) > 120:
            raise ValueError("name не должно превышать 120 символов")
        return v


class FloatingStructureRead(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    route_json: List[Dict[str, float]]
    speed: float
    started_at: datetime
    internal_district_id: Optional[int] = None
    area_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class FloatingStructurePublicRead(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    route_json: List[Dict[str, float]]
    speed: float
    started_at: datetime
    server_now: datetime
    internal_district_id: Optional[int] = None
    area_id: Optional[int] = None

    class Config:
        orm_mode = True


# -------------------------------
#   GATHERING NODE — ADMIN SCHEMAS (FEAT-128)
# -------------------------------
GatheringCategory = Literal["ore", "herb", "wood"]


class GatheringNodeAdminCreate(BaseModel):
    """Admin payload for creating a gathering node on a location."""

    node_name: str
    category: GatheringCategory
    result_item_id: int
    result_quantity_per_gather: int = 1
    stamina_per_gather: int
    daily_bank_max: int
    allow_concurrent_gather: bool = False
    is_enabled: bool = True

    @validator('node_name')
    def _vname(cls, v):
        if v is None or not v.strip():
            raise ValueError("Название ноды не может быть пустым")
        if len(v) > 120:
            raise ValueError("Название ноды не должно превышать 120 символов")
        return v.strip()

    @validator('result_item_id')
    def _vresult_item_id(cls, v):
        if v is None or v <= 0:
            raise ValueError("result_item_id должен быть положительным числом")
        return v

    @validator('result_quantity_per_gather')
    def _vqty(cls, v):
        if v is None or v < 1:
            raise ValueError("result_quantity_per_gather должно быть >= 1")
        return v

    @validator('stamina_per_gather')
    def _vstamina(cls, v):
        if v is None or v < 1:
            raise ValueError("stamina_per_gather должно быть >= 1")
        return v

    @validator('daily_bank_max')
    def _vbank(cls, v):
        if v is None or v < 1:
            raise ValueError("daily_bank_max должно быть >= 1")
        return v


class GatheringNodeAdminUpdate(BaseModel):
    """Admin payload for partial-update of a gathering node. All fields optional."""

    node_name: Optional[str] = None
    category: Optional[GatheringCategory] = None
    result_item_id: Optional[int] = None
    result_quantity_per_gather: Optional[int] = None
    stamina_per_gather: Optional[int] = None
    daily_bank_max: Optional[int] = None
    allow_concurrent_gather: Optional[bool] = None
    is_enabled: Optional[bool] = None

    @validator('node_name')
    def _vname(cls, v):
        if v is None:
            return v
        if not v.strip():
            raise ValueError("Название ноды не может быть пустым")
        if len(v) > 120:
            raise ValueError("Название ноды не должно превышать 120 символов")
        return v.strip()

    @validator('result_item_id')
    def _vresult_item_id(cls, v):
        if v is None:
            return v
        if v <= 0:
            raise ValueError("result_item_id должен быть положительным числом")
        return v

    @validator('result_quantity_per_gather')
    def _vqty(cls, v):
        if v is None:
            return v
        if v < 1:
            raise ValueError("result_quantity_per_gather должно быть >= 1")
        return v

    @validator('stamina_per_gather')
    def _vstamina(cls, v):
        if v is None:
            return v
        if v < 1:
            raise ValueError("stamina_per_gather должно быть >= 1")
        return v

    @validator('daily_bank_max')
    def _vbank(cls, v):
        if v is None:
            return v
        if v < 1:
            raise ValueError("daily_bank_max должно быть >= 1")
        return v


class GatheringNodeAdmin(BaseModel):
    """Admin read-shape for a gathering node, enriched with cross-service item info."""

    id: int
    location_id: int
    node_name: str
    category: str
    result_item_id: int
    result_quantity_per_gather: int
    stamina_per_gather: int
    daily_bank_max: int
    current_bank: int
    allow_concurrent_gather: bool
    depleted_at: Optional[datetime] = None
    restore_at: Optional[datetime] = None
    is_enabled: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Cross-service joined fields from items table (inventory-service-owned)
    result_item_name: Optional[str] = None
    result_item_image: Optional[str] = None
    result_item_type: Optional[str] = None

    class Config:
        orm_mode = True


# -------------------------------
#   GATHERING — CLIENT-FACING SCHEMAS (FEAT-128 task #11)
# -------------------------------
class ActiveGatherer(BaseModel):
    """Per-character entry inside `GatheringNodeClient.active_sessions`.

    Cross-service fields (`character_name`, `character_avatar_url`) are
    enriched on the locations-service side via the existing players-by-location
    lookup or `/{character_id}/short_info` fallback. Both may be empty strings
    if the character lookup failed (best-effort enrichment).
    """

    session_id: int
    character_id: int
    character_name: Optional[str] = ""
    character_avatar_url: Optional[str] = None
    started_at: Optional[datetime] = None
    complete_at: datetime

    class Config:
        orm_mode = True


class GatheringNodeClient(BaseModel):
    """Player-facing shape of a gathering node, surfaced inside
    `LocationClientDetails.gathering_nodes`. Mirrors section 3.1 of FEAT-128.

    `result_item_*` fields are joined from the shared `items` table (owned by
    inventory-service). `active_sessions` lists currently-active sessions on
    this node with character-name/avatar enriched in batch.
    """

    id: int
    node_name: str
    category: str
    result_item_id: int
    result_item_name: Optional[str] = None
    result_item_image: Optional[str] = None
    result_item_type: Optional[str] = None
    result_quantity_per_gather: int
    stamina_per_gather: int
    base_seconds: int
    current_bank: int
    daily_bank_max: int
    allow_concurrent_gather: bool
    depleted_at: Optional[datetime] = None
    restore_at: Optional[datetime] = None
    is_enabled: bool
    active_sessions: List[ActiveGatherer] = []

    class Config:
        orm_mode = True


# Resolve forward reference: `LocationClientDetails` declares
# `gathering_nodes: List["GatheringNodeClient"]` before this class exists.
LocationClientDetails.update_forward_refs(GatheringNodeClient=GatheringNodeClient)


# -------------------------------
#   GATHERING — START SESSION SCHEMAS (FEAT-128 task #14)
# -------------------------------
class StartGatheringRequest(BaseModel):
    """Player-facing request body for POST /gathering-nodes/{node_id}/start.

    `tool_inventory_item_id` is nullable — null means "gather without a tool"
    (lenient mode per FEAT-128 §3.6: rank speed/stamina bonuses still apply,
    only tool bonuses are zeroed and ×2 time penalty is added).
    """

    character_id: int
    tool_inventory_item_id: Optional[int] = None

    @validator('character_id')
    def _vcid(cls, v):
        if v is None or v <= 0:
            raise ValueError("character_id должен быть положительным числом")
        return v

    @validator('tool_inventory_item_id')
    def _vtool(cls, v):
        if v is None:
            return v
        if v <= 0:
            raise ValueError("tool_inventory_item_id должен быть положительным числом")
        return v


class NodeStateAfter(BaseModel):
    """Snapshot of node-side state immediately after a successful gather start.

    `current_bank` is unchanged on start (bank only decrements at finalize per
    FEAT-128 §3.5.1 step 15). `active_sessions_count` reflects the number of
    sessions on the node with `status='active'` and `complete_at > NOW()`
    AFTER the new session has been inserted (i.e. includes the just-created
    one).
    """

    current_bank: int
    active_sessions_count: int


class StartGatheringResponse(BaseModel):
    """Player-facing response for POST /gathering-nodes/{node_id}/start.

    Mirrors the contract in FEAT-128 §3.1.1. `effective_*` fields are the
    snapshot of the bonuses used at start, persisted on the session row so
    later admin edits to the node never affect the in-flight calculation.

    Spec-required fields: `tool_durability_at_start` and `auto_post_id`
    (added in Review #1 fix). `effective_stamina_bonus_pct` and
    `node_state_after` are additive debug info kept for the frontend's
    optional consumption — frontend ignores unknown fields.
    """

    session_id: int
    node_id: int
    character_id: int
    started_at: datetime
    complete_at: datetime
    effective_seconds: int
    effective_stamina_paid: int
    effective_speed_bonus_pct: float
    effective_double_chance_pct: float
    effective_stamina_bonus_pct: float
    tool_inventory_item_id: Optional[int] = None
    tool_durability_at_start: Optional[int] = None
    status: str
    auto_post_id: Optional[int] = None
    node_state_after: NodeStateAfter

    class Config:
        orm_mode = True


# -------------------------------
#   GATHERING — CANCEL SESSION SCHEMAS (FEAT-128 task #15)
# -------------------------------
class CancelGatheringRequest(BaseModel):
    """Request body for the player-facing manual cancel endpoint."""
    character_id: int

    @validator('character_id')
    def _vcid(cls, v):
        if v is None or v <= 0:
            raise ValueError("character_id должен быть положительным числом")
        return v


class CancelGatheringInternalRequest(BaseModel):
    """Request body for the internal cancel-gathering endpoint (called by
    battle-service when a battle interrupts the victim's gathering).
    """
    character_id: int

    @validator('character_id')
    def _vcid(cls, v):
        if v is None or v <= 0:
            raise ValueError("character_id должен быть положительным числом")
        return v


class CancelGatheringResponse(BaseModel):
    """Response shape for both cancel endpoints. `cancelled=False` is only
    used by the internal cancel when no active session existed (idempotent
    no-op). The manual cancel raises 400 in that case instead.
    """
    cancelled: bool
    session_id: Optional[int] = None
    stamina_refunded: Optional[int] = None
    reason: Optional[str] = None


# -------------------------------
#   GATHERING — POLL ACTIVE GATHERING SCHEMAS (FEAT-128 task #16)
# -------------------------------
class LastFinishedSessionInfo(BaseModel):
    """One-shot completion summary returned by the poll endpoint when a
    session was finalized DURING THE CURRENT REQUEST. Subsequent polls return
    `last_finished_session: null` — the client renders this as a toast.

    Field names match the frontend `FinishedGatheringSummary` interface in
    `services/frontend/app-chaldea/src/types/gathering.ts`:
      * `session_id` (was `id`)
      * `xp_gained`  (was `xp_awarded`)
      * `rank_up_to: int | None` (replaces `rank_up: bool` + `new_rank`).
        Truthy <=> rank changed; null <=> no rank-up this session.
      * `skill_slug` and `tool_durability_remaining` are added per spec.
    """
    session_id: int
    node_id: Optional[int] = None
    node_name: str = ""
    result_item_id: Optional[int] = None
    result_item_name: Optional[str] = None
    result_quantity: int
    xp_gained: int
    skill_slug: Optional[str] = None
    rank_up_to: Optional[int] = None
    tool_durability_remaining: Optional[int] = None
    tool_broke: bool
    status: str

    class Config:
        orm_mode = True


class ActiveGatheringResponse(BaseModel):
    """Top-level poll response for
    `GET /locations/characters/{cid}/active_gathering`.

    Per FEAT-128 §3.1.1 the active-session fields are FLAT on the top-level
    object (no nested `session` wrapper). This matches the frontend
    discriminated union `ActiveGatheringSession | NoActiveGatheringResponse`
    in `types/gathering.ts`. When `active=false`, the active-only fields are
    omitted (None).
    """
    active: bool
    # Active-only fields (populated when active=True):
    session_id: Optional[int] = None
    node_id: Optional[int] = None
    node_name: Optional[str] = None
    location_id: Optional[int] = None
    started_at: Optional[datetime] = None
    complete_at: Optional[datetime] = None
    remaining_seconds: Optional[int] = None
    stamina_paid: Optional[int] = None
    tool_inventory_item_id: Optional[int] = None
    effective_speed_bonus_pct: Optional[float] = None
    effective_double_chance_pct: Optional[float] = None
    effective_stamina_bonus_pct: Optional[float] = None
    # Toast trigger — only populated on the first poll after a finalize.
    last_finished_session: Optional[LastFinishedSessionInfo] = None

    class Config:
        orm_mode = True


