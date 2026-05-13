import asyncio
import sys
import os
import selectors

# Add root directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection, DBWrapper

async def get_roles():
    async with get_connection() as conn:
        rows = await DBWrapper.fetch_all(conn, "SELECT name FROM roles")
        print([r['name'] for r in rows])

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(get_roles())