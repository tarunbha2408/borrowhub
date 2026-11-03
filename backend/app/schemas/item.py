from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class CategoryOut(BaseModel):
    category_id: int
    category_name: str
    category_description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PickupLocationOut(BaseModel):
    location_id: int
    name: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ItemImageOut(BaseModel):
    image_id: int
    image_url: str
    sort_order: int
    is_primary: int

    model_config = ConfigDict(from_attributes=True)


class ItemCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=160)
    category_id: int
    location_id: Optional[int] = None
    custom_location: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = None
    item_condition: str = Field("GOOD", pattern="^(NEW|GOOD|FAIR|WORN|DAMAGED)$")
    deposit_amount: Decimal = Field(..., ge=0)
    daily_fee: Decimal = Field(..., ge=0)
    max_borrow_days: int = Field(..., ge=1, le=90)
    image_urls: List[str] = Field(default_factory=list, max_length=5)


class ItemUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=160)
    category_id: Optional[int] = None
    location_id: Optional[int] = None
    custom_location: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = None
    item_condition: Optional[str] = Field(None, pattern="^(NEW|GOOD|FAIR|WORN|DAMAGED)$")
    deposit_amount: Optional[Decimal] = Field(None, ge=0)
    daily_fee: Optional[Decimal] = Field(None, ge=0)
    max_borrow_days: Optional[int] = Field(None, ge=1, le=90)
    listing_status: Optional[str] = Field(None, pattern="^(ACTIVE|PAUSED|ARCHIVED)$")
    image_urls: Optional[List[str]] = Field(None, max_length=5)


class ItemOut(BaseModel):
    item_id: int
    owner_id: int
    owner_name: str
    owner_email: str
    owner_hostel: Optional[str] = None
    category_id: int
    category_name: str
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    title: str
    description: Optional[str] = None
    item_condition: str
    deposit_amount: Decimal
    daily_fee: Decimal
    max_borrow_days: int
    listing_status: str
    primary_image_url: Optional[str] = None
    is_favorite: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ItemDetailOut(ItemOut):
    images: List[ItemImageOut] = []
    average_rating: Optional[float] = None
    reviews_count: int = 0
