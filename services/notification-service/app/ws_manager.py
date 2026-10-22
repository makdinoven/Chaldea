# ws_manager.py

import asyncio
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Chat channels
# ──────────────────────────────────────────────

CHAT_CHANNELS = ("general", "trade", "help")

# ──────────────────────────────────────────────
# State
# ──────────────────────────────────────────────

# All active WS connections: user_id -> set of WebSocket.
# A user may have several connections open at once (multiple browser tabs);
# every tab gets its own socket and all of them receive broadcasts.
active_connections: dict[int, set[WebSocket]] = {}

# Login session (`sid` claim of the handshake token) of each socket, so a
# revoked session can have exactly its sockets closed. None = legacy token
# issued before sessions existed.
socket_sessions: dict[WebSocket, str | None] = {}

# Close code sent to sockets whose session was revoked. The frontend treats
# 4001 as "unauthorized": it tries a token refresh, which fails, and logs out.
SESSION_REVOKED_CLOSE_CODE = 4001

# Channel subscriptions: channel_name -> set(user_id)
channel_subscriptions: dict[str, set[int]] = {ch: set() for ch in CHAT_CHANNELS}

# Reference to the main asyncio event loop (set in connect())
_loop: asyncio.AbstractEventLoop | None = None


# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────

async def _send_json_safe(ws: WebSocket, data: dict) -> None:
    """Send JSON to a WebSocket, silently handling stale/closed connections."""
    try:
        await ws.send_json(data)
    except Exception:
        pass


async def _close_ws_safe(ws: WebSocket) -> None:
    """Close a WebSocket gracefully, ignoring errors."""
    try:
        await ws.close()
    except Exception:
        pass


def _sockets_for(user_id: int) -> list[WebSocket]:
    """Snapshot of the user's current sockets (safe to iterate while mutating)."""
    conns = active_connections.get(user_id)
    return list(conns) if conns else []


def is_online(user_id: int) -> bool:
    """True if the user has at least one active WebSocket connection."""
    return bool(active_connections.get(user_id))


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

async def connect(user_id: int, websocket: WebSocket, session_id: str | None = None) -> None:
    """
    Register a new WS connection for the user. Multiple connections per user
    are allowed (e.g. several tabs) — the socket is added to the user's set,
    existing sockets are kept open. Subscribes the user to all chat channels.
    `session_id` is the login session the handshake token belongs to.
    """
    global _loop
    _loop = asyncio.get_event_loop()

    active_connections.setdefault(user_id, set()).add(websocket)
    socket_sessions[websocket] = session_id

    # Subscribe to all chat channels
    for channel in CHAT_CHANNELS:
        channel_subscriptions[channel].add(user_id)

    logger.info(
        "WS: user %d connected (%d active socket(s))",
        user_id,
        len(active_connections.get(user_id, ())),
    )


async def disconnect(user_id: int, websocket: WebSocket | None = None) -> None:
    """
    Remove a connection for the user.

    If `websocket` is given, only that socket is removed; the user stays
    subscribed as long as they have other open sockets. If `websocket` is
    None, all of the user's sockets are closed and removed (full teardown).
    Channel subscriptions are dropped only once the user's last socket closes.
    """
    conns = active_connections.get(user_id)
    if conns is None:
        return

    if websocket is None:
        for ws in list(conns):
            socket_sessions.pop(ws, None)
            await _close_ws_safe(ws)
        conns.clear()
    else:
        conns.discard(websocket)
        socket_sessions.pop(websocket, None)
        await _close_ws_safe(websocket)

    if not conns:
        active_connections.pop(user_id, None)
        for channel in CHAT_CHANNELS:
            channel_subscriptions[channel].discard(user_id)
        logger.info("WS: user %d fully disconnected", user_id)
    else:
        logger.info(
            "WS: user %d closed one socket (%d remaining)", user_id, len(conns)
        )


async def close_revoked_sessions(
    user_id: int,
    session_ids: list[str] | None = None,
    all_except: str | None = None,
) -> int:
    """
    Close the user's sockets that belong to revoked login sessions, with
    close code 4001. Returns how many sockets were closed.

    - session_ids: close sockets opened with tokens of these sessions only;
    - all_except: close every socket except those of this session — sockets
      opened with legacy tokens (no session) are closed too. With
      all_except=None every socket of the user is closed.
    Pass at most one of the two (the caller validates that).
    """
    revoked = set(session_ids) if session_ids is not None else None
    closed = 0
    for ws in _sockets_for(user_id):
        sid = socket_sessions.get(ws)
        if revoked is not None:
            if sid is None or sid not in revoked:
                continue
        elif all_except is not None and sid == all_except:
            continue
        try:
            await ws.close(code=SESSION_REVOKED_CLOSE_CODE, reason="Session revoked")
        except Exception:
            pass
        # Drop it from the registry; the endpoint's own finally-block will
        # call disconnect() again, which is a no-op for an unknown socket.
        await disconnect(user_id, ws)
        closed += 1
    if closed:
        logger.info("WS: closed %d socket(s) of user %d (session revoked)", closed, user_id)
    return closed


def send_to_user(user_id: int, data: dict) -> None:
    """
    Send JSON data to all of a user's active connections.
    Thread-safe: uses asyncio.run_coroutine_threadsafe for calls from
    RabbitMQ consumer threads. Handles exceptions silently (stale connections).
    """
    sockets = _sockets_for(user_id)
    if not sockets:
        return

    loop = _loop
    if loop is None:
        logger.warning("WS: no event loop available for send_to_user")
        return

    for ws in sockets:
        asyncio.run_coroutine_threadsafe(_send_json_safe(ws, data), loop)


def broadcast_to_channel(channel: str, data: dict) -> None:
    """
    Send data to all sockets of all users subscribed to the given channel.
    Thread-safe: uses asyncio.run_coroutine_threadsafe.
    """
    subscriber_ids = channel_subscriptions.get(channel)
    if not subscriber_ids:
        return

    loop = _loop
    if loop is None:
        logger.warning("WS: no event loop available for broadcast_to_channel")
        return

    for uid in list(subscriber_ids):
        sockets = _sockets_for(uid)
        if not sockets:
            channel_subscriptions[channel].discard(uid)
            continue
        for ws in sockets:
            asyncio.run_coroutine_threadsafe(_send_json_safe(ws, data), loop)


def broadcast_to_all(data: dict) -> None:
    """
    Send data to ALL active sockets of all users.
    Thread-safe: uses asyncio.run_coroutine_threadsafe.
    """
    if not active_connections:
        return

    loop = _loop
    if loop is None:
        logger.warning("WS: no event loop available for broadcast_to_all")
        return

    for uid in list(active_connections.keys()):
        for ws in _sockets_for(uid):
            asyncio.run_coroutine_threadsafe(_send_json_safe(ws, data), loop)
