import asyncio
import sys
import os
import selectors
import uuid

# Add root directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection

async def check_docx_content():
    doc_id = uuid.UUID("488cb386-3923-4164-a0a3-ad6f350475c4")
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT content FROM document_versions WHERE document_id = %s LIMIT 1", (doc_id,))
            row = await cur.fetchone()
            if row:
                print(f"DOCX Content Length: {len(row[0])}")
                print(f"DOCX Content Preview: {row[0][:200]}")
            else:
                print("No content found for this DOCX.")

if __name__ == "__main__":
    loop_factory = lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()) if sys.platform == 'win32' else None
    if loop_factory:
        asyncio.run(check_docx_content(), loop_factory=loop_factory)
    else:
        asyncio.run(check_docx_content())
