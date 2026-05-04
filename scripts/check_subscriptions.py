import asyncio
import sys
import os
import selectors

# Add root directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection

async def check_subscriptions():
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM subscriptions")
            count = await cur.fetchone()
            print(f"Total Subscriptions: {count[0]}")
            
            await cur.execute("SELECT t.name, s.status FROM subscriptions s JOIN tenants t ON s.tenant_id = t.tenant_id")
            rows = await cur.fetchall()
            for row in rows:
                print(f"Tenant: {row[0]}, Status: {row[1]}")

if __name__ == "__main__":
    loop_factory = lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()) if sys.platform == 'win32' else None
    if loop_factory:
        asyncio.run(check_subscriptions(), loop_factory=loop_factory)
    else:
        asyncio.run(check_subscriptions())
