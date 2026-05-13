import os
import sys
import json
import logging
import uuid

# Add backend root to path to safely interact with extraction pipelines
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.services.db_wrapper import CronDBWrapper
from app.services.document_workflow_service import DocumentWorkflowService
from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] CronRetryService: %(message)s")
logger = logging.getLogger(__name__)

MAX_RETRIES = 5

class RetryService:
    @staticmethod
    async def process_failed_documents():
        logger.info("Checking for failed documents to retry...")
        
        # Using raw query to fetch eligible failed documents (up to 5 retries limit)
        query = """
            SELECT document_id, tenant_id, user_id, filename, file_url, metadata
            FROM documents 
            WHERE status = 'failed' 
              AND is_active = TRUE 
              AND updated_on < NOW() - INTERVAL '5 minutes'
              AND COALESCE((metadata->>'retry_count')::int, 0) < %s
        """
        failed_docs = await CronDBWrapper.fetch_all(query, (MAX_RETRIES,))
        
        if not failed_docs:
            logger.info("No eligible failed documents found.")
            return

        logger.info(f"Found {len(failed_docs)} failed documents to retry.")

        for doc in failed_docs:
            doc_id, tenant_id, user_id = doc["document_id"], doc["tenant_id"], doc["user_id"]
            filename, file_url, metadata = doc["filename"], doc["file_url"], doc["metadata"] or {}
            
            retry_count = metadata.get("retry_count", 0) + 1
            metadata["retry_count"] = retry_count
            
            # Lock the document immediately by changing status to processing & updating retry limit
            update_query = "UPDATE documents SET metadata = %s, status = 'processing', updated_on = NOW() WHERE document_id = %s::uuid"
            await CronDBWrapper.execute(update_query, (json.dumps(metadata), doc_id))
            
            logger.info(f"Retrying document {doc_id} (Attempt {retry_count}/{MAX_RETRIES})")
            
            ext = os.path.splitext(filename)[1].lower()
            local_path = os.path.join(settings.UPLOAD_DIR, file_url.split("/")[-1])
            
            try:
                await DocumentWorkflowService.process_document_background(doc_id, tenant_id, user_id, local_path, ext)
            except Exception as e:
                logger.error(f"Error during retry processing for {doc_id}: {e}")