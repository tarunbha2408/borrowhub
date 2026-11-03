from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    notif_id: int
    title: str
    message: str
    type: str
    reference_type: str
    reference_id: Optional[int] = None
    is_read: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
