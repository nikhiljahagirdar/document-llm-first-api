import asyncio
import os
import sys
import selectors
from dotenv import load_dotenv

# Add root directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection, DBWrapper

async def get_columns():
    load_dotenv()
    async with get_connection() as conn:
        rows = await DBWrapper.fetch_all(conn, "SELECT column_name FROM information_schema.columns WHERE table_name='subscriptions'")
        print("Subscriptions columns:", [r['column_name'] for r in rows])
        
        rows = await DBWrapper.fetch_all(conn, "SELECT column_name FROM information_schema.columns WHERE table_name='subscription_plans'")
        print("Subscription_plans columns:", [r['column_name'] for r in rows])
        
if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(get_columns())