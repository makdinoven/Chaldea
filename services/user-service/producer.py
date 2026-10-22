from pika import BlockingConnection, ConnectionParameters, BasicProperties
import json
import logging

logger = logging.getLogger("user-service.producer")


def _publish_notification(user_id: int):
    """Internal function that performs the blocking RabbitMQ publish."""
    connection = BlockingConnection(
        ConnectionParameters(
            "rabbitmq",
            socket_timeout=5,
            connection_attempts=1,
            retry_delay=1,
        )
    )
    channel = connection.channel()
    channel.queue_declare(queue="user_registration", durable=True)
    message = json.dumps({"user_id": user_id})
    channel.basic_publish(
        exchange="",
        routing_key="user_registration",
        body=message,
        properties=BasicProperties(delivery_mode=2),
    )
    connection.close()


def send_notification_event(user_id: int):
    """Publish registration notification to RabbitMQ.

    Handles RabbitMQ unavailability gracefully — logs a warning
    and does not crash the request.
    """
    try:
        _publish_notification(user_id)
    except Exception as e:
        logger.warning(f"Failed to send registration notification for user {user_id}: {e}")


# ── general_notifications (bell notifications via notification-service) ─────

GENERAL_NOTIFICATIONS_QUEUE = "general_notifications"
# Notification category understood by notification-service preferences.
CATEGORY_SOCIAL = "social"


def _publish_general(payload: dict):
    """Blocking publish of one payload to the general_notifications queue."""
    connection = BlockingConnection(
        ConnectionParameters(
            "rabbitmq",
            socket_timeout=5,
            connection_attempts=1,
            retry_delay=1,
        )
    )
    channel = connection.channel()
    channel.queue_declare(queue=GENERAL_NOTIFICATIONS_QUEUE, durable=True)
    channel.basic_publish(
        exchange="",
        routing_key=GENERAL_NOTIFICATIONS_QUEUE,
        body=json.dumps(payload),
        properties=BasicProperties(delivery_mode=2),
    )
    connection.close()


def send_social_notification(target_user_id: int, message: str, ws_type: str, ws_data: dict):
    """Publish a social bell notification for one user.

    Meant to run as a FastAPI BackgroundTask; never raises — a RabbitMQ
    outage is logged and the originating request is unaffected.
    """
    payload = {
        "target_type": "user",
        "target_value": target_user_id,
        "message": message,
        "category": CATEGORY_SOCIAL,
        "ws_type": ws_type,
        "ws_data": ws_data,
    }
    try:
        _publish_general(payload)
    except Exception as e:
        logger.warning(f"Failed to send {ws_type} notification for user {target_user_id}: {e}")
