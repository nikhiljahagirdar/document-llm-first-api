import os
import psycopg
from psycopg_pool import AsyncConnectionPool
from dotenv import load_dotenv
from app.config import settings
import logging
from contextlib import asynccontextmanager

load_dotenv()
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

# Global pool instance
_pool = None

async def get_pool():
    global _pool
    if _pool is None or _pool._closed:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("DATABASE_URL environment variable is not set")
        
        # Psycopg3 async on Windows REQUIRES SelectorEventLoop. 
        # Using open=False as recommended by documentation to avoid warnings/future errors.
        _pool = AsyncConnectionPool(
            conninfo=db_url, 
            open=False, 
            min_size=settings.DB_MIN_SIZE if hasattr(settings, "DB_MIN_SIZE") else 4,
            max_size=settings.DB_MAX_SIZE if hasattr(settings, "DB_MAX_SIZE") else 20,
            timeout=30.0,
            kwargs={"autocommit": True}
        )
        await _pool.open()
        global pool
        pool = _pool
        logger.info("AsyncConnectionPool initialized and opened.")
    return _pool

@asynccontextmanager
async def get_connection():
    """Reusable context manager to obtain a connection from the pool."""
    pool_instance = await get_pool()
    async with pool_instance.connection() as conn:
        yield conn

async def close_pool():
    """Gracefully close the database pool."""
    global _pool
    if _pool and not _pool._closed:
        await _pool.close()
        logger.info("AsyncConnectionPool closed.")

async def get_raw_db():
    """FastAPI dependency to get a raw database connection from the pool."""
    async with get_connection() as conn:
        yield conn

class DBWrapper:
    @staticmethod
    async def fetch_one(conn, query, params=None):
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            await cur.execute(query, params)
            return await cur.fetchone()

    @staticmethod
    async def fetch_all(conn, query, params=None):
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            await cur.execute(query, params)
            return await cur.fetchall()

    @staticmethod
    async def execute(conn, query, params=None):
        async with conn.cursor() as cur:
            await cur.execute(query, params)

    @staticmethod
    async def execute_returning(conn, query, params=None):
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            await cur.execute(query, params)
            return await cur.fetchone()

# For backward compatibility if any code uses 'pool' directly
# However, it's better to use get_pool()
pool = None # Will be populated by get_pool()
