import asyncio
import sys
import os
import selectors
import uuid

# Add root directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection, DBWrapper

async def check_docx_content():
    doc_id = uuid.UUID("488cb386-3923-4164-a0a3-ad6f350475c4")
    async with get_connection() as conn:
        query = "SELECT content FROM document_versions WHERE document_id = %s::uuid LIMIT 1"
        row = await DBWrapper.fetch_one(conn, query, (doc_id,))
        if row:
            content = row['content']
            print(f"DOCX Content Length: {len(content)}")
            print(f"DOCX Content Preview: {content[:200]}")
        else:
            print("No content found for this DOCX.")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(check_docx_content())