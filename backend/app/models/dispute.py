from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, String, Text, Numeric, DateTime, ForeignKey,
    Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class Dispute(Base):
    __tablename__ = "dispute"

    dispute_id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(Integer, ForeignKey("loan.loan_id", ondelete="RESTRICT"), nullable=False)
    raised_by = Column(Integer, ForeignKey("app_user.user_id", ondelete="RESTRICT"), nullable=False)
    against_user_id = Column(Integer, ForeignKey("app_user.user_id", ondelete="RESTRICT"), nullable=False)
    inspection_id = Column(Integer, ForeignKey("loan_inspection.inspection_id", ondelete="RESTRICT"), nullable=True)
    resolved_by = Column(Integer, ForeignKey("app_user.user_id", ondelete="RESTRICT"), nullable=True)
    dispute_type = Column(
        SQLEnum("DAMAGE", "NO_SHOW", "LATE_RETURN", "NON_PAYMENT", "OTHER", name="dispute_type"),
        nullable=False
    )
    description = Column(Text, nullable=False)
    status = Column(
        SQLEnum("OPEN", "UNDER_REVIEW", "RESOLVED", "REJECTED", name="dispute_status"),
        nullable=False,
        default="OPEN"
    )
    amount_claimed = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    amount_awarded = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    resolution_note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime, nullable=True)

    loan = relationship("Loan", back_populates="disputes")
    raiser = relationship("AppUser", foreign_keys=[raised_by])
    against_user = relationship("AppUser", foreign_keys=[against_user_id])
    resolver = relationship("AppUser", foreign_keys=[resolved_by])
    evidence = relationship("DisputeEvidence", back_populates="dispute", cascade="all, delete-orphan")


class DisputeEvidence(Base):
    __tablename__ = "dispute_evidence"

    evidence_id = Column(Integer, primary_key=True, autoincrement=True)
    dispute_id = Column(Integer, ForeignKey("dispute.dispute_id", ondelete="CASCADE"), nullable=False)
    image_url = Column(String(2048), nullable=False)
    uploaded_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    dispute = relationship("Dispute", back_populates="evidence")
