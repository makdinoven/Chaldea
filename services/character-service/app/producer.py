from pika import BlockingConnection, ConnectionParameters, BasicProperties
import json
import logging

logger = logging.getLogger("character-service.producer")


def send_character_approved_notification(user_id: int, character_name: str):
    """Publish notification to general_notifications queue when a character is approved."""
    try:
        connection = BlockingConnection(ConnectionParameters("rabbitmq"))
        channel = connection.channel()
        channel.queue_declare(queue="general_notifications", durable=True)
        message = json.dumps({
            "target_type": "user",
            "target_value": user_id,
            "message": f"Ваш персонаж «{character_name}» успешно создан!"
        })
        channel.basic_publish(
            exchange="",
            routing_key="general_notifications",
            body=message,
            properties=BasicProperties(delivery_mode=2)
        )
        connection.close()
    except Exception as e:
        logger.warning(f"Failed to send approval notification: {e}")
