from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class NotificationResponse(BaseModel):
    notification_id: UUID
    title: str
    message: str
    type: str
    is_read: Optional[bool] = False
    created_on: Optional[datetime] = None

    class Config:
        from_attributes = True
