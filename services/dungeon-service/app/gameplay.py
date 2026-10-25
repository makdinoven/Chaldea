"""
Dungeon run logic for dungeon-service (FEAT-175 «Данжи 2.0», stage 1).

Session lifecycle
-----------------
    (entry: solo / party)  ->  active  --boss chest-->  completed --finalize--> closed
                                  |  \\--flee / 24h idle-->  escaped  --finalize--> closed
                                  \\--all dead-->  wiped (closed at once, knock-out 1 h)

* One group per dungeon: a dungeon with an `active` session cannot be entered.
* The dungeon cooldown is global and starts ONLY when the boss chest is opened.
* Members are activity-locked in character-service for the whole run
  (`characters.dungeon_session_id`); escape releases the lock at once, a wipe
  turns it into a 1 h knock-out, completion releases it at finalize.
* `finalized_at` marks a fully closed session (loot handed out, Redis/WS gone).

All functions use async SQLAlchemy (the service pattern). Mutating actions take
a row lock on the session (`SELECT ... FOR UPDATE`) so double clicks and the
battle callback/polling race serialize per session.
"""

import asyncio
import json
import logging
import math
import random
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import event, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Session as OrmSession, selectinload

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
    DistributeLootResponse,
    GiveItemResponse,
    ExploredCorridorInfo,
    SeenDoorInfo,
    ExploredRoomInfo,
    FinalizeResponse,
    FleeItemInfo,
    FleeResponse,
    InteractResponse,
    ManaCoreInfo,
    MoveResponse,
    PartyVote,
    PartyVotesResponse,
    PickLockResponse,
    ChallengeResult,
    ChallengeStartResponse,
    ChallengeStepResponse,
    SecretInfo,
    ShieldInfo,
    ScoutInfo,
    FloorExtent,
    ChatEntry,
    AmbushInfo,
    LightResponse,
    WatchInfo,
    SessionMemberResponse,
    SessionResponse,
    SkippedMemberInfo,
    RoomExitResponse,
    RoomViewResponse,
    GroupInventoryItemResponse,
    SessionStateResponse,
    _parse_outcome_data,
    DUNGEON_KEYS,
)
import session_state
import ws_manager
import http_clients
import challenges
import chat

logger = logging.getLogger("dungeon-service.gameplay")


# =====================================================================
# Rules (FEAT-175, agreed with the user)
# =====================================================================

WIPE_KNOCKOUT_SECONDS = 3600            # a wiped party is unconscious for 1 h
ABANDON_AFTER_SECONDS = 24 * 3600       # 24 h without any action = escape
LEADER_AFK_SECONDS = 600                # leadership passes after 10 min idle + offline
SWEEP_INTERVAL_SECONDS = 300            # background sweeper period
ESCAPE_LOSS_CHANCE = 0.5                # each loot stack is lost with this chance
REVIVE_HP_FRACTION = 0.25
DEFAULT_REVIVE_COST = 500
MAX_TELEPORT_CHAIN = 3                  # teleport -> teleport -> ... guard
# Portals: a blue one is a door the party may step through when it likes; a red
# one is a trap — on entry the party rolls, and a failure throws it into one of
# the portal's configured rooms at random. A spotted red portal is harmless after.
PORTAL_BLUE = "blue"
PORTAL_RED = "red"
RED_PORTAL_DEFAULT_STAT = "intelligence"
RED_PORTAL_DEFAULT_DIFFICULTY = 10
# Locked doors: a key of the door's kind opens it (and every door of that kind)
# for the rest of the run; without one the lock may be picked — a stat check
# that costs every living member stamina, win or lose.
LOCK_DEFAULT_STAT = "agility"
LOCK_DEFAULT_DIFFICULTY = 12
LOCK_DEFAULT_PICK_COST = 2
# Floors: passages between neighbouring floors. A drop is one way down and may
# be hidden — walking into its room the party rolls: spotted, it is a way down
# to take at will; missed, the party falls through and takes damage.
DROP_DEFAULT_STAT = "intelligence"
DROP_DEFAULT_DIFFICULTY = 12
DROP_DEFAULT_DAMAGE = 15
ESCAPE_LOSS_CHANCE_MAX = 0.95

STATUS_ACTIVE = "active"
ENDED_STATUSES = ("completed", "escaped", "wiped")
OCCUPYING_STATUSES = ("forming", "active")

PHASE_EXPLORING = "exploring"
PHASE_RESTING = "resting"
PHASE_IN_BATTLE = "in_battle"
PHASE_BATTLE_PENDING = "battle_pending"   # battle room entered, battle not started (retry)
PHASE_DISTRIBUTING = "distributing_loot"
PHASE_WIPED = "wiped"
PHASE_FINISHED = "finished"               # finalized; read-only history

OCCUPIED_DETAIL = "В подземелье уже находится другая группа"


def _utcnow() -> datetime:
    return datetime.utcnow()


# =====================================================================
# Helpers
# =====================================================================

def _mob_count(room: DungeonRoom) -> Optional[int]:
    """Enemies waiting in a battle or boss room; None for other rooms."""
    if room.room_type not in ("battle", "boss"):
        return None
    cfg = room.room_config if isinstance(room.room_config, dict) else {}
    return len(cfg.get("mob_template_ids") or [])


def _room_floor(room: Optional[DungeonRoom]) -> int:
    return int(room.floor or 1) if room is not None and getattr(room, "floor", None) else 1


def _floor_factor(step: Optional[float], floor: int) -> float:
    """How much a value grows on `floor` (1 = the top floor, no growth)."""
    return 1.0 + float(step or 0.0) * max(0, floor - 1)


def _passage(corridor: DungeonCorridor) -> str:
    return corridor.passage_type or "corridor"


def _hidden_drop(corridor: DungeonCorridor) -> Optional[dict]:
    """A drop's hidden trap with defaults, or None for a plain (visible) way down."""
    if _passage(corridor) != "drop":
        return None
    cfg = corridor.passage_config if isinstance(corridor.passage_config, dict) else {}
    if not cfg.get("hidden"):
        return None
    return {
        "stat_check": cfg.get("stat_check") or DROP_DEFAULT_STAT,
        "difficulty": int(cfg["difficulty"]) if cfg.get("difficulty") is not None else DROP_DEFAULT_DIFFICULTY,
        "fail_damage": int(cfg["fail_damage"]) if cfg.get("fail_damage") is not None else DROP_DEFAULT_DAMAGE,
    }


def _corridor_lock(corridor: DungeonCorridor) -> Optional[dict]:
    """The corridor's lock with defaults filled in, or None for an open corridor.
    A lock is opened by its key and/or by a lever somewhere in the dungeon."""
    cfg = corridor.lock_config if isinstance(corridor.lock_config, dict) else None
    if not cfg:
        return None
    key = cfg.get("key") if cfg.get("key") in DUNGEON_KEYS else None
    lever = bool(cfg.get("lever"))
    if key is None and not lever:
        return None
    return {
        "key": key,
        "lever": lever,
        # Only a keyed lock can be picked unless the editor says otherwise.
        "pickable": cfg.get("pickable", key is not None) is not False,
        "stat_check": cfg.get("stat_check") or LOCK_DEFAULT_STAT,
        "difficulty": int(cfg["difficulty"]) if cfg.get("difficulty") is not None else LOCK_DEFAULT_DIFFICULTY,
        "pick_cost": int(cfg["pick_cost"]) if cfg.get("pick_cost") is not None else LOCK_DEFAULT_PICK_COST,
    }


def _lock_need(lock: dict) -> str:
    """What opens a shut door: its key, a lever, or either."""
    if lock["key"] and lock["lever"]:
        return f"нужен {DUNGEON_KEYS[lock['key']]} или рычаг"
    if lock["key"]:
        return f"нужен {DUNGEON_KEYS[lock['key']]}"
    return "её открывает рычаг где-то в подземелье"


def _door_refusal(lock: dict) -> str:
    hint = " Можно попробовать взломать замок." if lock["pickable"] else ""
    return f"Дверь заперта — {_lock_need(lock)}.{hint}"


def _session_keys(session_obj: DungeonSession) -> List[str]:
    keys = session_obj.keys_found if isinstance(session_obj.keys_found, list) else []
    return [k for k in keys if k in DUNGEON_KEYS]


def _is_shut(session_obj: Optional[DungeonSession], corridor: DungeonCorridor) -> bool:
    """A locked corridor not yet opened in this run."""
    if _corridor_lock(corridor) is None:
        return False
    opened = session_obj.unlocked_corridor_ids if session_obj is not None else None
    return not (isinstance(opened, list) and corridor.id in opened)


def _bolt_side(corridor: DungeonCorridor, here_id: Optional[int]) -> bool:
    """The party stands behind the lock: a door is locked against those coming
    from its `from` room and is unbolted from the other side without a key.
    A lift is a machine, not a door: it wants its key or lever from both ends."""
    return (
        here_id is not None
        and here_id == corridor.to_room_id
        and corridor.from_room_id != corridor.to_room_id
        and _passage(corridor) != "lift"
    )


def _is_shut_passage(session_obj: Optional[DungeonSession], corridor: DungeonCorridor) -> bool:
    """A hidden drop not yet found (spotted or fallen through) in this run."""
    opened = session_obj.unlocked_corridor_ids if session_obj is not None else None
    return not (isinstance(opened, list) and corridor.id in opened)


SECRET_DEFAULT_DIFFICULTY = 12
SECRET_DEFAULT_COST = 2
SECRET_DEFAULT_DAMAGE = 10
SECRET_HINTS = {
    "mechanism": "Плиты пола у одной из стен стёрты сильнее, чем везде, — будто там часто кто-то стоял.",
    "illusion": "Одна из стен будто чуть дрожит, если смотреть на неё краем глаза.",
    "rubble": "У стены громоздится завал, а из-за камней тянет сквозняком.",
}


def _secret(corridor: DungeonCorridor) -> Optional[dict]:
    """A secret way out (FEAT-176) with defaults, or None."""
    cfg = corridor.passage_config if isinstance(corridor.passage_config, dict) else {}
    s = cfg.get("secret")
    if not isinstance(s, dict) or s.get("kind") not in challenges.SECRET_KINDS:
        return None
    return {
        "kind": s["kind"],
        "difficulty": int(s["difficulty"]) if s.get("difficulty") is not None else SECRET_DEFAULT_DIFFICULTY,
        "cost": int(s["cost"]) if s.get("cost") is not None else SECRET_DEFAULT_COST,
        "fail_damage": int(s["fail_damage"]) if s.get("fail_damage") is not None else SECRET_DEFAULT_DAMAGE,
        "hint": s.get("hint") or SECRET_HINTS[s["kind"]],
    }


def _hidden_way(session_obj: Optional[DungeonSession], corridor: DungeonCorridor) -> bool:
    """A way the party has not found yet: a hidden drop, or a secret passage."""
    if _hidden_drop(corridor) is None and _secret(corridor) is None:
        return False
    return _is_shut_passage(session_obj, corridor)


GATE_DEFAULT_DIFFICULTY = 12
GATE_DEFAULT_COST = 2
GATE_DEFAULT_DAMAGE = 10
# What the gate is, as the messages name it: (nominative, accusative).
GATE_NOUNS = {"grate": ("решётка", "решётку"), "slab": ("плита", "плиту")}


def _gate(corridor: DungeonCorridor) -> Optional[dict]:
    """A gate down across the corridor (FEAT-176) with defaults, or None.
    Someone holds it up until it is propped; then it stays open for the run."""
    cfg = corridor.passage_config if isinstance(corridor.passage_config, dict) else {}
    g = cfg.get("gate")
    if not isinstance(g, dict) or g.get("look") not in GATE_NOUNS:
        return None
    return {
        "look": g["look"],
        "difficulty": int(g["difficulty"]) if g.get("difficulty") is not None else GATE_DEFAULT_DIFFICULTY,
        "cost": int(g["cost"]) if g.get("cost") is not None else GATE_DEFAULT_COST,
        "fail_damage": int(g["fail_damage"]) if g.get("fail_damage") is not None else GATE_DEFAULT_DAMAGE,
    }


def _gate_down(session_obj: Optional[DungeonSession], corridor: DungeonCorridor) -> Optional[dict]:
    """The corridor's gate while it is still down in this run."""
    gate = _gate(corridor)
    return gate if gate and _is_shut_passage(session_obj, corridor) else None


SEAL_DEFAULT_DIFFICULTY = 12
SEAL_DEFAULT_COST = 2
SEAL_DEFAULT_DAMAGE = 12


def _seal(corridor: DungeonCorridor) -> Optional[dict]:
    """A magic seal on the corridor (FEAT-176) with defaults, or None. A mage's
    craft to break; once broken it stays open for the run."""
    cfg = corridor.passage_config if isinstance(corridor.passage_config, dict) else {}
    seal = cfg.get("seal")
    if not isinstance(seal, dict):
        return None
    return {
        "difficulty": int(seal["difficulty"]) if seal.get("difficulty") is not None else SEAL_DEFAULT_DIFFICULTY,
        "cost": int(seal["cost"]) if seal.get("cost") is not None else SEAL_DEFAULT_COST,
        "fail_damage": int(seal["fail_damage"]) if seal.get("fail_damage") is not None else SEAL_DEFAULT_DAMAGE,
    }


def _seal_on(session_obj: Optional[DungeonSession], corridor: DungeonCorridor) -> Optional[dict]:
    """The corridor's seal while it is still unbroken in this run."""
    seal = _seal(corridor)
    return seal if seal and _is_shut_passage(session_obj, corridor) else None


# Dark rooms (FEAT-176): until a light burns, the ways out are unknown and traps
# strike harder. A mage's light lasts the run; a torch, until the party leaves.
DARK_TRAP_FACTOR = 1.5
LIGHT_SPELL_COST = 1
TORCH_COST = 3
LIGHT_SPELL = "spell"
LIGHT_TORCH = "torch"


def _dark_room(room: Optional[DungeonRoom]) -> bool:
    cfg = room.room_config if room is not None and isinstance(room.room_config, dict) else {}
    return cfg.get("dark") is True


def _spell_lit(room_state: Optional[DungeonRoomState]) -> bool:
    extra = room_state.extra_data if room_state is not None and isinstance(room_state.extra_data, dict) else {}
    return extra.get("lit") == LIGHT_SPELL


async def _in_darkness(session_obj: DungeonSession, room: Optional[DungeonRoom],
                       room_state: Optional[DungeonRoomState]) -> bool:
    """A dark room with no light burning in it now."""
    if not _dark_room(room) or _spell_lit(room_state):
        return False
    return await session_state.get_torch(session_obj.id) != room.id


def _open_corridor(session_obj: DungeonSession, corridor: DungeonCorridor) -> None:
    opened = session_obj.unlocked_corridor_ids if isinstance(session_obj.unlocked_corridor_ids, list) else []
    if corridor.id not in opened:
        session_obj.unlocked_corridor_ids = [*opened, corridor.id]


async def _grant_key(session_obj: DungeonSession, key: Optional[str], source: str) -> Optional[str]:
    """Give the party a key (once per kind); returns the kind when it is new."""
    if key not in DUNGEON_KEYS or key in _session_keys(session_obj):
        return None
    session_obj.keys_found = [*_session_keys(session_obj), key]
    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "key_found",
        "data": {"key": key, "source": source, "message": f"Найден {DUNGEON_KEYS[key]}! ({source})"},
    })
    return key


def _portal_kind(room_type: str, cfg) -> Optional[str]:
    """Blue or red for a teleport room (blue unless set otherwise); None for other rooms."""
    if room_type != "teleport":
        return None
    return PORTAL_RED if isinstance(cfg, dict) and cfg.get("portal") == PORTAL_RED else PORTAL_BLUE


# What the mage reads in an event's choices (FEAT-176), by outcome type.
OUTCOME_HINTS = {
    "reward": "награда",
    "damage": "опасно",
    "heal": "исцеление",
    "battle": "бой",
    "teleport": "перенесёт",
    "key": "ключ",
    "nothing": "ничего",
}


def _read(room_state: Optional[DungeonRoomState]) -> bool:
    """The mage has read this room (its event, its portal)."""
    extra = room_state.extra_data if room_state is not None and isinstance(room_state.extra_data, dict) else {}
    return bool(extra.get("insight"))


def _build_room_config_visible(
    room: DungeonRoom,
    room_state: Optional[DungeonRoomState] = None,
) -> dict:
    """Build a safe subset of room_config visible to players."""
    cfg = room.room_config if isinstance(room.room_config, dict) else {}
    visible: dict = {}

    if room.room_type == "event":
        if cfg.get("text"):
            visible["text"] = cfg["text"]
        choices = cfg.get("choices", []) or []
        # Only show choice text, not outcome data
        visible["choices"] = [
            c.get("text", "") if isinstance(c, dict) else str(c)
            for c in choices
        ]
        if room_state and room_state.event_choice_index is not None:
            visible["choice_made"] = room_state.event_choice_index
        if _read(room_state):
            # The mage has read the event: what each choice leads to, roughly.
            visible["choice_hints"] = [
                OUTCOME_HINTS.get((c.get("outcome_type") if isinstance(c, dict) else None) or "nothing", "неясно")
                for c in choices
            ]

    elif room.room_type in ("treasure", "boss"):
        if room_state:
            visible["loot_collected"] = bool(room_state.loot_collected)

    if cfg.get("lever_corridor_id"):
        extra = room_state.extra_data if room_state and isinstance(room_state.extra_data, dict) else {}
        visible["lever"] = {"pulled": bool(extra.get("lever_pulled"))}

    if room.room_type in ("battle", "boss"):
        # Only how many stand there (figurines on the table), never who.
        visible["mob_count"] = _mob_count(room)

    elif room.room_type == "rest":
        for key in ("heal_percent", "wait_seconds", "gold_cost", "revive_gold_cost"):
            if cfg.get(key) is not None:
                visible[key] = cfg[key]
        extra = room_state.extra_data if room_state and isinstance(room_state.extra_data, dict) else {}
        visible["rest_used"] = bool(extra.get("rest_used"))
        if extra.get("rest_started_at") and not extra.get("rest_used"):
            visible["rest_started_at"] = extra.get("rest_started_at")

    elif room.room_type == "merchant":
        extra = room_state.extra_data if room_state and isinstance(room_state.extra_data, dict) else {}
        stock = extra.get("merchant_stock", {})
        items = []
        for mi in cfg.get("items", []) or []:
            if not isinstance(mi, dict):
                continue
            entry = dict(mi)
            key = str(mi.get("item_id"))
            if key in stock:
                entry["stock"] = stock[key]
            items.append(entry)
        visible["items"] = items

    elif room.room_type == "trap":
        # Don't reveal stat_check or difficulty
        if room_state and isinstance(room_state.extra_data, dict) and "trap" in room_state.extra_data:
            visible["trap_result"] = room_state.extra_data["trap"]

    elif room.room_type == "teleport":
        visible["portal"] = _portal_kind(room.room_type, cfg)
        if visible["portal"] == PORTAL_BLUE:
            visible["target_room_id"] = cfg.get("target_room_id")
        elif room_state and isinstance(room_state.extra_data, dict) and "portal" in room_state.extra_data:
            # Where a red portal may throw the party is never shown — only how the last roll went.
            visible["portal_result"] = room_state.extra_data["portal"]

    return visible


async def _get_session(db: AsyncSession, session_id: int, lock: bool = False) -> DungeonSession:
    """Load a dungeon session with members, raising 404 if not found.

    `lock=True` takes a row lock (SELECT ... FOR UPDATE) and refreshes the
    identity map, so concurrent actions on one session serialize.
    """
    stmt = (
        select(DungeonSession)
        .where(DungeonSession.id == session_id)
        .options(selectinload(DungeonSession.members))
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Сессия подземелья не найдена")
    return session


async def _get_dungeon_for_session(db: AsyncSession, dungeon_id: int) -> Dungeon:
    """Helper to load dungeon, raising 404 if not found."""
    result = await db.execute(select(Dungeon).where(Dungeon.id == dungeon_id))
    dungeon = result.scalar_one_or_none()
    if not dungeon:
        raise HTTPException(status_code=404, detail="Подземелье не найдено")
    return dungeon


async def _get_room(db: AsyncSession, room_id) -> Optional[DungeonRoom]:
    if room_id is None:
        return None
    result = await db.execute(select(DungeonRoom).where(DungeonRoom.id == int(room_id)))
    return result.scalar_one_or_none()


def _profile_name(profile: dict, character_id: int) -> str:
    """character-service /profile exposes the name as `character_name`."""
    return (profile or {}).get("character_name") or f"Персонаж #{character_id}"


async def _character_name(character_id: int) -> str:
    try:
        return _profile_name(await http_clients.get_character_profile(character_id), character_id)
    except Exception:
        return f"Персонаж #{character_id}"


RESOURCE_FIELDS = (
    "current_health", "max_health", "current_mana", "max_mana",
    "current_energy", "max_energy", "current_stamina", "max_stamina",
)


# A game left without a word (the tab closed) stops showing over the figurine
# after its own clock plus this much; games with no clock, after BUSY_UNTIMED_MS.
BUSY_GRACE_MS = 10_000
BUSY_UNTIMED_MS = 180_000


async def _busy_kind(session_id: int, character_id: int) -> Optional[str]:
    """The minigame a member is in the middle of, for the others to see."""
    try:
        challenge = await session_state.get_challenge(session_id, character_id)
    except Exception:
        return None
    if not challenge:
        return None
    span = (challenge.get("params") or {}).get("time_limit_ms") or BUSY_UNTIMED_MS
    if time.time() * 1000 > (challenge.get("issued_at") or 0) + span + BUSY_GRACE_MS:
        return None
    return challenge.get("kind")


async def _member_frame(m: DungeonSessionMember, leader_id: int) -> SessionMemberResponse:
    """A member as the party frames show them: portrait, level and the four
    resource bars. Profile and attributes are read side by side; either may
    fail without hiding the member (the bars are simply left out)."""
    profile, attrs, busy = await asyncio.gather(
        http_clients.get_character_profile(m.character_id),
        http_clients.get_character_attributes(m.character_id),
        _busy_kind(m.session_id, m.character_id),
        return_exceptions=True,
    )
    profile = profile if isinstance(profile, dict) else {}
    attrs = attrs if isinstance(attrs, dict) else {}
    return SessionMemberResponse(
        character_id=m.character_id,
        name=_profile_name(profile, m.character_id),
        status=m.status,
        is_leader=(m.character_id == leader_id),
        user_id=m.user_id,
        avatar=profile.get("character_photo") or None,
        level=profile.get("character_level"),
        class_id=profile.get("character_class_id"),
        busy=busy if isinstance(busy, str) else None,
        **{f: attrs.get(f) for f in RESOURCE_FIELDS},
    )


async def _member_responses(session_obj: DungeonSession, members=None) -> List[SessionMemberResponse]:
    return list(await asyncio.gather(*(
        _member_frame(m, session_obj.leader_character_id)
        for m in (members if members is not None else session_obj.members)
    )))


async def _build_session_response(
    db: AsyncSession, session: DungeonSession, dungeon_id: int
) -> SessionResponse:
    """Build a SessionResponse from a DungeonSession ORM object."""
    members = (await db.execute(
        select(DungeonSessionMember).where(DungeonSessionMember.session_id == session.id)
    )).scalars().all()
    return SessionResponse(
        session_id=session.id,
        dungeon_id=dungeon_id,
        status=session.status,
        leader_character_id=session.leader_character_id,
        members=await _member_responses(session, members),
    )


def _reliability(dungeon: Optional[Dungeon], explored: bool) -> str:
    """Map stability to the values the frontend renders."""
    stability = getattr(dungeon, "stability_type", "static") if dungeon else "static"
    if stability == "unstable":
        return "uncertain"
    if stability == "chaotic":
        return "memory_only" if explored else "uncertain"
    return "reliable"


async def _visited_room_ids(db: AsyncSession, dungeon_id: int, character_id: int) -> set:
    rows = await db.execute(
        select(DungeonRoomVisit.room_id).where(
            DungeonRoomVisit.dungeon_id == dungeon_id,
            DungeonRoomVisit.character_id == character_id,
        )
    )
    return set(rows.scalars().all())


async def _get_room_exits(
    db: AsyncSession,
    room_id: int,
    dungeon_id: int,
    character_id: int,
    dungeon: Optional[Dungeon] = None,
    session_obj: Optional[DungeonSession] = None,
    dark: bool = False,
) -> List[RoomExitResponse]:
    """
    Build exit list for a room.
    Considers bidirectional corridors and fog of war.
    """
    corridors_from = (await db.execute(select(DungeonCorridor).where(
        DungeonCorridor.dungeon_id == dungeon_id,
        DungeonCorridor.from_room_id == room_id,
    ))).scalars().all()
    corridors_to = (await db.execute(select(DungeonCorridor).where(
        DungeonCorridor.dungeon_id == dungeon_id,
        DungeonCorridor.to_room_id == room_id,
        DungeonCorridor.is_bidirectional == True,  # noqa: E712
    ))).scalars().all()
    visited_room_ids = await _visited_room_ids(db, dungeon_id, character_id)

    exits: List[RoomExitResponse] = []
    charted = (dungeon.stability_type if dungeon else None) == "static"
    intel = await session_state.get_intel(session_obj.id) if session_obj is not None else {"scouted": {}, "disarmed": []}
    # A hidden drop or a secret passage is no way out until the party has found it
    # (from inside a secret room the way back is plain to see).
    corridors_from = [c for c in corridors_from if not _hidden_way(session_obj, c)]
    pairs = [(c, c.to_room_id, c.source_handle, c.target_handle) for c in corridors_from]
    # Reverse corridors (bidirectional) — swap source_handle/target_handle
    pairs += [(c, c.from_room_id, c.target_handle, c.source_handle) for c in corridors_to]
    for c, target_room_id, src_handle, dst_handle in pairs:
        # In the dark nobody can tell where a way leads, even a known one.
        explored = target_room_id in visited_room_ids and not dark
        target = await _get_room(db, target_room_id)
        lock = _corridor_lock(c)
        gate = _gate_down(session_obj, c)
        exits.append(
            RoomExitResponse(
                corridor_id=c.id,
                to_room_id=target_room_id,
                to_room_name=(target.name if (target and explored) else "???"),
                stamina_cost=c.stamina_cost,
                explored=explored,
                reliability=_reliability(dungeon, explored),
                position_x=target.position_x if target else None,
                position_y=target.position_y if target else None,
                # Its size gives the room away (a big hall): known once seen, or in a charted dungeon.
                grid_w=target.grid_w if target and (explored or charted) else None,
                grid_d=target.grid_d if target and (explored or charted) else None,
                source_handle=src_handle,
                target_handle=dst_handle,
                lock_key=lock["key"] if lock else None,
                locked=_is_shut(session_obj, c) and not _bolt_side(c, room_id),
                lock_pickable=bool(lock and lock["pickable"]),
                lock_lever=bool(lock and lock["lever"]),
                passage=_passage(c),
                to_floor=_room_floor(target),
                gate=gate["look"] if gate else None,
                sealed=bool(_seal_on(session_obj, c)),
                scout=_scout_info(intel, c.id, target_room_id),
            )
        )
    return exits


def _room_used(room_type: str, loot_collected: Optional[bool], extra_data) -> bool:
    """A treasure room's chest emptied, or a rest room's rest taken."""
    if room_type == "treasure":
        return bool(loot_collected)
    if room_type == "rest":
        return bool(isinstance(extra_data, dict) and extra_data.get("rest_used"))
    return False


async def _room_view(
    db: AsyncSession, room: DungeonRoom, room_state: Optional[DungeonRoomState],
    session_obj: DungeonSession, character_id: int, dungeon: Optional[Dungeon],
) -> RoomViewResponse:
    dark = await _in_darkness(session_obj, room, room_state)
    visible = _build_room_config_visible(room, room_state)
    cfg = room.room_config if isinstance(room.room_config, dict) else {}
    if _read(room_state) and _portal_kind(room.room_type, cfg) == PORTAL_BLUE and cfg.get("target_room_id"):
        target = await _get_room(db, cfg["target_room_id"])
        if target:
            visible["portal_to"] = {"name": target.name, "room_type": target.room_type}
    extra = room_state.extra_data if room_state is not None and isinstance(room_state.extra_data, dict) else {}
    watch = extra.get("watch") if extra.get("rest_started_at") and not extra.get("rest_used") else None
    return RoomViewResponse(
        id=room.id,
        room_type=room.room_type,
        name=room.name,
        description=room.description,
        image_url=room.image_url,
        is_entrance=room.is_entrance,
        is_boss_room=room.is_boss_room,
        is_mana_core_room=bool(room.is_mana_core_room),
        is_cleared=bool(room_state.is_cleared) if room_state else False,
        room_config_visible=visible,
        exits=await _get_room_exits(db, room.id, session_obj.dungeon_id, character_id, dungeon, session_obj, dark),
        floor=_room_floor(room),
        position_x=room.position_x,
        position_y=room.position_y,
        grid_w=room.grid_w,
        grid_d=room.grid_d,
        secrets=await _room_secrets(db, room, session_obj),
        dark_room=_dark_room(room),
        dark=dark,
        searched=bool(extra.get("searched")),
        watch=WatchInfo(**watch) if isinstance(watch, dict) else None,
    )


async def _room_secrets(db: AsyncSession, room: DungeonRoom, session_obj: DungeonSession) -> List[SecretInfo]:
    """Secret ways out of the room not found yet: their hints."""
    out = []
    for c in (await db.execute(select(DungeonCorridor).where(
        DungeonCorridor.dungeon_id == room.dungeon_id, DungeonCorridor.from_room_id == room.id,
    ))).scalars().all():
        secret = _secret(c)
        if secret and _is_shut_passage(session_obj, c):
            out.append(SecretInfo(corridor_id=c.id, kind=secret["kind"], hint=secret["hint"]))
    return out


async def _get_room_state(
    db: AsyncSession, session_id: int, room_id: int, lock: bool = False,
) -> DungeonRoomState:
    """Load or create DungeonRoomState for a room in this session."""
    stmt = select(DungeonRoomState).where(
        DungeonRoomState.session_id == session_id,
        DungeonRoomState.room_id == room_id,
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    room_state_obj = (await db.execute(stmt)).scalar_one_or_none()
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


async def _record_visit(db: AsyncSession, dungeon_id: int, member_ids: List[int], room_id: int) -> None:
    for mid in member_ids:
        visit = (await db.execute(select(DungeonRoomVisit).where(
            DungeonRoomVisit.dungeon_id == dungeon_id,
            DungeonRoomVisit.character_id == mid,
            DungeonRoomVisit.room_id == room_id,
        ))).scalar_one_or_none()
        if visit:
            visit.visit_count = (visit.visit_count or 0) + 1
            visit.last_visited_at = _utcnow()
        else:
            db.add(DungeonRoomVisit(dungeon_id=dungeon_id, character_id=mid, room_id=room_id))


def _touch(session_obj: DungeonSession) -> None:
    """Record activity for the 24 h abandonment rule."""
    session_obj.last_activity_at = _utcnow()


def _member_ids(session_obj: DungeonSession) -> List[int]:
    return [m.character_id for m in session_obj.members]


def _alive_ids(session_obj: DungeonSession) -> List[int]:
    return [m.character_id for m in session_obj.members if m.status == "alive"]


def _require_member(session_obj: DungeonSession, character_id: int) -> DungeonSessionMember:
    for m in session_obj.members:
        if m.character_id == character_id:
            return m
    raise HTTPException(status_code=403, detail="Персонаж не является участником этой сессии")


# Work that must follow a commit and never a rolled-back action (Redis, broadcasts).
AFTER_COMMIT_KEY = "dungeon_after_commit"
_after_commit_tasks: set = set()


def after_commit(db: AsyncSession, job) -> None:
    """Run `job()` (a coroutine function) once this transaction commits; dropped if it rolls back."""
    db.sync_session.info.setdefault(AFTER_COMMIT_KEY, []).append(job)


@event.listens_for(OrmSession, "after_commit")
def _run_after_commit(session) -> None:
    for job in session.info.pop(AFTER_COMMIT_KEY, []):
        task = asyncio.get_running_loop().create_task(job())
        _after_commit_tasks.add(task)
        task.add_done_callback(_after_commit_tasks.discard)


@event.listens_for(OrmSession, "after_transaction_end")
def _drop_after_commit(session, transaction) -> None:
    # The outer transaction is over without a commit (rolled back, or the session closed): drop the work.
    if transaction.parent is None:
        session.info.pop(AFTER_COMMIT_KEY, None)


async def _require_leader(
    db: AsyncSession, session_obj: DungeonSession, character_id: int, action_text: str,
) -> None:
    """Leader-only actions. If the leader has been idle for LEADER_AFK_SECONDS
    and is not connected to the session WebSocket, leadership passes to the
    member who acts (FEAT-175: "the leader closed the tab mid-run")."""
    _require_member(session_obj, character_id)
    if session_obj.leader_character_id == character_id:
        return
    leader = next(
        (m for m in session_obj.members if m.character_id == session_obj.leader_character_id), None,
    )
    last = session_obj.last_activity_at or session_obj.started_at or session_obj.created_at
    leader_online = leader is not None and leader.user_id in ws_manager.get_connected_users(session_obj.id)
    idle = last is None or (_utcnow() - last).total_seconds() >= LEADER_AFK_SECONDS
    if leader is None or (idle and not leader_online):
        # Part of the action's transaction: Redis and the party hear of it once that commits.
        session_obj.leader_character_id = character_id
        session_id = session_obj.id

        async def announce() -> None:
            await session_state.set_leader(session_id, character_id)
            await ws_manager.broadcast_to_session(session_id, {
                "type": "leader_changed",
                "data": {
                    "new_leader_character_id": character_id,
                    "message": "Лидер долго бездействовал — лидерство передано.",
                },
            })
            logger.info("Сессия %d: лидерство передано персонажу %d", session_id, character_id)

        after_commit(db, announce)
        return
    raise HTTPException(status_code=403, detail=f"Только лидер может {action_text}")


async def _item_name(item_id: int, cache: Optional[Dict[int, Optional[str]]] = None) -> Optional[str]:
    if cache is not None and item_id in cache:
        return cache[item_id]
    try:
        info = await http_clients.get_item_info(item_id)
        name = info.get("name") or info.get("item_name")
    except Exception:
        name = None
    if cache is not None:
        cache[item_id] = name
    return name


async def _add_to_group_inventory(
    db: AsyncSession,
    session_id: int,
    item_id: int,
    quantity: int,
    source_description: str,
) -> None:
    """Add an item to the dungeon group inventory (DB)."""
    db.add(DungeonSessionInventory(
        session_id=session_id,
        item_id=item_id,
        quantity=quantity,
        source_description=source_description,
    ))


async def _inventory_rows(db: AsyncSession, session_id: int, lock: bool = False) -> List[DungeonSessionInventory]:
    stmt = select(DungeonSessionInventory).where(DungeonSessionInventory.session_id == session_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return list((await db.execute(stmt)).scalars().all())


async def _sync_inventory_cache(db: AsyncSession, session_id: int) -> List[DungeonSessionInventory]:
    rows = await _inventory_rows(db, session_id)
    await session_state.set_session_inventory(session_id, [
        {"item_id": i.item_id, "quantity": i.quantity, "source_description": i.source_description}
        for i in rows
    ])
    return rows


# =====================================================================
# Cooldown / occupancy
# =====================================================================

async def check_cooldown(db: AsyncSession, dungeon_id: int) -> Tuple[bool, int]:
    """Global dungeon cooldown: Redis first, then the DB copy (survives a
    Redis flush). Returns (on_cooldown, remaining_seconds)."""
    on_cd, remaining = await session_state.check_dungeon_cooldown(dungeon_id)
    if on_cd:
        return True, remaining
    latest = (await db.execute(
        select(DungeonSession)
        .where(DungeonSession.dungeon_id == dungeon_id, DungeonSession.cooldown_until.isnot(None))
        .order_by(DungeonSession.cooldown_until.desc())
        .limit(1)
    )).scalar_one_or_none()
    now = _utcnow()
    if latest and latest.cooldown_until and latest.cooldown_until > now:
        remaining = int((latest.cooldown_until - now).total_seconds())
        await session_state.set_dungeon_cooldown_seconds(dungeon_id, latest.id, remaining)
        return True, remaining
    return False, 0


def _cooldown_detail(remaining: int) -> str:
    hours, minutes = remaining // 3600, (remaining % 3600) // 60
    return f"Подземелье на откате. Восстановится через {hours}ч {minutes}мин"


async def get_occupying_session(
    db: AsyncSession, dungeon_id: int, expire: bool = True,
) -> Optional[DungeonSession]:
    """The session currently holding the dungeon (one group at a time).
    With `expire=True` the 24 h abandonment rule is applied lazily first (it
    commits), so a dead run never blocks the dungeon."""
    sessions = (await db.execute(
        select(DungeonSession)
        .where(DungeonSession.dungeon_id == dungeon_id, DungeonSession.status.in_(OCCUPYING_STATUSES))
        .options(selectinload(DungeonSession.members))
        .order_by(DungeonSession.id)
    )).scalars().all()
    for sid in [s.id for s in sessions]:
        if expire and await expire_if_abandoned(db, sid):
            continue
        return await _get_session(db, sid)
    return None


# =====================================================================
# Entry (solo / party) — validate EVERYTHING before creating anything
# =====================================================================

async def _surface_busy(db: AsyncSession, character_id: int) -> Optional[str]:
    """A fight or a gathering already under way on the surface (shared DB,
    the same queries locations-service uses for its battle/gathering locks)."""
    in_battle = (await db.execute(text(
        "SELECT 1 FROM battles b JOIN battle_participants bp ON b.id = bp.battle_id "
        "WHERE bp.character_id = :cid AND b.status IN ('pending', 'in_progress') "
        "AND bp.dropped_out_at IS NULL LIMIT 1"
    ), {"cid": character_id})).first()
    if in_battle:
        return "в бою"
    gathering = (await db.execute(text(
        "SELECT 1 FROM gathering_sessions "
        "WHERE character_id = :cid AND status = 'active' AND complete_at > NOW() LIMIT 1"
    ), {"cid": character_id})).first()
    return "занят добычей" if gathering else None


async def _check_entrant(db: AsyncSession, character_id: int, profile: dict, dungeon: Dungeon) -> Optional[str]:
    """Reason why this character cannot enter, or None."""
    if profile.get("current_location_id") != dungeon.location_id:
        return "не на локации подземелья"
    lock = profile.get("activity_lock")
    if lock is None:
        lock = await http_clients.get_activity_lock(character_id)
    if lock and lock.get("locked"):
        if lock.get("reason") == "unconscious":
            return "без сознания"
        return "уже в подземелье"
    return await _surface_busy(db, character_id)


def _lock_refusal(profile: dict, reason: str) -> str:
    lock = profile.get("activity_lock") or {}
    if reason == "без сознания":
        until = lock.get("until")
        if until:
            try:
                t = datetime.fromisoformat(until) + timedelta(hours=3)
                return f"Персонаж без сознания до {t.strftime('%H:%M')} МСК"
            except ValueError:
                pass
        return "Персонаж без сознания"
    if reason == "уже в подземелье":
        return "Персонаж уже находится в подземелье"
    if reason == "в бою":
        return "Персонаж сейчас в бою — сначала завершите бой"
    if reason == "занят добычей":
        return "Персонаж сейчас добывает ресурсы — дождитесь окончания"
    return "Персонаж должен находиться на локации подземелья"


async def start_run(
    db: AsyncSession,
    dungeon_id: int,
    leader_character_id: int,
    user_id: int,
    party: bool,
) -> SessionStateResponse:
    """Create + start a run atomically (solo or party).

    Order: read-only validation (dungeon, owner, location, locks, party,
    entrance, cooldown) -> dungeon row lock -> occupancy + cooldown re-check
    -> insert session/members (flush) -> lock characters in character-service
    (all-or-nothing) -> consume the «Данж» intent post (irreversible, last)
    -> commit -> Redis. Any failure rolls back the DB and releases the
    character locks: no orphan `forming` session, no stray Redis markers.
    """
    dungeon = (await db.execute(select(Dungeon).where(Dungeon.id == dungeon_id))).scalar_one_or_none()
    if not dungeon:
        raise HTTPException(status_code=404, detail="Подземелье не найдено")
    if not dungeon.is_active:
        raise HTTPException(status_code=400, detail="Подземелье неактивно")

    profile = await http_clients.get_character_profile(leader_character_id)
    if profile.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Этот персонаж не принадлежит вам")
    reason = await _check_entrant(db, leader_character_id, profile, dungeon)
    if reason:
        status = 400 if reason == "не на локации подземелья" else 409
        raise HTTPException(status_code=status, detail=_lock_refusal(profile, reason))

    member_ids = [leader_character_id]
    profiles = {leader_character_id: profile}
    skipped: List[SkippedMemberInfo] = []
    if party:
        info = await http_clients.get_party_active_members(leader_character_id, dungeon.location_id)
        if not info.get("party_id") or info.get("leader_character_id") != leader_character_id:
            raise HTTPException(status_code=400, detail="Групповой заход доступен только лидеру отряда")
        for cid in info.get("member_character_ids", []):
            if cid == leader_character_id or cid in profiles:
                continue
            try:
                prof = await http_clients.get_character_profile(cid)
            except HTTPException:
                skipped.append(SkippedMemberInfo(character_id=cid, reason="недоступен"))
                continue
            why = await _check_entrant(db, cid, prof, dungeon)
            if why:
                skipped.append(SkippedMemberInfo(
                    character_id=cid, name=_profile_name(prof, cid), reason=why,
                ))
                continue
            profiles[cid] = prof
            member_ids.append(cid)

    entrance = (await db.execute(select(DungeonRoom).where(
        DungeonRoom.dungeon_id == dungeon_id, DungeonRoom.is_entrance == True,  # noqa: E712
    ).order_by(DungeonRoom.id).limit(1))).scalar_one_or_none()
    if not entrance:
        raise HTTPException(
            status_code=409,
            detail="Подземелье не имеет комнаты-входа. Обратитесь к администратору.",
        )

    on_cd, remaining = await check_cooldown(db, dungeon_id)
    if on_cd:
        raise HTTPException(status_code=403, detail=_cooldown_detail(remaining))

    # Lazy cleanup of an abandoned run first (commits), then serialize
    # concurrent entries on the dungeon row and re-check without side effects.
    if await get_occupying_session(db, dungeon_id) is not None:
        raise HTTPException(status_code=409, detail=OCCUPIED_DETAIL)
    # End the read snapshot before queueing on the row lock: under REPEATABLE
    # READ a plain re-check would still see the world from before the wait and
    # miss a run the previous lock holder has just committed.
    await db.commit()
    await db.execute(select(Dungeon.id).where(Dungeon.id == dungeon_id).with_for_update())
    occupied = (await db.execute(
        select(DungeonSession.id)
        .where(DungeonSession.dungeon_id == dungeon_id, DungeonSession.status.in_(OCCUPYING_STATUSES))
        .limit(1)
        .with_for_update()
    )).scalar_one_or_none()
    if occupied is not None:
        await db.rollback()
        raise HTTPException(status_code=409, detail=OCCUPIED_DETAIL)

    now = _utcnow()
    session_obj = DungeonSession(
        dungeon_id=dungeon_id,
        leader_character_id=leader_character_id,
        status=STATUS_ACTIVE,
        current_room_id=entrance.id,
        started_at=now,
        last_activity_at=now,
    )
    db.add(session_obj)
    await db.flush()
    for cid in member_ids:
        db.add(DungeonSessionMember(
            session_id=session_obj.id, character_id=cid,
            user_id=profiles[cid].get("user_id"), status="alive",
        ))
    db.add(DungeonRoomState(session_id=session_obj.id, room_id=entrance.id,
                            is_cleared=False, loot_collected=False))
    await _record_visit(db, dungeon_id, member_ids, entrance.id)
    await db.flush()

    try:
        await http_clients.set_dungeon_lock(member_ids, session_obj.id)
        if not await http_clients.consume_dungeon_gate(
            leader_character_id, dungeon.location_id, dungeon_id,
        ):
            raise HTTPException(
                status_code=403,
                detail="Нужен пост-намерение «Данж» с этим подземельем, чтобы войти",
            )
        await db.commit()
    except Exception:
        await db.rollback()
        # Always: the lock call may have landed even if it raised (a timeout).
        # Clearing is idempotent and touches only locks pointing at this session.
        await http_clients.clear_dungeon_lock(member_ids, session_obj.id)
        raise

    # --- Redis (rebuildable from the DB, see ensure_redis_state) -----------
    try:
        await session_state.init_session_state(
            session_id=session_obj.id,
            dungeon_id=dungeon_id,
            leader_character_id=leader_character_id,
            members={str(cid): {"user_id": profiles[cid].get("user_id"), "status": "alive"}
                     for cid in member_ids},
        )
        await session_state.update_session_state(
            session_obj.id, current_room_id=entrance.id, phase=PHASE_EXPLORING,
        )
        for cid in member_ids:
            await session_state.set_character_active_session(cid, session_obj.id)
    except Exception:
        logger.exception("Сессия %d: не удалось записать состояние в Redis (будет восстановлено)",
                         session_obj.id)

    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "session_status", "data": {"status": STATUS_ACTIVE, "phase": PHASE_EXPLORING},
    })
    state = await get_session_state(db, session_obj.id, leader_character_id)
    state.skipped_members = skipped
    return state


async def create_session(db: AsyncSession, character_id: int, dungeon_id: int, user_id: int) -> SessionResponse:
    """Solo entry (`POST /dungeons/{id}/sessions`). Kept for the old frontend
    flow (create -> enter): the run is created ALREADY active; `/enter` is now
    an idempotent no-op that returns the state."""
    state = await start_run(db, dungeon_id, character_id, user_id, party=False)
    session_obj = await _get_session(db, state.session_id)
    return await _build_session_response(db, session_obj, dungeon_id)


async def create_party_run(db: AsyncSession, character_id: int, dungeon_id: int, user_id: int) -> SessionStateResponse:
    """Party entry: the squad leader enters with every accepted squadmate who is
    on the dungeon location and free (FEAT-144 Ф3-3, FEAT-175 rules)."""
    return await start_run(db, dungeon_id, character_id, user_id, party=True)


async def enter_dungeon(db: AsyncSession, session_id: int, character_id: int) -> SessionStateResponse:
    """Legacy second step of the solo flow. Runs are created active now, so this
    only returns the state (idempotent). Legacy `forming` rows are closed by
    migration 004 / the sweeper."""
    session_obj = await _get_session(db, session_id)
    _require_member(session_obj, character_id)
    if session_obj.status == "forming":
        raise HTTPException(status_code=409, detail="Сессия устарела — войдите в подземелье заново")
    return await get_session_state(db, session_id, character_id)


# =====================================================================
# Redis state (cache of the DB run state)
# =====================================================================

async def ensure_redis_state(db: AsyncSession, session_obj: DungeonSession) -> Optional[Dict]:
    """Return the Redis state, rebuilding it from the DB if it is gone
    (Redis flush/restart). Returns None for ended sessions that have nothing
    to rebuild."""
    state = await session_state.get_session_state(session_obj.id)
    if state is not None:
        return state
    if session_obj.finalized_at is not None or session_obj.status == "wiped":
        return None
    if session_obj.status == STATUS_ACTIVE and session_obj.current_room_id is None:
        return None
    phase = PHASE_EXPLORING
    if session_obj.status in ("completed", "escaped"):
        phase = PHASE_DISTRIBUTING
    elif session_obj.active_battle_id:
        phase = PHASE_IN_BATTLE
    else:
        room = await _get_room(db, session_obj.current_room_id)
        rs = await _get_room_state(db, session_obj.id, session_obj.current_room_id)
        extra = rs.extra_data if isinstance(rs.extra_data, dict) else {}
        if room and room.room_type in ("battle", "boss") and not rs.is_cleared:
            phase = PHASE_BATTLE_PENDING
        elif extra.get("rest_started_at") and not extra.get("rest_used"):
            phase = PHASE_RESTING
    await session_state.init_session_state(
        session_id=session_obj.id,
        dungeon_id=session_obj.dungeon_id,
        leader_character_id=session_obj.leader_character_id,
        members={str(m.character_id): {"user_id": m.user_id, "status": m.status}
                 for m in session_obj.members},
    )
    state = await session_state.update_session_state(
        session_obj.id,
        status=session_obj.status,
        phase=phase,
        current_room_id=session_obj.current_room_id,
        active_battle_id=session_obj.active_battle_id,
        battle_mob_ids=session_obj.battle_mob_ids,
        pending_target_room_id=session_obj.pending_target_room_id,
        pending_corridor_id=session_obj.pending_corridor_id,
    )
    logger.warning("Сессия %d: состояние Redis восстановлено из БД (phase=%s)", session_obj.id, phase)
    return state


async def _require_state(db: AsyncSession, session_obj: DungeonSession) -> Dict:
    state = await ensure_redis_state(db, session_obj)
    if state is None:
        raise HTTPException(status_code=409, detail="Забег уже завершён")
    return state


# =====================================================================
# Session state (GET /state)
# =====================================================================

async def _mana_core_info(db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon) -> Optional[ManaCoreInfo]:
    mc_room = (await db.execute(select(DungeonRoom).where(
        DungeonRoom.dungeon_id == dungeon.id, DungeonRoom.is_mana_core_room == True,  # noqa: E712
    ).limit(1))).scalar_one_or_none()
    if not mc_room:
        return None
    boss_extra, boss_cleared = await _boss_state(db, session_obj)
    mc_state = (await db.execute(select(DungeonRoomState).where(
        DungeonRoomState.session_id == session_obj.id, DungeonRoomState.room_id == mc_room.id,
    ))).scalar_one_or_none()
    mc_extra = mc_state.extra_data if mc_state and isinstance(mc_state.extra_data, dict) else {}
    revealed = bool(boss_extra.get("mana_core_revealed"))
    searched = bool(mc_extra.get("mana_core_searched"))
    return ManaCoreInfo(
        revealed=revealed,
        room_id=mc_room.id if revealed else None,
        room_name=mc_room.name if revealed else None,
        accessible=revealed and boss_cleared and not searched and session_obj.status == STATUS_ACTIVE,
        searched=searched,
        destroyed=bool(mc_extra.get("mana_core_destroyed")),
    )


async def _boss_state(db: AsyncSession, session_obj: DungeonSession) -> Tuple[dict, bool]:
    """(extra_data of the cleared boss room state, any boss cleared?)"""
    rows = (await db.execute(
        select(DungeonRoomState)
        .join(DungeonRoom, DungeonRoom.id == DungeonRoomState.room_id)
        .where(DungeonRoomState.session_id == session_obj.id, DungeonRoom.is_boss_room == True)  # noqa: E712
    )).scalars().all()
    for rs in rows:
        if rs.is_cleared:
            return (rs.extra_data if isinstance(rs.extra_data, dict) else {}), True
    return {}, False


async def get_session_state(
    db: AsyncSession,
    session_id: int,
    character_id: int,
) -> SessionStateResponse:
    """Full session state for a member. Applies the abandonment rule and the
    battle-result polling fallback lazily."""
    session_obj = await _get_session(db, session_id)
    _require_member(session_obj, character_id)

    ended = await expire_if_abandoned(db, session_id)
    session_obj = await _get_session(db, session_id)
    if not ended and session_obj.status == STATUS_ACTIVE and session_obj.active_battle_id:
        # Polling fallback for the battle callback.
        try:
            await poll_active_battle(db, session_id)
        except Exception:
            logger.warning("Сессия %d: проверка боя не удалась", session_id, exc_info=True)
        session_obj = await _get_session(db, session_id)

    dungeon = await _get_dungeon_for_session(db, session_obj.dungeon_id)

    redis_state = None
    if session_obj.finalized_at is None and session_obj.status != "wiped":
        try:
            redis_state = await ensure_redis_state(db, session_obj)
        except Exception:
            logger.warning("Сессия %d: Redis недоступен", session_id, exc_info=True)
    if session_obj.status == "wiped":
        phase = PHASE_WIPED
    elif session_obj.finalized_at is not None:
        phase = PHASE_FINISHED
    elif redis_state:
        phase = redis_state.get("phase", PHASE_EXPLORING)
    elif session_obj.status in ("completed", "escaped"):
        phase = PHASE_DISTRIBUTING
    else:
        phase = PHASE_EXPLORING

    current_room_view = None
    room = await _get_room(db, session_obj.current_room_id)
    if room:
        rs = (await db.execute(select(DungeonRoomState).where(
            DungeonRoomState.session_id == session_id, DungeonRoomState.room_id == room.id,
        ))).scalar_one_or_none()
        current_room_view = await _room_view(db, room, rs, session_obj, character_id, dungeon)

    inv_items = await _inventory_rows(db, session_id)
    name_cache: Dict[int, Optional[str]] = {}
    group_inventory = [
        GroupInventoryItemResponse(
            item_id=item.item_id,
            item_name=await _item_name(item.item_id, name_cache),
            quantity=item.quantity,
            source_description=item.source_description,
        )
        for item in inv_items
    ]

    explored_rooms: List[ExploredRoomInfo] = []
    explored_corridors: List[ExploredCorridorInfo] = []
    seen_doors: List[SeenDoorInfo] = []
    if session_obj.current_room_id:
        visited_rows = (await db.execute(
            select(
                DungeonRoom.id, DungeonRoom.name, DungeonRoom.room_type,
                DungeonRoom.position_x, DungeonRoom.position_y, DungeonRoomState.is_cleared,
                DungeonRoom.grid_w, DungeonRoom.grid_d, DungeonRoom.is_entrance, DungeonRoom.room_config,
                DungeonRoom.floor, DungeonRoomState.loot_collected, DungeonRoomState.extra_data,
            )
            .join(DungeonRoomVisit, DungeonRoomVisit.room_id == DungeonRoom.id)
            .outerjoin(
                DungeonRoomState,
                (DungeonRoomState.room_id == DungeonRoom.id) & (DungeonRoomState.session_id == session_id),
            )
            .where(
                DungeonRoomVisit.dungeon_id == session_obj.dungeon_id,
                DungeonRoomVisit.character_id == character_id,
                DungeonRoom.id != session_obj.current_room_id,
            )
        )).all()
        for row in visited_rows:
            explored_rooms.append(ExploredRoomInfo(
                id=row[0], name=row[1], room_type=row[2],
                position_x=row[3], position_y=row[4],
                is_cleared=bool(row[5]) if row[5] is not None else False,
                grid_w=row[6], grid_d=row[7], is_entrance=bool(row[8]),
                mob_count=(len((row[9] or {}).get("mob_template_ids") or [])
                           if row[2] in ("battle", "boss") and isinstance(row[9], dict) else None),
                portal=_portal_kind(row[2], row[9]),
                floor=int(row[10] or 1),
                used=_room_used(row[2], row[11], row[12]),
                dark=bool(isinstance(row[9], dict) and row[9].get("dark") is True
                          and not (isinstance(row[12], dict) and row[12].get("lit") == LIGHT_SPELL)),
            ))
        visited_ids = {r.id for r in explored_rooms} | {session_obj.current_room_id}
        unseen_by_corridor: Dict[int, Tuple[int, int]] = {}
        unseen_locks: Dict[int, DungeonCorridor] = {}
        for c in (await db.execute(select(DungeonCorridor).where(
            DungeonCorridor.dungeon_id == session_obj.dungeon_id,
            DungeonCorridor.from_room_id.in_(visited_ids) | DungeonCorridor.to_room_id.in_(visited_ids),
        ))).scalars().all():
            if _hidden_way(session_obj, c):
                continue  # a hidden drop or secret passage not found yet is not seen either
            if c.from_room_id in visited_ids and c.to_room_id in visited_ids:
                lock = _corridor_lock(c)
                explored_corridors.append(ExploredCorridorInfo(
                    corridor_id=c.id, from_room_id=c.from_room_id, to_room_id=c.to_room_id,
                    source_handle=c.source_handle, target_handle=c.target_handle,
                    lock_key=lock["key"] if lock else None, locked=_is_shut(session_obj, c),
                    passage=_passage(c),
                ))
            elif c.from_room_id in visited_ids:
                unseen_by_corridor[c.id] = (c.from_room_id, c.to_room_id)
                unseen_locks[c.id] = c
            else:
                unseen_by_corridor[c.id] = (c.to_room_id, c.from_room_id)
                unseen_locks[c.id] = c
        if unseen_by_corridor:
            beyond = {r.id: r for r in (await db.execute(select(DungeonRoom).where(
                DungeonRoom.id.in_({to for _, to in unseen_by_corridor.values()}),
            ))).scalars().all()}
            for cid, (here_id, there_id) in unseen_by_corridor.items():
                room = beyond.get(there_id)
                if room is None:
                    continue
                lock = _corridor_lock(unseen_locks[cid])
                seen_doors.append(SeenDoorInfo(
                    corridor_id=cid, from_room_id=here_id, to_room_id=there_id,
                    position_x=room.position_x, position_y=room.position_y,
                    grid_w=room.grid_w, grid_d=room.grid_d,
                    lock_key=lock["key"] if lock else None,
                    locked=_is_shut(session_obj, unseen_locks[cid]) and not _bolt_side(unseen_locks[cid], here_id),
                    passage=_passage(unseen_locks[cid]), floor=_room_floor(room),
                ))

    last = session_obj.last_activity_at or session_obj.started_at
    knocked_out_until = None
    if session_obj.status == "wiped" and session_obj.finished_at:
        knocked_out_until = session_obj.finished_at + timedelta(seconds=WIPE_KNOCKOUT_SECONDS)

    return SessionStateResponse(
        session_id=session_obj.id,
        dungeon_id=session_obj.dungeon_id,
        dungeon_name=dungeon.name,
        location_id=dungeon.location_id,
        stability_type=dungeon.stability_type,
        danger_level=dungeon.danger_level,
        status=session_obj.status,
        phase=phase,
        current_room=current_room_view,
        members=await _member_responses(session_obj),
        group_inventory=group_inventory,
        active_battle_id=session_obj.active_battle_id,
        explored_rooms=explored_rooms,
        explored_corridors=explored_corridors,
        seen_doors=seen_doors,
        keys=_session_keys(session_obj),
        floors=int((await db.execute(select(func.max(DungeonRoom.floor)).where(
            DungeonRoom.dungeon_id == session_obj.dungeon_id))).scalar() or 1),
        mana_core=await _mana_core_info(db, session_obj, dungeon),
        finalized=session_obj.finalized_at is not None,
        cooldown_until=session_obj.cooldown_until,
        knocked_out_until=knocked_out_until,
        last_activity_at=last,
        abandon_at=(last + timedelta(seconds=ABANDON_AFTER_SECONDS))
        if (last and session_obj.finalized_at is None and session_obj.status != "wiped") else None,
        **(await _party_votes(session_obj)).dict(include={"votes", "waiting_for"}),
        shield=await _shield_info(session_obj),
        ambush=_ambush_info(session_obj, redis_state, phase),
        extents=await _floor_extents(db, session_obj.dungeon_id),
        theme=dungeon.theme or "stone",
        floor_themes=dungeon.floor_themes if isinstance(dungeon.floor_themes, dict) else {},
    )


# =====================================================================
# Party: deciding together (FEAT-176)
# =====================================================================
# The leader leads, but only once every living member has had their say on
# where to go from the room: a door, the blue portal, or "as the leader
# decides". A member away keeps the party waiting. A new room voids the votes.

VOTE_ANY = "any"
VOTE_PORTAL = "portal"
PING_COOLDOWN_SECONDS = 1


def _vote_of(character_id: int, choice: str) -> PartyVote:
    if choice == VOTE_PORTAL:
        return PartyVote(character_id=character_id, portal=True)
    if choice.startswith("c:"):
        return PartyVote(character_id=character_id, corridor_id=int(choice[2:]))
    return PartyVote(character_id=character_id)


async def _party_votes(session_obj: DungeonSession) -> PartyVotesResponse:
    room_id = session_obj.current_room_id
    alive = [m.character_id for m in session_obj.members if m.status == "alive"]
    if room_id is None:
        return PartyVotesResponse()
    votes = await session_state.get_votes(session_obj.id, alive, room_id)
    return PartyVotesResponse(
        room_id=room_id,
        votes=[_vote_of(cid, choice) for cid, choice in votes.items()],
        waiting_for=[cid for cid in alive if cid != session_obj.leader_character_id and cid not in votes],
    )


async def _require_party_ready(session_obj: DungeonSession) -> None:
    """The leader may lead the party on only once everyone has had their say."""
    waiting = (await _party_votes(session_obj)).waiting_for
    if waiting:
        names = [await _character_name(cid) for cid in waiting]
        raise HTTPException(
            status_code=409,
            detail=f"Отряд ещё не решил, куда идти: ждём {', '.join(names)}",
        )


async def vote_route(
    db: AsyncSession, session_id: int, character_id: int, corridor_id: Optional[int], portal: bool,
) -> PartyVotesResponse:
    """A member's say on where the party goes from the current room."""
    session_obj = await _get_session(db, session_id)
    if session_obj.status != STATUS_ACTIVE:
        raise HTTPException(status_code=400, detail="Сессия подземелья не активна")
    member = _require_member(session_obj, character_id)
    if member.status != "alive":
        raise HTTPException(status_code=409, detail="Павшие не решают, куда идти")
    redis_state = await _require_state(db, session_obj)
    if redis_state.get("phase") not in (PHASE_EXPLORING, PHASE_BATTLE_PENDING):
        raise HTTPException(status_code=400, detail="Сейчас не время решать, куда идти")
    room_id = session_obj.current_room_id
    if portal:
        room = await _get_room(db, room_id)
        cfg = room.room_config if room and isinstance(room.room_config, dict) else {}
        if room is None or _portal_kind(room.room_type, cfg) != PORTAL_BLUE:
            raise HTTPException(status_code=400, detail="Здесь нет портала, в который можно шагнуть")
        choice = VOTE_PORTAL
    elif corridor_id is not None:
        corridor = (await db.execute(select(DungeonCorridor).where(
            DungeonCorridor.id == corridor_id, DungeonCorridor.dungeon_id == session_obj.dungeon_id,
        ))).scalar_one_or_none()
        leads_out = corridor is not None and (
            corridor.from_room_id == room_id or (corridor.to_room_id == room_id and corridor.is_bidirectional)
        ) and not (_hidden_way(session_obj, corridor) and corridor.from_room_id == room_id)
        if not leads_out:
            raise HTTPException(status_code=400, detail="Этот коридор недоступен из текущей комнаты")
        choice = f"c:{corridor_id}"
    else:
        choice = VOTE_ANY
    await session_state.set_vote(session_id, character_id, room_id, choice)
    result = await _party_votes(session_obj)
    # Who voted, so the table can have them say it aloud.
    await ws_manager.broadcast_to_session(session_id, {"type": "party_vote",
                                                       "data": {**result.dict(), "character_id": character_id}})
    return result


async def chat_say(db: AsyncSession, session_id: int, character_id: int, text: str) -> ChatEntry:
    """A party member's line in the run's chat (anyone in the run, fallen too; not more than once a second)."""
    session_obj = await _get_session(db, session_id)
    if session_obj.status != STATUS_ACTIVE:
        raise HTTPException(status_code=400, detail="Сессия подземелья не активна")
    _require_member(session_obj, character_id)
    text = " ".join((text or "").split())
    if not text:
        raise HTTPException(status_code=400, detail="Пустое сообщение")
    if len(text) > chat.CHAT_MAX_LEN:
        raise HTTPException(status_code=400, detail=f"Сообщение длиннее {chat.CHAT_MAX_LEN} символов")
    if not await session_state.allow_say(session_id, character_id, chat.SAY_COOLDOWN_SECONDS):
        raise HTTPException(status_code=429, detail="Не так быстро")
    entry = await chat.say(session_id, character_id, await _character_name(character_id), text)
    return ChatEntry(**entry)


async def chat_history(db: AsyncSession, session_id: int, character_id: int) -> List[ChatEntry]:
    session_obj = await _get_session(db, session_id)
    _require_member(session_obj, character_id)
    return [ChatEntry(**e) for e in await chat.history(session_id)]


async def ping_board(
    db: AsyncSession, session_id: int, character_id: int, kind: str,
    room_id: Optional[int], corridor_id: Optional[int],
) -> dict:
    """A member marks a room or a door on the table for the others to see."""
    session_obj = await _get_session(db, session_id)
    if session_obj.status != STATUS_ACTIVE:
        raise HTTPException(status_code=400, detail="Сессия подземелья не активна")
    _require_member(session_obj, character_id)
    if room_id is None and corridor_id is None:
        raise HTTPException(status_code=400, detail="Отметьте комнату или дверь")
    if room_id is not None:
        room = await _get_room(db, room_id)
        if room is None or room.dungeon_id != session_obj.dungeon_id:
            raise HTTPException(status_code=404, detail="Комната не найдена")
    if corridor_id is not None:
        corridor = (await db.execute(select(DungeonCorridor).where(
            DungeonCorridor.id == corridor_id))).scalar_one_or_none()
        if corridor is None or corridor.dungeon_id != session_obj.dungeon_id:
            raise HTTPException(status_code=404, detail="Проход не найден")
    if not await session_state.allow_ping(session_id, character_id, PING_COOLDOWN_SECONDS):
        raise HTTPException(status_code=429, detail="Не так часто")
    await ws_manager.broadcast_to_session(session_id, {
        "type": "party_ping",
        "data": {"character_id": character_id, "kind": kind, "room_id": room_id, "corridor_id": corridor_id},
    })
    return {"ok": True}


# =====================================================================
# Stat checks / damage
# =====================================================================

async def perform_stat_check(
    session_state_data: Dict,
    stat_name: str,
    difficulty: int,
    difficulty_modifier: float,
) -> Tuple[bool, str, int]:
    """
    Stat check against the best value among alive party members.
    Returns (passed, best_character_name, best_value).
    """
    members = session_state_data.get("members", {})
    alive_ids = [int(cid) for cid, info in members.items() if info.get("status") == "alive"]
    if not alive_ids:
        return (False, "", 0)

    best_value = -1
    best_id = None
    for character_id in alive_ids:
        try:
            attrs = await http_clients.get_character_attributes(character_id)
        except Exception:
            logger.warning("Не удалось получить атрибуты персонажа %d для проверки %s",
                           character_id, stat_name)
            continue
        cumulative = attrs.get("cumulative_stats", {}) or {}
        value = cumulative.get(stat_name, attrs.get(stat_name, 0))
        if isinstance(value, (int, float)) and value > best_value:
            best_value = int(value)
            best_id = character_id

    best_name = await _character_name(best_id) if best_id is not None else ""
    adjusted_difficulty = math.ceil(difficulty * (difficulty_modifier or 1.0))
    return (best_value >= adjusted_difficulty, best_name, max(best_value, 0))


async def _damage_party(alive_ids: List[int], damage: int) -> List[dict]:
    """Deal `damage` HP to every alive member via character-attributes.
    Traps and events never kill: HP stops at 1 (deaths happen in battles)."""
    report = []
    if damage <= 0:
        return report
    for cid in alive_ids:
        try:
            attrs = await http_clients.get_character_attributes(cid)
            current = int(attrs.get("current_health", 0) or 0)
            dealt = max(0, min(damage, current - 1))
            if dealt > 0:
                await http_clients.recover_character(cid, health=-dealt)
            report.append({"character_id": cid, "damage": dealt})
        except Exception:
            logger.warning("Не удалось нанести урон персонажу %d", cid, exc_info=True)
    return report


async def _heal_party(alive_ids: List[int], heal_percent: Optional[float], heal_amount: Optional[int]) -> List[dict]:
    report = []
    for cid in alive_ids:
        try:
            if heal_percent is not None:
                attrs = await http_clients.get_character_attributes(cid)
                amount = max(1, int(int(attrs.get("max_health", 100) or 100) * float(heal_percent) / 100))
            else:
                amount = int(heal_amount or 0)
            if amount > 0:
                await http_clients.recover_character(cid, health=amount)
            report.append({"character_id": cid, "healed": amount})
        except Exception:
            logger.warning("Не удалось восстановить HP персонажу %d", cid, exc_info=True)
    return report


# =====================================================================
# Battles
# =====================================================================

async def _mob_names(mob_character_ids: List[int]) -> List[str]:
    return [await _character_name(cid) for cid in mob_character_ids]


async def start_battle(
    db: AsyncSession,
    session_obj: DungeonSession,
    dungeon: Dungeon,
    mob_template_ids: List[int],
    *,
    room: Optional[DungeonRoom] = None,
    corridor_id: Optional[int] = None,
    pending_target_room_id: Optional[int] = None,
) -> Tuple[int, List[str]]:
    """Spawn dungeon mobs and create a dungeon battle (battle-service internal
    path, tagged with the session). On failure nothing is left behind (mobs
    are despawned). Sets `active_battle_id` on the session (DB + Redis); the
    caller commits."""
    if not mob_template_ids:
        raise HTTPException(status_code=409, detail="Комната боя не настроена — нет мобов. Сообщите администратору.")
    alive_ids = _alive_ids(session_obj)
    if not alive_ids:
        raise HTTPException(status_code=400, detail="В группе нет живых участников для боя")

    # Deeper floors breed stronger mobs: the battle's room (or the corridor's target / the current room).
    floor_room = room or await _get_room(db, pending_target_room_id or session_obj.current_room_id)
    multiplier = float(dungeon.mob_multiplier or 1.0) * _floor_factor(dungeon.floor_mob_step, _room_floor(floor_room))
    mob_ids = await http_clients.spawn_dungeon_mobs(
        mob_template_ids, dungeon.location_id, stat_multiplier=round(multiplier, 3),
    )
    if not mob_ids:
        raise HTTPException(status_code=502, detail="Не удалось создать мобов для боя")
    players = [{"character_id": cid, "team": 1} for cid in alive_ids]
    players += [{"character_id": cid, "team": 2} for cid in mob_ids]
    try:
        battle = await http_clients.create_dungeon_battle(session_obj.id, players)
        battle_id = battle.get("battle_id")
        if not battle_id:
            raise HTTPException(status_code=502, detail="Боевая система вернула некорректный ответ")
    except Exception:
        await http_clients.despawn_dungeon_mobs(mob_ids)
        raise

    session_obj.active_battle_id = battle_id
    session_obj.battle_mob_ids = mob_ids
    session_obj.pending_target_room_id = pending_target_room_id
    session_obj.pending_corridor_id = corridor_id
    await session_state.update_session_state(
        session_obj.id,
        phase=PHASE_IN_BATTLE,
        active_battle_id=battle_id,
        battle_mob_ids=mob_ids,
        pending_target_room_id=pending_target_room_id,
        # A corridor ambush: the party is caught halfway (the 3D table shows it there).
        pending_corridor_id=corridor_id,
    )
    names = await _mob_names(mob_ids)
    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "battle_started",
        "data": {
            "battle_id": battle_id,
            "room_id": room.id if room else None,
            "room_name": room.name if room else None,
            "corridor_id": corridor_id,
            "mob_character_ids": mob_ids,
            "mob_names": names,
            "message": "В коридоре на вас напали враги!" if corridor_id else "Бой начинается!",
        },
    })
    logger.info("Сессия %d: бой %d (комната=%s, коридор=%s, мобы=%s)",
                session_obj.id, battle_id, room.id if room else None, corridor_id, mob_ids)
    return battle_id, names


def _battle_of(session_obj: DungeonSession, redis_state: Optional[dict]) -> Tuple[List[int], Optional[int], Optional[int]]:
    """The battle being fought: (mobs, target room, corridor). From the DB; Redis only for a battle
    started before the DB kept it (alembic 009)."""
    redis_state = redis_state or {}
    mobs = session_obj.battle_mob_ids or redis_state.get("battle_mob_ids") or []
    target = session_obj.pending_target_room_id or redis_state.get("pending_target_room_id")
    corridor = session_obj.pending_corridor_id or redis_state.get("pending_corridor_id")
    return list(mobs), target, corridor


def _forget_battle(session_obj: DungeonSession) -> None:
    session_obj.battle_mob_ids = None
    session_obj.pending_target_room_id = None
    session_obj.pending_corridor_id = None


def outcome_from_state(battle_state_data: dict) -> Optional[Tuple[bool, List[int]]]:
    """(party_won, party casualties) from a battle-service state, or None while
    the battle is still running."""
    participants = (battle_state_data or {}).get("runtime", {}).get("participants", {}) or {}
    if not participants:
        return None
    team1_alive = any(p.get("team") == 1 and (p.get("hp") or 0) > 0 for p in participants.values())
    team2_alive = any(p.get("team") == 2 and (p.get("hp") or 0) > 0 for p in participants.values())
    if team1_alive and team2_alive:
        return None
    casualties = [p.get("character_id") for p in participants.values()
                  if p.get("team") == 1 and (p.get("hp") or 0) <= 0]
    return (team1_alive and not team2_alive), casualties


async def poll_active_battle(db: AsyncSession, session_id: int) -> Optional[Dict]:
    """Polling fallback for the battle callback (GET /state, sweeper)."""
    session_obj = await _get_session(db, session_id)
    battle_id = session_obj.active_battle_id
    if not battle_id:
        return None
    state = await http_clients.get_battle_state(battle_id)
    if state is not None:
        outcome = outcome_from_state(state)
        if outcome is None:
            return None
        return await complete_battle(db, session_id, battle_id, party_won=outcome[0], casualties=outcome[1])
    result = await http_clients.get_battle_result(battle_id)
    if result is None or result.get("status") not in ("finished", "forfeit"):
        return None
    if result.get("aborted"):
        return await complete_battle(db, session_id, battle_id, party_won=False, casualties=[], aborted=True)
    party_won = result.get("winner_team") == 1
    casualties = [] if party_won else _member_ids(session_obj)
    return await complete_battle(db, session_id, battle_id, party_won=party_won, casualties=casualties)


async def process_battle_callback(db: AsyncSession, session_id: int, battle_id: int,
                                  winner_team: Optional[int], defeated: List[int], aborted: bool) -> Dict:
    session_obj = await _get_session(db, session_id)
    members = set(_member_ids(session_obj))
    casualties = [cid for cid in defeated if cid in members]
    return await complete_battle(
        db, session_id, battle_id,
        party_won=(winner_team == 1 and not aborted),
        casualties=casualties,
        aborted=aborted,
    )


async def complete_battle(
    db: AsyncSession,
    session_id: int,
    battle_id: int,
    *,
    party_won: bool,
    casualties: List[int],
    aborted: bool = False,
) -> Dict:
    """Apply a finished dungeon battle exactly once.

    Guard: under the session row lock, `active_battle_id` must still equal
    `battle_id`; it is cleared in the same transaction. A second caller
    (callback vs polling, double delivery) finds it cleared and is ignored.
    """
    session_obj = await _get_session(db, session_id, lock=True)
    if session_obj.active_battle_id != battle_id or session_obj.status != STATUS_ACTIVE:
        await db.commit()  # release the lock; commit (not rollback) keeps loaded objects usable
        return {"status": "ignored", "battle_id": battle_id}
    mob_ids, pending_target, _ = _battle_of(session_obj, await session_state.get_session_state(session_id))
    session_obj.active_battle_id = None
    _forget_battle(session_obj)
    _touch(session_obj)
    # A battle lost outright (not broken off): everyone in it is beaten, even one who sat it out
    # and still stands — a lost fight is a wipe, not a retry.
    if not party_won and not aborted:
        casualties = sorted(set(casualties) | set(_alive_ids(session_obj)))

    dungeon = await _get_dungeon_for_session(db, session_obj.dungeon_id)
    await ensure_redis_state(db, session_obj)
    results: Dict = {
        "status": "processed", "battle_id": battle_id, "party_won": party_won,
        "aborted": aborted, "casualties": casualties,
    }

    # Casualties (DB + Redis)
    for m in session_obj.members:
        if m.character_id in casualties and m.status != "dead":
            m.status = "dead"
            await session_state.update_member_status(session_id, str(m.character_id), "dead")

    if not aborted and all(m.status == "dead" for m in session_obj.members):
        await db.flush()
        await _wipe_session(db, session_obj, dungeon, battle_id=battle_id)
        await http_clients.despawn_dungeon_mobs(mob_ids)
        results["wiped"] = True
        return results

    room = await _get_room(db, session_obj.current_room_id)
    room_event = None
    if party_won and pending_target:
        # Corridor battle won: continue into the target room.
        target = await _get_room(db, pending_target)
        await session_state.update_session_state(
            session_id, active_battle_id=None, pending_target_room_id=None, pending_corridor_id=None,
            battle_mob_ids=None, phase=PHASE_EXPLORING,
        )
        if target:
            room_event = await _enter_room(db, session_obj, dungeon, target)
    elif party_won:
        rs = await _get_room_state(db, session_id, session_obj.current_room_id)
        rs.is_cleared = True
        if room and room.room_type == "battle" and isinstance(room.room_config, dict):
            await _grant_key(session_obj, room.room_config.get("key_reward"), f"Бой: {room.name}")
        await session_state.update_session_state(
            session_id, active_battle_id=None, battle_mob_ids=None, phase=PHASE_EXPLORING,
        )
        if room and room.is_boss_room:
            results["boss_cleared"] = True
            results.update(await _handle_boss_room_cleared(db, session_obj, dungeon, room, rs))
    else:
        # Aborted (force-finished) battle: nobody won. The party stays where it
        # was; an uncleared battle room can be retried (`start_battle`).
        retry = (
            not pending_target and room is not None
            and room.room_type in ("battle", "boss")
            and not (await _get_room_state(db, session_id, room.id)).is_cleared
        )
        await session_state.update_session_state(
            session_id, active_battle_id=None, pending_target_room_id=None, pending_corridor_id=None,
            battle_mob_ids=None, phase=PHASE_BATTLE_PENDING if retry else PHASE_EXPLORING,
        )

    await db.commit()
    await http_clients.despawn_dungeon_mobs(mob_ids)

    await ws_manager.broadcast_to_session(session_id, {
        "type": "battle_ended",
        "data": {
            "battle_id": battle_id,
            "party_won": party_won,
            "aborted": aborted,
            "casualties": casualties,
            "boss_cleared": results.get("boss_cleared", False),
            "mana_core_revealed": results.get("mana_core_revealed", False),
            "room_event": room_event,
            "message": (
                "Победа! Враги повержены." if party_won
                else ("Бой прерван." if aborted else "Поражение...")
            ),
        },
    })
    for cid in casualties:
        await ws_manager.broadcast_to_session(session_id, {
            "type": "member_status_changed",
            "data": {"character_id": cid, "name": await _character_name(cid),
                     "status": "dead", "new_status": "dead"},
        })
    return results


async def _handle_boss_room_cleared(
    db: AsyncSession,
    session_obj: DungeonSession,
    dungeon: Dungeon,
    boss_room: DungeonRoom,
    boss_state: DungeonRoomState,
) -> Dict:
    """Boss beaten. ONE mana-core roll per run; on success the core is revealed
    for THIS session only (stored on the boss room state — the dungeon graph
    is never modified). The party may search the core before opening the
    boss chest; opening the chest completes the run."""
    result: Dict = {}
    mc_room = (await db.execute(select(DungeonRoom).where(
        DungeonRoom.dungeon_id == dungeon.id, DungeonRoom.is_mana_core_room == True,  # noqa: E712
    ).limit(1))).scalar_one_or_none()
    extra = dict(boss_state.extra_data) if isinstance(boss_state.extra_data, dict) else {}
    if mc_room and (dungeon.mana_core_chance or 0) > 0 and "mana_core_roll" not in extra:
        roll = random.random()
        extra["mana_core_roll"] = roll
        if roll < dungeon.mana_core_chance:
            extra["mana_core_revealed"] = True
            result.update({"mana_core_revealed": True, "mana_core_room_id": mc_room.id,
                           "mana_core_room_name": mc_room.name})
        boss_state.extra_data = extra
    if result.get("mana_core_revealed"):
        await ws_manager.broadcast_to_session(session_obj.id, {
            "type": "mana_core_revealed",
            "data": {
                "room_id": mc_room.id,
                "room_name": mc_room.name,
                "message": "Ядро маны обнаружено! Его можно найти до того, как вы откроете сундук босса.",
            },
        })
    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "session_status",
        "data": {"status": STATUS_ACTIVE, "phase": PHASE_EXPLORING,
                 "message": "Босс повержен! Заберите добычу из сундука."},
    })
    result["boss_defeated"] = True
    return result


# =====================================================================
# Wipe / escape / close
# =====================================================================

async def _wipe_session(db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon,
                        battle_id: Optional[int] = None) -> None:
    """All members dead: the raid's loot is lost, everyone is knocked out for
    WIPE_KNOCKOUT_SECONDS on the dungeon's location, no cooldown."""
    now = _utcnow()
    for row in await _inventory_rows(db, session_obj.id):
        await db.delete(row)
    session_obj.status = "wiped"
    session_obj.active_battle_id = None
    session_obj.finished_at = session_obj.finished_at or now
    session_obj.finalized_at = now
    member_ids = _member_ids(session_obj)
    await db.commit()

    knocked = await http_clients.knockout_characters(
        member_ids, WIPE_KNOCKOUT_SECONDS, session_obj.id, dungeon.location_id,
    )
    if knocked is None:
        # Never leave the party dungeon-locked forever.
        await http_clients.clear_dungeon_lock(member_ids, session_obj.id)
    until = now + timedelta(seconds=WIPE_KNOCKOUT_SECONDS)
    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "session_status",
        "data": {
            "status": "wiped",
            "phase": PHASE_WIPED,
            "battle_id": battle_id,
            "knocked_out_until": until.isoformat(),
            "location_id": dungeon.location_id,
            "message": "Вся группа пала. Вас без сознания вынесли из подземелья — "
                       "очнётесь через час. Добыча забега потеряна.",
        },
    })
    await session_state.cleanup_session(session_obj.id, member_ids)
    await ws_manager.cleanup_session(session_obj.id)
    logger.info("Сессия %d: вайп, персонажи %s без сознания до %s", session_obj.id, member_ids, until)


async def _escape_loss_chance(db: AsyncSession, session_obj: DungeonSession) -> float:
    """Each loot stack is lost with this chance when fleeing: the deeper the party, the worse."""
    dungeon = await _get_dungeon_for_session(db, session_obj.dungeon_id)
    room = await _get_room(db, session_obj.current_room_id) if session_obj.current_room_id else None
    chance = ESCAPE_LOSS_CHANCE + float(dungeon.floor_flee_step or 0.0) * max(0, _room_floor(room) - 1)
    return min(ESCAPE_LOSS_CHANCE_MAX, chance)


async def _escape(db: AsyncSession, session_obj: DungeonSession, reason: str,
                  apply_loss: bool = True) -> Tuple[List[FleeItemInfo], List[FleeItemInfo]]:
    """End an active run as `escaped`: each loot stack is lost with
    ESCAPE_LOSS_CHANCE, the dungeon is free at once (no cooldown) and the
    members' dungeon lock is released. Remaining loot can still be
    distributed (phase distributing_loot) until finalize."""
    items_lost: List[FleeItemInfo] = []
    items_remaining: List[FleeItemInfo] = []
    cache: Dict[int, Optional[str]] = {}
    loss_chance = await _escape_loss_chance(db, session_obj)
    for item in await _inventory_rows(db, session_obj.id, lock=True):
        info = FleeItemInfo(item_id=item.item_id, quantity=item.quantity,
                            item_name=await _item_name(item.item_id, cache))
        if apply_loss and random.random() < loss_chance:
            items_lost.append(info)
            await db.delete(item)
        else:
            items_remaining.append(info)

    battle_mobs, _, _ = _battle_of(session_obj, await session_state.get_session_state(session_obj.id))
    _forget_battle(session_obj)
    session_obj.status = "escaped"
    session_obj.active_battle_id = None
    session_obj.finished_at = session_obj.finished_at or _utcnow()
    _touch(session_obj)
    await db.commit()

    member_ids = _member_ids(session_obj)
    await http_clients.clear_dungeon_lock(member_ids, session_obj.id)
    for cid in member_ids:
        await session_state.clear_character_active_session(cid)
    await session_state.update_session_state(
        session_obj.id, status="escaped", phase=PHASE_DISTRIBUTING,
        active_battle_id=None, pending_target_room_id=None, pending_corridor_id=None, battle_mob_ids=None,
    )
    await _sync_inventory_cache(db, session_obj.id)
    await http_clients.despawn_dungeon_mobs(battle_mobs)
    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "session_status",
        "data": {
            "status": "escaped",
            "phase": PHASE_DISTRIBUTING,
            "reason": reason,
            "items_lost": [i.dict() for i in items_lost],
            "items_remaining": [i.dict() for i in items_remaining],
            "message": "Группа покинула подземелье. Часть добычи потеряна."
            if items_lost else "Группа покинула подземелье.",
        },
    })
    return items_lost, items_remaining


async def _deliver_leftovers_to_leader(db: AsyncSession, session_obj: DungeonSession) -> bool:
    """Auto-close helper: hand undistributed loot to the leader. Returns False
    if some delivery failed (the rows stay; the sweeper retries)."""
    ok = True
    for row in await _inventory_rows(db, session_obj.id, lock=True):
        item_id, quantity, source = row.item_id, row.quantity, row.source_description
        # Claimed (gone from the run) before it is handed over: a delivery is never repeated by a
        # retry. If it fails, the row comes back for the sweeper.
        await db.delete(row)
        await db.commit()
        try:
            await http_clients.add_item_to_character(session_obj.leader_character_id, item_id, quantity)
        except Exception:
            ok = False
            db.add(DungeonSessionInventory(session_id=session_obj.id, item_id=item_id, quantity=quantity,
                                           source_description=source))
            await db.commit()
            logger.warning("Сессия %d: не удалось выдать предмет %d лидеру", session_obj.id, item_id)
    await db.commit()
    return ok


async def _close_session(db: AsyncSession, session_obj: DungeonSession) -> None:
    """Final cleanup of an ended (completed/escaped) session."""
    session_obj.finalized_at = _utcnow()
    session_obj.finished_at = session_obj.finished_at or session_obj.finalized_at
    await db.commit()
    member_ids = _member_ids(session_obj)
    await http_clients.clear_dungeon_lock(member_ids, session_obj.id)
    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "session_status",
        "data": {"status": session_obj.status, "phase": PHASE_FINISHED, "finalized": True,
                 "message": "Забег завершён."},
    })
    await session_state.cleanup_session(session_obj.id, member_ids)
    await ws_manager.cleanup_session(session_obj.id)


# =====================================================================
# Abandonment / sweeper
# =====================================================================

def _last_activity(session_obj: DungeonSession) -> Optional[datetime]:
    return session_obj.last_activity_at or session_obj.started_at or session_obj.created_at


async def expire_if_abandoned(db: AsyncSession, session_id: int, now: Optional[datetime] = None) -> bool:
    """24 h without any action -> treated as an escape (same loss rule), the
    leftovers go to the leader and the session is closed. Legacy `forming`
    sessions are closed outright. Returns True if the session was ended."""
    now = now or _utcnow()
    session_obj = await _get_session(db, session_id, lock=True)
    last = _last_activity(session_obj)
    stale = last is not None and (now - last).total_seconds() >= ABANDON_AFTER_SECONDS
    if session_obj.finalized_at is not None or session_obj.status == "wiped":
        await db.commit()  # nothing changed; release the row lock without expiring objects
        return False
    if session_obj.status == "forming":
        session_obj.status = "escaped"
        await _close_session(db, session_obj)
        return True
    if not stale:
        await db.commit()
        return False
    if session_obj.status == STATUS_ACTIVE:
        logger.info("Сессия %d брошена (последнее действие %s) — считается побегом", session_id, last)
        await _escape(db, session_obj, reason="abandoned", apply_loss=True)
        session_obj = await _get_session(db, session_id, lock=True)
    if await _deliver_leftovers_to_leader(db, session_obj):
        session_obj = await _get_session(db, session_id, lock=True)
        await _close_session(db, session_obj)
    return True


async def sweep_sessions(db: AsyncSession, now: Optional[datetime] = None) -> Dict[str, int]:
    """Periodic maintenance (background task, every SWEEP_INTERVAL_SECONDS).
    Idempotent: every step re-reads the session under its row lock."""
    now = now or _utcnow()
    stats = {"abandoned": 0, "battles": 0, "redis_rebuilt": 0}
    ids = (await db.execute(
        select(DungeonSession.id).where(
            DungeonSession.finalized_at.is_(None),
            DungeonSession.status.in_(("forming", "active", "completed", "escaped")),
        )
    )).scalars().all()
    await db.rollback()
    for sid in ids:
        try:
            if await expire_if_abandoned(db, sid, now=now):
                stats["abandoned"] += 1
                continue
            session_obj = await _get_session(db, sid)
            if session_obj.status != STATUS_ACTIVE:
                continue
            if await session_state.get_session_state(sid) is None:
                if await ensure_redis_state(db, session_obj) is not None:
                    stats["redis_rebuilt"] += 1
                    await db.commit()
                else:
                    await _escape(db, await _get_session(db, sid, lock=True), reason="state_lost",
                                  apply_loss=False)
                    stats["abandoned"] += 1
                    continue
            if session_obj.active_battle_id:
                if await poll_active_battle(db, sid):
                    stats["battles"] += 1
        except Exception:
            await db.rollback()
            logger.exception("Sweep: ошибка при обработке сессии %d", sid)
    return stats


# =====================================================================
# Room entry effects (trap / teleport / battle continuation)
# =====================================================================

async def _apply_trap(db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon,
                      cfg: dict, default_damage: int, source: str, shield: Optional[dict] = None,
                      dark: bool = False) -> dict:
    """The best of the party rolls to spot the trap; missed, it hits everyone —
    or only the one holding up the party shield, and softened by it. In the
    dark it strikes harder."""
    stat_check = cfg.get("stat_check", "agility")
    difficulty = int(cfg.get("difficulty", 10) or 10)
    fail_damage = int(cfg.get("fail_damage", default_damage) or 0)
    if dark:
        fail_damage = math.ceil(fail_damage * DARK_TRAP_FACTOR)
    state = {"members": {str(m.character_id): {"status": m.status} for m in session_obj.members}}
    passed, best_name, best_value = await perform_stat_check(
        state, stat_check, difficulty, dungeon.difficulty_modifier,
    )
    damage = 0 if passed else fail_damage
    shielded_by = None
    if passed:
        damage_report = []
        message = f"{best_name} замечает ловушку и обезвреживает её!"
    elif shield:
        damage = _shielded_damage(fail_damage, shield["block"])
        damage_report = await _damage_party([shield["character_id"]], damage)
        shielded_by = await _character_name(shield["character_id"])
        message = f"Ловушка сработала! {shielded_by} принимает удар на щит. Урон: {damage}."
    else:
        damage_report = await _damage_party(_alive_ids(session_obj), fail_damage)
        message = f"Ловушка сработала! Урон: {fail_damage}."
    if dark and not passed:
        message += " Во тьме удар сильнее."
    event = {
        "type": "trap_triggered", "source": source, "passed": passed,
        "stat_check": stat_check, "difficulty": difficulty,
        "best_character": best_name, "best_value": best_value,
        "damage": damage, "damage_report": damage_report, "shielded_by": shielded_by,
        "message": message,
    }
    await ws_manager.broadcast_to_session(session_obj.id, {"type": "trap_triggered", "data": event})
    return event


async def _enter_room(
    db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon, room: DungeonRoom, depth: int = 0,
    teleported_from: Optional[int] = None,
) -> Optional[dict]:
    """Move the party into `room` (no stamina) and run its entry effects.
    Used for corridor-battle continuation, teleports and event teleports.
    Returns the room_event dict (or None). Caller commits."""
    session_obj.current_room_id = room.id
    await session_state.delete_torch(session_obj.id)
    await _record_visit(db, session_obj.dungeon_id, _member_ids(session_obj), room.id)
    rs = await _get_room_state(db, session_obj.id, room.id)
    await session_state.update_session_state(session_obj.id, current_room_id=room.id, phase=PHASE_EXPLORING)
    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "room_entered",
        "data": {"room": {"id": room.id, "room_type": room.room_type, "name": room.name,
                          "description": room.description}, "corridor_event": None},
    })
    if rs.is_cleared:
        return await _hidden_drops(db, session_obj, dungeon, room, depth)
    cfg = room.room_config if isinstance(room.room_config, dict) else {}
    if room.room_type in ("battle", "boss"):
        try:
            battle_id, names = await start_battle(db, session_obj, dungeon, cfg.get("mob_template_ids") or [], room=room)
            return {"type": "battle_started", "battle_id": battle_id, "room_type": room.room_type,
                    "mob_names": names}
        except HTTPException as e:
            await session_state.set_phase(session_obj.id, PHASE_BATTLE_PENDING)
            return {"type": "battle_error", "message": str(e.detail), "can_retry": True}
    if room.room_type == "trap":
        event = await _apply_trap(db, session_obj, dungeon, cfg, default_damage=20, source="room",
                                  dark=await _in_darkness(session_obj, room, rs))
        rs.is_cleared = True
        rs.extra_data = {**(rs.extra_data or {}), "trap": {"passed": event["passed"], "damage": event["damage"]}}
        return event
    if room.room_type == "teleport" and _portal_kind(room.room_type, cfg) == PORTAL_RED:
        # A blue portal waits for the party to step in; a red one springs on arrival.
        return await _red_portal(db, session_obj, dungeon, room, rs, depth)
    return await _hidden_drops(db, session_obj, dungeon, room, depth)


async def _hidden_drops(db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon, room: DungeonRoom,
                        depth: int) -> Optional[dict]:
    """The party is in `room`: a hidden drop in its floor not yet found makes
    the best of it roll. Spotted — the drop becomes a way down to take at will.
    Missed — the party falls through to the floor below and takes damage.
    Found either way, it never springs again this run."""
    drops = (await db.execute(select(DungeonCorridor).where(
        DungeonCorridor.dungeon_id == session_obj.dungeon_id,
        DungeonCorridor.from_room_id == room.id,
        DungeonCorridor.passage_type == "drop",
    ))).scalars().all()
    drop = next((c for c in drops if _hidden_drop(c) is not None and _is_shut_passage(session_obj, c)), None)
    if drop is None or depth >= MAX_TELEPORT_CHAIN:
        return None
    trap = _hidden_drop(drop)
    state = {"members": {str(m.character_id): {"status": m.status} for m in session_obj.members}}
    passed, best_name, best_value = await perform_stat_check(
        state, trap["stat_check"], trap["difficulty"], dungeon.difficulty_modifier,
    )
    _open_corridor(session_obj, drop)
    roll = {"stat_check": trap["stat_check"], "difficulty": trap["difficulty"], "best_character": best_name,
            "best_value": best_value, "passed": passed}
    if passed:
        return {"type": "drop_spotted", **roll,
                "message": f"{best_name} замечает провал в полу — теперь вниз можно спуститься осторожно."}
    target = await _get_room(db, drop.to_room_id)
    if target is None:
        return None
    damage_report = await _damage_party(_alive_ids(session_obj), trap["fail_damage"])
    follow = await _enter_room(db, session_obj, dungeon, target, depth + 1)
    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "room_entered",
        "data": {"room": {"id": target.id, "room_type": target.room_type, "name": target.name,
                          "description": target.description},
                 "teleported": True, "message": f"Пол проваливается! Группа падает в «{target.name}»"},
    })
    return {"type": "teleported", "fell": True, **roll, "damage": trap["fail_damage"], "damage_report": damage_report,
            "target_room_id": target.id, "target_room_name": target.name, "teleported_from": room.id,
            "followup": follow,
            "message": f"Пол проваливается! Группа падает этажом ниже, в «{target.name}». Урон: {trap['fail_damage']}."}


async def _red_portal(db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon, room: DungeonRoom,
                      rs: DungeonRoomState, depth: int) -> Optional[dict]:
    """The party walked into a live red portal: the best of it rolls against
    the portal. Spotted — the portal is harmless from now on. Missed — the
    party is thrown into one of the portal's rooms at random (the portal stays
    live for the next walk-in)."""
    cfg = room.room_config if isinstance(room.room_config, dict) else {}
    stat_check = cfg.get("stat_check") or RED_PORTAL_DEFAULT_STAT
    difficulty = int(cfg.get("difficulty") or RED_PORTAL_DEFAULT_DIFFICULTY)
    state = {"members": {str(m.character_id): {"status": m.status} for m in session_obj.members}}
    passed, best_name, best_value = await perform_stat_check(
        state, stat_check, difficulty, dungeon.difficulty_modifier,
    )
    roll = {"stat_check": stat_check, "difficulty": difficulty, "best_character": best_name,
            "best_value": best_value, "passed": passed}
    rs.extra_data = {**(rs.extra_data or {}), "portal": {"passed": passed}}
    if passed:
        rs.is_cleared = True
        return {"type": "portal_spotted", **roll,
                "message": f"{best_name} распознаёт ловушку: красный портал больше не опасен."}
    targets = [t for t in (cfg.get("target_room_ids") or [])
               if isinstance(t, int) and not isinstance(t, bool) and t != room.id]
    if not targets:
        return {"type": "portal_spotted", **roll, "passed": False,
                "message": "Портал вспыхивает красным, но тут же гаснет — его магия никуда не ведёт."}
    event = await _teleport(db, session_obj, dungeon, room, None, random.choice(targets), depth)
    if event and event.get("type") == "teleported":
        event.update(roll)
        event["red_portal"] = True
        event["message"] = f"Красный портал затягивает группу! Вас выбросило в «{event['target_room_name']}»."
    return event


async def _teleport(db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon, from_room: DungeonRoom,
                    from_state: Optional[DungeonRoomState], target_room_id, depth: int) -> Optional[dict]:
    """Teleport the party to a room of the SAME dungeon. An invalid target is
    ignored (the room acts as an empty one) instead of crashing."""
    if from_state is not None:
        from_state.is_cleared = True
    target = await _get_room(db, target_room_id) if isinstance(target_room_id, int) else None
    if target is None or target.dungeon_id != session_obj.dungeon_id or target.id == from_room.id:
        logger.warning("Сессия %d: телепорт из комнаты %d в недопустимую комнату %s",
                       session_obj.id, from_room.id, target_room_id)
        return {"type": "teleport_failed", "message": "Телепорт молчит — магия здесь иссякла."}
    if depth >= MAX_TELEPORT_CHAIN:
        return {"type": "teleport_failed", "message": "Телепорт молчит — магия здесь иссякла."}
    follow = await _enter_room(db, session_obj, dungeon, target, depth + 1, teleported_from=from_room.id)
    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "room_entered",
        "data": {"room": {"id": target.id, "room_type": target.room_type, "name": target.name,
                          "description": target.description},
                 "teleported": True, "message": f"Телепорт! Группа перенесена в «{target.name}»"},
    })
    return {"type": "teleported", "target_room_id": target.id, "target_room_name": target.name,
            "teleported_from": from_room.id, "followup": follow}


# =====================================================================
# Room Movement
# =====================================================================

async def move_to_room(
    db: AsyncSession,
    session_id: int,
    character_id: int,
    corridor_id: int,
    auth_token: Optional[str] = None,  # kept for signature compatibility; unused
) -> MoveResponse:
    try:
        return await _move_to_room(db, session_id, character_id, corridor_id)
    except Exception:
        await db.rollback()
        raise


async def _move_to_room(
    db: AsyncSession,
    session_id: int,
    character_id: int,
    corridor_id: int,
) -> MoveResponse:
    """
    Move the party through a corridor. Leader only.

    Order (stamina is refunded if a battle cannot start):
    1. validate (session, leader, phase, corridor, stamina of every member),
       then spend stamina — before any battle exists, so a failed spend never
       leaves a started battle behind;
    2. corridor ambush roll -> start the corridor battle (fail = refund + error);
    3. corridor trap roll -> damage;
    4. target is an uncleared battle/boss room -> start its battle BEFORE the
       party walks in (fail = refund + error, party stays put, retryable);
    5. move, record visits, room entry effects (trap/teleport).
    """
    session_obj = await _get_session(db, session_id, lock=True)
    if session_obj.status != STATUS_ACTIVE:
        raise HTTPException(status_code=400, detail="Сессия подземелья не активна")
    await _require_leader(db, session_obj, character_id, "перемещать группу")
    redis_state = await _require_state(db, session_obj)

    phase = redis_state.get("phase", "")
    current_room_id = session_obj.current_room_id
    if phase not in (PHASE_EXPLORING, PHASE_BATTLE_PENDING):
        raise HTTPException(status_code=400, detail="Перемещение возможно только в фазе исследования")
    await _require_party_ready(session_obj)

    corridor = (await db.execute(select(DungeonCorridor).where(DungeonCorridor.id == corridor_id))).scalar_one_or_none()
    if not corridor or corridor.dungeon_id != session_obj.dungeon_id:
        raise HTTPException(status_code=404, detail="Коридор не найден")
    if corridor.from_room_id == current_room_id:
        target_room_id = corridor.to_room_id
    elif corridor.to_room_id == current_room_id and corridor.is_bidirectional:
        target_room_id = corridor.from_room_id
    else:
        raise HTTPException(status_code=400, detail="Этот коридор недоступен из текущей комнаты")

    # A locked door: a key of its kind opens it for the rest of the run; otherwise it stays shut.
    # From behind the lock it is simply unbolted (and stays open too).
    lock = _corridor_lock(corridor)
    if lock and _is_shut(session_obj, corridor):
        behind = _bolt_side(corridor, current_room_id)
        if not behind and (lock["key"] is None or lock["key"] not in _session_keys(session_obj)):
            raise HTTPException(status_code=409, detail=_door_refusal(lock))
        _open_corridor(session_obj, corridor)
    if _hidden_way(session_obj, corridor) and current_room_id == corridor.from_room_id:
        raise HTTPException(status_code=400, detail="Этот коридор недоступен из текущей комнаты")
    gate = _gate_down(session_obj, corridor)
    if gate:
        raise HTTPException(status_code=409, detail=f"Путь преграждает {GATE_NOUNS[gate['look']][0]} — "
                                                    f"её нужно поднять и подпереть.")
    if _seal_on(session_obj, corridor):
        raise HTTPException(status_code=409, detail="Проход запечатан магической печатью — её нужно снять.")

    if phase == PHASE_BATTLE_PENDING:
        # An uncleared battle room: retreat only to rooms the party already knows.
        visited = await _visited_room_ids(db, session_obj.dungeon_id, character_id)
        if target_room_id not in visited:
            raise HTTPException(
                status_code=409,
                detail="Путь преграждают враги: начните бой или отступите в исследованную комнату",
            )

    dungeon = await _get_dungeon_for_session(db, session_obj.dungeon_id)
    target_room = await _get_room(db, target_room_id)
    if target_room is None:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    target_state = (await db.execute(select(DungeonRoomState).where(
        DungeonRoomState.session_id == session_id, DungeonRoomState.room_id == target_room_id,
    ))).scalar_one_or_none()
    target_cleared = bool(target_state and target_state.is_cleared)
    target_cfg = target_room.room_config if isinstance(target_room.room_config, dict) else {}
    needs_room_battle = target_room.room_type in ("battle", "boss") and not target_cleared
    if needs_room_battle and not target_cfg.get("mob_template_ids"):
        raise HTTPException(
            status_code=409,
            detail="Комната боя не настроена — нет мобов. Сообщите администратору.",
        )

    dead_count = sum(1 for m in session_obj.members if m.status == "dead")
    final_cost = math.ceil(
        corridor.stamina_cost * (dungeon.stamina_multiplier or 1.0) * (1 + 0.25 * dead_count)
    )
    alive_ids = _alive_ids(session_obj)
    if not alive_ids:
        raise HTTPException(status_code=400, detail="В группе нет живых участников")
    for cid in alive_ids:
        try:
            attrs = await http_clients.get_character_attributes(cid)
        except Exception:
            raise HTTPException(status_code=502, detail=f"Не удалось проверить стамину персонажа #{cid}")
        current_stamina = attrs.get("current_stamina", 0)
        if current_stamina < final_cost:
            raise HTTPException(
                status_code=400,
                detail=f"Недостаточно стамины у {await _character_name(cid)} "
                       f"(нужно {final_cost}, имеется {current_stamina})",
            )

    # The party shield raised in this room meets whatever waits on the way, then is lowered.
    shield = await _raised_shield(session_obj)
    # Leaving an unlit dark room, the way's traps strike harder.
    here_room = await _get_room(db, current_room_id)
    here_state = (await db.execute(select(DungeonRoomState).where(
        DungeonRoomState.session_id == session_id, DungeonRoomState.room_id == current_room_id,
    ))).scalar_one_or_none()
    leaving_dark = await _in_darkness(session_obj, here_room, here_state)
    paid: List[int] = []

    async def _refund_stamina():
        for cid in paid:
            try:
                await http_clients.recover_character(cid, stamina=final_cost)
            except HTTPException:
                logger.warning("Сессия %d: не удалось вернуть стамину персонажу %d", session_id, cid)

    # Stamina goes first: a battle that has started can't be taken back, but
    # stamina can — if the battle then fails to start, everyone is refunded.
    for cid in alive_ids:
        try:
            ok = await http_clients.consume_stamina(cid, final_cost)
        except HTTPException:
            await _refund_stamina()
            raise
        if not ok:
            await _refund_stamina()
            raise HTTPException(status_code=400, detail=f"Не удалось списать стамину у персонажа #{cid}")
        paid.append(cid)

    async def _start_or_refund(*args, **kwargs):
        try:
            return await start_battle(*args, **kwargs)
        except Exception:
            await _refund_stamina()
            raise

    _touch(session_obj)
    here = await _get_room(db, current_room_id)
    await chat.log(session_id, f"Отряд идёт из «{here.name if here else '?'}» в «{target_room.name}».")

    # A scout who was seen put the corridor on its guard (once); a disarmed trap stays quiet.
    intel = await session_state.get_intel(session_id)
    alerted = corridor.id in intel["alerted"]
    ambush_chance = (corridor.random_battle_chance or 0)
    if alerted and corridor.random_battle_mob_ids:
        ambush_chance = min(1.0, ambush_chance + ALERT_AMBUSH_BONUS)
        intel["alerted"] = [c for c in intel["alerted"] if c != corridor.id]
        await session_state.set_intel(session_id, intel)
    trap_disarmed = corridor.id in intel["disarmed"]

    # 2. Corridor ambush: its first blow lands before the fight (on the shield, if one is up)
    if ambush_chance > 0 and random.random() < ambush_chance:
        strike, strike_message = await _opening_strike(session_obj, shield)
        try:
            battle_id, names = await _start_or_refund(
                db, session_obj, dungeon, corridor.random_battle_mob_ids or [],
                corridor_id=corridor.id, pending_target_room_id=target_room_id,
            )
        except Exception:
            await _undo_damage(session_id, strike)
            raise
        await db.commit()
        await session_state.delete_shield(session_id)
        await session_state.delete_torch(session_id)
        await chat.log(session_id, f"По дороге в «{target_room.name}» на отряд напали! {strike_message} "
                                   f"{await chat._damage_line(strike)}".strip(), chat.TONE_BAD)
        details = {"battle_id": battle_id, "mob_ids": corridor.random_battle_mob_ids or [],
                   "mob_names": names, "target_room_id": target_room_id,
                   "damage_report": strike, "shielded_by": await _character_name(shield["character_id"])
                   if shield else None}
        return MoveResponse(
            corridor_event=CorridorEventResponse(
                type="battle", details=details, message=f"В коридоре на вас напали враги! {strike_message}",
                battle_id=battle_id, mob_names=names,
            ),
            new_room=None,
            stamina_consumed=final_cost,
            room_event={"type": "battle_started", "battle_id": battle_id, "mob_names": names},
        )

    # 3. Corridor trap
    corridor_event: Optional[CorridorEventResponse] = None
    if not trap_disarmed and (corridor.trap_chance or 0) > 0 and random.random() < corridor.trap_chance:
        trap = await _apply_trap(db, session_obj, dungeon,
                                 corridor.trap_config if isinstance(corridor.trap_config, dict) else {},
                                 default_damage=15, source="corridor", shield=shield, dark=leaving_dark)
        corridor_event = CorridorEventResponse(
            type="trap", details=trap, message=trap["message"],
            stat_check=trap["stat_check"], difficulty=trap["difficulty"],
            best_character=trap["best_character"], best_value=trap["best_value"],
            passed=trap["passed"], damage=trap["damage"],
        )

    # 4. Room battle starts before the party walks in
    room_event = None
    if needs_room_battle:
        try:
            battle_id, names = await _start_or_refund(db, session_obj, dungeon, target_cfg["mob_template_ids"],
                                                      room=target_room)
        except Exception:
            # Nothing of the move stands, so neither does the trap: a retried move must not hurt twice.
            if corridor_event is not None and corridor_event.details:
                await _undo_damage(session_id, corridor_event.details.get("damage_report") or [])
            raise
        room_event = {"type": "battle_started", "battle_id": battle_id,
                      "room_type": target_room.room_type, "mob_names": names}

    # 5. Move (a torch stays behind)
    session_obj.current_room_id = target_room_id
    await session_state.delete_torch(session_id)
    await _record_visit(db, session_obj.dungeon_id, _member_ids(session_obj), target_room_id)
    room_state_obj = await _get_room_state(db, session_id, target_room_id)
    await session_state.update_session_state(
        session_id, current_room_id=target_room_id,
        **({} if needs_room_battle else {"phase": PHASE_EXPLORING}),
    )
    red_portal = _portal_kind(target_room.room_type, target_cfg) == PORTAL_RED
    if not needs_room_battle and not room_state_obj.is_cleared and (target_room.room_type == "trap" or red_portal):
        if target_room.room_type == "trap":
            room_event = await _apply_trap(db, session_obj, dungeon, target_cfg, default_damage=20, source="room",
                                           shield=shield,
                                           dark=await _in_darkness(session_obj, target_room, room_state_obj))
            room_state_obj.is_cleared = True
            room_state_obj.extra_data = {**(room_state_obj.extra_data or {}),
                                         "trap": {"passed": room_event["passed"], "damage": room_event["damage"]}}
        else:
            room_event = await _red_portal(db, session_obj, dungeon, target_room, room_state_obj, 0)
    if room_event is None and not needs_room_battle:
        room_event = await _hidden_drops(db, session_obj, dungeon, target_room, 0)
    await db.commit()
    await session_state.delete_shield(session_id)

    if corridor_event is None:
        corridor_event = CorridorEventResponse(type="safe", details={}, message="Переход прошёл без происшествий.")

    final_room = await _get_room(db, session_obj.current_room_id)
    final_state = await _get_room_state(db, session_id, final_room.id)
    new_room_view = await _room_view(db, final_room, final_state, session_obj, character_id, dungeon)
    from_room = await _get_room(db, current_room_id)
    await ws_manager.broadcast_to_session(session_id, {
        "type": "room_entered",
        "data": {
            "from_room_name": from_room.name if from_room else None,
            "room": new_room_view.dict(),
            "corridor_event": corridor_event.dict(),
            "room_event": room_event,
            "stamina_consumed": final_cost,
        },
    })
    return MoveResponse(
        corridor_event=corridor_event,
        new_room=new_room_view,
        stamina_consumed=final_cost,
        room_event=room_event,
    )


async def pick_lock(db: AsyncSession, session_id: int, character_id: int, corridor_id: int) -> PickLockResponse:
    """Pick a lock with a plain roll (any living member, with their own agility
    and stamina). The minigame is `start_challenge` with mode "game"."""
    started = await start_challenge(db, session_id, character_id, challenges.KIND_LOCKPICK, corridor_id, "roll")
    res = started.result
    return PickLockResponse(passed=res.passed, message=res.message, stat_check="agility",
                            difficulty=res.difficulty or 0, best_character=await _character_name(character_id),
                            best_value=res.rolled or 0, stamina_consumed=started.stamina_consumed)


# =====================================================================
# Class challenges: minigames and plain rolls (FEAT-176)
# =====================================================================
# A member tries something of a class's craft — a lock, a secret way. They pay the
# stamina; their own stat sets how hard it is; someone of another class may
# try too, at a disadvantage. One member works on a target at a time; the
# others see who and how it went.

CHALLENGE_GRACE_SECONDS = 60
# How each challenge ended, by kind: the game's endings and a plain roll's.
CHALLENGE_MESSAGES = {
    challenges.KIND_LOCKPICK: {
        "open": "{name} вскрывает замок — дверь открыта!",
        "broke": "У {name} ломается отмычка — замок не поддался.",
        "time": "{name} не успевает — замок так и не поддался.",
        "short": "{name} бросает возиться с замком.",
        "rolled_ok": "{name} вскрывает замок — дверь открыта!",
        "rolled_fail": "Замок не поддаётся {name}. Можно попробовать ещё раз.",
    },
    challenges.KIND_MECHANISM: {
        "open": "{name} нащупывает скрытый рычаг — в стене открывается тайный проход!",
        "broke": "{name} так и не находит механизм.",
        "time": "{name} так и не находит механизм.",
        "short": "{name} бросает поиски механизма.",
        "rolled_ok": "{name} находит скрытый механизм — в стене открывается тайный проход!",
        "rolled_fail": "{name} не находит механизма. Можно поискать ещё.",
    },
    challenges.KIND_ILLUSION: {
        "open": "{name} рассеивает иллюзию — за ней тайный проход!",
        "broke": "Руны сбиваются — иллюзия держится.",
        "time": "{name} не успевает — иллюзия держится.",
        "short": "{name} отступает от иллюзорной стены.",
        "rolled_ok": "{name} видит сквозь иллюзию — за ней тайный проход!",
        "rolled_fail": "Иллюзия не поддаётся {name}.",
    },
    challenges.KIND_RUBBLE: {
        "open": "{name} разбирает завал — путь свободен!",
        "broke": "Завал обрушивается на {name}!",
        "time": "{name} бросает разбирать завал.",
        "short": "{name} бросает разбирать завал.",
        "rolled_ok": "{name} разбирает завал — путь свободен!",
        "rolled_fail": "Завал осыпается на {name}.",
    },
    challenges.KIND_GATE: {
        "open": "{name} поднимает {what_acc} и подпирает её — путь открыт!",
        "broke": "{What} срывается вниз и бьёт {name}!",
        "time": "{name} выбивается из сил — {what} опускается.",
        "short": "{name} отпускает {what_acc}.",
        "rolled_ok": "{name} поднимает {what_acc} и подпирает её — путь открыт!",
        "rolled_fail": "{What} выскальзывает из рук {name} и падает.",
    },
    challenges.KIND_SEAL: {
        "open": "{name} проводит знак до конца — печать рассыпается искрами, проход открыт!",
        "broke": "Печать бьёт в ответ — {name} отлетает назад!",
        "time": "{name} не успевает — печать держится.",
        "short": "{name} отступает от печати.",
        "rolled_ok": "{name} снимает печать — проход открыт!",
        "rolled_fail": "Печать бьёт в ответ — {name} отлетает назад!",
    },
}
# Looking ahead (FEAT-176): scouting, disarming, reading.
SCOUT_DIFFICULTY = 12
SCOUT_COST = 2
SCOUT_SEEN_DAMAGE = 8
# A scout who was seen: the corridor's ambush chance goes up this much for the next crossing.
ALERT_AMBUSH_BONUS = 0.3
DISARM_DIFFICULTY = 12
DISARM_COST = 2
DISARM_FAIL_DAMAGE = 12
INSIGHT_DIFFICULTY = 12
INSIGHT_COST = 2
INTEL_KINDS = (challenges.KIND_SCOUT, challenges.KIND_DISARM, challenges.KIND_INSIGHT)
ROOM_KIND_NAMES = {
    "battle": "бой", "boss": "логово босса", "treasure": "сокровищница", "trap": "комната-ловушка", "event": "событие",
    "rest": "привал", "merchant": "торговец", "teleport": "портал", "fork": "развилка", "deadend": "тупик",
}

# Hurts whoever was at it when it went wrong.
DAMAGING_KINDS = (challenges.KIND_RUBBLE, challenges.KIND_GATE, challenges.KIND_SEAL)

# The party shield (FEAT-176): raised in a room, it meets the next trap or
# ambush on the way out — the one holding it takes the blow alone, softened.
SHIELD_DIFFICULTY = 12
SHIELD_COST = 2
# A shield held perfectly takes off this share of the blow.
SHIELD_ABSORB = 0.75
# A plain roll: how firmly it is held, rolled well or badly.
SHIELD_ROLL_BLOCK_OK = 0.8
SHIELD_ROLL_BLOCK_FAIL = 0.3
# Held at least this firmly counts as a success.
SHIELD_GOOD_BLOCK = 0.5
# An ambush's first blow, before the fight: on everyone, or on the shield.
AMBUSH_STRIKE_DAMAGE = 10
SHIELD_TARGET = "shield"


def _shielded_damage(damage: int, block: float) -> int:
    return math.ceil(damage * (1 - SHIELD_ABSORB * max(0.0, min(1.0, block))))


# The editor's grid: one room slot every this many pixels (the 3D table's room cell).
EDITOR_CELL_PX = 180


async def _floor_extents(db: AsyncSession, dungeon_id: int) -> List[FloorExtent]:
    """Each floor's span in room cells, from every placed room (only the frame, nothing of what is where)."""
    rows = (await db.execute(select(DungeonRoom.floor, DungeonRoom.position_x, DungeonRoom.position_y).where(
        DungeonRoom.dungeon_id == dungeon_id,
        DungeonRoom.position_x.isnot(None), DungeonRoom.position_y.isnot(None),
    ))).all()
    spans: Dict[int, List[int]] = {}
    for floor, x, y in rows:
        col, row = round(x / EDITOR_CELL_PX), round(y / EDITOR_CELL_PX)
        f = int(floor or 1)
        span = spans.setdefault(f, [col, col, row, row])
        span[0], span[1] = min(span[0], col), max(span[1], col)
        span[2], span[3] = min(span[2], row), max(span[3], row)
    return [FloorExtent(floor=f, min_col=a, max_col=b, min_row=c, max_row=d) for f, (a, b, c, d) in sorted(spans.items())]


def _ambush_info(session_obj: DungeonSession, redis_state: Optional[dict], phase: str) -> Optional[AmbushInfo]:
    """A corridor ambush being fought: where the party was caught."""
    if phase != PHASE_IN_BATTLE:
        return None
    _, target, corridor_id = _battle_of(session_obj, redis_state)
    if not corridor_id or not target or session_obj.current_room_id is None:
        return None
    return AmbushInfo(corridor_id=corridor_id, from_room_id=session_obj.current_room_id, to_room_id=target)


async def _raised_shield(session_obj: DungeonSession) -> Optional[dict]:
    """The shield raised in the room the party is in, held by someone alive."""
    shield = await session_state.get_shield(session_obj.id)
    if not shield or shield.get("room_id") != session_obj.current_room_id:
        return None
    if shield.get("character_id") not in _alive_ids(session_obj):
        return None
    return shield


async def _shield_info(session_obj: DungeonSession) -> Optional[ShieldInfo]:
    shield = await _raised_shield(session_obj)
    return ShieldInfo(character_id=shield["character_id"], block=shield["block"]) if shield else None


async def _opening_strike(session_obj: DungeonSession, shield: Optional[dict]) -> Tuple[List[dict], str]:
    """An ambush's first blow: (who took how much, what to tell the party)."""
    if shield:
        damage = _shielded_damage(AMBUSH_STRIKE_DAMAGE, shield["block"])
        report = await _damage_party([shield["character_id"]], damage)
        return report, f"{await _character_name(shield['character_id'])} принимает первый удар на щит. Урон: {damage}."
    report = await _damage_party(_alive_ids(session_obj), AMBUSH_STRIKE_DAMAGE)
    return report, f"Первый удар достаётся всем. Урон: {AMBUSH_STRIKE_DAMAGE}."


async def _undo_damage(session_id: int, report: List[dict]) -> None:
    """The fight could not start after all: give back what its first blow took."""
    for r in report:
        if r.get("damage"):
            try:
                await http_clients.recover_character(r["character_id"], health=r["damage"])
            except Exception:
                logger.warning("Сессия %d: не удалось вернуть здоровье персонажу %d", session_id, r["character_id"])


# Searching a room (FEAT-176): one search a room in a run. A stash set in the
# editor is found by the search; any search may also turn up a random find.
SEARCH_DIFFICULTY = 12
SEARCH_COST = 2
SEARCH_RANDOM_CHANCE = 0.05
# Standing watch at a rest: a plain roll; the watch meets a night raid.
WATCH_DIFFICULTY = 12
WATCH_COST = 1
WATCH_TARGET = "watch"


def _room_stash(room: DungeonRoom) -> Optional[dict]:
    cfg = room.room_config if isinstance(room.room_config, dict) else {}
    stash = cfg.get("stash")
    if not isinstance(stash, dict) or not stash.get("items"):
        return None
    return stash


async def _grant_loot(db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon, room: DungeonRoom,
                      entries: list, source: str) -> List[dict]:
    """Roll each {item_id, quantity, chance} and put what comes up in the group inventory."""
    gained = []
    cache: Dict[int, Optional[str]] = {}
    for e in entries:
        if not isinstance(e, dict) or not e.get("item_id"):
            continue
        chance = min(float(e.get("chance", 1.0)) * (dungeon.loot_multiplier or 1.0)
                     * _floor_factor(dungeon.floor_loot_step, _room_floor(room)), 1.0)
        if random.random() < chance:
            quantity = int(e.get("quantity", 1) or 1)
            await _add_to_group_inventory(db, session_obj.id, e["item_id"], quantity, source)
            gained.append({"item_id": e["item_id"], "item_name": await _item_name(e["item_id"], cache),
                           "quantity": quantity})
    return gained


def _loot_names(loot: List[dict]) -> str:
    return ", ".join(f"{i['item_name'] or 'предмет #%d' % i['item_id']}"
                     + (f" ×{i['quantity']}" if i["quantity"] > 1 else "") for i in loot)


def _scout_key(corridor_id: int, room_id: int) -> str:
    """Scouting looks one way: down the corridor towards this room (the far end is another room each way)."""
    return f"{corridor_id}>{room_id}"


def _trap_found(intel: dict, corridor_id: int) -> bool:
    """A scout has found the corridor's trap, from either end."""
    prefix = f"{corridor_id}>"
    return any(k.startswith(prefix) and v.get("trap") for k, v in intel.get("scouted", {}).items())


def _scout_info(intel: dict, corridor_id: int, room_id: int) -> Optional[ScoutInfo]:
    info = intel.get("scouted", {}).get(_scout_key(corridor_id, room_id))
    if not info:
        return None
    return ScoutInfo(**info, disarmed=corridor_id in intel.get("disarmed", []))


async def _corridor_from_here(db: AsyncSession, session_obj: DungeonSession, corridor_id: Optional[int]) -> Tuple[DungeonCorridor, int]:
    """A corridor out of the current room, and the room at its other end."""
    if corridor_id is None:
        raise HTTPException(status_code=400, detail="Укажите проход")
    corridor = (await db.execute(select(DungeonCorridor).where(DungeonCorridor.id == corridor_id))).scalar_one_or_none()
    here = session_obj.current_room_id
    if not corridor or corridor.dungeon_id != session_obj.dungeon_id:
        raise HTTPException(status_code=404, detail="Коридор не найден")
    if corridor.from_room_id == here and not _hidden_way(session_obj, corridor):
        return corridor, corridor.to_room_id
    if corridor.to_room_id == here and corridor.is_bidirectional:
        return corridor, corridor.from_room_id
    raise HTTPException(status_code=400, detail="Этот проход не ведёт из текущей комнаты")


async def _settle_intel(
    db: AsyncSession, session_obj: DungeonSession, kind: str, character_id: int, passed: bool, outcome: str,
    corridor: Optional[DungeonCorridor] = None, rolled: Optional[int] = None, difficulty: Optional[int] = None,
) -> ChallengeResult:
    """Scouting, disarming, reading: what the party learns (or what it costs)."""
    name = await _character_name(character_id)
    damage = 0
    intel = await session_state.get_intel(session_obj.id)
    if kind == challenges.KIND_SCOUT:
        target_id = corridor.to_room_id if corridor.from_room_id == session_obj.current_room_id else corridor.from_room_id
        target = await _get_room(db, target_id)
        if passed:
            ts = (await db.execute(select(DungeonRoomState).where(
                DungeonRoomState.session_id == session_obj.id, DungeonRoomState.room_id == target_id,
            ))).scalar_one_or_none()
            cleared = bool(ts and ts.is_cleared)
            info = {
                "room_type": target.room_type if target else "deadend",
                "room_name": target.name if target else None,
                "mob_count": _mob_count(target) if target and target.room_type in ("battle", "boss") and not cleared else None,
                "trap": (corridor.trap_chance or 0) > 0,
                "ambush": (corridor.random_battle_chance or 0) > 0 and bool(corridor.random_battle_mob_ids),
            }
            intel["scouted"][_scout_key(corridor.id, target_id)] = info
            what = ROOM_KIND_NAMES.get(info["room_type"], "комната")
            extra = []
            if info["mob_count"]:
                extra.append(f"врагов: {info['mob_count']}")
            if info["trap"]:
                extra.append("в коридоре ловушка")
            if info["ambush"]:
                extra.append("в коридоре можно нарваться на засаду")
            message = f"{name} разведывает путь: впереди {what}" + (f" ({', '.join(extra)})" if extra else "") + "."
        else:
            if corridor.id not in intel["alerted"]:
                intel["alerted"].append(corridor.id)
            report = await _damage_party([character_id], SCOUT_SEEN_DAMAGE)
            damage = sum(r["damage"] for r in report)
            message = f"{name} замечают в коридоре — теперь там настороже."
        await session_state.set_intel(session_obj.id, intel)
    elif kind == challenges.KIND_DISARM:
        if passed:
            if corridor.id not in intel["disarmed"]:
                intel["disarmed"].append(corridor.id)
            await session_state.set_intel(session_obj.id, intel)
            message = f"{name} обезвреживает ловушку в коридоре."
        elif outcome == "short":
            # Left before touching a taut rod: the trap stays set, nobody is hurt.
            message = f"{name} бросает возиться с ловушкой — она всё ещё взведена."
        else:
            report = await _damage_party([character_id], DISARM_FAIL_DAMAGE)
            damage = sum(r["damage"] for r in report)
            message = f"Ловушка срабатывает в руках {name}."
    else:
        room = await _get_room(db, session_obj.current_room_id)
        rs = await _get_room_state(db, session_obj.id, room.id)
        if passed:
            rs.extra_data = {**(rs.extra_data if isinstance(rs.extra_data, dict) else {}), "insight": True}
            message = (f"{name} читает знаки события — видно, куда ведёт каждый выбор." if room.room_type == "event"
                       else f"{name} вглядывается в портал — видно, куда он ведёт.")
        else:
            message = f"{name} не может разобрать знаки."
    if damage:
        message += f" Урон: {damage}."
    _touch(session_obj)
    await db.commit()
    target_key = f"corridor:{corridor.id}" if corridor is not None else f"insight:{session_obj.current_room_id}"
    await session_state.release_target(session_obj.id, target_key)
    result = ChallengeResult(passed=passed, kind=kind, outcome=outcome, message=message,
                             corridor_id=corridor.id if corridor is not None else None, character_id=character_id,
                             rolled=rolled, difficulty=difficulty)
    await ws_manager.broadcast_to_session(session_obj.id, {"type": "challenge_finished", "data": result.dict()})
    return result


async def _settle_search(
    db: AsyncSession, session_obj: DungeonSession, character_id: int, found: bool, outcome: str,
    rolled: Optional[int] = None, difficulty: Optional[int] = None,
) -> ChallengeResult:
    """The room is searched: the stash (if found) and maybe a random find go to the party."""
    room = await _get_room(db, session_obj.current_room_id)
    dungeon = await _get_dungeon_for_session(db, session_obj.dungeon_id)
    rs = await _get_room_state(db, session_obj.id, room.id)
    rs.extra_data = {**(rs.extra_data if isinstance(rs.extra_data, dict) else {}), "searched": True}
    stash = _room_stash(room)
    found = found and stash is not None
    name = await _character_name(character_id)
    stash_loot = await _grant_loot(db, session_obj, dungeon, room, stash["items"], f"Тайник: {room.name}") \
        if found else []
    lucky: List[dict] = []
    extras = dungeon.search_loot if isinstance(dungeon.search_loot, list) else []
    if extras and random.random() < SEARCH_RANDOM_CHANCE:
        lucky = await _grant_loot(db, session_obj, dungeon, room, [random.choice(extras)], f"Находка: {room.name}")
    if found and stash_loot:
        message = f"{name} находит тайник: {_loot_names(stash_loot)}!"
    elif found:
        message = f"{name} находит тайник, но он пуст."
    else:
        message = f"{name} обыскивает комнату, но тайника не находит."
    if lucky:
        message += f" {'А ещё' if found else 'Зато'} под ногами попадается: {_loot_names(lucky)}."
    loot = stash_loot + lucky
    _touch(session_obj)
    await db.commit()
    await session_state.release_target(session_obj.id, f"room:{room.id}")
    if loot:
        await _sync_inventory_cache(db, session_obj.id)
        await ws_manager.broadcast_to_session(session_obj.id, {
            "type": "loot_added",
            "data": {"source": f"Обыск: {room.name}", "items": loot, "item_name": _loot_names(loot),
                     "message": message, "quiet": True},
        })
    result = ChallengeResult(passed=bool(loot) or found, kind=challenges.KIND_SEARCH, outcome=outcome,
                             message=message, character_id=character_id, rolled=rolled, difficulty=difficulty,
                             loot=loot or None)
    await ws_manager.broadcast_to_session(session_obj.id, {"type": "challenge_finished", "data": result.dict()})
    return result


async def _settle_watch(
    db: AsyncSession, session_obj: DungeonSession, character_id: int, passed: bool,
    rolled: Optional[int] = None, difficulty: Optional[int] = None,
) -> ChallengeResult:
    """Someone stands watch over the rest — alert, or nodding off."""
    room = await _get_room(db, session_obj.current_room_id)
    rs = await _get_room_state(db, session_obj.id, room.id)
    rs.extra_data = {**(rs.extra_data if isinstance(rs.extra_data, dict) else {}),
                     "watch": {"character_id": character_id, "passed": passed}}
    name = await _character_name(character_id)
    message = (f"{name} встаёт в дозор — и глаз не сомкнёт." if passed
               else f"{name} встаёт в дозор, но то и дело клюёт носом.")
    _touch(session_obj)
    await db.commit()
    await session_state.release_target(session_obj.id, WATCH_TARGET)
    result = ChallengeResult(passed=passed, kind=challenges.KIND_WATCH, outcome="rolled", message=message,
                             character_id=character_id, rolled=rolled, difficulty=difficulty)
    await ws_manager.broadcast_to_session(session_obj.id, {"type": "challenge_finished", "data": result.dict()})
    return result


async def light_room(db: AsyncSession, session_id: int, character_id: int) -> LightResponse:
    """Light a dark room: a mage's spell for the rest of the run, anyone else's
    torch until the party leaves (dearer in stamina)."""
    session_obj = await _get_session(db, session_id, lock=True)
    if session_obj.status != STATUS_ACTIVE:
        raise HTTPException(status_code=400, detail="Сессия подземелья не активна")
    member = _require_member(session_obj, character_id)
    if member.status != "alive":
        raise HTTPException(status_code=409, detail="Павшие не могут этого сделать")
    redis_state = await _require_state(db, session_obj)
    if redis_state.get("phase", "") not in (PHASE_EXPLORING, PHASE_RESTING):
        raise HTTPException(status_code=400, detail="Сейчас не до света")
    room = await _get_room(db, session_obj.current_room_id)
    rs = await _get_room_state(db, session_id, room.id, lock=True)
    if not await _in_darkness(session_obj, room, rs):
        raise HTTPException(status_code=400, detail="Здесь и так светло")
    try:
        class_id = (await http_clients.get_character_profile(character_id)).get("character_class_id")
    except Exception:
        class_id = None
    mage = class_id == challenges.CLASS_MAGE
    dungeon = await _get_dungeon_for_session(db, session_obj.dungeon_id)
    cost = math.ceil((LIGHT_SPELL_COST if mage else TORCH_COST) * (dungeon.stamina_multiplier or 1.0))
    await _pay_stamina(character_id, cost)
    name = await _character_name(character_id)
    if mage:
        rs.extra_data = {**(rs.extra_data if isinstance(rs.extra_data, dict) else {}), "lit": LIGHT_SPELL}
        message = f"{name} зажигает магический свет — тьма отступает до конца забега."
    else:
        await session_state.set_torch(session_id, room.id)
        message = f"{name} зажигает факел — пока отряд здесь, светло."
    _touch(session_obj)
    await db.commit()
    how = LIGHT_SPELL if mage else LIGHT_TORCH
    await ws_manager.broadcast_to_session(session_id, {
        "type": "room_lit",
        "data": {"character_id": character_id, "name": name, "how": how, "room_id": room.id, "message": message},
    })
    return LightResponse(how=how, message=message, stamina_consumed=cost)


async def _settle_shield(
    db: AsyncSession, session_obj: DungeonSession, character_id: int, block: float, outcome: str,
    parried: Optional[int] = None, blows: Optional[int] = None,
    rolled: Optional[int] = None, difficulty: Optional[int] = None,
) -> ChallengeResult:
    """The shield is up (as firmly as it came out) until the party moves on."""
    block = round(max(0.0, min(1.0, block)), 2)
    name = await _character_name(character_id)
    if block > 0:
        await session_state.set_shield(session_obj.id, {
            "character_id": character_id, "room_id": session_obj.current_room_id, "block": block,
        })
    if outcome == "rolled":
        message = (f"{name} крепко держит щит наготове." if block >= SHIELD_GOOD_BLOCK
                   else f"{name} держит щит неуверенно.")
    elif block > 0:
        message = f"{name} поднимает щит: отбито {parried} из {blows}."
    else:
        message = f"{name} не успевает закрыться щитом — ни один удар не отбит."
    if block > 0:
        message += f" Щит наготове до следующего перехода (удар слабее на {round(SHIELD_ABSORB * block * 100)}%)."
    _touch(session_obj)
    await db.commit()
    await session_state.release_target(session_obj.id, SHIELD_TARGET)
    result = ChallengeResult(passed=block >= SHIELD_GOOD_BLOCK, kind=challenges.KIND_SHIELD, outcome=outcome,
                             message=message, character_id=character_id, rolled=rolled, difficulty=difficulty,
                             block=block)
    await ws_manager.broadcast_to_session(session_obj.id, {"type": "challenge_finished", "data": result.dict()})
    return result


async def _lock_to_pick(db: AsyncSession, session_obj: DungeonSession, corridor_id: int) -> Tuple[DungeonCorridor, dict]:
    """A shut, pickable door out of the current room."""
    corridor = (await db.execute(select(DungeonCorridor).where(DungeonCorridor.id == corridor_id))).scalar_one_or_none()
    here = session_obj.current_room_id
    if not corridor or corridor.dungeon_id != session_obj.dungeon_id:
        raise HTTPException(status_code=404, detail="Коридор не найден")
    if not (corridor.from_room_id == here or (corridor.to_room_id == here and corridor.is_bidirectional)):
        raise HTTPException(status_code=400, detail="Эта дверь не ведёт из текущей комнаты")
    lock = _corridor_lock(corridor)
    if lock is None or not _is_shut(session_obj, corridor):
        raise HTTPException(status_code=400, detail="Эта дверь не заперта")
    if not lock["pickable"]:
        raise HTTPException(status_code=400, detail=f"Этот замок не взломать — {_lock_need(lock)}")
    return corridor, lock


async def _challenge_target(
    db: AsyncSession, session_obj: DungeonSession, kind: str, corridor_id: Optional[int],
) -> Tuple[Optional[DungeonCorridor], int, int, int]:
    """What the challenge is tried on: (corridor — none for the shield, difficulty,
    stamina cost, damage on failure)."""
    if kind == challenges.KIND_SHIELD:
        raised = await _raised_shield(session_obj)
        if raised:
            raise HTTPException(status_code=409,
                                detail=f"Щит уже поднят — его держит {await _character_name(raised['character_id'])}")
        return None, SHIELD_DIFFICULTY, SHIELD_COST, 0
    if kind == challenges.KIND_SCOUT:
        corridor, target_id = await _corridor_from_here(db, session_obj, corridor_id)
        intel = await session_state.get_intel(session_obj.id)
        if _scout_key(corridor.id, target_id) in intel["scouted"]:
            raise HTTPException(status_code=409, detail="Этот путь уже разведан")
        return corridor, SCOUT_DIFFICULTY, SCOUT_COST, 0
    if kind == challenges.KIND_DISARM:
        corridor, _ = await _corridor_from_here(db, session_obj, corridor_id)
        intel = await session_state.get_intel(session_obj.id)
        if not _trap_found(intel, corridor.id):
            raise HTTPException(status_code=400, detail="Ловушку сначала надо найти — разведайте путь")
        if corridor.id in intel["disarmed"]:
            raise HTTPException(status_code=409, detail="Эта ловушка уже обезврежена")
        return corridor, DISARM_DIFFICULTY, DISARM_COST, 0
    if kind == challenges.KIND_INSIGHT:
        room = await _get_room(db, session_obj.current_room_id)
        rs = await _get_room_state(db, session_obj.id, room.id)
        cfg = room.room_config if isinstance(room.room_config, dict) else {}
        readable = room.room_type == "event" or _portal_kind(room.room_type, cfg) == PORTAL_BLUE
        if not readable:
            raise HTTPException(status_code=400, detail="Здесь нечего распознавать")
        if room.room_type == "event" and rs.event_choice_index is not None:
            raise HTTPException(status_code=409, detail="Выбор уже сделан")
        if _read(rs):
            raise HTTPException(status_code=409, detail="Здесь уже всё распознано")
        return None, INSIGHT_DIFFICULTY, INSIGHT_COST, 0
    if kind in (challenges.KIND_SEARCH, challenges.KIND_WATCH):
        room = await _get_room(db, session_obj.current_room_id)
        rs = await _get_room_state(db, session_obj.id, room.id)
        extra = rs.extra_data if isinstance(rs.extra_data, dict) else {}
        if kind == challenges.KIND_WATCH:
            if room.room_type != "rest" or not extra.get("rest_started_at") or extra.get("rest_used"):
                raise HTTPException(status_code=400, detail="Дозор несут только на привале")
            if extra.get("watch"):
                raise HTTPException(status_code=409, detail="В дозоре уже кто-то стоит")
            return None, WATCH_DIFFICULTY, WATCH_COST, 0
        if extra.get("searched"):
            raise HTTPException(status_code=409, detail="Эту комнату уже обыскали")
        if await _in_darkness(session_obj, room, rs):
            raise HTTPException(status_code=409, detail="В темноте ничего не найти — сначала зажгите свет")
        stash = _room_stash(room)
        difficulty = int(stash["difficulty"]) if stash and stash.get("difficulty") is not None else SEARCH_DIFFICULTY
        return None, difficulty, SEARCH_COST, 0
    if corridor_id is None:
        raise HTTPException(status_code=400, detail="Укажите проход")
    if kind == challenges.KIND_LOCKPICK:
        corridor, lock = await _lock_to_pick(db, session_obj, corridor_id)
        return corridor, lock["difficulty"], lock["pick_cost"], 0
    corridor = (await db.execute(select(DungeonCorridor).where(DungeonCorridor.id == corridor_id))).scalar_one_or_none()
    if not corridor or corridor.dungeon_id != session_obj.dungeon_id:
        raise HTTPException(status_code=404, detail="Коридор не найден")
    if kind == challenges.KIND_SEAL:
        here = session_obj.current_room_id
        if not (corridor.from_room_id == here or (corridor.to_room_id == here and corridor.is_bidirectional)):
            raise HTTPException(status_code=400, detail="Этот проход не ведёт из текущей комнаты")
        seal = _seal(corridor)
        if seal is None:
            raise HTTPException(status_code=400, detail="Здесь нет печати")
        if not _seal_on(session_obj, corridor):
            raise HTTPException(status_code=400, detail="Печать уже снята")
        return corridor, seal["difficulty"], seal["cost"], seal["fail_damage"]
    if kind == challenges.KIND_GATE:
        here = session_obj.current_room_id
        if not (corridor.from_room_id == here or (corridor.to_room_id == here and corridor.is_bidirectional)):
            raise HTTPException(status_code=400, detail="Этот проход не ведёт из текущей комнаты")
        gate = _gate(corridor)
        if gate is None:
            raise HTTPException(status_code=400, detail="Здесь нечего подпирать")
        if not _gate_down(session_obj, corridor):
            raise HTTPException(status_code=400, detail="Проход уже открыт")
        return corridor, gate["difficulty"], gate["cost"], gate["fail_damage"]
    secret = _secret(corridor)
    if corridor.from_room_id != session_obj.current_room_id or secret is None or secret["kind"] != kind:
        raise HTTPException(status_code=400, detail="Здесь нет такого тайника")
    if not _is_shut_passage(session_obj, corridor):
        raise HTTPException(status_code=400, detail="Этот проход уже открыт")
    return corridor, secret["difficulty"], secret["cost"], secret["fail_damage"]


async def _challenger(character_id: int, kind: str) -> Tuple[int, bool]:
    """The member's stat for the challenge, and whether it is someone else's craft."""
    try:
        attrs = await http_clients.get_character_attributes(character_id)
    except Exception:
        raise HTTPException(status_code=502, detail="Не удалось получить характеристики персонажа")
    stat = challenges.KIND_STAT[kind]
    cumulative = attrs.get("cumulative_stats", {}) or {}
    value = cumulative.get(stat, attrs.get(stat, 0))
    try:
        class_id = (await http_clients.get_character_profile(character_id)).get("character_class_id")
    except Exception:
        class_id = None
    return int(value) if isinstance(value, (int, float)) else 0, class_id != challenges.KIND_CLASS[kind]


async def _pay_stamina(character_id: int, cost: int) -> None:
    try:
        attrs = await http_clients.get_character_attributes(character_id)
    except Exception:
        raise HTTPException(status_code=502, detail="Не удалось проверить стамину персонажа")
    if attrs.get("current_stamina", 0) < cost:
        raise HTTPException(status_code=400, detail=f"Недостаточно стамины у {await _character_name(character_id)} "
                                                    f"(нужно {cost}, имеется {attrs.get('current_stamina', 0)})")
    if not await http_clients.consume_stamina(character_id, cost):
        raise HTTPException(status_code=400, detail="Не удалось списать стамину")


async def _settle_challenge(
    db: AsyncSession, session_obj: DungeonSession, corridor: DungeonCorridor, kind: str, character_id: int,
    passed: bool, outcome: str, rolled: Optional[int] = None, difficulty: Optional[int] = None,
    fail_damage: int = 0,
) -> ChallengeResult:
    """Open the way (or not), hurt whoever brought a cave-in down, tell the party."""
    damage = 0
    if passed:
        _open_corridor(session_obj, corridor)
    elif kind in DAMAGING_KINDS and outcome in ("broke", "rolled") and fail_damage > 0:
        report = await _damage_party([character_id], fail_damage)
        damage = sum(r["damage"] for r in report)
    _touch(session_obj)
    await db.commit()
    await session_state.release_target(session_obj.id, f"corridor:{corridor.id}")
    name = await _character_name(character_id)
    key = outcome if outcome != "rolled" else ("rolled_ok" if passed else "rolled_fail")
    gate = _gate(corridor) if kind == challenges.KIND_GATE else None
    what, what_acc = GATE_NOUNS[gate["look"]] if gate else ("", "")
    message = CHALLENGE_MESSAGES[kind][key].format(name=name, what=what, what_acc=what_acc, What=what.capitalize())
    if damage:
        message += f" Урон: {damage}."
    result = ChallengeResult(passed=passed, kind=kind, outcome=outcome, message=message,
                             corridor_id=corridor.id, character_id=character_id, rolled=rolled, difficulty=difficulty)
    await ws_manager.broadcast_to_session(session_obj.id, {"type": "challenge_finished", "data": result.dict()})
    return result


async def start_challenge(
    db: AsyncSession, session_id: int, character_id: int, kind: str, corridor_id: int, mode: str,
) -> ChallengeStartResponse:
    """A member takes on a challenge: a minigame to play, or a plain roll decided at once."""
    if kind not in challenges.KIND_CLASS:
        raise HTTPException(status_code=400, detail="Неизвестное испытание")
    session_obj = await _get_session(db, session_id, lock=True)
    if session_obj.status != STATUS_ACTIVE:
        raise HTTPException(status_code=400, detail="Сессия подземелья не активна")
    member = _require_member(session_obj, character_id)
    if member.status != "alive":
        raise HTTPException(status_code=409, detail="Павшие не могут этого сделать")
    redis_state = await _require_state(db, session_obj)
    if kind in challenges.ROLL_ONLY_KINDS and mode != "roll":
        raise HTTPException(status_code=400, detail="Дозор — это бросок силы, без мини-игры")
    phase_needed = PHASE_RESTING if kind == challenges.KIND_WATCH else PHASE_EXPLORING
    if redis_state.get("phase", "") != phase_needed:
        raise HTTPException(status_code=400, detail="Дозор несут только на привале" if kind == challenges.KIND_WATCH
                            else "Это можно делать только в фазе исследования")
    corridor, base_difficulty, base_cost, fail_damage = await _challenge_target(db, session_obj, kind, corridor_id)

    dungeon = await _get_dungeon_for_session(db, session_obj.dungeon_id)
    difficulty = math.ceil(base_difficulty * (dungeon.difficulty_modifier or 1.0))
    target = (f"corridor:{corridor.id}" if corridor
              else f"insight:{session_obj.current_room_id}" if kind == challenges.KIND_INSIGHT
              else f"room:{session_obj.current_room_id}" if kind == challenges.KIND_SEARCH
              else WATCH_TARGET if kind == challenges.KIND_WATCH else SHIELD_TARGET)
    busy_with = await session_state.claim_target(session_id, target, character_id, CHALLENGE_GRACE_SECONDS)
    if busy_with is not None:
        raise HTTPException(status_code=409, detail=f"Этим уже занимается {await _character_name(busy_with)}")
    try:
        cost = math.ceil(base_cost * (dungeon.stamina_multiplier or 1.0))
        await _pay_stamina(character_id, cost)
        stat, off_class = await _challenger(character_id, kind)
        if mode == "roll" and kind in INTEL_KINDS:
            passed, total = challenges.roll(stat, difficulty, off_class)
            result = await _settle_intel(db, session_obj, kind, character_id, passed, "rolled", corridor=corridor,
                                         rolled=total, difficulty=difficulty)
            return ChallengeStartResponse(kind=kind, off_class=off_class, stamina_consumed=cost, result=result)
        if mode == "roll" and corridor is None:
            passed, total = challenges.roll(stat, difficulty, off_class)
            if kind == challenges.KIND_WATCH:
                result = await _settle_watch(db, session_obj, character_id, passed, rolled=total,
                                             difficulty=difficulty)
            elif kind == challenges.KIND_SEARCH:
                result = await _settle_search(db, session_obj, character_id, passed, "rolled", rolled=total,
                                              difficulty=difficulty)
            else:
                result = await _settle_shield(db, session_obj, character_id,
                                              SHIELD_ROLL_BLOCK_OK if passed else SHIELD_ROLL_BLOCK_FAIL, "rolled",
                                              rolled=total, difficulty=difficulty)
            return ChallengeStartResponse(kind=kind, off_class=off_class, stamina_consumed=cost, result=result)
        if mode == "roll":
            passed, total = challenges.roll(stat, difficulty, off_class)
            result = await _settle_challenge(db, session_obj, corridor, kind, character_id, passed, "rolled",
                                             rolled=total, difficulty=difficulty, fail_damage=fail_damage)
            return ChallengeStartResponse(kind=kind, off_class=off_class, stamina_consumed=cost, result=result)

        hidden = None
        if kind == challenges.KIND_LOCKPICK:
            params = challenges.lockpick_params(stat, difficulty, off_class)
        elif kind == challenges.KIND_ILLUSION:
            params = challenges.runes_params(stat, difficulty, off_class)
        elif kind == challenges.KIND_MECHANISM:
            params, hidden = challenges.mechanism_params(stat, difficulty, off_class)
        elif kind == challenges.KIND_SHIELD:
            params = challenges.shield_params(stat, difficulty, off_class)
        elif kind == challenges.KIND_SEAL:
            params, hidden = challenges.seal_params(stat, difficulty, off_class)
        elif kind == challenges.KIND_SCOUT:
            params = challenges.shadow_params(stat, difficulty, off_class)
        elif kind == challenges.KIND_DISARM:
            params, hidden = challenges.wires_params(stat, difficulty, off_class)
        elif kind == challenges.KIND_INSIGHT:
            params = challenges.stars_params(stat, difficulty, off_class)
        elif kind == challenges.KIND_SEARCH:
            room = await _get_room(db, session_obj.current_room_id)
            params, hidden = challenges.search_params(stat, difficulty, off_class, _room_stash(room) is not None)
        elif kind == challenges.KIND_GATE:
            params = {**challenges.gate_params(stat, difficulty, off_class), "look": _gate(corridor)["look"]}
        else:
            params, hidden = challenges.rubble_params(stat, difficulty, off_class)
        challenge_id = uuid.uuid4().hex
        ttl = params.get("time_limit_ms", 0) // 1000 + CHALLENGE_GRACE_SECONDS * 5
        await session_state.claim_target(session_id, target, character_id, ttl)
        left = await session_state.get_challenge(session_id, character_id)
        if left and left.get("target") and left["target"] != target:
            await session_state.release_target(session_id, left["target"], character_id)
        await session_state.set_challenge(session_id, character_id, {
            "id": challenge_id, "kind": kind, "corridor_id": corridor.id if corridor else None,
            "room_id": session_obj.current_room_id, "target": target,
            "params": params, "hidden": hidden,
            "difficulty": difficulty, "fail_damage": fail_damage, "issued_at": time.time() * 1000, "ttl": ttl,
        }, ttl)
        _touch(session_obj)
        await db.commit()
        await ws_manager.broadcast_to_session(session_id, {
            "type": "challenge_started",
            "data": {"character_id": character_id, "name": await _character_name(character_id), "kind": kind,
                     "corridor_id": corridor.id if corridor else None,
                     # how long to show "busy" if no word of the end ever comes (the game left to lapse)
                     "busy_ms": (params.get("time_limit_ms") or BUSY_UNTIMED_MS) + BUSY_GRACE_MS},
        })
        return ChallengeStartResponse(kind=kind, off_class=off_class, stamina_consumed=cost,
                                      challenge_id=challenge_id, params=params)
    except Exception:
        await session_state.release_target(session_id, target)
        raise


async def _load_challenge(session_id: int, character_id: int, challenge_id: str) -> dict:
    challenge = await session_state.get_challenge(session_id, character_id)
    if not challenge or challenge.get("id") != challenge_id:
        raise HTTPException(status_code=404, detail="Испытание не найдено — возможно, время вышло")
    return challenge


async def _locked_challenge(
    db: AsyncSession, session_id: int, character_id: int, challenge_id: str,
) -> Tuple[DungeonSession, dict]:
    """The session under its row lock, then the member's game read afresh: moves and endings of one
    game are taken one at a time (parallel requests can't each see a fresh copy of its secret).
    A game the party has walked away from (or a run that is over) is void."""
    session_obj = await _get_session(db, session_id, lock=True)
    _require_member(session_obj, character_id)
    challenge = await _load_challenge(session_id, character_id, challenge_id)
    began_in = challenge.get("room_id")
    if session_obj.status != STATUS_ACTIVE or (began_in is not None and began_in != session_obj.current_room_id):
        await _drop_challenge(session_id, character_id, challenge)
        await db.commit()
        raise HTTPException(status_code=409, detail="Отряд уже ушёл — испытание сорвалось")
    return session_obj, challenge


async def _drop_challenge(session_id: int, character_id: int, challenge: dict) -> None:
    """A game gone without a verdict: its door or room is free for someone else at once."""
    await session_state.delete_challenge(session_id, character_id)
    if challenge.get("target"):
        await session_state.release_target(session_id, challenge["target"], character_id)


async def _challenge_corridor(db: AsyncSession, session_id: int, challenge: dict) -> DungeonCorridor:
    corridor = (await db.execute(select(DungeonCorridor).where(
        DungeonCorridor.id == challenge["corridor_id"]))).scalar_one_or_none()
    if corridor is None:
        await session_state.release_target(session_id, f"corridor:{challenge['corridor_id']}")
        raise HTTPException(status_code=404, detail="Коридор не найден")
    return corridor


async def finish_challenge(
    db: AsyncSession, session_id: int, character_id: int, challenge_id: str, presses: List[int],
) -> ChallengeResult:
    """The member's game is over: replay what they did and settle it. For a game
    played move by move, this is giving up."""
    session_obj, challenge = await _locked_challenge(db, session_id, character_id, challenge_id)
    await session_state.delete_challenge(session_id, character_id)
    kind = challenge["kind"]
    params = challenge["params"]
    elapsed = time.time() * 1000 - challenge["issued_at"]
    # Nothing can have happened later than the time that has really passed.
    seen_until = elapsed + challenges.CLOCK_SLACK_MS
    if kind == challenges.KIND_SHIELD:
        parried, blows = (challenges.shield_verdict(params, presses, seen_until)
                          if challenges.shield_plausible(params, presses) else (0, len(params["blows"])))
        return await _settle_shield(db, session_obj, character_id, parried / blows, "game",
                                    parried=parried, blows=blows, difficulty=challenge.get("difficulty"))
    if kind == challenges.KIND_SEARCH:
        return await _settle_search(db, session_obj, character_id, False, "short",
                                    difficulty=challenge.get("difficulty"))
    if kind == challenges.KIND_INSIGHT:
        if challenges.stars_plausible(params, presses) and elapsed >= len(presses) * challenges.STARS_MIN_GAP_MS:
            passed, outcome = challenges.stars_verdict(params, presses)
            if not passed and elapsed >= params["time_limit_ms"]:
                outcome = "time"
        else:
            passed, outcome = False, "broke"
        return await _settle_intel(db, session_obj, kind, character_id, passed, outcome,
                                   difficulty=challenge.get("difficulty"))
    if kind in (challenges.KIND_SCOUT, challenges.KIND_DISARM):
        corridor = await _challenge_corridor(db, session_id, challenge)
        if kind == challenges.KIND_SCOUT and challenges.shadow_plausible(params, presses):
            passed, outcome = challenges.shadow_verdict(params, presses, seen_until)
        else:
            passed, outcome = False, ("short" if kind == challenges.KIND_DISARM else "broke")
        return await _settle_intel(db, session_obj, kind, character_id, passed, outcome, corridor=corridor,
                                   difficulty=challenge.get("difficulty"))
    corridor = await _challenge_corridor(db, session_id, challenge)
    if kind in challenges.STEP_KINDS:
        passed, outcome = False, "short"
    elif kind == challenges.KIND_GATE:
        passed, outcome = (challenges.gate_verdict(params, presses, seen_until)
                           if challenges.gate_plausible(presses) else (False, "broke"))
    elif kind == challenges.KIND_ILLUSION:
        if not challenges.runes_plausible(params, presses) or elapsed < challenges.runes_min_ms(params):
            passed, outcome = False, "broke"
        else:
            passed, outcome = challenges.runes_verdict(params, presses)
            if outcome == "short" and elapsed >= params["time_limit_ms"]:
                outcome = "time"
    elif not challenges.presses_plausible(params, presses, elapsed):
        passed, outcome = False, "broke"
    else:
        passed, outcome = challenges.lockpick_verdict(params, presses)
        # Stopped pressing, but only because the time was up.
        if outcome == "short" and elapsed >= params["time_limit_ms"]:
            outcome = "time"
    return await _settle_challenge(db, session_obj, corridor, kind, character_id, passed, outcome,
                                   difficulty=challenge.get("difficulty"),
                                   fail_damage=challenge.get("fail_damage") or 0)


async def step_challenge(
    db: AsyncSession, session_id: int, character_id: int, challenge_id: str,
    x: Optional[int] = None, y: Optional[int] = None, index: Optional[int] = None,
) -> ChallengeStepResponse:
    """One move of a game the server keeps the secret of: a stone pressed or pulled."""
    session_obj, challenge = await _locked_challenge(db, session_id, character_id, challenge_id)
    kind = challenge["kind"]
    if kind not in challenges.STEP_KINDS:
        raise HTTPException(status_code=400, detail="В этом испытании нет ходов")
    params, hidden = challenge["params"], challenge["hidden"]
    distance = safe = pulsing = way = near = None
    try:
        if kind == challenges.KIND_MECHANISM:
            if x is None or y is None:
                raise ValueError("Укажите камень")
            distance, over = challenges.mechanism_probe(params, hidden, x, y)
        elif kind == challenges.KIND_SEAL:
            if index is None:
                raise ValueError("Укажите узел")
            safe, over, pulsing = challenges.seal_trace(params, hidden, index)
        elif kind == challenges.KIND_SEARCH:
            if x is None or y is None:
                raise ValueError("Укажите место")
            way, over = challenges.search_probe(params, hidden, x, y)
        elif kind == challenges.KIND_DISARM:
            if index is None:
                raise ValueError("Укажите тягу")
            safe, near, over = challenges.wires_cut(params, hidden, index)
        else:
            if index is None:
                raise ValueError("Укажите камень")
            safe, over = challenges.rubble_pull(params, hidden, index)
    except ValueError as e:
        await db.commit()  # release the row lock
        raise HTTPException(status_code=400, detail=str(e))
    if over is None:
        await session_state.set_challenge(session_id, character_id, challenge, challenge.get("ttl", 600))
        if challenge.get("target"):  # the door stays this member's for as long as the game goes on
            await session_state.claim_target(session_id, challenge["target"], character_id, challenge.get("ttl", 600))
        await db.commit()  # the move is written: the next one may go
        return ChallengeStepResponse(kind=kind, distance=distance, safe=safe, pulsing=pulsing, way=way, near=near,
                                     offsets=hidden.get("offsets") if pulsing else None)

    await session_state.delete_challenge(session_id, character_id)
    if kind == challenges.KIND_SEARCH:
        result = await _settle_search(db, session_obj, character_id, over == "open", over,
                                      difficulty=challenge.get("difficulty"))
        return ChallengeStepResponse(kind=kind, way=way, result=result)
    if kind == challenges.KIND_DISARM:
        corridor = await _challenge_corridor(db, session_id, challenge)
        result = await _settle_intel(db, session_obj, kind, character_id, over == "open", over, corridor=corridor,
                                     difficulty=challenge.get("difficulty"))
        return ChallengeStepResponse(kind=kind, safe=safe, near=near, result=result)
    corridor = await _challenge_corridor(db, session_id, challenge)
    result = await _settle_challenge(db, session_obj, corridor, kind, character_id, over == "open", over,
                                     difficulty=challenge.get("difficulty"),
                                     fail_damage=challenge.get("fail_damage") or 0)
    return ChallengeStepResponse(kind=kind, distance=distance, safe=safe, result=result)


# =====================================================================
# Room Interaction
# =====================================================================

async def interact_with_room(
    db: AsyncSession,
    session_id: int,
    character_id: int,
    action: str,
    choice_index: Optional[int] = None,
    target_character_id: Optional[int] = None,
    item_id: Optional[int] = None,
    quantity: Optional[int] = None,
    auth_token: Optional[str] = None,  # kept for signature compatibility; unused
) -> InteractResponse:
    """Route room interaction by action type (leader only). The session row
    and the room state row are locked, so double clicks serialize."""
    session_obj = await _get_session(db, session_id, lock=True)
    if session_obj.status != STATUS_ACTIVE:
        raise HTTPException(status_code=400, detail="Сессия подземелья не активна")
    await _require_leader(db, session_obj, character_id, "взаимодействовать с комнатой")
    redis_state = await _require_state(db, session_obj)

    phase = redis_state.get("phase", "")
    allowed_phases = (PHASE_EXPLORING, PHASE_RESTING)
    if action == "start_battle":
        allowed_phases = (PHASE_BATTLE_PENDING, PHASE_EXPLORING)
    if phase not in allowed_phases:
        raise HTTPException(status_code=400, detail="Взаимодействие с комнатой доступно только в фазе исследования")

    current_room = await _get_room(db, session_obj.current_room_id)
    if not current_room:
        raise HTTPException(status_code=409, detail="Текущая комната не определена")
    dungeon = await _get_dungeon_for_session(db, session_obj.dungeon_id)
    room_state_obj = await _get_room_state(db, session_id, current_room.id, lock=True)
    _touch(session_obj)

    handlers = {
        "open_chest": lambda: _handle_open_chest(db, session_obj, dungeon, current_room, room_state_obj),
        "event_choice": lambda: _handle_event_choice(db, session_obj, dungeon, current_room, room_state_obj,
                                                     choice_index),
        "start_rest": lambda: _handle_start_rest(db, session_obj, dungeon, current_room, room_state_obj),
        "complete_rest": lambda: _handle_complete_rest(db, session_obj, dungeon, current_room, room_state_obj),
        "revive_member": lambda: _handle_revive_member(db, session_obj, dungeon, current_room, room_state_obj,
                                                       target_character_id),
        "merchant_buy": lambda: _handle_merchant_buy(db, session_obj, dungeon, current_room, room_state_obj,
                                                     character_id, item_id, quantity),
        "start_battle": lambda: _handle_start_battle(db, session_obj, dungeon, current_room, room_state_obj),
        "enter_mana_core": lambda: _handle_enter_mana_core(db, session_obj, dungeon, current_room, room_state_obj),
        "search_mana_core": lambda: _handle_search_mana_core(db, session_obj, dungeon, current_room,
                                                             room_state_obj),
        "use_portal": lambda: _handle_use_portal(db, session_obj, dungeon, current_room),
        "pull_lever": lambda: _handle_pull_lever(db, session_obj, current_room, room_state_obj),
    }
    handler = handlers.get(action)
    if handler is None:
        raise HTTPException(status_code=400, detail=f"Неизвестное действие: {action}")
    try:
        return await handler()
    except Exception:
        # Nothing half-done survives a failed action (e.g. an event choice
        # whose battle could not start stays open for a retry).
        await db.rollback()
        raise


async def _handle_pull_lever(
    db: AsyncSession, session_obj: DungeonSession, room: DungeonRoom, room_state: DungeonRoomState,
) -> InteractResponse:
    """Pull the room's lever: the locked passage it works opens for the rest of the run."""
    cfg = room.room_config if isinstance(room.room_config, dict) else {}
    corridor_id = cfg.get("lever_corridor_id")
    if not corridor_id:
        raise HTTPException(status_code=400, detail="Здесь нет рычага")
    extra = room_state.extra_data if isinstance(room_state.extra_data, dict) else {}
    if extra.get("lever_pulled"):
        raise HTTPException(status_code=409, detail="Рычаг уже опущен")
    corridor = (await db.execute(select(DungeonCorridor).where(
        DungeonCorridor.id == corridor_id, DungeonCorridor.dungeon_id == session_obj.dungeon_id,
    ))).scalar_one_or_none()
    room_state.extra_data = {**extra, "lever_pulled": True}
    if corridor is not None:
        _open_corridor(session_obj, corridor)
    await db.commit()
    message = "Рычаг со скрежетом опускается — где-то в подземелье лязгнул механизм."
    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "lever_pulled", "data": {"room_id": room.id, "message": message},
    })
    return InteractResponse(action="pull_lever", success=True, message=message)


async def _handle_use_portal(
    db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon, room: DungeonRoom,
) -> InteractResponse:
    """Step through a blue portal. It stays open: the party may use it again,
    either way (a paired portal brings it back)."""
    cfg = room.room_config if isinstance(room.room_config, dict) else {}
    if _portal_kind(room.room_type, cfg) != PORTAL_BLUE:
        raise HTTPException(status_code=400, detail="Здесь нет портала, в который можно шагнуть")
    await _require_party_ready(session_obj)
    event = await _teleport(db, session_obj, dungeon, room, None, cfg.get("target_room_id"), 0)
    if not event or event.get("type") != "teleported":
        raise HTTPException(status_code=400, detail=(event or {}).get("message") or "Портал не отвечает")
    await db.commit()
    return InteractResponse(
        action="use_portal", success=True,
        message=f"Группа шагнула в портал и оказалась в «{event['target_room_name']}».",
        teleported_to={"room_id": event["target_room_id"], "room_name": event["target_room_name"]},
    )


async def _handle_open_chest(
    db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon,
    room: DungeonRoom, room_state: DungeonRoomState,
) -> InteractResponse:
    """Open a treasure chest (treasure room) or the boss chest. Opening the
    boss chest completes the run and starts the GLOBAL dungeon cooldown."""
    if room.room_type not in ("treasure", "boss"):
        raise HTTPException(status_code=400, detail="Открыть сундук можно только в сокровищнице или комнате босса")
    if room_state.loot_collected:
        raise HTTPException(status_code=409, detail="Сундук уже был открыт")
    if room.room_type == "boss" and not room_state.is_cleared:
        raise HTTPException(status_code=400, detail="Сначала нужно победить босса")

    session_id = session_obj.id
    room_config = room.room_config if isinstance(room.room_config, dict) else {}
    loot_table = room_config.get("boss_loot" if room.room_type == "boss" else "loot_table", []) or []
    loot_gained = []
    cache: Dict[int, Optional[str]] = {}
    for entry in loot_table:
        if not isinstance(entry, dict):
            continue
        entry_item_id = entry.get("item_id")
        entry_quantity = entry.get("quantity", 1)
        adjusted_chance = min(float(entry.get("chance", 1.0)) * (dungeon.loot_multiplier or 1.0)
                              * _floor_factor(dungeon.floor_loot_step, _room_floor(room)), 1.0)
        if entry_item_id and random.random() < adjusted_chance:
            await _add_to_group_inventory(db, session_id, entry_item_id, entry_quantity, f"Сундук: {room.name}")
            loot_gained.append({"item_id": entry_item_id, "item_name": await _item_name(entry_item_id, cache),
                                "quantity": entry_quantity})
    room_state.loot_collected = True
    key_found = None
    if room.room_type == "treasure":
        key_found = await _grant_key(session_obj, room_config.get("key_reward"), f"Сундук: {room.name}")

    cooldown_until = None
    if room.room_type == "boss":
        now = _utcnow()
        cooldown_until = now + timedelta(hours=dungeon.cooldown_hours or 0)
        session_obj.status = "completed"
        session_obj.finished_at = now
        session_obj.cooldown_until = cooldown_until
    await db.commit()

    if room.room_type == "boss":
        await session_state.set_dungeon_cooldown(dungeon.id, session_id, dungeon.cooldown_hours or 0)
        await session_state.update_session_state(session_id, phase=PHASE_DISTRIBUTING, status="completed")
        # The run is won: members are free to go while the loot is shared out.
        # _close_session clears again at finalize, which covers a failed call here.
        await http_clients.clear_dungeon_lock(_member_ids(session_obj), session_id)
    await _sync_inventory_cache(db, session_id)

    message = "Сундук открыт!" if loot_gained or key_found else "Сундук оказался пустым..."
    await ws_manager.broadcast_to_session(session_id, {
        "type": "loot_added",
        "data": {
            "source": f"Сундук: {room.name}",
            "items": loot_gained,
            "item_name": ", ".join(i["item_name"] or f"Предмет #{i['item_id']}" for i in loot_gained) or None,
            "message": message,
        },
    })
    if room.room_type == "boss":
        await ws_manager.broadcast_to_session(session_id, {
            "type": "session_status",
            "data": {
                "status": "completed",
                "phase": PHASE_DISTRIBUTING,
                "cooldown_until": cooldown_until.isoformat() if cooldown_until else None,
                "message": "Подземелье пройдено! Распределите добычу.",
            },
        })
    return InteractResponse(action="open_chest", success=True, message=message,
                            loot_gained=loot_gained or None, key_found=key_found)


async def _handle_event_choice(
    db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon,
    room: DungeonRoom, room_state: DungeonRoomState, choice_index: Optional[int],
) -> InteractResponse:
    """Handle an event room choice. The choice is recorded in the same
    transaction as its DB effects; HTTP side effects (gold, HP) run after the
    commit so a failure can never be applied twice."""
    if room.room_type != "event":
        raise HTTPException(status_code=400, detail="Выбор доступен только в комнате-событии")
    if room_state.event_choice_index is not None:
        raise HTTPException(status_code=409, detail="Выбор уже был сделан в этой комнате")
    if choice_index is None:
        raise HTTPException(status_code=400, detail="Необходимо указать choice_index")
    choices = (room.room_config if isinstance(room.room_config, dict) else {}).get("choices", []) or []
    if choice_index < 0 or choice_index >= len(choices):
        raise HTTPException(status_code=400,
                            detail=f"Неверный choice_index: {choice_index}. Доступно вариантов: {len(choices)}")

    chosen = choices[choice_index] if isinstance(choices[choice_index], dict) else {}
    outcome_type = chosen.get("outcome_type", "nothing")
    try:
        outcome_data = _parse_outcome_data(chosen.get("outcome_data"))
    except ValueError:
        outcome_data = {}
    result_message = chosen.get("outcome_text") or "Выбор сделан."
    session_id = session_obj.id

    loot_gained = None
    damage_taken = None
    effect_applied = None
    teleported_to = None
    gold = 0
    post_commit = None

    room_state.event_choice_index = choice_index
    room_state.is_cleared = True

    if outcome_type == "reward":
        loot_list = []
        cache: Dict[int, Optional[str]] = {}
        for entry in outcome_data.get("items", []) or []:
            eid, eq = entry.get("item_id"), entry.get("quantity", 1)
            if eid:
                await _add_to_group_inventory(db, session_id, eid, eq, f"Событие: {room.name}")
                loot_list.append({"item_id": eid, "item_name": await _item_name(eid, cache), "quantity": eq})
        gold = int(outcome_data.get("gold", 0) or 0)
        if gold > 0:
            loot_list.append({"gold": gold})
        loot_gained = loot_list or None

    elif outcome_type == "damage":
        damage_taken = int(outcome_data.get("damage", 10) or 0)
        effect_applied = "урон"
        post_commit = ("damage", damage_taken)

    elif outcome_type == "heal":
        heal_percent = outcome_data.get("heal_percent")
        heal_amount = outcome_data.get("heal_amount")
        if heal_percent is None and heal_amount is None:
            heal_percent = 30
        effect_applied = f"лечение ({heal_percent}% HP)" if heal_percent is not None else f"лечение ({heal_amount} HP)"
        post_commit = ("heal", (heal_percent, heal_amount))

    elif outcome_type == "key":
        await _grant_key(session_obj, outcome_data.get("key"), f"Событие: {room.name}")

    elif outcome_type == "teleport":
        event = await _teleport(db, session_obj, dungeon, room, None, outcome_data.get("target_room_id"), 0)
        if event and event.get("type") == "teleported":
            teleported_to = {"room_id": event["target_room_id"], "room_name": event["target_room_name"]}
        else:
            result_message = (event or {}).get("message", result_message)

    elif outcome_type == "battle":
        # Uses the OUTCOME's mobs. A failure rolls the choice back (retry).
        battle_id, names = await start_battle(
            db, session_obj, dungeon, outcome_data.get("mob_template_ids") or [], room=room,
        )
        effect_applied = "бой"
        teleported_to = None
        loot_gained = None
        result_message = chosen.get("outcome_text") or "На вас напали!"
        await db.commit()
        await _broadcast_event_result(session_id, room, choice_index, outcome_type, result_message,
                                      None, None, effect_applied, None, battle_id=battle_id, mob_names=names)
        resp = InteractResponse(action="event_choice", success=True, message=result_message,
                                effect_applied=effect_applied)
        return resp

    await db.commit()
    await _sync_inventory_cache(db, session_id)

    if gold > 0:
        try:
            await http_clients.add_gold(session_obj.leader_character_id, gold)
        except Exception:
            logger.warning("Не удалось начислить %d золота лидеру %d", gold, session_obj.leader_character_id)
    if post_commit and post_commit[0] == "damage":
        await _damage_party(_alive_ids(session_obj), post_commit[1])
    elif post_commit and post_commit[0] == "heal":
        await _heal_party(_alive_ids(session_obj), *post_commit[1])

    await _broadcast_event_result(session_id, room, choice_index, outcome_type, result_message,
                                  loot_gained, damage_taken, effect_applied, teleported_to)
    return InteractResponse(
        action="event_choice", success=True, message=result_message,
        loot_gained=loot_gained, damage_taken=damage_taken,
        effect_applied=effect_applied, teleported_to=teleported_to,
    )


async def _broadcast_event_result(session_id, room, choice_index, outcome_type, message,
                                  loot_gained, damage_taken, effect_applied, teleported_to, **extra):
    await ws_manager.broadcast_to_session(session_id, {
        "type": "event_result",
        "data": {
            "room_id": room.id, "choice_index": choice_index, "outcome_type": outcome_type,
            "message": message, "loot_gained": loot_gained, "damage_taken": damage_taken,
            "effect_applied": effect_applied, "teleported_to": teleported_to, **extra,
        },
    })


async def _handle_start_battle(
    db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon,
    room: DungeonRoom, room_state: DungeonRoomState,
) -> InteractResponse:
    """Retry the battle of an uncleared battle/boss room (phase battle_pending)."""
    if room.room_type not in ("battle", "boss") or room_state.is_cleared:
        raise HTTPException(status_code=400, detail="Здесь не с кем сражаться")
    if session_obj.active_battle_id:
        raise HTTPException(status_code=409, detail="Бой уже идёт")
    cfg = room.room_config if isinstance(room.room_config, dict) else {}
    battle_id, names = await start_battle(db, session_obj, dungeon, cfg.get("mob_template_ids") or [], room=room)
    await db.commit()
    return InteractResponse(action="start_battle", success=True, message="Бой начинается!",
                            effect_applied=f"battle_id={battle_id}")


async def _handle_start_rest(
    db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon,
    room: DungeonRoom, room_state: DungeonRoomState,
) -> InteractResponse:
    if room.room_type != "rest":
        raise HTTPException(status_code=400, detail="Отдых доступен только в комнате отдыха")
    if dungeon.disable_rest_rooms:
        raise HTTPException(status_code=400, detail="Комнаты отдыха отключены в этом подземелье")
    extra = dict(room_state.extra_data) if isinstance(room_state.extra_data, dict) else {}
    if extra.get("rest_used"):
        raise HTTPException(status_code=409, detail="Отдых в этой комнате уже использован")
    if extra.get("rest_started_at"):
        raise HTTPException(status_code=409, detail="Отдых уже начат. Используйте действие complete_rest для завершения.")

    cfg = room.room_config if isinstance(room.room_config, dict) else {}
    heal_percent = cfg.get("heal_percent", 30)
    wait_seconds = cfg.get("wait_seconds", 60)
    gold_cost = cfg.get("gold_cost", 0) or 0

    import time
    extra.update({"rest_started_at": time.time(), "heal_percent": heal_percent, "wait_seconds": wait_seconds})
    room_state.extra_data = extra
    await db.flush()
    gold_spent = None
    if gold_cost > 0:
        if not await http_clients.deduct_gold(session_obj.leader_character_id, gold_cost):
            await db.rollback()
            raise HTTPException(status_code=400, detail=f"Недостаточно золота для отдыха (нужно {gold_cost})")
        gold_spent = gold_cost
    await db.commit()
    await session_state.set_phase(session_obj.id, PHASE_RESTING)
    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "rest_started",
        "data": {"room_id": room.id, "wait_seconds": wait_seconds, "heal_percent": heal_percent,
                 "gold_cost": gold_cost,
                 "message": f"Группа устроилась на привал. Ожидание: {wait_seconds} секунд."},
    })
    return InteractResponse(
        action="start_rest", success=True,
        message=f"Отдых начат. Ожидание: {wait_seconds} секунд. Восстановление: {heal_percent}% HP.",
        gold_spent=gold_spent,
    )


async def _handle_complete_rest(
    db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon,
    room: DungeonRoom, room_state: DungeonRoomState,
) -> InteractResponse:
    if room.room_type != "rest":
        raise HTTPException(status_code=400, detail="Завершить отдых можно только в комнате отдыха")
    extra = dict(room_state.extra_data) if isinstance(room_state.extra_data, dict) else {}
    rest_started_at = extra.get("rest_started_at")
    if not rest_started_at:
        raise HTTPException(status_code=400, detail="Отдых не был начат")
    if extra.get("rest_used"):
        raise HTTPException(status_code=409, detail="Отдых в этой комнате уже использован")
    import time
    wait_seconds = extra.get("wait_seconds", 60)
    elapsed = time.time() - rest_started_at
    if elapsed < wait_seconds:
        raise HTTPException(status_code=400,
                            detail=f"Отдых ещё не завершён. Осталось {int(wait_seconds - elapsed)} секунд.")
    heal_percent = extra.get("heal_percent", 30)
    extra["rest_used"] = True
    room_state.extra_data = extra

    # A night raid (FEAT-176): the watch, if alert, raises the alarm in time; if
    # not — or if nobody watched — the rest is lost and a fight begins.
    raid_note = ""
    cfg = room.room_config if isinstance(room.room_config, dict) else {}
    raid_mobs = cfg.get("ambush_mob_ids") or []
    if raid_mobs and float(cfg.get("ambush_chance") or 0) > random.random():
        watch = extra.get("watch") if isinstance(extra.get("watch"), dict) else None
        watcher = watch["character_id"] if watch and watch["character_id"] in _alive_ids(session_obj) else None
        if watcher and watch.get("passed"):
            raid_note = (f"Ночью к привалу подкрались твари, но {await _character_name(watcher)} "
                         f"поднимает тревогу — вылазку отбили. ")
        else:
            struck = [watcher] if watcher else _alive_ids(session_obj)
            report = await _damage_party(struck, AMBUSH_STRIKE_DAMAGE)
            try:
                battle_id, names = await start_battle(db, session_obj, dungeon, raid_mobs, room=room)
            except Exception:
                # The raid could not start: give the blow back, the rest goes on as usual.
                logger.warning("Сессия %d: ночная вылазка не началась", session_obj.id, exc_info=True)
                await _undo_damage(session_obj.id, report)
            else:
                await db.commit()
                who = (f"{await _character_name(watcher)} клюёт носом в дозоре — первый удар достаётся дозорному"
                       if watcher else "Дозорного не было — первый удар достаётся всем")
                message = f"Ночью на привал напали! {who}. Урон: {AMBUSH_STRIKE_DAMAGE}. Отдых сорван."
                await ws_manager.broadcast_to_session(session_obj.id, {
                    "type": "rest_completed",
                    "data": {"room_id": room.id, "heal_percent": 0, "raided": True, "battle_id": battle_id,
                             "mob_names": names, "damage_report": report, "message": message},
                })
                return InteractResponse(action="complete_rest", success=True, message=message,
                                        damage_taken=AMBUSH_STRIKE_DAMAGE)
    await db.commit()

    recovery_details = await _heal_party(_alive_ids(session_obj), heal_percent, None)
    await session_state.set_phase(session_obj.id, PHASE_EXPLORING)
    message = f"{raid_note}Отдых завершён! Все живые участники восстановили {heal_percent}% HP."
    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "rest_completed",
        "data": {"room_id": room.id, "heal_percent": heal_percent,
                 "recovery_details": recovery_details, "message": message},
    })
    return InteractResponse(action="complete_rest", success=True, message=message,
                            effect_applied=f"лечение {heal_percent}% HP")


async def _handle_revive_member(
    db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon,
    room: DungeonRoom, room_state: DungeonRoomState, target_character_id: Optional[int],
) -> InteractResponse:
    """Revive a dead member in a rest room for gold. The member row is flipped
    under the session lock BEFORE gold is taken, and flipped back if the
    payment fails — a double click cannot pay twice."""
    if room.room_type != "rest":
        raise HTTPException(status_code=400, detail="Воскрешение доступно только в комнате отдыха")
    if target_character_id is None:
        raise HTTPException(status_code=400, detail="Необходимо указать target_character_id — ID погибшего участника")
    target = next((m for m in session_obj.members if m.character_id == target_character_id), None)
    if target is None:
        raise HTTPException(status_code=400, detail="Указанный персонаж не является участником группы")
    if target.status != "dead":
        raise HTTPException(status_code=409, detail="Указанный персонаж не мёртв")

    cfg = room.room_config if isinstance(room.room_config, dict) else {}
    revive_cost = cfg.get("revive_gold_cost", DEFAULT_REVIVE_COST)
    target.status = "alive"
    await db.flush()
    if not await http_clients.deduct_gold(session_obj.leader_character_id, revive_cost):
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Недостаточно золота для воскрешения (нужно {revive_cost})")
    await db.commit()
    await session_state.update_member_status(session_obj.id, str(target_character_id), "alive")

    try:
        attrs = await http_clients.get_character_attributes(target_character_id)
        revive_hp = max(1, int(int(attrs.get("max_health", 100) or 100) * REVIVE_HP_FRACTION))
        await http_clients.recover_character(target_character_id, health=revive_hp)
    except Exception:
        logger.warning("Не удалось восстановить HP воскрешённому персонажу %d", target_character_id)

    target_name = await _character_name(target_character_id)
    message = f"{target_name} воскрешён(а) за {revive_cost} золота!"
    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "member_status_changed",
        "data": {"character_id": target_character_id, "name": target_name,
                 "status": "alive", "new_status": "alive", "gold_spent": revive_cost, "message": message},
    })
    return InteractResponse(action="revive_member", success=True, message=message, gold_spent=revive_cost)


async def _handle_merchant_buy(
    db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon,
    room: DungeonRoom, room_state: DungeonRoomState,
    buyer_character_id: int, buy_item_id: Optional[int], buy_quantity: Optional[int],
) -> InteractResponse:
    """Buy from a merchant. Stock is reserved under the room-state row lock
    and released again if the payment fails."""
    if room.room_type != "merchant":
        raise HTTPException(status_code=400, detail="Покупка доступна только в комнате торговца")
    if dungeon.disable_merchants:
        raise HTTPException(status_code=400, detail="Торговцы отключены в этом подземелье")
    if buy_item_id is None:
        raise HTTPException(status_code=400, detail="Необходимо указать item_id для покупки")
    if buy_quantity is None or buy_quantity < 1:
        buy_quantity = 1

    items = (room.room_config if isinstance(room.room_config, dict) else {}).get("items", []) or []
    merchant_item = next((mi for mi in items if isinstance(mi, dict) and mi.get("item_id") == buy_item_id), None)
    if merchant_item is None:
        raise HTTPException(status_code=400, detail="Этот предмет не продаётся у торговца")
    price = merchant_item.get("price", 0) or 0
    extra = dict(room_state.extra_data) if isinstance(room_state.extra_data, dict) else {}
    stock = dict(extra.get("merchant_stock", {}))
    key = str(buy_item_id)
    remaining = stock.get(key, merchant_item.get("stock", 999))
    if remaining < buy_quantity:
        raise HTTPException(status_code=409, detail=f"Недостаточно товара. Осталось: {remaining}")
    total_cost = price * buy_quantity

    stock[key] = remaining - buy_quantity
    extra["merchant_stock"] = stock
    room_state.extra_data = extra
    await _add_to_group_inventory(db, session_obj.id, buy_item_id, buy_quantity, f"Торговец: {room.name}")
    await db.flush()
    if total_cost > 0 and not await http_clients.deduct_gold(buyer_character_id, total_cost):
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Недостаточно золота для покупки (нужно {total_cost})")
    await db.commit()
    await _sync_inventory_cache(db, session_obj.id)

    name = await _item_name(buy_item_id)
    items_out = [{"item_id": buy_item_id, "item_name": name, "quantity": buy_quantity}]
    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "loot_added",
        "data": {"source": f"Торговец: {room.name}", "items": items_out, "item_name": name,
                 "gold_spent": total_cost, "message": f"Куплен предмет за {total_cost} золота."},
    })
    return InteractResponse(action="merchant_buy", success=True,
                            message=f"Покупка совершена за {total_cost} золота.",
                            loot_gained=items_out, gold_spent=total_cost)


async def _handle_enter_mana_core(
    db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon,
    room: DungeonRoom, room_state: DungeonRoomState,
) -> InteractResponse:
    """From the cleared boss room, follow the revealed path to the mana core
    room (no corridor in the graph — the path exists for this run only)."""
    if not room.is_boss_room or not room_state.is_cleared:
        raise HTTPException(status_code=400, detail="Путь к ядру маны открывается в комнате побеждённого босса")
    info = await _mana_core_info(db, session_obj, dungeon)
    if not info or not info.revealed:
        raise HTTPException(status_code=400, detail="Ядро маны не обнаружено")
    if not info.accessible:
        raise HTTPException(status_code=409, detail="Ядро маны уже исследовано")
    mc_room = await _get_room(db, info.room_id)
    await _enter_room(db, session_obj, dungeon, mc_room)
    await db.commit()
    return InteractResponse(action="enter_mana_core", success=True,
                            message=f"Группа спустилась в «{mc_room.name}».",
                            teleported_to={"room_id": mc_room.id, "room_name": mc_room.name})


async def _handle_search_mana_core(
    db: AsyncSession, session_obj: DungeonSession, dungeon: Dungeon,
    room: DungeonRoom, room_state: DungeonRoomState,
) -> InteractResponse:
    """Destroy the mana core. Single roll per run: if the core was revealed
    after the boss, the search always succeeds; if the party reached the room
    by a regular corridor (no reveal), the one roll happens here. Success
    gives the crystal and DEACTIVATES the dungeon (kept from the old design —
    to be confirmed with the user). The party is then returned to the boss
    room to open the chest."""
    if not room.is_mana_core_room:
        raise HTTPException(status_code=400, detail="Поиск ядра маны доступен только в комнате ядра маны")
    boss_extra, boss_cleared = await _boss_state(db, session_obj)
    if not boss_cleared:
        raise HTTPException(status_code=400, detail="Сначала нужно победить босса подземелья")
    extra = dict(room_state.extra_data) if isinstance(room_state.extra_data, dict) else {}
    if extra.get("mana_core_searched"):
        raise HTTPException(status_code=409, detail="Ядро маны уже было исследовано")

    if boss_extra.get("mana_core_revealed"):
        success, roll = True, None
    elif "mana_core_roll" in boss_extra:
        success, roll = False, boss_extra["mana_core_roll"]  # already rolled at the boss
    else:
        roll = random.random()
        success = roll < (dungeon.mana_core_chance or 0)

    extra["mana_core_searched"] = True
    extra["mana_core_destroyed"] = bool(success and dungeon.mana_core_item_id)
    room_state.extra_data = extra
    loot = None
    if extra["mana_core_destroyed"]:
        await _add_to_group_inventory(db, session_obj.id, dungeon.mana_core_item_id, 1,
                                      "Ядро маны: Кристалл подземелья")
        dungeon.is_active = False
        loot = [{"item_id": dungeon.mana_core_item_id,
                 "item_name": await _item_name(dungeon.mana_core_item_id), "quantity": 1}]
        message = ("Ядро маны уничтожено! Получен Кристалл подземелья. Подземелье угасает — "
                   "после этого забега в него больше не войти.")
    else:
        message = "Ядро маны ускользнуло — здесь лишь угасающие отблески."

    boss_room = (await db.execute(
        select(DungeonRoom)
        .join(DungeonRoomState, DungeonRoomState.room_id == DungeonRoom.id)
        .where(DungeonRoomState.session_id == session_obj.id, DungeonRoom.is_boss_room == True,  # noqa: E712
               DungeonRoomState.is_cleared == True)  # noqa: E712
        .limit(1)
    )).scalar_one_or_none()
    if boss_room:
        await _enter_room(db, session_obj, dungeon, boss_room)
    await db.commit()
    await _sync_inventory_cache(db, session_obj.id)
    await ws_manager.broadcast_to_session(session_obj.id, {
        "type": "mana_core_result",
        "data": {"destroyed": extra["mana_core_destroyed"], "loot": loot, "message": message,
                 "returned_to_room_id": boss_room.id if boss_room else None},
    })
    logger.info("Ядро маны: session=%d dungeon=%d destroyed=%s roll=%s",
                session_obj.id, dungeon.id, extra["mana_core_destroyed"], roll)
    return InteractResponse(action="search_mana_core", success=extra["mana_core_destroyed"],
                            message=message, loot_gained=loot)


# =====================================================================
# Flee, Loot Distribution, Finalize
# =====================================================================

async def flee_dungeon(db: AsyncSession, session_id: int, character_id: int) -> FleeResponse:
    """Flee the run (leader). Each loot stack is lost with 50% chance; the
    session ends (escaped), the dungeon is free immediately, no cooldown,
    the members' lock is released. Leftover loot is distributed afterwards."""
    session_obj = await _get_session(db, session_id, lock=True)
    if session_obj.status != STATUS_ACTIVE:
        raise HTTPException(status_code=400, detail="Побег возможен только из активной сессии")
    await _require_leader(db, session_obj, character_id, "инициировать побег")
    redis_state = await _require_state(db, session_obj)
    if redis_state.get("phase") == PHASE_IN_BATTLE or session_obj.active_battle_id:
        raise HTTPException(status_code=400, detail="Нельзя сбежать во время боя")

    items_lost, items_remaining = await _escape(db, session_obj, reason="flee", apply_loss=True)
    if not items_remaining:
        session_obj = await _get_session(db, session_id, lock=True)
        await _close_session(db, session_obj)

    if not items_lost and not items_remaining:
        message = "Группа сбежала из подземелья! Инвентарь был пуст."
    elif not items_lost:
        message = "Группа сбежала из подземелья! Вся добыча сохранена."
    else:
        message = (f"Группа сбежала из подземелья! Потеряно предметов: {len(items_lost)}, "
                   f"сохранено: {len(items_remaining)}.")
    return FleeResponse(status="escaped", items_lost=items_lost, items_remaining=items_remaining, message=message)


CONSUMABLE_TYPE = "consumable"


async def give_item(
    db: AsyncSession, session_id: int, character_id: int, target_character_id: int, item_id: int, quantity: int,
) -> GiveItemResponse:
    """FEAT-178: mid-run the leader hands a found consumable to a living member — it goes into
    their camp backpack (no backpack, no room: refused, the item stays with the party).
    The group's rows stay locked while inventory-service takes it, so a double click
    cannot give one potion twice."""
    session_obj = await _get_session(db, session_id, lock=True)
    if session_obj.status != STATUS_ACTIVE:
        raise HTTPException(status_code=400, detail="Передавать находки можно только во время забега")
    await _require_leader(db, session_obj, character_id, "передавать находки")
    target = _require_member(session_obj, target_character_id)
    if target.status != "alive":
        raise HTTPException(status_code=400, detail="Передать можно только живому участнику")
    rows = [r for r in await _inventory_rows(db, session_id, lock=True) if r.item_id == item_id]
    if sum(r.quantity for r in rows) < quantity:
        raise HTTPException(status_code=409, detail="Столько этого предмета у отряда нет")
    info = await http_clients.get_item_info(item_id)
    if info.get("item_type") != CONSUMABLE_TYPE:
        raise HTTPException(status_code=400, detail="Во время забега передаются только расходники")
    target_name = await _character_name(target_character_id)
    try:
        await http_clients.add_to_backpack(target_character_id, item_id, quantity)
    except HTTPException as e:
        # inventory-service speaks to the backpack's owner; the leader is told about them.
        if e.status_code == 409 and "Наденьте" in str(e.detail):
            raise HTTPException(status_code=409, detail=f"{target_name}: нет походного рюкзака")
        if e.status_code == 409 and "нет места" in str(e.detail):
            raise HTTPException(status_code=409, detail=f"{target_name}: в рюкзаке нет места")
        raise

    left = quantity
    for row in rows:
        if left <= 0:
            break
        take = min(row.quantity, left)
        row.quantity -= take
        left -= take
        if row.quantity <= 0:
            await db.delete(row)
    _touch(session_obj)
    await db.commit()

    remaining = await _sync_inventory_cache(db, session_id)
    name = info.get("name") or f"Предмет #{item_id}"
    count = f" ×{quantity}" if quantity > 1 else ""
    await ws_manager.broadcast_to_session(session_id, {
        "type": "item_given",
        "data": {"target_character_id": target_character_id, "target_name": target_name, "item_id": item_id,
                 "item_name": name, "quantity": quantity,
                 # The run's log picks the message up from the broadcast.
                 "message": f"{target_name} получает от лидера: {name}{count} — в рюкзак"},
    })
    cache: Dict[int, Optional[str]] = {}
    return GiveItemResponse(
        message=f"{target_name}: {name}{count} — в рюкзаке",
        group_inventory=[
            GroupInventoryItemResponse(item_id=i.item_id, item_name=await _item_name(i.item_id, cache),
                                       quantity=i.quantity, source_description=i.source_description)
            for i in remaining
        ],
    )


async def _require_distributor(db: AsyncSession, session_obj: DungeonSession, character_id: int, action_text: str):
    if session_obj.status not in ("completed", "escaped"):
        raise HTTPException(status_code=400, detail="Распределение добычи доступно только после завершения или побега")
    if session_obj.finalized_at is not None:
        raise HTTPException(status_code=409, detail="Забег уже завершён")
    await _require_leader(db, session_obj, character_id, action_text)


async def distribute_loot(
    db: AsyncSession,
    session_id: int,
    character_id: int,
    distributions: List[dict],
) -> DistributeLootResponse:
    """Hand group loot to members (leader; an idle leader is replaced).
    Inventory rows are removed and COMMITTED first, then delivered; a failed
    delivery puts the item back. Double submits serialize on the row lock and
    the second one fails validation (items no longer there)."""
    session_obj = await _get_session(db, session_id, lock=True)
    await _require_distributor(db, session_obj, character_id, "распределять добычу")

    inv_items = await _inventory_rows(db, session_id, lock=True)
    inventory_map: Dict[int, List[DungeonSessionInventory]] = {}
    for item in inv_items:
        inventory_map.setdefault(item.item_id, []).append(item)
    available_qty = {iid: sum(r.quantity for r in rows) for iid, rows in inventory_map.items()}
    member_char_ids = set(_member_ids(session_obj))
    alive_char_ids = set(_alive_ids(session_obj))

    requested_qty: Dict[int, int] = {}
    for dist in distributions:
        d_item_id, d_quantity, d_to_char = dist.get("item_id"), dist.get("quantity", 0), dist.get("to_character_id")
        if d_quantity <= 0:
            raise HTTPException(status_code=400, detail=f"Количество должно быть положительным (item_id={d_item_id})")
        if d_item_id not in available_qty:
            raise HTTPException(status_code=409, detail=f"Предмет {d_item_id} отсутствует в групповом инвентаре")
        if d_to_char not in member_char_ids:
            raise HTTPException(status_code=400, detail=f"Персонаж {d_to_char} не является участником сессии")
        if d_to_char not in alive_char_ids:
            raise HTTPException(status_code=400, detail="Добычу можно отдать только живым участникам группы")
        requested_qty[d_item_id] = requested_qty.get(d_item_id, 0) + d_quantity
    for iid, req in requested_qty.items():
        if req > available_qty.get(iid, 0):
            raise HTTPException(status_code=409, detail=(
                f"Запрошено {req} единиц предмета {iid}, но в инвентаре только {available_qty.get(iid, 0)}"))

    for dist in distributions:
        remaining = dist["quantity"]
        for row in inventory_map.get(dist["item_id"], []):
            if remaining <= 0:
                break
            take = min(row.quantity, remaining)
            row.quantity -= take
            remaining -= take
    for rows in inventory_map.values():
        for row in rows:
            if row.quantity <= 0:
                await db.delete(row)
    _touch(session_obj)
    await db.commit()

    failed = []
    for dist in distributions:
        try:
            await http_clients.add_item_to_character(dist["to_character_id"], dist["item_id"], dist["quantity"])
        except Exception:
            failed.append(dist)
            await _add_to_group_inventory(db, session_id, dist["item_id"], dist["quantity"], "Возврат: не удалось выдать")
    if failed:
        await db.commit()

    remaining_items = await _sync_inventory_cache(db, session_id)
    cache: Dict[int, Optional[str]] = {}
    remaining_resp = [
        GroupInventoryItemResponse(item_id=i.item_id, item_name=await _item_name(i.item_id, cache),
                                   quantity=i.quantity, source_description=i.source_description)
        for i in remaining_items
    ]
    await ws_manager.broadcast_to_session(session_id, {
        "type": "loot_distributed",
        "data": {
            "distributions": distributions,
            "failed": failed,
            "remaining_count": len(remaining_resp),
            "message": "Добыча распределена!" if not remaining_resp
            else f"Часть добычи распределена. Осталось предметов: {len(remaining_resp)}.",
        },
    })
    if failed:
        message = f"Не удалось выдать {len(failed)} поз. — они возвращены в общий инвентарь."
    elif not remaining_resp:
        message = "Вся добыча распределена!"
    else:
        message = f"Добыча частично распределена. Осталось предметов: {len(remaining_resp)}."
    return DistributeLootResponse(success=not failed, message=message,
                                  remaining_inventory=remaining_resp, failed=failed)


async def finalize_session(
    db: AsyncSession,
    session_id: int,
    character_id: int,
    force: bool = False,
) -> FinalizeResponse:
    """Close a completed/escaped session. With leftovers, `force=true` is
    required and the leftovers are lost. The cooldown was already set when
    the boss chest was opened. Repeated calls answer the same (idempotent)."""
    session_obj = await _get_session(db, session_id, lock=True)
    if session_obj.status not in ("completed", "escaped"):
        raise HTTPException(status_code=400, detail="Завершить можно только пройденную или покинутую сессию")
    if session_obj.finalized_at is not None:
        _require_member(session_obj, character_id)
        await db.commit()
        return FinalizeResponse(message="Забег уже завершён.", cooldown_until=session_obj.cooldown_until)
    await _require_leader(db, session_obj, character_id, "завершить сессию")

    remaining_items = await _inventory_rows(db, session_id, lock=True)
    if remaining_items and not force:
        raise HTTPException(
            status_code=409,
            detail=("В групповом инвентаре остались нераспределённые предметы. "
                    "Распределите добычу или завершите с force=true (оставшиеся предметы будут потеряны)."),
        )
    for item in remaining_items:
        await db.delete(item)
    await _close_session(db, session_obj)

    if session_obj.status == "completed":
        message = "Подземелье пройдено!"
        if session_obj.cooldown_until:
            message += f" Откат подземелья до {(session_obj.cooldown_until + timedelta(hours=3)).strftime('%d.%m %H:%M')} МСК."
    else:
        message = "Забег завершён."
    return FinalizeResponse(message=message, cooldown_until=session_obj.cooldown_until,
                            items_lost=sum(i.quantity for i in remaining_items))


async def admin_force_cleanup_session(db: AsyncSession, session_id: int) -> dict:
    """Admin: end any session regardless of state (incl. completed/wiped
    leftovers): loot dropped, Redis/WS cleaned, character locks released.
    No cooldown is added; a completed run keeps the cooldown it earned."""
    session_obj = await _get_session(db, session_id, lock=True)
    member_char_ids = _member_ids(session_obj)
    battle_mobs, _, _ = _battle_of(session_obj, await session_state.get_session_state(session_id))
    _forget_battle(session_obj)

    for item in await _inventory_rows(db, session_id, lock=True):
        await db.delete(item)
    old_status = session_obj.status
    if session_obj.status not in ENDED_STATUSES:
        session_obj.status = "escaped"
    session_obj.active_battle_id = None
    now = _utcnow()
    session_obj.finished_at = session_obj.finished_at or now
    session_obj.finalized_at = session_obj.finalized_at or now
    await db.commit()

    await http_clients.clear_dungeon_lock(member_char_ids, session_id)
    await http_clients.despawn_dungeon_mobs(battle_mobs)
    await ws_manager.broadcast_to_session(session_id, {
        "type": "session_status",
        "data": {"status": session_obj.status, "phase": PHASE_FINISHED, "finalized": True,
                 "message": "Забег завершён администратором."},
    })
    await session_state.cleanup_session(session_id, member_char_ids)
    await ws_manager.cleanup_session(session_id)
    logger.info("Admin force-cleanup: сессия %d (было: %s), освобождены персонажи: %s",
                session_id, old_status, member_char_ids)
    return {
        "message": f"Сессия {session_id} принудительно завершена",
        "session_id": session_id,
        "previous_status": old_status,
        "freed_characters": member_char_ids,
    }


async def find_character_session(db: AsyncSession, character_id: int) -> Tuple[Optional[int], Optional[int]]:
    """(run in progress, ended run whose loot is still undivided) from the DB.
    A completed run counts as the latter: its members are already free."""
    rows = (await db.execute(
        select(DungeonSession.id, DungeonSession.status)
        .join(DungeonSessionMember, DungeonSessionMember.session_id == DungeonSession.id)
        .where(
            DungeonSessionMember.character_id == character_id,
            DungeonSession.finalized_at.is_(None),
            DungeonSession.status.in_(("active", "completed", "escaped")),
        )
        .order_by(DungeonSession.id.desc())
    )).all()
    active = next((sid for sid, st in rows if st == "active"), None)
    pending = next((sid for sid, st in rows if st in ("completed", "escaped")), None)
    return active, pending
