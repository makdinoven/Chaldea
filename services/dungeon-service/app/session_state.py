"""
Redis session state management for dungeon-service.

Key schema:
  - dungeon:session:{session_id}:state           — JSON, full session state (48h TTL)
  - dungeon:{dungeon_id}:cooldown                — STRING, session_id (cooldown_hours TTL)
  - dungeon:session:{session_id}:inventory        — JSON, group inventory cache (48h TTL)
  - dungeon:character:{character_id}:active_session — STRING, session_id (48h TTL)
  - dungeon:session:{session_id}:vote:{character_id} — STRING "room_id|choice", a member's say on where to go
  - dungeon:session:{session_id}:ping:{character_id} — STRING, a short rate limit on board marks
  - dungeon:session:{session_id}:challenge:{character_id} — JSON, the minigame a member is playing
  - dungeon:session:{session_id}:busy:{target}     — STRING, character_id of whoever works on it now

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


def _vote_key(session_id: int, character_id: int) -> str:
    return f"dungeon:session:{session_id}:vote:{character_id}"


def _ping_key(session_id: int, character_id: int) -> str:
    return f"dungeon:session:{session_id}:ping:{character_id}"


def _challenge_key(session_id: int, character_id: int) -> str:
    return f"dungeon:session:{session_id}:challenge:{character_id}"


def _shield_key(session_id: int) -> str:
    return f"dungeon_shield:{session_id}"


def _intel_key(session_id: int) -> str:
    return f"dungeon_intel:{session_id}"


def _chat_key(session_id: int) -> str:
    return f"dungeon_chat:{session_id}"


def _say_key(session_id: int, character_id: int) -> str:
    return f"dungeon:session:{session_id}:say:{character_id}"


def _torch_key(session_id: int) -> str:
    return f"dungeon_torch:{session_id}"


def _busy_key(session_id: int, target: str) -> str:
    return f"dungeon:session:{session_id}:busy:{target}"


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
    ttl_seconds = int(cooldown_hours * 3600)
    if ttl_seconds <= 0:
        return
    await rds.set(
        _cooldown_key(dungeon_id), str(session_id), ex=ttl_seconds
    )


async def set_dungeon_cooldown_seconds(
    dungeon_id: int, session_id: int, seconds: int
) -> None:
    """Re-arm the Redis cooldown with an exact remaining time (DB fallback)."""
    if seconds <= 0:
        return
    rds = await get_redis()
    await rds.set(_cooldown_key(dungeon_id), str(session_id), ex=int(seconds))


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


async def clear_dungeon_cooldown(dungeon_id: int) -> bool:
    """Remove cooldown for a dungeon. Returns True if key existed."""
    rds = await get_redis()
    deleted = await rds.delete(_cooldown_key(dungeon_id))
    return deleted > 0


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


# ---------- party votes and marks -------------------------------------------

async def set_vote(session_id: int, character_id: int, room_id: int, choice: str) -> None:
    """A member's say on where the party goes from `room_id` (a new room voids it)."""
    rds = await get_redis()
    await rds.set(_vote_key(session_id, character_id), f"{room_id}|{choice}", ex=SESSION_TTL)


async def get_votes(session_id: int, character_ids: List[int], room_id: int) -> Dict[int, str]:
    """The members' votes cast in `room_id`, by character id."""
    rds = await get_redis()
    votes: Dict[int, str] = {}
    for cid in character_ids:
        raw = await rds.get(_vote_key(session_id, cid))
        if not raw:
            continue
        voted_in, _, choice = raw.partition("|")
        if voted_in == str(room_id):
            votes[cid] = choice
    return votes


async def allow_ping(session_id: int, character_id: int, seconds: int) -> bool:
    """One board mark per member every `seconds`."""
    rds = await get_redis()
    key = _ping_key(session_id, character_id)
    if await rds.get(key):
        return False
    await rds.set(key, "1", ex=seconds)
    return True


# ---------- class challenges (minigames) -------------------------------------

async def set_challenge(session_id: int, character_id: int, challenge: dict, ttl: int) -> None:
    rds = await get_redis()
    await rds.set(_challenge_key(session_id, character_id), json.dumps(challenge), ex=ttl)


async def get_challenge(session_id: int, character_id: int) -> Optional[Dict]:
    rds = await get_redis()
    raw = await rds.get(_challenge_key(session_id, character_id))
    return json.loads(raw) if raw else None


async def delete_challenge(session_id: int, character_id: int) -> None:
    rds = await get_redis()
    await rds.delete(_challenge_key(session_id, character_id))


async def claim_target(session_id: int, target: str, character_id: int, ttl: int) -> Optional[int]:
    """Take a lock (or anything one member works on at a time). Returns None if
    taken now, or the character already at it."""
    rds = await get_redis()
    key = _busy_key(session_id, target)
    holder = await rds.get(key)
    if holder and int(holder) != character_id:
        return int(holder)
    await rds.set(key, str(character_id), ex=ttl)
    return None


async def release_target(session_id: int, target: str, character_id: Optional[int] = None) -> None:
    """Free a target. With `character_id`, only if that member still holds it (it may have lapsed
    and been taken by someone else meanwhile)."""
    rds = await get_redis()
    key = _busy_key(session_id, target)
    if character_id is not None:
        holder = await rds.get(key)
        if holder is None or int(holder) != character_id:
            return
    await rds.delete(key)


async def set_shield(session_id: int, shield: dict) -> None:
    rds = await get_redis()
    await rds.set(_shield_key(session_id), json.dumps(shield), ex=SESSION_TTL)


async def get_shield(session_id: int) -> Optional[Dict]:
    rds = await get_redis()
    raw = await rds.get(_shield_key(session_id))
    return json.loads(raw) if raw else None


async def delete_shield(session_id: int) -> None:
    rds = await get_redis()
    await rds.delete(_shield_key(session_id))


async def get_intel(session_id: int) -> Dict:
    """What the party has learnt of the way ahead: {scouted: {corridor: info}, alerted: [...], disarmed: [...]}."""
    rds = await get_redis()
    raw = await rds.get(_intel_key(session_id))
    intel = json.loads(raw) if raw else {}
    intel.setdefault("scouted", {})
    intel.setdefault("alerted", [])
    intel.setdefault("disarmed", [])
    return intel


async def set_intel(session_id: int, intel: Dict) -> None:
    rds = await get_redis()
    await rds.set(_intel_key(session_id), json.dumps(intel, ensure_ascii=False), ex=SESSION_TTL)


async def push_chat(session_id: int, entry: dict, keep: int) -> None:
    """Add a line to the run's chat and log, keeping the newest `keep`."""
    rds = await get_redis()
    key = _chat_key(session_id)
    await rds.rpush(key, json.dumps(entry, ensure_ascii=False))
    await rds.ltrim(key, -keep, -1)
    await rds.expire(key, SESSION_TTL)


async def get_chat(session_id: int, limit: int) -> List[Dict]:
    rds = await get_redis()
    raw = await rds.lrange(_chat_key(session_id), -limit, -1)
    return [json.loads(r) for r in raw]


async def allow_say(session_id: int, character_id: int, seconds: int) -> bool:
    """One chat line per member every `seconds`."""
    rds = await get_redis()
    key = _say_key(session_id, character_id)
    if await rds.get(key):
        return False
    await rds.set(key, "1", ex=seconds)
    return True


async def set_torch(session_id: int, room_id: int) -> None:
    """A torch burns in this room until the party leaves it."""
    rds = await get_redis()
    await rds.set(_torch_key(session_id), str(room_id), ex=SESSION_TTL)


async def get_torch(session_id: int) -> Optional[int]:
    rds = await get_redis()
    raw = await rds.get(_torch_key(session_id))
    return int(raw) if raw else None


async def delete_torch(session_id: int) -> None:
    rds = await get_redis()
    await rds.delete(_torch_key(session_id))


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
        _shield_key(session_id),
        _torch_key(session_id),
        _chat_key(session_id),
        _intel_key(session_id),
    ]
    for cid in member_character_ids:
        keys_to_delete.append(_active_session_key(cid))
        keys_to_delete.append(_vote_key(session_id, cid))
        keys_to_delete.append(_ping_key(session_id, cid))
        keys_to_delete.append(_challenge_key(session_id, cid))

    if keys_to_delete:
        await rds.delete(*keys_to_delete)
