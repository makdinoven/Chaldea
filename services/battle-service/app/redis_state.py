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
from typing import Dict, List, Optional

import redis.asyncio as redis

from config import settings

KEY_BATTLE_SNAPSHOT = "battle:{id}:snapshot"      # hash
KEY_BATTLE_TURNS    = "battle:{id}:turns"         # zset turn_number → 1

SNAPSHOT_TTL = 24 * 3600   # сек – сутки

# singleton-клиент, чтобы не открывать соединения при каждом вызове
_redis_client: redis.Redis | None = None


async def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await _redis_client.execute_command("CLIENT", "SETNAME", "battle-service")
        # Если accidental replica – валимся с явной ошибкой
        role = await _redis_client.info("replication")
        if role["role"] != "master":
            raise RuntimeError("Connected to Redis replica, need master")
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
        "active_effects": {},
        "participants": {
        str(p["participant_id"]): {
            "character_id": p["character_id"],
            "team"       : p["team"],
            "hp"         : p["hp"],
            "mana"       : p["mana"],
            "energy"     : p["energy"],
            "stamina"    : p["stamina"],
            "max_hp"     : p["max_hp"],
            "max_mana"   : p["max_mana"],
            "max_energy" : p["max_energy"],
            "max_stamina": p["max_stamina"],
            "cooldowns"  : {},
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
async def load_state(battle_id: int) -> Optional[Dict]:
    """
    Читает JSON-state из Redis, добавляет:
        • total_turns – сколько ходов было,
        • last_turn   – номер последнего хода.
    """
    redis = await get_redis_client()

    raw_json: str | None = await redis.get(state_key(battle_id))
    if raw_json is None:
        return None          # ещё не инициировали бой

    raw_state: Dict = json.loads(raw_json)

    turn_ids: list[bytes] = await redis.zrange(
        KEY_BATTLE_TURNS.format(id=battle_id), 0, -1
    )
    total_turns = len(turn_ids)
    last_turn   = int(turn_ids[-1]) if turn_ids else 0

    raw_state.update({"total_turns": total_turns, "last_turn": last_turn})
    return raw_state

async def save_state(battle_id: int, state: Dict) -> None:
    """Перезаписать состояние боя целиком."""
    redis_client = await get_redis_client()
    await redis_client.set(state_key(battle_id), json.dumps(state))

async def cache_snapshot(rds, battle_id: int, snapshot: dict) -> None:
    key = KEY_BATTLE_SNAPSHOT.format(id=battle_id)
    # Redis hash → сохраняем сразу целиком «как строку»
    await rds.set(key, json.dumps(snapshot), ex=SNAPSHOT_TTL)

async def get_cached_snapshot(rds, battle_id: int) -> dict | None:
    key = KEY_BATTLE_SNAPSHOT.format(id=battle_id)
    data = await rds.get(key)
    return json.loads(data) if data else None
