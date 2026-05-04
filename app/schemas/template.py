from pydantic import BaseModel
from uuid import UUID
from typing import Optional, Dict, Any

class TemplateBase(BaseModel):
    industry_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    subcategory_id: Optional[UUID] = None
    template_name: str
    description: Optional[str] = None
    template_schema: Optional[Dict[str, Any]] = None
    document_type: Optional[str] = None
    html_content: Optional[str] = None
    category: Optional[str] = None # String field for backward compatibility
    subcategory: Optional[str] = None # String field for backward compatibility
    title: Optional[str] = None
    subtitle: Optional[str] = None
    footer: Optional[str] = None
    header_image: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_public: bool = False

class TemplateCreate(TemplateBase):
    template_name: Optional[str] = None
    prompt: Optional[str] = None

class TemplateUpdate(BaseModel):
    industry_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    subcategory_id: Optional[UUID] = None
    template_name: Optional[str] = None
    description: Optional[str] = None
    template_schema: Optional[Dict[str, Any]] = None
    document_type: Optional[str] = None
    html_content: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    footer: Optional[str] = None
    header_image: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_public: Optional[bool] = None

class TemplateResponse(BaseModel):
    template_id: UUID
    tenant_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    industry_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    subcategory_id: Optional[UUID] = None
    template_name: str
    description: Optional[str] = None
    template_schema: Optional[Dict[str, Any]] = None
    document_type: Optional[str] = None
    html_content: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    footer: Optional[str] = None
    header_image: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_public: bool = False

    class Config:
        from_attributes = True

class TemplateGenerateRequest(BaseModel):
    data: Optional[Dict[str, Any]] = None # JSON data
    csv_data: Optional[str] = None # Base64 or raw CSV string
    sections: Optional[Dict[str, Any]] = None # Section-specific data
    filename: Optional[str] = None
    output_format: str = "pdf" # "pdf" or "docx"

