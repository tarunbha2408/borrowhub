from typing import List, Dict, Any
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.dependencies.auth import get_current_user
from backend.app.models.user import AppUser
from backend.app.schemas.notification import NotificationOut
from backend.app.services.notification_service import (
    get_user_notifications,
    get_unread_count,
    mark_notification_read,
    mark_all_notifications_read,
)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=List[NotificationOut])
def list_notifications(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_user_notifications(db, current_user.user_id)


@router.get("/unread-count", response_model=Dict[str, int])
def unread_count_endpoint(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    count = get_unread_count(db, current_user.user_id)
    return {"unread_count": count}


@router.post("/{notif_id}/read")
def mark_read_endpoint(
    notif_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    mark_notification_read(db, notif_id, current_user.user_id)
    return {"message": "Notification marked as read."}


@router.post("/read-all")
def mark_all_read_endpoint(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    count = mark_all_notifications_read(db, current_user.user_id)
    return {"message": "All notifications marked as read.", "count": count}
