import asyncio
import sys
import os
import selectors

# Add root directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection, DBWrapper

async def check_stats():
    async with get_connection() as conn:
        # Documents with versions but NO chunks
        query1 = """
            SELECT d.document_id, d.filename, d.status
            FROM documents d
            JOIN document_versions v ON d.document_id = v.document_id
            LEFT JOIN document_chunks c ON d.document_id = c.document_id
            WHERE c.chunk_id IS NULL AND d.is_active = TRUE
        """
        rows = await DBWrapper.fetch_all(conn, query1)
        print("Documents with Versions but NO Chunks:")
        for row in rows:
            print(f"ID: {row['document_id']}, Name: {row['filename']}, Status: {row['status']}")
        
        # Total chunks
        query2 = "SELECT COUNT(*) FROM document_chunks"
        count_row = await DBWrapper.fetch_one(conn, query2)
        print(f"\nTotal Chunks in DB: {count_row['count']}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(check_stats())