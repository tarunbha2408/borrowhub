from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, model_validator, ConfigDict


class BorrowRequestCreate(BaseModel):
    item_id: int
    start_date: date
    end_date: date
    request_message: Optional[str] = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("End date cannot be earlier than start date.")
        return self


class BorrowDecisionRequest(BaseModel):
    decision_note: Optional[str] = None


class BorrowRequestOut(BaseModel):
    request_id: int
    item_id: int
    item_title: str
    item_image: Optional[str] = None
    item_condition: str
    borrower_id: int
    borrower_name: str
    borrower_email: str
    borrower_roll: str
    owner_id: int
    owner_name: str
    start_date: date
    end_date: date
    days_count: int
    daily_fee: Decimal
    deposit_amount: Decimal
    total_fee: Decimal
    total_payable: Decimal
    request_message: Optional[str] = None
    status: str
    requested_at: datetime
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    loan_id: Optional[int] = None
    loan_status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
