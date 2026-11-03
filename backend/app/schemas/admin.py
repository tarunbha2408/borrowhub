from datetime import datetime
from decimal import Decimal
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserRoleUpdate(BaseModel):
    role: str = Field(..., pattern="^(STUDENT|MODERATOR|ADMIN)$")


class ItemStatusUpdate(BaseModel):
    listing_status: str = Field(..., pattern="^(ACTIVE|PAUSED|ARCHIVED)$")


class SystemStatsOut(BaseModel):
    total_students: int
    total_listings: int
    active_listings: int
    active_loans: int
    completed_loans: int
    total_rental_volume: Decimal
    total_held_deposits: Decimal
    pending_disputes: int


class AuditLogOut(BaseModel):
    log_id: int
    actor_id: Optional[int] = None
    action: str
    entity_type: str
    entity_id: int
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
