from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, BigInteger, String, Numeric, DateTime, ForeignKey,
    Enum as SQLEnum, JSON, SmallInteger
)
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class Payment(Base):
    __tablename__ = "payment"

    payment_id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(Integer, ForeignKey("loan.loan_id", ondelete="RESTRICT"), nullable=False)
    payer_id = Column(Integer, ForeignKey("app_user.user_id", ondelete="RESTRICT"), nullable=False)
    payee_id = Column(Integer, ForeignKey("app_user.user_id", ondelete="RESTRICT"), nullable=False)
    payment_type = Column(
        SQLEnum("RENTAL_FEE", "DEPOSIT", "LATE_FEE", "DAMAGE_CHARGE", "DAMAGE_DEDUCTION", "REFUND", name="payment_type"),
        nullable=False
    )
    method = Column(SQLEnum("UPI", "CARD", "CASH", name="payment_method"), nullable=False)
    payment_status = Column(
        SQLEnum("PENDING", "COMPLETED", "FAILED", name="payment_status"),
        nullable=False,
        default="PENDING"
    )
    amount = Column(Numeric(10, 2), nullable=False)
    refund_for_payment_id = Column(Integer, ForeignKey("payment.payment_id", ondelete="RESTRICT"), nullable=True)
    refund_reason = Column(
        SQLEnum("CANCELLED_LOAN", "DEPOSIT_SETTLEMENT", "DISPUTE_AWARD", "OVERPAYMENT", name="refund_reason"),
        nullable=True
    )
    confirmed_by_user_id = Column(Integer, ForeignKey("app_user.user_id", ondelete="RESTRICT"), nullable=True)
    gateway_order_id = Column(String(100), nullable=True)
    transaction_reference = Column(String(160), unique=True, nullable=True)
    idempotency_key = Column(String(100), unique=True, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    paid_at = Column(DateTime, nullable=True)

    # Relationships
    loan = relationship("Loan", back_populates="payments")
    payer = relationship("AppUser", foreign_keys=[payer_id])
    payee = relationship("AppUser", foreign_keys=[payee_id])
    webhook_events = relationship("PaymentWebhookEvent", back_populates="payment")


class PaymentWebhookEvent(Base):
    __tablename__ = "payment_webhook_event"

    event_id = Column(BigInteger, primary_key=True, autoincrement=True)
    payment_id = Column(Integer, ForeignKey("payment.payment_id", ondelete="RESTRICT"), nullable=False)
    gateway_event_id = Column(String(160), unique=True, nullable=False)
    event_type = Column(String(30), nullable=False)
    amount_reported = Column(Numeric(10, 2), nullable=False)
    transaction_reference = Column(String(160), nullable=False)
    signature_verified = Column(SmallInteger, nullable=False, default=0)
    event_status = Column(
        SQLEnum("RECEIVED", "VERIFIED", "REJECTED", name="webhook_event_status"),
        nullable=False,
        default="RECEIVED"
    )
    payload = Column(JSON, nullable=False)
    received_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime, nullable=True)

    payment = relationship("Payment", back_populates="webhook_events")
