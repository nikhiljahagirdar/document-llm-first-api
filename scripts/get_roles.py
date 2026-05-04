import asyncio
import sys
import os
import selectors

# Add root directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection

async def get_roles():
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT name FROM roles")
            rows = await cur.fetchall()
            print([r[0] for r in rows])

if __name__ == "__main__":
    loop_factory = lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()) if sys.platform == 'win32' else None
    if loop_factory:
        asyncio.run(get_roles(), loop_factory=loop_factory)
    else:
        asyncio.run(get_roles())
