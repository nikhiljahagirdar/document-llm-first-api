import asyncio
import sys
import os

# Add backend root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.db_raw import get_pool, close_pool
from app.services.retry_service import RetryService

async def main():
    await get_pool()
    try:
        await RetryService.process_failed_documents()
    finally:
        await close_pool()

if __name__ == "__main__":
    if sys.platform == 'win32':
        import selectors
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())