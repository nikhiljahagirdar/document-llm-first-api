import os
from dotenv import load_dotenv
import psycopg

load_dotenv(override=True)
url = os.getenv("DATABASE_URL")

try:
    print(f"Connecting to: {url[:50]}...")
    conn = psycopg.connect(url)
    with open('document_mgmt.sql', 'r', encoding='utf-8') as f:
        sql = f.read()
    
    print("Applying schema...")
    # psycopg.connect does not support execute() directly on connection in all versions/modes
    # but it works in some. To be safe, use cursor.
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print("SUCCESS: Schema applied!")
    conn.close()
except Exception as e:
    print(f"FAILED: {e}")
