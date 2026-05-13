import asyncio
import os
import sys
import uuid
import selectors
from datetime import datetime
from dotenv import load_dotenv

# Add root directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection, DBWrapper

async def simulate_max_usage():
    load_dotenv()
    try:
        async with get_connection() as conn:
            # 1. Clear any existing usage
            await DBWrapper.execute(conn, "DELETE FROM usage_logs")
            
            # 2. Get all tenants to apply the mock usage
            rows = await DBWrapper.fetch_all(conn, "SELECT tenant_id FROM tenants")
            
            now = datetime.now()
            
            for row in rows:
                tenant_id = row['tenant_id']
                log_id = uuid.uuid4()
                # 3. Insert exactly 1,000,000 usage
                await DBWrapper.execute(
                    conn,
                    """
                    INSERT INTO usage_logs (log_id, tenant_id, metric_name, quantity, created_on, updated_on)
                    VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s)
                    """,
                    (log_id, tenant_id, "AI Usage (Tokens)", 1000000, now, now)
                )
                
            print("Mocked 1,000,000 token usage successfully for all tenants.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(simulate_max_usage())