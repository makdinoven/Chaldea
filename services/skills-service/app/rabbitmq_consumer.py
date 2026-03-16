import aio_pika
import asyncio
import json
import logging

from config import settings
from database import async_session
import crud
import schemas

logger = logging.getLogger(__name__)


async def process_message(message: aio_pika.IncomingMessage):
    """
    Processes messages from RabbitMQ to assign skills to a character.
    Message format: {"character_id": 123, "skill_ids": [1, 2, 3]}
    Idempotent: checks if character already has skills before assigning.
    """
    async with message.process():
        data = json.loads(message.body.decode())
        character_id = data.get("character_id")
        skill_ids = data.get("skill_ids", [])

        if not character_id:
            logger.warning("Received message without character_id, skipping")
            return

        logger.info(f"Processing skills assignment for character {character_id}")

        async with async_session() as db:
            try:
                # Idempotency check: if character already has skills, skip
                existing = await crud.list_character_skills_for_character(db, character_id)
                if existing:
                    logger.info(f"Character {character_id} already has skills, skipping")
                    return

                for skill_id in skill_ids:
                    # Verify skill exists
                    skill_obj = await crud.get_skill(db, skill_id)
                    if not skill_obj:
                        logger.warning(f"Skill {skill_id} not found, skipping")
                        continue

                    # Find rank 1 for this skill
                    ranks = await crud.list_skill_ranks_by_skill(db, skill_id)
                    rank_obj = None
                    for r in ranks:
                        if r.rank_number == 1:
                            rank_obj = r
                            break

                    # If rank 1 doesn't exist, create it
                    if not rank_obj:
                        rank_data = schemas.SkillRankCreate(
                            skill_id=skill_id,
                            rank_number=1,
                        )
                        rank_obj = await crud.create_skill_rank(db, rank_data)

                    # Create CharacterSkill
                    cs_data = schemas.CharacterSkillCreate(
                        character_id=character_id,
                        skill_rank_id=rank_obj.id,
                    )
                    await crud.create_character_skill(db, cs_data)

                logger.info(f"Skills assigned for character {character_id}")
            except Exception as e:
                logger.error(f"Error assigning skills for character {character_id}: {e}")


async def start_consumer():
    """
    Connects to RabbitMQ and consumes messages from character_skills_queue.
    Reconnects automatically on failure.
    """
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            async with connection:
                channel = await connection.channel()
                queue = await channel.declare_queue("character_skills_queue", durable=True)
                logger.info("Skills consumer connected, waiting for messages...")
                async for message in queue:
                    try:
                        await process_message(message)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
        except Exception as e:
            logger.error(f"RabbitMQ connection error: {e}, retrying in 5s...")
            await asyncio.sleep(5)
