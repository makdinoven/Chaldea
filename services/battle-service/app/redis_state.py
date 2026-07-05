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
import os
from datetime import datetime
from typing import Dict, List, Optional

import redis.asyncio as redis

from config import settings

KEY_BATTLE_SNAPSHOT = "battle:{id}:snapshot"      # hash
KEY_BATTLE_TURNS    = "battle:{id}:turns"         # zset turn_number → 1

SNAPSHOT_TTL = 24 * 3600   # сек – сутки
STATE_TTL_HOURS = int(os.getenv("BATTLE_STATE_TTL_HOURS", 48))
STATE_TTL = STATE_TTL_HOURS * 3600

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


# ---------- очередь ходов --------------------------------------------------
def build_hybrid_turn_order(
    participants_payload: List[Dict],
    first_actor_participant_id: int,
) -> List[int]:
    """Initiative-based turn order, fixed once at battle start (FEAT-143).

    Rules:
      * the initiator (``first_actor_participant_id``, whoever started the fight)
        always takes slot 1, regardless of stats;
      * everyone else is ordered by DESCENDING initiative (a weighted stat sum:
        agility×1.0 + strength/intelligence/endurance×0.75 — so agile builds are
        naturally faster, but a high-total-stat bruiser can still out-tempo them);
      * ties break by agility, then by participant creation order (payload order);
      * teams do NOT alternate — a fast side may act several times in a row (the
        first-cycle one-skill restriction keeps that from snowballing);
      * computed once and never recomputed mid-battle — stat buffs do not
        reshuffle the queue, and dead members simply skip their slot.

    ``participants_payload`` entries must carry ``participant_id`` plus a
    precomputed ``initiative`` (and ``agility`` for tie-breaks). Returns an
    ordered list of ``participant_id``; ``order[0]`` is always the initiator.
    """
    initiative_of: Dict[int, float] = {}
    agility_of: Dict[int, float] = {}
    creation_index: Dict[int, int] = {}
    all_pids: List[int] = []
    for i, p in enumerate(participants_payload):
        pid = p["participant_id"]
        all_pids.append(pid)
        initiative_of[pid] = p.get("initiative", 0)
        agility_of[pid] = p.get("agility", 0)
        creation_index[pid] = i

    rest = [pid for pid in all_pids if pid != first_actor_participant_id]
    rest.sort(
        key=lambda pid: (-initiative_of[pid], -agility_of[pid], creation_index[pid])
    )
    lead = [first_actor_participant_id] if first_actor_participant_id in initiative_of else []
    return lead + rest


def compute_initiative(attributes: Dict) -> float:
    """Initiative score from a character's attributes (FEAT-143).

    Agility counts full (×1.0); strength and intelligence count at ×0.75.
    Endurance / luck / charisma do NOT contribute. So agility builds lead by
    default, but a warrior/mage with a much larger str/int pool can still
    out-initiative a rogue.
    """
    agi = attributes.get("agility", 0) or 0
    other = (attributes.get("strength", 0) or 0) + (attributes.get("intelligence", 0) or 0)
    return agi * 1.0 + other * 0.75


# ---------- инициализация --------------------------------------------------
async def init_battle_state(
    battle_id: int,
    participants_payload: List[Dict],   # [{participant_id, character_id, team}]
    first_actor_participant_id: int,
    deadline_at: datetime,
    location_id: int = None,
) -> None:
    """
    Создаём начальное состояние боя:
    • turn_number = 0
    • next_actor  = participant_id, который ходит первым
    • участники — словарь id → ресурсы (пока статика)
    """
    redis_client = await get_redis_client()

    # Hybrid initiative order (FEAT-143). Both turn advancement and the "next up"
    # preview read this single list, so they can never disagree.
    turn_order = build_hybrid_turn_order(
        participants_payload, first_actor_participant_id
    )

    # cформируем JSON-словарь состояния
    battle_state: Dict = {
        "turn_number": 0,
        "deadline_at": deadline_at.isoformat(),
        "next_actor": first_actor_participant_id,
        "first_actor": first_actor_participant_id,  # ← кто начинает
        "turn_order": turn_order,
        # Location where the fight happens — used to resolve co-located squadmates
        # for the party XP bonus (FEAT-144 Ф2).
        "location_id": location_id,
        # First cycle (FEAT-143): from the initiator's first turn until their
        # next turn, everyone may use only ONE skill type per turn. Unlocks once
        # the turn returns to the initiator.
        "first_cycle": True,
        "initiator_acted_once": False,
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
            "fast_slots": p["fast_slots"],
            "cooldowns"  : {},
            "total_damage_dealt": 0,
            "total_damage_received": 0,
            "equipment_durability": p.get("equipment_durability", {}),
            }
    for p in participants_payload
        },
    }

    # пишем состояние
    await redis_client.set(state_key(battle_id), json.dumps(battle_state), ex=STATE_TTL)
    print("[REDIS] write state", state_key(battle_id))

    # добавляем дедлайн первого хода в ZSET
    member = f"{battle_id}:{first_actor_participant_id}"
    await redis_client.zadd(ZSET_DEADLINES, {member: deadline_at.timestamp()})

    # уведомляем первого игрока / автобоя
    await redis_client.publish(
        f"battle:{battle_id}:your_turn",
        str(first_actor_participant_id),
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
    await redis_client.set(state_key(battle_id), json.dumps(state), ex=STATE_TTL)

async def cache_snapshot(rds, battle_id: int, snapshot: dict) -> None:
    key = KEY_BATTLE_SNAPSHOT.format(id=battle_id)
    # Redis hash → сохраняем сразу целиком «как строку»
    await rds.set(key, json.dumps(snapshot), ex=SNAPSHOT_TTL)

async def get_cached_snapshot(rds, battle_id: int) -> dict | None:
    key = KEY_BATTLE_SNAPSHOT.format(id=battle_id)
    data = await rds.get(key)
    return json.loads(data) if data else None
