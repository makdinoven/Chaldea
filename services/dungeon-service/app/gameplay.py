"""
Session management and party formation logic for dungeon-service.

All functions use async SQLAlchemy and follow the service's async pattern.
"""

import logging
import math
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from models import (
    Dungeon,
    DungeonRoom,
    DungeonCorridor,
    DungeonSession,
    DungeonSessionMember,
    DungeonSessionInventory,
    DungeonRoomVisit,
    DungeonRoomState,
)
from schemas import (
    CorridorEventResponse,
    DistributeLootRequest,
    DistributeLootResponse,
    ExploredCorridorInfo,
    ExploredRoomInfo,
    FinalizeRequest,
    FinalizeResponse,
    FleeItemInfo,
    FleeRequest,
    FleeResponse,
    InteractResponse,
    MoveResponse,
    SessionMemberResponse,
    SessionResponse,
    RoomExitResponse,
    RoomViewResponse,
    GroupInventoryItemResponse,
    SessionStateResponse,
)
import session_state
import ws_manager
import http_clients

logger = logging.getLogger("dungeon-service.gameplay")


# =====================================================================
# Helpers
# =====================================================================

def _build_room_config_visible(
    room: DungeonRoom,
    room_state: Optional[DungeonRoomState] = None,
) -> dict:
    """Build a safe subset of room_config visible to players."""
    cfg = room.room_config or {}
    visible: dict = {}

    if room.room_type == "event":
        if cfg.get("text"):
            visible["text"] = cfg["text"]
        choices = cfg.get("choices", [])
        # Only show choice text, not outcome data
        visible["choices"] = [
            c.get("text", c) if isinstance(c, dict) else str(c)
            for c in choices
        ]
        if room_state and room_state.event_choice_index is not None:
            visible["choice_made"] = room_state.event_choice_index

    elif room.room_type == "treasure":
        if room_state:
            visible["loot_collected"] = room_state.loot_collected

    elif room.room_type == "boss":
        if room_state:
            visible["loot_collected"] = room_state.loot_collected

    elif room.room_type == "rest":
        if cfg.get("heal_percent") is not None:
            visible["heal_percent"] = cfg["heal_percent"]
        if cfg.get("wait_seconds") is not None:
            visible["wait_seconds"] = cfg["wait_seconds"]
        if cfg.get("gold_cost") is not None:
            visible["gold_cost"] = cfg["gold_cost"]

    elif room.room_type == "merchant":
        visible["items"] = cfg.get("items", [])

    elif room.room_type == "trap":
        # Don't reveal stat_check or difficulty — just show description
        pass

    elif room.room_type == "teleport":
        visible["target_room_id"] = cfg.get("target_room_id")

    return visible


async def _get_session(db: AsyncSession, session_id: int) -> DungeonSession:
    """Load a dungeon session by id, raising 404 if not found."""
    stmt = (
        select(DungeonSession)
        .where(DungeonSession.id == session_id)
        .options(selectinload(DungeonSession.members))
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Сессия подземелья не найдена")
    return session


async def _build_session_response(
    db: AsyncSession, session: DungeonSession, dungeon_id: int
) -> SessionResponse:
    """Build a SessionResponse from a DungeonSession ORM object."""
    # Explicitly query members to avoid lazy-loading issues in async SQLAlchemy
    members_stmt = select(DungeonSessionMember).where(
        DungeonSessionMember.session_id == session.id
    )
    members_result = await db.execute(members_stmt)
    members = members_result.scalars().all()

    members_resp: List[SessionMemberResponse] = []
    for m in members:
        try:
            profile = await http_clients.get_character_profile(m.character_id)
            name = profile.get("character_name", f"Персонаж #{m.character_id}")
        except Exception:
            name = f"Персонаж #{m.character_id}"

        members_resp.append(
            SessionMemberResponse(
                character_id=m.character_id,
                name=name,
                status=m.status,
                is_leader=(m.character_id == session.leader_character_id),
                user_id=m.user_id,
            )
        )

    return SessionResponse(
        session_id=session.id,
        dungeon_id=dungeon_id,
        status=session.status,
        leader_character_id=session.leader_character_id,
        members=members_resp,
    )


async def _get_room_exits(
    db: AsyncSession,
    room_id: int,
    dungeon_id: int,
    character_id: int,
    dungeon: Optional[Dungeon] = None,
) -> List[RoomExitResponse]:
    """
    Build exit list for a room.
    Considers bidirectional corridors and fog of war.
    """
    # Get corridors originating from this room
    stmt_from = select(DungeonCorridor).where(
        DungeonCorridor.dungeon_id == dungeon_id,
        DungeonCorridor.from_room_id == room_id,
    )
    result_from = await db.execute(stmt_from)
    corridors_from = result_from.scalars().all()

    # Get bidirectional corridors pointing TO this room (reverse direction)
    stmt_to = select(DungeonCorridor).where(
        DungeonCorridor.dungeon_id == dungeon_id,
        DungeonCorridor.to_room_id == room_id,
        DungeonCorridor.is_bidirectional == True,
    )
    result_to = await db.execute(stmt_to)
    corridors_to = result_to.scalars().all()

    # Get this character's visited rooms for fog of war
    stmt_visits = select(DungeonRoomVisit.room_id).where(
        DungeonRoomVisit.dungeon_id == dungeon_id,
        DungeonRoomVisit.character_id == character_id,
    )
    result_visits = await db.execute(stmt_visits)
    visited_room_ids = set(result_visits.scalars().all())

    exits: List[RoomExitResponse] = []

    for c in corridors_from:
        target_room_id = c.to_room_id
        explored = target_room_id in visited_room_ids

        # Get target room name and position (or "???" if not explored)
        target_position_x = None
        target_position_y = None
        if explored:
            room_stmt = select(DungeonRoom).where(DungeonRoom.id == target_room_id)
            room_result = await db.execute(room_stmt)
            target_room_obj = room_result.scalar_one_or_none()
            room_name = target_room_obj.name if target_room_obj else "???"
            if target_room_obj:
                target_position_x = target_room_obj.position_x
                target_position_y = target_room_obj.position_y
        else:
            room_name = "???"
            # Still fetch position for map rendering (fog of war shows location)
            pos_stmt = select(DungeonRoom.position_x, DungeonRoom.position_y).where(
                DungeonRoom.id == target_room_id
            )
            pos_result = await db.execute(pos_stmt)
            pos_row = pos_result.one_or_none()
            if pos_row:
                target_position_x = pos_row[0]
                target_position_y = pos_row[1]

        # Determine reliability based on dungeon stability type
        reliability = None
        if dungeon:
            if dungeon.stability_type == "unstable" and explored:
                reliability = "uncertain"
            elif dungeon.stability_type == "chaotic" and explored:
                reliability = "memory"

        exits.append(
            RoomExitResponse(
                corridor_id=c.id,
                to_room_id=target_room_id,
                to_room_name=room_name,
                stamina_cost=c.stamina_cost,
                explored=explored,
                reliability=reliability,
                position_x=target_position_x,
                position_y=target_position_y,
                source_handle=c.source_handle,
                target_handle=c.target_handle,
            )
        )

    # Reverse corridors (bidirectional) — swap source_handle/target_handle
    for c in corridors_to:
        target_room_id = c.from_room_id
        explored = target_room_id in visited_room_ids

        target_position_x = None
        target_position_y = None
        if explored:
            room_stmt = select(DungeonRoom).where(DungeonRoom.id == target_room_id)
            room_result = await db.execute(room_stmt)
            target_room_obj = room_result.scalar_one_or_none()
            room_name = target_room_obj.name if target_room_obj else "???"
            if target_room_obj:
                target_position_x = target_room_obj.position_x
                target_position_y = target_room_obj.position_y
        else:
            room_name = "???"
            pos_stmt = select(DungeonRoom.position_x, DungeonRoom.position_y).where(
                DungeonRoom.id == target_room_id
            )
            pos_result = await db.execute(pos_stmt)
            pos_row = pos_result.one_or_none()
            if pos_row:
                target_position_x = pos_row[0]
                target_position_y = pos_row[1]

        reliability = None
        if dungeon:
            if dungeon.stability_type == "unstable" and explored:
                reliability = "uncertain"
            elif dungeon.stability_type == "chaotic" and explored:
                reliability = "memory"

        exits.append(
            RoomExitResponse(
                corridor_id=c.id,
                to_room_id=target_room_id,
                to_room_name=room_name,
                stamina_cost=c.stamina_cost,
                explored=explored,
                reliability=reliability,
                position_x=target_position_x,
                position_y=target_position_y,
                source_handle=c.target_handle,  # SWAPPED for reverse
                target_handle=c.source_handle,  # SWAPPED for reverse
            )
        )

    return exits


# =====================================================================
# Session Management
# =====================================================================

async def create_session(
    db: AsyncSession,
    character_id: int,
    dungeon_id: int,
    user_id: int,
) -> SessionResponse:
    """
    Create a new dungeon session (party formation).
    Validates dungeon, cooldown, character location, and no active session.
    """
    # 1. Validate dungeon exists and is active
    stmt = select(Dungeon).where(Dungeon.id == dungeon_id)
    result = await db.execute(stmt)
    dungeon = result.scalar_one_or_none()
    if not dungeon:
        raise HTTPException(status_code=404, detail="Подземелье не найдено")
    if not dungeon.is_active:
        raise HTTPException(status_code=400, detail="Подземелье неактивно")

    # 2. Check dungeon cooldown (Redis first, then DB fallback)
    on_cooldown, remaining = await session_state.check_dungeon_cooldown(dungeon_id)
    if on_cooldown:
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        raise HTTPException(
            status_code=403,
            detail=f"Подземелье на кулдауне. Восстановится через {hours}ч {minutes}мин",
        )

    # DB fallback: if Redis key expired but latest session still has future cooldown_until
    latest_session_stmt = (
        select(DungeonSession)
        .where(
            DungeonSession.dungeon_id == dungeon_id,
            DungeonSession.cooldown_until.isnot(None),
        )
        .order_by(DungeonSession.finished_at.desc())
        .limit(1)
    )
    latest_result = await db.execute(latest_session_stmt)
    latest_session = latest_result.scalar_one_or_none()
    if latest_session and latest_session.cooldown_until:
        now = datetime.utcnow()
        if latest_session.cooldown_until > now:
            # Re-set Redis cooldown from DB data
            remaining_seconds = int(
                (latest_session.cooldown_until - now).total_seconds()
            )
            remaining_hours = max(1, remaining_seconds // 3600)
            await session_state.set_dungeon_cooldown(
                dungeon_id, latest_session.id, remaining_hours,
            )
            hours = remaining_seconds // 3600
            minutes = (remaining_seconds % 3600) // 60
            raise HTTPException(
                status_code=403,
                detail=f"Подземелье на кулдауне. Восстановится через {hours}ч {minutes}мин",
            )

    # 3. Verify character is at the dungeon's location
    profile = await http_clients.get_character_profile(character_id)
    char_location = profile.get("current_location_id")
    if char_location != dungeon.location_id:
        raise HTTPException(
            status_code=400,
            detail="Персонаж должен находиться на локации подземелья",
        )

    # 4. Verify character belongs to the authenticated user
    char_user_id = profile.get("user_id")
    if char_user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Этот персонаж не принадлежит вам",
        )

    # 5. Check character not already in a session
    active_session_id = await session_state.get_character_active_session(character_id)
    if active_session_id is not None:
        raise HTTPException(
            status_code=409,
            detail="Персонаж уже участвует в другой сессии подземелья",
        )

    # 6. Create DungeonSession
    session_obj = DungeonSession(
        dungeon_id=dungeon_id,
        leader_character_id=character_id,
        status="forming",
    )
    db.add(session_obj)
    await db.flush()

    # 7. Create DungeonSessionMember for leader
    member = DungeonSessionMember(
        session_id=session_obj.id,
        character_id=character_id,
        user_id=user_id,
        status="alive",
    )
    db.add(member)
    await db.commit()
    await db.refresh(session_obj)

    # 8. Set character active session in Redis
    await session_state.set_character_active_session(character_id, session_obj.id)

    # 9. Return session data
    return await _build_session_response(db, session_obj, dungeon_id)


async def invite_member(
    db: AsyncSession,
    session_id: int,
    inviter_character_id: int,
    invitee_character_id: int,
    user_id: int,
) -> SessionResponse:
    """
    Invite a character to the party. Inviter must be the leader.
    """
    # 1. Validate session exists and status='forming'
    session_obj = await _get_session(db, session_id)
    if session_obj.status != "forming":
        raise HTTPException(
            status_code=400,
            detail="Приглашать можно только во время формирования группы",
        )

    # 2. Validate inviter is the leader
    if session_obj.leader_character_id != inviter_character_id:
        raise HTTPException(
            status_code=403,
            detail="Только лидер может приглашать участников",
        )

    # 3. Validate inviter belongs to authenticated user
    inviter_profile = await http_clients.get_character_profile(inviter_character_id)
    if inviter_profile.get("user_id") != user_id:
        raise HTTPException(
            status_code=403,
            detail="Этот персонаж не принадлежит вам",
        )

    # 4. Validate party size < 4
    if len(session_obj.members) >= 4:
        raise HTTPException(
            status_code=400,
            detail="Максимальный размер группы — 4 участника",
        )

    # 5. Get invitee profile, verify same location as dungeon
    invitee_profile = await http_clients.get_character_profile(invitee_character_id)
    dungeon = await _get_dungeon_for_session(db, session_obj.dungeon_id)
    invitee_location = invitee_profile.get("current_location_id")
    if invitee_location != dungeon.location_id:
        raise HTTPException(
            status_code=400,
            detail="Приглашаемый персонаж должен находиться на локации подземелья",
        )

    # 6. Check invitee not already in a session
    active = await session_state.get_character_active_session(invitee_character_id)
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail="Приглашаемый персонаж уже участвует в другой сессии подземелья",
        )

    # 7. Check invitee not already in this session
    for m in session_obj.members:
        if m.character_id == invitee_character_id:
            raise HTTPException(
                status_code=409,
                detail="Этот персонаж уже в группе",
            )

    # 8. Add DungeonSessionMember to DB
    invitee_user_id = invitee_profile.get("user_id")
    new_member = DungeonSessionMember(
        session_id=session_id,
        character_id=invitee_character_id,
        user_id=invitee_user_id,
        status="alive",
    )
    db.add(new_member)
    await db.commit()
    await db.refresh(session_obj)

    # 9. Set invitee active session in Redis
    await session_state.set_character_active_session(invitee_character_id, session_id)

    # 10. Broadcast via WebSocket: member joined
    invitee_name = invitee_profile.get("name", f"Персонаж #{invitee_character_id}")
    await ws_manager.broadcast_to_session(session_id, {
        "type": "member_joined",
        "data": {
            "character_id": invitee_character_id,
            "name": invitee_name,
            "user_id": invitee_user_id,
        },
    })

    # 11. Return updated session
    return await _build_session_response(db, session_obj, session_obj.dungeon_id)


async def _get_dungeon_for_session(db: AsyncSession, dungeon_id: int) -> Dungeon:
    """Helper to load dungeon, raising 404 if not found."""
    stmt = select(Dungeon).where(Dungeon.id == dungeon_id)
    result = await db.execute(stmt)
    dungeon = result.scalar_one_or_none()
    if not dungeon:
        raise HTTPException(status_code=404, detail="Подземелье не найдено")
    return dungeon


async def leave_session(
    db: AsyncSession,
    session_id: int,
    character_id: int,
) -> Optional[SessionResponse]:
    """
    Leave a forming session. If leader leaves, transfer leadership.
    If no members remain, delete the session.
    Returns updated session or None if session was deleted.
    """
    # 1. Validate session exists and status='forming'
    session_obj = await _get_session(db, session_id)
    if session_obj.status != "forming":
        raise HTTPException(
            status_code=400,
            detail="Покинуть группу можно только во время формирования",
        )

    # 2. Validate character is a member
    leaving_member = None
    for m in session_obj.members:
        if m.character_id == character_id:
            leaving_member = m
            break
    if leaving_member is None:
        raise HTTPException(
            status_code=400,
            detail="Персонаж не является участником этой сессии",
        )

    # 3. Remove member from DB
    await db.delete(leaving_member)

    # 4. Clear character active session in Redis
    await session_state.clear_character_active_session(character_id)

    # 5. Check if leaving member is leader
    remaining_members = [m for m in session_obj.members if m.character_id != character_id]

    if session_obj.leader_character_id == character_id:
        if remaining_members:
            # Transfer leadership to next member (by join order — earliest joined_at)
            remaining_members.sort(key=lambda m: m.joined_at or datetime.min)
            new_leader = remaining_members[0]
            session_obj.leader_character_id = new_leader.character_id
            await db.commit()
            await db.refresh(session_obj)

            # Broadcast: leader changed
            await ws_manager.broadcast_to_session(session_id, {
                "type": "leader_changed",
                "data": {
                    "new_leader_character_id": new_leader.character_id,
                },
            })

            # Broadcast: member left
            await ws_manager.broadcast_to_session(session_id, {
                "type": "member_left",
                "data": {"character_id": character_id},
            })

            return await _build_session_response(db, session_obj, session_obj.dungeon_id)
        else:
            # No members left — delete session
            await db.delete(session_obj)
            await db.commit()

            # Broadcast: session disbanded
            await ws_manager.broadcast_to_session(session_id, {
                "type": "session_status",
                "data": {"status": "disbanded"},
            })
            await ws_manager.cleanup_session(session_id)
            return None
    else:
        # Non-leader leaving
        await db.commit()
        await db.refresh(session_obj)

        # Broadcast: member left
        await ws_manager.broadcast_to_session(session_id, {
            "type": "member_left",
            "data": {"character_id": character_id},
        })

        return await _build_session_response(db, session_obj, session_obj.dungeon_id)


async def enter_dungeon(
    db: AsyncSession,
    session_id: int,
    character_id: int,
) -> SessionStateResponse:
    """
    Leader starts the dungeon run.
    Moves party to entrance room, changes status to 'active'.
    """
    # 1. Validate session exists and status='forming'
    session_obj = await _get_session(db, session_id)
    if session_obj.status != "forming":
        raise HTTPException(
            status_code=400,
            detail="Войти в подземелье можно только из состояния формирования группы",
        )

    # 2. Validate character is the leader
    if session_obj.leader_character_id != character_id:
        raise HTTPException(
            status_code=403,
            detail="Только лидер может начать прохождение подземелья",
        )

    # 3. At least 1 member must exist
    member_count_stmt = select(DungeonSessionMember).where(
        DungeonSessionMember.session_id == session_id
    )
    member_count_result = await db.execute(member_count_stmt)
    if not member_count_result.scalars().all():
        raise HTTPException(
            status_code=400,
            detail="В группе должен быть хотя бы один участник",
        )

    # 3.5. GATE (FEAT-145): entering needs a "dungeon" intent post on the
    # dungeon's location. Consumed by the leader.
    dungeon = (
        await db.execute(select(Dungeon).where(Dungeon.id == session_obj.dungeon_id))
    ).scalar_one_or_none()
    if dungeon and dungeon.location_id is not None:
        if not await http_clients.consume_dungeon_gate(
            character_id, dungeon.location_id, session_obj.dungeon_id
        ):
            raise HTTPException(
                status_code=403,
                detail="Нужен пост-намерение «Данж» с этим подземельем, чтобы войти",
            )

    # 4. Find entrance room
    stmt = select(DungeonRoom).where(
        DungeonRoom.dungeon_id == session_obj.dungeon_id,
        DungeonRoom.is_entrance == True,
    )
    result = await db.execute(stmt)
    entrance_room = result.scalar_one_or_none()
    if not entrance_room:
        raise HTTPException(
            status_code=500,
            detail="Подземелье не имеет комнаты-входа. Обратитесь к администратору.",
        )

    # 5. Update session: status='active', current_room_id=entrance, started_at=now
    now = datetime.utcnow()
    session_obj.status = "active"
    session_obj.current_room_id = entrance_room.id
    session_obj.started_at = now

    # 6. Load members explicitly for use after commit
    members_stmt = select(DungeonSessionMember).where(
        DungeonSessionMember.session_id == session_obj.id
    )
    members_result = await db.execute(members_stmt)
    members_list = members_result.scalars().all()

    # Init Redis session state
    members_dict = {}
    for m in members_list:
        members_dict[str(m.character_id)] = {
            "user_id": m.user_id,
            "status": m.status,
        }

    await session_state.init_session_state(
        session_id=session_obj.id,
        dungeon_id=session_obj.dungeon_id,
        leader_character_id=session_obj.leader_character_id,
        members=members_dict,
    )
    # Update Redis state with current room and exploring phase
    await session_state.set_current_room(session_obj.id, entrance_room.id)
    await session_state.set_phase(session_obj.id, "exploring")

    # 7. Create DungeonRoomVisit for entrance room for all members (upsert)
    for m in members_list:
        existing_visit_stmt = select(DungeonRoomVisit).where(
            DungeonRoomVisit.dungeon_id == session_obj.dungeon_id,
            DungeonRoomVisit.character_id == m.character_id,
            DungeonRoomVisit.room_id == entrance_room.id,
        )
        existing_visit_result = await db.execute(existing_visit_stmt)
        existing_visit = existing_visit_result.scalar_one_or_none()
        if existing_visit:
            existing_visit.visit_count += 1
            existing_visit.last_visited_at = now
        else:
            visit = DungeonRoomVisit(
                dungeon_id=session_obj.dungeon_id,
                character_id=m.character_id,
                room_id=entrance_room.id,
            )
            db.add(visit)

    # 8. Create DungeonRoomState for entrance room
    room_state = DungeonRoomState(
        session_id=session_obj.id,
        room_id=entrance_room.id,
        is_cleared=False,
        loot_collected=False,
    )
    db.add(room_state)

    await db.commit()
    await db.refresh(session_obj)

    # 9. Broadcast via WebSocket: session started, room entered
    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "session_status",
        "data": {"status": "active"},
    })

    # 10. Build and return session state with room info
    state_response = await get_session_state(db, session_obj.id, character_id)

    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "room_entered",
        "data": {
            "room": {
                "id": entrance_room.id,
                "room_type": entrance_room.room_type,
                "name": entrance_room.name,
                "description": entrance_room.description,
                "is_entrance": entrance_room.is_entrance,
            },
            "corridor_event": None,
        },
    })

    return state_response


async def create_party_run(
    db: AsyncSession,
    character_id: int,
    dungeon_id: int,
    user_id: int,
) -> SessionStateResponse:
    """Start a dungeon run from the leader's squad in one step (FEAT-144 Ф3-3).

    Members come from the existing party (co-located accepted squadmates) instead
    of a separate invite phase. Party membership is the consent. Squadmates already
    in another dungeon session are skipped. The run activates immediately.
    """
    dungeon = (
        await db.execute(select(Dungeon).where(Dungeon.id == dungeon_id))
    ).scalar_one_or_none()
    if not dungeon:
        raise HTTPException(status_code=404, detail="Подземелье не найдено")
    if not dungeon.is_active:
        raise HTTPException(status_code=400, detail="Подземелье неактивно")

    on_cd, remaining = await session_state.check_dungeon_cooldown(dungeon_id)
    if on_cd:
        h, m = remaining // 3600, (remaining % 3600) // 60
        raise HTTPException(
            status_code=403,
            detail=f"Подземелье на кулдауне. Восстановится через {h}ч {m}мин",
        )

    profile = await http_clients.get_character_profile(character_id)
    if profile.get("current_location_id") != dungeon.location_id:
        raise HTTPException(status_code=400, detail="Персонаж должен находиться на локации подземелья")
    if profile.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Этот персонаж не принадлежит вам")
    if await session_state.get_character_active_session(character_id) is not None:
        raise HTTPException(status_code=409, detail="Персонаж уже участвует в другой сессии подземелья")

    party = await http_clients.get_party_active_members(character_id, dungeon.location_id)
    if not party.get("party_id") or party.get("leader_character_id") != character_id:
        raise HTTPException(status_code=400, detail="Групповой заход доступен только лидеру отряда")

    # Available squadmates: co-located and not already in another dungeon session.
    available = [character_id]
    for cid in party.get("member_character_ids", []):
        if cid == character_id:
            continue
        if await session_state.get_character_active_session(cid) is None:
            available.append(cid)

    session_obj = DungeonSession(
        dungeon_id=dungeon_id, leader_character_id=character_id, status="forming",
    )
    db.add(session_obj)
    await db.flush()

    for cid in available:
        prof = profile if cid == character_id else await http_clients.get_character_profile(cid)
        db.add(DungeonSessionMember(
            session_id=session_obj.id,
            character_id=cid,
            user_id=prof.get("user_id"),
            status="alive",
        ))
    await db.commit()

    for cid in available:
        await session_state.set_character_active_session(cid, session_obj.id)

    # Activate the run right away (reuses the standard enter flow).
    return await enter_dungeon(db, session_obj.id, character_id)


async def get_session_state(
    db: AsyncSession,
    session_id: int,
    character_id: int,
) -> SessionStateResponse:
    """
    Get full session state including current room, members, group inventory.
    Validates that character is a member of the session.
    """
    # 1. Load session with members
    session_obj = await _get_session(db, session_id)

    # 2. Validate character is a member
    is_member = any(m.character_id == character_id for m in session_obj.members)
    if not is_member:
        raise HTTPException(
            status_code=403,
            detail="Персонаж не является участником этой сессии",
        )

    # 3. Load dungeon info
    dungeon = await _get_dungeon_for_session(db, session_obj.dungeon_id)

    # 4. Get Redis state
    redis_state = await session_state.get_session_state(session_id)
    phase = "forming"
    active_battle_id = None
    if redis_state:
        phase = redis_state.get("phase", "forming")
        active_battle_id = redis_state.get("active_battle_id")

    # 5. Build current room info with exits
    current_room_view = None
    if session_obj.current_room_id:
        room_stmt = select(DungeonRoom).where(DungeonRoom.id == session_obj.current_room_id)
        room_result = await db.execute(room_stmt)
        current_room = room_result.scalar_one_or_none()

        if current_room:
            # Check if room is cleared
            rs_stmt = select(DungeonRoomState).where(
                DungeonRoomState.session_id == session_id,
                DungeonRoomState.room_id == current_room.id,
            )
            rs_result = await db.execute(rs_stmt)
            room_state_obj = rs_result.scalar_one_or_none()
            is_cleared = room_state_obj.is_cleared if room_state_obj else False

            # Get exits with fog of war
            exits = await _get_room_exits(
                db, current_room.id, session_obj.dungeon_id, character_id, dungeon
            )

            current_room_view = RoomViewResponse(
                id=current_room.id,
                room_type=current_room.room_type,
                name=current_room.name,
                description=current_room.description,
                image_url=current_room.image_url,
                is_entrance=current_room.is_entrance,
                is_boss_room=current_room.is_boss_room,
                is_cleared=is_cleared,
                room_config_visible=_build_room_config_visible(current_room, room_state_obj),
                exits=exits,
                position_x=current_room.position_x,
                position_y=current_room.position_y,
            )

    # 6. Build members list
    members_resp: List[SessionMemberResponse] = []
    for m in session_obj.members:
        try:
            profile = await http_clients.get_character_profile(m.character_id)
            name = profile.get("name", f"Персонаж #{m.character_id}")
        except Exception:
            name = f"Персонаж #{m.character_id}"

        members_resp.append(
            SessionMemberResponse(
                character_id=m.character_id,
                name=name,
                status=m.status,
                is_leader=(m.character_id == session_obj.leader_character_id),
                user_id=m.user_id,
            )
        )

    # 7. Get group inventory from DB
    inv_stmt = select(DungeonSessionInventory).where(
        DungeonSessionInventory.session_id == session_id
    )
    inv_result = await db.execute(inv_stmt)
    inv_items = inv_result.scalars().all()
    # Fetch item names for all unique item_ids (cache within request)
    unique_item_ids = {item.item_id for item in inv_items}
    item_name_cache: Dict[int, Optional[str]] = {}
    for uid in unique_item_ids:
        try:
            info = await http_clients.get_item_info(uid)
            item_name_cache[uid] = info.get("name") or info.get("item_name")
        except Exception:
            item_name_cache[uid] = None

    group_inventory = [
        GroupInventoryItemResponse(
            item_id=item.item_id,
            item_name=item_name_cache.get(item.item_id),
            quantity=item.quantity,
            source_description=item.source_description,
        )
        for item in inv_items
    ]

    # 8. If active_battle_id: check battle status via http_clients
    if active_battle_id:
        # Skip battle re-processing for terminal sessions
        session_status = redis_state.get("status", "active") if redis_state else session_obj.status
        if session_status in ("completed", "escaped", "wiped"):
            # Session is terminal — just clear stale battle ID
            await session_state.update_session_state(session_id, active_battle_id=None)
            active_battle_id = None
        else:
            try:
                battle_state_data = await http_clients.get_battle_state(active_battle_id)

                if battle_state_data is None:
                    # Battle state not found (404 / Redis expired) — battle finished.
                    # Clean up dungeon session state.
                    logger.info(
                        "Бой %d не найден (Redis expired), очищаем состояние сессии %d",
                        active_battle_id, session_id,
                    )
                    # Mark room as cleared
                    current_room_id_val = redis_state.get("current_room_id") if redis_state else None
                    if current_room_id_val:
                        room_state_stmt = select(DungeonRoomState).where(
                            DungeonRoomState.session_id == session_id,
                            DungeonRoomState.room_id == int(current_room_id_val),
                        )
                        rs_result = await db.execute(room_state_stmt)
                        rs_obj = rs_result.scalar_one_or_none()
                        if rs_obj and not rs_obj.is_cleared:
                            rs_obj.is_cleared = True
                            await db.commit()

                        # Check if this was a boss room — handle completion
                        room_stmt = select(DungeonRoom).where(
                            DungeonRoom.id == int(current_room_id_val)
                        )
                        room_result = await db.execute(room_stmt)
                        cleared_room = room_result.scalar_one_or_none()
                        if cleared_room and cleared_room.is_boss_room:
                            dungeon_stmt = select(Dungeon).where(
                                Dungeon.id == session_obj.dungeon_id
                            )
                            dungeon_result = await db.execute(dungeon_stmt)
                            dungeon_for_boss = dungeon_result.scalar_one_or_none()
                            if dungeon_for_boss:
                                await _handle_boss_room_cleared(
                                    db, session_id, session_obj,
                                    dungeon_for_boss, cleared_room,
                                )
                                await db.commit()
                                refreshed = await session_state.get_session_state(session_id)
                                if refreshed:
                                    phase = refreshed.get("phase", "exploring")

                    await session_state.clear_active_battle(session_id)
                    if phase == "exploring":
                        await session_state.set_phase(session_id, "exploring")
                    active_battle_id = None
                else:
                    # Battle state exists — check if it's finished
                    runtime = battle_state_data.get("runtime", {})
                    participants = runtime.get("participants", {})

                    team1_all_dead = True
                    team2_all_dead = True
                    has_participants = bool(participants)
                    for pid, pdata in participants.items():
                        team = pdata.get("team")
                        hp = pdata.get("hp", 0)
                        if team == 1 and hp > 0:
                            team1_all_dead = False
                        elif team == 2 and hp > 0:
                            team2_all_dead = False

                    battle_finished = has_participants and (team1_all_dead or team2_all_dead)

                    if battle_finished:
                        try:
                            await process_battle_completion(
                                db, session_id, active_battle_id, battle_state_data,
                            )
                            refreshed_state = await session_state.get_session_state(session_id)
                            if refreshed_state:
                                phase = refreshed_state.get("phase", phase)
                                active_battle_id = refreshed_state.get("active_battle_id")
                        except Exception as proc_err:
                            logger.error(
                                "Ошибка при обработке завершения боя %d: %s",
                                active_battle_id, proc_err,
                            )
            except Exception:
                logger.warning(
                    "Не удалось проверить статус боя %d для сессии %d",
                    active_battle_id, session_id,
                    exc_info=True,
                )

    # 9. Build explored_rooms list (all rooms visited by this character, excluding current)
    explored_rooms: List[ExploredRoomInfo] = []
    if session_obj.current_room_id:
        visits_stmt = (
            select(
                DungeonRoom.id,
                DungeonRoom.name,
                DungeonRoom.room_type,
                DungeonRoom.position_x,
                DungeonRoom.position_y,
                DungeonRoomState.is_cleared,
            )
            .join(
                DungeonRoomVisit,
                DungeonRoomVisit.room_id == DungeonRoom.id,
            )
            .outerjoin(
                DungeonRoomState,
                (DungeonRoomState.room_id == DungeonRoom.id)
                & (DungeonRoomState.session_id == session_id),
            )
            .where(
                DungeonRoomVisit.dungeon_id == session_obj.dungeon_id,
                DungeonRoomVisit.character_id == character_id,
                DungeonRoom.id != session_obj.current_room_id,
            )
        )
        visits_result = await db.execute(visits_stmt)
        visited_rows = visits_result.all()

        for row in visited_rows:
            explored_rooms.append(
                ExploredRoomInfo(
                    id=row[0],
                    name=row[1],
                    room_type=row[2],
                    position_x=row[3],
                    position_y=row[4],
                    is_cleared=row[5] if row[5] is not None else False,
                )
            )

    # 10. Build explored_corridors — corridors between any visited rooms (including current)
    explored_corridors: List[ExploredCorridorInfo] = []
    if session_obj.current_room_id:
        # Collect all visited room IDs (including current room)
        visited_ids = {r.id for r in explored_rooms}
        visited_ids.add(session_obj.current_room_id)

        if len(visited_ids) >= 2:
            corridors_stmt = (
                select(DungeonCorridor)
                .where(
                    DungeonCorridor.dungeon_id == session_obj.dungeon_id,
                    DungeonCorridor.from_room_id.in_(visited_ids),
                    DungeonCorridor.to_room_id.in_(visited_ids),
                )
            )
            corridors_result = await db.execute(corridors_stmt)
            for c in corridors_result.scalars().all():
                explored_corridors.append(
                    ExploredCorridorInfo(
                        corridor_id=c.id,
                        from_room_id=c.from_room_id,
                        to_room_id=c.to_room_id,
                        source_handle=c.source_handle,
                        target_handle=c.target_handle,
                    )
                )

    # 11. Return full SessionStateResponse
    return SessionStateResponse(
        session_id=session_obj.id,
        dungeon_id=session_obj.dungeon_id,
        dungeon_name=dungeon.name,
        location_id=dungeon.location_id,
        status=session_obj.status,
        phase=phase,
        current_room=current_room_view,
        members=members_resp,
        group_inventory=group_inventory,
        active_battle_id=active_battle_id,
        explored_rooms=explored_rooms,
        explored_corridors=explored_corridors,
    )


# =====================================================================
# Stat Check Helper
# =====================================================================

async def perform_stat_check(
    session_state_data: Dict,
    stat_name: str,
    difficulty: int,
    difficulty_modifier: float,
) -> Tuple[bool, str, int]:
    """
    Perform a stat check against the best value among alive party members.

    Returns (passed, best_character_name, best_value).
    """
    members = session_state_data.get("members", {})
    alive_ids = [
        int(cid) for cid, info in members.items()
        if info.get("status") == "alive"
    ]

    if not alive_ids:
        return (False, "", 0)

    best_value = -1
    best_name = ""

    for character_id in alive_ids:
        try:
            attrs = await http_clients.get_character_attributes(character_id)
        except Exception:
            logger.warning(
                "Не удалось получить атрибуты персонажа %d для проверки %s",
                character_id, stat_name,
            )
            continue

        # Try to get the stat from cumulative_stats first, then top-level
        cumulative = attrs.get("cumulative_stats", {})
        value = cumulative.get(stat_name, attrs.get(stat_name, 0))
        if isinstance(value, (int, float)) and value > best_value:
            best_value = int(value)
            # Try to get character name
            try:
                profile = await http_clients.get_character_profile(character_id)
                best_name = profile.get("name", f"Персонаж #{character_id}")
            except Exception:
                best_name = f"Персонаж #{character_id}"

    adjusted_difficulty = math.ceil(difficulty * difficulty_modifier)
    passed = best_value >= adjusted_difficulty

    return (passed, best_name, best_value)


# =====================================================================
# Battle Integration
# =====================================================================

async def _get_alive_character_ids(session_state_data: Dict) -> List[int]:
    """Extract alive character IDs from session state members dict."""
    members = session_state_data.get("members", {})
    return [
        int(cid) for cid, info in members.items()
        if info.get("status") == "alive"
    ]


async def initiate_room_battle(
    db: AsyncSession,
    session_id: int,
    room: DungeonRoom,
    dungeon: Dungeon,
    session_state_data: Dict,
    auth_token: Optional[str] = None,
) -> int:
    """
    Initiate a PvE battle when entering a battle/boss room.

    1. Get mob_template_ids from room.room_config
    2. Spawn mobs via character-service
    3. Build battle players (party team 1 + mobs team 2)
    4. Create battle via battle-service
    5. Update Redis state: phase=in_battle, active_battle_id
    6. Broadcast battle_started via WebSocket
    7. Return battle_id
    """
    # 1. Get mob_template_ids from room_config
    room_config = room.room_config if isinstance(room.room_config, dict) else {}
    mob_template_ids = room_config.get("mob_template_ids", [])

    if not mob_template_ids:
        logger.warning(
            "Комната %d (тип=%s) не имеет mob_template_ids в room_config",
            room.id, room.room_type,
        )
        raise HTTPException(
            status_code=500,
            detail="Комната боя не настроена — нет шаблонов мобов",
        )

    # 2. Spawn mobs via character-service
    try:
        mob_character_ids = await http_clients.spawn_dungeon_mobs(
            mob_template_ids, dungeon.location_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Ошибка при спавне мобов для комнаты %d: %s", room.id, e)
        raise HTTPException(
            status_code=502,
            detail="Не удалось создать мобов для боя",
        )

    if not mob_character_ids:
        raise HTTPException(
            status_code=502,
            detail="Не удалось создать мобов для боя — сервис вернул пустой список",
        )

    logger.info(
        "Спавн мобов для комнаты %d: шаблоны=%s, персонажи=%s",
        room.id, mob_template_ids, mob_character_ids,
    )

    # 3. Build battle players list
    alive_ids = await _get_alive_character_ids(session_state_data)
    if not alive_ids:
        raise HTTPException(
            status_code=400,
            detail="В группе нет живых участников для боя",
        )

    players = []
    # Team 1: party members
    for cid in alive_ids:
        players.append({"character_id": cid, "team": 1})
    # Team 2: mobs
    for cid in mob_character_ids:
        players.append({"character_id": cid, "team": 2})

    # 4. Create battle via battle-service
    try:
        battle_data = await http_clients.create_battle(
            players=players,
            battle_type="pve",
            context={"dungeon_session_id": session_id, "room_id": room.id},
            auth_token=auth_token,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Ошибка при создании боя для комнаты %d: %s", room.id, e)
        raise HTTPException(
            status_code=502,
            detail="Не удалось создать бой",
        )

    battle_id = battle_data.get("battle_id")
    if not battle_id:
        logger.error(
            "battle-service вернул ответ без battle_id: %s", battle_data,
        )
        raise HTTPException(
            status_code=502,
            detail="Боевая система вернула некорректный ответ",
        )

    logger.info(
        "Бой создан: battle_id=%d, session=%d, room=%d, party=%s, mobs=%s",
        battle_id, session_id, room.id, alive_ids, mob_character_ids,
    )

    # 5. Update Redis state
    await session_state.set_active_battle(session_id, battle_id)

    # 6. Broadcast via WebSocket
    await ws_manager.broadcast_to_session(session_id, {
        "type": "battle_started",
        "data": {
            "battle_id": battle_id,
            "room_id": room.id,
            "room_name": room.name,
            "mob_character_ids": mob_character_ids,
            "message": "Бой начинается!",
        },
    })

    return battle_id


async def initiate_corridor_battle(
    db: AsyncSession,
    session_id: int,
    corridor: DungeonCorridor,
    dungeon: Dungeon,
    session_state_data: Dict,
    target_room_id: int,
    auth_token: Optional[str] = None,
) -> int:
    """
    Initiate a PvE battle triggered by a corridor random encounter.

    Similar to room battle but uses corridor's random_battle_mob_ids.
    Stores target_room_id in Redis so after battle the party continues to that room.
    Returns battle_id.
    """
    mob_template_ids = corridor.random_battle_mob_ids or []

    if not mob_template_ids:
        logger.warning(
            "Коридор %d не имеет random_battle_mob_ids, но бой был запущен",
            corridor.id,
        )
        raise HTTPException(
            status_code=500,
            detail="Коридор не настроен — нет шаблонов мобов для случайного боя",
        )

    # Spawn mobs
    try:
        mob_character_ids = await http_clients.spawn_dungeon_mobs(
            mob_template_ids, dungeon.location_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Ошибка при спавне мобов для коридора %d: %s", corridor.id, e,
        )
        raise HTTPException(
            status_code=502,
            detail="Не удалось создать мобов для боя в коридоре",
        )

    if not mob_character_ids:
        raise HTTPException(
            status_code=502,
            detail="Не удалось создать мобов — сервис вернул пустой список",
        )

    logger.info(
        "Спавн мобов для коридора %d: шаблоны=%s, персонажи=%s",
        corridor.id, mob_template_ids, mob_character_ids,
    )

    # Build players
    alive_ids = await _get_alive_character_ids(session_state_data)
    if not alive_ids:
        raise HTTPException(
            status_code=400,
            detail="В группе нет живых участников для боя",
        )

    players = []
    for cid in alive_ids:
        players.append({"character_id": cid, "team": 1})
    for cid in mob_character_ids:
        players.append({"character_id": cid, "team": 2})

    # Create battle
    try:
        battle_data = await http_clients.create_battle(
            players=players,
            battle_type="pve",
            context={
                "dungeon_session_id": session_id,
                "corridor_id": corridor.id,
            },
            auth_token=auth_token,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Ошибка при создании боя для коридора %d: %s", corridor.id, e,
        )
        raise HTTPException(
            status_code=502,
            detail="Не удалось создать бой в коридоре",
        )

    battle_id = battle_data.get("battle_id")
    if not battle_id:
        logger.error(
            "battle-service вернул ответ без battle_id: %s", battle_data,
        )
        raise HTTPException(
            status_code=502,
            detail="Боевая система вернула некорректный ответ",
        )

    logger.info(
        "Бой в коридоре создан: battle_id=%d, session=%d, corridor=%d, "
        "target_room=%d, party=%s, mobs=%s",
        battle_id, session_id, corridor.id, target_room_id,
        alive_ids, mob_character_ids,
    )

    # Update Redis: phase=in_battle, store target room for post-battle continuation
    await session_state.update_session_state(
        session_id,
        phase="in_battle",
        active_battle_id=battle_id,
        pending_target_room_id=target_room_id,
    )

    # Broadcast
    await ws_manager.broadcast_to_session(session_id, {
        "type": "battle_started",
        "data": {
            "battle_id": battle_id,
            "corridor_id": corridor.id,
            "mob_character_ids": mob_character_ids,
            "message": "В коридоре на вас напали враги!",
        },
    })

    return battle_id


async def process_battle_completion(
    db: AsyncSession,
    session_id: int,
    battle_id: int,
    battle_state_data: dict,
) -> Dict:
    """
    Process battle completion: mark room cleared, update casualties,
    handle boss room special logic, clear battle state.

    Returns dict with results summary.
    """
    redis_state_data = await session_state.get_session_state(session_id)
    if redis_state_data is None:
        logger.error("Redis state not found for session %d during battle completion", session_id)
        return {"error": "session_state_not_found"}

    # Determine winner from battle state
    runtime = battle_state_data.get("runtime", {})
    participants = runtime.get("participants", {})

    # Check if team 1 (party) won: at least one team 1 member alive
    team1_alive = False
    team2_alive = False
    team1_casualties = []
    team2_character_ids = []

    for pid, pdata in participants.items():
        team = pdata.get("team")
        hp = pdata.get("hp", 0)
        char_id = pdata.get("character_id")

        if team == 1:
            if hp > 0:
                team1_alive = True
            else:
                team1_casualties.append(char_id)
        elif team == 2:
            team2_character_ids.append(char_id)
            if hp > 0:
                team2_alive = True

    party_won = team1_alive and not team2_alive

    # Load session from DB
    session_obj = await _get_session(db, session_id)
    dungeon = await _get_dungeon_for_session(db, session_obj.dungeon_id)

    current_room_id = redis_state_data.get("current_room_id")
    pending_target_room_id = redis_state_data.get("pending_target_room_id")

    results = {
        "battle_id": battle_id,
        "party_won": party_won,
        "casualties": team1_casualties,
        "pending_target_room_id": pending_target_room_id,
    }

    if party_won:
        # Mark room as cleared (if it was a room battle, not corridor)
        if current_room_id and not pending_target_room_id:
            # Room battle — mark the current room as cleared
            rs_stmt = select(DungeonRoomState).where(
                DungeonRoomState.session_id == session_id,
                DungeonRoomState.room_id == current_room_id,
            )
            rs_result = await db.execute(rs_stmt)
            room_state_obj = rs_result.scalar_one_or_none()
            if room_state_obj:
                room_state_obj.is_cleared = True
            else:
                room_state_obj = DungeonRoomState(
                    session_id=session_id,
                    room_id=current_room_id,
                    is_cleared=True,
                    loot_collected=False,
                )
                db.add(room_state_obj)

            # Check if boss room
            room_stmt = select(DungeonRoom).where(DungeonRoom.id == current_room_id)
            room_result = await db.execute(room_stmt)
            room_obj = room_result.scalar_one_or_none()

            if room_obj and room_obj.is_boss_room:
                results["boss_cleared"] = True
                # Handle boss room completion
                boss_result = await _handle_boss_room_cleared(
                    db, session_id, session_obj, dungeon, room_obj,
                )
                results.update(boss_result)

    # Update party member casualties
    for char_id in team1_casualties:
        cid_str = str(char_id)
        await session_state.update_member_status(session_id, cid_str, "dead")
        # Update DB member status too
        member_stmt = select(DungeonSessionMember).where(
            DungeonSessionMember.session_id == session_id,
            DungeonSessionMember.character_id == char_id,
        )
        member_result = await db.execute(member_stmt)
        member_obj = member_result.scalar_one_or_none()
        if member_obj:
            member_obj.status = "dead"

    # Check if all party members are dead (wipe)
    updated_redis = await session_state.get_session_state(session_id)
    if updated_redis:
        members = updated_redis.get("members", {})
        all_dead = all(
            info.get("status") == "dead" for info in members.values()
        )
        if all_dead:
            results["wiped"] = True
            session_obj.status = "wiped"
            await session_state.update_session_state(
                session_id, phase="wiped", status="wiped",
                active_battle_id=None, pending_target_room_id=None,
            )
            await db.commit()

            await ws_manager.broadcast_to_session(session_id, {
                "type": "session_status",
                "data": {
                    "status": "wiped",
                    "message": "Вся группа погибла. Подземелье провалено.",
                },
            })
            return results

    # Clear battle state and resume exploring
    if pending_target_room_id:
        # Corridor battle completed — move party to target room
        await session_state.update_session_state(
            session_id,
            phase="exploring",
            active_battle_id=None,
            pending_target_room_id=None,
            current_room_id=pending_target_room_id,
        )
        session_obj.current_room_id = pending_target_room_id
    else:
        # Room battle completed — but if dungeon just completed,
        # boss handler already set the correct phase
        if not results.get("dungeon_completed"):
            await session_state.clear_active_battle(session_id)

    await db.commit()

    # Broadcast battle ended
    await ws_manager.broadcast_to_session(session_id, {
        "type": "battle_ended",
        "data": {
            "battle_id": battle_id,
            "party_won": party_won,
            "casualties": team1_casualties,
            "boss_cleared": results.get("boss_cleared", False),
            "mana_core_revealed": results.get("mana_core_revealed", False),
            "dungeon_completed": results.get("dungeon_completed", False),
            "message": (
                "Победа! Враги повержены."
                if party_won
                else "Поражение..."
            ),
        },
    })

    return results


async def _handle_boss_room_cleared(
    db: AsyncSession,
    session_id: int,
    session_obj: DungeonSession,
    dungeon: Dungeon,
    boss_room: DungeonRoom,
) -> Dict:
    """
    Handle boss room cleared: check mana core chance, potentially reveal
    mana core room, or complete the dungeon.

    Returns dict with boss_cleared details.
    """
    result: Dict = {}

    # Check if dungeon has a mana core room
    mc_stmt = select(DungeonRoom).where(
        DungeonRoom.dungeon_id == dungeon.id,
        DungeonRoom.is_mana_core_room == True,
    )
    mc_result = await db.execute(mc_stmt)
    mana_core_room = mc_result.scalar_one_or_none()

    # Roll mana core chance
    mana_core_revealed = False
    if mana_core_room and dungeon.mana_core_chance > 0:
        roll = random.random()
        if roll < dungeon.mana_core_chance:
            mana_core_revealed = True
            result["mana_core_revealed"] = True
            result["mana_core_room_id"] = mana_core_room.id
            result["mana_core_room_name"] = mana_core_room.name

            logger.info(
                "Ядро маны обнаружено! session=%d, dungeon=%d, "
                "mana_core_room=%d (шанс=%.2f, бросок=%.4f)",
                session_id, dungeon.id, mana_core_room.id,
                dungeon.mana_core_chance, roll,
            )

            # Create a virtual corridor from boss room to mana core room
            # (if one doesn't already exist)
            from models import DungeonCorridor
            existing_stmt = select(DungeonCorridor).where(
                DungeonCorridor.from_room_id == boss_room.id,
                DungeonCorridor.to_room_id == mana_core_room.id,
            )
            existing_result = await db.execute(existing_stmt)
            if not existing_result.scalar_one_or_none():
                virtual_corridor = DungeonCorridor(
                    dungeon_id=dungeon.id,
                    from_room_id=boss_room.id,
                    to_room_id=mana_core_room.id,
                    stamina_cost=0,
                    is_bidirectional=False,
                    random_battle_chance=0.0,
                    trap_chance=0.0,
                    description="Путь к Ядру маны открылся...",
                )
                db.add(virtual_corridor)

            # Broadcast mana core reveal
            await ws_manager.broadcast_to_session(session_id, {
                "type": "mana_core_revealed",
                "data": {
                    "room_id": mana_core_room.id,
                    "room_name": mana_core_room.name,
                    "message": "Ядро маны обнаружено! Открылся путь в скрытую комнату.",
                },
            })

            # Don't complete dungeon yet — player can choose to go to mana core
            return result

    # No mana core (or chance failed) — boss defeated, but session stays
    # active so the player can open the boss chest first.
    # Transition to "completed" happens later in _handle_open_chest (Task 7).
    result["dungeon_completed"] = True

    await session_state.update_session_state(
        session_id,
        phase="exploring",
        status="active",
        active_battle_id=None,
    )

    # Boss loot is NOT auto-added here — player must open the chest
    # (loot comes from _handle_open_chest using "boss_loot" key)

    await ws_manager.broadcast_to_session(session_id, {
        "type": "session_status",
        "data": {
            "status": "active",
            "message": "Босс повержен! Заберите добычу из сундука.",
        },
    })

    return result


# =====================================================================
# Room Movement
# =====================================================================

async def move_to_room(
    db: AsyncSession,
    session_id: int,
    character_id: int,
    corridor_id: int,
    auth_token: Optional[str] = None,
) -> MoveResponse:
    """
    Move the party to an adjacent room via a corridor. Leader only.

    Flow:
    1. Validate leader, session active, phase=exploring
    2. Validate corridor from current room
    3. Calculate stamina cost (with dead_count penalty)
    4. Check & consume stamina for all alive members
    5. Roll corridor events (battle, trap)
    6. Move to target room (if no corridor battle)
    7. Update fog of war
    8. Broadcast via WebSocket
    """
    # 1. Validate session
    session_obj = await _get_session(db, session_id)

    if session_obj.status != "active":
        raise HTTPException(
            status_code=400,
            detail="Сессия подземелья не активна",
        )

    if session_obj.leader_character_id != character_id:
        raise HTTPException(
            status_code=403,
            detail="Только лидер может перемещать группу",
        )

    # 2. Check phase from Redis
    redis_state = await session_state.get_session_state(session_id)
    if redis_state is None:
        raise HTTPException(
            status_code=500,
            detail="Состояние сессии не найдено в Redis",
        )

    phase = redis_state.get("phase", "")
    if phase != "exploring":
        raise HTTPException(
            status_code=400,
            detail="Перемещение возможно только в фазе исследования",
        )

    # 3. Get current room from Redis state
    current_room_id = redis_state.get("current_room_id")
    if current_room_id is None:
        raise HTTPException(
            status_code=400,
            detail="Текущая комната не определена",
        )

    # 4. Validate corridor exists from current room
    stmt = select(DungeonCorridor).where(DungeonCorridor.id == corridor_id)
    result = await db.execute(stmt)
    corridor = result.scalar_one_or_none()
    if not corridor:
        raise HTTPException(status_code=404, detail="Коридор не найден")

    # Determine direction: corridor can be used forward (from_room -> to_room)
    # or backward if bidirectional (to_room -> from_room)
    if corridor.from_room_id == current_room_id:
        target_room_id = corridor.to_room_id
    elif corridor.to_room_id == current_room_id and corridor.is_bidirectional:
        target_room_id = corridor.from_room_id
    else:
        raise HTTPException(
            status_code=400,
            detail="Этот коридор недоступен из текущей комнаты",
        )

    # 5. Load dungeon for modifiers
    dungeon = await _get_dungeon_for_session(db, session_obj.dungeon_id)

    # 6. Calculate stamina cost
    dead_count = redis_state.get("dead_count", 0)
    base_cost = corridor.stamina_cost
    final_cost = math.ceil(
        base_cost * dungeon.stamina_multiplier * (1 + 0.25 * dead_count)
    )

    # 7. Get alive members and check stamina for all BEFORE consuming
    members = redis_state.get("members", {})
    alive_ids = [
        int(cid) for cid, info in members.items()
        if info.get("status") == "alive"
    ]

    if not alive_ids:
        raise HTTPException(
            status_code=400,
            detail="В группе нет живых участников",
        )

    # Check all alive members have enough stamina
    for cid in alive_ids:
        try:
            attrs = await http_clients.get_character_attributes(cid)
        except Exception:
            raise HTTPException(
                status_code=502,
                detail=f"Не удалось проверить стамину персонажа #{cid}",
            )

        current_stamina = attrs.get("current_stamina", 0)
        if current_stamina < final_cost:
            # Get character name for a better error message
            try:
                profile = await http_clients.get_character_profile(cid)
                char_name = profile.get("name", f"Персонаж #{cid}")
            except Exception:
                char_name = f"Персонаж #{cid}"
            raise HTTPException(
                status_code=400,
                detail=f"Недостаточно стамины у {char_name} "
                       f"(нужно {final_cost}, имеется {current_stamina})",
            )

    # 8. Consume stamina from all alive members
    for cid in alive_ids:
        success = await http_clients.consume_stamina(cid, final_cost)
        if not success:
            # Should not happen since we checked, but handle gracefully
            raise HTTPException(
                status_code=400,
                detail=f"Не удалось списать стамину у персонажа #{cid}",
            )

    # 9. Roll corridor events
    corridor_event: Optional[CorridorEventResponse] = None

    # 9a. Roll random battle
    battle_triggered = False
    if corridor.random_battle_chance > 0:
        battle_triggered = random.random() < corridor.random_battle_chance

    if battle_triggered:
        # Initiate actual corridor battle via battle-service
        try:
            battle_id = await initiate_corridor_battle(
                db=db,
                session_id=session_id,
                corridor=corridor,
                dungeon=dungeon,
                session_state_data=redis_state,
                target_room_id=target_room_id,
                auth_token=auth_token,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "Ошибка при создании боя в коридоре %d: %s", corridor.id, e,
            )
            raise HTTPException(
                status_code=502,
                detail="Не удалось создать бой в коридоре",
            )

        corridor_event = CorridorEventResponse(
            type="battle",
            details={
                "battle_id": battle_id,
                "mob_ids": corridor.random_battle_mob_ids or [],
                "target_room_id": target_room_id,
            },
            message="В коридоре на вас напали враги!",
        )

        # Build response without moving to target room
        return MoveResponse(
            corridor_event=corridor_event,
            new_room=None,  # Did not reach target room
            stamina_consumed=final_cost,
            room_event={"type": "battle_started", "battle_id": battle_id},
        )

    # 9b. Roll trap (only if battle not triggered)
    trap_triggered = False
    if corridor.trap_chance > 0:
        trap_triggered = random.random() < corridor.trap_chance

    if trap_triggered and corridor.trap_config:
        trap_cfg = corridor.trap_config if isinstance(corridor.trap_config, dict) else {}
        stat_check = trap_cfg.get("stat_check", "agility")
        difficulty = trap_cfg.get("difficulty", 10)
        fail_damage = trap_cfg.get("fail_damage", 10)

        passed, best_name, best_value = await perform_stat_check(
            redis_state, stat_check, difficulty, dungeon.difficulty_modifier,
        )

        if passed:
            corridor_event = CorridorEventResponse(
                type="trap",
                details={
                    "stat_check": stat_check,
                    "difficulty": difficulty,
                    "best_character": best_name,
                    "best_value": best_value,
                    "passed": True,
                },
                message=f"{best_name} заметил ловушку и обезвредил её!",
            )
        else:
            corridor_event = CorridorEventResponse(
                type="trap",
                details={
                    "stat_check": stat_check,
                    "difficulty": difficulty,
                    "best_character": best_name,
                    "best_value": best_value,
                    "passed": False,
                    "fail_damage": fail_damage,
                },
                message=f"Ловушка сработала! Все получили {fail_damage} урона.",
            )
            # Trap damage tracking: for now just include in response.
            # Actual HP deduction will be refined in Task #14.

    if not corridor_event:
        corridor_event = CorridorEventResponse(
            type="safe",
            details={},
            message="Переход прошёл без происшествий.",
        )

    # 10. Move to target room
    # Update Redis state
    await session_state.set_current_room(session_id, target_room_id)

    # Update DB
    session_obj.current_room_id = target_room_id

    # 11. Create DungeonRoomVisit for all party members (if not already visited)
    all_member_ids = [int(cid) for cid in members.keys()]
    for mid in all_member_ids:
        # Check if visit already exists
        visit_stmt = select(DungeonRoomVisit).where(
            DungeonRoomVisit.dungeon_id == session_obj.dungeon_id,
            DungeonRoomVisit.character_id == mid,
            DungeonRoomVisit.room_id == target_room_id,
        )
        visit_result = await db.execute(visit_stmt)
        existing_visit = visit_result.scalar_one_or_none()

        if existing_visit:
            existing_visit.visit_count += 1
            # last_visited_at updated by onupdate
        else:
            new_visit = DungeonRoomVisit(
                dungeon_id=session_obj.dungeon_id,
                character_id=mid,
                room_id=target_room_id,
            )
            db.add(new_visit)

    # 12. Create DungeonRoomState for this room if not exists for this session
    rs_stmt = select(DungeonRoomState).where(
        DungeonRoomState.session_id == session_id,
        DungeonRoomState.room_id == target_room_id,
    )
    rs_result = await db.execute(rs_stmt)
    room_state_obj = rs_result.scalar_one_or_none()

    if not room_state_obj:
        room_state_obj = DungeonRoomState(
            session_id=session_id,
            room_id=target_room_id,
            is_cleared=False,
            loot_collected=False,
        )
        db.add(room_state_obj)

    await db.commit()
    await db.refresh(session_obj)

    # 13. Build new room view
    room_stmt = select(DungeonRoom).where(DungeonRoom.id == target_room_id)
    room_result = await db.execute(room_stmt)
    target_room = room_result.scalar_one_or_none()

    new_room_view: Optional[RoomViewResponse] = None
    if target_room:
        is_cleared = room_state_obj.is_cleared if room_state_obj else False
        exits = await _get_room_exits(
            db, target_room.id, session_obj.dungeon_id, character_id, dungeon,
        )
        new_room_view = RoomViewResponse(
            id=target_room.id,
            room_type=target_room.room_type,
            name=target_room.name,
            description=target_room.description,
            image_url=target_room.image_url,
            is_entrance=target_room.is_entrance,
            is_boss_room=target_room.is_boss_room,
            is_cleared=is_cleared,
            room_config_visible=_build_room_config_visible(target_room, room_state_obj),
            exits=exits,
            position_x=target_room.position_x,
            position_y=target_room.position_y,
        )

    # 14. Broadcast via WebSocket
    ws_data = {
        "type": "room_entered",
        "data": {
            "room": new_room_view.dict() if new_room_view else None,
            "corridor_event": corridor_event.dict() if corridor_event else None,
            "stamina_consumed": final_cost,
        },
    }
    await ws_manager.broadcast_to_session(session_id, ws_data)

    # 15. Check if target room requires a battle (battle/boss room, not cleared)
    room_event = None
    if target_room and not room_state_obj.is_cleared:
        if target_room.room_type in ("battle", "boss"):
            try:
                battle_id = await initiate_room_battle(
                    db=db,
                    session_id=session_id,
                    room=target_room,
                    dungeon=dungeon,
                    session_state_data=redis_state,
                    auth_token=auth_token,
                )
                room_event = {
                    "type": "battle_started",
                    "battle_id": battle_id,
                    "room_type": target_room.room_type,
                }
            except HTTPException as e:
                logger.error(
                    "Ошибка при инициации боя в комнате %d: %s",
                    target_room.id, e.detail,
                )
                # Don't fail the move — room was entered, but battle failed
                room_event = {
                    "type": "battle_error",
                    "message": str(e.detail),
                }
            except Exception as e:
                logger.error(
                    "Непредвиденная ошибка при инициации боя в комнате %d: %s",
                    target_room.id, e,
                )
                room_event = {
                    "type": "battle_error",
                    "message": "Ошибка при создании боя",
                }

    # 15b. Handle teleport room — automatically move party to target room
    if target_room and target_room.room_type == "teleport" and not room_state_obj.is_cleared:
        room_config = target_room.room_config or {}
        teleport_target_id = room_config.get("target_room_id")
        if teleport_target_id:
            # Mark teleport room as cleared
            room_state_obj.is_cleared = True
            await db.commit()

            # Load target room
            tp_stmt = select(DungeonRoom).where(DungeonRoom.id == int(teleport_target_id))
            tp_result = await db.execute(tp_stmt)
            tp_room = tp_result.scalar_one_or_none()

            if tp_room:
                # Move party to teleport target (no stamina cost)
                await session_state.set_current_room(session_id, tp_room.id)
                session_obj.current_room_id = tp_room.id
                await db.commit()

                # Record visit for all party members
                members_data = redis_state.get("members", {})
                for mid_str in members_data.keys():
                    mid = int(mid_str)
                    v_stmt = select(DungeonRoomVisit).where(
                        DungeonRoomVisit.dungeon_id == session_obj.dungeon_id,
                        DungeonRoomVisit.character_id == mid,
                        DungeonRoomVisit.room_id == tp_room.id,
                    )
                    v_res = await db.execute(v_stmt)
                    v_existing = v_res.scalar_one_or_none()
                    if v_existing:
                        v_existing.visit_count += 1
                    else:
                        db.add(DungeonRoomVisit(
                            dungeon_id=session_obj.dungeon_id,
                            character_id=mid,
                            room_id=tp_room.id,
                        ))
                await db.commit()

                # Create/load room state for target
                tp_room_state = await _get_room_state(db, session_id, tp_room.id)

                # Build new room view
                tp_exits = await _get_room_exits(
                    db, session_id, tp_room, session_obj.dungeon_id, character_id,
                )
                tp_room_view = RoomViewResponse(
                    id=tp_room.id,
                    room_type=tp_room.room_type,
                    name=tp_room.name,
                    description=tp_room.description,
                    image_url=tp_room.image_url,
                    is_entrance=tp_room.is_entrance,
                    is_boss_room=tp_room.is_boss_room,
                    is_cleared=tp_room_state.is_cleared,
                    room_config_visible=_build_room_config_visible(tp_room, tp_room_state),
                    exits=tp_exits,
                    position_x=tp_room.position_x,
                    position_y=tp_room.position_y,
                )

                new_room_view = tp_room_view

                room_event = {
                    "type": "teleported",
                    "target_room_id": tp_room.id,
                    "target_room_name": tp_room.name,
                }

                # Broadcast teleport
                await ws_manager.broadcast_to_session(session_id, {
                    "type": "room_entered",
                    "data": {
                        "room": tp_room_view.dict(),
                        "teleported": True,
                        "message": f"Телепорт! Группа перенесена в «{tp_room.name}»",
                    },
                })

                logger.info(
                    "Телепорт: сессия %d перенесена из комнаты %d в %d",
                    session_id, target_room.id, tp_room.id,
                )

                # Check if teleport target is a battle room
                if not tp_room_state.is_cleared and tp_room.room_type in ("battle", "boss"):
                    try:
                        battle_id = await initiate_room_battle(
                            db=db, session_id=session_id, room=tp_room,
                            dungeon=dungeon, session_state_data=redis_state,
                            auth_token=auth_token,
                        )
                        room_event = {
                            "type": "battle_started",
                            "battle_id": battle_id,
                            "room_type": tp_room.room_type,
                            "teleported_from": target_room.id,
                        }
                    except Exception as e:
                        logger.error("Ошибка боя после телепорта: %s", e)

    # 16. Return MoveResponse
    return MoveResponse(
        corridor_event=corridor_event,
        new_room=new_room_view,
        stamina_consumed=final_cost,
        room_event=room_event,
    )


# =====================================================================
# Room Interaction
# =====================================================================

async def _get_room_state(
    db: AsyncSession, session_id: int, room_id: int,
) -> DungeonRoomState:
    """Load or create DungeonRoomState for a room in this session."""
    stmt = select(DungeonRoomState).where(
        DungeonRoomState.session_id == session_id,
        DungeonRoomState.room_id == room_id,
    )
    result = await db.execute(stmt)
    room_state_obj = result.scalar_one_or_none()
    if room_state_obj is None:
        room_state_obj = DungeonRoomState(
            session_id=session_id,
            room_id=room_id,
            is_cleared=False,
            loot_collected=False,
        )
        db.add(room_state_obj)
        await db.flush()
    return room_state_obj


async def _add_to_group_inventory(
    db: AsyncSession,
    session_id: int,
    item_id: int,
    quantity: int,
    source_description: str,
) -> None:
    """Add an item to the dungeon group inventory (DB + Redis cache)."""
    inv_item = DungeonSessionInventory(
        session_id=session_id,
        item_id=item_id,
        quantity=quantity,
        source_description=source_description,
    )
    db.add(inv_item)


async def interact_with_room(
    db: AsyncSession,
    session_id: int,
    character_id: int,
    action: str,
    choice_index: Optional[int] = None,
    target_character_id: Optional[int] = None,
    item_id: Optional[int] = None,
    quantity: Optional[int] = None,
    auth_token: Optional[str] = None,
) -> InteractResponse:
    """
    Route room interaction by action type.
    Validates session, membership, phase, and delegates to specific handler.
    """
    # 1. Validate session (allow 'completed' for boss chest / mana core interactions)
    session_obj = await _get_session(db, session_id)
    if session_obj.status not in ("active", "completed"):
        raise HTTPException(
            status_code=400,
            detail="Сессия подземелья не активна",
        )

    # 2. Validate character is a member
    is_member = any(m.character_id == character_id for m in session_obj.members)
    if not is_member:
        raise HTTPException(
            status_code=403,
            detail="Персонаж не является участником этой сессии",
        )

    # 3. Check phase from Redis
    redis_state = await session_state.get_session_state(session_id)
    if redis_state is None:
        raise HTTPException(
            status_code=500,
            detail="Состояние сессии не найдено в Redis",
        )

    phase = redis_state.get("phase", "")
    if phase not in ("exploring", "resting"):
        raise HTTPException(
            status_code=400,
            detail="Взаимодействие с комнатой доступно только в фазе исследования",
        )

    # 4. Validate leader for most actions (except complete_rest which
    # any member might trigger, but we still require leader for consistency)
    if session_obj.leader_character_id != character_id:
        raise HTTPException(
            status_code=403,
            detail="Только лидер может взаимодействовать с комнатой",
        )

    # 5. Get current room
    current_room_id = redis_state.get("current_room_id")
    if current_room_id is None:
        raise HTTPException(status_code=400, detail="Текущая комната не определена")

    room_stmt = select(DungeonRoom).where(DungeonRoom.id == current_room_id)
    room_result = await db.execute(room_stmt)
    current_room = room_result.scalar_one_or_none()
    if not current_room:
        raise HTTPException(status_code=500, detail="Комната не найдена в БД")

    # 6. Load dungeon
    dungeon = await _get_dungeon_for_session(db, session_obj.dungeon_id)

    # 7. Load room state
    room_state_obj = await _get_room_state(db, session_id, current_room.id)

    # 8. Route by action
    if action == "open_chest":
        return await _handle_open_chest(
            db, session_id, session_obj, dungeon, current_room, room_state_obj,
            redis_state,
        )
    elif action == "event_choice":
        return await _handle_event_choice(
            db, session_id, session_obj, dungeon, current_room, room_state_obj,
            redis_state, choice_index,
        )
    elif action == "start_rest":
        return await _handle_start_rest(
            db, session_id, session_obj, dungeon, current_room, room_state_obj,
            redis_state,
        )
    elif action == "complete_rest":
        return await _handle_complete_rest(
            db, session_id, session_obj, dungeon, current_room, room_state_obj,
            redis_state,
        )
    elif action == "revive_member":
        return await _handle_revive_member(
            db, session_id, session_obj, dungeon, current_room, room_state_obj,
            redis_state, target_character_id,
        )
    elif action == "merchant_buy":
        return await _handle_merchant_buy(
            db, session_id, session_obj, dungeon, current_room, room_state_obj,
            redis_state, character_id, item_id, quantity,
        )
    elif action == "search_mana_core":
        return await _handle_search_mana_core(
            db, session_id, session_obj, dungeon, current_room, room_state_obj,
            redis_state,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестное действие: {action}",
        )


# =====================================================================
# Action Handlers
# =====================================================================

async def _handle_open_chest(
    db: AsyncSession,
    session_id: int,
    session_obj: DungeonSession,
    dungeon: Dungeon,
    room: DungeonRoom,
    room_state: DungeonRoomState,
    redis_state: Dict,
) -> InteractResponse:
    """Open a treasure chest in treasure or boss rooms."""
    # Validate room type
    if room.room_type not in ("treasure", "boss"):
        raise HTTPException(
            status_code=400,
            detail="Открыть сундук можно только в комнате-сокровищнице или босс-комнате",
        )

    # Validate chest not already opened
    if room_state.loot_collected:
        raise HTTPException(
            status_code=400,
            detail="Сундук уже был открыт",
        )

    # For boss rooms, room must be cleared first
    if room.room_type == "boss" and not room_state.is_cleared:
        raise HTTPException(
            status_code=400,
            detail="Сначала нужно победить босса",
        )

    # Get loot table from room_config (boss rooms use "boss_loot" key)
    room_config = room.room_config if isinstance(room.room_config, dict) else {}
    if room.room_type == "boss":
        loot_table = room_config.get("boss_loot", [])
    else:
        loot_table = room_config.get("loot_table", [])

    loot_gained = []
    for entry in loot_table:
        entry_item_id = entry.get("item_id")
        entry_quantity = entry.get("quantity", 1)
        chance = entry.get("chance", 1.0)

        # Apply dungeon loot_multiplier to chance
        adjusted_chance = min(chance * dungeon.loot_multiplier, 1.0)

        if entry_item_id and random.random() < adjusted_chance:
            await _add_to_group_inventory(
                db, session_id, entry_item_id, entry_quantity,
                f"Сундук: {room.name}",
            )
            # Fetch item_name for the loot response
            loot_item_name = None
            try:
                item_info = await http_clients.get_item_info(entry_item_id)
                loot_item_name = item_info.get("name") or item_info.get("item_name")
            except Exception:
                pass
            loot_gained.append({
                "item_id": entry_item_id,
                "item_name": loot_item_name,
                "quantity": entry_quantity,
            })

    # Mark loot as collected
    room_state.loot_collected = True
    await db.commit()

    # For boss rooms, transition to distributing_loot phase and completed status
    if room.room_type == "boss":
        await session_state.update_session_state(
            session_id,
            phase="distributing_loot",
            status="completed",
        )
        session_obj.status = "completed"
        session_obj.finished_at = datetime.utcnow()
        await db.commit()

    # Update Redis inventory cache
    inv_stmt = select(DungeonSessionInventory).where(
        DungeonSessionInventory.session_id == session_id
    )
    inv_result = await db.execute(inv_stmt)
    all_items = inv_result.scalars().all()
    cache_items = [
        {"item_id": i.item_id, "quantity": i.quantity, "source_description": i.source_description}
        for i in all_items
    ]
    await session_state.set_session_inventory(session_id, cache_items)

    # Broadcast via WebSocket
    await ws_manager.broadcast_to_session(session_id, {
        "type": "loot_added",
        "data": {
            "source": f"Сундук: {room.name}",
            "items": loot_gained,
            "message": "Сундук открыт!" if loot_gained else "Сундук оказался пустым...",
        },
    })

    # For boss rooms, broadcast dungeon completion after loot
    if room.room_type == "boss":
        await ws_manager.broadcast_to_session(session_id, {
            "type": "session_status",
            "data": {
                "status": "completed",
                "phase": "distributing_loot",
                "message": "Подземелье пройдено! Распределите добычу.",
            },
        })

    return InteractResponse(
        action="open_chest",
        success=True,
        message="Сундук открыт!" if loot_gained else "Сундук оказался пустым...",
        loot_gained=loot_gained if loot_gained else None,
    )


async def _handle_event_choice(
    db: AsyncSession,
    session_id: int,
    session_obj: DungeonSession,
    dungeon: Dungeon,
    room: DungeonRoom,
    room_state: DungeonRoomState,
    redis_state: Dict,
    choice_index: Optional[int],
) -> InteractResponse:
    """Handle an event room choice."""
    # Validate room type
    if room.room_type != "event":
        raise HTTPException(
            status_code=400,
            detail="Выбор доступен только в комнате-событии",
        )

    # Validate choice not already made
    if room_state.event_choice_index is not None:
        raise HTTPException(
            status_code=400,
            detail="Выбор уже был сделан в этой комнате",
        )

    # Validate choice_index provided
    if choice_index is None:
        raise HTTPException(
            status_code=400,
            detail="Необходимо указать choice_index",
        )

    # Get choices from room_config
    room_config = room.room_config if isinstance(room.room_config, dict) else {}
    choices = room_config.get("choices", [])

    if choice_index < 0 or choice_index >= len(choices):
        raise HTTPException(
            status_code=400,
            detail=f"Неверный choice_index: {choice_index}. Доступно вариантов: {len(choices)}",
        )

    chosen = choices[choice_index]
    outcome_type = chosen.get("outcome_type", "nothing")
    raw_outcome_data = chosen.get("outcome_data", {})
    # outcome_data may be stored as JSON string from admin editor — parse it
    if isinstance(raw_outcome_data, str):
        try:
            import json
            outcome_data = json.loads(raw_outcome_data)
        except (json.JSONDecodeError, TypeError):
            outcome_data = {}
    else:
        outcome_data = raw_outcome_data if isinstance(raw_outcome_data, dict) else {}
    outcome_text = chosen.get("outcome_text", "")

    result_message = outcome_text or "Выбор сделан."
    loot_gained = None
    damage_taken = None
    effect_applied = None
    gold_spent = None
    teleported_to = None

    if outcome_type == "reward":
        # Add items/gold from outcome_data to group inventory
        items = outcome_data.get("items", [])
        gold = outcome_data.get("gold", 0)
        loot_list = []
        for item_entry in items:
            eid = item_entry.get("item_id")
            eq = item_entry.get("quantity", 1)
            if eid:
                await _add_to_group_inventory(
                    db, session_id, eid, eq, f"Событие: {room.name}",
                )
                loot_list.append({"item_id": eid, "quantity": eq})
        if gold > 0:
            # Add gold to the leader via character-service add_rewards
            leader_id = session_obj.leader_character_id
            try:
                await http_clients.add_gold(leader_id, gold)
            except Exception as exc:
                logger.warning(
                    "Не удалось начислить %d золота лидеру %d: %s",
                    gold, leader_id, exc,
                )
            loot_list.append({"gold": gold})
        loot_gained = loot_list if loot_list else None

    elif outcome_type == "damage":
        dmg = outcome_data.get("damage", 10)
        damage_taken = dmg
        effect_applied = "урон"
        # Note: actual HP deduction would require calling attributes-service
        # for each alive member. For v1 we track it in the response.

    elif outcome_type == "teleport":
        target_room_id = outcome_data.get("target_room_id")
        if target_room_id:
            # Move party to specified room without stamina cost
            await session_state.set_current_room(session_id, target_room_id)
            session_obj.current_room_id = target_room_id

            # Create visit records for the target room
            members = redis_state.get("members", {})
            for mid_str in members.keys():
                mid = int(mid_str)
                visit_stmt = select(DungeonRoomVisit).where(
                    DungeonRoomVisit.dungeon_id == session_obj.dungeon_id,
                    DungeonRoomVisit.character_id == mid,
                    DungeonRoomVisit.room_id == target_room_id,
                )
                visit_result = await db.execute(visit_stmt)
                existing_visit = visit_result.scalar_one_or_none()
                if existing_visit:
                    existing_visit.visit_count += 1
                else:
                    new_visit = DungeonRoomVisit(
                        dungeon_id=session_obj.dungeon_id,
                        character_id=mid,
                        room_id=target_room_id,
                    )
                    db.add(new_visit)

            # Ensure room state exists for target room
            await _get_room_state(db, session_id, target_room_id)

            # Get target room info for response
            tr_stmt = select(DungeonRoom).where(DungeonRoom.id == target_room_id)
            tr_result = await db.execute(tr_stmt)
            target_room = tr_result.scalar_one_or_none()
            teleported_to = {
                "room_id": target_room_id,
                "room_name": target_room.name if target_room else "???",
            }

            await ws_manager.broadcast_to_session(session_id, {
                "type": "room_entered",
                "data": {
                    "room": {
                        "id": target_room_id,
                        "room_type": target_room.room_type if target_room else "unknown",
                        "name": target_room.name if target_room else "???",
                        "description": target_room.description if target_room else "",
                    },
                    "corridor_event": None,
                    "teleported": True,
                },
            })

    elif outcome_type == "battle":
        # Initiate battle with mobs from outcome_data
        mob_template_ids = outcome_data.get("mob_template_ids", [])
        if mob_template_ids:
            try:
                battle_id = await initiate_room_battle(
                    db=db,
                    session_id=session_id,
                    room=room,
                    dungeon=dungeon,
                    session_state_data=redis_state,
                    auth_token=auth_token,
                )
                effect_applied = f"бой начат (battle_id={battle_id})"
            except Exception as e:
                logger.error(
                    "Ошибка при создании боя из события в комнате %d: %s",
                    room.id, e,
                )
                effect_applied = "ошибка при начале боя"

    elif outcome_type == "heal":
        heal_amount = outcome_data.get("heal_amount", 50)
        members = redis_state.get("members", {})
        alive_ids = [
            int(cid) for cid, info in members.items()
            if info.get("status") == "alive"
        ]
        for cid in alive_ids:
            try:
                await http_clients.recover_character(cid, health=heal_amount)
            except Exception:
                logger.warning(
                    "Не удалось восстановить HP персонажу %d при событии", cid,
                )
        effect_applied = f"лечение ({heal_amount} HP)"

    # outcome_type == "nothing" — just flavor text, no special action

    # Save choice_index in room state
    room_state.event_choice_index = choice_index
    await db.commit()

    # Broadcast event result via WebSocket
    await ws_manager.broadcast_to_session(session_id, {
        "type": "event_result",
        "data": {
            "room_id": room.id,
            "choice_index": choice_index,
            "outcome_type": outcome_type,
            "message": result_message,
            "loot_gained": loot_gained,
            "damage_taken": damage_taken,
            "effect_applied": effect_applied,
            "teleported_to": teleported_to,
        },
    })

    return InteractResponse(
        action="event_choice",
        success=True,
        message=result_message,
        loot_gained=loot_gained,
        damage_taken=damage_taken,
        effect_applied=effect_applied,
        teleported_to=teleported_to,
    )


async def _handle_start_rest(
    db: AsyncSession,
    session_id: int,
    session_obj: DungeonSession,
    dungeon: Dungeon,
    room: DungeonRoom,
    room_state: DungeonRoomState,
    redis_state: Dict,
) -> InteractResponse:
    """Start resting in a rest room."""
    # Validate room type
    if room.room_type != "rest":
        raise HTTPException(
            status_code=400,
            detail="Отдых доступен только в комнате отдыха",
        )

    # Check if rest rooms are disabled for this dungeon
    if dungeon.disable_rest_rooms:
        raise HTTPException(
            status_code=400,
            detail="Комнаты отдыха отключены в этом подземелье",
        )

    # Check if rest already used
    extra = room_state.extra_data if isinstance(room_state.extra_data, dict) else {}
    if extra.get("rest_used"):
        raise HTTPException(
            status_code=400,
            detail="Отдых в этой комнате уже использован",
        )
    if extra.get("rest_started_at"):
        raise HTTPException(
            status_code=400,
            detail="Отдых уже начат. Используйте действие complete_rest для завершения.",
        )

    # Get rest config from room_config
    room_config = room.room_config if isinstance(room.room_config, dict) else {}
    heal_percent = room_config.get("heal_percent", 30)
    wait_seconds = room_config.get("wait_seconds", 60)
    gold_cost = room_config.get("gold_cost", 0)

    # If gold_cost > 0, deduct from leader
    gold_spent = None
    if gold_cost > 0:
        success = await http_clients.deduct_gold(
            session_obj.leader_character_id, gold_cost,
        )
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Недостаточно золота для отдыха (нужно {gold_cost})",
            )
        gold_spent = gold_cost

    # Mark rest started with timestamp
    import time
    extra["rest_started_at"] = time.time()
    extra["heal_percent"] = heal_percent
    extra["wait_seconds"] = wait_seconds
    room_state.extra_data = extra
    await db.commit()

    # Set phase to resting
    await session_state.set_phase(session_id, "resting")

    # Broadcast
    await ws_manager.broadcast_to_session(session_id, {
        "type": "rest_started",
        "data": {
            "room_id": room.id,
            "wait_seconds": wait_seconds,
            "heal_percent": heal_percent,
            "gold_cost": gold_cost,
            "message": f"Группа устроилась на привал. Ожидание: {wait_seconds} секунд.",
        },
    })

    return InteractResponse(
        action="start_rest",
        success=True,
        message=f"Отдых начат. Ожидание: {wait_seconds} секунд. Восстановление: {heal_percent}% HP.",
        gold_spent=gold_spent,
    )


async def _handle_complete_rest(
    db: AsyncSession,
    session_id: int,
    session_obj: DungeonSession,
    dungeon: Dungeon,
    room: DungeonRoom,
    room_state: DungeonRoomState,
    redis_state: Dict,
) -> InteractResponse:
    """Complete resting after the timer has elapsed."""
    # Validate room type
    if room.room_type != "rest":
        raise HTTPException(
            status_code=400,
            detail="Завершить отдых можно только в комнате отдыха",
        )

    extra = room_state.extra_data if isinstance(room_state.extra_data, dict) else {}

    # Validate rest was started
    rest_started_at = extra.get("rest_started_at")
    if not rest_started_at:
        raise HTTPException(
            status_code=400,
            detail="Отдых не был начат",
        )

    # Check if rest already used
    if extra.get("rest_used"):
        raise HTTPException(
            status_code=400,
            detail="Отдых в этой комнате уже использован",
        )

    # Validate enough real time has passed
    import time
    wait_seconds = extra.get("wait_seconds", 60)
    elapsed = time.time() - rest_started_at
    if elapsed < wait_seconds:
        remaining = int(wait_seconds - elapsed)
        raise HTTPException(
            status_code=400,
            detail=f"Отдых ещё не завершён. Осталось {remaining} секунд.",
        )

    # Recover HP for all alive members
    heal_percent = extra.get("heal_percent", 30)
    members = redis_state.get("members", {})
    alive_ids = [
        int(cid) for cid, info in members.items()
        if info.get("status") == "alive"
    ]

    recovery_details = []
    for cid in alive_ids:
        try:
            # Get max HP to calculate heal amount
            attrs = await http_clients.get_character_attributes(cid)
            max_hp = attrs.get("max_health", 100)
            heal_amount = max(1, int(max_hp * heal_percent / 100))
            await http_clients.recover_character(cid, health=heal_amount)
            recovery_details.append({
                "character_id": cid,
                "healed": heal_amount,
            })
        except Exception:
            logger.warning(
                "Не удалось восстановить HP персонажу %d при отдыхе", cid,
            )

    # Mark rest as used
    extra["rest_used"] = True
    room_state.extra_data = extra
    await db.commit()

    # Revert phase to exploring
    await session_state.set_phase(session_id, "exploring")

    # Broadcast recovery
    await ws_manager.broadcast_to_session(session_id, {
        "type": "rest_completed",
        "data": {
            "room_id": room.id,
            "heal_percent": heal_percent,
            "recovery_details": recovery_details,
            "message": f"Отдых завершён! Все живые участники восстановили {heal_percent}% HP.",
        },
    })

    return InteractResponse(
        action="complete_rest",
        success=True,
        message=f"Отдых завершён! Все живые участники восстановили {heal_percent}% HP.",
        effect_applied=f"лечение {heal_percent}% HP",
    )


async def _handle_revive_member(
    db: AsyncSession,
    session_id: int,
    session_obj: DungeonSession,
    dungeon: Dungeon,
    room: DungeonRoom,
    room_state: DungeonRoomState,
    redis_state: Dict,
    target_character_id: Optional[int],
) -> InteractResponse:
    """Revive a dead party member in a rest room for gold."""
    # Validate room type
    if room.room_type != "rest":
        raise HTTPException(
            status_code=400,
            detail="Воскрешение доступно только в комнате отдыха",
        )

    # Validate target provided
    if target_character_id is None:
        raise HTTPException(
            status_code=400,
            detail="Необходимо указать target_character_id — ID погибшего участника",
        )

    # Validate target is a dead party member
    members = redis_state.get("members", {})
    target_str = str(target_character_id)
    if target_str not in members:
        raise HTTPException(
            status_code=400,
            detail="Указанный персонаж не является участником группы",
        )
    if members[target_str].get("status") != "dead":
        raise HTTPException(
            status_code=400,
            detail="Указанный персонаж не мёртв",
        )

    # Get gold cost from room_config or default
    room_config = room.room_config if isinstance(room.room_config, dict) else {}
    revive_cost = room_config.get("revive_gold_cost", 500)

    # Deduct gold from leader
    success = await http_clients.deduct_gold(
        session_obj.leader_character_id, revive_cost,
    )
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Недостаточно золота для воскрешения (нужно {revive_cost})",
        )

    # Update member status to alive in Redis and DB
    await session_state.update_member_status(session_id, target_str, "alive")

    member_stmt = select(DungeonSessionMember).where(
        DungeonSessionMember.session_id == session_id,
        DungeonSessionMember.character_id == target_character_id,
    )
    member_result = await db.execute(member_stmt)
    member_obj = member_result.scalar_one_or_none()
    if member_obj:
        member_obj.status = "alive"

    # Recover the revived character to some HP (e.g., 25% max HP)
    try:
        attrs = await http_clients.get_character_attributes(target_character_id)
        max_hp = attrs.get("max_health", 100)
        revive_hp = max(1, int(max_hp * 0.25))
        await http_clients.recover_character(target_character_id, health=revive_hp)
    except Exception:
        logger.warning(
            "Не удалось восстановить HP воскрешённому персонажу %d",
            target_character_id,
        )

    await db.commit()

    # Broadcast
    try:
        profile = await http_clients.get_character_profile(target_character_id)
        target_name = profile.get("name", f"Персонаж #{target_character_id}")
    except Exception:
        target_name = f"Персонаж #{target_character_id}"

    await ws_manager.broadcast_to_session(session_id, {
        "type": "member_status_changed",
        "data": {
            "character_id": target_character_id,
            "name": target_name,
            "new_status": "alive",
            "gold_spent": revive_cost,
            "message": f"{target_name} воскрешён(а) за {revive_cost} золота!",
        },
    })

    return InteractResponse(
        action="revive_member",
        success=True,
        message=f"{target_name} воскрешён(а) за {revive_cost} золота!",
        gold_spent=revive_cost,
    )


async def _handle_merchant_buy(
    db: AsyncSession,
    session_id: int,
    session_obj: DungeonSession,
    dungeon: Dungeon,
    room: DungeonRoom,
    room_state: DungeonRoomState,
    redis_state: Dict,
    buyer_character_id: int,
    buy_item_id: Optional[int],
    buy_quantity: Optional[int],
) -> InteractResponse:
    """Buy an item from a merchant room."""
    # Validate room type
    if room.room_type != "merchant":
        raise HTTPException(
            status_code=400,
            detail="Покупка доступна только в комнате торговца",
        )

    # Check if merchants disabled
    if dungeon.disable_merchants:
        raise HTTPException(
            status_code=400,
            detail="Торговцы отключены в этом подземелье",
        )

    # Validate item_id and quantity
    if buy_item_id is None:
        raise HTTPException(
            status_code=400,
            detail="Необходимо указать item_id для покупки",
        )
    if buy_quantity is None or buy_quantity < 1:
        buy_quantity = 1

    # Get merchant items from room_config
    room_config = room.room_config if isinstance(room.room_config, dict) else {}
    merchant_items = room_config.get("items", [])

    # Find the item in merchant's stock
    merchant_item = None
    merchant_item_index = None
    for idx, mi in enumerate(merchant_items):
        if mi.get("item_id") == buy_item_id:
            merchant_item = mi
            merchant_item_index = idx
            break

    if merchant_item is None:
        raise HTTPException(
            status_code=400,
            detail="Этот предмет не продаётся у торговца",
        )

    price = merchant_item.get("price", 0)
    max_stock = merchant_item.get("stock", 999)

    # Check stock from extra_data (to track purchases)
    extra = room_state.extra_data if isinstance(room_state.extra_data, dict) else {}
    merchant_stock = extra.get("merchant_stock", {})
    # merchant_stock is a dict: { str(item_id): remaining_stock }
    stock_key = str(buy_item_id)
    remaining = merchant_stock.get(stock_key, max_stock)

    if remaining < buy_quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Недостаточно товара. Осталось: {remaining}",
        )

    total_cost = price * buy_quantity

    # Deduct gold from buyer
    if total_cost > 0:
        success = await http_clients.deduct_gold(buyer_character_id, total_cost)
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Недостаточно золота для покупки (нужно {total_cost})",
            )

    # Add item to group inventory
    await _add_to_group_inventory(
        db, session_id, buy_item_id, buy_quantity,
        f"Торговец: {room.name}",
    )

    # Decrement stock in extra_data
    merchant_stock[stock_key] = remaining - buy_quantity
    extra["merchant_stock"] = merchant_stock
    room_state.extra_data = extra
    await db.commit()

    # Broadcast
    await ws_manager.broadcast_to_session(session_id, {
        "type": "loot_added",
        "data": {
            "source": f"Торговец: {room.name}",
            "items": [{"item_id": buy_item_id, "quantity": buy_quantity}],
            "gold_spent": total_cost,
            "message": f"Куплен предмет за {total_cost} золота.",
        },
    })

    return InteractResponse(
        action="merchant_buy",
        success=True,
        message=f"Покупка совершена за {total_cost} золота.",
        loot_gained=[{"item_id": buy_item_id, "quantity": buy_quantity}],
        gold_spent=total_cost,
    )


async def _handle_search_mana_core(
    db: AsyncSession,
    session_id: int,
    session_obj: DungeonSession,
    dungeon: Dungeon,
    room: DungeonRoom,
    room_state: DungeonRoomState,
    redis_state: Dict,
) -> InteractResponse:
    """Search for and attempt to destroy the mana core."""
    # Validate room is mana core room
    if not room.is_mana_core_room:
        raise HTTPException(
            status_code=400,
            detail="Поиск ядра маны доступен только в комнате ядра маны",
        )

    # Validate boss has been defeated
    boss_stmt = select(DungeonRoom).where(
        DungeonRoom.dungeon_id == dungeon.id,
        DungeonRoom.is_boss_room == True,
    )
    boss_result = await db.execute(boss_stmt)
    boss_rooms = boss_result.scalars().all()

    boss_cleared = False
    for br in boss_rooms:
        bs_stmt = select(DungeonRoomState).where(
            DungeonRoomState.session_id == session_id,
            DungeonRoomState.room_id == br.id,
        )
        bs_result = await db.execute(bs_stmt)
        bs = bs_result.scalar_one_or_none()
        if bs and bs.is_cleared:
            boss_cleared = True
            break

    if not boss_cleared:
        raise HTTPException(
            status_code=400,
            detail="Сначала нужно победить босса подземелья",
        )

    # Check if already interacted with mana core
    extra = room_state.extra_data if isinstance(room_state.extra_data, dict) else {}
    if extra.get("mana_core_searched"):
        raise HTTPException(
            status_code=400,
            detail="Ядро маны уже было исследовано",
        )

    # Roll mana core chance
    roll = random.random()
    success = roll < dungeon.mana_core_chance

    extra["mana_core_searched"] = True
    room_state.extra_data = extra

    if success and dungeon.mana_core_item_id:
        # Add mana core crystal to group inventory
        await _add_to_group_inventory(
            db, session_id, dungeon.mana_core_item_id, 1,
            "Ядро маны: Кристалл подземелья",
        )

        # Set session status to completed
        session_obj.status = "completed"
        session_obj.finished_at = datetime.utcnow()

        # Deactivate dungeon
        dungeon.is_active = False

        # Set cooldown
        await session_state.set_dungeon_cooldown(
            dungeon.id, session_id, dungeon.cooldown_hours,
        )

        # Update Redis state
        await session_state.update_session_state(
            session_id,
            phase="distributing_loot",
            status="completed",
        )

        await db.commit()

        # Broadcast
        await ws_manager.broadcast_to_session(session_id, {
            "type": "session_status",
            "data": {
                "status": "completed",
                "mana_core_destroyed": True,
                "message": "Ядро маны уничтожено! Кристалл подземелья получен. "
                           "Подземелье рушится — группа телепортирована на поверхность!",
            },
        })

        logger.info(
            "Ядро маны уничтожено: session=%d, dungeon=%d, item=%d "
            "(шанс=%.2f, бросок=%.4f)",
            session_id, dungeon.id, dungeon.mana_core_item_id,
            dungeon.mana_core_chance, roll,
        )

        return InteractResponse(
            action="search_mana_core",
            success=True,
            message="Ядро маны уничтожено! Получен Кристалл подземелья. "
                    "Подземелье исчезает...",
            loot_gained=[{
                "item_id": dungeon.mana_core_item_id,
                "quantity": 1,
            }],
        )
    else:
        # Failed — dungeon still completed but no crystal
        session_obj.status = "completed"
        session_obj.finished_at = datetime.utcnow()

        await session_state.update_session_state(
            session_id,
            phase="distributing_loot",
            status="completed",
        )

        await db.commit()

        await ws_manager.broadcast_to_session(session_id, {
            "type": "session_status",
            "data": {
                "status": "completed",
                "mana_core_destroyed": False,
                "message": "Ядро маны оказалось слишком сильным... "
                           "Группа отступает. Подземелье пройдено.",
            },
        })

        logger.info(
            "Ядро маны устояло: session=%d, dungeon=%d "
            "(шанс=%.2f, бросок=%.4f)",
            session_id, dungeon.id, dungeon.mana_core_chance, roll,
        )

        return InteractResponse(
            action="search_mana_core",
            success=False,
            message="Ядро маны оказалось слишком сильным... "
                    "Группа отступает. Подземелье пройдено.",
        )


# =====================================================================
# Flee, Loot Distribution, Session Finalization
# =====================================================================

async def flee_dungeon(
    db: AsyncSession,
    session_id: int,
    character_id: int,
) -> FleeResponse:
    """
    Flee the dungeon. Leader only.
    50% chance to lose each item stack in group inventory.
    Sets session status to 'escaped', phase to 'distributing_loot'.
    """
    # 1. Validate session
    session_obj = await _get_session(db, session_id)

    if session_obj.status != "active":
        raise HTTPException(
            status_code=400,
            detail="Побег возможен только из активной сессии",
        )

    # 2. Validate character is the leader
    if session_obj.leader_character_id != character_id:
        raise HTTPException(
            status_code=403,
            detail="Только лидер может инициировать побег",
        )

    # 3. Check phase from Redis — must be exploring (not mid-battle)
    redis_state = await session_state.get_session_state(session_id)
    if redis_state is None:
        raise HTTPException(
            status_code=500,
            detail="Состояние сессии не найдено в Redis",
        )

    phase = redis_state.get("phase", "")
    if phase == "in_battle":
        raise HTTPException(
            status_code=400,
            detail="Нельзя сбежать во время боя",
        )

    # 4. Get group inventory from DB
    inv_stmt = select(DungeonSessionInventory).where(
        DungeonSessionInventory.session_id == session_id
    )
    inv_result = await db.execute(inv_stmt)
    inv_items = inv_result.scalars().all()

    items_lost: List[FleeItemInfo] = []
    items_remaining: List[FleeItemInfo] = []

    # 5. Roll 50% chance for each item stack
    for item in inv_items:
        if random.random() < 0.5:
            # Item lost
            items_lost.append(FleeItemInfo(
                item_id=item.item_id,
                quantity=item.quantity,
            ))
            await db.delete(item)
        else:
            # Item kept
            items_remaining.append(FleeItemInfo(
                item_id=item.item_id,
                quantity=item.quantity,
            ))

    # 6. Update session status
    session_obj.status = "escaped"
    session_obj.finished_at = datetime.utcnow()

    await db.commit()

    # 7. Update Redis state
    await session_state.update_session_state(
        session_id,
        status="escaped",
        phase="distributing_loot",
    )

    # 8. Update Redis inventory cache with remaining items
    cache_items = [
        {"item_id": i.item_id, "quantity": i.quantity}
        for i in items_remaining
    ]
    await session_state.set_session_inventory(session_id, cache_items)

    # 9. Broadcast via WebSocket
    await ws_manager.broadcast_to_session(session_id, {
        "type": "session_status",
        "data": {
            "status": "escaped",
            "items_lost": [i.dict() for i in items_lost],
            "items_remaining": [i.dict() for i in items_remaining],
            "message": "Группа сбежала из подземелья! Часть добычи потеряна.",
        },
    })

    # 10. Build message
    if not items_lost and not items_remaining:
        message = "Группа сбежала из подземелья! Инвентарь был пуст."
    elif not items_lost:
        message = "Группа сбежала из подземелья! Вся добыча сохранена."
    else:
        message = (
            f"Группа сбежала из подземелья! "
            f"Потеряно предметов: {len(items_lost)}, "
            f"сохранено: {len(items_remaining)}."
        )

    return FleeResponse(
        status="escaped",
        items_lost=items_lost,
        items_remaining=items_remaining,
        message=message,
    )


async def distribute_loot(
    db: AsyncSession,
    session_id: int,
    character_id: int,
    distributions: List[dict],
) -> DistributeLootResponse:
    """
    Distribute group inventory items to party members.
    Leader only. Session must be completed or escaped.
    Phase must be distributing_loot.
    """
    # 1. Validate session
    session_obj = await _get_session(db, session_id)

    if session_obj.status not in ("completed", "escaped"):
        raise HTTPException(
            status_code=400,
            detail="Распределение лута доступно только после завершения или побега",
        )

    # 2. Validate character is the leader
    if session_obj.leader_character_id != character_id:
        raise HTTPException(
            status_code=403,
            detail="Только лидер может распределять добычу",
        )

    # 3. Check phase
    redis_state = await session_state.get_session_state(session_id)
    if redis_state:
        phase = redis_state.get("phase", "")
        if phase != "distributing_loot":
            raise HTTPException(
                status_code=400,
                detail="Распределение лута доступно только в фазе распределения",
            )

    # 4. Get current group inventory from DB
    inv_stmt = select(DungeonSessionInventory).where(
        DungeonSessionInventory.session_id == session_id
    )
    inv_result = await db.execute(inv_stmt)
    inv_items = inv_result.scalars().all()

    # Build a lookup: item_id -> list of DungeonSessionInventory rows
    # (multiple rows can exist for the same item_id from different sources)
    inventory_map: Dict[int, List[DungeonSessionInventory]] = {}
    for item in inv_items:
        if item.item_id not in inventory_map:
            inventory_map[item.item_id] = []
        inventory_map[item.item_id].append(item)

    # Calculate total available quantity per item_id
    available_qty: Dict[int, int] = {}
    for item_id, rows in inventory_map.items():
        available_qty[item_id] = sum(r.quantity for r in rows)

    # 5. Get session member character IDs
    member_char_ids = set(m.character_id for m in session_obj.members)

    # 6. Validate all distributions
    # Track how much of each item_id we plan to distribute
    requested_qty: Dict[int, int] = {}
    for dist in distributions:
        d_item_id = dist.get("item_id")
        d_quantity = dist.get("quantity", 0)
        d_to_char = dist.get("to_character_id")

        if d_quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"Количество должно быть положительным (item_id={d_item_id})",
            )

        if d_item_id not in available_qty:
            raise HTTPException(
                status_code=400,
                detail=f"Предмет {d_item_id} отсутствует в групповом инвентаре",
            )

        if d_to_char not in member_char_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Персонаж {d_to_char} не является участником сессии",
            )

        requested_qty[d_item_id] = requested_qty.get(d_item_id, 0) + d_quantity

    # Check total requested doesn't exceed available
    for item_id, req in requested_qty.items():
        if req > available_qty.get(item_id, 0):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Запрошено {req} единиц предмета {item_id}, "
                    f"но в инвентаре только {available_qty.get(item_id, 0)}"
                ),
            )

    # 7. Process distributions
    for dist in distributions:
        d_item_id = dist["item_id"]
        d_quantity = dist["quantity"]
        d_to_char = dist["to_character_id"]

        # Add item to character's personal inventory via inventory-service
        await http_clients.add_item_to_character(d_to_char, d_item_id, d_quantity)

        # Subtract from group inventory DB rows
        remaining_to_subtract = d_quantity
        rows = inventory_map.get(d_item_id, [])
        for row in rows:
            if remaining_to_subtract <= 0:
                break
            if row.quantity <= remaining_to_subtract:
                remaining_to_subtract -= row.quantity
                row.quantity = 0
            else:
                row.quantity -= remaining_to_subtract
                remaining_to_subtract = 0

    # Delete rows with quantity <= 0
    for rows in inventory_map.values():
        for row in rows:
            if row.quantity <= 0:
                await db.delete(row)

    await db.commit()

    # 8. Get remaining inventory
    inv_stmt2 = select(DungeonSessionInventory).where(
        DungeonSessionInventory.session_id == session_id
    )
    inv_result2 = await db.execute(inv_stmt2)
    remaining_items = inv_result2.scalars().all()
    remaining_resp = [
        GroupInventoryItemResponse(
            item_id=item.item_id,
            quantity=item.quantity,
            source_description=item.source_description,
        )
        for item in remaining_items
    ]

    # 9. Update Redis inventory cache
    cache_items = [
        {"item_id": i.item_id, "quantity": i.quantity, "source_description": i.source_description}
        for i in remaining_items
    ]
    await session_state.set_session_inventory(session_id, cache_items)

    # 10. Broadcast via WebSocket
    await ws_manager.broadcast_to_session(session_id, {
        "type": "loot_distributed",
        "data": {
            "distributions": distributions,
            "remaining_count": len(remaining_resp),
            "message": (
                "Добыча распределена!"
                if not remaining_resp
                else f"Часть добычи распределена. Осталось предметов: {len(remaining_resp)}."
            ),
        },
    })

    return DistributeLootResponse(
        success=True,
        message=(
            "Вся добыча распределена!"
            if not remaining_resp
            else f"Добыча частично распределена. Осталось предметов: {len(remaining_resp)}."
        ),
        remaining_inventory=remaining_resp,
    )


async def finalize_session(
    db: AsyncSession,
    session_id: int,
    character_id: int,
    force: bool = False,
) -> FinalizeResponse:
    """
    Finalize a completed/escaped session.
    Sets dungeon cooldown, cleans up Redis, closes WebSocket connections.
    """
    # 1. Validate session
    session_obj = await _get_session(db, session_id)

    if session_obj.status not in ("completed", "escaped"):
        raise HTTPException(
            status_code=400,
            detail="Завершить можно только пройденную или покинутую сессию",
        )

    # 2. Validate character is the leader
    if session_obj.leader_character_id != character_id:
        raise HTTPException(
            status_code=403,
            detail="Только лидер может завершить сессию",
        )

    # 3. Check if group inventory is empty
    inv_stmt = select(DungeonSessionInventory).where(
        DungeonSessionInventory.session_id == session_id
    )
    inv_result = await db.execute(inv_stmt)
    remaining_items = inv_result.scalars().all()

    if remaining_items and not force:
        raise HTTPException(
            status_code=400,
            detail=(
                "В групповом инвентаре остались нераспределённые предметы. "
                "Распределите добычу или используйте force=true для принудительного завершения "
                "(оставшиеся предметы будут потеряны)."
            ),
        )

    # Force finalize: delete remaining items
    if remaining_items and force:
        for item in remaining_items:
            await db.delete(item)

    # 4. Load dungeon for cooldown hours
    dungeon = await _get_dungeon_for_session(db, session_obj.dungeon_id)

    # 5. Set dungeon cooldown
    cooldown_hours = dungeon.cooldown_hours
    cooldown_until = datetime.utcnow() + timedelta(hours=cooldown_hours)

    # Redis cooldown
    await session_state.set_dungeon_cooldown(
        dungeon.id, session_id, cooldown_hours,
    )

    # DB cooldown
    session_obj.cooldown_until = cooldown_until
    if not session_obj.finished_at:
        session_obj.finished_at = datetime.utcnow()

    await db.commit()

    # 6. Collect member character IDs for cleanup
    member_char_ids = [m.character_id for m in session_obj.members]

    # 7. Cleanup Redis keys
    await session_state.cleanup_session(session_id, member_char_ids)

    # 8. Close all WebSocket connections
    await ws_manager.cleanup_session(session_id)

    logger.info(
        "Сессия %d завершена. Кулдаун подземелья %d: %d часов (до %s)",
        session_id, dungeon.id, cooldown_hours, cooldown_until.isoformat(),
    )

    return FinalizeResponse(
        message=f"Подземелье пройдено! Кулдаун: {cooldown_hours} часов.",
        cooldown_until=cooldown_until,
    )


async def admin_force_cleanup_session(
    db: AsyncSession,
    session_id: int,
) -> dict:
    """
    Admin-only: force cleanup any dungeon session regardless of state.
    Sets status to 'escaped', cleans up Redis, closes WebSockets.
    No leader check, no inventory check, no cooldown.
    """
    session_obj = await _get_session(db, session_id)

    member_char_ids = [m.character_id for m in session_obj.members]

    # Delete remaining inventory
    inv_stmt = select(DungeonSessionInventory).where(
        DungeonSessionInventory.session_id == session_id
    )
    inv_result = await db.execute(inv_stmt)
    for item in inv_result.scalars().all():
        await db.delete(item)

    # Update DB status
    old_status = session_obj.status
    if session_obj.status not in ("completed", "escaped", "wiped"):
        session_obj.status = "escaped"
    if not session_obj.finished_at:
        session_obj.finished_at = datetime.utcnow()

    await db.commit()

    # Cleanup Redis
    await session_state.cleanup_session(session_id, member_char_ids)

    # Close WebSocket connections
    await ws_manager.cleanup_session(session_id)

    logger.info(
        "Admin force-cleanup: сессия %d (было: %s), освобождены персонажи: %s",
        session_id, old_status, member_char_ids,
    )

    return {
        "message": f"Сессия {session_id} принудительно завершена",
        "session_id": session_id,
        "previous_status": old_status,
        "freed_characters": member_char_ids,
    }
