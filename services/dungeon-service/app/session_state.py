"""
Redis session state management for dungeon-service.

Key schema:
  - dungeon:session:{session_id}:state           — JSON, full session state (48h TTL)
  - dungeon:{dungeon_id}:cooldown                — STRING, session_id (cooldown_hours TTL)
  - dungeon:session:{session_id}:inventory        — JSON, group inventory cache (48h TTL)
  - dungeon:character:{character_id}:active_session — STRING, session_id (48h TTL)

Follows the singleton-client pattern from battle-service redis_state.py.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import redis.asyncio as redis

from config import settings

SESSION_TTL_HOURS = int(os.getenv("DUNGEON_SESSION_TTL_HOURS", 48))
SESSION_TTL = SESSION_TTL_HOURS * 3600  # seconds

# Singleton Redis client
_redis_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """Get or create a singleton aioredis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await _redis_client.execute_command("CLIENT", "SETNAME", "dungeon-service")
        role_info = await _redis_client.info("replication")
        if role_info["role"] != "master":
            raise RuntimeError("Connected to Redis replica, need master")
    return _redis_client


# ---------- key generators ---------------------------------------------------

def _state_key(session_id: int) -> str:
    return f"dungeon:session:{session_id}:state"


def _cooldown_key(dungeon_id: int) -> str:
    return f"dungeon:{dungeon_id}:cooldown"


def _inventory_key(session_id: int) -> str:
    return f"dungeon:session:{session_id}:inventory"


def _active_session_key(character_id: int) -> str:
    return f"dungeon:character:{character_id}:active_session"


# ---------- session state ----------------------------------------------------

async def init_session_state(
    session_id: int,
    dungeon_id: int,
    leader_character_id: int,
    members: dict,
) -> None:
    """
    Create initial session state in Redis.

    members format: {
        "100": {"user_id": 10, "status": "alive"},
        "101": {"user_id": 11, "status": "alive"},
    }
    """
    rds = await get_redis()

    state: Dict = {
        "session_id": session_id,
        "dungeon_id": dungeon_id,
        "current_room_id": None,
        "status": "active",
        "leader_character_id": leader_character_id,
        "members": members,
        "active_battle_id": None,
        "dead_count": sum(
            1 for m in members.values() if m.get("status") == "dead"
        ),
        "phase": "forming",
    }

    await rds.set(_state_key(session_id), json.dumps(state), ex=SESSION_TTL)


async def get_session_state(session_id: int) -> Optional[Dict]:
    """Load session state from Redis. Returns None if not found."""
    rds = await get_redis()
    raw: Optional[str] = await rds.get(_state_key(session_id))
    if raw is None:
        return None
    return json.loads(raw)


async def update_session_state(session_id: int, **kwargs) -> Optional[Dict]:
    """
    Partial update of session state fields.
    Returns the updated state, or None if session not found.
    """
    state = await get_session_state(session_id)
    if state is None:
        return None

    state.update(kwargs)

    rds = await get_redis()
    await rds.set(_state_key(session_id), json.dumps(state), ex=SESSION_TTL)
    return state


# ---------- convenience setters ----------------------------------------------

async def set_current_room(session_id: int, room_id: int) -> Optional[Dict]:
    """Update current_room_id in session state."""
    return await update_session_state(session_id, current_room_id=room_id)


async def set_phase(session_id: int, phase: str) -> Optional[Dict]:
    """Update phase in session state."""
    return await update_session_state(session_id, phase=phase)


async def set_active_battle(session_id: int, battle_id: int) -> Optional[Dict]:
    """Set active_battle_id and phase to in_battle."""
    return await update_session_state(
        session_id, active_battle_id=battle_id, phase="in_battle"
    )


async def clear_active_battle(session_id: int) -> Optional[Dict]:
    """Clear active_battle_id and revert phase to exploring."""
    return await update_session_state(
        session_id, active_battle_id=None, phase="exploring"
    )


async def update_member_status(
    session_id: int, character_id: str, status: str
) -> Optional[Dict]:
    """
    Update a single member's status and recalculate dead_count.
    character_id is a string key in the members dict.
    """
    state = await get_session_state(session_id)
    if state is None:
        return None

    members = state.get("members", {})
    if character_id not in members:
        return None

    members[character_id]["status"] = status
    state["members"] = members
    state["dead_count"] = sum(
        1 for m in members.values() if m.get("status") == "dead"
    )

    rds = await get_redis()
    await rds.set(_state_key(session_id), json.dumps(state), ex=SESSION_TTL)
    return state


async def set_leader(session_id: int, character_id: int) -> Optional[Dict]:
    """Transfer leadership to another character."""
    return await update_session_state(
        session_id, leader_character_id=character_id
    )


# ---------- dungeon cooldown -------------------------------------------------

async def set_dungeon_cooldown(
    dungeon_id: int, session_id: int, cooldown_hours: int
) -> None:
    """Set a TTL-based cooldown key for a dungeon."""
    rds = await get_redis()
    ttl_seconds = cooldown_hours * 3600
    await rds.set(
        _cooldown_key(dungeon_id), str(session_id), ex=ttl_seconds
    )


async def check_dungeon_cooldown(dungeon_id: int) -> Tuple[bool, int]:
    """
    Check if a dungeon is on cooldown.
    Returns (is_on_cooldown, remaining_seconds).
    """
    rds = await get_redis()
    remaining = await rds.ttl(_cooldown_key(dungeon_id))
    # ttl returns -2 if key doesn't exist, -1 if no TTL set
    if remaining <= 0:
        return (False, 0)
    return (True, remaining)


# ---------- character active session -----------------------------------------

async def set_character_active_session(
    character_id: int, session_id: int
) -> None:
    """Mark a character as participating in a dungeon session."""
    rds = await get_redis()
    await rds.set(
        _active_session_key(character_id), str(session_id), ex=SESSION_TTL
    )


async def get_character_active_session(
    character_id: int,
) -> Optional[int]:
    """Get the session_id a character is currently in, or None."""
    rds = await get_redis()
    raw: Optional[str] = await rds.get(_active_session_key(character_id))
    if raw is None:
        return None
    return int(raw)


async def clear_character_active_session(character_id: int) -> None:
    """Remove the active session marker for a character."""
    rds = await get_redis()
    await rds.delete(_active_session_key(character_id))


# ---------- group inventory cache --------------------------------------------

async def set_session_inventory(session_id: int, items: list) -> None:
    """Cache the group inventory for a session."""
    rds = await get_redis()
    await rds.set(
        _inventory_key(session_id), json.dumps(items), ex=SESSION_TTL
    )


async def get_session_inventory(session_id: int) -> Optional[list]:
    """Get cached group inventory, or None if not set."""
    rds = await get_redis()
    raw: Optional[str] = await rds.get(_inventory_key(session_id))
    if raw is None:
        return None
    return json.loads(raw)


# ---------- cleanup ----------------------------------------------------------

async def cleanup_session(
    session_id: int, member_character_ids: list
) -> None:
    """
    Delete all Redis keys associated with a session:
    - session state
    - session inventory
    - active_session markers for all members
    """
    rds = await get_redis()

    keys_to_delete = [
        _state_key(session_id),
        _inventory_key(session_id),
    ]
    for cid in member_character_ids:
        keys_to_delete.append(_active_session_key(cid))

    if keys_to_delete:
        await rds.delete(*keys_to_delete)
