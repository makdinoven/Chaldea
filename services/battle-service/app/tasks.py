import os, motor.motor_asyncio, datetime
from celery import Celery

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
celery_app = Celery("battle_tasks", broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1"))

@celery_app.task
def save_log(battle_id: int, turn_number: int, events: list[dict]):
    """
    Асинхронно складывает логи в MongoDB (коллекция `battle_logs`).
    """
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    coll = client.game.battle_logs
    doc = {
        "battle_id": battle_id,
        "turn_number": turn_number,
        "events": events,
        "timestamp": datetime.datetime.utcnow(),
    }
    # motor – async; внутри Celery синхронно через loop.run_until_complete
    import asyncio, contextlib
    loop = asyncio.get_event_loop()
    with contextlib.suppress(RuntimeError):
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    loop.run_until_complete(coll.insert_one(doc))
