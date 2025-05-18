import asyncio, contextlib
import os
from datetime import datetime
from celery import Celery
from redis_state import get_redis_client, KEY_BATTLE_TURNS
from mongo_client import get_mongo_db
import logging
logger = logging.getLogger(__name__)
celery_app = Celery("battle_tasks", broker=os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672//"))

@celery_app.task
def save_log(battle_id: int, turn_number: int, events: list[dict]):
    logger.debug(f"[MONGO] saving log battle={battle_id} turn={turn_number}")
    db = get_mongo_db()                         # AsyncIOMotorDatabase
    async def _insert():
        await db.battle_logs.insert_one({
            "battle_id":  battle_id,
            "turn_number": turn_number,
            "events":      events,
            "timestamp":   datetime.utcnow(),
        })
    # выполняем корутину в текущем процессе Celery
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(_insert())
    with contextlib.suppress(Exception):
        loop.run_until_complete(
            get_redis_client()
            .zadd(KEY_BATTLE_TURNS.format(id=battle_id), {str(turn_number): 1})
        )
