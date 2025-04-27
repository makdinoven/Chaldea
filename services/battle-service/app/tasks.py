import asyncio, contextlib
import os
from datetime import datetime
from celery import Celery
from mongo_client import get_db

celery_app = Celery("battle_tasks", broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1"))

@celery_app.task
def save_log(battle_id: int, turn_number: int, events: list[dict]):
    db = get_db()                         # AsyncIOMotorDatabase
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
