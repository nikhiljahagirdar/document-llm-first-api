import asyncio
import sys
import os
import selectors

# Add root directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection, DBWrapper

async def check_subscriptions():
    async with get_connection() as conn:
        count_row = await DBWrapper.fetch_one(conn, "SELECT COUNT(*) FROM subscriptions")
        print(f"Total Subscriptions: {count_row['count']}")
        
        rows = await DBWrapper.fetch_all(conn, "SELECT t.name, s.status FROM subscriptions s JOIN tenants t ON s.tenant_id = t.tenant_id")
        for row in rows:
            print(f"Tenant: {row['name']}, Status: {row['status']}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(check_subscriptions())