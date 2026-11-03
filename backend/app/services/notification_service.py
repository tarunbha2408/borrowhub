from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from backend.app.models.notification import Notification


def create_notification(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    event_type: str = "SYSTEM",
    reference_type: str = "SYSTEM",
    reference_id: Optional[int] = None,
    related_request_id: Optional[int] = None,
    related_loan_id: Optional[int] = None,
) -> Notification:
    """Create a persistent in-app notification for a user."""
    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=event_type,
        reference_type=reference_type,
        reference_id=reference_id,
        related_request_id=related_request_id,
        related_loan_id=related_loan_id,
        is_read=0,
    )
    db.add(notif)
    db.flush()
    return notif


def get_user_notifications(db: Session, user_id: int, limit: int = 50) -> List[Notification]:
    """Retrieve the recent notifications for a user."""
    return db.query(Notification).filter(
        Notification.user_id == user_id
    ).order_by(desc(Notification.created_at)).limit(limit).all()


def get_unread_count(db: Session, user_id: int) -> int:
    """Count unread notifications for a user."""
    return db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == 0
    ).count()


def mark_notification_read(db: Session, notif_id: int, user_id: int) -> bool:
    """Mark a single notification as read if owned by the user."""
    notif = db.query(Notification).filter(
        Notification.notif_id == notif_id,
        Notification.user_id == user_id
    ).first()
    if notif:
        notif.is_read = 1
        db.commit()
        return True
    return False


def mark_all_notifications_read(db: Session, user_id: int) -> int:
    """Mark all unread notifications as read for a user."""
    count = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == 0
    ).update({"is_read": 1})
    db.commit()
    return count
