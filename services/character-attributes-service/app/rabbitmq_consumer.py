import aio_pika
import asyncio
import json
import logging

from config import settings
from database import SessionLocal
import crud
import schemas
import models

logger = logging.getLogger(__name__)


async def process_message(message: aio_pika.IncomingMessage):
    """
    Processes messages from RabbitMQ to create character attributes.
    Message format: {"character_id": 123, "attributes": {"strength": 10, "agility": 8, ...}}
    Idempotent: checks if character already has attributes before creating.
    """
    async with message.process():
        data = json.loads(message.body.decode())
        character_id = data.get("character_id")
        attributes = data.get("attributes", {})

        if not character_id:
            logger.warning("Received message without character_id, skipping")
            return

        logger.info(f"Processing attributes creation for character {character_id}")

        db = SessionLocal()
        try:
            # Idempotency check: if character already has attributes, skip
            existing = db.query(models.CharacterAttributes).filter(
                models.CharacterAttributes.character_id == character_id
            ).first()
            if existing:
                logger.info(f"Character {character_id} already has attributes, skipping")
                return

            # Build the schema object with character_id and provided attributes
            attrs_data = schemas.CharacterAttributesCreate(
                character_id=character_id,
                **attributes,
            )
            crud.create_character_attributes(db, attrs_data)

            logger.info(f"Attributes created for character {character_id}")
        except Exception as e:
            logger.error(f"Error creating attributes for character {character_id}: {e}")
            db.rollback()
        finally:
            db.close()


async def start_consumer():
    """
    Connects to RabbitMQ and consumes messages from character_attributes_queue.
    Reconnects automatically on failure.
    """
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            async with connection:
                channel = await connection.channel()
                queue = await channel.declare_queue("character_attributes_queue", durable=True)
                logger.info("Attributes consumer connected, waiting for messages...")
                async for message in queue:
                    try:
                        await process_message(message)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
        except Exception as e:
            logger.error(f"RabbitMQ connection error: {e}, retrying in 5s...")
            await asyncio.sleep(5)
