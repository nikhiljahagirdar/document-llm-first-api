from pydantic import BaseModel, Field, computed_field
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any

class AuditLogResponse(BaseModel):
    log_id: UUID
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_on: datetime
    updated_on: datetime

    @computed_field
    @property
    def timestamp(self) -> datetime:
        return self.created_on

    class Config:
        from_attributes = True
        populate_by_name = True
