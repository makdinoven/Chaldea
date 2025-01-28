# main.py

import asyncio
import json
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import List
from sqlalchemy.orm import Session

import models
from models import Notification
from database import engine, get_db
from schemas import Notification as NotificationSchema
from schemas import GeneralNotificationPayload, NotificationTargetType
from auth_http import get_current_user_via_http, UserRead

# Импортируем global connections (но не send_to_sse) из sse_manager
from sse_manager import connections

# Подключаем консьюмеры (без импорта из main!)
from consumers.user_registration import start_user_registration_consumer
from consumers.general_notification import start_general_notifications_consumer

import pika

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

@app.on_event("startup")
async def startup_event():
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

# Эндпоинт для админского уведомления (добавляет сообщение в очередь general_notifications)
@router.post("/create")
def create_admin_notification(
    data: GeneralNotificationPayload,
    current_user: UserRead = Depends(get_current_user_via_http)
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create notifications"
        )

    connection = pika.BlockingConnection(pika.ConnectionParameters(host="rabbitmq"))
    channel = connection.channel()
    channel.queue_declare(queue="general_notifications", durable=True)

    payload = {
        "target_type": data.target_type.value,
        "target_value": data.target_value,
        "message": data.message
    }
    channel.basic_publish(
        exchange='',
        routing_key="general_notifications",
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    connection.close()

    return {"detail": "Notification creation request sent to queue."}

# Остальные эндпоинты: get_unread_notifications, get_all_notifications, mark-as-read...
@router.get("/{user_id}/unread", response_model=List[NotificationSchema])
def get_unread_notifications(user_id: int, db: Session = Depends(get_db)):
    notifications = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.status == "unread"
    ).order_by(Notification.created_at.asc()).all()

    if not notifications:
        raise HTTPException(status_code=404, detail="No unread notifications found.")
    return notifications

@router.get("/{user_id}/full", response_model=List[NotificationSchema])
def get_all_notifications(user_id: int, db: Session = Depends(get_db)):
    notifications = db.query(Notification).filter(
        Notification.user_id == user_id
    ).order_by(Notification.created_at.asc()).all()

    if not notifications:
        raise HTTPException(status_code=404, detail="No notifications found.")
    return notifications

@router.put("/{user_id}/mark-as-read", response_model=List[NotificationSchema])
def mark_multiple_notifications_as_read(
    user_id: int,
    notification_ids: List[int],
    db: Session = Depends(get_db)
):
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
    db: Session = Depends(get_db)
):
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
