from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, BigInteger, String, DateTime, ForeignKey,
    Enum as SQLEnum, SmallInteger, Boolean
)
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class AppUser(Base):
    __tablename__ = "app_user"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    roll_number = Column(String(30), unique=True, nullable=False)
    full_name = Column(String(120), nullable=False)
    svnit_email = Column(String(254), unique=True, nullable=False)
    phone = Column(String(20), nullable=True)
    hostel_or_dept = Column(String(100), nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(SQLEnum("STUDENT", "MODERATOR", "ADMIN", name="user_role"), nullable=False, default="STUDENT")
    is_verified = Column(SmallInteger, nullable=False, default=0)
    is_active = Column(SmallInteger, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    # Timestamp of the last credential change; tokens issued before it are rejected.
    password_changed_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    # Relationships
    tokens = relationship("AuthToken", back_populates="user", cascade="all, delete-orphan")
    devices = relationship("DeviceToken", back_populates="user", cascade="all, delete-orphan")
    items = relationship("Item", back_populates="owner")
    borrow_requests = relationship("BorrowRequest", back_populates="borrower")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="user", cascade="all, delete-orphan")


class AuthToken(Base):
    __tablename__ = "auth_token"

    token_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("app_user.user_id", ondelete="CASCADE"), nullable=False)
    token_type = Column(SQLEnum("EMAIL_OTP", "PASSWORD_RESET", "REFRESH", name="token_type"), nullable=False)
    token_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    user = relationship("AppUser", back_populates="tokens")


class DeviceToken(Base):
    __tablename__ = "device_token"

    device_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("app_user.user_id", ondelete="CASCADE"), nullable=False)
    platform = Column(SQLEnum("ANDROID", "IOS", "WEB", name="platform_type"), nullable=False)
    push_token = Column(String(512), nullable=False)
    is_active = Column(SmallInteger, nullable=False, default=1)
    last_seen_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    user = relationship("AppUser", back_populates="devices")
