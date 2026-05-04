from pydantic import BaseModel
from uuid import UUID
from typing import Optional, List

# Subcategory Schemas
class SubcategoryBase(BaseModel):
    category_id: UUID
    name: str
    description: Optional[str] = None
    prompt: Optional[str] = None

class SubcategoryCreate(SubcategoryBase):
    pass

class SubcategoryUpdate(BaseModel):
    category_id: Optional[UUID] = None
    name: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None

class SubcategoryResponse(SubcategoryBase):
    subcategory_id: UUID

    class Config:
        from_attributes = True

# Category Schemas
class CategoryBase(BaseModel):
    industry_id: UUID
    name: str
    description: Optional[str] = None

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    industry_id: Optional[UUID] = None
    name: Optional[str] = None
    description: Optional[str] = None

class CategoryResponse(CategoryBase):
    category_id: UUID
    subcategories: List[SubcategoryResponse] = []

    class Config:
        from_attributes = True

# Industry Schemas
class IndustryBase(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None

class IndustryCreate(IndustryBase):
    pass

class IndustryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None

class IndustryResponse(IndustryBase):
    industry_id: UUID
    categories: List[CategoryResponse] = []

    class Config:
        from_attributes = True
