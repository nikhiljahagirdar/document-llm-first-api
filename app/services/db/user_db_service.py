import uuid
from datetime import datetime
from typing import Optional, List
import asyncpg
from .base_db_service import BaseDBService

class UserDBService(BaseDBService):
    async def get_user_by_email(self, conn: asyncpg.Connection, email: str) -> Optional[dict]:
        query = """
            SELECT u.*, r.name as role_name, r.permissions as role_permissions
            FROM users u 
            LEFT JOIN roles r ON u.role_id = r.role_id
            WHERE u.email = %s
        """
        return await self.fetch_one(conn, query, (email,))

    async def get_user_by_google_id_or_email(self, conn: asyncpg.Connection, google_id: str, email: str) -> Optional[dict]:
        query = """
            SELECT u.*, r.name as role_name 
            FROM users u 
            LEFT JOIN roles r ON u.role_id = r.role_id
            WHERE u.google_id = %s OR u.email = %s
        """
        return await self.fetch_one(conn, query, (google_id, email))

    async def get_user_by_id(self, conn: asyncpg.Connection, user_id: str) -> Optional[dict]:
        query = """
            SELECT u.*, r.name as role_name, r.permissions as role_permissions
            FROM users u 
            LEFT JOIN roles r ON u.role_id = r.role_id
            WHERE u.user_id::uuid = %s::uuid
        """
        return await self.fetch_one(conn, query, (user_id,))

    async def create_user(self, conn: asyncpg.Connection, user_data: dict) -> dict:
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

    async def update_user(self, conn: asyncpg.Connection, user_id: str, update_data: dict) -> dict:
        set_clause = ", ".join([f"{k} = %s" for k in update_data.keys()])
        query = f"UPDATE users SET {set_clause} WHERE user_id = %s::uuid RETURNING *"
        params = list(update_data.values()) + [user_id]
        return await self.execute_returning(conn, query, tuple(params))

    async def get_roles(self, conn: asyncpg.Connection) -> List[dict]:
        return await self.fetch_all(conn, "SELECT * FROM roles")

    async def get_role_by_name(self, conn: asyncpg.Connection, name: str) -> Optional[dict]:
        return await self.fetch_one(conn, "SELECT * FROM roles WHERE name = %s", (name,))

    async def get_role_by_id(self, conn: asyncpg.Connection, role_id: str) -> Optional[dict]:
        return await self.fetch_one(conn, "SELECT * FROM roles WHERE role_id::uuid = %s::uuid", (role_id,))

    async def list_tenant_users(self, conn: asyncpg.Connection, tenant_id: Optional[uuid.UUID] = None) -> List[dict]:
        query = """
            SELECT u.*, r.name as role_name, r.permissions as role_permissions
            FROM users u
            LEFT JOIN roles r ON u.role_id = r.role_id
        """
        params = []
        if tenant_id:
            query += " WHERE u.tenant_id::uuid = %s::uuid"
            params.append(tenant_id)
            
        query += " ORDER BY u.created_on DESC"
        return await self.fetch_all(conn, query, tuple(params) if params else None)
