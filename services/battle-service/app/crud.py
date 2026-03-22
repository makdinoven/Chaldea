# battle-service/app/crud.py
from datetime import datetime, timedelta
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Sequence
from motor.motor_asyncio import AsyncIOMotorDatabase
from mongo_client import get_mongo_db

import models, schemas


DEFAULT_DEADLINE_HOURS = 24


async def create_battle(
    db: AsyncSession,
    player_ids: list[int],
    teams: list[int],) -> tuple[models.Battle, list[models.BattleParticipant]]:

    battle = models.Battle()
    db.add(battle)
    await db.flush()

    participants = []
    for idx, cid in enumerate(player_ids):
        p = models.BattleParticipant(
            battle_id=battle.id,
            character_id=cid,
            team=teams[idx],
        )
        participants.append(p)
    db.add_all(participants)
    await db.commit()
    return battle, participants

async def write_turn(
    db: AsyncSession,
    battle_id: int,
    actor_participant_id: int,
    turn_number: int,
    skills,
    deadline_at,
):
    turn = models.BattleTurn(
        battle_id=battle_id,
        actor_participant_id=actor_participant_id,
        turn_number=turn_number,
        attack_rank_id=skills.attack_rank_id,
        defense_rank_id=skills.defense_rank_id,
        support_rank_id=skills.support_rank_id,
        item_id=skills.item_id,
        deadline_at=deadline_at,
    )
    db.add(turn)
    await db.commit()
    await db.refresh(turn)
    return turn

async def finish_battle(db: AsyncSession, battle_id: int) -> None:
    """Set battle status to 'finished' in MySQL."""
    await db.execute(
        sa.update(models.Battle)
        .where(models.Battle.id == battle_id)
        .values(status=models.BattleStatus.finished)
    )
    await db.commit()


async def get_battle(db: AsyncSession, battle_id: int) -> models.Battle | None:
    result = await db.execute(
        select(models.Battle).where(models.Battle.id == battle_id)
    )
    return result.scalar_one_or_none()

async def get_logs_for_turn(
    battle_id: int,
    turn_number: int,
    db: AsyncIOMotorDatabase | None = None
) -> Sequence[dict]:
    """
    Возвращает все события указанного хода, отсортированные по времени.

    Если `db` не передан, берём дефолтный `game` через get_mongo_db().
    """
    if db is None:                      # ← чтобы не приходилось передавать явно
        db = get_mongo_db("game")

    cursor = db.battle_logs.find(
        {"battle_id": battle_id, "turn_number": turn_number},
        sort=[("timestamp", 1)]         # motor-syntax «sort=[…]»
    )
    return await cursor.to_list(length=None)