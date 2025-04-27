from fastapi import FastAPI
from config import settings
import aioredis, asyncio

app = FastAPI()

# пример подписки на Redis‑канал (Health‑check)
@app.on_event("startup")
async def startup():
    app.state.redis = await aioredis.from_url(settings.REDIS_URL)
    # подписка, чтобы не оставлять пустым
    async def reader():
        sub = app.state.redis.pubsub()
        await sub.subscribe("battle:0:your_turn")
        async for msg in sub.listen():
            break
    asyncio.create_task(reader())

@app.get("/health")
async def health():
    # проверка HTTP и Redis
    pong = await app.state.redis.ping()
    return {"status": "ok", "redis_pong": pong}
