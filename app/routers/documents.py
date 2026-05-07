import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
import uuid
import shutil
import json
import asyncio
import httpx
import re
from datetime import datetime
from typing import List, Any, Optional

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Depends,
    HTTPException,
    BackgroundTasks,
    status,
)
import psycopg
from psycopg_pool import PoolClosed

from app.db_raw import get_raw_db, get_connection, DBWrapper
from app.dependencies import get_current_user, get_current_tenant
from app.schemas import (
    DocumentResponse,
    DocumentListResponse,
    PaginatedDocumentContentResponse,
    DocumentContentResponse,
    DocumentContentUpdate,
    DocumentCreateManual,
    DocumentCreateFromTemplate,
    GoogleDocImportRequest,
)
from app.services.storage_service import upload_to_s3, get_file_from_s3, get_s3_key_from_url, generate_presigned_url
from app.services.document_processing import (
    process_document, generate_page_previews
)
from app.services.embedding_service import get_text_embedding
from app.services.rag_service import RAGService
from app.services.llm_service import LLMService
from app.services.notification_service import NotificationService
from app.services.db.document_db_service import DocumentDBService
from app.services.db.template_db_service import TemplateDBService
from app.services.db.industry_db_service import IndustryDBService
from app.services.db.audit_log_db_service import AuditLogDBService
from app.services.db.metering_db_service import MeteringDBService
from app.config import settings

router = APIRouter(prefix="/documents", tags=["Documents Management"])

UPLOAD_DIR = settings.UPLOAD_DIR
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

async def run_async_notif(user_id: uuid.UUID, title: str, message: str, type: str):
    await NotificationService.send_notification(str(user_id), title, message, type)

def prepare_document_response(d: dict) -> dict:
    if not d: return {}
    
    # Generate a presigned URL for the main file if it's an S3 URL
    file_url = d["file_url"]
    metadata = d.get("metadata") or {}
    thumbnail_url = metadata.get("thumbnail_url")
    
    if thumbnail_url and "amazonaws.com" in thumbnail_url:
        thumb_key = get_s3_key_from_url(thumbnail_url)
        thumb_presigned = generate_presigned_url(thumb_key)
        if thumb_presigned:
            metadata["thumbnail_url"] = thumb_presigned

    if file_url and file_url.startswith("http") and "amazonaws.com" in file_url:
        s3_key = get_s3_key_from_url(file_url)
        presigned = generate_presigned_url(s3_key)
        if presigned:
            file_url = presigned

    # Also handle images if they are S3 URLs
    images = d.get("images", [])
    if images:
        for img in images:
            if img.get("image_url") and "amazonaws.com" in img["image_url"]:
                img_key = get_s3_key_from_url(img["image_url"])
                img_presigned = generate_presigned_url(img_key)
                if img_presigned:
                    img["image_url"] = img_presigned

    return {
        "document_id": str(d["document_id"]),
        "tenant_id": str(d["tenant_id"]),
        "user_id": str(d["user_id"]),
        "filename": d["filename"],
        "file_url": file_url,
        "status": d["status"],
        "file_size": d["file_size"],
        "file_type": d.get("file_type"),
        "page_count": d.get("page_count"),
        "metadata": metadata,
        "folder_id": str(d["folder_id"]) if d.get("folder_id") else None,
        "industry_id": str(d["industry_id"]) if d.get("industry_id") else None,
        "category_id": str(d["category_id"]) if d.get("category_id") else None,
        "subcategory_id": str(d["subcategory_id"]) if d.get("subcategory_id") else None,
        "industry_name": d.get("industry_name"),
        "category_name": d.get("category_name"),
        "subcategory_name": d.get("subcategory_name"),
        "google_file_id": d.get("google_file_id"),
        "google_last_modified": d.get("google_last_modified"),
        "created_on": d["created_on"],
        "updated_on": d["updated_on"],
        "versions": d.get("versions", []),
        "images": images
    }

async def get_document_service():
    return DocumentDBService()

async def get_template_service():
    return TemplateDBService()

async def get_industry_service():
    return IndustryDBService()

async def get_metering_service():
    return MeteringDBService()

processing_semaphore = asyncio.Semaphore(1)

def bg_log(msg):
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("bg_worker.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {msg}\n")

async def process_document_background(
    document_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID, original_file_path: str, file_extension: str
):
    """
    Background worker for document processing.
    Handles: Download, Extraction (Docling/Gemini), Categorization, Versioning, and RAG Ingestion.
    """
    from app.services.llm_service import LLMService
    service = DocumentDBService()
    ind_service = IndustryDBService()
    metering = MeteringDBService()
    
    # Task 2: Create a temp directory tenantid-documentid
    temp_dir = os.path.join(UPLOAD_DIR, f"temp-{tenant_id}-{document_id}")
    os.makedirs(temp_dir, exist_ok=True)
    
    # Move or copy the file to the temp directory for processing
    local_file_path = os.path.join(temp_dir, os.path.basename(original_file_path))
    if os.path.exists(original_file_path):
        shutil.copy2(original_file_path, local_file_path)
    
    async with processing_semaphore:
        bg_log(f"DEBUG: Starting background processing for document {document_id}")
        try:
            # 1. INITIAL FETCH & STATUS UPDATE
            async with get_connection() as conn:
                # CHECK OCR LIMIT
                await metering.check_usage_limits(conn, tenant_id, "ocr")
                
                document = await service.get_document(conn, document_id, tenant_id, is_admin=True)
                if not document:
                    bg_log(f"ERROR: Document {document_id} not found in DB for tenant {tenant_id}")
                    return

                # Ensure local file exists, download from S3 if missing
                if not os.path.exists(local_file_path):
                    bg_log(f"INFO: Local file missing at {local_file_path}, attempting download from S3")
                    s3_key = get_s3_key_from_url(document["file_url"])
                    file_bytes = await get_file_from_s3(s3_key)
                    if file_bytes:
                        with open(local_file_path, "wb") as f:
                            f.write(file_bytes)
                        bg_log(f"INFO: Successfully downloaded {document['filename']} to {local_file_path}")
                    else:
                        raise FileNotFoundError(f"Could not find local file or S3 object for document {document_id}")

                await service.update_document_statuses(
                    conn, document_id, "processing", f"Extracting text from {document['filename']}...", user_id
                )

            # 2. LONG RUNNING EXTRACTION (Release DB connection)
            bg_log(f"DEBUG: Calling process_document for {document_id}")
            
            # Start parallel preview generation (Thumbnail)
            preview_task = asyncio.create_task(generate_page_previews(local_file_path, tenant_id, document_id))
            
            processing_result = await process_document(local_file_path, file_extension, tenant_id=tenant_id, document_id=document_id)
            extracted_text = processing_result.get("text", "")
            rich_content = processing_result.get("rich_content") or {}
            
            # Wait for thumbnail
            thumbnail_url = await preview_task
            doc_metadata = processing_result.get("metadata") or {}
            if thumbnail_url:
                doc_metadata["thumbnail_url"] = thumbnail_url
                processing_result["metadata"] = doc_metadata
            
            bg_log(f"DEBUG: Extraction complete for {document_id}. Source: {processing_result.get('source')}")

            if not extracted_text:
                bg_log(f"DEBUG: Extraction failed for {document_id}")
                async with get_connection() as conn:
                    await service.update_document_statuses(
                        conn, document_id, "failed", "No text could be extracted", user_id
                    )
                return
            
            # Persist metadata
            async with get_connection() as conn:
                page_count = processing_result.get("page_count", 1)
                await service.update_document_metadata(
                    conn, 
                    document_id, 
                    processing_result.get("file_type", file_extension.lstrip('.')), 
                    page_count, 
                    processing_result.get("metadata", {})
                )
                # Log OCR Usage
                await LLMService.log_llm_usage(
                    conn, tenant_id, "OCR Usage (Pages)", page_count, user_id=user_id
                )
                
                # Save OCR result for auditing/dashboard
                await service.execute(
                    conn,
                    "INSERT INTO ocr_results (ocr_id, document_id, extracted_text, status) VALUES (%s::uuid, %s::uuid, %s, %s)",
                    (str(uuid.uuid4()), document_id, json.dumps({"text": extracted_text, "source": processing_result.get("source")}), "completed")
                )

            # 3. CATEGORIZATION & INDUSTRY DETECTION
            async with get_connection() as conn:
                await service.update_document_statuses(
                    conn, document_id, "processing", f"Categorizing {document['filename']}...", user_id
                )

                industries = await ind_service.list_industries(conn)
                detection = await LLMService.detect_industry(extracted_text, industries, tenant_id, conn, user_id=user_id)

                if detection and "error" not in detection:
                    await service.execute(
                        conn,
                        "UPDATE documents SET industry_id = %s::uuid, category_id = %s::uuid, subcategory_id = %s::uuid WHERE document_id::uuid = %s::uuid",
                        (detection.get("industry_id"), detection.get("category_id"), detection.get("subcategory_id"), document_id)
                    )

                # Task: Generate Global Document Embedding
                global_embedding = await get_text_embedding(processing_result.get("plain_text") or extracted_text)

                await service.save_document_version(
                    conn, 
                    document_id, 
                    1, 
                    processing_result.get("plain_text") or extracted_text, 
                    json.dumps(rich_content), 
                    user_id, 
                    json.dumps(processing_result.get("html")),
                    embedding=global_embedding
                )

            # 4. RAG INGESTION
            async with get_connection() as conn:
                await service.update_document_statuses(conn, document_id, "completed", "Success", user_id)
                
                # Await RAG indexing to ensure file is available
                await RAGService.ingest_document(None, document_id, tenant_id, extracted_text, file_path=local_file_path)
                
                # Record Audit Log for final processing success
                await AuditLogDBService.record_audit_log(
                    conn, tenant_id, user_id,
                    "document_processed", "document", str(document_id),
                    {"filename": document['filename'], "status": "success"}
                )

        except Exception as e:
            bg_log(f"ERROR: {document_id} failed: {e}")
            try:
                async with get_connection() as conn:
                    await service.update_document_statuses(conn, document_id, "failed", str(e), user_id)
                    # Record Audit Log for failure
                    await AuditLogDBService.record_audit_log(
                        conn, tenant_id, user_id,
                        "document_processing_failed", "document", str(document_id),
                        {"error": str(e)}
                    )
            except: pass
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            if os.path.exists(original_file_path):
                os.remove(original_file_path)


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    folder_id: Optional[uuid.UUID] = None,
    current_user: Any = Depends(get_current_user),
    tenant: Any = Depends(get_current_tenant),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: DocumentDBService = Depends(get_document_service),
    metering: MeteringDBService = Depends(get_metering_service)
):
    """
    **Upload and Process Document**

    Uploads a physical file (PDF, Image, Office) to secure storage and triggers an **AI-powered background processing pipeline**.
    - **Step 1:** Validate file and duplicate check.
    - **Step 2:** Upload to S3.
    - **Step 3:** Trigger extraction, categorization, and RAG ingestion.
    - **Returns:** 202 Accepted with document metadata. Check WebSocket or status endpoint for updates.
    """
    # CHECK STORAGE LIMIT
    await metering.check_usage_limits(conn, tenant.tenant_id, "storage")

    # Task 4: Check if file exists tell user that file already uploaded
    existing = await DBWrapper.fetch_one(
        conn, 
        "SELECT document_id FROM documents WHERE tenant_id = %s::uuid AND filename = %s AND is_active = TRUE",
        (tenant.tenant_id, file.filename)
    )
    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"A document with filename '{file.filename}' has already been uploaded for this tenant."
        )

    try:
        ext = os.path.splitext(file.filename)[1].lower()
        doc_id = uuid.uuid4()
        local_path = os.path.join(UPLOAD_DIR, f"{doc_id}{ext}")

        with open(local_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        try:
            s3_url = await upload_to_s3(local_path, f"tenant-{tenant.tenant_id}/documents/{doc_id}{ext}")
            
            doc = await service.create_document(
                conn, doc_id, tenant.tenant_id, current_user.user_id, file.filename, s3_url, os.path.getsize(local_path), folder_id
            )

            # Record Audit Log
            await AuditLogDBService.record_audit_log(
                conn, tenant.tenant_id, current_user.user_id,
                "document_upload", "document", str(doc_id),
                {"filename": file.filename}
            )

            background_tasks.add_task(process_document_background, doc_id, tenant.tenant_id, current_user.user_id, local_path, ext)
            return prepare_document_response(doc)
        except Exception as e:
            if os.path.exists(local_path): os.remove(local_path)
            err_msg = str(e)
            if "unique constraint" in err_msg.lower() or "uq_doc_tenant_filename" in err_msg:
                 raise HTTPException(status_code=400, detail=f"A document with filename '{file.filename}' already exists for this tenant.")
            
            bg_log(f"ERROR: Upload failed for {file.filename}: {err_msg}")
            raise HTTPException(status_code=500, detail=f"Upload failed: {err_msg}")
    except HTTPException:
        raise
    except Exception as e:
        bg_log(f"ERROR: Critical upload failure: {e}")
        raise HTTPException(status_code=500, detail=f"Critical upload failure: {e}")

@router.post("/manual", response_model=DocumentResponse)
async def create_document_manual(
    payload: DocumentCreateManual,
    current_user: Any = Depends(get_current_user),
    tenant: Any = Depends(get_current_tenant),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: DocumentDBService = Depends(get_document_service)
):
    """
    **Create Manual Document**

    Creates a new document entry based on raw text or HTML provided by the user. 
    Useful for creating notes or reports directly within the platform.
    """
    doc = await service.create_manual_document(
        conn,
        tenant.tenant_id,
        current_user.user_id,
        payload.filename,
        payload.content,
        payload.folder_id,
        payload.industry_id,
        payload.category_id,
        payload.subcategory_id
    )
    
    # Record Audit Log
    await AuditLogDBService.record_audit_log(
        conn, tenant.tenant_id, current_user.user_id,
        "document_manual_create", "document", str(doc["document_id"]),
        {"filename": payload.filename}
    )
    
    return prepare_document_response(doc)

@router.post("/from-template", response_model=DocumentResponse)
async def create_document_from_template(
    payload: DocumentCreateFromTemplate,
    current_user: Any = Depends(get_current_user),
    tenant: Any = Depends(get_current_tenant),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: DocumentDBService = Depends(get_document_service),
    tpl_service: TemplateDBService = Depends(get_template_service)
):
    """
    **Create Document from Template**

    Generates a new document using a pre-defined system or tenant template.
    Populates placeholders with provided `template_data`.
    """
    template = await tpl_service.get_template(conn, payload.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    content = template.get("html_content") or template.get("description") or ""
    
    # Simple placeholder replacement if template_data provided
    if payload.template_data:
        for key, val in payload.template_data.items():
            content = content.replace(f"{{{{{key}}}}}", str(val))
    
    doc = await service.create_manual_document(
        conn,
        tenant.tenant_id,
        current_user.user_id,
        payload.filename,
        content,
        payload.folder_id,
        template.get("industry_id"),
        template.get("category_id"),
        template.get("subcategory_id")
    )

    # Record Audit Log
    await AuditLogDBService.record_audit_log(
        conn, tenant.tenant_id, current_user.user_id,
        "document_from_template", "document", str(doc["document_id"]),
        {"filename": payload.filename, "template_id": str(payload.template_id)}
    )

    return prepare_document_response(doc)

@router.post("/import/google", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def import_google_doc(
    payload: GoogleDocImportRequest,
    background_tasks: BackgroundTasks,
    current_user: Any = Depends(get_current_user),
    tenant: Any = Depends(get_current_tenant),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: DocumentDBService = Depends(get_document_service),
    metering: MeteringDBService = Depends(get_metering_service)
):
    """
    **Import Google Doc**

    Downloads a Google Doc as a PDF and processes it.
    If the document is private, it uses the user's authorized Google Drive credentials.
    """
    await metering.check_usage_limits(conn, tenant.tenant_id, "storage")

    # Extract Document ID from URL
    match = re.search(r"/document/d/([a-zA-Z0-9-_]+)", payload.url)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid Google Docs URL format.")
    
    gdoc_id = match.group(1)
    
    # 1. Check for authorized credentials
    query = "SELECT access_token, refresh_token, expires_at FROM user_credentials WHERE user_id = %s AND provider = 'google'"
    creds = await DBWrapper.fetch_one(conn, query, (current_user.user_id,))
    
    access_token = None
    if creds:
        access_token = creds["access_token"]
        if creds["expires_at"] < datetime.now():
            # Refresh token
            async with httpx.AsyncClient() as client:
                refresh_res = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": settings.GOOGLE_CLIENT_ID,
                        "client_secret": settings.GOOGLE_CLIENT_SECRET,
                        "refresh_token": creds["refresh_token"],
                        "grant_type": "refresh_token",
                    }
                )
                if refresh_res.status_code == 200:
                    new_data = refresh_res.json()
                    access_token = new_data["access_token"]
                    expires_at = datetime.now() + timedelta(seconds=new_data.get("expires_in", 3600))
                    await DBWrapper.execute(
                        conn, 
                        "UPDATE user_credentials SET access_token = %s, expires_at = %s WHERE user_id = %s AND provider = 'google'",
                        (access_token, expires_at, current_user.user_id)
                    )

    # 2. Prepare export
    # For Google Docs, we export as PDF for high-quality extraction
    export_url = f"https://www.googleapis.com/drive/v3/files/{gdoc_id}/export?mimeType=application/pdf"
    
    filename = payload.filename or f"GoogleDoc_{gdoc_id}.pdf"
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
        
    doc_id = uuid.uuid4()
    local_path = os.path.join(UPLOAD_DIR, f"{doc_id}.pdf")

    try:
        headers = {}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
            
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(export_url, headers=headers, timeout=60.0)
            
            # If authorized fail, try public fallback if no credentials were used
            if response.status_code != 200 and not access_token:
                # Public fallback URL
                public_url = f"https://docs.google.com/document/d/{gdoc_id}/export?format=pdf"
                response = await client.get(public_url, timeout=30.0)

            if response.status_code != 200:
                detail = "Could not download document. Please ensure you have authorized Google Drive access or the document is public."
                if response.status_code == 403:
                    detail = "Access Denied. Please ensure you have authorized Google Drive access in the Integrations panel."
                raise HTTPException(status_code=response.status_code, detail=detail)
            
            with open(local_path, "wb") as f:
                f.write(response.content)

        s3_url = await upload_to_s3(local_path, f"tenant-{tenant.tenant_id}/documents/{doc_id}.pdf")
        
        doc = await service.create_document(
            conn, doc_id, tenant.tenant_id, current_user.user_id, filename, s3_url, os.path.getsize(local_path), payload.folder_id
        )

        await AuditLogDBService.record_audit_log(
            conn, tenant.tenant_id, current_user.user_id,
            "document_import_google", "document", str(doc_id),
            {"url": payload.url, "filename": filename, "private": bool(access_token)}
        )

        background_tasks.add_task(process_document_background, doc_id, tenant.tenant_id, current_user.user_id, local_path, ".pdf")
        return prepare_document_response(doc)
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(local_path): os.remove(local_path)
        bg_log(f"ERROR: Google Doc import failed: {e}")
        raise HTTPException(status_code=500, detail=f"Google Doc import failed: {e}")

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: Any = Depends(get_current_user),
    tenant: Any = Depends(get_current_tenant),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: DocumentDBService = Depends(get_document_service)
):
    """
    **Get Document Details**

    Retrieves full metadata, current status, and all versions/images associated with a specific document.
    """
    role_name = getattr(current_user.role, "name", "user") if hasattr(current_user, "role") else "user"
    is_admin = role_name in ["tenant_admin", "enterprise_tenant", "superadmin"]
    
    doc = await service.get_document(conn, document_id, tenant.tenant_id, current_user.user_id, is_admin)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc["versions"] = await service.get_versions(conn, document_id)
    doc["images"] = await service.get_images(conn, document_id)

    return prepare_document_response(doc)

@router.get("", response_model=List[DocumentListResponse])
async def get_documents(
    search: Optional[str] = None,
    folder_id: Optional[uuid.UUID] = None,
    limit: int = 20,
    offset: int = 0,
    current_user: Any = Depends(get_current_user),
    tenant: Any = Depends(get_current_tenant),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: DocumentDBService = Depends(get_document_service)
):
    """
    **List Documents**

    Returns a paginated list of documents accessible to the user.
    - Support for full-text search on filenames.
    - Filtering by `folder_id`.
    - Automatic tenant isolation.
    """
    role_name = getattr(current_user.role, "name", "user") if hasattr(current_user, "role") else "user"
    is_admin = role_name in ["tenant_admin", "enterprise_tenant", "superadmin"]
    
    return await service.list_documents(conn, tenant.tenant_id, current_user.user_id, is_admin, search, folder_id, limit, offset)

@router.get("/{document_id}/content", response_model=PaginatedDocumentContentResponse)
async def get_document_content(
    document_id: uuid.UUID,
    page: int = 1,
    page_size: int = 10000,
    current_user: Any = Depends(get_current_user),
    tenant: Any = Depends(get_current_tenant),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: DocumentDBService = Depends(get_document_service)
):
    """
    **Get Document Content (Paginated)**

    Retrieves the extracted text, HTML preview, and structured rich content for a document.
    - Supports **Physical Page-based Pagination** (for PDFs/Office docs).
    - If physical pages are not detected, it falls back to character-range pagination.
    """
    role_name = getattr(current_user.role, "name", "user") if hasattr(current_user, "role") else "user"
    is_admin = role_name in ["tenant_admin", "enterprise_tenant", "superadmin"]
    
    doc = await service.get_document(conn, document_id, tenant.tenant_id, current_user.user_id, is_admin)
    if not doc:
        raise HTTPException(status_code=404, detail="Not authorized or not found")

    versions = await service.get_versions(conn, document_id)
    if not versions:
        raise HTTPException(status_code=404, detail="No content")

    latest_version = versions[0]
    full_text = latest_version.get("content") or ""
    rich_data = latest_version.get("content_json")
    html_data = latest_version.get("content_html")
    
    total_chars = len(full_text)
    paged_text = ""
    paged_html = None
    paged_rich_content = None
    total_pages = 1

    # Attempt physical page-based pagination if rich_data or html_data exists
    if rich_data or html_data:
        try:
            if isinstance(rich_data, str):
                rich_data = json.loads(rich_data)
            if isinstance(html_data, str):
                html_data = json.loads(html_data)
            
            # Determine total pages from HTML data if available
            if isinstance(html_data, dict):
                total_pages = max([int(k) for k in html_data.keys()] + [1])
            elif isinstance(rich_data, dict):
                pages_info = rich_data.get("pages", [])
                if pages_info:
                    total_pages = len(pages_info)
                else:
                    all_els = rich_data.get("texts", []) + rich_data.get("tables", [])
                    total_pages = max([el.get("page_no", 1) for el in all_els] + [1])

            # Bound requested page
            page = max(1, min(page, total_pages))
            
            # Extract HTML for this page
            if isinstance(html_data, dict):
                # Try string key first, then int
                paged_html = html_data.get(str(page)) or html_data.get(page)

            # Extract text for this page from JSON elements if rich_data is available
            if isinstance(rich_data, dict):
                page_texts = [
                    el.get("text", "") for el in rich_data.get("texts", [])
                    if el.get("page_no") == page or (el.get("prov") and el["prov"][0].get("page_no") == page)
                ]
                paged_text = "\n\n".join(page_texts)

                # Extract rich content (tables, etc.) for this page
                paged_rich_content = rich_data.get(str(page)) or rich_data.get(page)
                if not paged_rich_content:
                    paged_rich_content = {
                        "page_no": page,
                        "elements": [
                            el for el in rich_data.get("texts", [])
                            if el.get("page_no") == page or (el.get("prov") and el["prov"][0].get("page_no") == page)
                        ],
                        "tables": [
                            t for t in rich_data.get("tables", [])
                            if t.get("page_no") == page or (t.get("prov") and t["prov"][0].get("page_no") == page)
                        ]
                    }
        except Exception as e:
            print(f"DEBUG: Page-based extraction failed, falling back to char-based: {e}")

    # Fallback to character-based pagination
    if not paged_text:
        total_pages = (total_chars + page_size - 1) // page_size if total_chars > 0 else 1
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        paged_text = full_text[start : start + page_size]
        paged_rich_content = rich_data 

    return {
        "document_id": str(document_id),
        "version_number": latest_version["version_number"],
        "content": paged_text,
        "content_html": paged_html,
        "rich_content": paged_rich_content,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "total_characters": total_chars,
        "created_on": latest_version["created_on"],
    }

@router.patch("/{document_id}/content", response_model=DocumentContentResponse)
async def update_document_content(
    document_id: uuid.UUID,
    content_update: DocumentContentUpdate,
    current_user: Any = Depends(get_current_user),
    tenant: Any = Depends(get_current_tenant),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: DocumentDBService = Depends(get_document_service)
):
    """
    **Update Document Content**

    Creates a new version of the document with the updated content. 
    Maintains a full audit trail of changes.
    """
    role_name = getattr(current_user.role, "name", "user") if hasattr(current_user, "role") else "user"
    is_admin = role_name in ["tenant_admin", "enterprise_tenant", "superadmin"]
    
    document = await service.get_document(conn, document_id, tenant.tenant_id, current_user.user_id, is_admin)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found or access denied")

    versions = await service.get_versions(conn, document_id)
    next_version_num = (versions[0]["version_number"] + 1) if versions else 1
    
    await service.save_document_version(
        conn, document_id, next_version_num, content_update.content, None, current_user.user_id
    )
    
    # Record Audit Log
    await AuditLogDBService.record_audit_log(
        conn, tenant.tenant_id, current_user.user_id,
        "document_content_update", "document", str(document_id),
        {"version_number": next_version_num}
    )

    # Return the newly created version
    new_versions = await service.get_versions(conn, document_id)
    return new_versions[0]

@router.post("/{document_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: Any = Depends(get_current_user),
    tenant: Any = Depends(get_current_tenant),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: DocumentDBService = Depends(get_document_service)
):
    """
    **Trigger Document Reprocessing**

    Manually triggers the AI background pipeline for an existing document. 
    Useful if extraction failed or if you want to apply updated AI models.
    """
    document = await service.get_document(conn, document_id, tenant.tenant_id, current_user.user_id, True)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    await service.update_document_statuses(
        conn, document_id, "processing", "Reprocessing triggered.", current_user.user_id
    )
    
    # Record Audit Log
    await AuditLogDBService.record_audit_log(
        conn, tenant.tenant_id, current_user.user_id,
        "document_reprocess_triggered", "document", str(document_id)
    )
        
    local_filename = document["file_url"].split("/")[-1]
    local_path = os.path.join(UPLOAD_DIR, local_filename)
    ext = os.path.splitext(document["filename"])[1].lower()
    background_tasks.add_task(process_document_background, document_id, tenant.tenant_id, current_user.user_id, local_path, ext)
    return {"status": "processing"}

@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: Any = Depends(get_current_user),
    tenant: Any = Depends(get_current_tenant),
    conn: psycopg.AsyncConnection = Depends(get_raw_db),
    service: DocumentDBService = Depends(get_document_service)
):
    """
    **Delete Document**

    Soft-deletes a document and its associated data.
    """
    role_name = getattr(current_user.role, "name", "user") if hasattr(current_user, "role") else "user"
    is_admin = role_name in ["tenant_admin", "enterprise_tenant", "superadmin"]
    
    success = await service.delete_document(conn, document_id, tenant.tenant_id, current_user.user_id, is_admin)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found or access denied")
    
    # Record Audit Log
    await AuditLogDBService.record_audit_log(
        conn, tenant.tenant_id, current_user.user_id,
        "document_deleted", "document", str(document_id)
    )

    return None

async def process_google_import_background(
    gdoc_id: str, 
    filename: str, 
    modified_time: datetime,
    tenant_id: uuid.UUID, 
    user_id: uuid.UUID, 
    access_token: str
):
    """
    Background task to download and process a Google Drive file during sync.
    """
    service = DocumentDBService()
    export_url = f"https://www.googleapis.com/drive/v3/files/{gdoc_id}/export?mimeType=application/pdf"
    
    # Handle PDF directly if it's already a PDF in Drive
    # Note: Drive API 'export' is for Google Docs. For binary files like PDFs, use 'get' with ?alt=media.
    # We'll check the extension or assume Google Doc for now, or refine later.
    
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    doc_id = uuid.uuid4()
    local_path = os.path.join(UPLOAD_DIR, f"{doc_id}.pdf")
    
    try:
        bg_log(f"SYNC: Downloading {filename} from Google Drive")
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                export_url, 
                headers={"Authorization": f"Bearer {access_token}"}, 
                timeout=60.0
            )
            
            # If export fails, it might be a native PDF, try alt=media
            if response.status_code != 200:
                media_url = f"https://www.googleapis.com/drive/v3/files/{gdoc_id}?alt=media"
                response = await client.get(
                    media_url, 
                    headers={"Authorization": f"Bearer {access_token}"}, 
                    timeout=60.0
                )

            if response.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(response.content)
                
                s3_url = await upload_to_s3(local_path, f"tenant-{tenant_id}/documents/{doc_id}.pdf")
                
                # Check if document already exists to update instead of creating duplicate
                async with get_connection() as conn:
                    existing = await service.get_document_by_google_id(conn, gdoc_id, tenant_id)
                    
                    if existing:
                        doc_id = existing["document_id"]
                        bg_log(f"SYNC: Updating existing document {doc_id}")
                        # Task: Use the service method to update status and record history
                        await service.update_document_statuses(
                            conn, doc_id, "processing", f"Sync update triggered (modified at {modified_time})", user_id
                        )
                        # Still update the specific Google field
                        await service.execute(
                            conn, 
                            "UPDATE documents SET google_last_modified = %s, updated_on = NOW() WHERE document_id = %s",
                            (modified_time, doc_id)
                        )
                    else:
                        bg_log(f"SYNC: Creating new document {doc_id}")
                        doc = await service.create_document(
                            conn, doc_id, tenant_id, user_id, filename, s3_url, os.path.getsize(local_path)
                        )
                        # Add Google metadata
                        await service.execute(
                            conn,
                            "UPDATE documents SET google_file_id = %s, google_last_modified = %s WHERE document_id = %s",
                            (gdoc_id, modified_time, doc_id)
                        )

                # Trigger processing
                await process_document_background(doc_id, tenant_id, user_id, local_path, ".pdf")
            else:
                bg_log(f"SYNC ERROR: Failed to download {filename}: {response.text}")
                
    except Exception as e:
        bg_log(f"SYNC ERROR: {filename} failed: {e}")
        if os.path.exists(local_path):
            os.remove(local_path)


async def retry_failed_documents():
    """
    Background job to retry documents stuck in processing or failed states.
    Runs every 5 minutes.
    """
    service = DocumentDBService()
    while True:
        try:
            async with get_connection() as conn:
                failed_docs = await service.list_failed_documents(conn)
                for doc in failed_docs:
                    doc_id = doc["document_id"]
                    bg_log(f"RETRY: Retrying document {doc_id}")
                    ext = os.path.splitext(doc["filename"])[1].lower()
                    local_filename = doc["file_url"].split("/")[-1]
                    local_path = os.path.join(UPLOAD_DIR, local_filename)
                    
                    asyncio.create_task(
                        process_document_background(doc_id, doc["tenant_id"], doc["user_id"], local_path, ext)
                    )
        except PoolClosed:
            bg_log("INFO: DB Pool closed, stopping retry_failed_documents loop.")
            break
        except asyncio.CancelledError:
            bg_log("INFO: retry_failed_documents task cancelled.")
            break
        except Exception as e:
            bg_log(f"ERROR: retry_failed_documents error: {e}")
            
        await asyncio.sleep(60 * 5)
