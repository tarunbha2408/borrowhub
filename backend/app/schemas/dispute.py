from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class DisputeCreate(BaseModel):
    loan_id: int
    dispute_type: str = Field("OTHER", pattern="^(DAMAGE|NO_SHOW|LATE_RETURN|NON_PAYMENT|OTHER)$")
    description: str = Field(..., min_length=10, max_length=2000)
    amount_claimed: Decimal = Field(Decimal("0.00"), ge=0)
    evidence_urls: List[str] = Field(default_factory=list, max_length=5)


class DisputeResolve(BaseModel):
    amount_awarded: Decimal = Field(Decimal("0.00"), ge=0)
    resolution_note: str = Field(..., min_length=5, max_length=2000)
    status: str = Field("RESOLVED", pattern="^(RESOLVED|REJECTED)$")


class DisputeOut(BaseModel):
    dispute_id: int
    loan_id: int
    raised_by: int
    raised_by_name: str
    against_user_id: int
    against_user_name: str
    dispute_type: str
    description: str
    status: str
    amount_claimed: Decimal
    amount_awarded: Decimal
    resolution_note: Optional[str] = None
    evidence_urls: List[str] = Field(default_factory=list)
    created_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
