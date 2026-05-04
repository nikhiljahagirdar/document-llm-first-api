import asyncio
import sys
import os
import selectors
import uuid

# Add root directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection
from app.services.rag_service import RAGService

async def reingest_all():
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT d.document_id, d.tenant_id, v.content, d.filename
                FROM documents d
                JOIN document_versions v ON d.document_id = v.document_id
                WHERE d.is_active = TRUE AND d.status = 'processed'
            """)
            rows = await cur.fetchall()
            print(f"Found {len(rows)} processed documents to re-ingest.")
            for row in rows:
                doc_id, tenant_id, content, filename = row
                print(f"Ingesting {filename} ({doc_id})...")
                success = await RAGService.ingest_document(conn, doc_id, tenant_id, content)
                print(f"Result: {'Success' if success else 'Failed'}")

if __name__ == "__main__":
    loop_factory = lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()) if sys.platform == 'win32' else None
    if loop_factory:
        asyncio.run(reingest_all(), loop_factory=loop_factory)
    else:
        asyncio.run(reingest_all())
