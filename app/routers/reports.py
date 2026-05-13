from fastapi import APIRouter, Depends, HTTPException, Body, status
from app.db_raw import get_raw_db
from app.schemas import GeneratedReportResponse
from app.dependencies import get_current_user, get_current_tenant
from app.services.llm_service import LLMService
from app.services.storage_service import (
    get_file_from_s3,
    get_s3_key_from_url,
)
from app.services.render_service import render_html_template
from app.services.document_processing import process_document
from app.services.db.report_db_service import ReportDBService
from app.services.db.document_db_service import DocumentDBService
from app.services.db.template_db_service import TemplateDBService
import uuid
import os
import json
from typing import List, Optional, Any
from datetime import datetime

router = APIRouter(prefix="/reports", tags=["reports"])

async def get_report_service():
    return ReportDBService()

async def get_document_service():
    return DocumentDBService()

async def get_template_service():
    return TemplateDBService()

@router.get("", response_model=List[GeneratedReportResponse])
async def get_my_reports(
    search: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    tenant: Any = Depends(get_current_tenant),
    conn: Any = Depends(get_raw_db),
    service: ReportDBService = Depends(get_report_service)
):
    """
    Retrieve reports generated for the current tenant.
    """
    return await service.list_reports(conn, tenant.tenant_id, limit, offset, search)

@router.post("/analyze", response_model=GeneratedReportResponse)
async def analyze_document(
    document_id: uuid.UUID = Body(...),
    template_id: uuid.UUID = Body(...),
    prompt: str = Body("Extract all fields including tables."),
    conn: Any = Depends(get_raw_db),
    current_user: Any = Depends(get_current_user),
    tenant: Any = Depends(get_current_tenant),
    service: ReportDBService = Depends(get_report_service),
    doc_service: DocumentDBService = Depends(get_document_service),
    tpl_service: TemplateDBService = Depends(get_template_service)
):
    """
    Analyze a document using a template and LLM.
    """
    # 1. Fetch document and template
    document = await doc_service.get_document(conn, document_id, tenant.tenant_id)
    template = await tpl_service.get_template(conn, template_id)

    if not document or not template:
        raise HTTPException(status_code=404, detail="Document or Template not found")

    # 2. Extract text (existing or fallback)
    ocr_res = await doc_service.get_ocr_result(conn, document_id)
    raw_text = ""
    
    if ocr_res and ocr_res["extracted_text"]:
        raw_text_data = ocr_res["extracted_text"]
        raw_text = raw_text_data.get("text", "") if isinstance(raw_text_data, dict) else str(raw_text_data)
    elif not document.get("file_url"):
        # Manual document, fetch content from versions
        versions = await doc_service.get_versions(conn, document_id)
        if versions:
            raw_text = versions[0].get("content", "")
    else:
        # Simplified: fallback to processing if text missing
        from app.routers.documents import UPLOAD_DIR
        local_filename = document["file_url"].split("/")[-1]
        local_path = os.path.join(UPLOAD_DIR, local_filename)
        if not os.path.exists(local_path):
             s3_key = get_s3_key_from_url(document["file_url"])
             file_bytes = await get_file_from_s3(s3_key)
             if file_bytes:
                 with open(local_path, "wb") as f: f.write(file_bytes)
        
        ext = os.path.splitext(document["filename"])[1].lower()
        res = await process_document(local_path, ext)
        raw_text = res.get("text", "")

    if not raw_text:
        raise HTTPException(status_code=500, detail="Text extraction failed")

    # 4. AI Extraction
    extraction_schema = template.get("template_schema") or {"summary": "string"}
    extracted_data, tokens_consumed = await LLMService.extract_structured_data(f"{prompt}\n\nContent: {raw_text[:20000]}", extraction_schema, tenant.tenant_id, conn)

    if "error" in extracted_data:
        raise HTTPException(status_code=500, detail=extracted_data["error"])

    rendered_content = await render_html_template(template.get("html_content"), extracted_data) if template.get("html_content") else "No Template"

    # 5. Save
    report_id = uuid.uuid4()
    now = datetime.now()
    report_data = {
        "report_id": report_id,
        "user_id": current_user.user_id,
        "template_id": template_id,
        "title": f"Analysis - {document['filename']}",
        "content_markdown": rendered_content,
        "structured_data": extracted_data,
        "chart_data": extracted_data,
        "tokens_consumed": tokens_consumed,
        "original_prompt": prompt,
        "version": 1,
        "created_on": now,
        "updated_on": now
    }
    await service.create_report(conn, report_data)
    
    return await service.get_report(conn, report_id, tenant.tenant_id)

@router.get("/{report_id}", response_model=GeneratedReportResponse)
async def get_report(
    report_id: uuid.UUID,
    tenant: Any = Depends(get_current_tenant),
    conn: Any = Depends(get_raw_db),
    service: ReportDBService = Depends(get_report_service)
):
    """
    Retrieve a specific report.
    """
    report = await service.get_report(conn, report_id, tenant.tenant_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report

@router.get("/{report_id}/versions", response_model=List[GeneratedReportResponse])
async def get_report_versions(
    report_id: uuid.UUID,
    tenant: Any = Depends(get_current_tenant),
    conn: Any = Depends(get_raw_db),
    service: ReportDBService = Depends(get_report_service)
):
    """
    Retrieve all versions of a report.
    """
    return await service.get_report_versions(conn, report_id, tenant.tenant_id)
