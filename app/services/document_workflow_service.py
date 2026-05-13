import os
import shutil
import json
import asyncio
import httpx
import uuid
from datetime import datetime

import asyncpg
from app.db_raw import get_connection
from app.services.storage_service import get_file_from_s3, get_s3_key_from_url, upload_to_s3
from app.services.document_processing import process_document, generate_page_previews
from app.services.embedding_service import get_text_embedding
from app.services.rag_service import RAGService
from app.services.llm_service import LLMService
from app.services.db.document_db_service import DocumentDBService
from app.services.db.industry_db_service import IndustryDBService
from app.services.db.audit_log_db_service import AuditLogDBService
from app.services.db.metering_db_service import MeteringDBService
from app.config import settings

UPLOAD_DIR = settings.UPLOAD_DIR
processing_semaphore = asyncio.Semaphore(1)

def bg_log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("bg_worker.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {msg}\n")

class DocumentWorkflowService:
    @staticmethod
    async def process_document_background(
        document_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID, original_file_path: str, file_extension: str
    ):
        service = DocumentDBService()
        ind_service = IndustryDBService()
        metering = MeteringDBService()
        
        temp_dir = os.path.join(UPLOAD_DIR, f"temp-{tenant_id}-{document_id}")
        os.makedirs(temp_dir, exist_ok=True)
        
        local_file_path = os.path.join(temp_dir, os.path.basename(original_file_path))
        if os.path.exists(original_file_path):
            shutil.copy2(original_file_path, local_file_path)
        
        async with processing_semaphore:
            bg_log(f"DEBUG: Starting background processing for document {document_id}")
            try:
                async with get_connection() as conn:
                    is_valid = await metering.check_usage_limits(conn, tenant_id, "ocr")
                    if is_valid is False:
                        await service.update_document_statuses(conn, document_id, "failed", "OCR limit exceeded. Please upgrade your plan.", user_id)
                        return
                    
                    document = await service.get_document(conn, document_id, tenant_id, is_admin=True)
                    if not document:
                        bg_log(f"ERROR: Document {document_id} not found in DB for tenant {tenant_id}")
                        return

                    if not os.path.exists(local_file_path):
                        bg_log(f"INFO: Local file missing at {local_file_path}, attempting download from S3")
                        s3_key = get_s3_key_from_url(document["file_url"])
                        file_bytes = await get_file_from_s3(s3_key)
                        if file_bytes:
                            with open(local_file_path, "wb") as f:
                                f.write(file_bytes)
                        else:
                            raise FileNotFoundError(f"Could not find local file or S3 object for document {document_id}")

                    await service.update_document_statuses(conn, document_id, "processing", f"Extracting text from {document['filename']}...", user_id)

                bg_log(f"DEBUG: Calling process_document for {document_id}")
                
                preview_task = asyncio.create_task(generate_page_previews(local_file_path, tenant_id, document_id))
                
                processing_result = await process_document(local_file_path, file_extension, tenant_id=tenant_id, document_id=document_id)
                extracted_text = processing_result.get("text", "")
                rich_content = processing_result.get("rich_content") or {}
                
                thumbnail_url = await preview_task
                doc_metadata = processing_result.get("metadata") or {}
                if thumbnail_url:
                    doc_metadata["thumbnail_url"] = thumbnail_url
                    processing_result["metadata"] = doc_metadata
                
                bg_log(f"DEBUG: Extraction complete for {document_id}. Source: {processing_result.get('source')}")

                if not extracted_text:
                    async with get_connection() as conn:
                        await service.update_document_statuses(conn, document_id, "failed", "No text could be extracted", user_id)
                    return
                
                async with get_connection() as conn:
                    page_count = processing_result.get("page_count", 1)
                    await service.update_document_metadata(
                        conn, document_id, processing_result.get("file_type", file_extension.lstrip('.')), 
                        page_count, processing_result.get("metadata", {})
                    )
                    await LLMService.log_llm_usage(conn, tenant_id, "OCR Usage (Pages)", page_count, user_id=user_id)
                    await service.save_ocr_result(conn, document_id, extracted_text, processing_result.get("source"))

                async with get_connection() as conn:
                    await service.update_document_statuses(conn, document_id, "processing", f"Categorizing {document['filename']}...", user_id)

                    industries = await ind_service.list_industries(conn)
                    detection = await LLMService.detect_industry(extracted_text, industries, tenant_id, conn, user_id=user_id)

                    if detection and "error" not in detection:
                        await service.update_document_classification(
                            conn, document_id, detection.get("industry_id"), detection.get("category_id"), detection.get("subcategory_id")
                        )

                    global_embedding = await get_text_embedding(processing_result.get("plain_text") or extracted_text)

                    # Get next version number
                    versions = await service.get_versions(conn, document_id)
                    next_version = (versions[0]["version_number"] + 1) if versions else 1

                    await service.save_document_version(
                        conn, document_id, next_version, processing_result.get("plain_text") or extracted_text, 
                        json.dumps(rich_content), user_id, json.dumps(processing_result.get("html")),
                        embedding=global_embedding
                    )

                async with get_connection() as conn:
                    await service.update_document_statuses(conn, document_id, "completed", "Success", user_id)
                    await RAGService.ingest_document(None, document_id, tenant_id, extracted_text, file_path=local_file_path)
                    
                    await AuditLogDBService.record_audit_log(
                        conn, tenant_id, user_id, "document_processed", "document", str(document_id),
                        {"filename": document['filename'], "status": "success"}
                    )

            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                bg_log(f"ERROR: {document_id} failed: {e}\nTraceback:\n{tb}")
                try:
                    async with get_connection() as conn:
                        await service.update_document_statuses(conn, document_id, "failed", str(e), user_id)
                        await AuditLogDBService.record_audit_log(
                            conn, tenant_id, user_id, "document_processing_failed", "document", str(document_id), {"error": str(e)}
                        )
                except: pass
            finally:
                if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
                if os.path.exists(original_file_path): os.remove(original_file_path)

    @staticmethod
    async def process_google_import_background(gdoc_id: str, filename: str, modified_time: datetime, tenant_id: uuid.UUID, user_id: uuid.UUID, access_token: str):
        service = DocumentDBService()
        export_url = f"https://www.googleapis.com/drive/v3/files/{gdoc_id}/export?mimeType=application/pdf"
        
        if not filename.lower().endswith(".pdf"): filename += ".pdf"
        doc_id = uuid.uuid4()
        local_path = os.path.join(UPLOAD_DIR, f"{doc_id}.pdf")
        
        try:
            bg_log(f"SYNC: Downloading {filename} from Google Drive")
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(export_url, headers={"Authorization": f"Bearer {access_token}"}, timeout=60.0)
                if response.status_code != 200:
                    response = await client.get(f"https://www.googleapis.com/drive/v3/files/{gdoc_id}?alt=media", headers={"Authorization": f"Bearer {access_token}"}, timeout=60.0)

                if response.status_code == 200:
                    with open(local_path, "wb") as f: f.write(response.content)
                    s3_url = await upload_to_s3(local_path, f"tenant-{tenant_id}/documents/{doc_id}.pdf")
                    
                    async with get_connection() as conn:
                        existing = await service.get_document_by_google_id(conn, gdoc_id, tenant_id)
                        if existing:
                            doc_id = existing["document_id"]
                            bg_log(f"SYNC: Updating existing document {doc_id}")
                            await service.update_document_statuses(conn, doc_id, "processing", f"Sync update triggered (modified at {modified_time})", user_id)
                            await service.update_google_sync(conn, doc_id, gdoc_id, modified_time, is_new=False)
                        else:
                            bg_log(f"SYNC: Creating new document {doc_id}")
                            await service.create_document(conn, doc_id, tenant_id, user_id, filename, s3_url, os.path.getsize(local_path))
                            await service.update_google_sync(conn, doc_id, gdoc_id, modified_time, is_new=True)

                    await DocumentWorkflowService.process_document_background(doc_id, tenant_id, user_id, local_path, ".pdf")
        except Exception as e:
            bg_log(f"SYNC ERROR: {filename} failed: {e}")
            if os.path.exists(local_path): os.remove(local_path)