import logging
from collections import defaultdict, deque
from typing import List, Optional, Dict, Tuple

from fastapi import HTTPException
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from models import Dungeon, DungeonRoom, DungeonCorridor
from schemas import (
    DungeonCreate, DungeonUpdate,
    DungeonRoomCreate, DungeonRoomUpdate,
    DungeonCorridorCreate, DungeonCorridorUpdate,
    DungeonValidationResponse,
    RoomPositionItem,
    validate_room_config,
    _parse_outcome_data,
    DUNGEON_KEYS,
)

logger = logging.getLogger(__name__)


# ===========================
#  Dungeon CRUD
# ===========================

async def location_exists(session: AsyncSession, location_id: int) -> bool:
    """`Locations` belongs to locations-service (shared DB, read-only here)."""
    row = (await session.execute(
        text("SELECT id FROM Locations WHERE id = :lid"), {"lid": location_id},
    )).fetchone()
    return row is not None


async def _require_location(session: AsyncSession, location_id: int) -> None:
    if not await location_exists(session, location_id):
        raise HTTPException(status_code=400, detail=f"Локация {location_id} не найдена")


async def create_dungeon(session: AsyncSession, data: DungeonCreate) -> Dungeon:
    await _require_location(session, data.location_id)
    dungeon = Dungeon(**data.dict())
    session.add(dungeon)
    await session.commit()
    await session.refresh(dungeon)
    return dungeon


async def list_dungeons(
    session: AsyncSession, skip: int = 0, limit: int = 50
) -> List[Dungeon]:
    stmt = select(Dungeon).order_by(Dungeon.id.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_dungeon(session: AsyncSession, dungeon_id: int) -> Dungeon:
    stmt = select(Dungeon).where(Dungeon.id == dungeon_id)
    result = await session.execute(stmt)
    dungeon = result.scalar_one_or_none()
    if not dungeon:
        raise HTTPException(status_code=404, detail="Подземелье не найдено")
    return dungeon


async def get_dungeon_detail(session: AsyncSession, dungeon_id: int) -> Dungeon:
    """Get dungeon with eagerly loaded rooms and corridors."""
    stmt = (
        select(Dungeon)
        .where(Dungeon.id == dungeon_id)
        .options(
            selectinload(Dungeon.rooms),
            selectinload(Dungeon.corridors),
        )
    )
    result = await session.execute(stmt)
    dungeon = result.scalar_one_or_none()
    if not dungeon:
        raise HTTPException(status_code=404, detail="Подземелье не найдено")
    return dungeon


async def update_dungeon(
    session: AsyncSession, dungeon_id: int, data: DungeonUpdate
) -> Dungeon:
    dungeon = await get_dungeon(session, dungeon_id)
    update_data = data.dict(exclude_unset=True)
    if update_data.get("location_id") is not None:
        await _require_location(session, update_data["location_id"])
    for key, value in update_data.items():
        setattr(dungeon, key, value)
    await session.commit()
    await session.refresh(dungeon)
    return dungeon


async def delete_dungeon(session: AsyncSession, dungeon_id: int) -> None:
    dungeon = await get_dungeon(session, dungeon_id)
    await session.delete(dungeon)
    await session.commit()


# ===========================
#  Room CRUD
# ===========================

async def _check_room_targets(
    session: AsyncSession, dungeon_id: int, room_type: str, cfg, own_room_id: Optional[int] = None,
) -> None:
    """Teleport targets (teleport room + event teleport outcomes) must be rooms
    of the SAME dungeon (FEAT-175: the live dungeon had a teleport to -15)."""
    if not isinstance(cfg, dict):
        return
    targets = []
    if room_type == "teleport" and cfg.get("target_room_id") is not None:
        targets.append(cfg["target_room_id"])
    if room_type == "teleport" and isinstance(cfg.get("target_room_ids"), list):
        targets.extend(cfg["target_room_ids"])
    if room_type == "event":
        for c in cfg.get("choices") or []:
            if isinstance(c, dict) and c.get("outcome_type") == "teleport":
                targets.append(_parse_outcome_data(c.get("outcome_data")).get("target_room_id"))
    lever = cfg.get("lever_corridor_id")
    if lever is not None:
        row = (await session.execute(
            select(DungeonCorridor.id).where(DungeonCorridor.id == lever, DungeonCorridor.dungeon_id == dungeon_id)
        )).first()
        if row is None:
            raise HTTPException(status_code=400, detail=f"Коридор {lever} для рычага не найден в этом подземелье")
    for t in targets:
        if own_room_id is not None and t == own_room_id:
            raise HTTPException(status_code=400, detail="Телепорт не может вести в эту же комнату")
        row = (await session.execute(
            select(DungeonRoom.id).where(DungeonRoom.id == t, DungeonRoom.dungeon_id == dungeon_id)
        )).first()
        if row is None:
            raise HTTPException(
                status_code=400,
                detail=f"Комната {t} для телепорта не найдена в этом подземелье",
            )


async def create_room(
    session: AsyncSession, dungeon_id: int, data: DungeonRoomCreate
) -> DungeonRoom:
    # Validate dungeon exists
    await get_dungeon(session, dungeon_id)
    await _check_room_targets(session, dungeon_id, data.room_type, data.room_config)

    room = DungeonRoom(dungeon_id=dungeon_id, **data.dict())
    session.add(room)
    await session.commit()
    await session.refresh(room)
    return room


async def get_room(session: AsyncSession, room_id: int) -> DungeonRoom:
    stmt = select(DungeonRoom).where(DungeonRoom.id == room_id)
    result = await session.execute(stmt)
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    return room


async def update_room(
    session: AsyncSession, room_id: int, data: DungeonRoomUpdate
) -> DungeonRoom:
    room = await get_room(session, room_id)
    update_data = data.dict(exclude_unset=True)
    # FEAT-175: validate the resulting config against the resulting type —
    # an update may send only one of the two.
    new_type = update_data.get("room_type") or room.room_type
    new_cfg = update_data["room_config"] if "room_config" in update_data else room.room_config
    if "room_type" in update_data or "room_config" in update_data:
        try:
            validate_room_config(new_type, new_cfg)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        await _check_room_targets(session, room.dungeon_id, new_type, new_cfg, own_room_id=room.id)
    for key, value in update_data.items():
        setattr(room, key, value)
    await session.commit()
    await session.refresh(room)
    return room


async def delete_room(session: AsyncSession, room_id: int) -> None:
    room = await get_room(session, room_id)
    await session.delete(room)
    await session.commit()


# ===========================
#  Bulk Room Position Update
# ===========================

async def bulk_update_room_positions(
    session: AsyncSession, dungeon_id: int, positions: List[RoomPositionItem]
) -> int:
    """Update position_x and position_y for multiple rooms at once."""
    # Validate dungeon exists
    await get_dungeon(session, dungeon_id)

    room_ids = [p.room_id for p in positions]

    # Fetch all requested rooms in one query
    stmt = select(DungeonRoom).where(DungeonRoom.id.in_(room_ids))
    result = await session.execute(stmt)
    rooms = {r.id: r for r in result.scalars().all()}

    # Verify all room_ids exist and belong to this dungeon
    for rid in room_ids:
        if rid not in rooms:
            raise HTTPException(
                status_code=400,
                detail=f"Комната {rid} не найдена",
            )
        if rooms[rid].dungeon_id != dungeon_id:
            raise HTTPException(
                status_code=400,
                detail=f"Комната {rid} не принадлежит подземелью {dungeon_id}",
            )

    # Apply updates
    for p in positions:
        room = rooms[p.room_id]
        room.position_x = p.position_x
        room.position_y = p.position_y

    await session.commit()
    return len(positions)


# ===========================
#  Corridor CRUD
# ===========================

async def create_corridor(
    session: AsyncSession, dungeon_id: int, data: DungeonCorridorCreate
) -> DungeonCorridor:
    # Validate dungeon exists
    await get_dungeon(session, dungeon_id)

    # Validate both rooms exist and belong to this dungeon
    from_room = await get_room(session, data.from_room_id)
    if from_room.dungeon_id != dungeon_id:
        raise HTTPException(
            status_code=400,
            detail=f"Комната {data.from_room_id} не принадлежит подземелью {dungeon_id}",
        )

    to_room = await get_room(session, data.to_room_id)
    if to_room.dungeon_id != dungeon_id:
        raise HTTPException(
            status_code=400,
            detail=f"Комната {data.to_room_id} не принадлежит подземелью {dungeon_id}",
        )

    # Check for duplicate corridor
    stmt = select(DungeonCorridor).where(
        DungeonCorridor.from_room_id == data.from_room_id,
        DungeonCorridor.to_room_id == data.to_room_id,
    )
    result = await session.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Коридор между этими комнатами уже существует",
        )

    payload = data.dict()
    _check_passage(from_room, to_room, payload["passage_type"])
    if payload["passage_type"] == "drop":
        payload["is_bidirectional"] = False  # a drop is one way: down
    corridor = DungeonCorridor(dungeon_id=dungeon_id, **payload)
    session.add(corridor)
    await session.commit()
    await session.refresh(corridor)
    return corridor


def _passage_problem(from_room: DungeonRoom, to_room: DungeonRoom, passage: str) -> Optional[str]:
    """What is wrong with joining these rooms by this kind of passage (None = fine)."""
    a, b = from_room.floor or 1, to_room.floor or 1
    if passage == "corridor":
        if a != b:
            return "Комнаты на разных этажах соединяются лестницей, провалом или подъёмником"
        return None
    if abs(a - b) != 1:
        return "Лестница, провал и подъёмник ведут только на соседний этаж"
    if passage == "drop" and b != a + 1:
        return "Провал ведёт только вниз — из верхней комнаты в нижнюю"
    return None


def _check_passage(from_room: DungeonRoom, to_room: DungeonRoom, passage: str) -> None:
    problem = _passage_problem(from_room, to_room, passage)
    if problem:
        raise HTTPException(status_code=400, detail=problem)


async def get_corridor(session: AsyncSession, corridor_id: int) -> DungeonCorridor:
    stmt = select(DungeonCorridor).where(DungeonCorridor.id == corridor_id)
    result = await session.execute(stmt)
    corridor = result.scalar_one_or_none()
    if not corridor:
        raise HTTPException(status_code=404, detail="Коридор не найден")
    return corridor


async def update_corridor(
    session: AsyncSession, corridor_id: int, data: DungeonCorridorUpdate
) -> DungeonCorridor:
    corridor = await get_corridor(session, corridor_id)
    update_data = data.dict(exclude_unset=True)
    if update_data.get("passage_type") is None:
        update_data.pop("passage_type", None)
    passage = update_data.get("passage_type", corridor.passage_type or "corridor")
    _check_passage(await get_room(session, corridor.from_room_id), await get_room(session, corridor.to_room_id),
                   passage)
    if passage == "drop":
        update_data["is_bidirectional"] = False
    for key, value in update_data.items():
        setattr(corridor, key, value)
    await session.commit()
    await session.refresh(corridor)
    return corridor


async def delete_corridor(session: AsyncSession, corridor_id: int) -> None:
    corridor = await get_corridor(session, corridor_id)
    await session.delete(corridor)
    await session.commit()


# ===========================
#  Dungeon Validation
# ===========================

async def validate_dungeon(
    session: AsyncSession, dungeon_id: int
) -> DungeonValidationResponse:
    """
    Validate dungeon graph integrity:
    - Has at least one entrance room
    - Has at least one boss room
    - All rooms reachable from entrance (BFS)
    - Detect orphan rooms (no corridors at all)
    """
    dungeon = await get_dungeon_detail(session, dungeon_id)
    rooms = dungeon.rooms
    corridors = dungeon.corridors

    errors: List[str] = []
    warnings: List[str] = []

    if not rooms:
        errors.append("Подземелье не содержит комнат")
        return DungeonValidationResponse(valid=False, errors=errors, warnings=warnings)

    # Check entrance
    entrance_rooms = [r for r in rooms if r.is_entrance]
    if not entrance_rooms:
        errors.append("Подземелье не имеет комнаты-входа (is_entrance=true)")
    elif len(entrance_rooms) > 1:
        warnings.append(
            f"Найдено {len(entrance_rooms)} комнат-входов — рекомендуется одна"
        )

    # Check boss room
    boss_rooms = [r for r in rooms if r.is_boss_room]
    if not boss_rooms:
        errors.append("Подземелье не имеет комнаты босса (is_boss_room=true)")

    # Build adjacency list (considering bidirectional corridors)
    room_ids = {r.id for r in rooms}
    adjacency: Dict[int, List[int]] = defaultdict(list)
    connected_rooms = set()

    for c in corridors:
        adjacency[c.from_room_id].append(c.to_room_id)
        connected_rooms.add(c.from_room_id)
        connected_rooms.add(c.to_room_id)
        if c.is_bidirectional:
            adjacency[c.to_room_id].append(c.from_room_id)

    # Detect orphan rooms (not connected to any corridor)
    # The mana core room is reached by the path revealed after the boss
    # (enter_mana_core), not by a corridor — it may legitimately have none.
    for r in rooms:
        if r.is_mana_core_room and r.id not in connected_rooms:
            continue
        if r.id not in connected_rooms and len(rooms) > 1:
            warnings.append(
                f"Комната '{r.name}' (id={r.id}) не имеет коридоров — возможно, так задумано"
            )

    # BFS from entrance to check reachability
    if entrance_rooms:
        entrance_id = entrance_rooms[0].id
        visited = set()
        queue = deque([entrance_id])
        visited.add(entrance_id)

        while queue:
            current = queue.popleft()
            for neighbor in adjacency.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        unreachable = room_ids - visited
        for r in rooms:
            if r.id in unreachable and not (r.is_mana_core_room and r.id not in connected_rooms):
                errors.append(
                    f"Комната '{r.name}' (id={r.id}) недостижима от входа"
                )

    # FEAT-175: content checks that used to fail only at play time
    room_ids_all = {r.id for r in rooms}
    for r in rooms:
        cfg = r.room_config if isinstance(r.room_config, dict) else {}
        if r.room_type in ("battle", "boss") and not cfg.get("mob_template_ids"):
            errors.append(f"Комната '{r.name}' (id={r.id}): не заданы мобы для боя")
        if r.room_type == "event" and not cfg.get("choices"):
            warnings.append(f"Комната-событие '{r.name}' (id={r.id}) без вариантов выбора")
        if r.room_type == "teleport" and cfg.get("portal") == "red":
            targets = cfg.get("target_room_ids") or []
            if not targets:
                warnings.append(f"Красный портал '{r.name}' (id={r.id}) без комнат — никуда не перенесёт")
            for t in targets:
                if t not in room_ids_all:
                    errors.append(f"Красный портал '{r.name}' (id={r.id}) ведёт в несуществующую комнату {t}")
        elif r.room_type == "teleport":
            t = cfg.get("target_room_id")
            if t is None:
                warnings.append(f"Телепорт '{r.name}' (id={r.id}) без цели — работает как пустая комната")
            elif t not in room_ids_all:
                errors.append(f"Телепорт '{r.name}' (id={r.id}) ведёт в несуществующую комнату {t}")
        if r.room_type == "event":
            for idx, c in enumerate(cfg.get("choices") or []):
                if isinstance(c, dict) and c.get("outcome_type") == "teleport":
                    try:
                        t = _parse_outcome_data(c.get("outcome_data")).get("target_room_id")
                    except ValueError:
                        t = None
                    if t not in room_ids_all:
                        errors.append(
                            f"Событие '{r.name}' (id={r.id}), вариант {idx + 1}: "
                            f"телепорт в несуществующую комнату {t}"
                        )
    # Floors: a room moved to another floor may leave a passage pointing the wrong way.
    by_id = {r.id: r for r in rooms}
    for c in corridors:
        a, b = by_id.get(c.from_room_id), by_id.get(c.to_room_id)
        if a is None or b is None:
            continue
        problem = _passage_problem(a, b, c.passage_type or "corridor")
        if problem:
            errors.append(f"«{a.name}» — «{b.name}»: {problem}")
    floors = {r.floor or 1 for r in rooms}
    for f in range(1, max(floors, default=1) + 1):
        if f not in floors:
            warnings.append(f"Этаж {f} пуст — ниже него ничего не достать")
    # A lever-only lock no lever in the dungeon works stays shut for good.
    levers = {(r.room_config or {}).get("lever_corridor_id") for r in rooms if isinstance(r.room_config, dict)}

    # Locked doors: a key nobody can find leaves the door to picking (or shut for good).
    keys_given = set()
    for r in rooms:
        cfg = r.room_config if isinstance(r.room_config, dict) else {}
        if r.room_type in ("treasure", "battle") and cfg.get("key_reward"):
            keys_given.add(cfg["key_reward"])
        if r.room_type == "event":
            for c in cfg.get("choices") or []:
                if isinstance(c, dict) and c.get("outcome_type") == "key":
                    try:
                        keys_given.add(_parse_outcome_data(c.get("outcome_data")).get("key"))
                    except ValueError:
                        pass
    names = {r.id: r.name for r in rooms}
    for c in corridors:
        lock = c.lock_config if isinstance(c.lock_config, dict) else None
        if lock and lock.get("lever") and c.id not in levers and not lock.get("key"):
            errors.append(f"Дверь «{names.get(c.from_room_id)}» — «{names.get(c.to_room_id)}»: "
                          f"открывается рычагом, но рычага в подземелье нет")
            continue
        if not lock or not lock.get("key") or lock.get("key") in keys_given or c.id in levers:
            continue
        where = f"Дверь «{names.get(c.from_room_id)}» — «{names.get(c.to_room_id)}»"
        key_name = DUNGEON_KEYS.get(lock.get("key"), lock.get("key"))
        if lock.get("pickable", True) is False:
            errors.append(f"{where}: {key_name} нигде не выдаётся, а взлом запрещён — дверь не открыть")
        else:
            warnings.append(f"{where}: {key_name} нигде не выдаётся — открыть можно только взломом")
    # Rooms the party is thrown into (portals, teleporting choices, drops) need a way
    # out that wants no key or lever: a door is unbolted from behind its lock, a lift is not.
    arrivals: Dict[int, str] = {}
    for r in rooms:
        cfg = r.room_config if isinstance(r.room_config, dict) else {}
        if r.room_type == "teleport" and cfg.get("portal") == "red":
            for t in cfg.get("target_room_ids") or []:
                arrivals.setdefault(t, f"красный портал «{r.name}»")
        elif r.room_type == "teleport" and cfg.get("target_room_id") is not None:
            arrivals.setdefault(cfg["target_room_id"], f"портал «{r.name}»")
        if r.room_type == "event":
            for c in cfg.get("choices") or []:
                if isinstance(c, dict) and c.get("outcome_type") == "teleport":
                    try:
                        t = _parse_outcome_data(c.get("outcome_data")).get("target_room_id")
                    except ValueError:
                        t = None
                    if t is not None:
                        arrivals.setdefault(t, f"событие «{r.name}»")
    for c in corridors:
        if (c.passage_type or "corridor") == "drop":
            arrivals.setdefault(c.to_room_id, f"провал из «{names.get(c.from_room_id)}»")

    def _free_way_out(room_id: int) -> bool:
        for c in corridors:
            locked = isinstance(c.lock_config, dict) and (c.lock_config.get("key") or c.lock_config.get("lever"))
            if c.from_room_id == room_id and not locked:
                return True
            if c.to_room_id == room_id and c.is_bidirectional and (
                not locked or (c.passage_type or "corridor") != "lift"
            ):
                return True
        return False

    for room_id, source in arrivals.items():
        room = by_id.get(room_id)
        if room is None or room.is_boss_room or _free_way_out(room_id):
            continue
        warnings.append(
            f"Из «{room.name}» (сюда ведёт {source}) не выйти без ключа или рычага — группа может застрять"
        )

    mana_core_rooms = [r for r in rooms if r.is_mana_core_room]
    if mana_core_rooms and (dungeon.mana_core_chance or 0) <= 0:
        warnings.append("Есть комната ядра маны, но шанс ядра маны равен 0")

    # Check deadend rooms
    for r in rooms:
        if r.room_type == "deadend":
            outgoing = [c for c in corridors if c.from_room_id == r.id]
            if outgoing:
                warnings.append(
                    f"Комната-тупик '{r.name}' (id={r.id}) имеет выходящие коридоры"
                )

    valid = len(errors) == 0
    return DungeonValidationResponse(valid=valid, errors=errors, warnings=warnings)
