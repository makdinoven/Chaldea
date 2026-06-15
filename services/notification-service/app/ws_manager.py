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


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

async def connect(user_id: int, websocket: WebSocket) -> None:
    """
    Register a new WS connection for the user. Multiple connections per user
    are allowed (e.g. several tabs) — the socket is added to the user's set,
    existing sockets are kept open. Subscribes the user to all chat channels.
    """
    global _loop
    _loop = asyncio.get_event_loop()

    active_connections.setdefault(user_id, set()).add(websocket)

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
            await _close_ws_safe(ws)
        conns.clear()
    else:
        conns.discard(websocket)
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
