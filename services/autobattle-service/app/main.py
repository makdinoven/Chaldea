import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

import aioredis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from clients import get_battle_state, post_battle_action
from config import settings
from strategy import Strategy

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("auto-battle")

app = FastAPI(title="Auto-Battle AI")
strategy = Strategy()


# ───────────────────────────────────────────────────────────────
# REST-эндпоинты управления
# ───────────────────────────────────────────────────────────────
class ModePayload(BaseModel):
    mode: str  # attack / defense / balance


@app.post("/mode")
def set_mode(p: ModePayload):
    try:
        strategy.set_mode(p.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "mode": strategy.mode}

@app.post("/register")
async def register(participant_id: int = Body(..., embed=True)):
    """
    Игрок нажал «Автобой». Добавляем id в whitelist
    и сразу же делаем ход, если это уже *его* очередь.
    """
    app.state.allowed.add(participant_id)

    # Проверяем, вдруг сейчас именно его ход
    ctx = await get_battle_state_of_pid(participant_id)
    if ctx and ctx["runtime"]["current_actor"] == participant_id:
        asyncio.create_task(handle_turn(ctx["battle_id"], participant_id))

    return {"ok": True, "allowed": list(app.state.allowed)}

@app.post("/unregister")
async def unregister(participant_id: int = Body(..., embed=True)):
    """Игрок отключил автобой."""
    app.state.allowed.discard(participant_id)
    return {"ok": True, "allowed": list(app.state.allowed)}


@app.get("/health")
async def health():
    pong = await app.state.redis.ping()
    return {"status": "ok", "redis_pong": pong, "mode": strategy.mode}


# ───────────────────────────────────────────────────────────────
# Startup: Redis-подписка на battle:{id}:your_turn
# ───────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    app.state.redis = await aioredis.from_url(settings.REDIS_URL)

    async def reader():
        sub = app.state.redis.pubsub()
        await sub.psubscribe("battle:*:your_turn")
        async for msg in sub.listen():
            if msg["type"] != "pmessage":
                continue
            channel = msg["channel"]  # battle:{id}:your_turn
            payload = msg["data"]
            try:
                battle_id = int(channel.split(":")[1])
                participant_id = int(payload)
            except (ValueError, IndexError):
                continue
            asyncio.create_task(handle_turn(battle_id, participant_id))

    asyncio.create_task(reader())
    log.info("Auto-battle service started. Mode=%s", strategy.mode)


# ───────────────────────────────────────────────────────────────
# Основной цикл одного хода
# ───────────────────────────────────────────────────────────────
async def handle_turn(battle_id: int, participant_id: int):
    """
    Получив сообщение «твой ход», делаем 1 полный цикл:
      • тянем state,
      • выбираем действия,
      • POST /action,
      • логируем.
    """
    try:
        ctx = await get_battle_state(battle_id)
        if ctx["runtime"]["current_actor"] != participant_id:
            # Между подпиской и fetch-ем ход успел сделать соперник.
            return

        skills, item_id = strategy.select_actions(ctx)
        payload = {"participant_id": participant_id, "skills": skills}
        if item_id:
            payload["skills"]["item_id"] = item_id

        res = await post_battle_action(battle_id, payload)
        log.info(
            "[BATTLE %s] turn=%s, actor=%s, actions=%s -> ok=%s",
            battle_id,
            res["turn_number"],
            participant_id,
            payload,
            res["ok"],
        )

    except Exception as e:
        log.error("[BATTLE %s] error: %s", battle_id, e)


# make the module executable
if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8020, reload=False)
