import asyncio
import sys
import os
import selectors

# Add root directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection, DBWrapper

async def get_ids():
    async with get_connection() as conn:
        query = "SELECT document_id, tenant_id, filename FROM documents LIMIT 5"
        rows = await DBWrapper.fetch_all(conn, query)
        for row in rows:
            print(f"Doc ID: {row['document_id']}, Tenant ID: {row['tenant_id']}, Filename: {row['filename']}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(get_ids())
