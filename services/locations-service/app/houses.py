"""Дома игроков (FEAT-180), stage 1.

Admins lay out plots in city locations, each with a ready house made of
template rooms. A character standing in that location buys the house for gold;
the rooms are copied into the house and the character becomes its owner.

Stage 2: a plot may also be sold empty — the owner builds rooms on it up to
its size. Every room type has levels 1..3; building and upgrading cost gold,
materials from the bag and time (`house_build_costs`, set by admins) and
finish by themselves. A bedroom lets a character sleep (activity locked, rest
multiplied by the bedroom's level); a workshop has a profession and gives that
profession a crafting bonus (inventory-service reads it).

Stage 3: furniture — items of type 'furniture' made for a room type. The owner
places them from the bag into a room (as many as its level) and takes them
back; each adds its item's bonus there (bedroom: sleep multiplier, storage:
stacks, workshop: experience and refining double chance — counted by
inventory-service), a hall's furniture is shown to guests.

Stage 4: a tax every tax period (a game season with the transition after it,
49 real days): 5 % of the plot price plus 50 gold per room level (admin rates).
The purchase period is free; a period left unpaid freezes the house (nothing
but looking and paying), one more seizes it: the plot sells again as it was
laid out and the house stays as an archive with its buildings, furniture,
stored items and posts. The owner names an heir among the residents; when the
owner character is deleted the house passes to the heir, or is seized. A house
without debts can be put up for sale; the buyer takes it with its furniture
and stored items, the residents and the heir are written out. All of this is
settled lazily (`_settle_house`) whenever a house is read or acted on.

Stage 5: the plan. A plot is a grid on up to four layers (first and second
floor, basement, yard); each room stands on a cell of it. A layer allows its
own room types (a cell may narrow them), a layer with a price is bought before
building on it (a second floor), 'extension' cells are bought one by one at the
plot's extension price. What the owner bought stays with the house.

Stage 6a: the generic workshop gave way to six profession rooms (forge,
alchemy lab, kitchen, jewelry, enchanting hall, mystic's study), each serving
its profession (`workshop_profession_id` is set from `PROFESSION_ROOMS`); a
kitchen also makes food last longer (inventory-service). A cellar is a bigger
storage in the basement. A garden, greenhouse or apiary has beds by its level:
anyone let into it plants a seed (an item with seed fields, inventory-service),
and the planter or the owner harvests it once grown (herbalism, through
inventory-service's gathering award). A bath restores a share of health, mana,
energy and stamina once per 24 h per character. Furniture follows a room's
furniture group (`FURNITURE_GROUP`).

Stage 6b: a library — a character reads there (activity locked like sleep, rest
as usual) and, on stopping, gets 1 % to all character experience per full hour
read, up to the library's cap, for 24 h. A shrine gives once per 24 h one
blessing for 24 h (gathering experience, rest or post experience). Both live in
`house_buffs` (one row per source), which inventory-service (experience) and
attributes-service (rest) read. A trophy hall holds elite trophies (items flagged
`is_elite_trophy`), each +1 % battle experience to the owner and the residents
wherever they are (inventory-service counts it). A guest room is for invited
guests (`house_guests`): they enter only the guest rooms and sleep there. A return
circle is the target of the home teleport scroll (inventory-service).

Stage 7: presence. `characters.house_room_id` is the room a character stands in
(enter, walk between rooms, leave — instant). It counts only while that room's
house stands in the character's location, and character-service clears it on
every change of location. Room functions (posts, sleep, bath, beds, library,
shrine; storage and workshop in inventory-service) need the character in that
room; owner management needs only the house's location. Only the owner,
residents, guests and staff see inside a house — everyone else gets its facade.

Rooms are role-play locations with their own posts: writing needs the
character to stand in the house's location, gives experience like an ordinary
post, and never reaches the site-wide activity feed. The owner opens rooms to
every reader or keeps them closed, and lets residents (other characters) into
chosen rooms and the storage. Houses are always a safe zone. The storage's
items live in inventory-service (`house_storage`), which reads the residents'
rights from these tables.
"""

from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

import httpx

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from pydantic import BaseModel, conint, constr, root_validator, validator
from sqlalchemy import bindparam, delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import crud
import models
from auth_http import UserRead, get_current_user_via_http, require_permission
from database import get_db
import math

from config import settings
from episodes import get_viewer

router = APIRouter(prefix="/locations/houses", tags=["houses"])

POSTS_PAGE = 30
MAX_POST_CHARS = 200_000
CHARACTER_SEARCH_LIMIT = 10
MAX_GRID = 6
# Pictures come from photo-service's player-picture upload (the same folder
# episodes use), never from elsewhere.
IMAGE_PATH_MARK = "/episode_images/"
ROOM_TYPES = models.HOUSE_ROOM_TYPES
ROOM_TYPE_LABEL = {
    "hall": "гостиная", "bedroom": "спальня", "storage": "кладовая", "cellar": "погреб", "garden": "огород",
    "greenhouse": "оранжерея", "apiary": "пасека", "bath": "баня", "forge": "кузница",
    "alchemy_lab": "алхимическая лаборатория", "kitchen": "кухня", "jewelry": "ювелирная мастерская",
    "enchanting": "зал зачарования", "study": "кабинет мистика",
    "library": "библиотека", "shrine": "святилище", "trophy_hall": "трофейный зал",
    "guest_room": "гостевая", "return_circle": "круг возвращения",
}

LAYERS = models.HOUSE_LAYERS
LAYER_LABEL = {"floor1": "1 этаж", "floor2": "2 этаж", "basement": "подвал", "yard": "двор"}
# Where each room type may stand; a cell's `allowed_types` narrows it further.
ROOM_LAYERS = {
    "hall": ("floor1", "floor2"),
    "bedroom": ("floor1", "floor2"),
    "storage": ("floor1", "floor2", "basement"),
    "cellar": ("basement",),
    "garden": ("yard",),
    "greenhouse": ("yard",),
    "apiary": ("yard",),
    "bath": ("yard", "floor1"),
    "forge": ("yard", "floor1"),
    "alchemy_lab": ("basement", "floor1", "floor2"),
    "kitchen": ("floor1",),
    "jewelry": ("floor1", "floor2"),
    "enchanting": ("floor1", "floor2", "basement"),
    "study": ("floor1", "floor2"),
    "library": ("floor1", "floor2"),
    "shrine": ("floor1", "floor2", "yard"),
    "trophy_hall": ("floor1", "floor2"),
    "guest_room": ("floor1", "floor2"),
    "return_circle": ("yard", "basement", "floor1"),
}
# Stage 6a: a profession room serves the profession of this slug (inventory `professions.slug`).
PROFESSION_ROOMS = {"forge": "blacksmith", "alchemy_lab": "alchemist", "kitchen": "cook",
                    "jewelry": "jeweler", "enchanting": "enchanter", "study": "scholar"}
# The furniture (items.furniture_room_type) a room takes; rooms not listed take none.
FURNITURE_GROUP = {"hall": "hall", "bedroom": "bedroom", "storage": "storage", "cellar": "storage",
                   "guest_room": "bedroom", **{room: "workshop" for room in PROFESSION_ROOMS}}
STORAGE_ROOMS = ("storage", "cellar")
GARDEN_ROOMS = ("garden", "greenhouse", "apiary")
SEED_PLACE = {"garden": "его сажают в огороде", "greenhouse": "его сажают в оранжерее",
              "apiary": "его ставят на пасеке"}

NOT_HERE = "Дойдите до локации, где стоит дом"
PLOT_KINDS = ("ready", "empty")
MAX_ROOM_LEVEL = 3
# Rest multiplier while asleep in a bedroom of the level.
BEDROOM_SLEEP_FACTOR = {1: 2.0, 2: 2.5, 3: 3.0}
# Mirror inventory-service `house_workshop.STORAGE_STACKS_BY_LEVEL` / `CELLAR_STACKS_BY_LEVEL`
# (demolition check, the house response).
STORAGE_STACKS_BY_LEVEL = {1: 30, 2: 45, 3: 60}
CELLAR_STACKS_BY_LEVEL = {1: 50, 2: 75, 3: 100}
# Stage 6a: beds of a garden / greenhouse / apiary, and what a bath restores (share of the maximum).
GARDEN_BEDS_BY_LEVEL = {1: 4, 2: 8, 3: 12}
BATH_RESTORE_PCT = {1: 0.20, 2: 0.35, 3: 0.50}
BATH_COOLDOWN_HOURS = 24
INVENTORY_UNREACHABLE = "Не удалось связаться с инвентарём — попробуйте ещё раз"
ATTRIBUTES_UNREACHABLE = "Не удалось восстановить силы — попробуйте ещё раз"

# Stage 6b. Rooms one sleeps in (a guest room sleeps like a bedroom of its level, beds add to it).
SLEEP_ROOMS = ("bedroom", "guest_room")
GUEST_ROOMS = ("guest_room",)
TROPHY_HALL = "trophy_hall"
BUFF_HOURS = 24
# Library: 1 % to all character experience per full hour read, capped by the level.
LIBRARY_RATE_PER_HOUR = 0.01
LIBRARY_CAP = {1: 0.05, 2: 0.07, 3: 0.10}
# Shrine: one blessing per 24 h per character, its value by the level.
SHRINE_BONUS = {1: 0.05, 2: 0.10, 3: 0.15}
SHRINE_COOLDOWN_HOURS = 24
SHRINE_BLESSINGS = ("gathering_xp", "regen", "post_xp")
# Trophy hall: elite trophies it holds by level, each +1 % battle experience; at most 15 % in all.
TROPHY_SLOTS = {1: 5, 2: 10, 3: 15}
TROPHY_BONUS_PER_PIECE = 0.01
TROPHY_BONUS_CAP = 0.15
# Return circle: the chance the home teleport scroll is kept (mirror of inventory-service
# `house_workshop.CIRCLE_KEEP_CHANCE`, shown in the house response).
CIRCLE_KEEP_CHANCE = {1: 0.0, 2: 0.15, 3: 0.30}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

def _image(value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return None
    if not value.startswith("https://") or IMAGE_PATH_MARK not in value or len(value) > 512:
        raise ValueError("Картинку нужно загрузить через форму")
    return value


def _room_type(value: str) -> str:
    if value not in ROOM_TYPES:
        raise ValueError("Неизвестный тип комнаты")
    return value


def _layer(value: str) -> str:
    if value not in LAYERS:
        raise ValueError("Неизвестный слой плана")
    return value


def _types_for(layer: str, allowed: Optional[Iterable[str]]) -> List[str]:
    """Room types a cell takes: the layer's, narrowed by the cell's own list."""
    types = [t for t in ROOM_TYPES if layer in ROOM_LAYERS[t]]
    return [t for t in types if t in allowed] if allowed else types


class PlotRoomIn(BaseModel):
    room_type: str
    name: constr(strip_whitespace=True, min_length=1, max_length=120)
    description: constr(strip_whitespace=True, max_length=5000) = ""
    image_url: Optional[str] = None
    layer: str = "floor1"
    x: conint(ge=0, lt=MAX_GRID)
    y: conint(ge=0, lt=MAX_GRID)

    _img = validator("image_url", allow_reuse=True)(_image)
    _type = validator("room_type", allow_reuse=True)(_room_type)
    _lay = validator("layer", allow_reuse=True)(_layer)


class PlotLayerIn(BaseModel):
    layer: str
    # None or 0: open from the start; otherwise the owner buys the layer.
    unlock_price: Optional[conint(ge=0, le=1_000_000_000)] = None

    _lay = validator("layer", allow_reuse=True)(_layer)


class PlotCellIn(BaseModel):
    layer: str
    x: conint(ge=0, lt=MAX_GRID)
    y: conint(ge=0, lt=MAX_GRID)
    kind: str = "open"
    allowed_types: List[str] = []

    _lay = validator("layer", allow_reuse=True)(_layer)

    @validator("kind")
    def _kind(cls, v):
        if v not in ("open", "extension"):
            raise ValueError("Клетка бывает открытой или пристройкой")
        return v

    @validator("allowed_types")
    def _allowed(cls, v, values):
        if len(set(v)) != len(v):
            raise ValueError("Типы комнат в клетке повторяются")
        for t in v:
            _room_type(t)
            if values.get("layer") and values["layer"] not in ROOM_LAYERS[t]:
                raise ValueError(f"Комнату «{ROOM_TYPE_LABEL[t]}» не ставят: {LAYER_LABEL[values['layer']]}")
        return v


class PlotIn(BaseModel):
    location_id: int
    name: constr(strip_whitespace=True, min_length=1, max_length=120)
    description: constr(strip_whitespace=True, max_length=5000) = ""
    image_url: Optional[str] = None
    price: conint(ge=0, le=1_000_000_000)
    map_x: Optional[float] = None
    map_y: Optional[float] = None
    kind: str = "ready"
    grid_w: conint(ge=1, le=MAX_GRID)
    grid_h: conint(ge=1, le=MAX_GRID)
    extension_price: Optional[conint(ge=0, le=1_000_000_000)] = None
    layers: List[PlotLayerIn]
    cells: List[PlotCellIn]
    rooms: List[PlotRoomIn] = []

    _img = validator("image_url", allow_reuse=True)(_image)

    @validator("kind")
    def _kind(cls, v):
        if v not in PLOT_KINDS:
            raise ValueError("Неизвестный вид участка")
        return v

    @root_validator(skip_on_failure=True)
    def _plan(cls, values):
        layers = {l.layer: l for l in values["layers"]}
        if len(layers) != len(values["layers"]):
            raise ValueError("Слой плана указан дважды")
        if "floor1" not in layers or layers["floor1"].unlock_price:
            raise ValueError("Первый этаж есть у каждого дома и открыт сразу")
        cells = {}
        for c in values["cells"]:
            if c.layer not in layers:
                raise ValueError(f"Клетка на слое, которого нет в плане: {LAYER_LABEL[c.layer]}")
            if c.x >= values["grid_w"] or c.y >= values["grid_h"]:
                raise ValueError("Клетка за пределами сетки")
            if (c.layer, c.x, c.y) in cells:
                raise ValueError("Клетка указана дважды")
            cells[(c.layer, c.x, c.y)] = c
        if any(c.kind == "extension" for c in cells.values()) and values.get("extension_price") is None:
            raise ValueError("Укажите цену пристройки — на плане есть клетки-пристройки")
        if not any(c.kind == "open" and not layers[c.layer].unlock_price for c in cells.values()):
            raise ValueError("Нужна хотя бы одна открытая клетка на открытом слое")
        rooms = values["rooms"]
        if values["kind"] == "empty":
            if rooms:
                raise ValueError("На пустом участке комнат нет — их строит хозяин")
            return values
        if not rooms:
            raise ValueError("В доме должна быть хотя бы одна комната")
        taken = set()
        for r in rooms:
            key = (r.layer, r.x, r.y)
            cell = cells.get(key)
            if cell is None or cell.kind != "open" or layers[r.layer].unlock_price:
                raise ValueError(f"Комната «{r.name}» должна стоять на открытой клетке открытого слоя")
            if key in taken:
                raise ValueError("Две комнаты в одной клетке")
            if r.room_type not in _types_for(r.layer, cell.allowed_types):
                raise ValueError(f"Комнату «{r.name}» нельзя поставить в эту клетку")
            taken.add(key)
        return values


class CharacterIn(BaseModel):
    character_id: int


class HouseIn(CharacterIn):
    name: constr(strip_whitespace=True, min_length=1, max_length=120)
    description: constr(strip_whitespace=True, max_length=5000) = ""
    image_url: Optional[str] = None

    _img = validator("image_url", allow_reuse=True)(_image)


class RoomIn(CharacterIn):
    name: constr(strip_whitespace=True, min_length=1, max_length=120)
    description: constr(strip_whitespace=True, max_length=5000) = ""
    image_url: Optional[str] = None
    is_open: bool = False
    # Stage 6a: ignored — a profession room's profession follows its type.
    workshop_profession_id: Optional[int] = None

    _img = validator("image_url", allow_reuse=True)(_image)


class ResidentAddIn(CharacterIn):
    resident_character_id: int


class ResidentRightsIn(CharacterIn):
    room_ids: List[int] = []
    can_take: bool = False
    can_put: bool = True


class PostIn(CharacterIn):
    content: str


class PostEditIn(BaseModel):
    content: str


class HeirIn(CharacterIn):
    heir_character_id: Optional[int] = None


class SaleIn(CharacterIn):
    price: conint(ge=1, le=1_000_000_000)


class TaxSettingsIn(BaseModel):
    tax_price_pct: float
    tax_per_room_level: conint(ge=0, le=1_000_000)

    @validator("tax_price_pct")
    def _pct(cls, v):
        if not 0 <= v <= 100:
            raise ValueError("Процент — от 0 до 100")
        return v


class FurnitureIn(CharacterIn):
    inventory_item_id: int


class PlantIn(CharacterIn):
    inventory_item_id: int
    bed_no: Optional[conint(ge=1, le=100)] = None


class HarvestIn(CharacterIn):
    bed_no: conint(ge=1, le=100)


class PrayIn(CharacterIn):
    blessing: str

    @validator("blessing")
    def _blessing(cls, v):
        if v not in SHRINE_BLESSINGS:
            raise ValueError("Неизвестное благословение")
        return v


class GuestIn(CharacterIn):
    guest_character_id: int


class BuildIn(CharacterIn):
    room_type: str
    cell_id: int
    name: constr(strip_whitespace=True, min_length=1, max_length=120)

    _type = validator("room_type", allow_reuse=True)(_room_type)


class CostItemIn(BaseModel):
    item_id: int
    quantity: conint(ge=1, le=10_000)


class CostIn(BaseModel):
    gold: conint(ge=0, le=1_000_000_000)
    build_hours: conint(ge=0, le=24 * 365)
    items: List[CostItemIn] = []


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def _is_admin(user: Optional[UserRead]) -> bool:
    return bool(user) and user.role == "admin"


def _is_staff(user: Optional[UserRead]) -> bool:
    return bool(user) and user.role in ("admin", "moderator")


async def _characters(db: AsyncSession, ids: Iterable) -> Dict[int, dict]:
    ids = sorted({int(i) for i in ids if i is not None})
    if not ids:
        return {}
    rows = await db.execute(
        text("SELECT id, name, avatar, user_id FROM characters WHERE id IN :ids")
        .bindparams(bindparam("ids", expanding=True)),
        {"ids": ids},
    )
    return {r[0]: {"id": r[0], "name": r[1], "avatar": r[2], "user_id": r[3]} for r in rows.fetchall()}


async def _user_character_ids(db: AsyncSession, user: Optional[UserRead]) -> List[int]:
    if not user:
        return []
    rows = await db.execute(text("SELECT id FROM characters WHERE user_id = :uid"), {"uid": user.id})
    return [r[0] for r in rows.fetchall()]


async def _own_character(db: AsyncSession, character_id: int, user: UserRead) -> dict:
    """The user's character with its current location, or 403/404."""
    row = (await db.execute(
        text("SELECT user_id, current_location_id FROM characters WHERE id = :cid"),
        {"cid": character_id},
    )).fetchone()
    if not row:
        raise HTTPException(404, "Персонаж не найден")
    if row[0] != user.id:
        raise HTTPException(403, "Это не ваш персонаж")
    return {"id": character_id, "location_id": row[1]}


async def _house(db: AsyncSession, house_id: int) -> models.House:
    """The house after settling its tax and owner; a seized one is gone for players (404)."""
    house = await db.get(models.House, house_id)
    if not house:
        raise HTTPException(404, "Дом не найден")
    await _settle_house(db, house)
    if house.status == "seized":
        raise HTTPException(404, "Дом изъят городом")
    return house


def _require_active(house: models.House) -> None:
    if house.status == "frozen":
        raise HTTPException(409, "Дом заморожен за неуплату налога — заплатите налог")


async def _plot(db: AsyncSession, plot_id: int) -> models.HousePlot:
    plot = await db.get(models.HousePlot, plot_id)
    if not plot:
        raise HTTPException(404, "Участок не найден")
    return plot


async def _room(db: AsyncSession, room_id: int) -> models.HouseRoom:
    room = await db.get(models.HouseRoom, room_id)
    if not room:
        raise HTTPException(404, "Комната не найдена")
    return room


async def _owned_house(db: AsyncSession, house_id: int, character_id: int, user: UserRead) -> models.House:
    await _own_character(db, character_id, user)
    house = await _house(db, house_id)
    if house.owner_character_id != character_id:
        raise HTTPException(403, "Это может только хозяин дома")
    return house


async def _residents(db: AsyncSession, house_id: int) -> List[models.HouseResident]:
    return (await db.execute(
        select(models.HouseResident).where(models.HouseResident.house_id == house_id)
        .order_by(models.HouseResident.id)
    )).scalars().all()


async def _resident_rooms(db: AsyncSession, resident_ids: List[int]) -> Dict[int, List[int]]:
    if not resident_ids:
        return {}
    rows = (await db.execute(
        select(models.HouseResidentRoom).where(models.HouseResidentRoom.resident_id.in_(resident_ids))
    )).scalars().all()
    out: Dict[int, List[int]] = {}
    for r in rows:
        out.setdefault(r.resident_id, []).append(r.room_id)
    return out


async def _room_writers(db: AsyncSession, house: models.House, room_id: int,
                        room_type: Optional[str] = None) -> List[int]:
    """Characters who may enter and write in a room: the owner and residents let in;
    in a guest room (pass its `room_type`) also the house's guests."""
    rows = await db.execute(
        select(models.HouseResident.character_id)
        .join(models.HouseResidentRoom, models.HouseResidentRoom.resident_id == models.HouseResident.id)
        .where(models.HouseResident.house_id == house.id, models.HouseResidentRoom.room_id == room_id)
    )
    writers = [house.owner_character_id, *[r[0] for r in rows.fetchall()]]
    if room_type in GUEST_ROOMS:
        writers += await _guest_ids(db, house.id)
    return writers


async def _guest_ids(db: AsyncSession, house_id: int) -> List[int]:
    return list((await db.execute(select(models.HouseGuest.character_id).where(
        models.HouseGuest.house_id == house_id).order_by(models.HouseGuest.id))).scalars().all())


async def _region_of_location(db: AsyncSession, location_id: int) -> Optional[int]:
    """The region a location lies in: its own, its district's, or its parent's."""
    seen = set()
    while location_id and location_id not in seen:
        seen.add(location_id)
        loc = await db.get(models.Location, location_id)
        if not loc:
            return None
        if loc.region_id:
            return loc.region_id
        if loc.district_id:
            district = await db.get(models.District, loc.district_id)
            if district:
                return district.region_id
        location_id = loc.parent_id
    return None


async def _location_names(db: AsyncSession, ids: Iterable) -> Dict[int, str]:
    ids = sorted({int(i) for i in ids if i is not None})
    if not ids:
        return {}
    rows = await db.execute(select(models.Location.id, models.Location.name).where(models.Location.id.in_(ids)))
    return {r[0]: r[1] for r in rows.fetchall()}


def _plot_out(plot: models.HousePlot, house: Optional[models.House], chars: Dict[int, dict],
              locations: Dict[int, str], room_count: int, cells: dict) -> dict:
    return {
        "id": plot.id,
        "location_id": plot.location_id,
        "location_name": locations.get(plot.location_id),
        "region_id": plot.region_id,
        "name": plot.name,
        "description": plot.description,
        "image_url": plot.image_url,
        "price": plot.price,
        "kind": plot.kind,
        "room_count": room_count,
        # Places for rooms right after purchase, and with everything bought.
        "cells_open": cells.get("open", 0),
        "cells_total": cells.get("total", 0),
        "map_x": plot.map_x,
        "map_y": plot.map_y,
        "house": None if house is None else {
            "id": house.id,
            "name": house.name,
            "image_url": house.image_url,
            "owner": chars.get(house.owner_character_id),
            "status": house.status,
            "sale_price": house.sale_price,
        },
    }


async def _plots_out(db: AsyncSession, plots: List[models.HousePlot]) -> List[dict]:
    if not plots:
        return []
    ids = [p.id for p in plots]
    houses = {}
    for h in (await db.execute(select(models.House).where(models.House.plot_id.in_(ids)))).scalars().all():
        await _settle_house(db, h)
        if h.status != "seized":
            houses[h.plot_id] = h
    template_counts = dict((await db.execute(
        select(models.HousePlotRoom.plot_id, func.count()).where(models.HousePlotRoom.plot_id.in_(ids))
        .group_by(models.HousePlotRoom.plot_id))).all())
    chars = await _characters(db, [h.owner_character_id for h in houses.values()])
    locations = await _location_names(db, [p.location_id for p in plots])
    cells = await _cell_counts(db, ids)
    return [_plot_out(p, houses.get(p.id), chars, locations, template_counts.get(p.id, 0), cells.get(p.id, {}))
            for p in plots]


async def _cell_counts(db: AsyncSession, plot_ids: List[int]) -> Dict[int, dict]:
    rows = (await db.execute(
        select(models.HousePlotCell.plot_id, models.HousePlotCell.kind, models.HousePlotLayer.unlock_price)
        .join(models.HousePlotLayer, (models.HousePlotLayer.plot_id == models.HousePlotCell.plot_id)
              & (models.HousePlotLayer.layer == models.HousePlotCell.layer))
        .where(models.HousePlotCell.plot_id.in_(plot_ids)))).all()
    out: Dict[int, dict] = {}
    for plot_id, kind, unlock_price in rows:
        c = out.setdefault(plot_id, {"open": 0, "total": 0})
        c["total"] += 1
        if kind == "open" and not unlock_price:
            c["open"] += 1
    return out


async def _plan(db: AsyncSession, plot: models.HousePlot, house: Optional[models.House] = None,
                rooms: Optional[List[models.HouseRoom]] = None) -> dict:
    """The plot's plan; with a house, what of it the owner has and which room stands where."""
    layers = (await db.execute(select(models.HousePlotLayer).where(models.HousePlotLayer.plot_id == plot.id)))\
        .scalars().all()
    cells = (await db.execute(select(models.HousePlotCell).where(models.HousePlotCell.plot_id == plot.id)
                              .order_by(models.HousePlotCell.layer, models.HousePlotCell.y,
                                        models.HousePlotCell.x))).scalars().all()
    bought_layers, bought_cells, by_cell = set(), set(), {}
    if house is not None:
        bought_layers = set((await db.execute(select(models.HouseLayerUnlock.layer).where(
            models.HouseLayerUnlock.house_id == house.id))).scalars().all())
        bought_cells = set((await db.execute(select(models.HouseCellUnlock.cell_id).where(
            models.HouseCellUnlock.house_id == house.id))).scalars().all())
        by_cell = {r.cell_id: r.id for r in rooms or [] if r.cell_id}
    open_layers = {l.layer for l in layers if not l.unlock_price or l.layer in bought_layers}
    order = {name: i for i, name in enumerate(LAYERS)}
    return {
        "width": plot.grid_w,
        "height": plot.grid_h,
        "extension_price": plot.extension_price,
        "layers": [{"layer": l.layer, "label": LAYER_LABEL[l.layer], "unlock_price": l.unlock_price or None,
                    "unlocked": l.layer in open_layers}
                   for l in sorted(layers, key=lambda l: order[l.layer])],
        "cells": [{
            "id": c.id, "layer": c.layer, "x": c.x, "y": c.y, "kind": c.kind,
            "allowed_types": _types_for(c.layer, _split(c.allowed_types)),
            "unlocked": c.layer in open_layers and (c.kind == "open" or c.id in bought_cells),
            "room_id": by_cell.get(c.id),
        } for c in cells],
    }


def _split(value: Optional[str]) -> List[str]:
    return [t for t in (value or "").split(",") if t]


# ---------------------------------------------------------------------------
# Plots: where houses stand
# ---------------------------------------------------------------------------

@router.get("/by-location/{location_id}")
async def plots_at_location(location_id: int, db: AsyncSession = Depends(get_db)):
    plots = (await db.execute(
        select(models.HousePlot).where(models.HousePlot.location_id == location_id)
        .order_by(models.HousePlot.id))).scalars().all()
    return await _plots_out(db, plots)


@router.get("/by-region/{region_id}")
async def plots_in_region(region_id: int, db: AsyncSession = Depends(get_db)):
    """Plots with a point on the region map."""
    plots = (await db.execute(
        select(models.HousePlot).where(
            models.HousePlot.region_id == region_id,
            models.HousePlot.map_x.isnot(None), models.HousePlot.map_y.isnot(None),
        ).order_by(models.HousePlot.id))).scalars().all()
    return await _plots_out(db, plots)


@router.get("/plots/{plot_id}")
async def get_plot(plot_id: int, db: AsyncSession = Depends(get_db)):
    plot = await _plot(db, plot_id)
    out = (await _plots_out(db, [plot]))[0]
    rooms = (await db.execute(
        select(models.HousePlotRoom).where(models.HousePlotRoom.plot_id == plot_id)
        .order_by(models.HousePlotRoom.sort_order, models.HousePlotRoom.id))).scalars().all()
    out["rooms"] = [{"room_type": r.room_type, "name": r.name, "description": r.description,
                     "image_url": r.image_url, "cell_id": r.cell_id} for r in rooms]
    out["plan"] = await _plan(db, plot)
    out["grid_w"], out["grid_h"], out["extension_price"] = plot.grid_w, plot.grid_h, plot.extension_price
    return out


@router.post("/plots/{plot_id}/buy")
async def buy_house(
    plot_id: int,
    body: CharacterIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    from main import check_not_activity_locked, check_not_in_battle

    character = await _own_character(db, body.character_id, user)
    plot = await _plot(db, plot_id)
    if character["location_id"] is None or int(character["location_id"]) != plot.location_id:
        raise HTTPException(400, "Дом покупают на месте — дойдите до его локации")
    await check_not_activity_locked(db, body.character_id)
    await check_not_in_battle(db, body.character_id, "Во время боя дом не купить")
    standing = (await db.execute(select(models.House).where(models.House.plot_id == plot_id))).scalar_one_or_none()
    if standing is not None:
        await _settle_house(db, standing)  # an overdue house leaves the plot here
        if standing.status != "seized":
            raise HTTPException(409, "Этот дом уже куплен")
    templates = (await db.execute(
        select(models.HousePlotRoom).where(models.HousePlotRoom.plot_id == plot_id)
        .order_by(models.HousePlotRoom.sort_order, models.HousePlotRoom.id))).scalars().all()

    house = models.House(plot_id=plot.id, owner_character_id=body.character_id, name=plot.name,
                         description=plot.description, image_url=plot.image_url,
                         tax_paid_through=(await _tax_period(db))["period"])
    db.add(house)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Этот дом уже куплен")
    professions = await _profession_ids(db)
    for i, t in enumerate(templates):
        db.add(models.HouseRoom(house_id=house.id, room_type=t.room_type, name=t.name,
                                description=t.description, image_url=t.image_url,
                                is_open=t.room_type == "hall", sort_order=i, cell_id=t.cell_id,
                                workshop_profession_id=professions.get(t.room_type)))
    await db.flush()
    house_id = house.id
    # FEAT-181: the payment goes to the plot's region treasury in the same transaction as the
    # house; without enough gold nothing is committed and the house stays for sale.
    balance = await _charge(db, body.character_id, plot.price, plot, "house_purchase",
                            {"plot_id": plot.id, "house_id": house_id})
    await db.commit()
    return {"house_id": house_id, "gold": balance}


# ---------------------------------------------------------------------------
# Houses
# ---------------------------------------------------------------------------

@router.get("/my")
async def my_houses(db: AsyncSession = Depends(get_db), user: UserRead = Depends(get_current_user_via_http)):
    """Houses the user's characters own, live in or are guests of (status owner / resident / guest)."""
    char_ids = await _user_character_ids(db, user)
    if not char_ids:
        return []
    owned = (await db.execute(select(models.House).where(models.House.owner_character_id.in_(char_ids)))).scalars().all()
    lived = (await db.execute(
        select(models.House, models.HouseResident.character_id)
        .join(models.HouseResident, models.HouseResident.house_id == models.House.id)
        .where(models.HouseResident.character_id.in_(char_ids)))).all()
    visiting = (await db.execute(
        select(models.House, models.HouseGuest.character_id)
        .join(models.HouseGuest, models.HouseGuest.house_id == models.House.id)
        .where(models.HouseGuest.character_id.in_(char_ids)))).all()
    entries = ([(h, h.owner_character_id, "owner") for h in owned] + [(h, cid, "resident") for h, cid in lived]
               + [(h, cid, "guest") for h, cid in visiting])
    for h, _, _ in entries:
        await _settle_house(db, h)
    entries = [(h, cid, st) for h, cid, st in entries if h.status != "seized"
               and (st != "owner" or h.owner_character_id in char_ids)]
    plots = {p.id: p for p in (await db.execute(
        select(models.HousePlot).where(models.HousePlot.id.in_([h.plot_id for h, _, _ in entries] or [0])))).scalars().all()}
    chars = await _characters(db, [cid for _, cid, _ in entries])
    locations = await _location_names(db, [p.location_id for p in plots.values()])
    return [{
        "id": h.id, "name": h.name, "image_url": h.image_url, "status": status,
        "character": chars.get(cid),
        "location_id": plots[h.plot_id].location_id if h.plot_id in plots else None,
        "location_name": locations.get(plots[h.plot_id].location_id) if h.plot_id in plots else None,
    } for h, cid, status in entries]


@router.get("/buffs")
async def my_buffs(
    character_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """The character's active house blessings (library, shrine) and its trophy bonus."""
    await _own_character(db, character_id, user)
    now = await _db_now(db)
    return {"buffs": (await _buffs(db, [character_id], now)).get(character_id, []),
            "trophy_bonus": (await _trophy_bonus(db, [character_id], now)).get(character_id, 0.0)}


@router.get("/character-search")
async def character_search(
    q: str = Query(..., min_length=2, max_length=50),
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Player characters by name, to let one into a house."""
    like = q.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    rows = await db.execute(
        text("SELECT id, name, avatar FROM characters WHERE is_npc = 0 AND user_id IS NOT NULL "
             "AND name LIKE :q ESCAPE '!' ORDER BY name LIMIT :n"),
        {"q": f"%{like}%", "n": CHARACTER_SEARCH_LIMIT},
    )
    return [{"id": r[0], "name": r[1], "avatar": r[2]} for r in rows.fetchall()]


@router.get("/build-costs")
async def build_costs(db: AsyncSession = Depends(get_db)):
    costs = (await db.execute(select(models.HouseBuildCost).order_by(
        models.HouseBuildCost.room_type, models.HouseBuildCost.level))).scalars().all()
    items = (await db.execute(select(models.HouseBuildCostItem)
                              .order_by(models.HouseBuildCostItem.id))).scalars().all()
    names = await _item_names(db, [i.item_id for i in items])
    by_cost: Dict[int, list] = {}
    for i in items:
        by_cost.setdefault(i.cost_id, []).append({
            "item_id": i.item_id, "quantity": i.quantity,
            "name": names.get(i.item_id, {}).get("name"), "image": names.get(i.item_id, {}).get("image"),
        })
    return [{"room_type": c.room_type, "level": c.level, "gold": c.gold, "build_hours": c.build_hours,
             "items": by_cost.get(c.id, [])} for c in costs]


@router.get("/market")
async def market(db: AsyncSession = Depends(get_db)):
    """Houses up for sale, with what the buyer takes along."""
    houses = (await db.execute(select(models.House).where(models.House.sale_price.isnot(None))
                               .order_by(models.House.listed_at.desc()))).scalars().all()
    out = []
    for h in houses:
        await _settle_house(db, h)
        if h.status != "active" or h.sale_price is None:
            continue
        plot = await _plot(db, h.plot_id)
        rooms = await _rooms_of(db, h.id)
        furniture = await _furniture(db, [r.id for r in rooms])
        stored = await _stored_stacks(db, h.id)
        out.append({
            "id": h.id, "name": h.name, "image_url": h.image_url, "price": h.sale_price,
            "listed_at": h.listed_at, "location_id": plot.location_id,
            "location_name": (await _location_names(db, [plot.location_id])).get(plot.location_id),
            "owner": (await _characters(db, [h.owner_character_id])).get(h.owner_character_id),
            "cells": _cells_summary(await _plan(db, plot, h, rooms)),
            "rooms": [{"room_type": r.room_type, "name": r.name, "level": r.level} for r in rooms],
            "furniture_count": sum(len(v) for v in furniture.values()),
            "stored_stacks": stored,
            "tax_per_season": await _tax_amount(db, h, plot),
        })
    return out


def _cells_summary(plan: dict) -> dict:
    """Places the owner has, how many are taken, and how many more could be bought."""
    cells = plan["cells"]
    return {"usable": sum(c["unlocked"] for c in cells), "taken": sum(bool(c["room_id"]) for c in cells),
            "total": len(cells)}


@router.get("/{house_id}")
async def get_house(
    house_id: int,
    db: AsyncSession = Depends(get_db),
    user: Optional[UserRead] = Depends(get_viewer),
):
    house = await _house(db, house_id)
    plot = await _plot(db, house.plot_id)
    await _settle_rooms(db, house_id)
    rooms = await _rooms_of(db, house_id)
    residents = await _residents(db, house_id)
    resident_rooms = await _resident_rooms(db, [r.id for r in residents])
    post_counts = dict((await db.execute(
        select(models.HousePost.room_id, func.count())
        .where(models.HousePost.room_id.in_([r.id for r in rooms] or [0]))
        .group_by(models.HousePost.room_id))).all())

    my_chars = set(await _user_character_ids(db, user))
    chars = await _characters(db, [house.owner_character_id, *[r.character_id for r in residents]])
    is_owner = house.owner_character_id in my_chars
    my_residents = [r for r in residents if r.character_id in my_chars]
    my_rooms = {room_id for r in my_residents for room_id in resident_rooms.get(r.id, [])}
    guests = (await db.execute(select(models.HouseGuest).where(models.HouseGuest.house_id == house_id)
                               .order_by(models.HouseGuest.id))).scalars().all()
    my_guests = [g for g in guests if g.character_id in my_chars]
    guest_room_ids = [r.id for r in rooms if r.room_type in GUEST_ROOMS]
    guest_chars = await _characters(db, [g.character_id for g in guests])
    chars.update(guest_chars)
    if my_guests:
        my_rooms |= set(guest_room_ids)
    locations = await _location_names(db, [plot.location_id])
    # Stage 7: only the owner, residents and guests (and staff, for moderation) see inside.
    member = is_owner or bool(my_residents) or bool(my_guests)
    if not member and not _is_staff(user):
        return _exterior(house, plot, chars, locations)

    def can_enter(room: models.HouseRoom) -> bool:
        return is_owner or room.id in my_rooms

    def can_read(room: models.HouseRoom) -> bool:
        # An open room is read by everyone let into the house, a closed one only by those let into it.
        return _is_staff(user) or can_enter(room) or (room.is_open and member)

    # The characters through which the viewer acts here, with what each may do.
    acting = []
    if is_owner:
        acting.append({"character": chars.get(house.owner_character_id), "is_owner": True,
                       "room_ids": [r.id for r in rooms], "can_take": True, "can_put": True})
    for r in my_residents:
        acting.append({"character": chars.get(r.character_id), "is_owner": False,
                       "room_ids": resident_rooms.get(r.id, []), "can_take": r.can_take, "can_put": r.can_put})
    for a in acting:
        a["is_guest"] = False
    for g in my_guests:
        if g.character_id == house.owner_character_id or any(r.character_id == g.character_id for r in my_residents):
            continue
        acting.append({"character": chars.get(g.character_id), "is_owner": False, "is_guest": True,
                       "room_ids": guest_room_ids, "can_take": False, "can_put": False})
    furniture = await _furniture(db, [r.id for r in rooms])
    acting_ids = [a["character"]["id"] for a in acting if a["character"]]
    states = await _character_states(db, acting_ids)
    room_ids = {r.id for r in rooms}
    whereabouts = await _presence(db, acting_ids)
    for cid, room_id in whereabouts.items():
        if room_id in room_ids:
            states.setdefault(cid, {})["room_id"] = room_id
    present = await _present_in(db, room_ids)
    now = await _db_now(db)
    baths = await _bath_next(db, acting_ids, now)
    prayers = await _pray_next(db, acting_ids, now)
    buffs = await _buffs(db, acting_ids, now)
    trophies = await _trophy_bonus(db, acting_ids, now)
    for a in acting:
        if a["character"]:
            cid = a["character"]["id"]
            a["room_id"] = None  # the room of this house the character stands in now
            a.update(states.get(cid, {}))
            a["bath_next_at"] = baths.get(cid)
            a["pray_next_at"] = prayers.get(cid)
            a["buffs"] = buffs.get(cid, [])
            a["trophy_bonus"] = 0.0 if a["is_guest"] else trophies.get(cid, 0.0)
    beds = await _beds(db, [r.id for r in rooms if r.room_type in GARDEN_ROOMS])

    out = {
        "id": house.id,
        "name": house.name,
        "description": house.description,
        "image_url": house.image_url,
        "plot_id": plot.id,
        "plot_kind": plot.kind,
        "plan": await _plan(db, plot, house, rooms),
        "status": house.status,
        "tax": await _tax_state(db, house, plot),
        "heir": chars.get(house.heir_character_id) if house.heir_character_id else None,
        "sale_price": house.sale_price,
        "location_id": plot.location_id,
        "location_name": locations.get(plot.location_id),
        "owner": chars.get(house.owner_character_id),
        "is_owner": is_owner,
        "can_view_inside": True,
        "acting": acting,
        # Stage 6b: what this house's trophy halls give its owner and residents (a fraction).
        "trophy_bonus": _house_trophy_total(rooms, await _trophy_counts(db, [r.id for r in rooms]))
        if house.status == "active" else 0.0,
        "rooms": [{
            "id": r.id, "room_type": r.room_type, "name": r.name, "description": r.description,
            "image_url": r.image_url, "is_open": r.is_open, "posts_count": post_counts.get(r.id, 0),
            "cell_id": r.cell_id,
            "can_enter": can_enter(r), "can_read": can_read(r),
            "present": present.get(r.id, []),
            "level": r.level, "upgrade_to_level": r.upgrade_to_level,
            "upgrade_complete_at": r.upgrade_complete_at, "workshop_profession_id": r.workshop_profession_id,
            "sleep_factor": _sleep_factor(r, furniture.get(r.id, [])) if r.room_type in SLEEP_ROOMS else None,
            "furniture": furniture.get(r.id, []),
            "furniture_slots": _furniture_slots(r),
            "library_cap": LIBRARY_CAP.get(r.level) if r.room_type == "library" else None,
            "shrine_bonus": SHRINE_BONUS.get(r.level) if r.room_type == "shrine" else None,
            "trophy_slots": TROPHY_SLOTS.get(r.level, 0) if r.room_type == TROPHY_HALL else None,
            "circle_keep_chance": CIRCLE_KEEP_CHANCE.get(r.level) if r.room_type == "return_circle" else None,
            "furniture_group": FURNITURE_GROUP.get(r.room_type),
            "profession_slug": PROFESSION_ROOMS.get(r.room_type),
            "storage_stacks": _room_stacks(r, furniture.get(r.id, [])) if r.room_type in STORAGE_ROOMS else None,
            **_beds_view(r, beds.get(r.id, []), now),
        } for r in rooms],
        "residents": [{
            "id": r.id, "character": chars.get(r.character_id), "room_ids": resident_rooms.get(r.id, []),
            "can_take": r.can_take, "can_put": r.can_put,
        } for r in residents] if is_owner or my_residents or _is_staff(user) else [],
        "guests": [{"character": guest_chars.get(g.character_id), "invited_at": g.invited_at} for g in guests]
        if is_owner or my_residents or _is_staff(user) else [],
    }
    await _fill_beds(db, out["rooms"])
    return out


def _exterior(house: models.House, plot: models.HousePlot, chars: Dict[int, dict],
              locations: Dict[int, str]) -> dict:
    """What an outsider sees of a house: the facade, where it stands, whose it is and its sale price.
    The keys of the full answer stay, empty, so a client reads both shapes alike."""
    return {
        "id": house.id, "name": house.name, "description": house.description, "image_url": house.image_url,
        "plot_id": plot.id, "plot_kind": plot.kind, "status": house.status, "sale_price": house.sale_price,
        "location_id": plot.location_id, "location_name": locations.get(plot.location_id),
        "owner": chars.get(house.owner_character_id), "is_owner": False, "can_view_inside": False,
        "plan": None, "tax": None, "heir": None, "trophy_bonus": None,
        "acting": [], "rooms": [], "residents": [], "guests": [],
    }


@router.put("/{house_id}")
async def update_house(
    house_id: int,
    body: HouseIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    house = await _owned_house(db, house_id, body.character_id, user)
    house.name, house.description, house.image_url = body.name, body.description, body.image_url
    await db.commit()
    return {"ok": True}


@router.put("/{house_id}/rooms/{room_id}")
async def update_room(
    house_id: int,
    room_id: int,
    body: RoomIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    await _owned_house(db, house_id, body.character_id, user)
    room = await _room(db, room_id)
    if room.house_id != house_id:
        raise HTTPException(404, "Комната не найдена")
    room.name, room.description, room.image_url, room.is_open = (
        body.name, body.description, body.image_url, body.is_open)
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Building, levels and sleep (stage 2)
# ---------------------------------------------------------------------------

async def _rooms_of(db: AsyncSession, house_id: int) -> List[models.HouseRoom]:
    return (await db.execute(
        select(models.HouseRoom).where(models.HouseRoom.house_id == house_id)
        .order_by(models.HouseRoom.sort_order, models.HouseRoom.id))).scalars().all()


async def _settle_rooms(db: AsyncSession, house_id: int) -> None:
    """Finish builds and upgrades whose time has come."""
    now = await _db_now(db)
    done = (await db.execute(select(models.HouseRoom).where(
        models.HouseRoom.house_id == house_id,
        models.HouseRoom.upgrade_complete_at.isnot(None),
        models.HouseRoom.upgrade_complete_at <= now,
    ))).scalars().all()
    for room in done:
        room.level, room.upgrade_to_level, room.upgrade_complete_at = room.upgrade_to_level, None, None
    if done:
        await db.commit()


async def _character_states(db: AsyncSession, ids: List[int]) -> Dict[int, dict]:
    """Where each character stands, the bedroom it sleeps in and the library it reads in."""
    if not ids:
        return {}
    rows = await db.execute(
        text("SELECT id, current_location_id, sleep_house_room_id, reading_house_room_id, reading_since "
             "FROM characters WHERE id IN :ids")
        .bindparams(bindparam("ids", expanding=True)), {"ids": ids})
    return {r[0]: {"location_id": r[1], "asleep_room_id": r[2], "reading_room_id": r[3],
                   "reading_since": _dt(r[4])} for r in rows.fetchall()}


# ---------------------------------------------------------------------------
# Presence inside a house (stage 7)
# ---------------------------------------------------------------------------

# A character's `characters.house_room_id` counts only while the room's house stands in the
# location the character is in: a clear missed on some move never grants anything from afar.
PRESENT_SQL = (
    "SELECT c.id, c.house_room_id FROM characters c "
    "JOIN house_rooms r ON r.id = c.house_room_id "
    "JOIN houses h ON h.id = r.house_id "
    "JOIN house_plots p ON p.id = h.plot_id "
    "WHERE p.location_id = c.current_location_id"
)
GO_TO_ROOM = "Сначала перейдите в эту комнату"
NOT_A_MEMBER = "Внутрь дома могут заглянуть только хозяин, жильцы и гости"


async def _presence(db: AsyncSession, character_ids: Iterable) -> Dict[int, int]:
    """character id -> the house room it stands in now (only characters that are inside a house)."""
    ids = sorted({int(i) for i in character_ids if i is not None})
    if not ids:
        return {}
    rows = await db.execute(text(PRESENT_SQL + " AND c.id IN :ids")
                            .bindparams(bindparam("ids", expanding=True)), {"ids": ids})
    return {r[0]: r[1] for r in rows.fetchall()}


async def _present_in(db: AsyncSession, room_ids: Iterable) -> Dict[int, List[dict]]:
    """room id -> the characters standing in it now ({id, name, avatar})."""
    ids = sorted({int(i) for i in room_ids if i is not None})
    if not ids:
        return {}
    rows = await db.execute(text(
        "SELECT c.id, c.house_room_id, c.name, c.avatar FROM characters c "
        "JOIN house_rooms r ON r.id = c.house_room_id "
        "JOIN houses h ON h.id = r.house_id "
        "JOIN house_plots p ON p.id = h.plot_id "
        "WHERE p.location_id = c.current_location_id AND c.house_room_id IN :ids ORDER BY c.name, c.id")
        .bindparams(bindparam("ids", expanding=True)), {"ids": ids})
    out: Dict[int, List[dict]] = {}
    for cid, room_id, name, avatar in rows.fetchall():
        out.setdefault(room_id, []).append({"id": cid, "name": name, "avatar": avatar})
    return out


async def _require_in_room(db: AsyncSession, character_id: int, room_id: int,
                           message: str = GO_TO_ROOM) -> None:
    """403 unless the character stands in this very room."""
    if (await _presence(db, [character_id])).get(character_id) != room_id:
        raise HTTPException(403, message)


async def _put_out(db: AsyncSession, room_ids: List[int], character_id: Optional[int] = None) -> None:
    """Whoever stands in these rooms (or only this character) is out of the house. Does not commit."""
    if not room_ids:
        return
    query = "UPDATE characters SET house_room_id = NULL WHERE house_room_id IN :ids"
    params = {"ids": list(room_ids)}
    if character_id is not None:
        query += " AND id = :c"
        params["c"] = character_id
    await db.execute(text(query).bindparams(bindparam("ids", expanding=True)), params)


async def _membership(db: AsyncSession, house: models.House, character_id: int,
                      rooms: List[models.HouseRoom]) -> Optional[List[int]]:
    """The rooms (in plan order) the character may enter: all for the owner, the rooms let in
    for a resident, the guest rooms for a guest; None when it is none of them."""
    if character_id == house.owner_character_id:
        return [r.id for r in rooms]
    resident = (await db.execute(select(models.HouseResident).where(
        models.HouseResident.house_id == house.id,
        models.HouseResident.character_id == character_id))).scalar_one_or_none()
    if resident is not None:
        let_in = set((await _resident_rooms(db, [resident.id])).get(resident.id, []))
        return [r.id for r in rooms if r.id in let_in]
    if character_id in await _guest_ids(db, house.id):
        return [r.id for r in rooms if r.room_type in GUEST_ROOMS]
    return None


async def _viewer_members(db: AsyncSession, house: models.House, user: Optional[UserRead]) -> List[int]:
    """The viewer's characters that own, live in or are guests of the house."""
    mine = set(await _user_character_ids(db, user))
    if not mine:
        return []
    members = {house.owner_character_id}
    members |= set((await db.execute(select(models.HouseResident.character_id).where(
        models.HouseResident.house_id == house.id))).scalars().all())
    members |= set(await _guest_ids(db, house.id))
    return sorted(mine & members)


async def _cost(db: AsyncSession, room_type: str, level: int) -> dict:
    cost = (await db.execute(select(models.HouseBuildCost).where(
        models.HouseBuildCost.room_type == room_type, models.HouseBuildCost.level == level))).scalar_one_or_none()
    if cost is None:
        raise HTTPException(409, "Стоимость стройки не задана — обратитесь к администрации")
    items = (await db.execute(select(models.HouseBuildCostItem).where(
        models.HouseBuildCostItem.cost_id == cost.id).order_by(models.HouseBuildCostItem.id))).scalars().all()
    return {"gold": cost.gold, "build_hours": cost.build_hours,
            "items": [{"item_id": i.item_id, "quantity": i.quantity} for i in items]}


async def _item_names(db: AsyncSession, ids: Iterable) -> Dict[int, dict]:
    ids = sorted({int(i) for i in ids})
    if not ids:
        return {}
    rows = await db.execute(text("SELECT id, name, image FROM items WHERE id IN :ids")
                            .bindparams(bindparam("ids", expanding=True)), {"ids": ids})
    return {r[0]: {"id": r[0], "name": r[1], "image": r[2]} for r in rows.fetchall()}


async def _take_materials(db: AsyncSession, character_id: int, items: List[dict]) -> None:
    """Takes the materials from the bag (plain stacks only); 400 naming what is short. Does not commit."""
    names = await _item_names(db, [i["item_id"] for i in items])
    for need in items:
        rows = (await db.execute(text(
            "SELECT id, quantity FROM character_inventory WHERE character_id = :c AND item_id = :i "
            "AND COALESCE(enhancement_points_spent, 0) = 0 AND socketed_gems IS NULL "
            "AND current_durability IS NULL ORDER BY quantity, id"),
            {"c": character_id, "i": need["item_id"]})).fetchall()
        have = sum(r[1] for r in rows)
        if have < need["quantity"]:
            await db.rollback()
            name = names.get(need["item_id"], {}).get("name", f"предмет #{need['item_id']}")
            raise HTTPException(400, f"Не хватает: {name} — нужно {need['quantity']}, есть {have}")
        left = need["quantity"]
        for row_id, qty in rows:
            if left <= 0:
                break
            if qty <= left:
                await db.execute(text("DELETE FROM character_inventory WHERE id = :r"), {"r": row_id})
                left -= qty
            else:
                await db.execute(text("UPDATE character_inventory SET quantity = quantity - :q WHERE id = :r"),
                                 {"q": left, "r": row_id})
                left = 0


async def _charge(db: AsyncSession, character_id: int, amount: int, plot: models.HousePlot, op_type: str,
                  metadata: dict, short: Optional[str] = None) -> int:
    """FEAT-181: the character pays `amount` into the plot's region treasury (no commit).
    Not enough gold -> rollback + 400. Returns the new balance."""
    balance = await crud.charge_character(db, character_id, amount, op_type=op_type,
                                          location_id=plot.location_id, region_id=plot.region_id,
                                          metadata=metadata)
    if balance is None:
        await db.rollback()
        message = await crud.not_enough_gold_message(db)
        if short:
            message = f"{message}: {short} {await crud.format_gold(db, amount)}"
        raise HTTPException(400, message)
    return balance


async def _pay_for_build(db: AsyncSession, character_id: int, cost: dict, plot: models.HousePlot,
                         what: str) -> None:
    """Takes the materials and the gold together with the pending room change; commits, or rolls back with 400."""
    await _take_materials(db, character_id, cost["items"])
    await db.flush()
    await _charge(db, character_id, cost["gold"], plot, "house_build", {"plot_id": plot.id, "what": what})
    await db.commit()


async def _builder(db: AsyncSession, house_id: int, character_id: int, user: UserRead):
    """The owner standing at the house, free to act: (house, plot)."""
    from main import check_not_activity_locked, check_not_in_battle

    house = await _owned_house(db, house_id, character_id, user)
    _require_active(house)
    plot = await _plot(db, house.plot_id)
    character = await _own_character(db, character_id, user)
    if character["location_id"] is None or int(character["location_id"]) != plot.location_id:
        raise HTTPException(403, NOT_HERE)
    await check_not_activity_locked(db, character_id)
    await check_not_in_battle(db, character_id, "Во время боя не строят")
    await _settle_rooms(db, house_id)
    return house, plot


@router.post("/{house_id}/rooms")
async def build_room(
    house_id: int,
    body: BuildIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    house, plot = await _builder(db, house_id, body.character_id, user)
    rooms = await _rooms_of(db, house_id)
    cell = next((c for c in (await _plan(db, plot, house, rooms))["cells"] if c["id"] == body.cell_id), None)
    if cell is None:
        raise HTTPException(404, "Такого места на плане нет")
    if not cell["unlocked"]:
        raise HTTPException(409, "Это место ещё не куплено")
    if cell["room_id"]:
        raise HTTPException(409, "Это место уже занято")
    if body.room_type not in cell["allowed_types"]:
        raise HTTPException(400, f"Здесь нельзя построить {ROOM_TYPE_LABEL[body.room_type]}")
    cost = await _cost(db, body.room_type, 1)
    now = await _db_now(db)
    room = models.HouseRoom(house_id=house_id, room_type=body.room_type, name=body.name, description="",
                            level=0, upgrade_to_level=1,
                            workshop_profession_id=(await _profession_ids(db)).get(body.room_type),
                            upgrade_complete_at=now + timedelta(hours=cost["build_hours"]),
                            sort_order=max([r.sort_order for r in rooms], default=-1) + 1, cell_id=body.cell_id)
    db.add(room)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Это место уже занято")
    room_id = room.id
    await _pay_for_build(db, body.character_id, cost, plot, f"house #{house_id} build {body.room_type}")
    await _settle_rooms(db, house_id)
    return {"room_id": room_id}


@router.post("/{house_id}/layers/{layer}/unlock")
async def unlock_layer(
    house_id: int,
    layer: str,
    body: CharacterIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Buys a layer of the plan that has a price (a second floor, a basement)."""
    house, plot = await _builder(db, house_id, body.character_id, user)
    entry = next((l for l in (await _plan(db, plot, house))["layers"] if l["layer"] == layer), None)
    if entry is None:
        raise HTTPException(404, "Такого слоя у этого дома нет")
    if entry["unlocked"]:
        raise HTTPException(409, "Этот слой уже открыт")
    db.add(models.HouseLayerUnlock(house_id=house_id, layer=layer))
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Этот слой уже открыт")
    await _pay_for_build(db, body.character_id, {"gold": entry["unlock_price"], "items": []}, plot,
                         f"house #{house_id} layer {layer}")
    return {"ok": True}


@router.post("/{house_id}/cells/{cell_id}/unlock")
async def unlock_cell(
    house_id: int,
    cell_id: int,
    body: CharacterIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Buys an extension cell at the plot's extension price."""
    house, plot = await _builder(db, house_id, body.character_id, user)
    plan = await _plan(db, plot, house)
    cell = next((c for c in plan["cells"] if c["id"] == cell_id), None)
    if cell is None:
        raise HTTPException(404, "Такого места на плане нет")
    if cell["unlocked"]:
        raise HTTPException(409, "Это место уже ваше")
    if not next(l for l in plan["layers"] if l["layer"] == cell["layer"])["unlocked"]:
        raise HTTPException(409, f"Сначала откройте слой: {LAYER_LABEL[cell['layer']]}")
    db.add(models.HouseCellUnlock(house_id=house_id, cell_id=cell_id))
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Это место уже ваше")
    await _pay_for_build(db, body.character_id, {"gold": plot.extension_price or 0, "items": []}, plot,
                         f"house #{house_id} extension cell #{cell_id}")
    return {"ok": True}


@router.post("/{house_id}/rooms/{room_id}/upgrade")
async def upgrade_room(
    house_id: int,
    room_id: int,
    body: CharacterIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    _house_row, plot = await _builder(db, house_id, body.character_id, user)
    room = await _room(db, room_id)
    if room.house_id != house_id:
        raise HTTPException(404, "Комната не найдена")
    if room.upgrade_to_level is not None:
        raise HTTPException(409, "Комната уже строится")
    if room.level >= MAX_ROOM_LEVEL:
        raise HTTPException(409, "У комнаты уже наивысший уровень")
    target = room.level + 1
    cost = await _cost(db, room.room_type, target)
    now = await _db_now(db)
    room.upgrade_to_level = target
    room.upgrade_complete_at = now + timedelta(hours=cost["build_hours"])
    await db.flush()
    await _pay_for_build(db, body.character_id, cost, plot, f"house #{house_id} room #{room_id} to level {target}")
    await _settle_rooms(db, house_id)
    return {"ok": True}


@router.delete("/{house_id}/rooms/{room_id}")
async def demolish_room(
    house_id: int,
    room_id: int,
    character_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Pulls a room down, costs not returned. A storage the others could not replace stays."""
    await _owned_house(db, house_id, character_id, user)
    room = await _room(db, room_id)
    if room.house_id != house_id:
        raise HTTPException(404, "Комната не найдена")
    if (await db.execute(text("SELECT 1 FROM characters WHERE sleep_house_room_id = :r"), {"r": room_id})).first():
        raise HTTPException(409, "В этой спальне кто-то спит")
    if (await db.execute(text("SELECT 1 FROM characters WHERE reading_house_room_id = :r"), {"r": room_id})).first():
        raise HTTPException(409, "В этой библиотеке кто-то читает")
    if (await db.execute(select(models.HouseFurniture.id).where(models.HouseFurniture.room_id == room_id))).first():
        raise HTTPException(409, "Сначала уберите из комнаты мебель")
    if (await db.execute(select(models.HouseGardenBed.id).where(models.HouseGardenBed.room_id == room_id))).first():
        raise HTTPException(409, "Сначала соберите урожай")
    if room.room_type in STORAGE_ROOMS:
        await _settle_rooms(db, house_id)
        if await _stored_stacks(db, house_id) > await _storage_capacity(db, house_id, without_room=room_id):
            raise HTTPException(409, "Сначала освободите кладовую: остальные кладовые не вместят её вещи")
    await _put_out(db, [room_id])  # stage 7: whoever stood in it is out of the house
    await db.delete(room)
    await db.commit()
    return {"ok": True}


async def _settle_regen(character_id: int) -> None:
    """Regen up to now in attributes-service, so sleep starts or ends on a settled clock (503 if it fails)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{settings.ATTRIBUTES_SERVICE_URL}/attributes/internal/settle-regen",
                                     json={"character_ids": [character_id]},
                                     headers=crud._internal_token_headers())
        if resp.status_code == 200:
            return
    except httpx.HTTPError:
        pass
    raise HTTPException(503, "Не удалось пересчитать восстановление — попробуйте ещё раз")


@router.post("/rooms/{room_id}/sleep")
async def go_to_sleep(
    room_id: int,
    body: CharacterIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    from main import check_not_activity_locked, check_not_gathering, check_not_in_battle

    character = await _own_character(db, body.character_id, user)
    room = await _room(db, room_id)
    house = await _house(db, room.house_id)
    _require_active(house)
    await _settle_rooms(db, house.id)
    await db.refresh(room)
    if room.room_type not in SLEEP_ROOMS:
        raise HTTPException(400, "Спят в спальне или гостевой")
    if room.level < 1:
        raise HTTPException(409, "Спальня ещё строится")
    if body.character_id not in await _room_writers(db, house, room.id, room.room_type):
        raise HTTPException(403, "Хозяин не пускал этого персонажа в спальню")
    plot = await _plot(db, house.plot_id)
    if character["location_id"] is None or int(character["location_id"]) != plot.location_id:
        raise HTTPException(403, NOT_HERE)
    await check_not_activity_locked(db, body.character_id)
    await check_not_in_battle(db, body.character_id, "Во время боя не спят")
    await check_not_gathering(db, body.character_id, "Во время добычи не спят")
    await _require_in_room(db, body.character_id, room.id)
    await _settle_regen(body.character_id)
    factor = _sleep_factor(room, (await _furniture(db, [room.id])).get(room.id, []))
    done = await db.execute(text(
        "UPDATE characters SET asleep_since = :t, sleep_regen_factor = :f, sleep_house_room_id = :r "
        "WHERE id = :c AND asleep_since IS NULL AND reading_since IS NULL"),
        {"t": datetime.utcnow(), "f": factor, "r": room.id, "c": body.character_id})
    if not done.rowcount and (await db.execute(text("SELECT reading_since FROM characters WHERE id = :c"),
                                               {"c": body.character_id})).scalar() is not None:
        await db.rollback()
        raise HTTPException(409, "Персонаж читает — сначала нужно закончить чтение")
    await db.commit()
    return {"asleep": True, "sleep_factor": factor}


@router.post("/wake")
async def wake_up(
    body: CharacterIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Wakes the character wherever it sleeps; the rest slept so far is credited first."""
    await _own_character(db, body.character_id, user)
    asleep = (await db.execute(text("SELECT asleep_since FROM characters WHERE id = :c"),
                               {"c": body.character_id})).scalar()
    if asleep is None:
        return {"asleep": False}
    await _settle_regen(body.character_id)
    await db.execute(text(
        "UPDATE characters SET asleep_since = NULL, sleep_regen_factor = NULL, sleep_house_room_id = NULL "
        "WHERE id = :c"), {"c": body.character_id})
    await db.commit()
    return {"asleep": False}


# ---------------------------------------------------------------------------
# Residents
# ---------------------------------------------------------------------------

@router.post("/{house_id}/residents")
async def add_resident(
    house_id: int,
    body: ResidentAddIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    house = await _owned_house(db, house_id, body.character_id, user)
    if body.resident_character_id == house.owner_character_id:
        raise HTTPException(400, "Хозяин и так живёт в доме")
    row = (await db.execute(
        text("SELECT is_npc, user_id FROM characters WHERE id = :cid"), {"cid": body.resident_character_id},
    )).fetchone()
    if not row or row[0] or row[1] is None:
        raise HTTPException(404, "Персонаж не найден")
    halls = (await db.execute(select(models.HouseRoom.id).where(
        models.HouseRoom.house_id == house_id, models.HouseRoom.room_type == "hall"))).scalars().all()
    resident = models.HouseResident(house_id=house_id, character_id=body.resident_character_id)
    db.add(resident)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Этот персонаж уже живёт в доме")
    for room_id in halls:
        db.add(models.HouseResidentRoom(resident_id=resident.id, room_id=room_id))
    # Stage 7: a guest becoming a resident leaves the rooms (guest rooms) it is not let into now.
    others = (await db.execute(select(models.HouseRoom.id).where(
        models.HouseRoom.house_id == house_id, models.HouseRoom.id.notin_(halls or [0])))).scalars().all()
    await _leave_rooms(db, list(others), body.resident_character_id)
    await db.execute(delete(models.HouseGuest).where(models.HouseGuest.house_id == house_id,
                                                     models.HouseGuest.character_id == body.resident_character_id))
    await db.commit()
    return {"id": resident.id}


@router.put("/{house_id}/residents/{resident_id}")
async def set_resident_rights(
    house_id: int,
    resident_id: int,
    body: ResidentRightsIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    await _owned_house(db, house_id, body.character_id, user)
    resident = await db.get(models.HouseResident, resident_id)
    if not resident or resident.house_id != house_id:
        raise HTTPException(404, "Жилец не найден")
    house_rooms = set((await db.execute(
        select(models.HouseRoom.id).where(models.HouseRoom.house_id == house_id))).scalars().all())
    if not set(body.room_ids) <= house_rooms:
        raise HTTPException(400, "Такой комнаты в доме нет")
    resident.can_take, resident.can_put = body.can_take, body.can_put
    # Stage 7: out of the rooms it is no longer let into (waking or stopping reading there).
    await _leave_rooms(db, sorted(house_rooms - set(body.room_ids)), resident.character_id)
    await db.execute(delete(models.HouseResidentRoom).where(models.HouseResidentRoom.resident_id == resident_id))
    for room_id in sorted(set(body.room_ids)):
        db.add(models.HouseResidentRoom(resident_id=resident_id, room_id=room_id))
    await db.commit()
    return {"ok": True}


@router.delete("/{house_id}/residents/{resident_id}")
async def remove_resident(
    house_id: int,
    resident_id: int,
    character_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """The owner sends a resident away, or the resident moves out."""
    await _own_character(db, character_id, user)
    house = await _house(db, house_id)
    resident = await db.get(models.HouseResident, resident_id)
    if not resident or resident.house_id != house_id:
        raise HTTPException(404, "Жилец не найден")
    if character_id not in (house.owner_character_id, resident.character_id):
        raise HTTPException(403, "Это может только хозяин дома или сам жилец")
    if house.heir_character_id == resident.character_id:
        house.heir_character_id = None
    await _leave_rooms(db, [r.id for r in await _rooms_of(db, house_id)], resident.character_id)
    await db.delete(resident)
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Room posts
# ---------------------------------------------------------------------------

async def _open_room(db: AsyncSession, room_id: int, user: Optional[UserRead]):
    """The room and its house, when the viewer may read it (403 when not).

    Stage 7: nobody outside the house reads it — only the owner, residents and guests (an open
    room: all of them; a closed one: those let into it), and staff for moderation."""
    room = await _room(db, room_id)
    house = await _house(db, room.house_id)
    if _is_staff(user):
        return room, house
    members = await _viewer_members(db, house, user)
    if not members:
        raise HTTPException(403, NOT_A_MEMBER)
    if room.is_open or set(members) & set(await _room_writers(db, house, room.id, room.room_type)):
        return room, house
    raise HTTPException(403, "Комната закрыта — читать её могут только впущенные в неё")


async def _db_now(db: AsyncSession) -> datetime:
    """The database clock: post timestamps are written by it, not by this process."""
    now = (await db.execute(text("SELECT CURRENT_TIMESTAMP"))).scalar()
    return datetime.fromisoformat(now) if isinstance(now, str) else now


async def _posts_out(db: AsyncSession, posts: List[models.HousePost], user: Optional[UserRead],
                     house: models.House) -> List[dict]:
    chars = await _characters(db, [p.character_id for p in posts])
    my_chars = set(await _user_character_ids(db, user))
    window = timedelta(hours=crud.POST_EDIT_WINDOW_HOURS)
    now = await _db_now(db)
    out = []
    for p in posts:
        mine = p.character_id in my_chars
        out.append({
            "id": p.id,
            "content": p.content,
            "created_at": p.created_at,
            "edited_at": p.edited_at,
            "character": chars.get(p.character_id),
            "can_edit": _is_admin(user) or (mine and p.created_at and now - p.created_at < window),
            "can_delete": mine or _is_staff(user) or house.owner_character_id in my_chars,
        })
    return out


@router.get("/rooms/{room_id}")
async def get_room(
    room_id: int,
    before_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: Optional[UserRead] = Depends(get_viewer),
):
    room, house = await _open_room(db, room_id, user)
    q = (select(models.HousePost).where(models.HousePost.room_id == room_id)
         .order_by(models.HousePost.id.desc()).limit(POSTS_PAGE + 1))
    if before_id:
        q = q.where(models.HousePost.id < before_id)
    posts = (await db.execute(q)).scalars().all()
    writers = set(await _room_writers(db, house, room.id, room.room_type))
    my_chars = await _user_character_ids(db, user)
    chars = await _characters(db, [c for c in my_chars if c in writers])
    await _settle_rooms(db, house.id)
    await db.refresh(room)
    beds = await _beds(db, [room.id]) if room.room_type in GARDEN_ROOMS else {}
    here = await _presence(db, list(chars))
    out = {
        "room": {"id": room.id, "house_id": house.id, "house_name": house.name, "room_type": room.room_type,
                 "name": room.name, "description": room.description, "image_url": room.image_url,
                 "is_open": room.is_open, "level": room.level,
                 **_beds_view(room, beds.get(room.id, []), await _db_now(db))},
        # Stage 7: `in_room` — the writer stands in this room (writing needs it).
        "writers": [{**chars[c], "in_room": here.get(c) == room.id} for c in my_chars if c in chars],
        # Stage 7: who stands in this room now.
        "present": (await _present_in(db, [room.id])).get(room.id, []),
        "posts": await _posts_out(db, posts[:POSTS_PAGE], user, house),
        "has_more": len(posts) > POSTS_PAGE,
    }
    await _fill_beds(db, [out["room"]])
    return out


def _content(raw: str) -> str:
    if len(raw or "") > MAX_POST_CHARS:
        raise HTTPException(400, "Пост слишком длинный")
    plain = crud.strip_html_tags(raw or "")
    if len(plain) < crud.MIN_POST_LENGTH:
        raise HTTPException(400, f"Минимальная длина поста — {crud.MIN_POST_LENGTH} символов (сейчас: {len(plain)})")
    return raw


@router.post("/rooms/{room_id}/posts")
async def create_post(
    room_id: int,
    body: PostIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    from main import (_auto_progress_quest, _track_cumulative_stats, check_not_activity_locked,
                      check_not_gathering, check_not_in_battle)

    character = await _own_character(db, body.character_id, user)
    room = await _room(db, room_id)
    house = await _house(db, room.house_id)
    if body.character_id not in await _room_writers(db, house, room.id, room.room_type):
        raise HTTPException(403, "Хозяин не пускал этого персонажа в комнату")
    _require_active(house)
    await _settle_rooms(db, house.id)
    await db.refresh(room)
    if room.level < 1:
        raise HTTPException(409, "Комната ещё строится")
    plot = await _plot(db, house.plot_id)
    if character["location_id"] is None or int(character["location_id"]) != plot.location_id:
        raise HTTPException(403, NOT_HERE)
    await check_not_activity_locked(db, body.character_id)
    await check_not_in_battle(db, body.character_id, "Вы не можете писать посты во время боя")
    await check_not_gathering(db, body.character_id, "Вы не можете писать посты во время добычи")
    await _require_in_room(db, body.character_id, room.id)
    content = _content(body.content)

    post = models.HousePost(room_id=room_id, character_id=body.character_id, content=content)
    db.add(post)
    await db.commit()
    await db.refresh(post)

    # Experience as for an ordinary post; quests and stats that are not tied to
    # a world location count it too. The activity feed never sees house posts.
    char_count, xp = crud.calculate_post_xp(content)
    background_tasks.add_task(crud.award_post_xp_and_log, body.character_id, post.id, plot.location_id,
                              f"доме «{house.name}»", char_count, xp)
    background_tasks.add_task(_track_cumulative_stats, body.character_id, {"total_posts": 1})
    background_tasks.add_task(_auto_progress_quest, db, body.character_id, "write_posts")
    background_tasks.add_task(_auto_progress_quest, db, body.character_id, "write_chars", char_count)
    return (await _posts_out(db, [post], user, house))[0]


@router.put("/posts/{post_id}")
async def edit_post(
    post_id: int,
    body: PostEditIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    post = await db.get(models.HousePost, post_id)
    if not post:
        raise HTTPException(404, "Пост не найден")
    room = await _room(db, post.room_id)
    house = await _house(db, room.house_id)
    (out,) = await _posts_out(db, [post], user, house)
    if not out["can_edit"]:
        raise HTTPException(403, f"Пост можно править только свой и в течение {crud.POST_EDIT_WINDOW_HOURS} ч")
    post.content = _content(body.content)
    post.edited_at = await _db_now(db)
    await db.commit()
    await db.refresh(post)
    return (await _posts_out(db, [post], user, house))[0]


@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    post = await db.get(models.HousePost, post_id)
    if not post:
        raise HTTPException(404, "Пост не найден")
    room = await _room(db, post.room_id)
    house = await _house(db, room.house_id)
    (out,) = await _posts_out(db, [post], user, house)
    if not out["can_delete"]:
        raise HTTPException(403, "Удалить пост может автор, хозяин дома или модератор")
    await db.delete(post)
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin: plots
# ---------------------------------------------------------------------------

async def _save_plot(db: AsyncSession, plot: models.HousePlot, body: PlotIn) -> None:
    """Saves the plot and its plan. Cells keep their ids by position, so the rooms of a
    bought house stay where they stand; a place with such a room can not be removed."""
    if not await db.get(models.Location, body.location_id):
        raise HTTPException(404, "Локация не найдена")
    plot.location_id = body.location_id
    plot.region_id = await _region_of_location(db, body.location_id)
    plot.name, plot.description, plot.image_url = body.name, body.description, body.image_url
    plot.price, plot.map_x, plot.map_y = body.price, body.map_x, body.map_y
    plot.kind = body.kind
    plot.grid_w, plot.grid_h, plot.extension_price = body.grid_w, body.grid_h, body.extension_price
    db.add(plot)
    await db.flush()

    layers = {l.layer: l for l in (await db.execute(select(models.HousePlotLayer).where(
        models.HousePlotLayer.plot_id == plot.id))).scalars().all()}
    for l in body.layers:
        row = layers.pop(l.layer, None) or models.HousePlotLayer(plot_id=plot.id, layer=l.layer)
        row.unlock_price = l.unlock_price or None
        db.add(row)
    for row in layers.values():
        await db.delete(row)

    house = (await db.execute(select(models.House).where(models.House.plot_id == plot.id))).scalar_one_or_none()
    occupied = set()
    if house is not None:
        occupied = {r.cell_id for r in await _rooms_of(db, house.id) if r.cell_id}
    cells = {(c.layer, c.x, c.y): c for c in (await db.execute(select(models.HousePlotCell).where(
        models.HousePlotCell.plot_id == plot.id))).scalars().all()}
    kept = {}
    for c in body.cells:
        row = cells.pop((c.layer, c.x, c.y), None) or models.HousePlotCell(plot_id=plot.id, layer=c.layer, x=c.x, y=c.y)
        row.kind, row.allowed_types = c.kind, ",".join(c.allowed_types) or None
        db.add(row)
        kept[(c.layer, c.x, c.y)] = row
    for row in cells.values():
        if row.id in occupied:
            where = f"{LAYER_LABEL[row.layer]}, {row.x + 1}:{row.y + 1}"
            await db.rollback()
            raise HTTPException(409, f"В клетке ({where}) стоит комната купленного дома — её нельзя убрать")
        await db.delete(row)
    await db.flush()

    await db.execute(delete(models.HousePlotRoom).where(models.HousePlotRoom.plot_id == plot.id))
    for i, r in enumerate(body.rooms):
        db.add(models.HousePlotRoom(plot_id=plot.id, room_type=r.room_type, name=r.name,
                                    description=r.description, image_url=r.image_url, sort_order=i,
                                    cell_id=kept[(r.layer, r.x, r.y)].id))
    await db.commit()


@router.get("/admin/plots")
async def admin_list_plots(
    db: AsyncSession = Depends(get_db),
    _: UserRead = Depends(require_permission("locations:read")),
):
    plots = (await db.execute(select(models.HousePlot).order_by(models.HousePlot.id.desc()))).scalars().all()
    return await _plots_out(db, plots)


@router.post("/admin/plots")
async def admin_create_plot(
    body: PlotIn,
    db: AsyncSession = Depends(get_db),
    _: UserRead = Depends(require_permission("locations:create")),
):
    plot = models.HousePlot()
    await _save_plot(db, plot, body)
    return {"id": plot.id}


@router.put("/admin/plots/{plot_id}")
async def admin_update_plot(
    plot_id: int,
    body: PlotIn,
    db: AsyncSession = Depends(get_db),
    _: UserRead = Depends(require_permission("locations:update")),
):
    """Changes the plot and the rooms of a house not sold yet; a bought house keeps its own rooms."""
    plot = await _plot(db, plot_id)
    await _save_plot(db, plot, body)
    return {"id": plot.id}


@router.delete("/admin/plots/{plot_id}")
async def admin_delete_plot(
    plot_id: int,
    db: AsyncSession = Depends(get_db),
    _: UserRead = Depends(require_permission("locations:delete")),
):
    plot = await _plot(db, plot_id)
    if (await db.execute(select(models.House.id).where(models.House.plot_id == plot_id))).first():
        raise HTTPException(409, "На участке стоит купленный дом — его нельзя удалить")
    await db.delete(plot)
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin: build costs
# ---------------------------------------------------------------------------

@router.put("/admin/build-costs/{room_type}/{level}")
async def admin_set_build_cost(
    room_type: str,
    level: int,
    body: CostIn,
    db: AsyncSession = Depends(get_db),
    _: UserRead = Depends(require_permission("locations:update")),
):
    if room_type not in ROOM_TYPES or not 1 <= level <= MAX_ROOM_LEVEL:
        raise HTTPException(404, "Нет такой ступени стройки")
    merged: Dict[int, int] = {}
    for i in body.items:
        merged[i.item_id] = merged.get(i.item_id, 0) + i.quantity
    if merged and set((await _item_names(db, merged)).keys()) != set(merged):
        raise HTTPException(400, "Такого предмета нет")
    cost = (await db.execute(select(models.HouseBuildCost).where(
        models.HouseBuildCost.room_type == room_type, models.HouseBuildCost.level == level))).scalar_one_or_none()
    if cost is None:
        cost = models.HouseBuildCost(room_type=room_type, level=level)
        db.add(cost)
    cost.gold, cost.build_hours = body.gold, body.build_hours
    await db.flush()
    await db.execute(delete(models.HouseBuildCostItem).where(models.HouseBuildCostItem.cost_id == cost.id))
    for item_id, qty in merged.items():
        db.add(models.HouseBuildCostItem(cost_id=cost.id, item_id=item_id, quantity=qty))
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Furniture (stage 3)
# ---------------------------------------------------------------------------

def _furniture_slots(room: models.HouseRoom) -> int:
    """Pieces a room holds: its level, or a trophy hall's trophy slots (0 while being built)."""
    if room.room_type == TROPHY_HALL:
        return TROPHY_SLOTS.get(room.level, 0)
    return room.level if room.room_type in FURNITURE_GROUP else 0


def _sleep_factor(room: models.HouseRoom, furniture: List[dict]) -> Optional[float]:
    if room.level < 1:
        return None
    return BEDROOM_SLEEP_FACTOR.get(room.level, 1.0) + sum(f["sleep_bonus"] for f in furniture)


async def _furniture(db: AsyncSession, room_ids: List[int]) -> Dict[int, List[dict]]:
    """What stands in each room, with the item's picture and bonuses."""
    if not room_ids:
        return {}
    rows = (await db.execute(text(
        "SELECT f.id, f.room_id, i.id, i.name, i.image, i.item_rarity, i.description, "
        "i.furniture_sleep_bonus, i.furniture_storage_stacks, i.furniture_xp_bonus_pct, "
        "i.furniture_refine_bonus_pct FROM house_furniture f JOIN items i ON i.id = f.item_id "
        "WHERE f.room_id IN :ids ORDER BY f.id").bindparams(bindparam("ids", expanding=True)),
        {"ids": list(room_ids)})).fetchall()
    out: Dict[int, List[dict]] = {}
    for fid, room_id, item_id, name, image, rarity, description, sleep, stacks, xp, refine in rows:
        out.setdefault(room_id, []).append({
            "id": fid, "item_id": item_id, "name": name, "image": image, "rarity": rarity,
            "description": description, "sleep_bonus": float(sleep or 0), "storage_stacks": int(stacks or 0),
            "xp_bonus_pct": float(xp or 0), "refine_bonus_pct": float(refine or 0),
        })
    return out


async def _stored_stacks(db: AsyncSession, house_id: int) -> int:
    return (await db.execute(text("SELECT COUNT(*) FROM house_storage WHERE house_id = :h"),
                             {"h": house_id})).scalar() or 0


async def _storage_capacity(db: AsyncSession, house_id: int, without_room: Optional[int] = None,
                            without_furniture: Optional[int] = None) -> int:
    """Stacks the built storage rooms hold (as inventory-service counts them), minus a room or a piece."""
    rooms = [r for r in await _rooms_of(db, house_id)
             if r.room_type in STORAGE_ROOMS and r.level >= 1 and r.id != without_room]
    furniture = await _furniture(db, [r.id for r in rooms])
    return sum(_room_stacks(r, [f for f in furniture.get(r.id, []) if f["id"] != without_furniture])
               for r in rooms)


def _room_stacks(room: models.HouseRoom, furniture: List[dict]) -> Optional[int]:
    """Stacks a built storage or cellar holds with its furniture (None while being built)."""
    if room.level < 1:
        return None
    by_level = CELLAR_STACKS_BY_LEVEL if room.room_type == "cellar" else STORAGE_STACKS_BY_LEVEL
    return by_level.get(room.level, 0) + sum(f["storage_stacks"] for f in furniture)


async def _furnishing(db: AsyncSession, house_id: int, room_id: int, character_id: int, user: UserRead):
    """The owner at the house and the room to furnish (built, nobody asleep in it)."""
    await _builder(db, house_id, character_id, user)
    room = await _room(db, room_id)
    if room.house_id != house_id:
        raise HTTPException(404, "Комната не найдена")
    await db.refresh(room)
    if room.level < 1:
        raise HTTPException(409, "Комната ещё строится")
    if (await db.execute(text("SELECT 1 FROM characters WHERE sleep_house_room_id = :r"), {"r": room_id})).first():
        raise HTTPException(409, "В этой спальне кто-то спит")
    return room


@router.post("/{house_id}/rooms/{room_id}/furniture")
async def place_furniture(
    house_id: int,
    room_id: int,
    body: FurnitureIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Moves one piece of furniture from the owner's bag into the room."""
    room = await _furnishing(db, house_id, room_id, body.character_id, user)
    trophy_hall = room.room_type == TROPHY_HALL
    group = FURNITURE_GROUP.get(room.room_type)
    if group is None and not trophy_hall:
        raise HTTPException(409, "В эту комнату мебель не ставят")
    placed = (await db.execute(select(func.count()).select_from(models.HouseFurniture)
                               .where(models.HouseFurniture.room_id == room_id))).scalar() or 0
    if placed >= _furniture_slots(room):
        raise HTTPException(409, "В зале нет свободного места — улучшите его" if trophy_hall
                            else "В комнате нет свободного места под мебель — улучшите её")
    row = (await db.execute(text(
        "SELECT ci.id, ci.quantity, i.id, i.item_type, i.furniture_room_type, i.is_elite_trophy "
        "FROM character_inventory ci "
        "JOIN items i ON i.id = ci.item_id WHERE ci.id = :r AND ci.character_id = :c"),
        {"r": body.inventory_item_id, "c": body.character_id})).fetchone()
    if not row:
        raise HTTPException(404, "Предмет не найден в сумке")
    row_id, quantity, item_id, item_type, furniture_room, elite = row
    if trophy_hall:
        if item_type == "furniture":
            raise HTTPException(409, "В трофейный зал мебель не ставят")
        if not elite:
            raise HTTPException(400, "Сюда вешают только элитные трофеи")
    elif item_type != "furniture":
        raise HTTPException(400, "Это не мебель")
    elif furniture_room != group:
        raise HTTPException(400, "Эта мебель для комнаты другого типа")
    if quantity > 1:
        await db.execute(text("UPDATE character_inventory SET quantity = quantity - 1 WHERE id = :r"), {"r": row_id})
    else:
        await db.execute(text("DELETE FROM character_inventory WHERE id = :r"), {"r": row_id})
    db.add(models.HouseFurniture(room_id=room_id, item_id=item_id))
    await db.commit()
    return {"ok": True}


@router.delete("/{house_id}/rooms/{room_id}/furniture/{furniture_id}")
async def remove_furniture(
    house_id: int,
    room_id: int,
    furniture_id: int,
    character_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Puts a piece back into the owner's bag; a storage keeps it while its items would not fit."""
    room = await _furnishing(db, house_id, room_id, character_id, user)
    piece = await db.get(models.HouseFurniture, furniture_id)
    if not piece or piece.room_id != room_id:
        raise HTTPException(404, "Мебель не найдена")
    if room.room_type in STORAGE_ROOMS and (
            await _stored_stacks(db, house_id) > await _storage_capacity(db, house_id, without_furniture=piece.id)):
        raise HTTPException(409, "Без этой мебели кладовая не вместит свои вещи — сначала освободите место")
    max_stack = (await db.execute(text("SELECT max_stack_size FROM items WHERE id = :i"),
                                  {"i": piece.item_id})).scalar() or 1
    stack = (await db.execute(text(
        "SELECT id FROM character_inventory WHERE character_id = :c AND item_id = :i AND quantity < :m "
        "AND COALESCE(enhancement_points_spent, 0) = 0 AND socketed_gems IS NULL AND current_durability IS NULL "
        "ORDER BY id LIMIT 1"), {"c": character_id, "i": piece.item_id, "m": max_stack})).scalar()
    if stack:
        await db.execute(text("UPDATE character_inventory SET quantity = quantity + 1 WHERE id = :r"), {"r": stack})
    else:
        await db.execute(text("INSERT INTO character_inventory (character_id, item_id, quantity) VALUES (:c, :i, 1)"),
                         {"c": character_id, "i": piece.item_id})
    await db.delete(piece)
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Tax, inheritance, seizure, sale (stage 4)
# ---------------------------------------------------------------------------

TAX_PERIOD_DAYS = 49  # a game season (39 days) and the transition after it (10)
FREEZE_AFTER_PERIODS = 2  # owing the current and the previous period
SEIZE_AFTER_PERIODS = 3
DEFAULT_EPOCH = datetime(2026, 3, 19)


async def _tax_period(db: AsyncSession) -> dict:
    """The current tax period index and when it ends (naive UTC)."""
    config = await crud.get_game_time_config(db)
    epoch, offset = (config.epoch, config.offset_days) if config else (DEFAULT_EPOCH, 0)
    days = max(0, math.floor((datetime.utcnow() - epoch).total_seconds() / 86400) + offset)
    period = days // TAX_PERIOD_DAYS
    ends = epoch + timedelta(days=(period + 1) * TAX_PERIOD_DAYS - offset)
    return {"period": period, "ends_at": ends}


async def _tax_settings(db: AsyncSession) -> models.HouseSettings:
    row = await db.get(models.HouseSettings, 1)
    return row or models.HouseSettings(id=1, tax_price_pct=5.0, tax_per_room_level=50)


async def _tax_amount(db: AsyncSession, house: models.House, plot: models.HousePlot) -> int:
    rates = await _tax_settings(db)
    levels = sum(r.level for r in await _rooms_of(db, house.id) if r.level >= 1)
    return int(round(plot.price * rates.tax_price_pct / 100)) + rates.tax_per_room_level * levels


async def _tax_state(db: AsyncSession, house: models.House, plot: models.HousePlot) -> dict:
    period = await _tax_period(db)
    owed = max(0, period["period"] - (house.tax_paid_through if house.tax_paid_through is not None
                                      else period["period"]))
    per_season = await _tax_amount(db, house, plot)
    return {
        "per_season": per_season,
        "owed_periods": owed,
        "due": owed * per_season,
        "period_ends_at": period["ends_at"],
        # What happens when this period ends unpaid.
        "next_step": None if owed == 0 else ("freeze" if owed + 1 == FREEZE_AFTER_PERIODS else "seize"),
    }


async def _wake_sleepers(db: AsyncSession, room_ids: List[int]) -> None:
    """Wakes whoever sleeps in these rooms (the house is changing hands or is seized)."""
    if not room_ids:
        return
    sleepers = (await db.execute(
        text("SELECT id FROM characters WHERE sleep_house_room_id IN :ids")
        .bindparams(bindparam("ids", expanding=True)), {"ids": room_ids})).scalars().all()
    for character_id in sleepers:
        try:
            await _settle_regen(character_id)
        except HTTPException:
            pass  # the rest slept so far is lost, the character still wakes up
        await db.execute(text(
            "UPDATE characters SET asleep_since = NULL, sleep_regen_factor = NULL, sleep_house_room_id = NULL "
            "WHERE id = :c"), {"c": character_id})


async def _write_out_residents(db: AsyncSession, house: models.House) -> None:
    """Residents and guests leave; whoever sleeps or reads in the house stops (readers keep what they earned)
    and whoever stands inside is out."""
    room_ids = [r.id for r in await _rooms_of(db, house.id)]
    await _wake_sleepers(db, room_ids)
    await _stop_readers(db, room_ids)
    await _put_out(db, room_ids)  # stage 7: everyone inside, the old owner too, is out
    await db.execute(delete(models.HouseResident).where(models.HouseResident.house_id == house.id))
    await db.execute(delete(models.HouseGuest).where(models.HouseGuest.house_id == house.id))
    house.heir_character_id = None
    house.sale_price = house.listed_at = None


async def _seize(db: AsyncSession, house: models.House, reason: str) -> None:
    await _write_out_residents(db, house)
    house.status = "seized"
    house.former_plot_id, house.plot_id = house.plot_id, None
    house.seized_at = datetime.utcnow()
    house.seized_reason = reason


async def _character_exists(db: AsyncSession, character_id: Optional[int]) -> bool:
    if not character_id:
        return False
    return (await db.execute(text("SELECT 1 FROM characters WHERE id = :c"), {"c": character_id})).first() is not None


async def _settle_house(db: AsyncSession, house: models.House) -> None:
    """Inheritance, then the tax: freeze or seize as the periods passed demand."""
    if house.status == "seized":
        return
    changed = False
    if not await _character_exists(db, house.owner_character_id):
        heir = house.heir_character_id
        heir_lives_here = heir and (await db.execute(select(models.HouseResident).where(
            models.HouseResident.house_id == house.id, models.HouseResident.character_id == heir))).scalar_one_or_none()
        if heir_lives_here and await _character_exists(db, heir):
            await db.delete(heir_lives_here)
            house.owner_character_id, house.heir_character_id = heir, None
            house.sale_price = house.listed_at = None
        else:
            await _seize(db, house, "no_heir")
            await db.commit()
            return
        changed = True
    period = (await _tax_period(db))["period"]
    if house.tax_paid_through is None:
        house.tax_paid_through = period
        changed = True
    owed = period - house.tax_paid_through
    if owed >= SEIZE_AFTER_PERIODS:
        await _seize(db, house, "tax")
        changed = True
    elif owed >= FREEZE_AFTER_PERIODS and house.status != "frozen":
        house.status = "frozen"
        house.sale_price = house.listed_at = None
        changed = True
    if changed:
        await db.commit()


@router.post("/{house_id}/tax")
async def pay_tax(
    house_id: int,
    body: CharacterIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """The owner or a resident pays every period owed up to the current one."""
    await _own_character(db, body.character_id, user)
    house = await _house(db, house_id)
    if body.character_id != house.owner_character_id and not (await db.execute(select(models.HouseResident.id).where(
            models.HouseResident.house_id == house_id,
            models.HouseResident.character_id == body.character_id))).first():
        raise HTTPException(403, "Налог платят хозяин или жильцы")
    plot = await _plot(db, house.plot_id)
    state = await _tax_state(db, house, plot)
    if state["owed_periods"] == 0:
        raise HTTPException(400, "Налог за этот сезон уже уплачен")
    period = (await _tax_period(db))["period"]
    house.tax_paid_through = period
    house.status = "active"
    await db.flush()
    await _charge(db, body.character_id, state["due"], plot, "house_tax",
                  {"house_id": house_id, "periods": state["owed_periods"]}, short="налог")
    await db.commit()
    return {"paid": state["due"]}


@router.put("/{house_id}/heir")
async def set_heir(
    house_id: int,
    body: HeirIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    house = await _owned_house(db, house_id, body.character_id, user)
    if body.heir_character_id is not None and not (await db.execute(select(models.HouseResident.id).where(
            models.HouseResident.house_id == house_id,
            models.HouseResident.character_id == body.heir_character_id))).first():
        raise HTTPException(400, "Наследником может быть только жилец дома")
    house.heir_character_id = body.heir_character_id
    await db.commit()
    return {"ok": True}


@router.put("/{house_id}/sale")
async def put_up_for_sale(
    house_id: int,
    body: SaleIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    house = await _owned_house(db, house_id, body.character_id, user)
    _require_active(house)
    if (await _tax_state(db, house, await _plot(db, house.plot_id)))["owed_periods"]:
        raise HTTPException(409, "Сначала заплатите налог за этот сезон")
    house.sale_price = body.price
    house.listed_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}


@router.delete("/{house_id}/sale")
async def take_off_sale(
    house_id: int,
    character_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    house = await _owned_house(db, house_id, character_id, user)
    house.sale_price = house.listed_at = None
    await db.commit()
    return {"ok": True}


@router.post("/{house_id}/buy")
async def buy_listed_house(
    house_id: int,
    body: CharacterIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Buys a house off the board: gold to the seller, residents and heir written out."""
    from main import check_not_activity_locked, check_not_in_battle

    character = await _own_character(db, body.character_id, user)
    await _house(db, house_id)  # 404 for an unknown house
    # FEAT-181: lock the house row so two buyers cannot both take it (business row first, then gold).
    house = (await db.execute(
        select(models.House).where(models.House.id == house_id).with_for_update()
        .execution_options(populate_existing=True))).scalar_one()
    if house.sale_price is None or house.status != "active":
        raise HTTPException(409, "Дом не продаётся")
    if house.owner_character_id == body.character_id:
        raise HTTPException(400, "Это ваш дом")
    plot = await _plot(db, house.plot_id)
    if character["location_id"] is None or int(character["location_id"]) != plot.location_id:
        raise HTTPException(400, "Дом покупают на месте — дойдите до его локации")
    await check_not_activity_locked(db, body.character_id)
    await check_not_in_battle(db, body.character_id, "Во время боя дом не купить")
    seller, price = house.owner_character_id, house.sale_price
    await _write_out_residents(db, house)
    house.owner_character_id = body.character_id
    await db.flush()
    # FEAT-181: buyer -> seller as ONE house_resale operation, committed with the ownership change.
    balance = await crud.transfer_between_characters(
        db, body.character_id, seller, price, op_type="house_resale", location_id=plot.location_id,
        metadata={"house_id": house_id, "seller": seller, "buyer": body.character_id},
    )
    if balance is None:
        await db.rollback()
        raise HTTPException(400, await crud.not_enough_gold_message(db))
    await db.commit()
    return {"house_id": house_id, "gold": balance}


def verify_internal_token(x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token")) -> None:
    """main.verify_internal_token, looked up at call time (main imports this module)."""
    import main

    main.verify_internal_token(x_internal_token)


@router.post("/internal/character-deleted/{character_id}")
async def character_deleted(
    character_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_token),
):
    """character-service, after deleting a character: its houses pass to their heirs or are
    seized, and it stops living anywhere. The same happens lazily on the next read anyway."""
    owned = (await db.execute(select(models.House).where(models.House.owner_character_id == character_id))).scalars().all()
    for house in owned:
        await _settle_house(db, house)
    for house in (await db.execute(select(models.House).where(
            models.House.heir_character_id == character_id))).scalars().all():
        house.heir_character_id = None
    await db.execute(delete(models.HouseResident).where(models.HouseResident.character_id == character_id))
    await db.execute(delete(models.HouseGuest).where(models.HouseGuest.character_id == character_id))
    await db.execute(delete(models.HouseBuff).where(models.HouseBuff.character_id == character_id))
    await db.commit()
    return {"houses": [h.id for h in owned]}


@router.get("/admin/settings")
async def admin_get_settings(
    db: AsyncSession = Depends(get_db),
    _: UserRead = Depends(require_permission("locations:read")),
):
    rates = await _tax_settings(db)
    return {"tax_price_pct": rates.tax_price_pct, "tax_per_room_level": rates.tax_per_room_level,
            "tax_period_days": TAX_PERIOD_DAYS}


@router.put("/admin/settings")
async def admin_set_settings(
    body: TaxSettingsIn,
    db: AsyncSession = Depends(get_db),
    _: UserRead = Depends(require_permission("locations:update")),
):
    rates = await db.get(models.HouseSettings, 1)
    if rates is None:
        rates = models.HouseSettings(id=1)
        db.add(rates)
    rates.tax_price_pct, rates.tax_per_room_level = body.tax_price_pct, body.tax_per_room_level
    await db.commit()
    return {"ok": True}


@router.get("/admin/seized")
async def admin_seized_houses(
    db: AsyncSession = Depends(get_db),
    _: UserRead = Depends(require_permission("locations:read")),
):
    """The archive of seized houses (their buildings, furniture and stored items wait for the treasury)."""
    houses = (await db.execute(select(models.House).where(models.House.status == "seized")
                               .order_by(models.House.seized_at.desc()))).scalars().all()
    chars = await _characters(db, [h.owner_character_id for h in houses])
    plots = {p.id: p for p in (await db.execute(select(models.HousePlot).where(
        models.HousePlot.id.in_([h.former_plot_id for h in houses] or [0])))).scalars().all()}
    locations = await _location_names(db, [p.location_id for p in plots.values()])
    out = []
    for h in houses:
        rooms = await _rooms_of(db, h.id)
        furniture = await _furniture(db, [r.id for r in rooms])
        plot = plots.get(h.former_plot_id)
        out.append({
            "id": h.id, "name": h.name, "owner": chars.get(h.owner_character_id),
            "seized_at": h.seized_at, "reason": h.seized_reason,
            "location_name": locations.get(plot.location_id) if plot else None,
            "rooms": [{"room_type": r.room_type, "name": r.name, "level": r.level} for r in rooms],
            "furniture": [f["name"] for v in furniture.values() for f in v],
            "stored_stacks": await _stored_stacks(db, h.id),
        })
    return out


# ---------------------------------------------------------------------------
# Profession rooms, garden rooms and the bath (stage 6a)
# ---------------------------------------------------------------------------

async def _profession_ids(db: AsyncSession) -> Dict[str, int]:
    """room type -> `professions.id` for the profession rooms."""
    rows = await db.execute(text("SELECT id, slug FROM professions WHERE slug IN :slugs")
                            .bindparams(bindparam("slugs", expanding=True)),
                            {"slugs": list(PROFESSION_ROOMS.values())})
    by_slug = {slug: pid for pid, slug in rows.fetchall()}
    return {room: by_slug[slug] for room, slug in PROFESSION_ROOMS.items() if slug in by_slug}


def _left(delta: timedelta) -> str:
    minutes = max(1, math.ceil(delta.total_seconds() / 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours} ч {minutes} мин" if hours else f"{minutes} мин"


async def _beds(db: AsyncSession, room_ids: List[int]) -> Dict[int, List[models.HouseGardenBed]]:
    if not room_ids:
        return {}
    rows = (await db.execute(select(models.HouseGardenBed).where(models.HouseGardenBed.room_id.in_(room_ids))
                             .order_by(models.HouseGardenBed.bed_no))).scalars().all()
    out: Dict[int, List[models.HouseGardenBed]] = {}
    for b in rows:
        out.setdefault(b.room_id, []).append(b)
    return out


def _beds_view(room: models.HouseRoom, beds: List[models.HouseGardenBed], now: datetime) -> dict:
    """`beds_total` and `beds` for a garden room (filled by `_fill_beds`), None for other rooms."""
    if room.room_type not in GARDEN_ROOMS:
        return {"beds_total": None, "beds": None}
    return {"beds_total": GARDEN_BEDS_BY_LEVEL.get(room.level, 0),
            "beds": [{"bed_no": b.bed_no, "planted_by": b.character_id, "seed": b.seed_item_id,
                      "result": b.result_item_id, "quantity": b.result_quantity, "planted_at": b.planted_at,
                      "ready_at": b.ready_at, "ready": b.ready_at <= now} for b in beds]}


async def _fill_beds(db: AsyncSession, rooms: List[dict]) -> None:
    """Replaces the ids in `beds` entries with the planter and the items."""
    entries = [b for r in rooms for b in (r.get("beds") or [])]
    if not entries:
        return
    chars = await _characters(db, [b["planted_by"] for b in entries])
    items = await _item_names(db, [b["seed"] for b in entries] + [b["result"] for b in entries])
    for b in entries:
        b["planted_by"] = chars.get(b["planted_by"])
        b["seed"] = items.get(b["seed"])
        b["result"] = items.get(b["result"])


async def _bath_next(db: AsyncSession, character_ids: List[int], now: datetime) -> Dict[int, datetime]:
    """When each character may bathe again (only those still waiting)."""
    if not character_ids:
        return {}
    rows = (await db.execute(select(models.HouseBathUse).where(
        models.HouseBathUse.character_id.in_(character_ids)))).scalars().all()
    out = {}
    for row in rows:
        next_at = row.last_at + timedelta(hours=BATH_COOLDOWN_HOURS)
        if next_at > now:
            out[row.character_id] = next_at
    return out


async def _room_user(db: AsyncSession, room_id: int, character_id: int, user: UserRead, types: Iterable[str],
                     wrong_type: str, battle_message: str):
    """A character let into a built room of these types, standing at the house and free to act:
    (room, house)."""
    from main import check_not_activity_locked, check_not_gathering, check_not_in_battle

    character = await _own_character(db, character_id, user)
    room = await _room(db, room_id)
    house = await _house(db, room.house_id)
    _require_active(house)
    await _settle_rooms(db, house.id)
    await db.refresh(room)
    if room.room_type not in types:
        raise HTTPException(400, wrong_type)
    if room.level < 1:
        raise HTTPException(409, "Комната ещё строится")
    if character_id not in await _room_writers(db, house, room.id):
        raise HTTPException(403, "Хозяин не пускал этого персонажа в эту комнату")
    plot = await _plot(db, house.plot_id)
    if character["location_id"] is None or int(character["location_id"]) != plot.location_id:
        raise HTTPException(403, NOT_HERE)
    await check_not_activity_locked(db, character_id)
    await check_not_in_battle(db, character_id, battle_message)
    await check_not_gathering(db, character_id, "Во время добычи этого не сделать")
    await _require_in_room(db, character_id, room.id)
    return room, house


async def _seed_rows(db: AsyncSession, character_id: int, room_type: Optional[str] = None,
                     row_id: Optional[int] = None) -> list:
    """The character's plain bag stacks of seeds (all, or one row), with what they grow into."""
    query = (
        "SELECT ci.id, ci.quantity, i.id, i.name, i.image, i.seed_room_type, i.seed_grow_hours, "
        "i.seed_result_item_id, i.seed_result_quantity, i.seed_herbalism_xp "
        "FROM character_inventory ci JOIN items i ON i.id = ci.item_id "
        "WHERE ci.character_id = :c AND ci.quantity >= 1 AND i.item_type = 'resource' "
        "AND i.seed_result_item_id IS NOT NULL AND i.seed_room_type IS NOT NULL "
        "AND COALESCE(ci.enhancement_points_spent, 0) = 0 AND ci.socketed_gems IS NULL "
        "AND ci.current_durability IS NULL"
    )
    params = {"c": character_id}
    if room_type is not None:
        query += " AND i.seed_room_type = :t"
        params["t"] = room_type
    if row_id is not None:
        query += " AND ci.id = :r"
        params["r"] = row_id
    return (await db.execute(text(query + " ORDER BY ci.id"), params)).fetchall()


@router.get("/rooms/{room_id}/seeds")
async def seeds_for_room(
    room_id: int,
    character_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """The character's seeds that grow in this garden room (to choose what to plant)."""
    await _own_character(db, character_id, user)
    room = await _room(db, room_id)
    house = await _house(db, room.house_id)
    if room.room_type not in GARDEN_ROOMS:
        raise HTTPException(400, "Здесь ничего не сажают")
    if character_id not in await _room_writers(db, house, room.id):
        raise HTTPException(403, "Хозяин не пускал этого персонажа в эту комнату")
    rows = await _seed_rows(db, character_id, room.room_type)
    results = await _item_names(db, [r[7] for r in rows])
    return [{
        "inventory_item_id": r[0], "item_id": r[2], "name": r[3], "image": r[4], "quantity": r[1],
        "grow_hours": r[6], "result": results.get(r[7]), "result_quantity": r[8], "herbalism_xp": r[9],
    } for r in rows]


@router.post("/rooms/{room_id}/plant")
async def plant_seed(
    room_id: int,
    body: PlantIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Plants one seed from the bag into a free bed of a garden, greenhouse or apiary."""
    room, house = await _room_user(db, room_id, body.character_id, user, GARDEN_ROOMS,
                                   "Здесь ничего не сажают", "Во время боя не сажают")
    found = (await db.execute(text(
        "SELECT ci.id, i.item_type, i.seed_result_item_id, i.seed_room_type FROM character_inventory ci "
        "JOIN items i ON i.id = ci.item_id WHERE ci.id = :r AND ci.character_id = :c"),
        {"r": body.inventory_item_id, "c": body.character_id})).fetchone()
    if not found:
        raise HTTPException(404, "Предмет не найден в сумке")
    if found[1] != "resource" or found[2] is None or found[3] is None:
        raise HTTPException(400, "Это не семена")
    if found[3] != room.room_type:
        raise HTTPException(400, f"Это семя растёт не здесь: {SEED_PLACE.get(found[3], found[3])}")
    seed = await _seed_rows(db, body.character_id, row_id=body.inventory_item_id)
    if not seed:
        raise HTTPException(400, "Посадить можно только обычные семена из сумки")
    row_id, quantity, seed_id, _, _, _, hours, result_id, result_qty, xp = seed[0]

    total = GARDEN_BEDS_BY_LEVEL.get(room.level, 0)
    taken = {b.bed_no for b in (await _beds(db, [room.id])).get(room.id, [])}
    if body.bed_no is not None:
        if body.bed_no > total:
            raise HTTPException(409, "Такой грядки нет — улучшите комнату")
        if body.bed_no in taken:
            raise HTTPException(409, "Эта грядка занята")
        bed_no = body.bed_no
    else:
        bed_no = next((n for n in range(1, total + 1) if n not in taken), None)
        if bed_no is None:
            raise HTTPException(409, "Все грядки заняты")

    if quantity > 1:
        await db.execute(text("UPDATE character_inventory SET quantity = quantity - 1 WHERE id = :r"), {"r": row_id})
    else:
        await db.execute(text("DELETE FROM character_inventory WHERE id = :r"), {"r": row_id})
    now = await _db_now(db)
    bed = models.HouseGardenBed(room_id=room.id, bed_no=bed_no, character_id=body.character_id,
                                seed_item_id=seed_id, result_item_id=result_id, result_quantity=result_qty,
                                herbalism_xp=xp or 0, planted_at=now, ready_at=now + timedelta(hours=hours))
    db.add(bed)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Эта грядка занята")
    return {"bed_no": bed_no, "ready_at": bed.ready_at}


async def _inventory_award(character_id: int, payload: dict) -> dict:
    """inventory-service's gathering award (the harvest goes into the bag, herbalism experience).
    502/503 with a Russian message when it fails."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.INVENTORY_SERVICE_URL}/inventory/internal/characters/{character_id}/gathering/award",
                json=payload, headers=crud._internal_token_headers())
    except httpx.HTTPError:
        raise HTTPException(503, INVENTORY_UNREACHABLE)
    if resp.status_code != 200:
        raise HTTPException(502, INVENTORY_UNREACHABLE)
    return resp.json()


@router.post("/rooms/{room_id}/harvest")
async def harvest_bed(
    room_id: int,
    body: HarvestIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """The planter or the house owner gathers a grown bed into the bag."""
    from main import check_not_activity_locked, check_not_gathering, check_not_in_battle

    character = await _own_character(db, body.character_id, user)
    room = await _room(db, room_id)
    house = await _house(db, room.house_id)
    _require_active(house)
    if room.room_type not in GARDEN_ROOMS:
        raise HTTPException(400, "Здесь ничего не растёт")
    bed = (await db.execute(select(models.HouseGardenBed).where(
        models.HouseGardenBed.room_id == room_id, models.HouseGardenBed.bed_no == body.bed_no))).scalar_one_or_none()
    if bed is None:
        raise HTTPException(404, "На этой грядке ничего не посажено")
    if body.character_id not in (bed.character_id, house.owner_character_id):
        raise HTTPException(403, "Собрать урожай может тот, кто сажал, или хозяин дома")
    plot = await _plot(db, house.plot_id)
    if character["location_id"] is None or int(character["location_id"]) != plot.location_id:
        raise HTTPException(403, NOT_HERE)
    await check_not_activity_locked(db, body.character_id)
    await check_not_in_battle(db, body.character_id, "Во время боя урожай не собирают")
    await check_not_gathering(db, body.character_id, "Во время добычи этого не сделать")
    await _require_in_room(db, body.character_id, room.id)
    now = await _db_now(db)
    if bed.ready_at > now:
        raise HTTPException(409, f"Ещё не выросло — осталось {_left(bed.ready_at - now)}")

    # The bed is claimed first, so two harvests at once cannot both be paid; it
    # comes back when nothing reached the bag.
    kept = {c.name: getattr(bed, c.name) for c in models.HouseGardenBed.__table__.columns}
    gone = await db.execute(delete(models.HouseGardenBed).where(models.HouseGardenBed.id == bed.id))
    await db.commit()
    if not gone.rowcount:
        raise HTTPException(409, "Урожай уже собран")

    async def _restore():
        db.add(models.HouseGardenBed(**kept))
        await db.commit()

    try:
        award = await _inventory_award(body.character_id, {
            "skill_slug": "herbalism", "result_item_id": kept["result_item_id"],
            "result_quantity": kept["result_quantity"], "xp_to_add": kept["herbalism_xp"],
            "tool_inventory_item_id": None, "tool_durability_to_consume": 0,
        })
    except HTTPException:
        await _restore()
        raise
    added = int(award.get("actual_quantity_added") or 0)
    if added <= 0:
        await _restore()
        raise HTTPException(409, "Сумка полна")
    item = (await _item_names(db, [kept["result_item_id"]])).get(kept["result_item_id"])
    return {"added": added, "quantity": kept["result_quantity"], "item": item,
            "xp_awarded": award.get("xp_awarded", 0), "rank_up": bool(award.get("rank_up"))}


async def _recover(character_id: int, amounts: dict) -> None:
    """attributes-service recover (settles regen first, caps at the maximum); 502/503 when it fails."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{settings.ATTRIBUTES_SERVICE_URL}/attributes/{character_id}/recover",
                                     json=amounts, headers=crud._internal_token_headers())
    except httpx.HTTPError:
        raise HTTPException(503, ATTRIBUTES_UNREACHABLE)
    if resp.status_code != 200:
        raise HTTPException(502, ATTRIBUTES_UNREACHABLE)


@router.post("/rooms/{room_id}/bathe")
async def bathe(
    room_id: int,
    body: CharacterIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """A bath restores a share of health, mana, energy and stamina, once per 24 h per character."""
    room, _ = await _room_user(db, room_id, body.character_id, user, ("bath",), "Мыться ходят в баню",
                               "Во время боя в баню не ходят")
    now = await _db_now(db)
    use = await db.get(models.HouseBathUse, body.character_id)
    previous = use.last_at if use else None
    if previous is not None and previous + timedelta(hours=BATH_COOLDOWN_HOURS) > now:
        next_at = previous + timedelta(hours=BATH_COOLDOWN_HOURS)
        raise HTTPException(409, f"Баня ещё не остыла — снова можно через {_left(next_at - now)}")
    maxima = (await db.execute(text(
        "SELECT max_health, max_mana, max_energy, max_stamina FROM character_attributes WHERE character_id = :c"),
        {"c": body.character_id})).fetchone()
    if not maxima:
        raise HTTPException(404, "Атрибуты персонажа не найдены")
    share = BATH_RESTORE_PCT.get(room.level, 0.0)
    restored = {name: int(round((value or 0) * share))
                for name, value in zip(("health", "mana", "energy", "stamina"), maxima)}

    # The bath is taken first (two at once cannot both restore); it is given back if recovery fails.
    if use is None:
        db.add(models.HouseBathUse(character_id=body.character_id, last_at=now))
    else:
        claimed = await db.execute(update(models.HouseBathUse).where(
            models.HouseBathUse.character_id == body.character_id,
            models.HouseBathUse.last_at <= now - timedelta(hours=BATH_COOLDOWN_HOURS))
            .values(last_at=now))
        if not claimed.rowcount:
            await db.rollback()
            raise HTTPException(409, "Баня ещё не остыла")
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Баня ещё не остыла")
    try:
        await _recover(body.character_id, {f"{k}_recovery": v for k, v in restored.items()})
    except HTTPException:
        if previous is None:
            await db.execute(delete(models.HouseBathUse).where(models.HouseBathUse.character_id == body.character_id))
        else:
            await db.execute(update(models.HouseBathUse).where(
                models.HouseBathUse.character_id == body.character_id).values(last_at=previous))
        await db.commit()
        raise
    return {"restored": restored, "next_at": now + timedelta(hours=BATH_COOLDOWN_HOURS)}


# ---------------------------------------------------------------------------
# Library, shrine, trophy hall, guests (stage 6b)
# ---------------------------------------------------------------------------

def _dt(value) -> Optional[datetime]:
    """A DB timestamp as a naive datetime (SQLite hands back strings)."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).strip().replace(" ", "T", 1))


def _level_now(level: int, upgrade_to_level: Optional[int], complete_at, now: datetime) -> int:
    """A room's level with a finished but not yet settled upgrade counted (as inventory-service reads it)."""
    complete_at = _dt(complete_at)
    if upgrade_to_level is not None and complete_at is not None and complete_at <= now:
        return int(upgrade_to_level)
    return int(level or 0)


async def _upsert_buff(db: AsyncSession, character_id: int, source: str, kind: str, value: float,
                       expires_at: datetime) -> None:
    buff = (await db.execute(select(models.HouseBuff).where(
        models.HouseBuff.character_id == character_id, models.HouseBuff.source == source))).scalar_one_or_none()
    if buff is None:
        db.add(models.HouseBuff(character_id=character_id, source=source, kind=kind, value=value,
                                expires_at=expires_at))
    else:
        buff.kind, buff.value, buff.expires_at = kind, value, expires_at


async def _buffs(db: AsyncSession, character_ids: List[int], now: datetime) -> Dict[int, List[dict]]:
    """Each character's running house blessings."""
    if not character_ids:
        return {}
    rows = (await db.execute(select(models.HouseBuff).where(
        models.HouseBuff.character_id.in_(character_ids), models.HouseBuff.expires_at > now)
        .order_by(models.HouseBuff.source))).scalars().all()
    out: Dict[int, List[dict]] = {}
    for b in rows:
        out.setdefault(b.character_id, []).append(
            {"source": b.source, "kind": b.kind, "value": b.value, "expires_at": b.expires_at})
    return out


async def _end_reading(db: AsyncSession, character_id: int, now: datetime) -> Optional[dict]:
    """Stops the character's reading and grants what it earned; None when it was not reading.
    Does not commit.

    The library blessing: 1 % per full hour read, up to the library's cap, for 24 h
    from now when it reaches 1 %. A higher blessing still running is kept (its value),
    but its 24 h start again — reading never makes a blessing worse."""
    row = (await db.execute(text("SELECT reading_since, reading_house_room_id FROM characters WHERE id = :c"),
                            {"c": character_id})).fetchone()
    if not row or row[0] is None:
        return None
    hours = max(0, int((now - _dt(row[0])).total_seconds() // 3600))
    room = await db.get(models.HouseRoom, row[1]) if row[1] else None
    level = _level_now(room.level, room.upgrade_to_level, room.upgrade_complete_at, now) if room else 0
    bonus = round(min(hours * LIBRARY_RATE_PER_HOUR, LIBRARY_CAP.get(level, 0.0)), 4)
    await db.execute(text("UPDATE characters SET reading_since = NULL, reading_house_room_id = NULL WHERE id = :c"),
                     {"c": character_id})
    value, expires_at = 0.0, None
    if bonus + 1e-9 >= LIBRARY_RATE_PER_HOUR:
        expires_at = now + timedelta(hours=BUFF_HOURS)
        running = (await _buffs(db, [character_id], now)).get(character_id, [])
        held = max((b["value"] for b in running if b["source"] == "library"), default=0.0)
        value = max(bonus, held)
        await _upsert_buff(db, character_id, "library", "character_xp", value, expires_at)
    return {"hours": hours, "bonus": bonus, "value": value, "expires_at": expires_at}


async def _stop_readers(db: AsyncSession, room_ids: List[int]) -> None:
    """Whoever reads in these rooms stops, keeping what it earned (the house changes hands,
    is seized, or the reader leaves). Does not commit."""
    if not room_ids:
        return
    readers = (await db.execute(
        text("SELECT id FROM characters WHERE reading_house_room_id IN :ids")
        .bindparams(bindparam("ids", expanding=True)), {"ids": room_ids})).scalars().all()
    now = await _db_now(db)
    for character_id in readers:
        await _end_reading(db, character_id, now)


async def _leave_rooms(db: AsyncSession, room_ids: List[int], character_id: int) -> None:
    """The character stops sleeping or reading in these rooms and is out of them (it leaves the
    house, or is no longer let into them). Does not commit."""
    if not room_ids:
        return
    await _put_out(db, room_ids, character_id)
    row = (await db.execute(text("SELECT sleep_house_room_id, reading_house_room_id FROM characters WHERE id = :c"),
                            {"c": character_id})).fetchone()
    if not row:
        return
    if row[0] in room_ids:
        try:
            await _settle_regen(character_id)
        except HTTPException:
            pass  # the rest slept so far is lost, the character still wakes up
        await db.execute(text(
            "UPDATE characters SET asleep_since = NULL, sleep_regen_factor = NULL, sleep_house_room_id = NULL "
            "WHERE id = :c"), {"c": character_id})
    if row[1] in room_ids:
        await _end_reading(db, character_id, await _db_now(db))


@router.post("/rooms/{room_id}/read")
async def start_reading(
    room_id: int,
    body: CharacterIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """The character sits down to read in a library (activity locked until it stops)."""
    room, _ = await _room_user(db, room_id, body.character_id, user, ("library",), "Читают в библиотеке",
                               "Во время боя не читают")
    now = await _db_now(db)
    done = await db.execute(text(
        "UPDATE characters SET reading_since = :t, reading_house_room_id = :r "
        "WHERE id = :c AND reading_since IS NULL AND asleep_since IS NULL"),
        {"t": now, "r": room.id, "c": body.character_id})
    if not done.rowcount:
        await db.rollback()
        raise HTTPException(409, "Персонаж уже читает или спит")
    await db.commit()
    return {"reading": True, "reading_since": now, "cap": LIBRARY_CAP.get(room.level, 0.0)}


@router.post("/stop-reading")
async def stop_reading(
    body: CharacterIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Ends reading wherever the character reads; the library blessing earned is granted."""
    await _own_character(db, body.character_id, user)
    result = await _end_reading(db, body.character_id, await _db_now(db))
    if result is None:
        return {"reading": False, "hours": 0, "bonus": 0.0, "value": 0.0, "expires_at": None}
    await db.commit()
    return {"reading": False, **result}


async def _pray_next(db: AsyncSession, character_ids: List[int], now: datetime) -> Dict[int, datetime]:
    """When each character may pray again (only those still waiting)."""
    if not character_ids:
        return {}
    rows = (await db.execute(select(models.HouseShrineUse).where(
        models.HouseShrineUse.character_id.in_(character_ids)))).scalars().all()
    out = {}
    for row in rows:
        next_at = row.last_at + timedelta(hours=SHRINE_COOLDOWN_HOURS)
        if next_at > now:
            out[row.character_id] = next_at
    return out


@router.post("/rooms/{room_id}/pray")
async def pray(
    room_id: int,
    body: PrayIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """A shrine gives one blessing for 24 h, once per 24 h per character; a new prayer
    replaces the previous shrine blessing."""
    room, _ = await _room_user(db, room_id, body.character_id, user, ("shrine",), "Молятся в святилище",
                               "Во время боя не молятся")
    now = await _db_now(db)
    use = await db.get(models.HouseShrineUse, body.character_id)
    if use is not None and use.last_at + timedelta(hours=SHRINE_COOLDOWN_HOURS) > now:
        next_at = use.last_at + timedelta(hours=SHRINE_COOLDOWN_HOURS)
        raise HTTPException(409, f"Святилище ещё не услышит вас — снова можно через {_left(next_at - now)}")
    # The rest so far is credited under the old blessing before a new one replaces it.
    await _settle_regen(body.character_id)
    if use is None:
        db.add(models.HouseShrineUse(character_id=body.character_id, last_at=now))
    else:
        claimed = await db.execute(update(models.HouseShrineUse).where(
            models.HouseShrineUse.character_id == body.character_id,
            models.HouseShrineUse.last_at <= now - timedelta(hours=SHRINE_COOLDOWN_HOURS)).values(last_at=now))
        if not claimed.rowcount:
            await db.rollback()
            raise HTTPException(409, "Святилище ещё не услышит вас")
    value = SHRINE_BONUS.get(room.level, 0.0)
    expires_at = now + timedelta(hours=BUFF_HOURS)
    await _upsert_buff(db, body.character_id, "shrine", body.blessing, value, expires_at)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Святилище ещё не услышит вас")
    return {"blessing": body.blessing, "value": value, "expires_at": expires_at,
            "next_at": now + timedelta(hours=SHRINE_COOLDOWN_HOURS)}


async def _trophy_counts(db: AsyncSession, room_ids: List[int]) -> Dict[int, int]:
    """Elite trophies placed in each room."""
    if not room_ids:
        return {}
    rows = await db.execute(text(
        "SELECT f.room_id, COUNT(*) FROM house_furniture f JOIN items i ON i.id = f.item_id "
        "WHERE f.room_id IN :ids AND i.is_elite_trophy = 1 GROUP BY f.room_id")
        .bindparams(bindparam("ids", expanding=True)), {"ids": list(room_ids)})
    return {r[0]: int(r[1]) for r in rows.fetchall()}


def _house_trophy_total(rooms: List[models.HouseRoom], counts: Dict[int, int],
                        levels: Optional[Dict[int, int]] = None) -> float:
    """A house's battle experience bonus: +1 % per elite trophy, a hall counting at most
    its slots, at most 15 % in all."""
    pieces = sum(min(counts.get(r.id, 0), TROPHY_SLOTS.get((levels or {}).get(r.id, r.level), 0))
                 for r in rooms if r.room_type == TROPHY_HALL)
    return round(min(pieces * TROPHY_BONUS_PER_PIECE, TROPHY_BONUS_CAP), 4)


async def _trophy_bonus(db: AsyncSession, character_ids: List[int], now: datetime) -> Dict[int, float]:
    """Each character's trophy bonus: the best active house it owns or lives in (guests get none).
    inventory-service counts the same for battle experience."""
    if not character_ids:
        return {}
    homes = (await db.execute(select(models.House.id, models.House.owner_character_id).where(
        models.House.owner_character_id.in_(character_ids), models.House.status == "active",
        models.House.plot_id.isnot(None)))).all()
    homes += (await db.execute(select(models.House.id, models.HouseResident.character_id)
                               .join(models.HouseResident, models.HouseResident.house_id == models.House.id)
                               .where(models.HouseResident.character_id.in_(character_ids),
                                      models.House.status == "active", models.House.plot_id.isnot(None)))).all()
    if not homes:
        return {}
    halls = (await db.execute(select(models.HouseRoom).where(
        models.HouseRoom.house_id.in_(sorted({h for h, _ in homes})), models.HouseRoom.room_type == TROPHY_HALL))).scalars().all()
    counts = await _trophy_counts(db, [r.id for r in halls])
    levels = {r.id: _level_now(r.level, r.upgrade_to_level, r.upgrade_complete_at, now) for r in halls}
    by_house = {h: _house_trophy_total([r for r in halls if r.house_id == h], counts, levels) for h, _ in homes}
    out: Dict[int, float] = {}
    for house_id, character_id in homes:
        out[character_id] = max(out.get(character_id, 0.0), by_house[house_id])
    return out


@router.post("/{house_id}/guests")
async def invite_guest(
    house_id: int,
    body: GuestIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """The owner invites a player character: it may enter the guest rooms and sleep there."""
    house = await _owned_house(db, house_id, body.character_id, user)
    _require_active(house)
    if body.guest_character_id == house.owner_character_id:
        raise HTTPException(400, "Хозяин и так живёт в доме")
    row = (await db.execute(text("SELECT is_npc, user_id FROM characters WHERE id = :cid"),
                            {"cid": body.guest_character_id})).fetchone()
    if not row or row[0] or row[1] is None:
        raise HTTPException(404, "Персонаж не найден")
    if (await db.execute(select(models.HouseResident.id).where(
            models.HouseResident.house_id == house_id,
            models.HouseResident.character_id == body.guest_character_id))).first():
        raise HTTPException(409, "Этот персонаж живёт в доме — гостем ему быть не нужно")
    guest = models.HouseGuest(house_id=house_id, character_id=body.guest_character_id)
    db.add(guest)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Этот персонаж уже гость дома")
    return {"id": guest.id}


@router.delete("/{house_id}/guests/{guest_character_id}")
async def remove_guest(
    house_id: int,
    guest_character_id: int,
    character_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """The owner sends a guest away, or the guest leaves (waking up if it sleeps here)."""
    await _own_character(db, character_id, user)
    house = await _house(db, house_id)
    if character_id not in (house.owner_character_id, guest_character_id):
        raise HTTPException(403, "Это может только хозяин дома или сам гость")
    guest = (await db.execute(select(models.HouseGuest).where(
        models.HouseGuest.house_id == house_id,
        models.HouseGuest.character_id == guest_character_id))).scalar_one_or_none()
    if guest is None:
        raise HTTPException(404, "Гость не найден")
    await _leave_rooms(db, [r.id for r in await _rooms_of(db, house_id)], guest_character_id)
    await db.delete(guest)
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Entering, walking about and leaving the house (stage 7)
# ---------------------------------------------------------------------------

class EnterIn(CharacterIn):
    room_id: Optional[int] = None


async def _place(db: AsyncSession, house: models.House, character_id: int, room_id: Optional[int],
                 user: UserRead) -> dict:
    """Puts the character into a room of the house (the given one, or the first it may enter in
    plan order): it stands in the house's location, is let in, free to act. Instant — no stamina,
    no time, no post anywhere."""
    from main import check_not_activity_locked, check_not_gathering, check_not_in_battle

    character = await _own_character(db, character_id, user)
    _require_active(house)
    plot = await _plot(db, house.plot_id)
    if character["location_id"] is None or int(character["location_id"]) != plot.location_id:
        raise HTTPException(403, NOT_HERE)
    await _settle_rooms(db, house.id)
    rooms = await _rooms_of(db, house.id)
    allowed = await _membership(db, house, character_id, rooms)
    if allowed is None:
        raise HTTPException(403, "Вас не пускали в этот дом")
    built = {r.id for r in rooms if r.level >= 1}
    if room_id is not None:
        if room_id not in {r.id for r in rooms}:
            raise HTTPException(404, "Комната не найдена")
        if room_id not in allowed:
            raise HTTPException(403, "Хозяин не пускал этого персонажа в эту комнату")
        if room_id not in built:
            raise HTTPException(409, "Комната ещё строится")
    else:
        room_id = next((r for r in allowed if r in built), None)
        if room_id is None:
            raise HTTPException(409, "В доме нет готовой комнаты, куда вас пускают")
    # Asleep or reading the character stays where it is (the lock says why).
    await check_not_activity_locked(db, character_id)
    await check_not_in_battle(db, character_id, "Во время боя в дом не войти")
    await check_not_gathering(db, character_id, "Во время добычи в дом не войти")
    await db.execute(text("UPDATE characters SET house_room_id = :r WHERE id = :c"),
                     {"r": room_id, "c": character_id})
    await db.commit()
    room = next(r for r in rooms if r.id == room_id)
    return {"house_id": house.id, "room_id": room.id, "room_type": room.room_type, "room_name": room.name}


@router.post("/{house_id}/enter")
async def enter_house(
    house_id: int,
    body: EnterIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """The character enters the house: into `room_id`, or the first room it may enter."""
    return await _place(db, await _house(db, house_id), body.character_id, body.room_id, user)


@router.post("/rooms/{room_id}/go")
async def go_to_room(
    room_id: int,
    body: CharacterIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """The character walks into another room of the house (or enters the house right into it)."""
    room = await _room(db, room_id)
    return await _place(db, await _house(db, room.house_id), body.character_id, room_id, user)


@router.post("/{house_id}/leave")
async def leave_house(
    house_id: int,
    body: CharacterIn,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """The character steps out of the house into its location (nothing happens if it is not inside)."""
    from main import check_not_activity_locked

    await _own_character(db, body.character_id, user)
    room_ids = [r.id for r in await _rooms_of(db, house_id)]
    current = (await db.execute(text("SELECT house_room_id FROM characters WHERE id = :c"),
                                {"c": body.character_id})).scalar()
    if current is not None and current in room_ids:
        await check_not_activity_locked(db, body.character_id)
        await _put_out(db, room_ids, body.character_id)
        await db.commit()
    return {"house_id": house_id, "room_id": None}
