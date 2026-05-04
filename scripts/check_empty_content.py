import asyncio
import sys
import os
import selectors

# Add root directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection

async def check_empty_content():
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT d.document_id, d.filename, 
                       LENGTH(v.content) as content_len, 
                       v.content_json IS NOT NULL as has_json
                FROM documents d
                JOIN document_versions v ON d.document_id = v.document_id
                WHERE (v.content IS NULL OR LENGTH(v.content) = 0)
                  AND d.is_active = TRUE
            """)
            rows = await cur.fetchall()
            print("Documents with EMPTY content but possibly having JSON:")
            for row in rows:
                print(f"ID: {row[0]}, Name: {row[1]}, Content Len: {row[2]}, Has JSON: {row[3]}")

if __name__ == "__main__":
    loop_factory = lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()) if sys.platform == 'win32' else None
    if loop_factory:
        asyncio.run(check_empty_content(), loop_factory=loop_factory)
    else:
        asyncio.run(check_empty_content())
