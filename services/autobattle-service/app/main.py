from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any, Dict, Set

import aioredis
import uvicorn
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from clients import get_battle_state, post_battle_action
from config import settings
from strategy import Strategy

# ──────────────────────  logging  ──────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("auto-battle")

# ──────────────────────  FastAPI  ──────────────────────
app = FastAPI(title="Auto-Battle AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://4452515-co41851.twc1.net",
        "http://4452515-co41851.twc1.net:5173",
        "http://4452515-co41851.twc1.net:5555",
        "http://4452515-co41851.twc1.net:8005",
        "http://4452515-co41851.twc1.net:8004",
        "http://4452515-co41851.twc1.net:8003",
        "http://4452515-co41851.twc1.net:8002",
        "http://4452515-co41851.twc1.net:8001",
        "http://4452515-co41851.twc1.net:8000",
        "http://localhost",
        "http://localhost:8000",
        "http://localhost:8001",
        "http://localhost:8002",
        "http://localhost:8003",
        "http://localhost:8004",
        "http://localhost:8005",
        "http://localhost:5555",
                    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
strategy = Strategy()

# ──────────────────────  runtime state  ──────────────────────
class RuntimeState:
    redis: aioredis.Redis                        # подключение к Redis
    allowed: Set[int] = set()                    # pid, за которые играет бот
    pid_battle_map: Dict[int, int] = {}          # pid → последний battle_id

app.state = RuntimeState()  # type: ignore[attr-defined]

# ──────────────────────  models  ──────────────────────
class ModePayload(BaseModel):
    mode: str  # attack / defense / balance


class RegisterPayload(BaseModel):
    participant_id: int
    battle_id: int = 0   # можно не знать battle_id (0 = определить позднее)


# ──────────────────────  startup  ──────────────────────
@app.on_event("startup")
async def on_startup() -> None:
    app.state.redis = await aioredis.from_url(
        settings.REDIS_URL, decode_responses=True
    )
    asyncio.create_task(_redis_reader())
    log.info("auto-battle started, mode=%s", strategy.mode)


async def _redis_reader() -> None:
    """
    Слушаем battle:*:your_turn и запускаем handle_turn,
    если pid зарегистрирован в allowed.
    """
    pub = app.state.redis.pubsub()
    await pub.psubscribe("battle:*:your_turn")

    async for msg in pub.listen():
        if msg["type"] != "pmessage":
            continue

        try:
            battle_id = int(msg["channel"].split(":")[1])
            participant_id = int(msg["data"])
            log.debug("⏺  msg from Redis  battle=%s  pid=%s", battle_id, participant_id)
        except (ValueError, IndexError):
            continue

        # запоминаем «последний обнаруженный» бой для pid
        app.state.pid_battle_map[participant_id] = battle_id

        # делаем ход, только если бот включён
        if participant_id in app.state.allowed:
            asyncio.create_task(handle_turn(battle_id, participant_id))


# ──────────────────────  REST-API  ──────────────────────
@app.get("/health")
async def health() -> Dict[str, Any]:
    pong = await app.state.redis.ping()
    return {
        "status": "ok",
        "redis": pong,
        "mode": strategy.mode,
        "allowed": list(app.state.allowed),
    }


@app.post("/mode")
def set_mode(p: ModePayload):
    try:
        strategy.set_mode(p.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "mode": strategy.mode}


@app.post("/register")
async def register(p: RegisterPayload):
    """
    Включаем автобой для participant_id.
    Если battle_id=0  → ждём первого сообщения your_turn.
    Если battle_id передан  → сразу проверяем, не пора ли ходить.
    """
    app.state.allowed.add(p.participant_id)

    if p.battle_id:
        app.state.pid_battle_map[p.participant_id] = p.battle_id

    # пробуем сразу сделать ход, если уже очередь этого pid
    battle_id = app.state.pid_battle_map.get(p.participant_id)
    if battle_id:
        ctx = await get_battle_state(battle_id)
        if ctx["runtime"]["current_actor"] == p.participant_id:
            asyncio.create_task(handle_turn(battle_id, p.participant_id))

    return {"ok": True, "allowed": list(app.state.allowed)}


@app.post("/unregister")
def unregister(participant_id: int = Body(..., embed=True)):
    """Выключаем автобой для participant_id."""
    app.state.allowed.discard(participant_id)
    return {"ok": True, "allowed": list(app.state.allowed)}


# ──────────────────────  core  ──────────────────────
async def handle_turn(battle_id: int, participant_id: int) -> None:
    """
    Один «авто-ход».
    """
    try:
        ctx = await get_battle_state(battle_id)
        if ctx["runtime"]["current_actor"] != participant_id:
            log.debug("skip: not my turn (battle %s, pid %s)", battle_id, participant_id)
            return  # ход уже сделали вручную

        skills, item_id = strategy.select_actions(ctx)
        payload = {
            "participant_id": participant_id,
            "skills": skills,
        }
        if item_id:
            payload["skills"]["item_id"] = item_id

        res = await post_battle_action(battle_id, payload)

        log.info(
            "battle=%s turn=%s pid=%s ok=%s",
            battle_id, res["turn_number"], participant_id, res["ok"]
        )

    except Exception as exc:  # pylint: disable=broad-except
        log.error("handle_turn error: %s", exc)
        log.error("TRACE:\n%s", traceback.format_exc())


# ──────────────────────  cli run  ──────────────────────
if __name__ == "__main__":  # pragma: no cover
    uvicorn.run("main:app", host="0.0.0.0", port=8020, reload=False)
