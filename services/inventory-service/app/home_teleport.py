"""The home teleport scroll (FEAT-180, stage 6b).

A scroll flagged `is_home_teleport` (crafted by the mystic like any recipe
result) carries its reader to a house with a built return circle: one it owns,
or whose circle the owner let it into. character-service performs the move with
the side effects of an admin move (gathering cancelled, intentions expired,
travel cooldown reset, a journal row). The scroll is spent only after the move
succeeded, unless the circle keeps it (`house_workshop.CIRCLE_KEEP_CHANCE` by its
level).
"""

import logging
import random
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

import house_workshop
import models
from auth_http import get_current_user_via_http
from config import settings
# Imported at the end of main.py, after these are defined there.
from main import (_internal_token_headers, check_not_activity_locked, check_not_gathering, check_not_in_battle,
                  get_db, verify_character_ownership)

logger = logging.getLogger("inventory-service")

router = APIRouter(prefix="/inventory", tags=["home-teleport"])

MOVE_TIMEOUT = 15.0
MOVE_FAILED = "Не удалось перенести персонажа — попробуйте ещё раз"


class HomeTeleportRequest(BaseModel):
    inventory_item_id: int
    house_id: int


def keep_roll(chance: float) -> bool:
    """Whether the circle keeps the scroll (monkeypatched in tests)."""
    return chance > 0 and random.random() < chance


def _location_names(db: Session, ids) -> dict:
    ids = sorted({int(i) for i in ids if i is not None})
    if not ids:
        return {}
    try:
        rows = db.execute(text("SELECT id, name FROM Locations WHERE id IN :ids")
                          .bindparams(bindparam("ids", expanding=True)), {"ids": ids}).fetchall()
    except Exception:
        return {}
    return {r[0]: r[1] for r in rows}


def _targets(db: Session, character_id: int) -> list:
    circles = house_workshop.return_circles(db, character_id)
    names = _location_names(db, [c["location_id"] for c in circles])
    for c in circles:
        c["location_name"] = names.get(c["location_id"])
    return circles


async def move_home(character_id: int, location_id: int, house_room_id: Optional[int] = None) -> dict:
    """character-service moves the character (409/400 with its message, 502/503 when unreachable);
    with `house_room_id` (stage 7) it arrives standing in that room of the house."""
    try:
        async with httpx.AsyncClient(timeout=MOVE_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.CHARACTER_SERVICE_URL}/characters/internal/{character_id}/home-teleport",
                json={"location_id": location_id, "house_room_id": house_room_id},
                headers=_internal_token_headers())
    except httpx.HTTPError as e:
        logger.warning(f"Home teleport of character {character_id}: character-service unreachable: {e}")
        raise HTTPException(status_code=503, detail=MOVE_FAILED)
    if resp.status_code == 200:
        return resp.json()
    if resp.status_code in (400, 409):
        try:
            detail = resp.json().get("detail") or MOVE_FAILED
        except ValueError:
            detail = MOVE_FAILED
        raise HTTPException(status_code=resp.status_code, detail=detail)
    logger.warning(f"Home teleport of character {character_id}: character-service answered {resp.status_code}")
    raise HTTPException(status_code=502, detail=MOVE_FAILED)


@router.get("/{character_id}/home-teleport/targets")
def home_teleport_targets(
    character_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Houses the character's home teleport scroll may carry it to."""
    verify_character_ownership(db, character_id, current_user.id)
    return _targets(db, character_id)


@router.post("/{character_id}/home-teleport")
async def use_home_teleport(
    character_id: int,
    req: HomeTeleportRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Reads a home teleport scroll: the character goes to the house's location; the scroll
    is spent unless the return circle keeps it. A failed move spends nothing."""
    verify_character_ownership(db, character_id, current_user.id)
    row = db.query(models.CharacterInventory).filter(
        models.CharacterInventory.id == req.inventory_item_id,
        models.CharacterInventory.character_id == character_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")
    item = db.query(models.Items).filter(models.Items.id == row.item_id).first()
    if item is None or not item.is_home_teleport:
        raise HTTPException(status_code=400, detail="Это не свиток возвращения домой")
    target = next((t for t in _targets(db, character_id) if t["house_id"] == req.house_id), None)
    if target is None:
        raise HTTPException(status_code=403,
                            detail="Свиток не перенесёт в этот дом: нужен построенный круг возвращения, куда вас пустили")
    here = db.execute(text("SELECT current_location_id FROM characters WHERE id = :c"),
                      {"c": character_id}).scalar()
    if here is not None and int(here) == int(target["location_id"]):
        raise HTTPException(status_code=400, detail="Вы уже в локации этого дома")
    check_not_activity_locked(db, character_id)
    check_not_in_battle(db, character_id, "Во время боя свиток не прочесть")
    check_not_gathering(db, character_id, "Во время добычи свиток не прочесть")
    db.rollback()  # no transaction held across the call

    moved = await move_home(character_id, target["location_id"], target.get("room_id"))

    kept = keep_roll(target["keep_chance"])
    if not kept:
        stack = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == req.inventory_item_id,
            models.CharacterInventory.character_id == character_id,
        ).with_for_update().first()
        if stack is None:
            logger.warning(f"Home teleport of character {character_id}: the scroll row vanished before it was spent")
        elif stack.quantity > 1:
            stack.quantity -= 1
        else:
            db.delete(stack)
        db.commit()
    return {"location_id": target["location_id"],
            "location_name": moved.get("location_name") or target["location_name"],
            "house_id": target["house_id"], "house_room_id": target.get("room_id"),
            "scroll_kept": kept}
