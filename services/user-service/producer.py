from pika import BlockingConnection, ConnectionParameters, BasicProperties
import json

def send_notification_event(user_id: int):
    connection = BlockingConnection(ConnectionParameters("rabbitmq"))
    channel = connection.channel()
    channel.queue_declare(queue="user_registration", durable=True)
    message = json.dumps({"user_id": user_id})
    channel.basic_publish(
        exchange="",
        routing_key="user_registration",
        body=message,
        properties=BasicProperties(delivery_mode=2)
    )
    connection.close()