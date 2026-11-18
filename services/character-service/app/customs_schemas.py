"""FEAT-216 customs — Pydantic v1 schemas of the officer job (C1–C4) and the admin bans API (A1, A2)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Extra, Field, conint

import customs_core


# --------------------------------------------------------------------------------------------- officer (C1–C4)

class CustomsCharacterIn(BaseModel):
    character_id: int = Field(..., ge=1)


class CustomsJobOut(BaseModel):
    country_id: int
    country_name: Optional[str]
    status: str                            # active (only active jobs are returned)
    enlisted_at: datetime
    seizures: int
    earned: int


class CustomsOfficerParamsOut(BaseModel):
    officer_share: float                   # officers' share of the fine (0..1)
    alert_minutes: int                     # how long a detected caravan waits for «Досмотреть»


class CustomsOfficerViewOut(BaseModel):
    npc_id: int
    country_id: int
    country_name: Optional[str]
    location_id: int
    job: Optional[CustomsJobOut]
    can_enlist: bool
    reason: Optional[str]                  # Russian refusal text when can_enlist is false
    params: CustomsOfficerParamsOut


class CustomsJobWrapOut(BaseModel):
    job: Optional[CustomsJobOut]


class CustomsResignOut(BaseModel):
    ok: bool


# --------------------------------------------------------------------------------------------- admin (A1, A2)

class CustomsPostOut(BaseModel):
    location_id: int
    name: Optional[str]
    is_port: bool


class CustomsCountryOut(BaseModel):
    country_id: int
    name: Optional[str]
    banned_groups: List[str]
    posts: List[CustomsPostOut]


class CustomsGroupOut(BaseModel):
    code: str
    name: str


class CustomsAdminOut(BaseModel):
    countries: List[CustomsCountryOut]
    groups: List[CustomsGroupOut]


# raw payload guard only; the ≤ MAX_BANNED_GROUPS rule (after dedup) is checked in customs_crud with a Russian text
BANS_PAYLOAD_MAX = customs_core.MAX_BANNED_GROUPS * 4


class CustomsBansIn(BaseModel):
    banned_groups: List[str] = Field(default_factory=list, max_items=BANS_PAYLOAD_MAX)


class CustomsInspectIn(BaseModel):
    """C5 body: the officer and whether his free squad joins."""
    character_id: conint(strict=True, ge=1)
    group: bool = False

    class Config:
        extra = Extra.forbid


class CustomsInspectOut(BaseModel):
    raid_id: int
    battle_id: int
