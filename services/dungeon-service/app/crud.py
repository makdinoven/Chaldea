import logging
from collections import defaultdict, deque
from typing import List, Optional, Dict, Tuple

from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from models import Dungeon, DungeonRoom, DungeonCorridor
from schemas import (
    DungeonCreate, DungeonUpdate,
    DungeonRoomCreate, DungeonRoomUpdate,
    DungeonCorridorCreate, DungeonCorridorUpdate,
    DungeonValidationResponse,
)

logger = logging.getLogger(__name__)


# ===========================
#  Dungeon CRUD
# ===========================

async def create_dungeon(session: AsyncSession, data: DungeonCreate) -> Dungeon:
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

async def create_room(
    session: AsyncSession, dungeon_id: int, data: DungeonRoomCreate
) -> DungeonRoom:
    # Validate dungeon exists
    await get_dungeon(session, dungeon_id)

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

    corridor = DungeonCorridor(dungeon_id=dungeon_id, **data.dict())
    session.add(corridor)
    await session.commit()
    await session.refresh(corridor)
    return corridor


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
    for r in rooms:
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
            if r.id in unreachable:
                errors.append(
                    f"Комната '{r.name}' (id={r.id}) недостижима от входа"
                )

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
