import asyncio
import json
import os
import sys
import selectors
from dotenv import load_dotenv

# Add root directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db_raw import get_connection, DBWrapper

async def update_limits():
    load_dotenv()
    try:
        async with get_connection() as conn:
            new_limits = {
                "reports": 1000000, 
                "documents": 1000000, 
                "storage_mb": 10240,
                "ai_limit": 1000000,
                "ocr_pages": 100000,
                "doc_limit": 1000000,
                "storage_limit_mb": 10240,
                "total_tokens": 1000000
            }
            
            # 1. Update subscription_plans
            rows = await DBWrapper.fetch_all(conn, "SELECT plan_id, limits FROM subscription_plans")
            for row in rows:
                plan_id = row['plan_id']
                limits = row['limits']
                if isinstance(limits, str):
                    try:
                        limits = json.loads(limits)
                    except:
                        limits = {}
                if not limits:
                    limits = {}
                limits.update(new_limits)
                await DBWrapper.execute(conn, "UPDATE subscription_plans SET limits = %s WHERE plan_id = %s::uuid", (json.dumps(limits), plan_id))
                
            # 2. Update subscriptions
            sub_rows = await DBWrapper.fetch_all(conn, "SELECT subscription_id, limits FROM subscriptions")
            for sub_row in sub_rows:
                sub_id = sub_row['subscription_id']
                limits = sub_row['limits']
                if isinstance(limits, str):
                    try:
                        limits = json.loads(limits)
                    except:
                        limits = {}
                if not limits:
                    limits = {}
                limits.update(new_limits)
                await DBWrapper.execute(conn, "UPDATE subscriptions SET limits = %s WHERE subscription_id = %s::uuid", (json.dumps(limits), sub_id))

            print("Subscription and plan limits updated successfully.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(update_limits())