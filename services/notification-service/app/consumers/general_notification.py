# consumers/general_notifications.py

import pika
import json
import logging
import requests
from threading import Thread
from sqlalchemy.orm import Session
from pydantic import ValidationError

from database import get_db
from models import Notification
from schemas import NotificationCreate, GeneralNotificationPayload, NotificationTargetType

from ws_manager import send_to_user

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

QUEUE_NAME = "general_notifications"

def consume():
    import time
    while True:
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host="rabbitmq"))
            break
        except pika.exceptions.AMQPConnectionError:
            logger.warning("RabbitMQ not ready, retrying in 5s...")
            time.sleep(5)
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    def callback(ch, method, properties, body):
        try:
            data = json.loads(body)
            payload = GeneralNotificationPayload(**data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Failed to parse/validate notification payload: {e}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        db: Session = next(get_db())
        try:
            if payload.target_type == NotificationTargetType.user:
                user_id = payload.target_value
                if user_id is not None:
                    create_and_send(db, user_id, payload.message)
                else:
                    logger.error("target_value is None for 'user'")
            elif payload.target_type == NotificationTargetType.all:
                users = get_all_users()
                for user_data in users:
                    create_and_send(db, user_data["id"], payload.message)
            elif payload.target_type == NotificationTargetType.admins:
                admins = get_admins()
                for admin_data in admins:
                    create_and_send(db, admin_data["id"], payload.message)

            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as ex:
            logger.exception(f"Error while processing general notification: {ex}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
        finally:
            db.close()

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
    logger.info("[general_notifications_consumer] Waiting for messages...")
    channel.start_consuming()

def create_and_send(db: Session, user_id: int, message: str):
    """
    Создаём запись в БД и сразу отправляем через SSE
    """
    new_data = NotificationCreate(user_id=user_id, message=message)
    db_obj = Notification(**new_data.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)

    # Отправляем через WebSocket, если пользователь подключён
    notification_data = {
        "id": db_obj.id,
        "user_id": db_obj.user_id,
        "message": db_obj.message,
        "status": db_obj.status,
        "created_at": str(db_obj.created_at)
    }
    send_to_user(user_id, {"type": "notification", "data": notification_data})

    logger.info(f"[general_notifications_consumer] Created notification {db_obj.id} for user {user_id}")

def get_all_users() -> list:
    """
    Запрос в user-service (GET /users/all)
    """
    url = "http://user-service:8000/users/all"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()

def get_admins() -> list:
    """
    Запрос в user-service (GET /users/admins)
    """
    url = "http://user-service:8000/users/admins"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()

def start_general_notifications_consumer():
    thread = Thread(target=consume, daemon=True)
    thread.start()
