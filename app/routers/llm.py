from typing import Dict, Any, List, Optional
import uuid
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Body, status
from pydantic import BaseModel, Field

from app.schemas import (
    IndustryDetectionResponse,
    IndustryDetectionRequest,
    DocumentGenerationResponse,
    DocumentGenerationRequest,
    MultimodalAnalysisRequest,
    DocumentChatResponse,
)
from app.db_raw import get_raw_db
from app.dependencies import get_current_user
from app.services.rag_service import RAGService
from app.services.llm_service import LLMService
from app.services.render_service import generate_docx_template
from app.services.storage_service import upload_bytes_to_s3, get_s3_key_from_url, generate_presigned_url
from app.services.db.industry_db_service import IndustryDBService
from app.services.db.template_db_service import TemplateDBService
from app.services.db.document_db_service import DocumentDBService
from app.services.db.category_db_service import CategoryDBService
from app.services.db.subcategory_db_service import SubcategoryDBService

router = APIRouter(prefix="/llm", tags=["AI & LLM Services"])


class ChatMessage(BaseModel):
    role: str = Field(..., description="Role: 'user' or 'assistant'")
    content: str = Field(..., description="The message content")

class ChatDocumentRequest(BaseModel):
    document_id: uuid.UUID = Field(..., description="The ID of the document to chat with")
    user_input: str = Field(..., description="The user's question or message")
    history: Optional[List[ChatMessage]] = Field(default_factory=list, description="Optional chat history for context")

class ChatRAGRequest(BaseModel):
    user_input: str = Field(..., description="The user's question or message")
    history: Optional[List[ChatMessage]] = Field(default_factory=list, description="Optional chat history for context")


async def get_industry_service():
    return IndustryDBService()


async def get_template_service():
    return TemplateDBService()


async def get_document_service():
    return DocumentDBService()


async def get_category_service():
    return CategoryDBService()


async def get_subcategory_service():
    return SubcategoryDBService()


@router.get("/rag-health", tags=["AI & LLM Services"])
async def check_rag_health(
    conn: Any = Depends(get_raw_db)
):
    """
    **Check RAG Database Health**

    Tests the database connection to the PostgreSQL database
    and returns the total number of document chunks currently indexed.
    """
    try:
        from app.db_raw import DBWrapper
        result = await DBWrapper.fetch_one(conn, "SELECT COUNT(*) as count FROM document_chunks")
        doc_count = result["count"] if result else 0
        return {
            "status": "connected",
            "vector_database": "pgvector",
            "total_chunks_indexed": doc_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG Database connection failed: {e}")


@router.post("/detect-industry", response_model=IndustryDetectionResponse)
async def detect_document_industry(
    request: IndustryDetectionRequest,
    conn: Any = Depends(get_raw_db),
    current_user: Any = Depends(get_current_user),
    service: IndustryDBService = Depends(get_industry_service),
    sub_service: SubcategoryDBService = Depends(get_subcategory_service),
    doc_service: DocumentDBService = Depends(get_document_service),
):
    """
    **AI Industry & Category Detection**

    Analyzes document text and automatically maps it to the best matching Industry, Category, and Subcategory
    based on the tenant's configured hierarchy. Returns UUIDs and confidence levels.
    """
    # Fetch all subcategories with their parent hierarchy (flat list) for better precision
    subcategories = await sub_service.get_all_subcategories_with_parents(conn)

    detection = await LLMService.detect_industry(
        request.file_content, subcategories, current_user.tenant_id, conn
    )

    # If document_id is provided, update the document record with the detected classification
    if request.document_id and "error" not in detection:
        try:
            industry_id = detection.get("industry_id")
            category_id = detection.get("category_id")
            subcategory_id = detection.get("subcategory_id")

            if industry_id and category_id and subcategory_id:
                update_query = """
                    UPDATE documents 
                    SET industry_id = %s::uuid, 
                        category_id = %s::uuid, 
                        subcategory_id = %s::uuid, 
                        updated_on = NOW() 
                    WHERE document_id = %s::uuid AND tenant_id = %s::uuid
                """
                await doc_service.execute(
                    conn, 
                    update_query, 
                    (industry_id, category_id, subcategory_id, request.document_id, current_user.tenant_id)
                )

                # Log the classification in document history
                await doc_service.update_document_statuses(
                    conn, 
                    request.document_id, 
                    "completed", 
                    f"AI detected classification: {detection.get('industry_name')} > {detection.get('category_name')} > {detection.get('subcategory_name')}",
                    current_user.user_id
                )
        except Exception as e:
            # We don't want to fail the whole request if only the DB update fails
            print(f"DEBUG: Failed to update document classification: {e}")

    if "error" in detection and "LIMIT_REACHED" in detection["error"]:
        raise HTTPException(status_code=403, detail=detection["error"])

    return detection


@router.post("/generate", response_model=DocumentGenerationResponse)
async def generate_document(
    request: DocumentGenerationRequest,
    conn: Any = Depends(get_raw_db),
    current_user: Any = Depends(get_current_user),
    service: TemplateDBService = Depends(get_template_service),
    ind_service: IndustryDBService = Depends(get_industry_service),
    cat_service: CategoryDBService = Depends(get_category_service),
    sub_service: SubcategoryDBService = Depends(get_subcategory_service),
):
    """
    **AI Document Generation**

    Generates a new, professional document based on a template and user-provided context.
    - If `template_id` is provided, it uses that specific template.
    - Otherwise, it searches for a suitable template based on industry/category criteria.
    - Generates a `.docx` file, uploads it to S3, and records it as a `GeneratedReport`.
    """
    template = None

    if request.template_id:
        template = await service.get_template(conn, request.template_id)
    else:
        # Fallback to search by criteria if no template_id
        public_tpls = await service.list_public_templates(
            conn,
            industry_id=request.industry_id,
            category_id=request.category_id,
            subcategory_id=request.subcategory_id,
        )
        if public_tpls:
            template = public_tpls[0]
        else:
            # Absolute fallback: just get ANY public template if criteria search fails
            all_public = await service.list_public_templates(conn, limit=1)
            if all_public:
                template = all_public[0]

    if not template:
        raise HTTPException(
            status_code=404,
            detail="No document templates available. Please create a template first.",
        )

    template_content = template.get("html_content") or template.get("description") or ""

    # 2. Fetch context if IDs provided
    context_parts = []
    subcategory_prompt = None
    if request.industry_id:
        ind = await ind_service.get_industry(conn, request.industry_id)
        if ind:
            context_parts.append(f"Industry: {ind['name']}")
    elif request.industry_context:
        context_parts.append(f"Industry Context: {request.industry_context}")

    if request.category_id:
        cat = await cat_service.get_category(conn, request.category_id)
        if cat:
            context_parts.append(f"Category: {cat['name']}")

    if request.subcategory_id:
        sub = await sub_service.get_subcategory(conn, request.subcategory_id)
        if sub:
            context_parts.append(f"Subcategory: {sub['name']}")
            subcategory_prompt = sub.get("prompt")

    full_context = " | ".join(context_parts) if context_parts else "General"

    # 3. Call LLM Service
    generated_content = await LLMService.generate_document(
        template_content,
        request.user_input,
        full_context,
        current_user.tenant_id,
        conn,
        override_prompt=subcategory_prompt,
    )

    if isinstance(generated_content, str) and "LIMIT_REACHED" in generated_content:
        raise HTTPException(status_code=403, detail="LIMIT_REACHED: AI Usage token limit exceeded. Please upgrade your plan.")

    # 4. Produce .docx and upload to S3
    docx_data = {
        "template_name": template.get("template_name") or template.get("name"),
        "industry_name": next(
            (p.split(": ")[1] for p in context_parts if "Industry" in p), "N/A"
        ),
        "category_name": next(
            (p.split(": ")[1] for p in context_parts if "Category" in p), "N/A"
        ),
        "subcategory_name": next(
            (p.split(": ")[1] for p in context_parts if "Subcategory" in p), "N/A"
        ),
        "description": f"AI generated based on: {request.user_input[:100]}...",
        "html_content": generated_content,
    }

    docx_bytes = await generate_docx_template(docx_data)

    unique_id = uuid.uuid4()
    s3_filename = f"generated/{unique_id}_report.docx"
    document_url = await upload_bytes_to_s3(
        docx_bytes,
        s3_filename,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    # 5. Record in GeneratedReport
    from app.services.db.report_db_service import ReportDBService

    report_service = ReportDBService()

    report_id = uuid.uuid4()
    now = datetime.now()
    report_data = {
        "report_id": report_id,
        "user_id": current_user.user_id,
        "template_id": template["template_id"],
        "title": docx_data["template_name"],
        "content_markdown": generated_content,
        "original_prompt": request.user_input,
        "structured_data": {"s3_url": document_url},
        "created_on": now,
        "updated_on": now,
    }
    await report_service.create_report(conn, report_data)

    presigned_url = generate_presigned_url(get_s3_key_from_url(document_url)) or document_url

    return {
        "content": generated_content,
        "template_id": template["template_id"],
        "document_url": presigned_url,
    }


@router.post("/analyze-multimodal")
async def analyze_multimodal(
    request: MultimodalAnalysisRequest,
    conn: Any = Depends(get_raw_db),
    current_user: Any = Depends(get_current_user),
):
    """
    **AI Multimodal Analysis**

    Performs deep analysis on a combination of document text and multiple associated images.
    Provides cross-modal insights and summaries.
    """
    analysis = await LLMService.analyze_multimodal(
        request.text, request.image_urls, current_user.tenant_id, conn
    )
    if isinstance(analysis, str) and "LIMIT_REACHED" in analysis:
        raise HTTPException(status_code=403, detail="LIMIT_REACHED: AI Usage token limit exceeded.")
    if isinstance(analysis, dict) and "error" in analysis and "LIMIT_REACHED" in analysis["error"]:
        raise HTTPException(status_code=403, detail=analysis["error"])
    return {"analysis": analysis}


@router.get("/documents/{document_id}/suggestions")
async def get_document_suggestions(
    document_id: uuid.UUID,
    conn: Any = Depends(get_raw_db),
    current_user: Any = Depends(get_current_user),
    doc_service: DocumentDBService = Depends(get_document_service),
):
    """
    **Proactive Document Insights**

    Analyzes the content of a specific document and generates 3-4 proactive suggestions,
    risk warnings, or follow-up questions to help the user understand the document better.
    """
    document = await doc_service.get_document(
        conn, document_id, current_user.tenant_id, is_admin=True
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get latest content from versions
    versions = await doc_service.get_versions(conn, document_id)
    if not versions:
        return {"suggestions": []}

    context = versions[0].get("content", "")
    raw_suggestions = await LLMService.generate_suggestions(
        context, current_user.tenant_id, conn, current_user.user_id
    )
    if raw_suggestions and isinstance(raw_suggestions, list) and len(raw_suggestions) > 0:
        if "LIMIT_REACHED" in raw_suggestions[0]:
            raise HTTPException(status_code=403, detail=raw_suggestions[0])
            
    suggestions = [{"label": s, "type": "insight"} for s in raw_suggestions]
    return {"suggestions": suggestions}


@router.post("/chat/summarize")
async def summarize_chat(
    body: Dict[str, Any] = Body(...),
    conn: Any = Depends(get_raw_db),
    current_user: Any = Depends(get_current_user),
):
    """
    **AI Summarization**

    Summarizes a block of text or document content into a concise, professional executive summary.
    """
    text_to_summarize = (
        body.get("text")
        or body.get("content")
        or body.get("message")
        or body.get("user_input")
    )

    if not text_to_summarize:
        if len(body) == 1 and isinstance(list(body.values())[0], str):
            text_to_summarize = list(body.values())[0]
        elif body:
            text_to_summarize = json.dumps(body)
        else:
            raise HTTPException(
                status_code=400, detail="No content found in request body to summarize"
            )

    summary = await LLMService.summarize_text(
        str(text_to_summarize), current_user.tenant_id, conn
    )
    if isinstance(summary, str) and "LIMIT_REACHED" in summary:
        raise HTTPException(status_code=403, detail="LIMIT_REACHED: AI Usage token limit exceeded. Please upgrade your plan.")
    return {"summary": summary}


@router.post("/chat/document", response_model=DocumentChatResponse)
async def chat_with_document(
    request: ChatDocumentRequest,
    conn: Any = Depends(get_raw_db),
    current_user: Any = Depends(get_current_user),
    doc_service: DocumentDBService = Depends(get_document_service),
):
    """
    **Focused Document Chat (RAG)**

    Allows a conversation focused on a single specific document.
    Uses semantic search (RAG) to find relevant sections and provides an answer
    along with **intelligent follow-up suggestions**.
    """
    document_id = request.document_id
    user_input = request.user_input
    document = await doc_service.get_document(
        conn, document_id, current_user.tenant_id, is_admin=True
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    now = datetime.now()

    # Audit log entry for user question
    await doc_service.execute(
        conn,
        "INSERT INTO document_history (history_id, document_id, user_id, event_type, message, created_on, updated_on) VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s)",
        (
            uuid.uuid4(),
            document_id,
            current_user.user_id,
            "user_chat",
            user_input,
            now,
            now,
        ),
    )

    ai_response = await RAGService.query_with_rag(
        conn=conn,
        query=user_input,
        tenant_id=current_user.tenant_id,
        document_id=document_id,
        history=request.history
    )

    if isinstance(ai_response, str) and "LIMIT_REACHED" in ai_response:
        raise HTTPException(status_code=403, detail="LIMIT_REACHED: AI Usage token limit exceeded.")

    # Extract chart data if present
    chart_data = None
    clean_response = ai_response
    if "### DATA_FOR_CHART ###" in ai_response:
        try:
            parts = ai_response.split("### DATA_FOR_CHART ###")
            clean_response = parts[0].strip()
            chart_json = parts[1].strip()
            # Handle potential markdown code blocks around the JSON
            if chart_json.startswith("```"):
                chart_json = chart_json.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            chart_data = json.loads(chart_json)
        except Exception as e:
            print(f"DEBUG: Failed to parse chart data: {e}")

    # Generate suggestions based on the new context (response)
    raw_suggestions = await LLMService.generate_suggestions(
        f"User asked: {user_input}\nAI responded: {clean_response}", 
        current_user.tenant_id, 
        conn, 
        current_user.user_id
    )
    suggestions = [{"label": s, "type": "question"} for s in raw_suggestions]

    # Audit log entry for AI response
    await doc_service.execute(
        conn,
        "INSERT INTO document_history (history_id, document_id, user_id, event_type, message, created_on, updated_on) VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s)",
        (
            uuid.uuid4(),
            document_id,
            current_user.user_id,
            "ai_response",
            clean_response,
            now,
            now,
        ),
    )

    return {"response": clean_response, "suggestions": suggestions, "chart_data": chart_data}


@router.post("/rag-agent", response_model=DocumentChatResponse)
async def general_rag_agent(
    request: ChatRAGRequest,
    conn: Any = Depends(get_raw_db),
    current_user: Any = Depends(get_current_user),
):
    """
    **General Knowledge Agent (Tenant-wide RAG)**

    Queries across ALL documents belonging to the current tenant.
    Acts as an intelligent agent to decompose the query, search multiple times, and provide a unified answer
    and **intelligent follow-up suggestions**.
    """
    ai_response = await RAGService.query_with_agent(
        conn=conn, query=request.user_input, tenant_id=current_user.tenant_id, history=request.history
    )

    if isinstance(ai_response, str) and "LIMIT_REACHED" in ai_response:
        raise HTTPException(status_code=403, detail="LIMIT_REACHED: AI Usage token limit exceeded.")

    # Extract chart data if present
    chart_data = None
    clean_response = ai_response
    if "### DATA_FOR_CHART ###" in ai_response:
        try:
            parts = ai_response.split("### DATA_FOR_CHART ###")
            clean_response = parts[0].strip()
            chart_json = parts[1].strip()
            if chart_json.startswith("```"):
                chart_json = chart_json.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            chart_data = json.loads(chart_json)
        except Exception as e:
            print(f"DEBUG: Failed to parse chart data in RAG Agent: {e}")

    # Generate general suggestions
    raw_suggestions = await LLMService.generate_suggestions(
        f"User asked: {request.user_input}\nAI responded: {clean_response}", 
        current_user.tenant_id, 
        conn, 
        current_user.user_id
    )
    suggestions = [{"label": s, "type": "question"} for s in raw_suggestions]

    return {"response": clean_response, "suggestions": suggestions, "chart_data": chart_data}
