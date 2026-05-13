import asyncio
import json
import os
import sys
import selectors
from dotenv import load_dotenv

# Add root directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection, DBWrapper

async def increase_limits():
    load_dotenv()
    try:
        async with get_connection() as conn:
            # Update all plans with much higher limits
            new_limits = {
                "ai_limit": 1000000,
                "ocr_pages": 10000,
                "storage_limit_mb": 10240,
                "total_tokens": 1000000
            }
            
            rows = await DBWrapper.fetch_all(conn, "SELECT plan_id, limits FROM subscription_plans")
            
            for row in rows:
                plan_id = row['plan_id']
                limits = row['limits']
                if isinstance(limits, str):
                    limits = json.loads(limits)
                
                limits.update(new_limits)
                await DBWrapper.execute(
                    conn,
                    "UPDATE subscription_plans SET limits = %s WHERE plan_id = %s::uuid",
                    (json.dumps(limits), plan_id)
                )
                
            print("Limits increased successfully")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(increase_limits())