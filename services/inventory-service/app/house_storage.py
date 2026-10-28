"""House storage (FEAT-180).

A house's storage rooms hold stacks of anything from the bag; every built
storage room gives stacks by its level (`house_workshop.STORAGE_STACKS_BY_LEVEL`),
a cellar more (`CELLAR_STACKS_BY_LEVEL`, stage 6a); the house's one storage is
all of them together.
An item keeps its sharpening, gems and wear while it lies here. The house, its owner and the residents' rights
live in locations-service's tables, read here straight from the shared DB:
the owner may put and take, a resident as the owner allowed. Both need the
character standing in the house's location and out of battle.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, validator
from sqlalchemy import text
from sqlalchemy.orm import Session

import backpack
import crud
import house_workshop
import models
import schemas
from auth_http import get_current_user_via_http
# Imported at the end of main.py, after these are defined there.
from main import check_not_in_battle, get_db, verify_character_ownership

router = APIRouter(prefix="/inventory/houses", tags=["house-storage"])

NO_STORAGE = "В доме нет кладовой"
NO_ROOM = "В кладовой нет места"
NOT_HERE = "Дойдите до локации, где стоит дом"
GO_TO_STORAGE = "Сначала перейдите в кладовую или погреб этого дома"
FROZEN = "Дом заморожен за неуплату налога — заплатите налог"


class PutRequest(BaseModel):
    character_id: int
    inventory_item_id: int
    quantity: int = 1

    @validator("quantity")
    def _positive(cls, v):
        if v < 1:
            raise ValueError("Количество — от 1")
        return v


class TakeRequest(BaseModel):
    character_id: int
    storage_item_id: int
    quantity: int = 1

    @validator("quantity")
    def _positive(cls, v):
        if v < 1:
            raise ValueError("Количество — от 1")
        return v


def _rights(db: Session, house_id: int, character_id: int) -> dict:
    """What the character may do with the storage, and where the house stands (404 / 403)."""
    house = db.execute(
        text("SELECT h.owner_character_id, p.location_id, h.status FROM houses h "
             "JOIN house_plots p ON p.id = h.plot_id WHERE h.id = :hid"),
        {"hid": house_id},
    ).fetchone()
    if not house:
        raise HTTPException(status_code=404, detail="Дом не найден")
    if house[0] == character_id:
        can_take = can_put = True
    else:
        resident = db.execute(
            text("SELECT can_take, can_put FROM house_residents WHERE house_id = :hid AND character_id = :cid"),
            {"hid": house_id, "cid": character_id},
        ).fetchone()
        if not resident:
            raise HTTPException(status_code=403, detail="Персонаж не живёт в этом доме")
        can_take, can_put = bool(resident[0]), bool(resident[1])
    location = crud.get_character_location(db, character_id)
    at_house = location is not None and int(location) == int(house[1])
    return {
        "can_take": can_take,
        "can_put": can_put,
        "capacity": house_workshop.storage_capacity(db, house_id),
        "at_house": at_house,
        # Stage 7: putting and taking need the character standing in a storage or cellar of this house.
        "in_storage": at_house and _in_storage(db, house_id, character_id),
        # FEAT-180 stage 4: a house frozen for unpaid tax can only be looked at.
        "frozen": house[2] == "frozen",
    }


def _in_storage(db: Session, house_id: int, character_id: int) -> bool:
    """Whether the character stands in a built storage or cellar of this house (`characters.house_room_id`,
    set by locations-service; the caller has checked that the character is in the house's location)."""
    try:
        row = db.execute(text(
            f"SELECT {house_workshop.ROOM_LEVEL_SQL} FROM characters c JOIN house_rooms r ON r.id = c.house_room_id "
            "WHERE c.id = :cid AND r.house_id = :hid AND r.room_type IN ('storage', 'cellar')"),
            {"cid": character_id, "hid": house_id}).fetchone()
    except Exception:
        return False
    return row is not None and int(row[0] or 0) >= 1


def _check_here(db: Session, rights: dict, character_id: int) -> None:
    if rights["frozen"]:
        raise HTTPException(status_code=409, detail=FROZEN)
    if not rights["capacity"]:
        raise HTTPException(status_code=409, detail=NO_STORAGE)
    if not rights["at_house"]:
        raise HTTPException(status_code=403, detail=NOT_HERE)
    if not rights["in_storage"]:
        raise HTTPException(status_code=403, detail=GO_TO_STORAGE)
    check_not_in_battle(db, character_id, "Во время боя кладовой не пользуются")
    backpack.check_bag_open(db, character_id)


def _rows(db: Session, house_id: int, lock: bool = False) -> List[models.HouseStorageItem]:
    q = db.query(models.HouseStorageItem).filter(models.HouseStorageItem.house_id == house_id)
    if lock:
        q = q.with_for_update()
    return q.order_by(models.HouseStorageItem.id).all()


def _is_plain(row) -> bool:
    """A row without sharpening, gems or wear: it stacks with others of its item."""
    return (
        (row.is_identified is None or bool(row.is_identified))
        and not row.enhancement_points_spent
        and not row.enhancement_bonuses
        and not row.socketed_gems
        and row.current_durability is None
    )


def _state(db: Session, house_id: int, rights: dict) -> dict:
    entries = []
    for row in _rows(db, house_id):
        item = row.item
        if item is None:
            continue
        entries.append({
            "id": row.id, "item_id": item.id, "quantity": row.quantity, "name": item.name,
            "description": item.description, "image_url": item.image,
            "item_type": schemas._enum_value(item.item_type),
            "rarity": schemas._enum_value(item.item_rarity),
            "max_stack_size": item.max_stack_size or 1,
            "is_identified": bool(row.is_identified),
            "enhancement_points_spent": row.enhancement_points_spent or 0,
            "current_durability": row.current_durability,
            "max_durability": item.max_durability or 0,
        })
    return {**rights, "used": len(entries), "items": entries}


@router.get("/{house_id}/storage")
def get_storage(
    house_id: int,
    character_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    verify_character_ownership(db, character_id, current_user.id)
    return _state(db, house_id, _rights(db, house_id, character_id))


@router.post("/{house_id}/storage/put")
def put_into_storage(
    house_id: int,
    req: PutRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    verify_character_ownership(db, req.character_id, current_user.id)
    rights = _rights(db, house_id, req.character_id)
    if not rights["can_put"]:
        raise HTTPException(status_code=403, detail="Хозяин не разрешил класть в кладовую")
    _check_here(db, rights, req.character_id)
    try:
        inv = db.query(models.CharacterInventory).filter(
            models.CharacterInventory.id == req.inventory_item_id,
            models.CharacterInventory.character_id == req.character_id,
        ).with_for_update().first()
        if not inv:
            raise HTTPException(status_code=404, detail="Предмет не найден в инвентаре")
        if inv.quantity < req.quantity:
            raise HTTPException(status_code=400, detail="Недостаточно предметов в инвентаре")
        item = db.query(models.Items).filter(models.Items.id == inv.item_id).first()
        current = _rows(db, house_id, lock=True)
        max_stack = max(1, item.max_stack_size or 1)

        if _is_plain(inv):
            # Onto unfilled plain stacks of the item first, then into free stacks.
            open_stacks = [r for r in current if r.item_id == item.id and _is_plain(r) and r.quantity < max_stack]
            space = sum(max_stack - r.quantity for r in open_stacks)
            new_stacks = -(-max(0, req.quantity - space) // max_stack)
            if len(current) + new_stacks > rights["capacity"]:
                raise HTTPException(status_code=409, detail=NO_ROOM)
            left = req.quantity
            for r in open_stacks:
                put = min(max_stack - r.quantity, left)
                r.quantity += put
                left -= put
            while left > 0:
                put = min(max_stack, left)
                db.add(models.HouseStorageItem(house_id=house_id, item_id=item.id, quantity=put))
                left -= put
        else:
            if len(current) + 1 > rights["capacity"]:
                raise HTTPException(status_code=409, detail=NO_ROOM)
            db.add(models.HouseStorageItem(
                house_id=house_id, item_id=item.id, quantity=req.quantity,
                is_identified=bool(inv.is_identified) if inv.is_identified is not None else True,
                enhancement_points_spent=inv.enhancement_points_spent or 0,
                enhancement_bonuses=inv.enhancement_bonuses, socketed_gems=inv.socketed_gems,
                current_durability=inv.current_durability,
            ))
        inv.quantity -= req.quantity
        if inv.quantity <= 0:
            db.delete(inv)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    return _state(db, house_id, rights)


@router.post("/{house_id}/storage/take")
def take_from_storage(
    house_id: int,
    req: TakeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    verify_character_ownership(db, req.character_id, current_user.id)
    rights = _rights(db, house_id, req.character_id)
    if not rights["can_take"]:
        raise HTTPException(status_code=403, detail="Хозяин не разрешил брать из кладовой")
    _check_here(db, rights, req.character_id)
    try:
        row = db.query(models.HouseStorageItem).filter(
            models.HouseStorageItem.id == req.storage_item_id,
            models.HouseStorageItem.house_id == house_id,
        ).with_for_update().first()
        if not row:
            raise HTTPException(status_code=404, detail="Предмета нет в кладовой")
        if row.quantity < req.quantity:
            raise HTTPException(status_code=400, detail="В кладовой столько нет")
        if _is_plain(row):
            crud._add_items_to_inventory(db, req.character_id, row.item_id, req.quantity)
        else:
            db.add(models.CharacterInventory(
                character_id=req.character_id, item_id=row.item_id, quantity=req.quantity,
                is_identified=row.is_identified, enhancement_points_spent=row.enhancement_points_spent,
                enhancement_bonuses=row.enhancement_bonuses, socketed_gems=row.socketed_gems,
                current_durability=row.current_durability,
            ))
        row.quantity -= req.quantity
        if row.quantity <= 0:
            db.delete(row)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    return _state(db, house_id, rights)
