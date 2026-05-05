import asyncio
import psycopg
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

async def get_sample():
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT document_id, tenant_id FROM documents LIMIT 1")
            row = await cur.fetchone()
            if row:
                print(f"DOC_ID={row[0]}")
                print(f"TENANT_ID={row[1]}")
            else:
                print("No documents found")

if __name__ == "__main__":
    import selectors
    try:
        asyncio.run(get_sample(), loop_factory=asyncio.SelectorEventLoop)
    except TypeError:
        # Fallback for older python
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        asyncio.set_event_loop(loop)
        loop.run_until_complete(get_sample())
