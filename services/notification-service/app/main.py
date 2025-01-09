from fastapi import FastAPI, APIRouter, Depends, HTTPException
from consumers.user_registration import start_user_registration_consumer
import models
from database import engine
from sqlalchemy.orm import Session
from database import get_db
import models
from schemas import Notification
from typing import List, Optional

app = FastAPI()

models.Base.metadata.create_all(bind=engine)

@app.on_event("startup")
async def startup_event():
    # Асинхронно запускаем consumer
    start_user_registration_consumer()


router = APIRouter(prefix="/notifications")
@router.get("/{user_id}/unread", response_model=List[Notification])
def get_unread_notifications(user_id: int, db: Session = Depends(get_db)):
    """
    Получение всех непрочитанных уведомлений пользователя.
    """
    notifications = db.query(models.Notification).filter(
        models.Notification.user_id == user_id,
        models.Notification.status == "unread"
    ).order_by(models.Notification.created_at.asc()).all()

    if not notifications:
        raise HTTPException(status_code=404, detail="No unread notifications found.")

    return notifications


@router.get("/{user_id}/full", response_model=List[Notification])
def get_all_notifications(user_id: int, db: Session = Depends(get_db)):
    """
    Получение всех уведомлений пользователя.
    """
    notifications = db.query(models.Notification).filter(
        models.Notification.user_id == user_id
    ).order_by(models.Notification.created_at.asc()).all()

    if not notifications:
        raise HTTPException(status_code=404, detail="No notifications found.")

    return notifications


@router.put("/{user_id}/mark-as-read", response_model=List[Notification])
def mark_multiple_notifications_as_read(
    user_id: int,
    notification_ids: List[int],
    db: Session = Depends(get_db)
):
    """
    Отметить несколько уведомлений как прочитанные.
    """
    notifications = db.query(models.Notification).filter(
        models.Notification.user_id == user_id,
        models.Notification.id.in_(notification_ids),
        models.Notification.status == "unread"
    ).all()

    if not notifications:
        raise HTTPException(status_code=404, detail="No unread notifications to update.")

    for notification in notifications:
        notification.status = "read"
    db.commit()

    return notifications


@router.put("/{user_id}/mark-all-as-read", response_model=List[Notification])
def mark_all_notifications_as_read(user_id: int, db: Session = Depends(get_db)):
    """
    Отметить все уведомления пользователя как прочитанные.
    """
    notifications = db.query(models.Notification).filter(
        models.Notification.user_id == user_id,
        models.Notification.status == "unread"
    ).all()

    if not notifications:
        raise HTTPException(status_code=404, detail="No unread notifications to update.")

    for notification in notifications:
        notification.status = "read"
    db.commit()

    return notifications

app.include_router(router)