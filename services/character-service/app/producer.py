import aio_pika
import json
import logging
from config import settings

logger = logging.getLogger("character-service.producer")


async def send_character_approved_notification(user_id: int, character_name: str):
    """Publish notification to general_notifications queue when a character is approved.

    Uses aio_pika for async publishing. Handles RabbitMQ unavailability
    gracefully — logs a warning and does not crash the request.
    """
    try:
        connection = await aio_pika.connect_robust(
            settings.RABBITMQ_URL,
            timeout=5,
        )
        async with connection:
            channel = await connection.channel()
            await channel.declare_queue("general_notifications", durable=True)
            message_body = json.dumps({
                "target_type": "user",
                "target_value": user_id,
                "message": f"Ваш персонаж «{character_name}» успешно создан!"
            })
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=message_body.encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key="general_notifications",
            )
    except Exception as e:
        logger.warning(f"Failed to send approval notification: {e}")


async def publish_character_inventory(character_id: int, items: list):
    """Publish to character_inventory_queue.

    items format: [{"item_id": 1, "quantity": 5}, ...]
    Message must match what inventory-service consumer expects.
    """
    try:
        connection = await aio_pika.connect_robust(
            settings.RABBITMQ_URL,
            timeout=5,
        )
        async with connection:
            channel = await connection.channel()
            await channel.declare_queue("character_inventory_queue", durable=True)
            message_body = json.dumps({
                "character_id": character_id,
                "items": items,
            })
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=message_body.encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key="character_inventory_queue",
            )
            logger.info(f"Published inventory message for character {character_id}")
    except Exception as e:
        logger.warning(f"Failed to publish inventory message for character {character_id}: {e}")


async def publish_character_skills(character_id: int, skill_ids: list):
    """Publish to character_skills_queue.

    Message format matches what skills-service consumer expects:
    {"character_id": N, "skill_ids": [1, 2, 3]}
    """
    try:
        connection = await aio_pika.connect_robust(
            settings.RABBITMQ_URL,
            timeout=5,
        )
        async with connection:
            channel = await connection.channel()
            await channel.declare_queue("character_skills_queue", durable=True)
            message_body = json.dumps({
                "character_id": character_id,
                "skill_ids": skill_ids,
            })
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=message_body.encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key="character_skills_queue",
            )
            logger.info(f"Published skills message for character {character_id}")
    except Exception as e:
        logger.warning(f"Failed to publish skills message for character {character_id}: {e}")


async def publish_character_attributes(character_id: int, attributes: dict):
    """Publish to character_attributes_queue.

    Message format matches what character-attributes-service consumer expects:
    {"character_id": N, "attributes": {"strength": 10, ...}}
    """
    try:
        connection = await aio_pika.connect_robust(
            settings.RABBITMQ_URL,
            timeout=5,
        )
        async with connection:
            channel = await connection.channel()
            await channel.declare_queue("character_attributes_queue", durable=True)
            message_body = json.dumps({
                "character_id": character_id,
                "attributes": attributes,
            })
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=message_body.encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key="character_attributes_queue",
            )
            logger.info(f"Published attributes message for character {character_id}")
    except Exception as e:
        logger.warning(f"Failed to publish attributes message for character {character_id}: {e}")
