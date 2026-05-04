import psycopg
from psycopg.rows import dict_row
from typing import Any, List, Optional
from contextlib import asynccontextmanager
from app.db_raw import get_connection, DBWrapper

class BaseDBService:
    def __init__(self, conn: Optional[psycopg.AsyncConnection] = None):
        self.conn = conn

    def get_connection(self):
        if self.conn:
            @asynccontextmanager
            async def _existing_conn():
                yield self.conn
            return _existing_conn()
        return get_connection()

    @staticmethod
    async def fetch_all(conn: psycopg.AsyncConnection, query: str, params: tuple | dict = None) -> List[dict]:
        return await DBWrapper.fetch_all(conn, query, params)

    @staticmethod
    async def fetch_one(conn: psycopg.AsyncConnection, query: str, params: tuple | dict = None) -> Optional[dict]:
        return await DBWrapper.fetch_one(conn, query, params)

    @staticmethod
    async def execute(conn: psycopg.AsyncConnection, query: str, params: tuple | dict = None):
        await DBWrapper.execute(conn, query, params)

    @staticmethod
    async def execute_returning(conn: psycopg.AsyncConnection, query: str, params: tuple | dict = None) -> Optional[dict]:
        return await DBWrapper.execute_returning(conn, query, params)
