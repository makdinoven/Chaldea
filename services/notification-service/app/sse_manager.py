# sse_manager.py

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Notification SSE (existing unicast connections)
# ──────────────────────────────────────────────

# Глобальный словарь: user_id -> asyncio.Queue()
connections = {}

def send_to_sse(user_id: int, data: dict):
    """
    Отправляем уведомление 'data' пользователю user_id (если у него есть активное SSE-соединение).
    data сериализуем в JSON, кладём в очередь (queue.put(...)) для этого user_id.
    """
    queue = connections.get(user_id)
    if queue:
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(
            queue.put(json.dumps(data)),
            loop
        )


# ──────────────────────────────────────────────
# Chat SSE (broadcast connections by channel)
# ──────────────────────────────────────────────

CHAT_CHANNELS = ("general", "trade", "help")

# Отдельный словарь для чат-соединений: user_id -> asyncio.Queue()
chat_connections: dict[int, asyncio.Queue] = {}

# Подписки по каналам: channel_name -> set(user_id)
channel_subscriptions: dict[str, set[int]] = {ch: set() for ch in CHAT_CHANNELS}


def add_chat_connection(user_id: int) -> asyncio.Queue:
    """
    Создаёт новую asyncio.Queue для пользователя, сохраняет в chat_connections,
    подписывает пользователя на все 3 канала и возвращает очередь.
    Если у пользователя уже есть соединение — старое заменяется.
    """
    # Если пользователь уже подключён — убираем старое соединение
    if user_id in chat_connections:
        remove_chat_connection(user_id)

    queue: asyncio.Queue = asyncio.Queue(maxsize=256)
    chat_connections[user_id] = queue

    for channel in CHAT_CHANNELS:
        channel_subscriptions[channel].add(user_id)

    logger.info("Chat SSE: user %d connected (channels: %s)", user_id, ", ".join(CHAT_CHANNELS))
    return queue


def remove_chat_connection(user_id: int) -> None:
    """
    Удаляет пользователя из chat_connections и из всех channel_subscriptions.
    Безопасно обрабатывает случай, когда пользователь уже отсутствует.
    """
    chat_connections.pop(user_id, None)

    for channel in CHAT_CHANNELS:
        channel_subscriptions[channel].discard(user_id)

    logger.info("Chat SSE: user %d disconnected", user_id)


def broadcast_to_channel(channel: str, data: dict) -> None:
    """
    Отправляет data (как JSON-строку) во все очереди пользователей,
    подписанных на указанный канал.
    Thread-safe: использует run_coroutine_threadsafe для put в asyncio.Queue
    из sync-контекста (FastAPI sync endpoints работают в thread pool).
    """
    subscriber_ids = channel_subscriptions.get(channel)
    if not subscriber_ids:
        return

    message = json.dumps(data)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        logger.warning("Chat SSE: no event loop available for broadcast")
        return

    for user_id in list(subscriber_ids):
        queue = chat_connections.get(user_id)
        if queue is None:
            remove_chat_connection(user_id)
            continue
        try:
            asyncio.run_coroutine_threadsafe(queue.put(message), loop)
        except Exception:
            logger.exception("Chat SSE: error broadcasting to user %d on channel %s", user_id, channel)


def broadcast_to_all(data: dict) -> None:
    """
    Отправляет data (как JSON-строку) во ВСЕ активные чат-соединения,
    независимо от канала. Используется для событий, которые должны дойти
    до всех (например, chat_message_deleted).
    Thread-safe: использует run_coroutine_threadsafe.
    """
    if not chat_connections:
        return

    message = json.dumps(data)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        logger.warning("Chat SSE: no event loop available for broadcast_to_all")
        return

    for user_id, queue in list(chat_connections.items()):
        try:
            asyncio.run_coroutine_threadsafe(queue.put(message), loop)
        except Exception:
            logger.exception("Chat SSE: error broadcasting to user %d", user_id)
            remove_chat_connection(user_id)
