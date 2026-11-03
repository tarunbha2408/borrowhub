from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator


class LoanOut(BaseModel):
    loan_id: int
    request_id: int
    item_id: int
    item_title: str
    item_image: Optional[str] = None
    borrower_id: int
    borrower_name: str
    borrower_email: str
    owner_id: int
    owner_name: str
    owner_email: str
    status: str
    issued_at: Optional[datetime] = None
    due_at: datetime
    returned_at: Optional[datetime] = None
    agreed_daily_fee: Decimal
    agreed_deposit: Decimal
    agreed_total_fee: Decimal
    total_payable: Decimal
    late_fee: Decimal
    deposit_status: str
    deposit_deducted: Decimal
    handover_otp: Optional[str] = None  # Populated only for borrower in SCHEDULED state
    return_otp: Optional[str] = None    # Populated only for eligible party in ACTIVE state
    is_owner: bool = False
    is_borrower: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HandoverVerifyRequest(BaseModel):
    handover_otp: str = Field(..., min_length=6, max_length=6)
    condition_found: str = Field("GOOD", pattern="^(NEW|GOOD|FAIR|WORN|DAMAGED)$")
    notes: Optional[str] = None


class ReturnSubmitRequest(BaseModel):
    condition_found: str = Field("GOOD", pattern="^(NEW|GOOD|FAIR|WORN|DAMAGED)$")
    notes: Optional[str] = None


class ReturnVerifyRequest(BaseModel):
    return_otp: str = Field(..., min_length=6, max_length=6)
    counterparty_notes: Optional[str] = None
    agree: bool = True


class DepositSettleRequest(BaseModel):
    deduct_amount: Decimal = Field(Decimal("0.00"), ge=0)
    damage_fee_deduction: Optional[Decimal] = Field(None, ge=0)
    late_fee_deduction: Optional[Decimal] = Field(None, ge=0)
    settlement_reason: Optional[str] = None
    refund_method: str = Field("UPI", pattern="^(UPI|CARD|CASH|ORIGINAL)$")

    @model_validator(mode="before")
    @classmethod
    def reconcile_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "deduct_amount" not in data or data.get("deduct_amount") is None:
                dmg = Decimal(str(data.get("damage_fee_deduction") or 0))
                lte = Decimal(str(data.get("late_fee_deduction") or 0))
                data["deduct_amount"] = dmg + lte
            if data.get("refund_method") == "ORIGINAL":
                data["refund_method"] = "UPI"
        return data
