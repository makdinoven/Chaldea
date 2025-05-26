# main.py  ────────────────────────────────────────────────────────
"""
Микросервис «автобой» на FastAPI.
 • подписывается на Redis battle:*:your_turn
 • ходит только за participant_id, зарегистрированные через /register
"""

import asyncio
import logging
from typing import Dict, Set, TypedDict

import aioredis
from fastapi import Body, FastAPI, HTTPException

from clients import get_battle_state, post_battle_action
from config import settings
from strategy import Strategy

# ───────────────────────────────
# Логирование
# ───────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("auto-battle")

# ───────────────────────────────
# FastAPI-приложение
# ───────────────────────────────
app = FastAPI(title="Auto-Battle AI")
strategy = Strategy()

# ───────────────────────────────
# Типизация app.state
# ───────────────────────────────
class State(TypedDict):
    redis: aioredis.Redis
    allowed: Set[int]            # участники, за которых бот играет
    pid_battle_map: Dict[int, int]  # participant_id → последний battle_id

app.state: State = {             # type: ignore[assignment]
    "redis": None,
    "allowed": set(),
    "pid_battle_map": {},
}

# ───────────────────────────────
# STARTUP  (можно оставить on_event, IDE-warning безопасен)
# ───────────────────────────────
@app.on_event("startup")
async def startup() -> None:
    """
    • Создаём Redis-клиент.
    • Подписываемся на battle:*:your_turn.
    """
    app.state["redis"] = await aioredis.from_url(
        settings.REDIS_URL, decode_responses=True
    )

    async def reader() -> None:
        sub = app.state["redis"].pubsub()
        await sub.psubscribe("battle:*:your_turn")
        async for msg in sub.listen():
            if msg["type"] != "pmessage":
                continue
            battle_id = int(msg["channel"].split(":")[1])
            participant_id = int(msg["data"])
            app.state["pid_battle_map"][participant_id] = battle_id
            if participant_id in app.state["allowed"]:
                asyncio.create_task(handle_turn(battle_id, participant_id))

    asyncio.create_task(reader())
    log.info("auto-battle started. mode=%s", strategy.mode)

# ───────────────────────────────
# Хелпер: получить state по participant_id
# ───────────────────────────────
async def get_battle_state_of_pid(pid: int):
    """Ищем последний известный battle_id -> state; None если не знаем."""
    battle_id = app.state["pid_battle_map"].get(pid)
    if battle_id is None:
        return None
    try:
        state = await get_battle_state(battle_id)
        state["battle_id"] = battle_id
        return state
    except Exception:  # сеть упала / бой закончился
        return None

# ───────────────────────────────
# REST-эндпоинты
# ───────────────────────────────
@app.get("/health")
async def health():
    pong = await app.state["redis"].ping()
    return {
        "status": "ok",
        "redis": pong,
        "mode": strategy.mode,
        "allowed": list(app.state["allowed"]),
    }

@app.post("/mode")
async def set_mode(mode: str = Body(..., embed=True)):
    try:
        strategy.set_mode(mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "mode": strategy.mode}

@app.post("/register")
async def register(participant_id: int = Body(..., embed=True)):
    app.state["allowed"].add(participant_id)
    # возможно, прямо сейчас очередь уже за этим персонажем
    ctx = await get_battle_state_of_pid(participant_id)
    if ctx and ctx["runtime"]["current_actor"] == participant_id:
        asyncio.create_task(handle_turn(ctx["battle_id"], participant_id))
    return {"ok": True, "allowed": list(app.state["allowed"])}

@app.post("/unregister")
async def unregister(participant_id: int = Body(..., embed=True)):
    app.state["allowed"].discard(participant_id)
    return {"ok": True, "allowed": list(app.state["allowed"])}

# ───────────────────────────────
# Один ход
# ───────────────────────────────
async def handle_turn(battle_id: int, participant_id: int) -> None:
    try:
        state = await get_battle_state(battle_id)
        if state["runtime"]["current_actor"] != participant_id:
            return  # кто-то уже походил вручную

        skills, item_id = strategy.select_actions(state)
        payload = {"participant_id": participant_id, "skills": skills}
        if item_id:
            payload["skills"]["item_id"] = item_id

        res = await post_battle_action(battle_id, payload)
        log.info(
            "[battle %s] turn=%s actor=%s ok=%s",
            battle_id,
            res["turn_number"],
            participant_id,
            res["ok"],
        )
    except Exception as exc:  # pylint: disable=broad-except
        log.error("handle_turn: %s", exc)

# ───────────────────────────────
# CLI-запуск
# ───────────────────────────────
if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8020)
