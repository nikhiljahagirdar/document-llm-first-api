from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any, List

class DocumentVersionResponse(BaseModel):
    """Schema for document version information."""
    
    version_id: UUID = Field(
        ..., 
        description="Unique version identifier",
        examples=["123e4567-e89b-12d3-a456-426614174000"]
    )
    version_number: int = Field(
        ..., 
        ge=1,
        description="Version number (starts at 1)",
        examples=[1, 2, 3]
    )
    content: str = Field(
        ..., 
        description="Document content for this version",
        examples=["This is the document content..."]
    )
    created_on: Optional[datetime] = Field(
        None, 
        description="Timestamp when this version was created",
        examples=["2024-01-01T00:00:00Z"]
    )
    created_by: Optional[UUID] = Field(
        None, 
        description="User ID who created this version",
        examples=["123e4567-e89b-12d3-a456-426614174001"]
    )

    class Config:
        from_attributes = True

class DocumentImageResponse(BaseModel):
    """Schema for document image information."""
    
    image_id: UUID = Field(
        ..., 
        description="Unique image identifier",
        examples=["123e4567-e89b-12d3-a456-426614174000"]
    )
    image_url: str = Field(
        ..., 
        max_length=1000,
        description="URL to access the image",
        examples=["https://api.documentintelligence.com/images/123.jpg"]
    )
    created_on: Optional[datetime] = Field(
        None, 
        description="Timestamp when the image was extracted",
        examples=["2024-01-01T00:00:00Z"]
    )

    class Config:
        from_attributes = True

class DocumentResponse(BaseModel):
    """Comprehensive document response schema."""
    
    document_id: UUID = Field(
        ..., 
        description="Unique document identifier",
        examples=["123e4567-e89b-12d3-a456-426614174000"]
    )
    filename: str = Field(
        ..., 
        max_length=255,
        description="Original filename of the uploaded document",
        examples=["contract.pdf", "report.docx"]
    )
    file_url: str = Field(
        ..., 
        max_length=1000,
        description="URL to access the document file",
        examples=["https://api.documentintelligence.com/files/contract.pdf"]
    )
    industry_id: Optional[UUID] = Field(
        None, 
        description="Industry ID this document belongs to",
        examples=["123e4567-e89b-12d3-a456-426614174001"]
    )
    category_id: Optional[UUID] = Field(
        None, 
        description="Category ID this document belongs to",
        examples=["123e4567-e89b-12d3-a456-426614174002"]
    )
    subcategory_id: Optional[UUID] = Field(
        None, 
        description="Subcategory ID this document belongs to",
        examples=["123e4567-e89b-12d3-a456-426614174003"]
    )
    folder_id: Optional[UUID] = Field(
        None, 
        description="Folder ID where this document is stored",
        examples=["123e4567-e89b-12d3-a456-426614174004"]
    )
    industry_name: Optional[str] = Field(
        None, 
        max_length=100,
        description="Industry name (helper field for UI)",
        examples=["Legal", "Healthcare"]
    )
    category_name: Optional[str] = Field(
        None, 
        max_length=100,
        description="Category name (helper field for UI)",
        examples=["Contracts", "Reports"]
    )
    subcategory_name: Optional[str] = Field(
        None, 
        max_length=100,
        description="Subcategory name (helper field for UI)",
        examples=["Employment", "Financial"]
    )
    google_file_id: Optional[str] = Field(
        None, 
        max_length=100,
        description="Google Drive file ID if imported from Google Docs",
        examples=["1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"]
    )
    google_last_modified: Optional[datetime] = Field(
        None, 
        description="Last modification time in Google Drive",
        examples=["2024-01-01T00:00:00Z"]
    )
    status: str = Field(
        ..., 
        pattern="^(uploading|processing|completed|failed|archived)$",
        description="Document processing status",
        examples=["processing", "completed"]
    )
    file_size: Optional[int] = Field(
        None, 
        ge=0,
        description="File size in bytes",
        examples=[1048576]
    )
    file_type: Optional[str] = Field(
        None, 
        max_length=50,
        description="File MIME type or extension",
        examples=["application/pdf", "image/jpeg"]
    )
    page_count: Optional[int] = Field(
        None, 
        ge=0,
        description="Number of pages in the document",
        examples=[10]
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, 
        description="Additional document metadata extracted during processing",
        examples=[{"author": "John Doe", "created_date": "2024-01-01"}]
    )
    created_on: Optional[datetime] = Field(
        None, 
        description="Timestamp when the document was uploaded",
        examples=["2024-01-01T00:00:00Z"]
    )
    versions: Optional[List[DocumentVersionResponse]] = Field(
        default_factory=list, 
        description="List of document versions"
    )
    images: Optional[List[DocumentImageResponse]] = Field(
        default_factory=list, 
        description="List of extracted images from the document"
    )

    class Config:
        from_attributes = True

class DocumentListResponse(BaseModel):
    document_id: UUID
    filename: str
    file_url: str
    industry_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    subcategory_id: Optional[UUID] = None
    folder_id: Optional[UUID] = None
    industry_name: Optional[str] = None
    category_name: Optional[str] = None
    subcategory_name: Optional[str] = None
    google_file_id: Optional[str] = None
    google_last_modified: Optional[datetime] = None
    status: str
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    page_count: Optional[int] = None
    created_on: Optional[datetime] = None

    class Config:
        from_attributes = True

class DocumentCreateManual(BaseModel):
    filename: str
    content: str
    folder_id: Optional[UUID] = None
    industry_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    subcategory_id: Optional[UUID] = None

class GoogleDocImportRequest(BaseModel):
    url: str
    filename: Optional[str] = None
    folder_id: Optional[UUID] = None

class DocumentCreateFromTemplate(BaseModel):
    filename: str
    template_id: UUID
    folder_id: Optional[UUID] = None
    # Data to fill placeholders if any
    template_data: Optional[Dict[str, Any]] = None

class DocumentContentUpdate(BaseModel):
    content: str

class DocumentContentResponse(BaseModel):
    document_id: UUID
    version_number: int
    content: str
    created_on: Optional[datetime] = None

    class Config:
        from_attributes = True

class PaginatedDocumentContentResponse(BaseModel):
    document_id: UUID
    version_number: int
    content: str
    content_html: Optional[str] = None
    rich_content: Optional[Any] = None
    page: int
    page_size: int
    total_pages: int
    total_characters: int
    created_on: Optional[datetime] = None

    class Config:
        from_attributes = True

class GeneratedReportResponse(BaseModel):
    report_id: UUID
    parent_id: Optional[UUID] = None
    version: Optional[int] = 1
    original_prompt: Optional[str] = None
    title: str
    content_markdown: str
    structured_data: Optional[Dict[str, Any]] = None
    chart_data: Optional[Dict[str, Any]] = None
    tokens_consumed: Optional[int] = 0
    created_on: Optional[datetime] = None

    class Config:
        from_attributes = True
