from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID


class IndustryDetectionRequest(BaseModel):
    file_content: str
    document_id: Optional[UUID] = None


class IndustryDetectionResponse(BaseModel):
    industry_id: Optional[UUID] = None
    industry_name: Optional[str] = None
    category_id: Optional[UUID] = None
    category_name: Optional[str] = None
    subcategory_id: Optional[UUID] = None
    subcategory_name: Optional[str] = None
    confidence: float = 0.0


class DocumentGenerationRequest(BaseModel):
    template_id: Optional[UUID] = None
    user_input: str = Field(..., validation_alias="prompt")
    tenant_id: Optional[UUID] = None
    industry_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    subcategory_id: Optional[UUID] = None
    industry_context: Optional[str] = None

    model_config = {
        "populate_by_name": True
    }


class DocumentGenerationResponse(BaseModel):
    content: str
    template_id: Optional[UUID] = None
    document_url: Optional[str] = None


class MultimodalAnalysisRequest(BaseModel):
    text: str
    image_urls: List[str]


class DocumentChatRequest(BaseModel):
    user_input: str = Field(..., validation_alias="prompt")

    model_config = {
        "populate_by_name": True
    }


class DocumentChatSuggestion(BaseModel):
    label: str
    type: str = "question" # question, insight, warning


class DocumentChatResponse(BaseModel):
    response: str
    suggestions: List[DocumentChatSuggestion] = []
    chart_data: Optional[Dict[str, Any]] = None
