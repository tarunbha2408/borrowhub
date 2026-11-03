from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, String, Text, Numeric, DateTime, ForeignKey,
    Enum as SQLEnum, SmallInteger
)
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class Category(Base):
    __tablename__ = "category"

    category_id = Column(Integer, primary_key=True, autoincrement=True)
    category_name = Column(String(80), unique=True, nullable=False)
    category_description = Column(Text, nullable=True)

    items = relationship("Item", back_populates="category")


class PickupLocation(Base):
    __tablename__ = "pickup_location"

    location_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), unique=True, nullable=False)
    description = Column(String(255), nullable=True)

    items = relationship("Item", back_populates="location")


class Item(Base):
    __tablename__ = "item"

    item_id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("app_user.user_id", ondelete="RESTRICT"), nullable=False)
    category_id = Column(Integer, ForeignKey("category.category_id", ondelete="RESTRICT"), nullable=False)
    location_id = Column(Integer, ForeignKey("pickup_location.location_id", ondelete="RESTRICT"), nullable=True)
    title = Column(String(160), nullable=False)
    description = Column(Text, nullable=True)
    item_condition = Column(
        SQLEnum("NEW", "GOOD", "FAIR", "WORN", "DAMAGED", name="item_condition"),
        nullable=False,
        default="GOOD"
    )
    deposit_amount = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    daily_fee = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    max_borrow_days = Column(Integer, nullable=False, default=1)
    listing_status = Column(
        SQLEnum("ACTIVE", "PAUSED", "ARCHIVED", name="listing_status"),
        nullable=False,
        default="ACTIVE"
    )
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime, nullable=True)

    # Relationships
    owner = relationship("AppUser", back_populates="items")
    category = relationship("Category", back_populates="items")
    location = relationship("PickupLocation", back_populates="items")
    images = relationship("ItemImage", back_populates="item", cascade="all, delete-orphan", order_by="ItemImage.sort_order")
    borrow_requests = relationship("BorrowRequest", back_populates="item")
    booked_dates = relationship("BookedDate", back_populates="item", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="item", cascade="all, delete-orphan")


class ItemImage(Base):
    __tablename__ = "item_image"

    image_id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("item.item_id", ondelete="CASCADE"), nullable=False)
    image_url = Column(String(2048), nullable=False)
    sort_order = Column(SmallInteger, nullable=False, default=0)
    is_primary = Column(SmallInteger, nullable=False, default=0)
    uploaded_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    item = relationship("Item", back_populates="images")


class Favorite(Base):
    __tablename__ = "favorite"

    user_id = Column(Integer, ForeignKey("app_user.user_id", ondelete="CASCADE"), primary_key=True)
    item_id = Column(Integer, ForeignKey("item.item_id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    user = relationship("AppUser", back_populates="favorites")
    item = relationship("Item", back_populates="favorites")
