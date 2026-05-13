import asyncio
import os
import sys
import selectors
from dotenv import load_dotenv

# Add root directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection, DBWrapper

async def increase_tenant_limits():
    load_dotenv()
    try:
        async with get_connection() as conn:
            # We also need to wipe out the current month's token usage so the user can use it immediately!
            await DBWrapper.execute(conn, "DELETE FROM usage_logs")
            print("Tenant token usage reset successfully.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(increase_tenant_limits())