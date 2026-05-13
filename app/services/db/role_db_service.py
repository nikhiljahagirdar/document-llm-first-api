import asyncpg
import json
from typing import List, Optional, Any
import uuid
from app.services.db.base_db_service import BaseDBService

class RoleDBService(BaseDBService):
    async def list_roles(self, conn: asyncpg.Connection, tenant_id: uuid.UUID, limit: int = 100, offset: int = 0, search: Optional[str] = None) -> List[dict]:
        """
        Retrieve all roles applicable to the current tenant.
        Includes both system-wide roles (tenant_id IS NULL) and tenant-specific custom roles.
        """
        query = """
            SELECT * FROM roles 
            WHERE (tenant_id IS NULL OR tenant_id = %s::uuid)
        """
        params = [tenant_id]
        
        if search:
            query += " AND name ILIKE %s"
            params.append(f"%{search}%")
            
        query += " ORDER BY created_on DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        return await self.fetch_all(conn, query, tuple(params))

    async def get_role(self, conn: asyncpg.Connection, role_id: uuid.UUID) -> Optional[dict]:
        query = "SELECT * FROM roles WHERE role_id = %s::uuid"
        return await self.fetch_one(conn, query, (role_id,))

    async def get_tenant_role(self, conn: asyncpg.Connection, role_id: uuid.UUID, tenant_id: uuid.UUID) -> Optional[dict]:
        stmt = "SELECT * FROM roles WHERE role_id = %s::uuid AND tenant_id = %s::uuid"
        return await self.fetch_one(conn, stmt, (role_id, tenant_id))

    async def get_role_by_name_and_tenant(self, conn: asyncpg.Connection, name: str, tenant_id: uuid.UUID) -> Optional[dict]:
        stmt = """
            SELECT 1 FROM roles 
            WHERE name = %s AND (tenant_id = %s::uuid OR tenant_id IS NULL)
        """
        return await self.fetch_one(conn, stmt, (name, tenant_id))

    async def create_role(self, conn: asyncpg.Connection, tenant_id: uuid.UUID, name: str, permissions: Any) -> dict:
        query = """
            INSERT INTO roles (role_id, tenant_id, name, permissions)
            VALUES (%s::uuid, %s::uuid, %s, %s)
            RETURNING *
        """
        new_id = uuid.uuid4()
        # asyncpg handles dict to JSON conversion if we pass it directly
        return await self.execute_returning(conn, query, (
            new_id, tenant_id, name, json.dumps(permissions) if isinstance(permissions, (dict, list)) else permissions
        ))

    async def update_role(self, conn: asyncpg.Connection, role_id: uuid.UUID, update_data: dict) -> Optional[dict]:
        if not update_data:
            return await self.get_role(conn, role_id)
        
        # Handle dict/list fields for JSONB
        processed_data = {}
        for k, v in update_data.items():
            if isinstance(v, (dict, list)):
                processed_data[k] = json.dumps(v)
            else:
                processed_data[k] = v

        set_clause = ", ".join([f"{k} = %s" for k in processed_data.keys()])
        query = f"UPDATE roles SET {set_clause}, updated_on = CURRENT_TIMESTAMP WHERE role_id = %s::uuid RETURNING *"
        params = list(processed_data.values()) + [role_id]
        return await self.execute_returning(conn, query, tuple(params))

    async def delete_role(self, conn: asyncpg.Connection, role_id: uuid.UUID) -> bool:
        query = "DELETE FROM roles WHERE role_id = %s::uuid RETURNING role_id"
        result = await self.fetch_one(conn, query, (role_id,))
        return result is not None

    async def is_role_assigned_to_users(self, conn: asyncpg.Connection, role_id: uuid.UUID) -> bool:
        user_check = await self.fetch_one(conn, "SELECT 1 FROM users WHERE role_id = %s::uuid", (role_id,))
        return user_check is not None
