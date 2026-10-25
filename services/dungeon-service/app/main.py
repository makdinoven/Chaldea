import os
import asyncio
import logging
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import get_db, async_session
from auth_http import (
    get_current_user_via_http,
    require_permission,
    UserRead,
    authenticate_websocket,
    verify_internal_token,
)
from models import Dungeon, DungeonSession, DungeonSessionMember
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
    BulkRoomPositionUpdate, BulkPositionUpdateResponse,
    SessionCreateRequest,
    SessionEnterRequest, SessionResponse, SessionStateResponse,
    MoveRequest, MoveResponse, PickLockRequest, PickLockResponse,
    VoteRequest, PartyVotesResponse, PingRequest,
    ChallengeStartRequest, ChallengeStartResponse, ChallengeFinishRequest, ChallengeResult,
    ChallengeStepRequest, ChallengeStepResponse, LightRequest, LightResponse, ChatSayRequest, ChatEntry,
    BattleCallbackRequest,
    InteractRequest, InteractResponse,
    FleeRequest, FleeResponse,
    DistributeLootRequest, DistributeLootResponse,
    FinalizeRequest, FinalizeResponse,
    AdminSessionResponse,
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

# RBAC (FEAT-035 / user-service migration 0024). Admin gets everything
# automatically; moderator has all four, editor only `view`.
can_view = require_permission("dungeons:view")
can_create = require_permission("dungeons:create")
can_edit = require_permission("dungeons:edit")
can_delete = require_permission("dungeons:delete")


@app.get("/dungeons/health")
async def health():
    return {"status": "ok"}


# ===========================
#  Background sweeper (FEAT-175)
# ===========================

_sweeper_task: Optional[asyncio.Task] = None


async def _sweep_loop():
    """Every SWEEP_INTERVAL_SECONDS: close abandoned runs (24 h idle = escape),
    finish runs whose battle ended unseen, rebuild lost Redis state.
    Single uvicorn worker; every step is idempotent and row-locked."""
    while True:
        await asyncio.sleep(gameplay.SWEEP_INTERVAL_SECONDS)
        try:
            async with async_session() as db:
                stats = await gameplay.sweep_sessions(db)
            if any(stats.values()):
                logger.info("Dungeon sweep: %s", stats)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Dungeon sweep failed")


@app.on_event("startup")
async def _start_sweeper():
    global _sweeper_task
    if os.environ.get("DUNGEON_SWEEPER_DISABLED") == "1":
        return
    _sweeper_task = asyncio.create_task(_sweep_loop())


@app.on_event("shutdown")
async def _stop_sweeper():
    if _sweeper_task is not None:
        _sweeper_task.cancel()


def _bearer(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    return auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None


async def _require_own_character(character_id: int, user: UserRead) -> dict:
    profile = await http_clients.get_character_profile(character_id)
    if profile.get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="Этот персонаж не принадлежит вам")
    return profile


# ===========================
#  Admin: Dungeons
# ===========================

@app.post("/dungeons/admin/dungeons", response_model=DungeonResponse, status_code=201)
async def admin_create_dungeon(
    data: DungeonCreate,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(can_create),
):
    return await crud.create_dungeon(db, data)


@app.get("/dungeons/admin/dungeons", response_model=List[DungeonListResponse])
async def admin_list_dungeons(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(can_view),
):
    return await crud.list_dungeons(db, skip=skip, limit=limit)


@app.get("/dungeons/admin/dungeons/{dungeon_id}", response_model=DungeonDetailResponse)
async def admin_get_dungeon(
    dungeon_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(can_view),
):
    return await crud.get_dungeon_detail(db, dungeon_id)


@app.put("/dungeons/admin/dungeons/{dungeon_id}", response_model=DungeonResponse)
async def admin_update_dungeon(
    dungeon_id: int,
    data: DungeonUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(can_edit),
):
    return await crud.update_dungeon(db, dungeon_id, data)


@app.delete("/dungeons/admin/dungeons/{dungeon_id}", status_code=204)
async def admin_delete_dungeon(
    dungeon_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(can_delete),
):
    # Deleting would cascade the running session away and leave its members
    # activity-locked forever.
    if await gameplay.get_occupying_session(db, dungeon_id) is not None:
        raise HTTPException(
            status_code=409,
            detail="В подземелье находится группа — сначала завершите её сессию",
        )
    await crud.delete_dungeon(db, dungeon_id)


# ===========================
#  Admin: Rooms
# ===========================

@app.post("/dungeons/admin/dungeons/{dungeon_id}/rooms", response_model=DungeonRoomResponse, status_code=201)
async def admin_create_room(
    dungeon_id: int,
    data: DungeonRoomCreate,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(can_edit),
):
    return await crud.create_room(db, dungeon_id, data)


@app.put("/dungeons/admin/rooms/{room_id}", response_model=DungeonRoomResponse)
async def admin_update_room(
    room_id: int,
    data: DungeonRoomUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(can_edit),
):
    return await crud.update_room(db, room_id, data)


@app.delete("/dungeons/admin/rooms/{room_id}", status_code=204)
async def admin_delete_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(can_edit),
):
    await crud.delete_room(db, room_id)


@app.put("/dungeons/admin/dungeons/{dungeon_id}/rooms/positions", response_model=BulkPositionUpdateResponse)
async def admin_bulk_update_room_positions(
    dungeon_id: int,
    data: BulkRoomPositionUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(can_edit),
):
    updated = await crud.bulk_update_room_positions(db, dungeon_id, data.positions)
    return BulkPositionUpdateResponse(updated=updated)


# ===========================
#  Admin: Corridors
# ===========================

@app.post("/dungeons/admin/dungeons/{dungeon_id}/corridors", response_model=DungeonCorridorResponse, status_code=201)
async def admin_create_corridor(
    dungeon_id: int,
    data: DungeonCorridorCreate,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(can_edit),
):
    return await crud.create_corridor(db, dungeon_id, data)


@app.put("/dungeons/admin/corridors/{corridor_id}", response_model=DungeonCorridorResponse)
async def admin_update_corridor(
    corridor_id: int,
    data: DungeonCorridorUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(can_edit),
):
    return await crud.update_corridor(db, corridor_id, data)


@app.delete("/dungeons/admin/corridors/{corridor_id}", status_code=204)
async def admin_delete_corridor(
    corridor_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(can_edit),
):
    await crud.delete_corridor(db, corridor_id)


@app.post("/dungeons/admin/dungeons/{dungeon_id}/validate", response_model=DungeonValidationResponse)
async def admin_validate_dungeon(
    dungeon_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(can_view),
):
    return await crud.validate_dungeon(db, dungeon_id)


# ===========================
#  Admin: Session Management
# ===========================

@app.get("/dungeons/admin/sessions", response_model=List[AdminSessionResponse])
async def admin_list_sessions(
    status: str = Query(None, description="Filter by status: forming, active, completed, escaped, wiped"),
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(can_view),
):
    """List dungeon sessions. Without a filter: every session that is not
    fully closed yet (active runs + runs awaiting loot distribution)."""
    stmt = select(DungeonSession).options(
        selectinload(DungeonSession.members),
        selectinload(DungeonSession.dungeon),
    ).order_by(DungeonSession.created_at.desc())
    if status:
        stmt = stmt.where(DungeonSession.status == status)
    else:
        stmt = stmt.where(DungeonSession.finalized_at.is_(None), DungeonSession.status != "wiped")
    sessions = (await db.execute(stmt)).scalars().all()
    return [
        AdminSessionResponse(
            id=s.id,
            dungeon_id=s.dungeon_id,
            dungeon_name=s.dungeon.name if s.dungeon else None,
            leader_character_id=s.leader_character_id,
            status=s.status,
            current_room_id=s.current_room_id,
            started_at=s.started_at,
            created_at=s.created_at,
            finished_at=s.finished_at,
            finalized_at=s.finalized_at,
            last_activity_at=s.last_activity_at,
            members=[
                {"character_id": m.character_id, "user_id": m.user_id, "status": m.status}
                for m in s.members
            ],
        )
        for s in sessions
    ]


@app.delete("/dungeons/admin/sessions/{session_id}")
async def admin_force_cleanup_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(can_edit),
):
    """Admin force-cleanup: end any session regardless of state. Frees all characters."""
    return await gameplay.admin_force_cleanup_session(db, session_id)


@app.delete("/dungeons/admin/dungeons/{dungeon_id}/cooldown")
async def admin_clear_dungeon_cooldown(
    dungeon_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(can_edit),
):
    """Admin: remove cooldown from a dungeon so it can be entered immediately."""
    await session_state.clear_dungeon_cooldown(dungeon_id)
    result = await db.execute(select(DungeonSession).where(
        DungeonSession.dungeon_id == dungeon_id,
        DungeonSession.cooldown_until != None,  # noqa: E711
    ))
    for s in result.scalars().all():
        s.cooldown_until = None
    await db.commit()
    return {"message": f"Кулдаун подземелья #{dungeon_id} снят"}


# ===========================
#  Player: Dungeons at Location
# ===========================

@app.get("/dungeons/at-location/{location_id}", response_model=List[DungeonAtLocationResponse])
async def get_dungeons_at_location(
    location_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Active dungeons at a location with cooldown / occupancy info."""
    dungeons = (await db.execute(
        select(Dungeon)
        .where(Dungeon.location_id == location_id, Dungeon.is_active == True)  # noqa: E712
        .order_by(Dungeon.recommended_level.asc(), Dungeon.id.asc())
    )).scalars().all()
    response = []
    for d in dungeons:
        is_on_cooldown, remaining = await gameplay.check_cooldown(db, d.id)
        occupied = await gameplay.get_occupying_session(db, d.id) is not None
        response.append(DungeonAtLocationResponse(
            id=d.id, name=d.name, description=d.description, lore_text=d.lore_text,
            stability_type=d.stability_type, danger_level=d.danger_level,
            recommended_level=d.recommended_level, recommended_party_size=d.recommended_party_size,
            is_on_cooldown=is_on_cooldown, cooldown_remaining_seconds=remaining,
            is_occupied=occupied, image_url=d.image_url,
        ))
    return response


# ===========================
#  Player: Entry
# ===========================

@app.post("/dungeons/{dungeon_id}/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    dungeon_id: int,
    data: SessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Solo entry. The run is created already ACTIVE (no `forming` stage);
    the follow-up `/enter` call of the old flow is an idempotent no-op."""
    return await gameplay.create_session(db=db, character_id=data.character_id,
                                         dungeon_id=dungeon_id, user_id=user.id)


@app.post("/dungeons/{dungeon_id}/party-run", response_model=SessionStateResponse, status_code=201)
async def party_run(
    dungeon_id: int,
    data: SessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Squad leader enters with every free squadmate on the dungeon location."""
    return await gameplay.create_party_run(db=db, character_id=data.character_id,
                                           dungeon_id=dungeon_id, user_id=user.id)


@app.post("/dungeons/sessions/{session_id}/enter", response_model=SessionStateResponse)
async def enter_dungeon(
    session_id: int,
    data: SessionEnterRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Legacy: returns the state of an already active run."""
    await _require_own_character(data.character_id, user)
    return await gameplay.enter_dungeon(db=db, session_id=session_id, character_id=data.character_id)


@app.get("/dungeons/sessions/{session_id}/state", response_model=SessionStateResponse)
async def get_session_state_endpoint(
    session_id: int,
    character_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    await _require_own_character(character_id, user)
    return await gameplay.get_session_state(db=db, session_id=session_id, character_id=character_id)


# ===========================
#  Player: Actions
# ===========================

@app.post("/dungeons/sessions/{session_id}/move", response_model=MoveResponse)
async def move_to_room(
    session_id: int,
    data: MoveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Move the party through a corridor (leader)."""
    await _require_own_character(data.character_id, user)
    return await gameplay.move_to_room(db=db, session_id=session_id, character_id=data.character_id,
                                       corridor_id=data.corridor_id, auth_token=_bearer(request))


@app.post("/dungeons/sessions/{session_id}/vote", response_model=PartyVotesResponse)
async def vote_route_endpoint(
    session_id: int,
    data: VoteRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """A member's say on where the party goes next (any living member)."""
    await _require_own_character(data.character_id, user)
    return await gameplay.vote_route(db=db, session_id=session_id, character_id=data.character_id,
                                     corridor_id=data.corridor_id, portal=data.portal)


@app.post("/dungeons/sessions/{session_id}/chat", response_model=ChatEntry)
async def chat_say_endpoint(
    session_id: int,
    data: ChatSayRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """A line in the run's chat (any member, once a second at most)."""
    await _require_own_character(data.character_id, user)
    return await gameplay.chat_say(db=db, session_id=session_id, character_id=data.character_id, text=data.text)


@app.get("/dungeons/sessions/{session_id}/chat", response_model=List[ChatEntry])
async def chat_history_endpoint(
    session_id: int,
    character_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """The run's chat and log, oldest first (the run's last 200 lines)."""
    await _require_own_character(character_id, user)
    return await gameplay.chat_history(db=db, session_id=session_id, character_id=character_id)


@app.post("/dungeons/sessions/{session_id}/ping")
async def ping_board_endpoint(
    session_id: int,
    data: PingRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Mark a room or a door on the table for the party (any member)."""
    await _require_own_character(data.character_id, user)
    return await gameplay.ping_board(db=db, session_id=session_id, character_id=data.character_id,
                                     kind=data.kind, room_id=data.room_id, corridor_id=data.corridor_id)


@app.post("/dungeons/sessions/{session_id}/light", response_model=LightResponse)
async def light_room_endpoint(
    session_id: int,
    data: LightRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Light a dark room (any living member): a mage's spell lasts the run, a torch until the party leaves."""
    await _require_own_character(data.character_id, user)
    return await gameplay.light_room(db=db, session_id=session_id, character_id=data.character_id)


@app.post("/dungeons/sessions/{session_id}/challenges", response_model=ChallengeStartResponse)
async def start_challenge_endpoint(
    session_id: int,
    data: ChallengeStartRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """A member takes on a class challenge (any living member): a minigame, or a plain roll."""
    await _require_own_character(data.character_id, user)
    return await gameplay.start_challenge(db=db, session_id=session_id, character_id=data.character_id,
                                          kind=data.kind, corridor_id=data.corridor_id, mode=data.mode)


@app.post("/dungeons/sessions/{session_id}/challenges/finish", response_model=ChallengeResult)
async def finish_challenge_endpoint(
    session_id: int,
    data: ChallengeFinishRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """The member's minigame is over: the server replays it and settles the outcome."""
    await _require_own_character(data.character_id, user)
    return await gameplay.finish_challenge(db=db, session_id=session_id, character_id=data.character_id,
                                           challenge_id=data.challenge_id, presses=data.presses)


@app.post("/dungeons/sessions/{session_id}/challenges/step", response_model=ChallengeStepResponse)
async def step_challenge_endpoint(
    session_id: int,
    data: ChallengeStepRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """One move of a challenge whose secret the server keeps (the mechanism's lever, the cave-in's stones)."""
    await _require_own_character(data.character_id, user)
    return await gameplay.step_challenge(db=db, session_id=session_id, character_id=data.character_id,
                                         challenge_id=data.challenge_id, x=data.x, y=data.y, index=data.index)


@app.post("/dungeons/sessions/{session_id}/pick-lock", response_model=PickLockResponse)
async def pick_lock_endpoint(
    session_id: int,
    data: PickLockRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Try to pick a locked door out of the current room (leader)."""
    await _require_own_character(data.character_id, user)
    return await gameplay.pick_lock(db=db, session_id=session_id, character_id=data.character_id,
                                    corridor_id=data.corridor_id)


@app.post("/dungeons/sessions/{session_id}/interact", response_model=InteractResponse)
async def interact_with_room_endpoint(
    session_id: int,
    data: InteractRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Room actions: open_chest, event_choice, start_rest, complete_rest,
    revive_member, merchant_buy, start_battle, enter_mana_core, search_mana_core."""
    await _require_own_character(data.character_id, user)
    return await gameplay.interact_with_room(
        db=db, session_id=session_id, character_id=data.character_id, action=data.action,
        choice_index=data.choice_index, target_character_id=data.target_character_id,
        item_id=data.item_id, quantity=data.quantity, auth_token=_bearer(request),
    )


@app.post("/dungeons/sessions/{session_id}/flee", response_model=FleeResponse)
async def flee_dungeon_endpoint(
    session_id: int,
    data: FleeRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Flee (leader): 50% chance to lose each loot stack, run ends, no cooldown."""
    await _require_own_character(data.character_id, user)
    return await gameplay.flee_dungeon(db=db, session_id=session_id, character_id=data.character_id)


@app.post("/dungeons/sessions/{session_id}/distribute-loot", response_model=DistributeLootResponse)
async def distribute_loot_endpoint(
    session_id: int,
    data: DistributeLootRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    await _require_own_character(data.character_id, user)
    distributions = [
        {"item_id": d.item_id, "quantity": d.quantity, "to_character_id": d.to_character_id}
        for d in data.distributions
    ]
    return await gameplay.distribute_loot(db=db, session_id=session_id,
                                          character_id=data.character_id, distributions=distributions)


@app.post("/dungeons/sessions/{session_id}/finalize", response_model=FinalizeResponse)
async def finalize_session_endpoint(
    session_id: int,
    data: FinalizeRequest,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """Close a completed/escaped run; leftovers need force=true (they are lost)."""
    await _require_own_character(data.character_id, user)
    return await gameplay.finalize_session(db=db, session_id=session_id,
                                           character_id=data.character_id, force=data.force)


# ===========================
#  Player: own character's session
# ===========================

@app.get("/dungeons/my-session/{character_id}")
async def get_my_active_session(
    character_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserRead = Depends(get_current_user_via_http),
):
    """The caller's own character only (or an admin/moderator).
    `session_id` — run in progress;
    `pending_loot_session_id` — completed or escaped run whose loot is still undivided."""
    if user.role not in ("admin", "moderator"):
        await _require_own_character(character_id, user)
    active, pending = await gameplay.find_character_session(db, character_id)
    return {"in_dungeon": active is not None, "session_id": active, "pending_loot_session_id": pending}


# ===========================
#  Internal
# ===========================

@app.get("/dungeons/internal/character-session/{character_id}", dependencies=[Depends(verify_internal_token)])
async def check_character_session(character_id: int, db: AsyncSession = Depends(get_db)):
    """Internal: is the character in a dungeon run (DB-based)."""
    active, _pending = await gameplay.find_character_session(db, character_id)
    return {"in_dungeon": active is not None, "session_id": active}


@app.post("/dungeons/internal/battle-callback", dependencies=[Depends(verify_internal_token)])
async def battle_callback(data: BattleCallbackRequest, db: AsyncSession = Depends(get_db)):
    """battle-service reports the end of a dungeon battle (FEAT-175). Exactly
    once: a duplicate / late delivery (or the polling fallback winning the
    race) answers {"status": "ignored"}."""
    try:
        return await gameplay.process_battle_callback(
            db, data.session_id, data.battle_id, data.winner_team,
            data.defeated_characters, data.aborted,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Ошибка при обработке battle callback (battle=%d, session=%d)",
                         data.battle_id, data.session_id)
        raise HTTPException(status_code=500, detail="Ошибка при обработке результатов боя")


# ===========================
#  WebSocket: Dungeon Session
# ===========================

@app.websocket("/dungeons/ws/{session_id}")
async def dungeon_websocket(websocket: WebSocket, session_id: int, token: str = Query(...)):
    """Real-time dungeon session updates. Auth via ?token=; members only.
    Server pushes events; the client may only send heartbeat."""
    # Accepted first, then closed with a reason: a close before accept() reaches the
    # browser as 1006, and the client could not tell a stale token from a dropped line.
    user = await authenticate_websocket(token)
    if not user:
        await websocket.accept()
        await websocket.close(code=4001, reason="Unauthorized")
        return
    user_id = user["id"]

    async with async_session() as db:
        member = (await db.execute(select(DungeonSessionMember).where(
            DungeonSessionMember.session_id == session_id,
            DungeonSessionMember.user_id == user_id,
        ))).scalars().first()
        if not member:
            await websocket.accept()
            await websocket.close(code=4003, reason="Forbidden")
            return

    await websocket.accept()
    await ws_manager.connect(session_id, user_id, websocket)
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                if isinstance(data, dict) and data.get("type") == "heartbeat":
                    await websocket.send_json({"type": "heartbeat_ack", "data": {}})
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping", "data": {}})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # Only this socket: a reconnect may already have replaced it.
        await ws_manager.disconnect(session_id, user_id, websocket)
