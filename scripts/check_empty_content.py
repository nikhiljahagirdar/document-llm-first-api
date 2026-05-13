import asyncio
import sys
import os
import selectors

# Add root directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection, DBWrapper

async def check_empty_content():
    async with get_connection() as conn:
        query = """
            SELECT d.document_id, d.filename, 
                   LENGTH(v.content) as content_len, 
                   v.content_json IS NOT NULL as has_json
            FROM documents d
            JOIN document_versions v ON d.document_id = v.document_id
            WHERE (v.content IS NULL OR LENGTH(v.content) = 0)
              AND d.is_active = TRUE
        """
        rows = await DBWrapper.fetch_all(conn, query)
        print("Documents with EMPTY content but possibly having JSON:")
        for row in rows:
            print(f"ID: {row['document_id']}, Name: {row['filename']}, Content Len: {row['content_len']}, Has JSON: {row['has_json']}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(check_empty_content())