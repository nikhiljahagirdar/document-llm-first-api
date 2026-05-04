import asyncio
import sys
import os
import selectors
import uuid

# Add root directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection

async def check_version_content():
    # Use IDs found in the database
    doc_id = uuid.UUID("77c1667c-71ef-4181-8a86-0363befae5fa")
    
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT content, content_json FROM document_versions WHERE document_id = %s LIMIT 1", (doc_id,))
            row = await cur.fetchone()
            if row:
                content = row[0]
                content_json = row[1]
                print(f"Content Length: {len(content) if content else 0}")
                print(f"Content Preview: {content[:100] if content else 'N/A'}")
                print(f"JSON Preview: {str(content_json)[:100] if content_json else 'N/A'}")
            else:
                print("No version found for this document.")

if __name__ == "__main__":
    loop_factory = lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()) if sys.platform == 'win32' else None
    if loop_factory:
        asyncio.run(check_version_content(), loop_factory=loop_factory)
    else:
        asyncio.run(check_version_content())
