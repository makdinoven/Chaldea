
import pika
import json
from threading import Thread
from sqlalchemy.orm import Session
from database import get_db
from models import Notification
from schemas import NotificationCreate
from sse_manager import send_to_sse

QUEUE_NAME = "user_registration"

def consume():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host="rabbitmq"))
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

        # Отправляем в SSE (если пользователь подключён)
        sse_data = {
            "id": db_notification.id,
            "user_id": db_notification.user_id,
            "message": db_notification.message,
            "status": db_notification.status,
            "created_at": str(db_notification.created_at)
        }
        send_to_sse(user_id, sse_data)

        print(f"[user_registration_consumer] Notification created for user {user_id}")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
    print("[user_registration_consumer] Waiting for messages...")
    channel.start_consuming()

def start_user_registration_consumer():
    thread = Thread(target=consume, daemon=True)
    thread.start()
