from typing import Optional
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from .enums import TenantTypeSchema

class TenantBase(BaseModel):
    name: str
    type: TenantTypeSchema
    slug: str
    org_name: Optional[str] = None
    address: Optional[str] = None

class TenantResponse(TenantBase):
    tenant_id: UUID
    is_active: Optional[bool] = True
    created_on: Optional[datetime] = None
    subscription_status: Optional[str] = None
    plan_name: Optional[str] = None

    class Config:
        from_attributes = True
