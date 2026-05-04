from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, List

class FolderBase(BaseModel):
    name: str
    description: Optional[str] = None
    parent_folder_id: Optional[UUID] = None

class FolderCreate(FolderBase):
    pass

class FolderUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_folder_id: Optional[UUID] = None

class FolderResponse(FolderBase):
    folder_id: UUID
    tenant_id: UUID
    user_id: UUID
    created_on: datetime
    updated_on: datetime

    class Config:
        from_attributes = True
