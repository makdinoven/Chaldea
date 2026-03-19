
import pika
import json
from threading import Thread
from sqlalchemy.orm import Session
from database import get_db
from models import Notification
from schemas import NotificationCreate
from ws_manager import send_to_user

QUEUE_NAME = "user_registration"

def consume():
    import time
    while True:
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host="rabbitmq"))
            break
        except pika.exceptions.AMQPConnectionError:
            print("[user_registration_consumer] RabbitMQ not ready, retrying in 5s...")
            time.sleep(5)
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    def callback(ch, method, properties, body):
        data = json.loads(body)
        user_id = data.get("user_id")
        message = "Welcome to our platform!"

        db: Session = next(get_db())
        notification_data = NotificationCreate(user_id=user_id, message=message)
        db_notification = Notification(**notification_data.dict())
        db.add(db_notification)
        db.commit()
        db.refresh(db_notification)

        # Отправляем через WebSocket (если пользователь подключён)
        notification_data = {
            "id": db_notification.id,
            "user_id": db_notification.user_id,
            "message": db_notification.message,
            "status": db_notification.status,
            "created_at": str(db_notification.created_at)
        }
        send_to_user(user_id, {"type": "notification", "data": notification_data})

        print(f"[user_registration_consumer] Notification created for user {user_id}")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
    print("[user_registration_consumer] Waiting for messages...")
    channel.start_consuming()

def start_user_registration_consumer():
    thread = Thread(target=consume, daemon=True)
    thread.start()
