from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, Date, DateTime, Numeric, String, Text, ForeignKey,
    Enum as SQLEnum, CHAR
)
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class BorrowRequest(Base):
    __tablename__ = "borrow_request"

    request_id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("item.item_id", ondelete="RESTRICT"), nullable=False)
    borrower_id = Column(Integer, ForeignKey("app_user.user_id", ondelete="RESTRICT"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    request_message = Column(Text, nullable=True)
    status = Column(
        SQLEnum("PENDING", "APPROVED", "REJECTED", "CANCELLED", name="request_status"),
        nullable=False,
        default="PENDING"
    )
    requested_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    decided_at = Column(DateTime, nullable=True)
    decision_note = Column(Text, nullable=True)

    # Relationships
    item = relationship("Item", back_populates="borrow_requests")
    borrower = relationship("AppUser", back_populates="borrow_requests")
    loan = relationship("Loan", back_populates="request", uselist=False)
    booked_dates = relationship("BookedDate", back_populates="request")


class BookedDate(Base):
    __tablename__ = "booked_date"

    item_id = Column(Integer, ForeignKey("item.item_id", ondelete="CASCADE"), primary_key=True)
    booked_date = Column(Date, primary_key=True)
    request_id = Column(Integer, ForeignKey("borrow_request.request_id", ondelete="CASCADE"), nullable=False)

    item = relationship("Item", back_populates="booked_dates")
    request = relationship("BorrowRequest", back_populates="booked_dates")


class Loan(Base):
    __tablename__ = "loan"

    loan_id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(Integer, ForeignKey("borrow_request.request_id", ondelete="RESTRICT"), unique=True, nullable=False)
    status = Column(
        SQLEnum("SCHEDULED", "ACTIVE", "OVERDUE", "RETURNED", "CANCELLED", name="loan_status"),
        nullable=False,
        default="SCHEDULED"
    )
    issued_at = Column(DateTime, nullable=True)
    due_at = Column(DateTime, nullable=False)
    returned_at = Column(DateTime, nullable=True)
    agreed_daily_fee = Column(Numeric(10, 2), nullable=False)
    agreed_deposit = Column(Numeric(10, 2), nullable=False)
    agreed_total_fee = Column(Numeric(10, 2), nullable=False)
    late_fee = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    deposit_status = Column(
        SQLEnum("NOT_PAID", "HELD", "RELEASED", "FORFEITED", "PARTIAL", name="deposit_status"),
        nullable=False,
        default="NOT_PAID"
    )
    deposit_deducted = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    handover_otp_hash = Column(CHAR(64), nullable=False)
    return_otp_hash = Column(CHAR(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    request = relationship("BorrowRequest", back_populates="loan")
    payments = relationship("Payment", back_populates="loan")
    inspections = relationship("LoanInspection", back_populates="loan")
    reviews = relationship("Review", back_populates="loan")
    disputes = relationship("Dispute", back_populates="loan")


class TemporaryOTP(Base):
    __tablename__ = "temporary_otp"

    otp_id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(Integer, ForeignKey("loan.loan_id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(String(20), nullable=False)  # "HANDOVER" or "RETURN"
    otp_code = Column(String(10), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    loan = relationship("Loan", backref="temporary_otps")

