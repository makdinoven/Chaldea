import pika
import json
from sqlalchemy.orm import Session
from database import get_db
from models import Notification
from schemas import NotificationCreate

QUEUE_NAME = "user_registration"

def start():
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host="rabbitmq")
    )
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    def callback(ch, method, properties, body):
        data = json.loads(body)
        user_id = data.get("user_id")
        message = "Welcome to our platform!"

        db: Session = next(get_db())
        notification = NotificationCreate(user_id=user_id, message=message)
        db_notification = Notification(**notification.dict())
        db.add(db_notification)
        db.commit()

        print(f"Notification created for user {user_id}")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
    print(" [*] Waiting for messages. To exit press CTRL+C")
    channel.start_consuming()
