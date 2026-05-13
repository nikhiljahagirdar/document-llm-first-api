import asyncio
import os
import sys
from dotenv import load_dotenv
import asyncpg

load_dotenv()

async def run_sql_file():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found in .env")
        return
    
    script_path = r"c:\selling-point\document\app\backend\document_mgmt.sql"
    if not os.path.exists(script_path):
        print(f"File not found: {script_path}")
        return
        
    with open(script_path, "r", encoding="utf-8") as f:
        sql_content = f.read()
        
    try:
        print(f"Connecting to database...")
        conn = await asyncpg.connect(db_url)
        print(f"Executing SQL content from {script_path}...")
        await conn.execute(sql_content)
        print("SQL Script executed successfully.")
        await conn.close()
    except Exception as e:
        print(f"Error executing SQL script: {e}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_sql_file())
