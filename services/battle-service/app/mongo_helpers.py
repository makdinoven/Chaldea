# battle_service/mongo_helpers.py
from datetime import datetime
from typing import Sequence

from motor.motor_asyncio import AsyncIOMotorDatabase
from mongo_client import get_mongo_db


def _db(db: AsyncIOMotorDatabase | None = None) -> AsyncIOMotorDatabase:
    return db or get_mongo_db("game")


async def save_snapshot(battle_id: int,
                        participants: Sequence[dict],
                        db: AsyncIOMotorDatabase | None = None) -> None:
    await _db(db).battle_snapshots.insert_one(
        {
            "battle_id": battle_id,
            "created_at": datetime.utcnow(),
            "participants": list(participants),
        }
    )


async def load_snapshot(battle_id: int,
                        db: AsyncIOMotorDatabase | None = None) -> dict | None:
    return await _db(db).battle_snapshots.find_one({"battle_id": battle_id})
