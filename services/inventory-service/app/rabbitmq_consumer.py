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
    Processes messages from RabbitMQ to create inventory items for a character.
    Message format: {"character_id": 123, "items": [{"item_id": 1, "quantity": 5}, ...]}
    Idempotent: checks if inventory already exists before creating.
    """
    async with message.process():
        data = json.loads(message.body.decode())
        character_id = data.get("character_id")
        items = data.get("items", [])

        if not character_id:
            logger.warning("Received message without character_id, skipping")
            return

        logger.info(f"Processing inventory creation for character {character_id}")

        db = SessionLocal()
        try:
            # Idempotency check: if character already has inventory items, skip
            existing = crud.get_inventory_items(db, character_id)
            if existing:
                logger.info(f"Character {character_id} already has inventory, skipping")
                return

            # Create default equipment slots
            crud.create_default_equipment_slots(db, character_id)

            # Add each item to inventory
            for item_data in items:
                item_id = item_data.get("item_id")
                quantity = item_data.get("quantity", 1)

                # Verify item exists
                db_item = db.query(models.Items).filter(models.Items.id == item_id).first()
                if not db_item:
                    logger.warning(f"Item {item_id} not found, skipping")
                    continue

                inventory_data = schemas.CharacterInventoryBase(
                    character_id=character_id,
                    item_id=item_id,
                    quantity=quantity,
                )
                crud.create_character_inventory(db, inventory_data)

            logger.info(f"Inventory created for character {character_id}")
        except Exception as e:
            logger.error(f"Error creating inventory for character {character_id}: {e}")
            db.rollback()
        finally:
            db.close()


async def start_consumer():
    """
    Connects to RabbitMQ and consumes messages from character_inventory_queue.
    Reconnects automatically on failure.
    """
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            async with connection:
                channel = await connection.channel()
                queue = await channel.declare_queue("character_inventory_queue", durable=True)
                logger.info("Inventory consumer connected, waiting for messages...")
                async for message in queue:
                    try:
                        await process_message(message)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
        except Exception as e:
            logger.error(f"RabbitMQ connection error: {e}, retrying in 5s...")
            await asyncio.sleep(5)
