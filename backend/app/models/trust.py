from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey,
    Enum as SQLEnum, SmallInteger, CHAR
)
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class Review(Base):
    __tablename__ = "review"

    review_id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(Integer, ForeignKey("loan.loan_id", ondelete="RESTRICT"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("app_user.user_id", ondelete="RESTRICT"), nullable=False)
    reviewee_id = Column(Integer, ForeignKey("app_user.user_id", ondelete="RESTRICT"), nullable=False)
    rating = Column(SmallInteger, nullable=False)
    review_text = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    loan = relationship("Loan", back_populates="reviews")
    reviewer = relationship("AppUser", foreign_keys=[reviewer_id])
    reviewee = relationship("AppUser", foreign_keys=[reviewee_id])


class LoanInspection(Base):
    __tablename__ = "loan_inspection"

    inspection_id = Column(Integer, primary_key=True, autoincrement=True)
    loan_id = Column(Integer, ForeignKey("loan.loan_id", ondelete="RESTRICT"), nullable=False)
    stage = Column(SQLEnum("HANDOVER", "RETURN", name="inspection_stage"), nullable=False)
    inspected_by = Column(Integer, ForeignKey("app_user.user_id", ondelete="RESTRICT"), nullable=False)
    confirmed_by = Column(Integer, ForeignKey("app_user.user_id", ondelete="RESTRICT"), nullable=True)
    condition_found = Column(
        SQLEnum("NEW", "GOOD", "FAIR", "WORN", "DAMAGED", name="inspection_condition"),
        nullable=False
    )
    notes = Column(Text, nullable=True)
    counterparty_notes = Column(Text, nullable=True)
    owner_agreed = Column(SmallInteger, nullable=False, default=0)
    owner_agreed_at = Column(DateTime, nullable=True)
    borrower_agreed = Column(SmallInteger, nullable=False, default=0)
    borrower_agreed_at = Column(DateTime, nullable=True)
    provided_otp_hash = Column(CHAR(64), nullable=True)
    otp_verified = Column(SmallInteger, nullable=False, default=0)
    inspection_status = Column(
        SQLEnum("PENDING_COUNTERPARTY", "VERIFIED", "DISPUTED", name="inspection_status"),
        nullable=False,
        default="PENDING_COUNTERPARTY"
    )
    inspected_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    verified_at = Column(DateTime, nullable=True)

    loan = relationship("Loan", back_populates="inspections")
    inspector = relationship("AppUser", foreign_keys=[inspected_by])
    confirmer = relationship("AppUser", foreign_keys=[confirmed_by])
    photos = relationship("InspectionPhoto", back_populates="inspection", cascade="all, delete-orphan")


class InspectionPhoto(Base):
    __tablename__ = "inspection_photo"

    photo_id = Column(Integer, primary_key=True, autoincrement=True)
    inspection_id = Column(Integer, ForeignKey("loan_inspection.inspection_id", ondelete="CASCADE"), nullable=False)
    image_url = Column(String(2048), nullable=False)
    uploaded_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    inspection = relationship("LoanInspection", back_populates="photos")
