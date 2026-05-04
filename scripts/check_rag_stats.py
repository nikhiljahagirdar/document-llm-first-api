import asyncio
import sys
import os
import selectors

# Add root directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection

async def check_stats():
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            # Documents with versions but NO chunks
            await cur.execute("""
                SELECT d.document_id, d.filename, d.status
                FROM documents d
                JOIN document_versions v ON d.document_id = v.document_id
                LEFT JOIN document_chunks c ON d.document_id = c.document_id
                WHERE c.chunk_id IS NULL AND d.is_active = TRUE
            """)
            rows = await cur.fetchall()
            print("Documents with Versions but NO Chunks:")
            for row in rows:
                print(f"ID: {row[0]}, Name: {row[1]}, Status: {row[2]}")
            
            # Total chunks
            await cur.execute("SELECT COUNT(*) FROM document_chunks")
            count = await cur.fetchone()
            print(f"\nTotal Chunks in DB: {count[0]}")

if __name__ == "__main__":
    loop_factory = lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()) if sys.platform == 'win32' else None
    if loop_factory:
        asyncio.run(check_stats(), loop_factory=loop_factory)
    else:
        asyncio.run(check_stats())
