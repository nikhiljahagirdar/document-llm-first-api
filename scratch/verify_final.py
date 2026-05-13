import asyncio
import os
import sys
sys.path.append(os.path.abspath("."))
from app.db_raw import get_connection, DBWrapper

async def check():
    async with get_connection() as conn:
        r = await DBWrapper.fetch_one(conn, "SELECT status, updated_on FROM documents WHERE document_id = 'f13333dc-a260-4827-901a-893879aa5fbe'::uuid")
        print(f"Document Result: {r}")

asyncio.run(check())
