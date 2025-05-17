"""
Храним «текущее» состояние боя в Redis:
  • ключ  battle:{battle_id}:state      — JSON-словарь со счётчиком ходов,
    очередью участников, их текущими ресурсами.
  • ZSET  battle:deadlines              — элементы вида
       member = "{battle_id}:{participant_id}",
       score  = unix-timestamp дедлайна.
  • Pub/Sub канал battle:{battle_id}:your_turn – сообщение next_actor_id.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List

import redis.asyncio as redis

from config import settings

# singleton-клиент, чтобы не открывать соединения при каждом вызове
_redis_client: redis.Redis | None = None


async def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL,
                                       decode_responses=True)
        # если вдруг подключились к реплике кластера – включаем запись
        try:
            await _redis_client.execute_command("READWRITE")
        except redis.ResponseError:
            pass         # обычный одиночный Redis вернёт ERR unknown command
    return _redis_client


# ---------- ключевые генераторы -------------------------------------------
def state_key(battle_id: int) -> str:
    return f"battle:{battle_id}:state"


ZSET_DEADLINES: str = "battle:deadlines"      # один ZSET на все бои


# ---------- инициализация --------------------------------------------------
async def init_battle_state(
    battle_id: int,
    participants_payload: List[Dict],   # [{participant_id, character_id, team}]
    first_actor_participant_id: int,
    deadline_at: datetime,
) -> None:
    """
    Создаём начальное состояние боя:
    • turn_number = 0
    • next_actor  = participant_id, который ходит первым
    • участники — словарь id → ресурсы (пока статика)
    """
    redis_client = await get_redis_client()

    # cформируем JSON-словарь состояния
    battle_state: Dict = {
        "turn_number": 0,
        "next_actor": first_actor_participant_id,
        "participants": {
            str(p["participant_id"]): {
                "character_id": p["character_id"],
                "team": p["team"],
                # базовые текущие ресурсы — позже заменим реальными атрибутами
                "hp": 100,
                "mana": 75,
                "energy": 50,
                "stamina": 50,
            }
            for p in participants_payload
        },
    }

    # пишем состояние
    await redis_client.set(state_key(battle_id), json.dumps(battle_state))
    print("[REDIS] write state", state_key(battle_id))

    # добавляем дедлайн первого хода в ZSET
    member = f"{battle_id}:{first_actor_participant_id}"
    await redis_client.zadd(ZSET_DEADLINES, {member: deadline_at.timestamp()})

    # уведомляем первого игрока / автобоя
    await redis_client.publish(
        f"battle:{battle_id}:your_turn",
        json.dumps(battle_state),
    )


# ---------- вспомогательные операции --------------------------------------
async def load_state(battle_id: int) -> Dict | None:
    """Получить текущее состояние боя из Redis (dict) или None."""
    redis_client = await get_redis_client()
    raw_json: str | None = await redis_client.get(state_key(battle_id))
    return json.loads(raw_json) if raw_json else None


async def save_state(battle_id: int, state: Dict) -> None:
    """Перезаписать состояние боя целиком."""
    redis_client = await get_redis_client()
    await redis_client.set(state_key(battle_id), json.dumps(state))
