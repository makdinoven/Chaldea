# battle-service/app/crud.py
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

async def get_battle(db: AsyncSession, battle_id: int) -> models.Battle | None:
    result = await db.execute(
        select(models.Battle).where(models.Battle.id == battle_id)
    )
    return result.scalar_one_or_none()
