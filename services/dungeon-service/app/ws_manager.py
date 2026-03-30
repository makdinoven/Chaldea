"""
WebSocket connection manager for dungeon-service.

Manages per-session connections: session_id -> { user_id -> WebSocket }
Follows battle-service ws_manager.py pattern.
"""

import logging
from typing import List
from fastapi import WebSocket

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# State
# ──────────────────────────────────────────────

# All active WS connections: session_id -> { user_id -> WebSocket }
session_connections: dict[int, dict[int, WebSocket]] = {}


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

async def connect(session_id: int, user_id: int, websocket: WebSocket) -> None:
    """
    Register a new WS connection for a specific dungeon session.
    If the user already has a connection to this session, close the old one first
    (max 1 connection per user per session).
    """
    if session_id not in session_connections:
        session_connections[session_id] = {}

    # Close existing connection if any
    old_ws = session_connections[session_id].get(user_id)
    if old_ws is not None:
        await _close_ws_safe(old_ws)

    session_connections[session_id][user_id] = websocket
    logger.info("WS: user %d connected to dungeon session %d", user_id, session_id)


async def disconnect(session_id: int, user_id: int) -> None:
    """
    Remove user from session connections.
    Closes the WebSocket gracefully.
    """
    conns = session_connections.get(session_id)
    if conns is None:
        return

    ws = conns.pop(user_id, None)
    if ws is not None:
        await _close_ws_safe(ws)

    # Clean up empty session dict
    if not conns:
        session_connections.pop(session_id, None)

    logger.info("WS: user %d disconnected from dungeon session %d", user_id, session_id)


async def broadcast_to_session(session_id: int, data: dict) -> None:
    """
    Send JSON data to all users connected to a specific dungeon session.
    Removes stale connections that fail to send.
    """
    conns = session_connections.get(session_id)
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
        logger.info(
            "WS: removed stale connection for user %d in dungeon session %d",
            uid, session_id,
        )

    # Clean up empty session dict
    if not conns:
        session_connections.pop(session_id, None)


async def send_to_user(session_id: int, user_id: int, message: dict) -> bool:
    """
    Send JSON data to a specific user in a dungeon session.
    Returns True if sent successfully, False otherwise.
    """
    conns = session_connections.get(session_id)
    if not conns:
        return False

    ws = conns.get(user_id)
    if ws is None:
        return False

    ok = await _send_json_safe(ws, message)
    if not ok:
        # Remove stale connection
        conns.pop(user_id, None)
        if not conns:
            session_connections.pop(session_id, None)
        logger.info(
            "WS: removed stale connection for user %d in dungeon session %d",
            user_id, session_id,
        )
    return ok


async def cleanup_session(session_id: int) -> None:
    """
    Close all WebSocket connections for a dungeon session and remove
    the session from the dict. Called when a session finishes.
    """
    conns = session_connections.pop(session_id, None)
    if not conns:
        return

    for uid, ws in conns.items():
        await _close_ws_safe(ws)

    logger.info(
        "WS: cleaned up all connections for dungeon session %d (%d connections)",
        session_id, len(conns),
    )


def get_connected_users(session_id: int) -> List[int]:
    """Return list of user_ids currently connected to a dungeon session."""
    conns = session_connections.get(session_id)
    if not conns:
        return []
    return list(conns.keys())
