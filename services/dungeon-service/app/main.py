import os
import asyncio
import logging
from typing import List

from fastapi import FastAPI, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db, async_session
from auth_http import get_admin_user, get_current_user_via_http, UserRead, authenticate_websocket
from models import Dungeon, DungeonSessionMember
import crud
import gameplay
import http_clients
import ws_manager
from schemas import (
    DungeonCreate, DungeonUpdate, DungeonResponse, DungeonListResponse,
    DungeonDetailResponse, DungeonAtLocationResponse,
    DungeonRoomCreate, DungeonRoomUpdate, DungeonRoomResponse,
    DungeonCorridorCreate, DungeonCorridorUpdate, DungeonCorridorResponse,
    DungeonValidationResponse,
    SessionCreateRequest, SessionInviteRequest, SessionLeaveRequest,
    SessionEnterRequest, SessionResponse, SessionStateResponse,
    MoveRequest, MoveResponse,
    BattleCallbackRequest,
    InteractRequest, InteractResponse,
    FleeRequest, FleeResponse,
    DistributeLootRequest, DistributeLootResponse,
    FinalizeRequest, FinalizeResponse,
)
import session_state

logger = logging.getLogger(__name__)

app = FastAPI()

cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/dungeons/health")
async def health():
    return {"status": "ok"}


# ===========================
#  Admin: Dungeons
# ===========================

@app.post(
    "/dungeons/admin/dungeons",
    response_model=DungeonResponse,
    status_code=201,
)
async def admin_create_dungeon(
    data: DungeonCreate,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_admin_user),
):
    dungeon = await crud.create_dungeon(db, data)
    return dungeon


@app.get(
    "/dungeons/admin/dungeons",
    response_model=List[DungeonListResponse],
)
async def admin_list_dungeons(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_admin_user),
):
    return await crud.list_dungeons(db, skip=skip, limit=limit)


@app.get(
    "/dungeons/admin/dungeons/{dungeon_id}",
    response_model=DungeonDetailResponse,
)
async def admin_get_dungeon(
    dungeon_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_admin_user),
):
    return await crud.get_dungeon_detail(db, dungeon_id)


@app.put(
    "/dungeons/admin/dungeons/{dungeon_id}",
    response_model=DungeonResponse,
)
async def admin_update_dungeon(
    dungeon_id: int,
    data: DungeonUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_admin_user),
):
    return await crud.update_dungeon(db, dungeon_id, data)


@app.delete(
    "/dungeons/admin/dungeons/{dungeon_id}",
    status_code=204,
)
async def admin_delete_dungeon(
    dungeon_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_admin_user),
):
    await crud.delete_dungeon(db, dungeon_id)


# ===========================
#  Admin: Rooms
# ===========================

@app.post(
    "/dungeons/admin/dungeons/{dungeon_id}/rooms",
    response_model=DungeonRoomResponse,
    status_code=201,
)
async def admin_create_room(
    dungeon_id: int,
    data: DungeonRoomCreate,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_admin_user),
):
    return await crud.create_room(db, dungeon_id, data)


@app.put(
    "/dungeons/admin/rooms/{room_id}",
    response_model=DungeonRoomResponse,
)
async def admin_update_room(
    room_id: int,
    data: DungeonRoomUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_admin_user),
):
    return await crud.update_room(db, room_id, data)


@app.delete(
    "/dungeons/admin/rooms/{room_id}",
    status_code=204,
)
async def admin_delete_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_admin_user),
):
    await crud.delete_room(db, room_id)


# ===========================
#  Admin: Corridors
# ===========================

@app.post(
    "/dungeons/admin/dungeons/{dungeon_id}/corridors",
    response_model=DungeonCorridorResponse,
    status_code=201,
)
async def admin_create_corridor(
    dungeon_id: int,
    data: DungeonCorridorCreate,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_admin_user),
):
    return await crud.create_corridor(db, dungeon_id, data)


@app.put(
    "/dungeons/admin/corridors/{corridor_id}",
    response_model=DungeonCorridorResponse,
)
async def admin_update_corridor(
    corridor_id: int,
    data: DungeonCorridorUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_admin_user),
):
    return await crud.update_corridor(db, corridor_id, data)


@app.delete(
    "/dungeons/admin/corridors/{corridor_id}",
    status_code=204,
)
async def admin_delete_corridor(
    corridor_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_admin_user),
):
    await crud.delete_corridor(db, corridor_id)


# ===========================
#  Admin: Validation
# ===========================

@app.post(
    "/dungeons/admin/dungeons/{dungeon_id}/validate",
    response_model=DungeonValidationResponse,
)
async def admin_validate_dungeon(
    dungeon_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_admin_user),
):
    return await crud.validate_dungeon(db, dungeon_id)


# ===========================
#  Player: Dungeons at Location
# ===========================

@app.get(
    "/dungeons/at-location/{location_id}",
    response_model=List[DungeonAtLocationResponse],
)
async def get_dungeons_at_location(
    location_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """List active dungeons at a given location with cooldown info. Requires JWT auth."""
    stmt = (
        select(Dungeon)
        .where(Dungeon.location_id == location_id, Dungeon.is_active == True)
        .order_by(Dungeon.recommended_level.asc(), Dungeon.id.asc())
    )
    result = await db.execute(stmt)
    dungeons = result.scalars().all()

    response = []
    for d in dungeons:
        is_on_cooldown, remaining = await session_state.check_dungeon_cooldown(d.id)
        response.append(
            DungeonAtLocationResponse(
                id=d.id,
                name=d.name,
                description=d.description,
                lore_text=d.lore_text,
                stability_type=d.stability_type,
                danger_level=d.danger_level,
                recommended_level=d.recommended_level,
                recommended_party_size=d.recommended_party_size,
                is_on_cooldown=is_on_cooldown,
                cooldown_remaining_seconds=remaining,
                image_url=d.image_url,
            )
        )
    return response


# ===========================
#  Player: Session Management
# ===========================

@app.post(
    "/dungeons/{dungeon_id}/sessions",
    response_model=SessionResponse,
    status_code=201,
)
async def create_session(
    dungeon_id: int,
    data: SessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Create a dungeon session (party formation). Requires JWT auth."""
    return await gameplay.create_session(
        db=db,
        character_id=data.character_id,
        dungeon_id=dungeon_id,
        user_id=user.id,
    )


@app.post(
    "/dungeons/sessions/{session_id}/invite",
    response_model=SessionResponse,
)
async def invite_member(
    session_id: int,
    data: SessionInviteRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Invite a character to the party. Leader only. Requires JWT auth."""
    # We need the leader's character_id — the authenticated user must own
    # the leader character. gameplay.invite_member verifies this internally.
    # We pass the invitee character_id from the request body.
    # The inviter is determined inside invite_member by checking who the leader is.
    session_obj = await gameplay._get_session(db, session_id)
    return await gameplay.invite_member(
        db=db,
        session_id=session_id,
        inviter_character_id=session_obj.leader_character_id,
        invitee_character_id=data.character_id,
        user_id=user.id,
    )


@app.post(
    "/dungeons/sessions/{session_id}/leave",
    response_model=SessionResponse,
)
async def leave_session(
    session_id: int,
    data: SessionLeaveRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Leave a forming session. Requires JWT auth."""
    # Verify the character belongs to the authenticated user
    profile = await http_clients.get_character_profile(data.character_id)
    if profile.get("user_id") != user.id:
        raise HTTPException(
            status_code=403,
            detail="Этот персонаж не принадлежит вам",
        )

    result = await gameplay.leave_session(
        db=db,
        session_id=session_id,
        character_id=data.character_id,
    )
    if result is None:
        # Session was deleted (last member left)
        return SessionResponse(
            session_id=session_id,
            dungeon_id=0,
            status="disbanded",
            leader_character_id=0,
            members=[],
        )
    return result


@app.post(
    "/dungeons/sessions/{session_id}/enter",
    response_model=SessionStateResponse,
)
async def enter_dungeon(
    session_id: int,
    data: SessionEnterRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Start dungeon run. Leader only. Requires JWT auth."""
    # Verify the character belongs to the authenticated user
    profile = await http_clients.get_character_profile(data.character_id)
    if profile.get("user_id") != user.id:
        raise HTTPException(
            status_code=403,
            detail="Этот персонаж не принадлежит вам",
        )

    return await gameplay.enter_dungeon(
        db=db,
        session_id=session_id,
        character_id=data.character_id,
    )


@app.get(
    "/dungeons/sessions/{session_id}/state",
    response_model=SessionStateResponse,
)
async def get_session_state_endpoint(
    session_id: int,
    character_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Get current session state. Requires JWT auth."""
    # Verify the character belongs to the authenticated user
    profile = await http_clients.get_character_profile(character_id)
    if profile.get("user_id") != user.id:
        raise HTTPException(
            status_code=403,
            detail="Этот персонаж не принадлежит вам",
        )

    return await gameplay.get_session_state(
        db=db,
        session_id=session_id,
        character_id=character_id,
    )


# ===========================
#  Player: Movement
# ===========================

@app.post(
    "/dungeons/sessions/{session_id}/move",
    response_model=MoveResponse,
)
async def move_to_room(
    session_id: int,
    data: MoveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Move party to adjacent room via corridor. Leader only. Requires JWT auth."""
    # Verify the character belongs to the authenticated user
    profile = await http_clients.get_character_profile(data.character_id)
    if profile.get("user_id") != user.id:
        raise HTTPException(
            status_code=403,
            detail="Этот персонаж не принадлежит вам",
        )

    # Extract JWT token for battle-service calls
    auth_header = request.headers.get("Authorization", "")
    auth_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None

    return await gameplay.move_to_room(
        db=db,
        session_id=session_id,
        character_id=data.character_id,
        corridor_id=data.corridor_id,
        auth_token=auth_token,
    )


# ===========================
#  Player: Room Interaction
# ===========================

@app.post(
    "/dungeons/sessions/{session_id}/interact",
    response_model=InteractResponse,
)
async def interact_with_room_endpoint(
    session_id: int,
    data: InteractRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Interact with the current room (open chest, event choice, merchant, rest, etc.). Requires JWT auth."""
    # Verify the character belongs to the authenticated user
    profile = await http_clients.get_character_profile(data.character_id)
    if profile.get("user_id") != user.id:
        raise HTTPException(
            status_code=403,
            detail="Этот персонаж не принадлежит вам",
        )

    auth_header = request.headers.get("Authorization", "")
    auth_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None

    return await gameplay.interact_with_room(
        db=db,
        session_id=session_id,
        character_id=data.character_id,
        action=data.action,
        choice_index=data.choice_index,
        target_character_id=data.target_character_id,
        item_id=data.item_id,
        quantity=data.quantity,
        auth_token=auth_token,
    )


# ===========================
#  Player: Flee
# ===========================

@app.post(
    "/dungeons/sessions/{session_id}/flee",
    response_model=FleeResponse,
)
async def flee_dungeon_endpoint(
    session_id: int,
    data: FleeRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Flee the dungeon. Leader only. 50% chance to lose each item. Requires JWT auth."""
    # Verify the character belongs to the authenticated user
    profile = await http_clients.get_character_profile(data.character_id)
    if profile.get("user_id") != user.id:
        raise HTTPException(
            status_code=403,
            detail="Этот персонаж не принадлежит вам",
        )

    return await gameplay.flee_dungeon(
        db=db,
        session_id=session_id,
        character_id=data.character_id,
    )


# ===========================
#  Player: Loot Distribution
# ===========================

@app.post(
    "/dungeons/sessions/{session_id}/distribute-loot",
    response_model=DistributeLootResponse,
)
async def distribute_loot_endpoint(
    session_id: int,
    data: DistributeLootRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Distribute group inventory to party members. Leader only. Requires JWT auth."""
    # Verify the character belongs to the authenticated user
    profile = await http_clients.get_character_profile(data.character_id)
    if profile.get("user_id") != user.id:
        raise HTTPException(
            status_code=403,
            detail="Этот персонаж не принадлежит вам",
        )

    # Convert Pydantic models to dicts for gameplay function
    distributions = [
        {
            "item_id": d.item_id,
            "quantity": d.quantity,
            "to_character_id": d.to_character_id,
        }
        for d in data.distributions
    ]

    return await gameplay.distribute_loot(
        db=db,
        session_id=session_id,
        character_id=data.character_id,
        distributions=distributions,
    )


# ===========================
#  Player: Finalize Session
# ===========================

@app.post(
    "/dungeons/sessions/{session_id}/finalize",
    response_model=FinalizeResponse,
)
async def finalize_session_endpoint(
    session_id: int,
    data: FinalizeRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Finalize session after loot distribution. Sets cooldown. Leader only. Requires JWT auth."""
    # Verify the character belongs to the authenticated user
    profile = await http_clients.get_character_profile(data.character_id)
    if profile.get("user_id") != user.id:
        raise HTTPException(
            status_code=403,
            detail="Этот персонаж не принадлежит вам",
        )

    return await gameplay.finalize_session(
        db=db,
        session_id=session_id,
        character_id=data.character_id,
        force=data.force,
    )


# ===========================
#  Public: Character Active Session Check
# ===========================

@app.get("/dungeons/my-session/{character_id}")
async def get_my_active_session(
    character_id: int,
    user: UserRead = Depends(get_current_user_via_http),
):
    """
    Check if a character has an active dungeon session.
    Returns session_id if active, null otherwise.
    """
    active = await session_state.get_character_active_session(character_id)
    if active is not None:
        return {"in_dungeon": True, "session_id": active}
    return {"in_dungeon": False, "session_id": None}


# ===========================
#  Internal: Character Session Check
# ===========================

@app.get("/dungeons/internal/character-session/{character_id}")
async def check_character_session(character_id: int):
    """
    Internal endpoint: check if a character is currently in a dungeon session.
    Blocked by Nginx for external access.
    """
    active = await session_state.get_character_active_session(character_id)
    if active is not None:
        return {"in_dungeon": True, "session_id": active}
    return {"in_dungeon": False, "session_id": None}


# ===========================
#  Internal: Battle Callback
# ===========================

@app.post("/dungeons/internal/battle-callback")
async def battle_callback(
    data: BattleCallbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Internal endpoint: called when a dungeon battle ends (backup to polling).
    Processes battle results — marks room cleared, updates casualties, etc.
    Blocked by Nginx for external access.
    """
    session_id = data.session_id
    battle_id = data.battle_id

    # Verify session exists and has this battle active
    redis_state_data = await session_state.get_session_state(session_id)
    if redis_state_data is None:
        raise HTTPException(
            status_code=404,
            detail="Сессия подземелья не найдена",
        )

    active_bid = redis_state_data.get("active_battle_id")
    if active_bid != battle_id:
        logger.warning(
            "Battle callback для session=%d: ожидался battle_id=%s, получен %d",
            session_id, active_bid, battle_id,
        )
        return {"status": "ignored", "reason": "battle_id_mismatch"}

    # Try to get full battle state for detailed processing
    try:
        battle_state_data = await http_clients.get_battle_state(battle_id)
        results = await gameplay.process_battle_completion(
            db, session_id, battle_id, battle_state_data,
        )
    except HTTPException as e:
        if e.status_code == 404:
            # Battle state already expired — do best-effort cleanup
            logger.info(
                "Battle callback: state for battle %d not found, cleaning up",
                battle_id,
            )
            await session_state.clear_active_battle(session_id)
            results = {"battle_id": battle_id, "cleanup": True}
        else:
            raise
    except Exception as e:
        logger.error(
            "Ошибка при обработке battle callback (battle=%d, session=%d): %s",
            battle_id, session_id, e,
        )
        raise HTTPException(
            status_code=500,
            detail="Ошибка при обработке результатов боя",
        )

    return {"status": "processed", "results": results}


# ===========================
#  WebSocket: Dungeon Session
# ===========================

@app.websocket("/dungeons/ws/{session_id}")
async def dungeon_websocket(
    websocket: WebSocket,
    session_id: int,
    token: str = Query(...),
):
    """
    WebSocket endpoint for real-time dungeon session updates.
    Auth via ?token= query param. Only session members can connect.
    Server pushes events; client may only send heartbeat.
    """
    # 1. Authenticate via JWT
    user = await authenticate_websocket(token)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    user_id = user["id"]

    # 2. Verify user is a member of this dungeon session
    async with async_session() as db:
        result = await db.execute(
            select(DungeonSessionMember).where(
                DungeonSessionMember.session_id == session_id,
                DungeonSessionMember.user_id == user_id,
            )
        )
        member = result.scalars().first()
        if not member:
            await websocket.close(code=4003, reason="Forbidden")
            return

    # 3. Accept connection and register
    await websocket.accept()
    await ws_manager.connect(session_id, user_id, websocket)

    # 4. Read loop with 30s ping keepalive
    try:
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(), timeout=30.0,
                )
                # Only handle heartbeat; ignore everything else
                if isinstance(data, dict) and data.get("type") == "heartbeat":
                    await ws_manager.send_to_user(
                        session_id, user_id, {"type": "heartbeat_ack", "data": {}},
                    )
            except asyncio.TimeoutError:
                # Send application-level ping on timeout
                await websocket.send_json({"type": "ping", "data": {}})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await ws_manager.disconnect(session_id, user_id)
