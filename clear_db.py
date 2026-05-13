import asyncio
import os
import sys
from dotenv import load_dotenv
import asyncpg

load_dotenv()

async def clear_database():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found in .env")
        return
    
    try:
        conn = await asyncpg.connect(db_url)
        
        # Get all tables in the public schema
        rows = await conn.fetch("""
            SELECT tablename 
            FROM pg_catalog.pg_tables 
            WHERE schemaname = 'public'
        """)
        tables = [row['tablename'] for row in rows]
        
        if not tables:
            print("No tables found in the database.")
            await conn.close()
            return

        # Disable triggers and truncate all tables with CASCADE
        # Note: Truncating in a single command is more efficient and handles dependencies better
        table_list = ", ".join([f'"{t}"' for t in tables])
        print(f"Truncating tables: {table_list}")
        
        await conn.execute(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE;")
        
        print("Database cleared successfully.")
        await conn.close()
        
    except Exception as e:
        print(f"Error clearing database: {e}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        import selectors
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(clear_database())
