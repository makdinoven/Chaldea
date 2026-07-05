"""Publish notifications to notification-service via RabbitMQ (FEAT-144).

party-service is synchronous, so a blocking pika publish is fine here. Mirrors
battle-service's payload for the `general_notifications` queue.
"""
import json
import logging

import pika

from config import settings

logger = logging.getLogger("party-service.notifications")

QUEUE_NAME = "general_notifications"


def publish_notification(user_id: int, message: str, ws_type: str = None, ws_data: dict = None) -> None:
    """Fire-and-forget notification for a single user. Non-fatal."""
    payload = {"target_type": "user", "target_value": user_id, "message": message}
    if ws_type:
        payload["ws_type"] = ws_type
    if ws_data:
        payload["ws_data"] = ws_data
    try:
        connection = pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2),
        )
        connection.close()
    except Exception as e:
        logger.warning(f"Failed to publish notification for user {user_id}: {e}")
