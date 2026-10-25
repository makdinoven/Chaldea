"""Camp backpack (FEAT-178).

A cloak marked `is_backpack`, worn in the cloak slot, holds a few stacks of
consumables the character takes into a dungeon. Its capacity (in stacks) comes
from its rarity. Packed stacks live in `character_backpack`, apart from the bag.

In a dungeon run the bag is closed: of the character's own things only what is
in the backpack can be used (out of battle) or put on the belt. Packing and
unpacking happen outside a run.
"""

from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

import activity_lock
import crud
import models

# Stacks a backpack holds, by rarity (legendary and above are one tier).
CAPACITY_BY_RARITY = {
    "common": 4,
    "rare": 6,
    "epic": 8,
    "legendary": 10,
    "mythical": 10,
    "divine": 10,
    "demonic": 10,
}
PACKABLE_TYPE = "consumable"
CLOAK_SLOT = "cloak"

NOT_PACKABLE = "В походный рюкзак кладутся только расходники"
NO_BACKPACK = "Наденьте походный рюкзак в слот плаща"
NO_ROOM = "В походном рюкзаке нет места"
PACK_IN_RUN = "В подземелье рюкзак не перекладывают — соберите его до входа"
BAG_CLOSED = "В подземелье можно пользоваться только вещами из походного рюкзака"
KEEP_ON_IN_RUN = "В подземелье походный рюкзак не снять"


def _value(v) -> str:
    return getattr(v, "value", v)


def capacity_of(item: Optional[models.Items]) -> int:
    if item is None or not item.is_backpack:
        return 0
    return CAPACITY_BY_RARITY.get(_value(item.item_rarity), CAPACITY_BY_RARITY["common"])


def worn_backpack(db: Session, character_id: int) -> Optional[models.Items]:
    """The backpack in the cloak slot, or None."""
    row = (
        db.query(models.Items)
        .join(models.EquipmentSlot, models.EquipmentSlot.item_id == models.Items.id)
        .filter(models.EquipmentSlot.character_id == character_id, models.EquipmentSlot.slot_type == CLOAK_SLOT)
        .first()
    )
    return row if row is not None and row.is_backpack else None


def rows(db: Session, character_id: int, lock: bool = False) -> List[models.BackpackItem]:
    q = db.query(models.BackpackItem).filter(models.BackpackItem.character_id == character_id)
    if lock:
        q = q.with_for_update()
    return q.order_by(models.BackpackItem.id).all()


def in_dungeon(db: Session, character_id: int) -> bool:
    return activity_lock.get_activity_lock(db, character_id).get("reason") == activity_lock.REASON_DUNGEON


def check_bag_open(db: Session, character_id: int) -> None:
    """The bag itself (not the backpack) is out of reach in a dungeon run."""
    if in_dungeon(db, character_id):
        raise HTTPException(status_code=409, detail=BAG_CLOSED)


def room_for(db: Session, character_id: int, item: models.Items, quantity: int,
             current: Optional[List[models.BackpackItem]] = None) -> bool:
    """Whether `quantity` of `item` fits: onto unfilled stacks of it first, then into free stacks."""
    cap = capacity_of(worn_backpack(db, character_id))
    current = rows(db, character_id) if current is None else current
    max_stack = max(1, item.max_stack_size or 1)
    space = sum(max_stack - r.quantity for r in current if r.item_id == item.id and r.quantity < max_stack)
    left = max(0, quantity - space)
    new_stacks = -(-left // max_stack)
    return len(current) + new_stacks <= cap


def add(db: Session, character_id: int, item: models.Items, quantity: int) -> None:
    """Put `quantity` of `item` into the backpack (409 when it does not fit). Flushes, does not commit."""
    if _value(item.item_type) != PACKABLE_TYPE:
        raise HTTPException(status_code=400, detail=NOT_PACKABLE)
    if worn_backpack(db, character_id) is None:
        raise HTTPException(status_code=409, detail=NO_BACKPACK)
    current = rows(db, character_id, lock=True)
    if not room_for(db, character_id, item, quantity, current):
        raise HTTPException(status_code=409, detail=NO_ROOM)
    max_stack = max(1, item.max_stack_size or 1)
    left = quantity
    for r in current:
        if left <= 0:
            break
        if r.item_id == item.id and r.quantity < max_stack:
            put = min(max_stack - r.quantity, left)
            r.quantity += put
            left -= put
    while left > 0:
        put = min(max_stack, left)
        db.add(models.BackpackItem(character_id=character_id, item_id=item.id, quantity=put))
        left -= put
    db.flush()


def take(db: Session, character_id: int, backpack_item_id: int, quantity: int = 1) -> Tuple[models.BackpackItem, models.Items]:
    """Take `quantity` off one packed stack (404 / 400). Flushes, does not commit."""
    row = (
        db.query(models.BackpackItem)
        .filter(models.BackpackItem.id == backpack_item_id, models.BackpackItem.character_id == character_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Предмета нет в походном рюкзаке")
    if quantity < 1 or row.quantity < quantity:
        raise HTTPException(status_code=400, detail="В рюкзаке столько нет")
    item = db.query(models.Items).filter(models.Items.id == row.item_id).first()
    row.quantity -= quantity
    if row.quantity <= 0:
        db.delete(row)
    db.flush()
    return row, item


def empty_into_bag(db: Session, character_id: int) -> int:
    """Everything packed goes back to the bag (the backpack came off). Returns the stacks moved."""
    packed = rows(db, character_id, lock=True)
    for r in packed:
        crud._add_items_to_inventory(db, character_id, r.item_id, r.quantity)
        db.delete(r)
    db.flush()
    return len(packed)


def leaving_cloak_slot(db: Session, character_id: int, old_item: Optional[models.Items]) -> None:
    """Called before the cloak slot gives up `old_item`: a backpack stays on in a run, else it empties."""
    if old_item is None or not old_item.is_backpack:
        return
    if in_dungeon(db, character_id):
        raise HTTPException(status_code=409, detail=KEEP_ON_IN_RUN)
    empty_into_bag(db, character_id)
