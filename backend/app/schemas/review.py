from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class ReviewCreate(BaseModel):
    loan_id: int
    rating: int = Field(..., ge=1, le=5)
    review_text: Optional[str] = Field(None, max_length=1000)


class ReviewOut(BaseModel):
    review_id: int
    loan_id: int
    reviewer_id: int
    reviewer_name: str
    reviewee_id: int
    reviewee_name: str
    rating: int
    review_text: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
