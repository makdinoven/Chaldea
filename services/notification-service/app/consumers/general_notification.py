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
from notification_categories import (
    DEFAULT_CATEGORY,
    MODE_BELL,
    MODE_OFF,
    get_user_mode,
    resolve_category,
)

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
            GeneralNotificationPayload(**data)
        except (json.JSONDecodeError, ValidationError, TypeError) as e:
            logger.error(f"Failed to parse/validate notification payload: {e}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        db: Session = next(get_db())
        try:
            handle_notification(db, data)
        except Exception as ex:
            logger.exception(f"Error while processing general notification: {ex}")
        finally:
            ch.basic_ack(delivery_tag=method.delivery_tag)
            db.close()

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
    logger.info("[general_notifications_consumer] Waiting for messages...")
    channel.start_consuming()

def handle_notification(db: Session, data: dict) -> None:
    """Route one `general_notifications` payload to its recipients.

    The category is resolved once (explicit > ws_type fallback > system).
    For a single user the stored preference decides: `off` drops the
    notification entirely, `bell` stores it but pushes it as silent.
    Broadcasts (all/admins) are never filtered.
    """
    payload = GeneralNotificationPayload(**data)
    ws_type = data.get("ws_type")
    ws_data = data.get("ws_data")
    category = resolve_category(payload.category, ws_type)

    if payload.target_type == NotificationTargetType.user:
        user_id = payload.target_value
        if user_id is None:
            logger.error("target_value is None for 'user'")
            return
        mode = get_user_mode(db, user_id, category)
        if mode == MODE_OFF:
            logger.info(
                f"[general_notifications_consumer] Skipped {category} notification "
                f"for user {user_id} (muted)"
            )
            return
        create_and_send(db, user_id, payload.message, ws_type=ws_type,
                        ws_data=ws_data, category=category,
                        silent=(mode == MODE_BELL))
    elif payload.target_type == NotificationTargetType.all:
        for user_data in get_all_users():
            create_and_send(db, user_data["id"], payload.message, ws_type=ws_type,
                            ws_data=dict(ws_data) if ws_data else None,
                            category=category)
    elif payload.target_type == NotificationTargetType.admins:
        for admin_data in get_admins():
            create_and_send(db, admin_data["id"], payload.message, ws_type=ws_type,
                            ws_data=dict(ws_data) if ws_data else None,
                            category=category)


def create_and_send(db: Session, user_id: int, message: str,
                    ws_type: str = None, ws_data: dict = None,
                    category: str = DEFAULT_CATEGORY, silent: bool = False):
    """
    Создаём запись в БД и сразу отправляем через WebSocket.

    If ws_type is provided, the WebSocket message uses that type with ws_data
    instead of the generic "notification" format. The text message is always
    saved to the DB for persistence. Every push carries `category` and
    `silent` (true = bell only, the client must not show a popup/play sound).
    """
    new_data = NotificationCreate(user_id=user_id, message=message, category=category)
    db_obj = Notification(**new_data.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)

    # Отправляем через WebSocket, если пользователь подключён
    if ws_type:
        # Structured WS message with custom type
        ws_payload = {
            "type": ws_type,
            "data": ws_data or {},
        }
        # Also include the notification ID and message for reference
        ws_payload["data"]["notification_id"] = db_obj.id
        ws_payload["data"]["message"] = db_obj.message
        ws_payload["data"]["category"] = db_obj.category
        ws_payload["data"]["silent"] = silent
        send_to_user(user_id, ws_payload)
    else:
        # Default notification format (backward compatible)
        notification_data = {
            "id": db_obj.id,
            "user_id": db_obj.user_id,
            "message": db_obj.message,
            "status": db_obj.status,
            "created_at": str(db_obj.created_at),
            "category": db_obj.category,
            "silent": silent,
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
