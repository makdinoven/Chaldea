"""
WebSocket connection manager for battle-service.

Manages per-battle connections: battle_id -> { user_id -> WebSocket }
Follows notification-service ws_manager.py pattern.
"""

import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# State
# ──────────────────────────────────────────────

# All active WS connections: battle_id -> { user_id -> WebSocket }
battle_connections: dict[int, dict[int, WebSocket]] = {}


# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────

async def _send_json_safe(ws: WebSocket, data: dict) -> bool:
    """Send JSON to a WebSocket, silently handling stale/closed connections.
    Returns True on success, False on failure."""
    try:
        await ws.send_json(data)
        return True
    except Exception:
        return False


async def _close_ws_safe(ws: WebSocket) -> None:
    """Close a WebSocket gracefully, ignoring errors."""
    try:
        await ws.close()
    except Exception:
        pass


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

async def connect(battle_id: int, user_id: int, websocket: WebSocket) -> None:
    """
    Register a new WS connection for a specific battle.
    If the user already has a connection to this battle, close the old one first
    (max 1 connection per user per battle).
    """
    if battle_id not in battle_connections:
        battle_connections[battle_id] = {}

    # Close existing connection if any
    old_ws = battle_connections[battle_id].get(user_id)
    if old_ws is not None:
        await _close_ws_safe(old_ws)

    battle_connections[battle_id][user_id] = websocket
    logger.info("WS: user %d connected to battle %d", user_id, battle_id)


async def disconnect(battle_id: int, user_id: int) -> None:
    """
    Remove user from battle connections.
    Closes the WebSocket gracefully.
    """
    conns = battle_connections.get(battle_id)
    if conns is None:
        return

    ws = conns.pop(user_id, None)
    if ws is not None:
        await _close_ws_safe(ws)

    # Clean up empty battle dict
    if not conns:
        battle_connections.pop(battle_id, None)

    logger.info("WS: user %d disconnected from battle %d", user_id, battle_id)


async def broadcast_to_battle(battle_id: int, data: dict) -> None:
    """
    Send JSON data to all users connected to a specific battle.
    Removes stale connections that fail to send.
    """
    conns = battle_connections.get(battle_id)
    if not conns:
        return

    stale_users = []
    for uid, ws in list(conns.items()):
        ok = await _send_json_safe(ws, data)
        if not ok:
            stale_users.append(uid)

    # Clean up stale connections
    for uid in stale_users:
        conns.pop(uid, None)
        logger.info("WS: removed stale connection for user %d in battle %d", uid, battle_id)

    # Clean up empty battle dict
    if not conns:
        battle_connections.pop(battle_id, None)


async def cleanup_battle(battle_id: int) -> None:
    """
    Close all WebSocket connections for a battle and remove the battle from the dict.
    Called when a battle finishes.
    """
    conns = battle_connections.pop(battle_id, None)
    if not conns:
        return

    for uid, ws in conns.items():
        await _close_ws_safe(ws)

    logger.info("WS: cleaned up all connections for battle %d (%d connections)", battle_id, len(conns))
