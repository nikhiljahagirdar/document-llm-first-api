import asyncio
import os
import sys
import selectors
from dotenv import load_dotenv

# Add root directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection, DBWrapper

async def reset_usage():
    load_dotenv()
    try:
        async with get_connection() as conn:
            tenant_id = '04c2ffd1-a2dc-4b89-a1ad-4c48849122aa'
            
            await DBWrapper.execute(conn, "DELETE FROM usage_logs WHERE tenant_id = %s::uuid", (tenant_id,))
            
            # Also ensure we have a valid subscription with high limits
            await DBWrapper.execute(conn, """
                UPDATE subscriptions 
                SET status = 'active', 
                    current_period_end = '2030-01-01'
                WHERE tenant_id = %s::uuid
            """, (tenant_id,))
            
            print(f"Usage reset and subscription extended for {tenant_id}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(reset_usage())