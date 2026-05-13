import sys
import os
import asyncio
import uuid

# Add workspace to sys.path to resolve app imports
sys.path.append(os.path.abspath("."))

from app.services.document_workflow_service import DocumentWorkflowService
from app.services.db.document_db_service import DocumentDBService
from app.db_raw import get_connection

async def repro():
    doc_id_str = "f13333dc-a260-4827-901a-893879aa5fbe"
    doc_id = uuid.UUID(doc_id_str)
    
    print(f"Fetching metadata for {doc_id}...")
    async with get_connection() as conn:
        from app.db_raw import DBWrapper
        res = await DBWrapper.fetch_one(conn, "SELECT * FROM documents WHERE document_id = %s::uuid", (doc_id,))
        if not res:
            print("Document not found in documents table.")
            return
        doc = res
        
        tenant_id = doc["tenant_id"]
        user_id = doc["user_id"]
        filename = doc["filename"]
        ext = os.path.splitext(filename)[1].lower()
        
        print(f"Found: {filename}, Tenant: {tenant_id}")
        
        # We'll pass a nonexistent file path to force it to redownload from S3
        dummy_path = f"nonexistent_temp_file{ext}"
        
        print("Invoking background processor...")
        try:
            await DocumentWorkflowService.process_document_background(
                doc_id, tenant_id, user_id, dummy_path, ext
            )
            print("Done.")
        except Exception as e:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(repro())
