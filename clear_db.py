import psycopg
import os
from dotenv import load_dotenv

load_dotenv()

def clear_database():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found in .env")
        return
    
    try:
        conn = psycopg.connect(db_url)
        cur = conn.cursor()
        
        # Get all tables in the public schema
        cur.execute("""
            SELECT tablename 
            FROM pg_catalog.pg_tables 
            WHERE schemaname = 'public'
        """)
        tables = cur.fetchall()
        
        if not tables:
            print("No tables found in the database.")
            return

        # Disable triggers and truncate all tables with CASCADE
        # Note: Truncating in a single command is more efficient and handles dependencies better
        table_list = ", ".join([f'"{t[0]}"' for t in tables])
        print(f"Truncating tables: {table_list}")
        
        cur.execute(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE;")
        
        conn.commit()
        print("Database cleared successfully.")
        
    except Exception as e:
        print(f"Error clearing database: {e}")
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    clear_database()
