import os
from dotenv import load_dotenv
import psycopg

# Load .env explicitly from current dir
load_dotenv(override=True)
url = os.getenv("DATABASE_URL")
print(f"URL: {url}")

try:
    conn = psycopg.connect(url)
    print("SUCCESS: Connected!")
    conn.close()
except Exception as e:
    print(f"FAILED: {e}")
