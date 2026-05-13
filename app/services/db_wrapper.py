import os
import asyncpg
from app.db_raw import get_connection, DBWrapper

class CronDBWrapper:
    @staticmethod
    async def fetch_all(query, params=None):
        async with get_connection() as conn:
            return await DBWrapper.fetch_all(conn, query, params)

    @staticmethod
    async def execute(query, params=None):
        async with get_connection() as conn:
            await DBWrapper.execute(conn, query, params)
