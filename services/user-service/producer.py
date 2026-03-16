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
