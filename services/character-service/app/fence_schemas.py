"""FEAT-211 3.11 / 3.13 A11-A12: schemas of the fence («Скупщик») settings (Pydantic v1).

Kept apart from ``schemas.py`` (file-disjoint from the parallel raid work). Range checks live in ``fence_crud`` so
the admin gets Russian 400 texts instead of Pydantic's 422 list.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

FENCE_PRICE_PCT_MIN = 1
FENCE_PRICE_PCT_MAX = 100
FENCE_PRICE_PCT_DEFAULT = 40
FENCE_CASH_TARGET_MIN = 0
FENCE_CASH_TARGET_MAX = 10_000_000
FENCE_CASH_TARGET_DEFAULT = 2000
FENCE_MAX_GROUPS = 12          # econ_core.GOODS_GROUPS


class FenceSettingsIn(BaseModel):
    """PUT /characters/admin/npcs/{npc_id}/fence. Empty ``accepted_groups`` = every goods group."""
    is_active: bool = True
    price_pct: int = FENCE_PRICE_PCT_DEFAULT
    accepted_groups: List[str] = Field(default_factory=list, max_items=FENCE_MAX_GROUPS * 2)
    cash_target: int = FENCE_CASH_TARGET_DEFAULT


class FenceSettingsOut(BaseModel):
    npc_id: int
    is_active: bool
    price_pct: int
    accepted_groups: List[str]
    cash_target: int
    cash: int
    region_id: Optional[int] = None
    region_name: Optional[str] = None
    refill_active: bool
