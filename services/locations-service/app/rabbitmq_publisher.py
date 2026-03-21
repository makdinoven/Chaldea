"""
RabbitMQ publisher for locations-service.

Uses blocking pika wrapped in run_in_executor to avoid blocking the async event loop.
Publishes to the 'general_notifications' queue with the format expected by
notification-service's general_notification consumer:
    {"target_type": "user", "target_value": <user_id>, "message": "..."}
"""

import json
import logging
import asyncio
from typing import Optional

import pika
from config import settings

logger = logging.getLogger(__name__)

QUEUE_NAME = "general_notifications"


def _publish_sync(payload: dict) -> None:
    """Blocking publish — must be called via run_in_executor."""
    try:
        connection = pika.BlockingConnection(
            pika.URLParameters(settings.RABBITMQ_URL)
        )
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.basic_publish(
            exchange='',
            routing_key=QUEUE_NAME,
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2),
        )
        connection.close()
    except Exception as e:
        logger.warning(f"Failed to publish notification to RabbitMQ: {e}")


async def publish_notification(target_user_id: int, message: str) -> None:
    """
    Publish a notification for a single user.
    Runs the blocking pika call in a thread-pool executor.
    """
    payload = {
        "target_type": "user",
        "target_value": target_user_id,
        "message": message,
    }
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _publish_sync, payload)


def publish_notification_sync(target_user_id: int, message: str) -> None:
    """
    Synchronous version for use inside BackgroundTasks (already in a thread).
    """
    payload = {
        "target_type": "user",
        "target_value": target_user_id,
        "message": message,
    }
    _publish_sync(payload)
