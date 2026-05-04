import psycopg
from typing import List, Optional
import uuid
import json
from datetime import datetime
from app.services.db.base_db_service import BaseDBService

class ReportDBService(BaseDBService):
    REPORT_QUERY = """
    SELECT r.*, row_to_json(t_data) as template
    FROM generated_reports r
    LEFT JOIN (SELECT template_id, template_name, description FROM templates) t_data ON r.template_id = t_data.template_id
    JOIN users u ON r.user_id = u.user_id
    """

    async def list_reports(self, conn: psycopg.AsyncConnection, tenant_id: uuid.UUID, limit: int = 100, offset: int = 0, search: Optional[str] = None) -> List[dict]:
        print(f"DEBUG: list_reports called for tenant {tenant_id}")
        query = self.REPORT_QUERY + " WHERE u.tenant_id = %s::uuid"
        params = [tenant_id]
        if search:
            query += " AND (r.title ILIKE %s OR r.content_markdown ILIKE %s)"
            params.extend([f"%{search}%", f"%{search}%"])
        query += " ORDER BY r.created_on DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        return await self.fetch_all(conn, query, tuple(params))

    async def get_report(self, conn: psycopg.AsyncConnection, report_id: uuid.UUID, tenant_id: uuid.UUID) -> Optional[dict]:
        query = self.REPORT_QUERY + " WHERE r.report_id = %s::uuid AND u.tenant_id = %s::uuid"
        return await self.fetch_one(conn, query, (report_id, tenant_id))

    async def get_report_versions(self, conn: psycopg.AsyncConnection, report_id: uuid.UUID, tenant_id: uuid.UUID) -> List[dict]:
        query = self.REPORT_QUERY + " WHERE (r.report_id = %s::uuid OR r.parent_id = %s::uuid) AND u.tenant_id = %s::uuid ORDER BY r.version ASC"
        return await self.fetch_all(conn, query, (report_id, report_id, tenant_id))

    async def create_report(self, conn: psycopg.AsyncConnection, report_data: dict) -> dict:
        columns = list(report_data.keys())
        placeholders = ["%s"] * len(columns)
        values = []
        for v in report_data.values():
            if isinstance(v, (dict, list)):
                values.append(json.dumps(v))
            else:
                values.append(v)

        query = f"INSERT INTO generated_reports ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING *"
        report = await self.execute_returning(conn, query, tuple(values))
        return report

    async def delete_report(self, conn: psycopg.AsyncConnection, report_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        # Check ownership first
        query = "SELECT 1 FROM generated_reports r JOIN users u ON r.user_id = u.user_id WHERE r.report_id = %s::uuid AND u.tenant_id = %s::uuid"
        if not await self.fetch_one(conn, query, (report_id, tenant_id)):
            return False

        await self.execute(conn, "DELETE FROM generated_reports WHERE report_id = %s::uuid", (report_id,))
        return True
