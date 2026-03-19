# main.py

import asyncio
import json
import logging
import os
from fastapi import BackgroundTasks, FastAPI, APIRouter, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import List
from sqlalchemy.orm import Session

from models import Notification
from database import get_db
from schemas import Notification as NotificationSchema
from schemas import GeneralNotificationPayload, NotificationTargetType
from auth_http import get_current_user_via_http, require_permission, UserRead

# Импортируем global connections (но не send_to_sse) из sse_manager
from sse_manager import connections

# Подключаем консьюмеры (без импорта из main!)
from consumers.user_registration import start_user_registration_consumer
from consumers.general_notification import start_general_notifications_consumer

from chat_routes import chat_router

import pika

logger = logging.getLogger("notification-service")

app = FastAPI()

cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    # Schema is now managed by Alembic (runs before uvicorn in Dockerfile CMD).
    # Запускаем консьюмеры
    start_user_registration_consumer()
    start_general_notifications_consumer()

router = APIRouter(prefix="/notifications")

# SSE-эндпоинт
@router.get("/stream", response_class=StreamingResponse)
async def sse_notifications_stream(
    current_user: UserRead = Depends(get_current_user_via_http)
):
    """
    Открываем постоянное соединение SSE для текущего пользователя.
    """
    user_id = current_user.id
    if user_id not in connections:
        connections[user_id] = asyncio.Queue()
    queue = connections[user_id]

    async def event_generator():
        while True:
            data_str = await queue.get()
            yield f"data: {data_str}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

def _publish_admin_notification(payload: dict):
    """Internal function that performs the blocking RabbitMQ publish for admin notifications."""
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host="rabbitmq",
                socket_timeout=5,
                connection_attempts=1,
                retry_delay=1,
            )
        )
        channel = connection.channel()
        channel.queue_declare(queue="general_notifications", durable=True)
        channel.basic_publish(
            exchange='',
            routing_key="general_notifications",
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        connection.close()
    except Exception as e:
        logger.warning(f"Failed to publish admin notification to RabbitMQ: {e}")


# Эндпоинт для админского уведомления (добавляет сообщение в очередь general_notifications)
@router.post("/create")
def create_admin_notification(
    data: GeneralNotificationPayload,
    background_tasks: BackgroundTasks,
    current_user: UserRead = Depends(require_permission("notifications:create"))
):
    payload = {
        "target_type": data.target_type.value,
        "target_value": data.target_value,
        "message": data.message
    }
    background_tasks.add_task(_publish_admin_notification, payload)

    return {"detail": "Notification creation request sent to queue."}

# Остальные эндпоинты: get_unread_notifications, get_all_notifications, mark-as-read...
@router.get("/{user_id}/unread")
def get_unread_notifications(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Доступ к чужим уведомлениям запрещён")
    query = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.status == "unread"
    ).order_by(Notification.created_at.asc())

    total = query.count()
    notifications = query.offset((page - 1) * page_size).limit(page_size).all()

    return {"items": notifications, "total": total, "page": page, "page_size": page_size}

@router.get("/{user_id}/full")
def get_all_notifications(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Доступ к чужим уведомлениям запрещён")
    query = db.query(Notification).filter(
        Notification.user_id == user_id
    ).order_by(Notification.created_at.asc())

    total = query.count()
    notifications = query.offset((page - 1) * page_size).limit(page_size).all()

    return {"items": notifications, "total": total, "page": page, "page_size": page_size}

@router.put("/{user_id}/mark-as-read", response_model=List[NotificationSchema])
def mark_multiple_notifications_as_read(
    user_id: int,
    notification_ids: List[int],
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Доступ к чужим уведомлениям запрещён")
    notifications = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.id.in_(notification_ids),
        Notification.status == "unread"
    ).all()

    if not notifications:
        raise HTTPException(status_code=404, detail="No unread notifications to update.")

    for notification in notifications:
        notification.status = "read"
    db.commit()

    return notifications

@router.put("/{user_id}/mark-all-as-read", response_model=List[NotificationSchema])
def mark_all_notifications_as_read(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Доступ к чужим уведомлениям запрещён")
    notifications = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.status == "unread"
    ).all()

    if not notifications:
        raise HTTPException(status_code=404, detail="No unread notifications to update.")

    for notification in notifications:
        notification.status = "read"
    db.commit()

    return notifications

app.include_router(router)
app.include_router(chat_router)
