"""
RabbitMQ publisher for inventory-service (synchronous).

Uses blocking pika directly since inventory-service is sync.
Publishes to the 'general_notifications' queue with the format expected by
notification-service's general_notification consumer:
    {"target_type": "user", "target_value": <user_id>, "message": "..."}
"""

import json
import logging

import pika
from config import settings

logger = logging.getLogger(__name__)

QUEUE_NAME = "general_notifications"


def publish_notification_sync(target_user_id: int, message: str) -> None:
    """
    Publish a notification for a single user (synchronous).
    """
    payload = {
        "target_type": "user",
        "target_value": target_user_id,
        "message": message,
    }
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


def publish_auction_notification(
    target_user_id: int,
    message: str,
    ws_type: str,
    ws_data: dict,
) -> None:
    """
    Publish auction notification with structured WS payload.

    Uses ws_type/ws_data fields supported by the general_notifications
    consumer in notification-service for real-time WebSocket delivery.
    """
    payload = {
        "target_type": "user",
        "target_value": target_user_id,
        "message": message,
        "ws_type": ws_type,
        "ws_data": ws_data,
    }
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
        logger.warning(f"Failed to publish auction notification to RabbitMQ: {e}")
