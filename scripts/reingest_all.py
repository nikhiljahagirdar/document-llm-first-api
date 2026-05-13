import asyncio
import sys
import os
import selectors
import uuid

# Add root directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection, DBWrapper
from app.services.rag_service import RAGService

async def reingest_all():
    async with get_connection() as conn:
        query = """
            SELECT d.document_id, d.tenant_id, v.content, d.filename
            FROM documents d
            JOIN document_versions v ON d.document_id = v.document_id
            WHERE d.is_active = TRUE AND d.status = 'completed'
        """
        rows = await DBWrapper.fetch_all(conn, query)
        print(f"Found {len(rows)} processed documents to re-ingest.")
        for row in rows:
            doc_id, tenant_id, content, filename = row['document_id'], row['tenant_id'], row['content'], row['filename']
            print(f"Ingesting {filename} ({doc_id})...")
            success = await RAGService.ingest_document(conn, doc_id, tenant_id, content)
            print(f"Result: {'Success' if success else 'Failed'}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(reingest_all())