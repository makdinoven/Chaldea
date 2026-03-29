from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, validator


# ---------- Reward ----------

class RewardOut(BaseModel):
    id: int
    reward_type: str
    reward_value: int
    item_id: Optional[int] = None
    item_name: Optional[str] = None
    cosmetic_slug: Optional[str] = None

    class Config:
        orm_mode = True


# ---------- Level ----------

class LevelOut(BaseModel):
    level_number: int
    required_xp: int
    free_rewards: List[RewardOut] = []
    premium_rewards: List[RewardOut] = []

    class Config:
        orm_mode = True


# ---------- Season ----------

class SeasonCurrentOut(BaseModel):
    id: int
    name: str
    segment_name: str
    year: int
    start_date: datetime
    end_date: datetime
    grace_end_date: datetime
    is_active: bool
    status: str  # "active", "grace", "ended"
    days_remaining: int
    current_week: int
    total_weeks: int
    levels: List[LevelOut] = []

    class Config:
        orm_mode = True


# ---------- User Progress ----------

class ClaimedRewardOut(BaseModel):
    level_number: int
    track: str
    claimed_at: datetime
    character_id: int

    class Config:
        orm_mode = True


class UserProgressOut(BaseModel):
    season_id: int
    current_level: int
    current_xp: int
    xp_to_next_level: Optional[int] = None
    is_premium: bool
    claimed_rewards: List[ClaimedRewardOut] = []

    class Config:
        orm_mode = True


# ---------- Missions ----------

class MissionOut(BaseModel):
    id: int
    week_number: int
    mission_type: str
    description: str
    target_count: int
    current_count: int = 0
    is_completed: bool = False
    completed_at: Optional[datetime] = None
    xp_reward: int

    class Config:
        orm_mode = True


class MissionsResponse(BaseModel):
    season_id: int
    current_week: int
    missions: List[MissionOut] = []

    class Config:
        orm_mode = True


# ---------- Mission Complete ----------

class MissionCompleteOut(BaseModel):
    ok: bool = True
    xp_awarded: int
    new_total_xp: int
    new_level: int
    leveled_up: bool

    class Config:
        orm_mode = True


# ---------- Reward Claim ----------

class RewardClaimRequest(BaseModel):
    level_number: int
    track: str  # "free" or "premium"


class RewardClaimOut(BaseModel):
    ok: bool = True
    reward_type: str
    reward_value: int
    delivered_to_character_id: int
    delivered_to_character_name: str

    class Config:
        orm_mode = True


# ---------- Track Event (internal) ----------

class TrackEventRequest(BaseModel):
    user_id: int
    event_type: str  # "location_visit"
    character_id: int
    metadata: Optional[dict] = None


# ==========================================================================
# Admin schemas
# ==========================================================================

# ---------- Season Admin ----------

class SeasonCreate(BaseModel):
    name: str
    segment_name: str
    year: int
    start_date: datetime
    end_date: datetime

    @validator("end_date")
    def end_after_start(cls, v, values):
        if "start_date" in values and v <= values["start_date"]:
            raise ValueError("end_date должна быть позже start_date")
        return v


class SeasonUpdate(BaseModel):
    name: Optional[str] = None
    segment_name: Optional[str] = None
    year: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: Optional[bool] = None


class SeasonAdminOut(BaseModel):
    id: int
    name: str
    segment_name: str
    year: int
    start_date: datetime
    end_date: datetime
    grace_end_date: datetime
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True


class SeasonListOut(BaseModel):
    items: List[SeasonAdminOut] = []
    total: int


# ---------- Level + Reward Admin ----------

class RewardIn(BaseModel):
    reward_type: str
    reward_value: int
    item_id: Optional[int] = None
    cosmetic_slug: Optional[str] = None

    @validator("reward_type")
    def valid_reward_type(cls, v):
        allowed = {"gold", "xp", "item", "diamonds", "frame", "chat_background"}
        if v not in allowed:
            raise ValueError(f"reward_type должен быть одним из: {', '.join(sorted(allowed))}")
        return v

    @validator("reward_value")
    def positive_value(cls, v):
        if v <= 0:
            raise ValueError("reward_value должен быть положительным")
        return v

    @validator("cosmetic_slug", always=True)
    def cosmetic_slug_required_for_cosmetics(cls, v, values):
        reward_type = values.get("reward_type")
        if reward_type in ("frame", "chat_background") and not v:
            raise ValueError("cosmetic_slug обязателен для типов frame и chat_background")
        return v


class LevelWithRewardsIn(BaseModel):
    level_number: int
    required_xp: int
    free_rewards: List[RewardIn] = []
    premium_rewards: List[RewardIn] = []

    @validator("level_number")
    def valid_level(cls, v):
        if v < 1 or v > 30:
            raise ValueError("level_number должен быть от 1 до 30")
        return v

    @validator("required_xp")
    def positive_xp(cls, v):
        if v <= 0:
            raise ValueError("required_xp должен быть положительным")
        return v


class LevelsBulkUpsert(BaseModel):
    levels: List[LevelWithRewardsIn]


class RewardAdminOut(BaseModel):
    id: int
    track: str
    reward_type: str
    reward_value: int
    item_id: Optional[int] = None
    cosmetic_slug: Optional[str] = None

    class Config:
        orm_mode = True


class LevelAdminOut(BaseModel):
    id: int
    level_number: int
    required_xp: int
    rewards: List[RewardAdminOut] = []

    class Config:
        orm_mode = True


# ---------- Mission Admin ----------

class MissionIn(BaseModel):
    week_number: int
    mission_type: str
    description: str
    target_count: int
    xp_reward: int

    @validator("week_number")
    def positive_week(cls, v):
        if v < 1:
            raise ValueError("week_number должен быть >= 1")
        return v

    @validator("mission_type")
    def valid_mission_type(cls, v):
        allowed = {
            "kill_mobs", "write_posts", "level_up", "visit_locations",
            "earn_gold", "spend_gold", "quest_complete", "dungeon_run",
            "resource_gather",
        }
        if v not in allowed:
            raise ValueError(f"mission_type должен быть одним из: {', '.join(sorted(allowed))}")
        return v

    @validator("target_count")
    def positive_target(cls, v):
        if v <= 0:
            raise ValueError("target_count должен быть положительным")
        return v

    @validator("xp_reward")
    def positive_xp_reward(cls, v):
        if v <= 0:
            raise ValueError("xp_reward должен быть положительным")
        return v


class MissionsBulkUpsert(BaseModel):
    missions: List[MissionIn]


class MissionAdminOut(BaseModel):
    id: int
    week_number: int
    mission_type: str
    description: str
    target_count: int
    xp_reward: int

    class Config:
        orm_mode = True


class MissionsGroupedOut(BaseModel):
    weeks: Dict[str, List[MissionAdminOut]] = {}
