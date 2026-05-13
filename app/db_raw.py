import os
import asyncpg
import logging
import re
from typing import Any, List, Optional, Tuple, Dict
from contextlib import asynccontextmanager
from app.config import settings
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

# Global pool instance
_pool = None
pool = None

def convert_query(query: str, params: Any = None) -> Tuple[str, list]:
    """
    Converts %s and %(key)s placeholders to $1, $2, etc. for asyncpg.
    Returns (new_query, ordered_params).
    """
    if not query:
        return query, []
    
    new_query = ""
    ordered_params = []
    
    if isinstance(params, dict):
        # Handle %(key)s
        param_idx = 1
        i = 0
        while i < len(query):
            if query[i:i+2] == "%(":
                end = query.find(")s", i)
                if end != -1:
                    key = query[i+2:end]
                    new_query += f"${param_idx}"
                    ordered_params.append(params[key])
                    param_idx += 1
                    i = end + 2
                else:
                    new_query += query[i]
                    i += 1
            elif query[i:i+2] == "%%":
                new_query += "%"
                i += 2
            else:
                new_query += query[i]
                i += 1
        return new_query, ordered_params
    else:
        # Handle %s
        new_query = ""
        i = 0
        param_idx = 1
        while i < len(query):
            if query[i:i+2] == "%s":
                new_query += f"${param_idx}"
                param_idx += 1
                i += 2
            elif query[i:i+2] == "%%":
                new_query += "%"
                i += 2
            else:
                new_query += query[i]
                i += 1
        
        if params is None:
            return new_query, []
        if isinstance(params, (list, tuple)):
            return new_query, list(params)
        return new_query, [params]

async def get_pool():
    global _pool, pool
    if _pool is None:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("DATABASE_URL environment variable is not set")
        
        try:
            # The user requested ssl=true. In asyncpg we use ssl='require' 
            # or a boolean if we want to use default settings.
            _pool = await asyncpg.create_pool(
                dsn=db_url,
                min_size=getattr(settings, "DB_MIN_SIZE", 4),
                max_size=getattr(settings, "DB_MAX_SIZE", 20),
                command_timeout=60.0,
                ssl='require'
            )
            pool = _pool
            logger.info("asyncpg Connection Pool initialized with SSL.")
        except Exception as e:
            logger.error(f"Failed to initialize asyncpg pool: {e}")
            raise
    return _pool

@asynccontextmanager
async def get_connection():
    """Reusable context manager to obtain a connection from the pool."""
    pool_instance = await get_pool()
    async with pool_instance.acquire() as conn:
        yield conn

async def close_pool():
    """Gracefully close the database pool."""
    global _pool, pool
    if _pool:
        await _pool.close()
        _pool = None
        pool = None
        logger.info("asyncpg Connection Pool closed.")

async def get_raw_db():
    """FastAPI dependency to get a raw database connection from the pool."""
    async with get_connection() as conn:
        yield conn

class DBWrapper:
    @staticmethod
    async def fetch_one(conn, query: str, params: Any = None):
        q, p = convert_query(query, params)
        if p:
            row = await conn.fetchrow(q, *p)
        else:
            row = await conn.fetchrow(q)
        return dict(row) if row else None

    @staticmethod
    async def fetch_all(conn, query: str, params: Any = None):
        q, p = convert_query(query, params)
        if p:
            rows = await conn.fetch(q, *p)
        else:
            rows = await conn.fetch(q)
        return [dict(r) for r in rows]

    @staticmethod
    async def execute(conn, query: str, params: Any = None):
        q, p = convert_query(query, params)
        if p:
            await conn.execute(q, *p)
        else:
            await conn.execute(q)

    @staticmethod
    async def executemany(conn, query: str, params_list: List[Any]):
        if not params_list:
            return
        
        first_params = params_list[0]
        q, _ = convert_query(query, first_params)
        
        if isinstance(first_params, dict):
            # Extract named keys in the order they appear in the query
            keys = []
            i = 0
            while i < len(query):
                if query[i:i+2] == "%(":
                    end = query.find(")s", i)
                    if end != -1:
                        keys.append(query[i+2:end])
                        i = end + 2
                    else:
                        i += 1
                else:
                    i += 1
            
            # Convert list of dicts to list of tuples for asyncpg
            sequences = [tuple(d.get(k) for k in keys) for d in params_list]
            await conn.executemany(q, sequences)
        else:
            await conn.executemany(q, params_list)

    @staticmethod
    async def execute_returning(conn, query: str, params: Any = None):
        return await DBWrapper.fetch_one(conn, query, params)
