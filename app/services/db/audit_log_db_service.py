import asyncpg
from typing import List, Optional
import uuid
from datetime import datetime
import json
from app.services.db.base_db_service import BaseDBService

class AuditLogDBService(BaseDBService):
    async def list_logs(self, conn: asyncpg.Connection, tenant_id: uuid.UUID, limit: int = 100, offset: int = 0, search: Optional[str] = None) -> List[dict]:
        query = "SELECT * FROM audit_logs WHERE tenant_id = %s::uuid"
        params = [tenant_id]
        if search:
            query += " AND (action ILIKE %s OR resource_type ILIKE %s OR details::text ILIKE %s)"
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
        query += " ORDER BY created_on DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        return await self.fetch_all(conn, query, tuple(params))

    async def create_log(
        self, 
        conn: asyncpg.Connection, 
        tenant_id: uuid.UUID, 
        action: str, 
        resource_type: str, 
        resource_id: Optional[str] = None, 
        details: Optional[dict] = None,
        user_id: Optional[uuid.UUID] = None,
        ip_address: Optional[str] = None
    ) -> dict:
        query = """
            INSERT INTO audit_logs (log_id, tenant_id, user_id, action, resource_type, resource_id, details, ip_address, created_on, updated_on)
            VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        new_id = uuid.uuid4()
        now = datetime.now()
        details_json = json.dumps(details) if details else None
        return await self.execute_returning(conn, query, (new_id, tenant_id, user_id, action, resource_type, resource_id, details_json, ip_address, now, now))

    @staticmethod
    async def record_audit_log(
        conn: asyncpg.Connection,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None
    ):
        """
        Intelligent helper to record audit logs without requiring a service instance.
        """
        service = AuditLogDBService()
        try:
            await service.create_log(conn, tenant_id, action, resource_type, resource_id, details, user_id, ip_address)
        except Exception as e:
            print(f"FAILED TO RECORD AUDIT LOG: {e}")
