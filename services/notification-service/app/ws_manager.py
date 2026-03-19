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

# All active WS connections: user_id -> WebSocket
active_connections: dict[int, WebSocket] = {}

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


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

async def connect(user_id: int, websocket: WebSocket) -> None:
    """
    Register a new WS connection. If the user already has a connection,
    close the old one first (max 1 connection per user).
    Subscribes the user to all chat channels.
    """
    global _loop
    _loop = asyncio.get_event_loop()

    # Close existing connection if any
    old_ws = active_connections.get(user_id)
    if old_ws is not None:
        await _close_ws_safe(old_ws)

    active_connections[user_id] = websocket

    # Subscribe to all chat channels
    for channel in CHAT_CHANNELS:
        channel_subscriptions[channel].add(user_id)

    logger.info("WS: user %d connected (channels: %s)", user_id, ", ".join(CHAT_CHANNELS))


async def disconnect(user_id: int) -> None:
    """
    Remove user from active_connections and all channel_subscriptions.
    Closes the WebSocket gracefully.
    """
    ws = active_connections.pop(user_id, None)
    if ws is not None:
        await _close_ws_safe(ws)

    for channel in CHAT_CHANNELS:
        channel_subscriptions[channel].discard(user_id)

    logger.info("WS: user %d disconnected", user_id)


def send_to_user(user_id: int, data: dict) -> None:
    """
    Send JSON data to a specific user.
    Thread-safe: uses asyncio.run_coroutine_threadsafe for calls from
    RabbitMQ consumer threads.
    Handles exceptions silently (stale connections).
    """
    ws = active_connections.get(user_id)
    if ws is None:
        return

    loop = _loop
    if loop is None:
        logger.warning("WS: no event loop available for send_to_user")
        return

    asyncio.run_coroutine_threadsafe(_send_json_safe(ws, data), loop)


def broadcast_to_channel(channel: str, data: dict) -> None:
    """
    Send data to all users subscribed to the given channel.
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
        ws = active_connections.get(uid)
        if ws is None:
            channel_subscriptions[channel].discard(uid)
            continue
        asyncio.run_coroutine_threadsafe(_send_json_safe(ws, data), loop)


def broadcast_to_all(data: dict) -> None:
    """
    Send data to ALL active connections.
    Thread-safe: uses asyncio.run_coroutine_threadsafe.
    """
    if not active_connections:
        return

    loop = _loop
    if loop is None:
        logger.warning("WS: no event loop available for broadcast_to_all")
        return

    for uid, ws in list(active_connections.items()):
        asyncio.run_coroutine_threadsafe(_send_json_safe(ws, data), loop)
