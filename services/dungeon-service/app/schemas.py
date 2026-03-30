from pydantic import BaseModel, validator
from typing import Optional, List, Any
from datetime import datetime


# ---------- Dungeon ----------

class DungeonCreate(BaseModel):
    name: str
    description: str
    lore_text: Optional[str] = None
    stability_type: str = "static"
    danger_level: str = "safe"
    location_id: int
    recommended_level: Optional[int] = 1
    recommended_party_size: Optional[int] = 1
    cooldown_hours: int = 24
    mob_multiplier: float = 1.0
    loot_multiplier: float = 1.0
    stamina_multiplier: float = 1.0
    difficulty_modifier: float = 1.0
    disable_rest_rooms: bool = False
    disable_merchants: bool = False
    mana_core_chance: float = 0.0
    mana_core_item_id: Optional[int] = None
    image_url: Optional[str] = None

    @validator("stability_type")
    def validate_stability_type(cls, v):
        allowed = ("static", "unstable", "chaotic")
        if v not in allowed:
            raise ValueError(f"stability_type должен быть одним из: {', '.join(allowed)}")
        return v

    @validator("danger_level")
    def validate_danger_level(cls, v):
        allowed = ("safe", "deadly")
        if v not in allowed:
            raise ValueError(f"danger_level должен быть одним из: {', '.join(allowed)}")
        return v

    @validator("mana_core_chance")
    def validate_mana_core_chance(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError("mana_core_chance должен быть от 0.0 до 1.0")
        return v


class DungeonUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    lore_text: Optional[str] = None
    stability_type: Optional[str] = None
    danger_level: Optional[str] = None
    location_id: Optional[int] = None
    recommended_level: Optional[int] = None
    recommended_party_size: Optional[int] = None
    cooldown_hours: Optional[int] = None
    is_active: Optional[bool] = None
    mob_multiplier: Optional[float] = None
    loot_multiplier: Optional[float] = None
    stamina_multiplier: Optional[float] = None
    difficulty_modifier: Optional[float] = None
    disable_rest_rooms: Optional[bool] = None
    disable_merchants: Optional[bool] = None
    mana_core_chance: Optional[float] = None
    mana_core_item_id: Optional[int] = None
    image_url: Optional[str] = None

    @validator("stability_type")
    def validate_stability_type(cls, v):
        if v is None:
            return v
        allowed = ("static", "unstable", "chaotic")
        if v not in allowed:
            raise ValueError(f"stability_type должен быть одним из: {', '.join(allowed)}")
        return v

    @validator("danger_level")
    def validate_danger_level(cls, v):
        if v is None:
            return v
        allowed = ("safe", "deadly")
        if v not in allowed:
            raise ValueError(f"danger_level должен быть одним из: {', '.join(allowed)}")
        return v

    @validator("mana_core_chance")
    def validate_mana_core_chance(cls, v):
        if v is None:
            return v
        if not 0.0 <= v <= 1.0:
            raise ValueError("mana_core_chance должен быть от 0.0 до 1.0")
        return v


class DungeonResponse(BaseModel):
    id: int
    name: str
    description: str
    lore_text: Optional[str] = None
    stability_type: str
    danger_level: str
    location_id: int
    recommended_level: Optional[int] = None
    recommended_party_size: Optional[int] = None
    cooldown_hours: int
    is_active: bool
    mob_multiplier: float
    loot_multiplier: float
    stamina_multiplier: float
    difficulty_modifier: float
    disable_rest_rooms: bool
    disable_merchants: bool
    mana_core_chance: float
    mana_core_item_id: Optional[int] = None
    image_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class DungeonListResponse(BaseModel):
    id: int
    name: str
    stability_type: str
    danger_level: str
    location_id: int
    is_active: bool
    recommended_level: Optional[int] = None
    recommended_party_size: Optional[int] = None
    cooldown_hours: int
    image_url: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class DungeonAtLocationResponse(BaseModel):
    id: int
    name: str
    description: str
    lore_text: Optional[str] = None
    stability_type: str
    danger_level: str
    recommended_level: Optional[int] = None
    recommended_party_size: Optional[int] = None
    is_on_cooldown: bool = False
    cooldown_remaining_seconds: int = 0
    image_url: Optional[str] = None

    class Config:
        orm_mode = True


# ---------- DungeonRoom ----------

VALID_ROOM_TYPES = (
    "battle", "boss", "treasure", "trap", "event",
    "rest", "merchant", "fork", "teleport", "deadend",
)


class DungeonRoomCreate(BaseModel):
    room_type: str
    name: str
    description: str
    image_url: Optional[str] = None
    sort_order: int = 0
    is_entrance: bool = False
    is_boss_room: bool = False
    is_mana_core_room: bool = False
    room_config: Optional[Any] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None

    @validator("room_type")
    def validate_room_type(cls, v):
        if v not in VALID_ROOM_TYPES:
            raise ValueError(f"room_type должен быть одним из: {', '.join(VALID_ROOM_TYPES)}")
        return v

    @validator("room_config")
    def validate_room_config(cls, v, values):
        if v is None:
            return v
        room_type = values.get("room_type")
        if room_type == "battle" and isinstance(v, dict):
            if "mob_template_ids" in v and not isinstance(v["mob_template_ids"], list):
                raise ValueError("room_config.mob_template_ids должен быть списком")
        if room_type == "boss" and isinstance(v, dict):
            if "mob_template_ids" in v and not isinstance(v["mob_template_ids"], list):
                raise ValueError("room_config.mob_template_ids должен быть списком")
        if room_type == "teleport" and isinstance(v, dict):
            if "target_room_id" in v and not isinstance(v["target_room_id"], int):
                raise ValueError("room_config.target_room_id должен быть целым числом")
        if room_type == "treasure" and isinstance(v, dict):
            if "loot_table" in v and not isinstance(v["loot_table"], list):
                raise ValueError("room_config.loot_table должен быть списком")
        if room_type == "event" and isinstance(v, dict):
            if "choices" in v and not isinstance(v["choices"], list):
                raise ValueError("room_config.choices должен быть списком")
        if room_type == "merchant" and isinstance(v, dict):
            if "items" in v and not isinstance(v["items"], list):
                raise ValueError("room_config.items должен быть списком")
        if room_type == "trap" and isinstance(v, dict):
            if "stat_check" in v and not isinstance(v["stat_check"], str):
                raise ValueError("room_config.stat_check должен быть строкой")
        return v


class DungeonRoomUpdate(BaseModel):
    room_type: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: Optional[int] = None
    is_entrance: Optional[bool] = None
    is_boss_room: Optional[bool] = None
    is_mana_core_room: Optional[bool] = None
    room_config: Optional[Any] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None

    @validator("room_type")
    def validate_room_type(cls, v):
        if v is None:
            return v
        if v not in VALID_ROOM_TYPES:
            raise ValueError(f"room_type должен быть одним из: {', '.join(VALID_ROOM_TYPES)}")
        return v


class DungeonRoomResponse(BaseModel):
    id: int
    dungeon_id: int
    room_type: str
    name: str
    description: str
    image_url: Optional[str] = None
    sort_order: int
    is_entrance: bool
    is_boss_room: bool
    is_mana_core_room: bool
    room_config: Optional[Any] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


# ---------- Bulk Room Position Update ----------

class RoomPositionItem(BaseModel):
    room_id: int
    position_x: float
    position_y: float

class BulkRoomPositionUpdate(BaseModel):
    positions: List[RoomPositionItem]

    @validator("positions")
    def validate_not_empty(cls, v):
        if not v:
            raise ValueError("positions list must not be empty")
        return v

class BulkPositionUpdateResponse(BaseModel):
    updated: int


# ---------- DungeonCorridor ----------

class DungeonCorridorCreate(BaseModel):
    from_room_id: int
    to_room_id: int
    stamina_cost: int = 5
    is_bidirectional: bool = True
    random_battle_chance: float = 0.0
    random_battle_mob_ids: Optional[Any] = None
    trap_chance: float = 0.0
    trap_config: Optional[Any] = None
    description: Optional[str] = None
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None

    @validator("random_battle_chance", "trap_chance")
    def validate_chance(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError("Шанс должен быть от 0.0 до 1.0")
        return v

    @validator("from_room_id")
    def validate_not_self_loop(cls, v, values):
        return v

    @validator("to_room_id")
    def validate_to_room(cls, v, values):
        from_id = values.get("from_room_id")
        if from_id is not None and v == from_id:
            raise ValueError("Коридор не может вести из комнаты в саму себя")
        return v


class DungeonCorridorUpdate(BaseModel):
    stamina_cost: Optional[int] = None
    is_bidirectional: Optional[bool] = None
    random_battle_chance: Optional[float] = None
    random_battle_mob_ids: Optional[Any] = None
    trap_chance: Optional[float] = None
    trap_config: Optional[Any] = None
    description: Optional[str] = None
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None

    @validator("random_battle_chance", "trap_chance")
    def validate_chance(cls, v):
        if v is None:
            return v
        if not 0.0 <= v <= 1.0:
            raise ValueError("Шанс должен быть от 0.0 до 1.0")
        return v


class DungeonCorridorResponse(BaseModel):
    id: int
    dungeon_id: int
    from_room_id: int
    to_room_id: int
    stamina_cost: int
    is_bidirectional: bool
    random_battle_chance: float
    random_battle_mob_ids: Optional[Any] = None
    trap_chance: float
    trap_config: Optional[Any] = None
    description: Optional[str] = None
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


# ---------- Dungeon Detail (dungeon + rooms + corridors) ----------

class DungeonDetailResponse(BaseModel):
    id: int
    name: str
    description: str
    lore_text: Optional[str] = None
    stability_type: str
    danger_level: str
    location_id: int
    recommended_level: Optional[int] = None
    recommended_party_size: Optional[int] = None
    cooldown_hours: int
    is_active: bool
    mob_multiplier: float
    loot_multiplier: float
    stamina_multiplier: float
    difficulty_modifier: float
    disable_rest_rooms: bool
    disable_merchants: bool
    mana_core_chance: float
    mana_core_item_id: Optional[int] = None
    image_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    rooms: List[DungeonRoomResponse] = []
    corridors: List[DungeonCorridorResponse] = []

    class Config:
        orm_mode = True


# ---------- Dungeon Validation ----------

class DungeonValidationResponse(BaseModel):
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []


# ---------- Session / Party ----------

class SessionCreateRequest(BaseModel):
    character_id: int


class SessionInviteRequest(BaseModel):
    character_id: int


class SessionLeaveRequest(BaseModel):
    character_id: int


class SessionEnterRequest(BaseModel):
    character_id: int


class SessionMemberResponse(BaseModel):
    character_id: int
    name: str
    status: str
    is_leader: bool
    user_id: int

    class Config:
        orm_mode = True


class SessionResponse(BaseModel):
    session_id: int
    dungeon_id: int
    status: str
    leader_character_id: int
    members: List[SessionMemberResponse] = []

    class Config:
        orm_mode = True


class RoomExitResponse(BaseModel):
    corridor_id: int
    to_room_id: int
    to_room_name: str
    stamina_cost: int
    explored: bool
    reliability: Optional[str] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None


class RoomViewResponse(BaseModel):
    id: int
    room_type: str
    name: str
    description: str
    image_url: Optional[str] = None
    is_entrance: bool
    is_boss_room: bool
    is_cleared: bool = False
    room_config_visible: Optional[Any] = None
    exits: List[RoomExitResponse] = []
    position_x: Optional[float] = None
    position_y: Optional[float] = None

    class Config:
        orm_mode = True


class ExploredRoomInfo(BaseModel):
    id: int
    name: str
    room_type: str
    is_cleared: bool
    position_x: Optional[float] = None
    position_y: Optional[float] = None


class ExploredCorridorInfo(BaseModel):
    corridor_id: int
    from_room_id: int
    to_room_id: int
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None


class GroupInventoryItemResponse(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    quantity: int
    source_description: Optional[str] = None

    class Config:
        orm_mode = True


class SessionStateResponse(BaseModel):
    session_id: int
    dungeon_id: int
    dungeon_name: str
    location_id: int = 0
    status: str
    phase: str
    current_room: Optional[RoomViewResponse] = None
    members: List[SessionMemberResponse] = []
    group_inventory: List[GroupInventoryItemResponse] = []
    active_battle_id: Optional[int] = None
    explored_rooms: List[ExploredRoomInfo] = []
    explored_corridors: List[ExploredCorridorInfo] = []

    class Config:
        orm_mode = True


# ---------- Movement ----------

class MoveRequest(BaseModel):
    character_id: int
    corridor_id: int


class CorridorEventResponse(BaseModel):
    type: str  # "battle", "trap", "safe"
    details: Optional[dict] = None
    message: str


class MoveResponse(BaseModel):
    corridor_event: Optional[CorridorEventResponse] = None
    new_room: Optional[RoomViewResponse] = None
    stamina_consumed: int
    room_event: Optional[dict] = None


# ---------- Battle Callback (internal) ----------

class BattleCallbackRequest(BaseModel):
    battle_id: int
    session_id: int
    winner_team: Optional[int] = None
    defeated_characters: List[int] = []
    battle_loot: Optional[List[dict]] = None


# ---------- Room Interaction ----------

class InteractRequest(BaseModel):
    character_id: int
    action: str
    choice_index: Optional[int] = None
    target_character_id: Optional[int] = None
    item_id: Optional[int] = None
    quantity: Optional[int] = None


class InteractResponse(BaseModel):
    action: str
    success: bool
    message: str
    loot_gained: Optional[List[dict]] = None
    damage_taken: Optional[int] = None
    effect_applied: Optional[str] = None
    gold_spent: Optional[int] = None
    teleported_to: Optional[dict] = None


# ---------- Flee ----------

class FleeRequest(BaseModel):
    character_id: int


class FleeItemInfo(BaseModel):
    item_id: int
    quantity: int
    item_name: Optional[str] = None


class FleeResponse(BaseModel):
    status: str
    items_lost: List[FleeItemInfo] = []
    items_remaining: List[FleeItemInfo] = []
    message: str


# ---------- Loot Distribution ----------

class LootDistributionItem(BaseModel):
    item_id: int
    quantity: int
    to_character_id: int


class DistributeLootRequest(BaseModel):
    character_id: int
    distributions: List[LootDistributionItem] = []


class DistributeLootResponse(BaseModel):
    success: bool
    message: str
    remaining_inventory: List[GroupInventoryItemResponse] = []


# ---------- Finalize ----------

class FinalizeRequest(BaseModel):
    character_id: int
    force: bool = False


class FinalizeResponse(BaseModel):
    message: str
    cooldown_until: Optional[datetime] = None


# ---------- Admin: Sessions ----------

class AdminSessionMemberResponse(BaseModel):
    character_id: int
    user_id: int
    status: str

    class Config:
        orm_mode = True


class AdminSessionResponse(BaseModel):
    id: int
    dungeon_id: int
    dungeon_name: Optional[str] = None
    leader_character_id: int
    status: str
    current_room_id: Optional[int] = None
    started_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    members: List[AdminSessionMemberResponse] = []

    class Config:
        orm_mode = True
