# sse_manager.py

import asyncio
import json

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
