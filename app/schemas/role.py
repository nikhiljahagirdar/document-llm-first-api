from pydantic import BaseModel
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime

class RoleBase(BaseModel):
    name: str
    permissions: Optional[Dict[str, Any]] = {}

class RoleCreate(RoleBase):
    pass

class RoleUpdate(BaseModel):
    name: Optional[str] = None
    permissions: Optional[Dict[str, Any]] = None

class RoleResponse(RoleBase):
    role_id: UUID
    tenant_id: Optional[UUID] = None
    is_active: Optional[bool] = True
    created_on: Optional[datetime] = None
    updated_on: Optional[datetime] = None

    class Config:
        from_attributes = True
