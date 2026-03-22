"""
RabbitMQ publisher for battle-service.

Uses blocking pika wrapped in run_in_executor to avoid blocking the async event loop.
Publishes to the 'general_notifications' queue with the format expected by
notification-service's general_notification consumer:
    {"target_type": "user", "target_value": <user_id>, "message": "..."}

Optionally includes ws_type / ws_data for structured WebSocket messages.
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


async def publish_notification(
    target_user_id: int,
    message: str,
    ws_type: Optional[str] = None,
    ws_data: Optional[dict] = None,
) -> None:
    """
    Publish a notification for a single user.
    Runs the blocking pika call in a thread-pool executor.

    If ws_type is provided, notification-service will send a structured
    WebSocket message with that type and ws_data payload.
    """
    payload = {
        "target_type": "user",
        "target_value": target_user_id,
        "message": message,
    }
    if ws_type:
        payload["ws_type"] = ws_type
    if ws_data:
        payload["ws_data"] = ws_data

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _publish_sync, payload)
