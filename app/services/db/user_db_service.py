import uuid
from datetime import datetime
from typing import Optional, List
import psycopg
from .base_db_service import BaseDBService

class UserDBService(BaseDBService):
    async def get_user_by_email(self, conn: psycopg.AsyncConnection, email: str) -> Optional[dict]:
        query = """
            SELECT u.*, r.name as role_name, r.permissions as role_permissions
            FROM users u 
            LEFT JOIN roles r ON u.role_id = r.role_id
            WHERE u.email = %s
        """
        return await self.fetch_one(conn, query, (email,))

    async def get_user_by_google_id_or_email(self, conn: psycopg.AsyncConnection, google_id: str, email: str) -> Optional[dict]:
        query = """
            SELECT u.*, r.name as role_name 
            FROM users u 
            LEFT JOIN roles r ON u.role_id = r.role_id
            WHERE u.google_id = %s OR u.email = %s
        """
        return await self.fetch_one(conn, query, (google_id, email))

    async def get_user_by_id(self, conn: psycopg.AsyncConnection, user_id: str) -> Optional[dict]:
        query = """
            SELECT u.*, r.name as role_name, r.permissions as role_permissions
            FROM users u 
            LEFT JOIN roles r ON u.role_id = r.role_id
            WHERE u.user_id::uuid = %s::uuid
        """
        return await self.fetch_one(conn, query, (user_id,))

    async def create_user(self, conn: psycopg.AsyncConnection, user_data: dict) -> dict:
        fields = list(user_data.keys())
        # Cast uuid fields if necessary
        cast_fields = ["user_id", "tenant_id", "role_id"]
        
        placeholders = []
        for field in fields:
            if field in cast_fields:
                placeholders.append(f"%({field})s::uuid")
            else:
                placeholders.append(f"%({field})s")

        query = f"""
            INSERT INTO users ({', '.join(fields)})
            VALUES ({', '.join(placeholders)})
            RETURNING *
        """
        return await self.execute_returning(conn, query, user_data)

    async def update_user(self, conn: psycopg.AsyncConnection, user_id: str, update_data: dict) -> dict:
        set_clause = ", ".join([f"{k} = %s" for k in update_data.keys()])
        query = f"UPDATE users SET {set_clause} WHERE user_id = %s::uuid RETURNING *"
        params = list(update_data.values()) + [user_id]
        return await self.execute_returning(conn, query, tuple(params))

    async def get_roles(self, conn: psycopg.AsyncConnection) -> List[dict]:
        return await self.fetch_all(conn, "SELECT * FROM roles")

    async def get_role_by_name(self, conn: psycopg.AsyncConnection, name: str) -> Optional[dict]:
        return await self.fetch_one(conn, "SELECT * FROM roles WHERE name = %s", (name,))

    async def get_role_by_id(self, conn: psycopg.AsyncConnection, role_id: str) -> Optional[dict]:
        return await self.fetch_one(conn, "SELECT * FROM roles WHERE role_id::uuid = %s::uuid", (role_id,))

    async def list_tenant_users(self, conn: psycopg.AsyncConnection, tenant_id: uuid.UUID) -> List[dict]:
        query = "SELECT * FROM users WHERE tenant_id::uuid = %s::uuid"
        return await self.fetch_all(conn, query, (tenant_id,))
