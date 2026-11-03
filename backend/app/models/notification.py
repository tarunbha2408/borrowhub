from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, ForeignKey,
    Enum as SQLEnum, SmallInteger
)
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class Notification(Base):
    __tablename__ = "notification"

    notif_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("app_user.user_id", ondelete="CASCADE"), nullable=False)
    related_request_id = Column(Integer, ForeignKey("borrow_request.request_id", ondelete="SET NULL"), nullable=True)
    related_loan_id = Column(Integer, ForeignKey("loan.loan_id", ondelete="SET NULL"), nullable=True)
    reference_type = Column(
        SQLEnum("REQUEST", "LOAN", "PAYMENT", "REVIEW", "DISPUTE", "SYSTEM", name="notif_ref_type"),
        nullable=False,
        default="SYSTEM"
    )
    reference_id = Column(BigInteger, nullable=True)
    type = Column(
        SQLEnum(
            "REQUEST_RECEIVED", "REQUEST_APPROVED", "REQUEST_REJECTED", "REQUEST_CANCELLED",
            "LOAN_STARTED", "LOAN_OVERDUE", "LOAN_RETURNED", "PAYMENT_UPDATE",
            "REVIEW_RECEIVED", "DISPUTE_UPDATE", "SYSTEM",
            name="notif_event_type"
        ),
        nullable=False
    )
    title = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(SmallInteger, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    user = relationship("AppUser", back_populates="notifications")
