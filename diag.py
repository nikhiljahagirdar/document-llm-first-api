import sys
import os

# Add backend root to path, finding it relative to this script
backend_root = os.path.abspath(os.path.dirname(__file__))
sys.path.append(backend_root)
os.chdir(backend_root)

print(f"Running Diagnostic from: {os.getcwd()}")

# Load dotenv override as main.py does
from dotenv import load_dotenv
load_dotenv(override=True)

try:
    print("1. Importing DB Raw...")
    from app.db_raw import get_pool
    print("Success.")

    print("2. Importing Documents Router...")
    from app.routers import documents
    print("Success.")

    print("3. Importing Retry Loop...")
    from app.routers.documents import retry_failed_documents
    print("Success.")

    print("4. Attempting to import main application...")
    from main import app
    print("Main Application Imported Successfully!")
    
    print("5. Running validation checks completed. No obvious ImportErrors found.")

except Exception as e:
    import traceback
    print("\nFATAL DIAGNOSTIC ERROR DETECTED:")
    traceback.print_exc()
    sys.exit(1)
