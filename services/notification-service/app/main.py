from fastapi import FastAPI, APIRouter, Depends, HTTPException
from consumers.user_registration import start_user_registration_consumer
import models
from database import engine
from sqlalchemy.orm import Session
from database import get_db
from models import Notification
from schemas import Notification
from typing import List, Optional

app = FastAPI()

models.Base.metadata.create_all(bind=engine)

@app.on_event("startup")
async def startup_event():
    # Асинхронно запускаем consumer
    start_user_registration_consumer()


router = APIRouter(prefix="/notifications")

@router.get("/", response_model=List[Notification])
def get_notifications(
    user_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Получение списка уведомлений для пользователя.
    Можно фильтровать по статусу (unread, read).
    """
    query = db.query(Notification).filter(Notification.user_id == user_id)

    if status:
        query = query.filter(Notification.status == status)

    notifications = query.order_by(Notification.created_at.desc()).all()

    if not notifications:
        raise HTTPException(status_code=404, detail="No notifications found.")

    return notifications

@router.put("/{notification_id}/read", response_model=Notification)
def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db)
):
    """
    Отметить уведомление как прочитанное.
    """
    notification = db.query(Notification).filter(Notification.id == notification_id).first()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found.")

    notification.status = "read"
    db.commit()
    db.refresh(notification)

    return notification

app.include_router(router)